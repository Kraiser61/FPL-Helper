import sqlite3
from typing import List, Optional
from datetime import datetime
from data.database import db_manager
from data.models import TeamDTO, EventDTO, FixtureDTO
from utils.logger import app_logger

class FixtureRepository:
    """Repository for managing teams, gameweeks, and fixtures in the SQLite database."""

    @staticmethod
    def upsert_team(team: TeamDTO, season_id: int):
        FixtureRepository.upsert_many_teams([team], season_id)

    @staticmethod
    def upsert_many_teams(teams: List[TeamDTO], season_id: int):
        """Batch upserts multiple teams within a single transaction."""
        query = """
        INSERT INTO teams (
            id, season_id, name, short_name, strength, strength_overall_home, 
            strength_overall_away, strength_attack_home, strength_attack_away, 
            strength_defence_home, strength_defence_away
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            short_name = excluded.short_name,
            strength = excluded.strength,
            strength_overall_home = excluded.strength_overall_home,
            strength_overall_away = excluded.strength_overall_away,
            strength_attack_home = excluded.strength_attack_home,
            strength_attack_away = excluded.strength_attack_away,
            strength_defence_home = excluded.strength_defence_home,
            strength_defence_away = excluded.strength_defence_away,
            updated_at = CURRENT_TIMESTAMP
        """
        records = [
            (
                t.id, season_id, t.name, t.short_name, t.strength, 
                t.strength_overall_home, t.strength_overall_away, 
                t.strength_attack_home, t.strength_attack_away, 
                t.strength_defence_home, t.strength_defence_away
            )
            for t in teams
        ]
        with db_manager.get_connection() as conn:
            try:
                conn.executemany(query, records)
                conn.commit()
            except sqlite3.Error as e:
                app_logger.error(f"Failed to batch upsert teams: {e}")

    @staticmethod
    def upsert_gameweek(gw: EventDTO, season_id: int):
        FixtureRepository.upsert_many_gameweeks([gw], season_id)

    @staticmethod
    def upsert_many_gameweeks(gws: List[EventDTO], season_id: int):
        """Batch upserts multiple gameweeks within a single transaction."""
        query = """
        INSERT INTO gameweeks (
            id, season_id, name, deadline_time, finished, is_current, 
            is_next, average_score, highest_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            deadline_time = excluded.deadline_time,
            finished = excluded.finished,
            is_current = excluded.is_current,
            is_next = excluded.is_next,
            average_score = excluded.average_score,
            highest_score = excluded.highest_score,
            updated_at = CURRENT_TIMESTAMP
        """
        records = []
        for gw in gws:
            dl_time_str = gw.deadline_time.isoformat() if isinstance(gw.deadline_time, datetime) else gw.deadline_time
            records.append((
                gw.id, season_id, gw.name, dl_time_str, gw.finished, 
                gw.is_current, gw.is_next, gw.average_entry_score, gw.highest_score
            ))
            
        with db_manager.get_connection() as conn:
            try:
                conn.executemany(query, records)
                conn.commit()
            except sqlite3.Error as e:
                app_logger.error(f"Failed to batch upsert gameweeks: {e}")

    @staticmethod
    def upsert_fixture(fixture: FixtureDTO, season_id: int):
        FixtureRepository.upsert_many_fixtures([fixture], season_id)

    @staticmethod
    def upsert_many_fixtures(fixtures: List[FixtureDTO], season_id: int):
        """Batch upserts multiple fixtures within a single transaction."""
        query = """
        INSERT INTO fixtures (
            id, season_id, gameweek_id, team_home_id, team_away_id, 
            team_h_difficulty, team_a_difficulty, team_h_score, team_a_score, 
            kickoff_time, started, finished
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            gameweek_id = excluded.gameweek_id,
            team_home_id = excluded.team_home_id,
            team_away_id = excluded.team_away_id,
            team_h_difficulty = excluded.team_h_difficulty,
            team_a_difficulty = excluded.team_a_difficulty,
            team_h_score = excluded.team_h_score,
            team_a_score = excluded.team_a_score,
            kickoff_time = excluded.kickoff_time,
            started = excluded.started,
            finished = excluded.finished,
            updated_at = CURRENT_TIMESTAMP
        """
        records = []
        for fixture in fixtures:
            ko_time_str = fixture.kickoff_time.isoformat() if fixture.kickoff_time else None
            records.append((
                fixture.id, season_id, fixture.event, fixture.team_h, fixture.team_a,
                fixture.team_h_difficulty, fixture.team_a_difficulty, 
                fixture.team_h_score, fixture.team_a_score, ko_time_str, 
                fixture.started, fixture.finished
            ))
            
        with db_manager.get_connection() as conn:
            try:
                conn.executemany(query, records)
                conn.commit()
            except sqlite3.Error as e:
                app_logger.error(f"Failed to batch upsert fixtures: {e}")

    @staticmethod
    def get_fixtures_by_gw(gw_id: int) -> List[sqlite3.Row]:
        """Fetches all fixtures for a specific gameweek."""
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM fixtures WHERE gameweek_id = ? ORDER BY kickoff_time ASC", (gw_id,))
            return cursor.fetchall()

    @staticmethod
    def get_upcoming_fixtures(team_id: int, limit: int = 5) -> List[sqlite3.Row]:
        """Fetches upcoming fixtures for a given team."""
        query = """
        SELECT f.*, gw.name as gw_name
        FROM fixtures f
        LEFT JOIN gameweeks gw ON f.gameweek_id = gw.id
        WHERE (f.team_home_id = ? OR f.team_away_id = ?) 
          AND f.finished = 0
        ORDER BY f.kickoff_time ASC
        LIMIT ?
        """
        with db_manager.get_connection() as conn:
            cursor = conn.execute(query, (team_id, team_id, limit))
            return cursor.fetchall()
