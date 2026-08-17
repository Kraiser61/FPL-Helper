import sqlite3
from typing import List, Optional, Any
from data.database import db_manager
from data.models import UserPickDTO, UserTeamDTO
from utils.logger import app_logger

class UserRepository:
    """Repository for managing the FPL Manager's user profile, squad picks, transfers, and chips."""

    @staticmethod
    def upsert_user_profile(manager_id: int, season_id: int, email: str = "", player_name: str = "", team_name: str = "", overall_points: int = 0, overall_rank: int = 0):
        query = """
        INSERT INTO user_profile (id, email, player_name, team_name, overall_points, overall_rank, season_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email = excluded.email,
            player_name = excluded.player_name,
            team_name = excluded.team_name,
            overall_points = excluded.overall_points,
            overall_rank = excluded.overall_rank,
            updated_at = CURRENT_TIMESTAMP
        """
        with db_manager.get_connection() as conn:
            conn.execute(query, (manager_id, email, player_name, team_name, overall_points, overall_rank, season_id))
            conn.commit()

    @staticmethod
    def get_user_profile(manager_id: int) -> Optional[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM user_profile WHERE id = ?", (manager_id,))
            return cursor.fetchone()

    @staticmethod
    def save_user_picks(gw_id: int, user_pick_data: UserPickDTO):
        """Saves a manager's 15-player squad selection for a given GW."""
        history = user_pick_data.entry_history
        chip = user_pick_data.active_chip

        delete_query = "DELETE FROM user_gw_picks WHERE gameweek_id = ?"
        insert_query = """
        INSERT INTO user_gw_picks (
            gameweek_id, player_id, position, multiplier, is_captain, is_vice_captain,
            gw_points, gw_total_points, gw_rank, gw_value, gw_bank, gw_transfers, gw_transfer_cost, gw_points_on_bench, active_chip
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with db_manager.get_connection() as conn:
            try:
                # First delete existing picks for this GW
                conn.execute(delete_query, (gw_id,))
                
                # Insert the new ones
                for pick in user_pick_data.picks:
                    conn.execute(insert_query, (
                        gw_id, pick.element, pick.position, pick.multiplier, 
                        pick.is_captain, pick.is_vice_captain,
                        history.points, history.total_points, history.rank,
                        history.value, history.bank, history.event_transfers,
                        history.event_transfers_cost, history.points_on_bench, chip
                    ))
                conn.commit()
            except sqlite3.Error as e:
                app_logger.error(f"Failed to save user picks for GW {gw_id}: {e}")

    @staticmethod
    def get_user_picks(gw_id: int) -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM user_gw_picks WHERE gameweek_id = ? ORDER BY position ASC", (gw_id,))
            return cursor.fetchall()

    @staticmethod
    def update_chip_status(season_id: int, chips: List[Any]):
        """Updates the available/used status of chips from UserTeamDTO."""
        query = """
        INSERT INTO chip_usage (season_id, chip_name, status)
        VALUES (?, ?, ?)
        """
        # In a real scenario, this would reconcile with existing chips in the DB
        # For Phase 1/2 MVP, we'll keep it simple
        with db_manager.get_connection() as conn:
            try:
                # Clear un-used chips to refresh (simplistic approach)
                conn.execute("DELETE FROM chip_usage WHERE season_id = ? AND status = 'available'", (season_id,))
                for chip in chips:
                    # status_for_entry is often 'available' or 'active'
                    status = 'available' if chip.status_for_entry in ['available', 'active'] else chip.status_for_entry
                    conn.execute(query, (season_id, chip.name, status))
                conn.commit()
            except sqlite3.Error as e:
                 app_logger.error(f"Failed to update chip status: {e}")

    @staticmethod
    def get_chip_usage(season_id: int) -> List[sqlite3.Row]:
        with db_manager.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM chip_usage WHERE season_id = ?", (season_id,))
            return cursor.fetchall()
