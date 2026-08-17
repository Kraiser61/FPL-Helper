import json
from typing import Dict, Any, List
from core.xp_calculator import XPCalculator, FixtureContext
from core.transfer_optimizer import TransferOptimizer, PlayerData
from core.lineup_selector import LineupSelector, SquadPlayer
from core.captain_selector import CaptainSelector, CaptaincyCandidate
from core.chip_advisor import ChipAdvisor
from data.database import db_manager
from utils.logger import app_logger

class RecommendationEngine:
    """
    Orchestrates all sub-decision modules (xP, Optimizer, Lineup, Captain, Chip)
    to generate a comprehensive JSON recommendation and persist it.
    """
    
    def __init__(self, player_repo, fixture_repo, user_repo):
        self.player_repo = player_repo
        self.fixture_repo = fixture_repo
        self.user_repo = user_repo
        
    def generate_full_recommendation(self, gw_id: int, current_bank: float, free_transfers: int) -> Dict[str, Any]:
        """
        Runs the full pipeline for a given gameweek.
        """
        app_logger.info(f"Starting Recommendation Engine Pipeline for GW {gw_id}")
        
        # 1. Prepare Data (In real app, this builds from DB records)
        # Here we mock the data extraction for the architectural layout
        squad_players_mock = self._build_squad_players()
        all_players_mock = self._build_all_players_for_optimizer()
        
        # 2. Lineup & Bench Selection
        lineup_selector = LineupSelector(squad_players_mock)
        lineup_result = lineup_selector.select_optimal_lineup()
        
        # 3. Captaincy Selection
        cap_candidates = [
            CaptaincyCandidate(
                id=pid, 
                xp=next(p.xp for p in squad_players_mock if p.id == pid), 
                chance_of_playing=next(p.chance_of_playing for p in squad_players_mock if p.id == pid), 
                is_force_captain=False
            ) for pid in lineup_result.starting_11
        ]
        captain_selector = CaptainSelector(cap_candidates)
        cap_result = captain_selector.select()
        
        # 4. Transfer Optimization
        transfer_opt = TransferOptimizer(all_players_mock, current_bank, free_transfers)
        transfers = transfer_opt.optimize(num_suggestions=5)
        
        # 5. Chip Advice (Example: evaluating Free Hit)
        current_xp = lineup_result.total_xp
        # optimal_xp_1gw = ... (would require running LineupSelector on transfer_opt's top result)
        chip_advice = ChipAdvisor.evaluate_free_hit(
            is_available=True, is_bgw=False, current_squad_1gw_xp=current_xp, optimal_squad_1gw_xp=current_xp + 10.0
        )
        
        # 6. Package JSON
        recommendation_payload = {
            "gameweek": gw_id,
            "lineup": {
                "starting_11": lineup_result.starting_11,
                "bench_order": lineup_result.bench_order,
                "formation": lineup_result.formation,
                "base_xp": lineup_result.total_xp,
                "captain_id": cap_result.captain_id,
                "vice_captain_id": cap_result.vice_captain_id,
                "total_expected_xp": lineup_result.total_xp + cap_result.expected_extra_points
            },
            "transfers": [
                {
                    "players_out": t.players_out,
                    "players_in": t.players_in,
                    "net_xp_gain": t.net_xp_gain,
                    "hit_cost": t.hit_cost
                } for t in transfers
            ],
            "chip_advice": {
                "name": chip_advice.chip_name,
                "should_play": chip_advice.should_play,
                "reasoning": chip_advice.reasoning
            }
        }
        
        self._persist_recommendation(gw_id, "full_weekly", recommendation_payload, recommendation_payload["lineup"]["total_expected_xp"])
        
        app_logger.info(f"Recommendation Engine Pipeline completed for GW {gw_id}")
        return recommendation_payload
        
    def _persist_recommendation(self, gw_id: int, rec_type: str, payload: dict, xp_score: float):
        query = """
        INSERT INTO recommendation_history (gameweek_id, recommendation_type, recommendation_json, xp_score)
        VALUES (?, ?, ?, ?)
        """
        with db_manager.get_connection() as conn:
            conn.execute(query, (gw_id, rec_type, json.dumps(payload), xp_score))
            conn.commit()

    # -- Mock Data Builders for Phase 6 Integration Structure --
    def _build_squad_players(self) -> List[SquadPlayer]:
        # Returns 15 dummy SquadPlayer objects
        return [SquadPlayer(id=i, element_type=(1 if i < 2 else 2 if i < 7 else 3 if i < 12 else 4), 
                            xp=5.0 + (i%5), chance_of_playing=1.0, is_locked_starter=False) for i in range(1, 16)]
                            
    def _build_all_players_for_optimizer(self) -> List[PlayerData]:
        # Returns dummy PlayerData for optimizer
        return [PlayerData(id=i, element_type=(1 if i < 2 else 2 if i < 7 else 3 if i < 12 else 4),
                           team_id=1, now_cost=50, selling_price=50, xp=5.0+(i%5), is_locked=False, in_current_squad=(i<16)) for i in range(1, 100)]
