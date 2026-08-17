import pulp
from typing import List, Dict, Tuple
from dataclasses import dataclass
from utils.logger import app_logger

@dataclass
class PlayerData:
    id: int
    element_type: int
    team_id: int
    now_cost: int
    selling_price: int
    xp: float
    is_locked: bool # e.g. 'no_sell'
    in_current_squad: bool

@dataclass
class TransferSuggestion:
    players_out: List[int]
    players_in: List[int]
    net_xp_gain: float
    hit_cost: int
    budget_remaining: int

class TransferOptimizer:
    """
    Solves the constrained optimization problem for FPL transfers using PuLP (Linear Programming).
    Includes safe fallback mechanisms when MILP constraints are Infeasible.
    """

    def __init__(
        self, 
        players: List[PlayerData], 
        current_bank: int, 
        free_transfers: int
    ):
        self.players = players
        self.current_bank = current_bank
        self.free_transfers = free_transfers
        
    def optimize(self, num_suggestions: int = 5, lookahead_gw: int = 5) -> List[TransferSuggestion]:
        """
        Calculates the best possible transfers maximizing xP while satisfying constraints.
        Returns top N suggestions with fallback if MILP is infeasible.
        """
        suggestions = []
        
        # Base constraints
        total_players_required = 15
        pos_limits = {1: 2, 2: 5, 3: 5, 4: 3} # GKP, DEF, MID, FWD
        max_from_team = 3
        
        current_squad = [p for p in self.players if p.in_current_squad]
        if not current_squad:
            app_logger.warning("No current squad provided to TransferOptimizer.")
            return []
            
        squad_value = sum(p.selling_price for p in current_squad)
        total_budget = squad_value + self.current_bank
        
        try:
            # Formulate MILP
            prob = pulp.LpProblem("FPL_Transfer_Optimization", pulp.LpMaximize)
            player_vars = pulp.LpVariable.dicts("player", [p.id for p in self.players], cat='Binary')
            
            # Objective Function: Maximize total xP
            prob += pulp.lpSum([p.xp * player_vars[p.id] for p in self.players]), "Total_Expected_Points"
            
            # Constraints
            prob += pulp.lpSum([player_vars[p.id] for p in self.players]) == total_players_required, "Total_Players"
            
            for pos_id, limit in pos_limits.items():
                prob += pulp.lpSum([player_vars[p.id] for p in self.players if p.element_type == pos_id]) == limit, f"Pos_{pos_id}_Limit"
                
            teams = set(p.team_id for p in self.players)
            for team_id in teams:
                prob += pulp.lpSum([player_vars[p.id] for p in self.players if p.team_id == team_id]) <= max_from_team, f"Team_{team_id}_Limit"
                
            prob += pulp.lpSum([
                player_vars[p.id] * (p.now_cost if not p.in_current_squad else p.selling_price) 
                for p in self.players
            ]) <= total_budget, "Budget_Limit"
            
            # User Locks (no_sell)
            for p in current_squad:
                if p.is_locked:
                    prob += player_vars[p.id] == 1, f"Lock_Player_{p.id}"
                    
            for k in range(0, min(3, len(current_squad) + 1)):
                prob_k = prob.copy()
                prob_k += pulp.lpSum([player_vars[p.id] for p in self.players if not p.in_current_squad]) == k, "Exact_Transfers"
                
                # Solve quietly
                prob_k.solve(pulp.PULP_CBC_CMD(msg=0))
                
                if pulp.LpStatus[prob_k.status] == 'Optimal':
                    selected_ids = [p.id for p in self.players if player_vars[p.id].value() == 1.0]
                    
                    players_in = [pid for pid in selected_ids if not any(p.id == pid and p.in_current_squad for p in self.players)]
                    players_out = [p.id for p in current_squad if p.id not in selected_ids]
                    
                    hit_cost = max(0, (k - self.free_transfers) * 4)
                    raw_xp = pulp.value(prob_k.objective) or 0.0
                    
                    base_xp = sum(p.xp for p in current_squad)
                    net_xp = raw_xp - base_xp - hit_cost
                    
                    cost_in = sum(p.now_cost for p in self.players if p.id in players_in)
                    revenue_out = sum(p.selling_price for p in current_squad if p.id in players_out)
                    budget_remaining = self.current_bank + revenue_out - cost_in
                    
                    suggestions.append(TransferSuggestion(
                        players_out=players_out,
                        players_in=players_in,
                        net_xp_gain=net_xp,
                        hit_cost=hit_cost,
                        budget_remaining=budget_remaining
                    ))
        except Exception as e:
            app_logger.error(f"Error during PuLP optimization: {e}")

        # Fallback if solver yielded no valid suggestions (Infeasible due to locks/budget)
        if not suggestions:
            app_logger.warning("PuLP solver yielded 0 suggestions. Returning fallback (No-Op transfer).")
            suggestions.append(TransferSuggestion(
                players_out=[],
                players_in=[],
                net_xp_gain=0.0,
                hit_cost=0,
                budget_remaining=self.current_bank
            ))

        # Sort by highest net XP gain
        suggestions.sort(key=lambda x: x.net_xp_gain, reverse=True)
        return suggestions[:num_suggestions]
