import sqlite3
from typing import List, Optional, Dict, Any
from data.database import db_manager
from data.models import PlayerDTO
from utils.logger import app_logger

class PlayerRepository:
    """Repository for managing players, price changes, and user locks in the SQLite database."""
    
    @staticmethod
    def upsert_player(player: PlayerDTO, season_id: int):
        """Inserts or updates a single player record."""
        PlayerRepository.upsert_many_players([player], season_id)

    @staticmethod
    def upsert_many_players(players: List[PlayerDTO], season_id: int):
        """Batch upserts multiple players within a single transaction."""
        query = """
        INSERT INTO players (
            id, season_id, team_id, web_name, element_type, now_cost, form, 
            total_points, selected_by_percent, status, news, 
            chance_of_playing_next, chance_of_playing_this, minutes, 
            goals_scored, assists, clean_sheets, bonus, bps, 
            expected_goals, expected_assists, expected_goal_involvements, 
            expected_goals_conceded, ict_index, transfers_in_event, transfers_out_event,
            yellow_cards, red_cards, points_per_game, value_form, value_season,
            influence, creativity, threat, ep_next, ep_this
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(id) DO UPDATE SET
            team_id = excluded.team_id,
            web_name = excluded.web_name,
            element_type = excluded.element_type,
            now_cost = excluded.now_cost,
            form = excluded.form,
            total_points = excluded.total_points,
            selected_by_percent = excluded.selected_by_percent,
            status = excluded.status,
            news = excluded.news,
            chance_of_playing_next = excluded.chance_of_playing_next,
            chance_of_playing_this = excluded.chance_of_playing_this,
            minutes = excluded.minutes,
            goals_scored = excluded.goals_scored,
            assists = excluded.assists,
            clean_sheets = excluded.clean_sheets,
            bonus = excluded.bonus,
            bps = excluded.bps,
            expected_goals = excluded.expected_goals,
            expected_assists = excluded.expected_assists,
            expected_goal_involvements = excluded.expected_goal_involvements,
            expected_goals_conceded = excluded.expected_goals_conceded,
            ict_index = excluded.ict_index,
            transfers_in_event = excluded.transfers_in_event,
            transfers_out_event = excluded.transfers_out_event,
            yellow_cards = excluded.yellow_cards,
            red_cards = excluded.red_cards,
            points_per_game = excluded.points_per_game,
            value_form = excluded.value_form,
            value_season = excluded.value_season,
            influence = excluded.influence,
            creativity = excluded.creativity,
            threat = excluded.threat,
            ep_next = excluded.ep_next,
            ep_this = excluded.ep_this,
            updated_at = CURRENT_TIMESTAMP
        """
        
        records = [
            (
                p.id, season_id, p.team, p.web_name, p.element_type, p.now_cost, 
                p.form, p.total_points, p.selected_by_percent, p.status, 
                p.news, p.chance_of_playing_next_round, p.chance_of_playing_this_round, 
                p.minutes, p.goals_scored, p.assists, p.clean_sheets, 
                p.bonus, p.bps, p.expected_goals, p.expected_assists, 
                p.expected_goal_involvements, p.expected_goals_conceded, p.ict_index,
                p.transfers_in_event, p.transfers_out_event,
                p.yellow_cards, p.red_cards, p.points_per_game, p.value_form, p.value_season,
                p.influence, p.creativity, p.threat, p.ep_next, p.ep_this
            )
            for p in players
        ]
        
        with db_manager.get_connection() as conn:
            try:
                conn.executemany(query, records)
                conn.commit()
            except sqlite3.Error as e:
                app_logger.error(f"Failed to batch upsert players: {e}")

    @staticmethod
    def get_all_players() -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM players")
            return cursor.fetchall()

    @staticmethod
    def get_player_by_id(player_id: int) -> Optional[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM players WHERE id = ?", (player_id,))
            return cursor.fetchone()

    @staticmethod
    def get_players_by_team(team_id: int) -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM players WHERE team_id = ?", (team_id,))
            return cursor.fetchall()

    @staticmethod
    def get_players_by_position(element_type: int) -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM players WHERE element_type = ?", (element_type,))
            return cursor.fetchall()

    @staticmethod
    def log_price_change(player_id: int, old_price: int, new_price: int, change_date: str):
        """Records a price change for a player."""
        query = "INSERT INTO price_changes (player_id, old_price, new_price, change_date) VALUES (?, ?, ?, ?)"
        with db_manager.get_connection() as conn:
            conn.execute(query, (player_id, old_price, new_price, change_date))
            conn.commit()

    @staticmethod
    def get_price_changes_by_player(player_id: int) -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM price_changes WHERE player_id = ? ORDER BY change_date DESC", (player_id,))
            return cursor.fetchall()

    @staticmethod
    def add_player_lock(player_id: int, lock_type: str, reason: Optional[str] = None, expires_gw: Optional[int] = None):
        """Adds a user lock (e.g., 'no_sell', 'force_captain') for a player."""
        query = """
        INSERT INTO player_locks (player_id, lock_type, reason, expires_gw) 
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            lock_type = excluded.lock_type,
            reason = excluded.reason,
            expires_gw = excluded.expires_gw
        """
        with db_manager.get_connection() as conn:
            conn.execute(query, (player_id, lock_type, reason, expires_gw))
            conn.commit()

    @staticmethod
    def get_all_player_locks() -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM player_locks")
            return cursor.fetchall()

    @staticmethod
    def remove_player_lock(player_id: int):
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM player_locks WHERE player_id = ?", (player_id,))
            conn.commit()
