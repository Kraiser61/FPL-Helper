import math
from typing import Dict, List, Optional
from dataclasses import dataclass
from utils.logger import app_logger

@dataclass
class FixtureContext:
    fdr: int
    is_home: bool
    opponent_strength_attack: int
    opponent_strength_defence: int
    opponent_team_id: int = -1
    matches_in_gw: int = 1  # 0 for BGW, 1 for SGW, 2 for DGW (Ben Crellin Model)

class XPCalculator:
    """
    Calculates Expected Points (xP) for FPL players based on FFS & FPL Review methodologies.
    Features Split FDR and Home/Away Venue Multipliers (1.12x Attack, 1.15x Clean Sheet).
    """
    
    FORM_DECAY_LAMBDA = 0.15
    
    # Calibrated Home/Away Venue Multipliers (FFS/FPL Review baseline: ~6-10% venue effect)
    HOME_MULTIPLIERS = {1: 1.08, 2: 1.10, 3: 1.06, 4: 1.06}
    AWAY_MULTIPLIERS = {1: 0.92, 2: 0.90, 3: 0.94, 4: 0.94}
    
    GOAL_POINTS = {1: 6, 2: 6, 3: 5, 4: 4}
    ASSIST_POINTS = 3
    CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}
    
    @staticmethod
    def get_fdr_multiplier(fdr: int, is_attack: bool) -> float:
        """Calibrated FDR multiplier without extreme inflation."""
        if is_attack:
            mapping = {1: 1.15, 2: 1.08, 3: 1.00, 4: 0.90, 5: 0.80}
        else:
            mapping = {1: 1.20, 2: 1.10, 3: 1.00, 4: 0.88, 5: 0.75}
        return mapping.get(fdr, 1.0)
        
    @classmethod
    def calculate_fdr_factor(cls, fdr: int, opponent_strength: int = 3, is_attack: bool = True) -> float:
        """Adjusts base FDR multiplier smoothly without compounding distortion."""
        base_multiplier = cls.get_fdr_multiplier(fdr, is_attack)
        strength = max(1, min(5, opponent_strength or 3))
        strength_adj = 1.0 + ((3 - strength) * 0.03)  # Gentle ±3% per strength delta
        return max(0.70, min(1.30, base_multiplier * strength_adj))

    @staticmethod
    def calculate_form_weight(recent_xps: List[float]) -> float:
        """Calculates normalized form multiplier centered around 1.0 with [0.85, 1.15] bounds."""
        if not recent_xps:
            return 1.0
            
        weighted_sum = 0.0
        weight_total = 0.0
        
        for i, xp in enumerate(recent_xps):
            if xp is None:
                continue
            weight = math.exp(-XPCalculator.FORM_DECAY_LAMBDA * i)
            weighted_sum += weight * xp
            weight_total += weight
            
        raw_avg = (weighted_sum / weight_total) if weight_total > 0 else 4.0
        # Normalize relative to benchmark 4.5 pts/gw
        norm_form = 1.0 + ((raw_avg - 4.5) / 15.0)
        return max(0.85, min(1.15, norm_form))

    @classmethod
    def calculate_xp_single_fixture(
        cls, 
        element_type: int,
        xg_per90: float, 
        xa_per90: float, 
        team_xgc_per90: float,
        expected_mins: float,
        fixture_ctx: FixtureContext,
        form_weight: float = 1.0,
        avg_bps_per90: float = 0.0,
        bps_to_bonus_ratio: float = 0.0,
        penalty_miss_rate: float = 0.0,
        expected_penalties: float = 0.0
    ) -> float:
        """Calculates total xP for a single fixture with calibrated rates and floor guarantee."""
        
        expected_mins = max(0.0, min(90.0, expected_mins or 0.0))
        if expected_mins <= 0:
            return 0.0
            
        is_home = fixture_ctx.is_home
        fdr = fixture_ctx.fdr or 3
        
        home_away_attack = cls.HOME_MULTIPLIERS.get(element_type, 1.06) if is_home else cls.AWAY_MULTIPLIERS.get(element_type, 0.94)
        home_away_defence = cls.HOME_MULTIPLIERS.get(element_type, 1.10) if is_home else cls.AWAY_MULTIPLIERS.get(element_type, 0.90)
        
        # --- Positional Noise Elimination & Specific Base Points ---
        if element_type == 1:
            xg_per90 = 0.0
            xa_per90 = 0.0
            saves_per90 = max(2.0, min(4.5, 3.5 - ((team_xgc_per90 or 1.2) - 1.2) * 0.5))
            xp_saves = ((saves_per90 * expected_mins / 90.0) / 3.0) * 1.0
        else:
            xp_saves = 0.0

        if element_type in (3, 4):
            team_xgc_per90 = 0.0  # Mid/Fwd do not lose points on goals conceded

        # Attack - FDR Defence of Opponent
        fdr_attack = cls.calculate_fdr_factor(fdr, fixture_ctx.opponent_strength_defence, is_attack=True)
        mins_ratio = expected_mins / 90.0
        
        xp_goal = ((xg_per90 or 0.0) * mins_ratio) * cls.GOAL_POINTS.get(element_type, 4) * fdr_attack * form_weight * home_away_attack
        xp_assist = ((xa_per90 or 0.0) * mins_ratio) * cls.ASSIST_POINTS * fdr_attack * form_weight * home_away_attack
        xp_attack = xp_goal + xp_assist
        
        # Defence - FDR Attack of Opponent
        fdr_defence = cls.calculate_fdr_factor(fdr, fixture_ctx.opponent_strength_attack, is_attack=False)
        
        # Realistic Clean Sheet Probability: Top sides ~40-50%, Average ~25-35%, Poor ~15-20%
        base_cs_prob = max(0.10, min(0.55, 0.38 - (((team_xgc_per90 or 1.2) - 1.2) * 0.12)))
        cs_prob = min(0.60, base_cs_prob * fdr_defence * home_away_defence)
        
        xp_cs = cs_prob * cls.CS_POINTS.get(element_type, 0) if expected_mins >= 60 else 0.0
        
        xp_gc = 0.0
        if element_type in (1, 2) and team_xgc_per90 > 0:
            expected_gc = (team_xgc_per90 or 1.2) * mins_ratio
            xp_gc = -int(math.floor(expected_gc / 2.0))
            
        xp_defence = xp_cs + xp_gc + xp_saves
        
        # Playing Appearance Points: 2.0 for 60+ mins, 1.0 for sub appearances
        xp_playing = 2.0 * (expected_mins / 90.0) if expected_mins >= 60 else (1.0 * (expected_mins / 45.0) if expected_mins > 0 else 0.0)
        
        # Penalty Risk
        xp_pen_risk = -((penalty_miss_rate or 0.0) * (expected_penalties or 0.0) * 2.0)
        
        total_xp = xp_attack + xp_defence + xp_playing + xp_pen_risk
        return max(0.0, total_xp)

    @classmethod
    def calculate_total_xp(
        cls,
        element_type: int,
        xg_per90: float, 
        xa_per90: float, 
        team_xgc_per90: float,
        chance_of_playing: float,
        avg_mins_per_game: float,
        fixtures: List[FixtureContext],
        recent_xps: Optional[List[float]] = None,
        avg_bps_per90: float = 0.0,
        bps_to_bonus_ratio: float = 0.0,
        penalty_miss_rate: float = 0.0,
        expected_penalties: float = 0.0
    ) -> float:
        """
        Calculates total expected points across 1 or more fixtures.
        """
        if not fixtures or chance_of_playing <= 0:
            return 0.0
            
        form_weight = cls.calculate_form_weight(recent_xps or [])
        expected_mins = chance_of_playing * (avg_mins_per_game or 90.0)
        
        total_xp = 0.0
        for fixture in fixtures:
             xp = cls.calculate_xp_single_fixture(
                 element_type=element_type,
                 xg_per90=xg_per90,
                 xa_per90=xa_per90,
                 team_xgc_per90=team_xgc_per90,
                 expected_mins=expected_mins,
                 fixture_ctx=fixture,
                 form_weight=form_weight,
                 avg_bps_per90=avg_bps_per90,
                 bps_to_bonus_ratio=bps_to_bonus_ratio,
                 penalty_miss_rate=penalty_miss_rate,
                 expected_penalties=expected_penalties
             )
             total_xp += xp
             
        if len(fixtures) > 1:
             total_xp *= 0.9
             
        return total_xp
