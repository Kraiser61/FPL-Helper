import math
from typing import Dict, Any, Optional, List, Tuple
from utils.logger import app_logger

def calculate_true_probability(odd: float, market_odds: List[float]) -> float:
    """
    Calculates True Probability by removing Overround factor.
    Formula: Overround_Factor = Sum(1 / Odds_i)
             P_real = (1 / Odd) / Overround_Factor
    """
    if odd <= 0.0 or any(o <= 0.0 for o in market_odds):
        raise ValueError("Oranlar 0'dan büyük olmalıdır.")
        
    overround_factor = sum(1.0 / o for o in market_odds)
    p_real = (1.0 / odd) / overround_factor
    return round(p_real, 4)

def blend_xp_and_detect_anomaly_standardized(
    xp_model: float, 
    xp_bookies: float, 
    current_gw: int
) -> Tuple[float, str]:
    """
    Blends internal model xP with bookmaker derived xP using standardized relative percentage deviation D_pct.
    D_pct = |xp_model - xp_bookies| / max(xp_model, xp_bookies, 1.0)
    
    Season Base Weights:
    - GW 1-3: w_internal = 0.55, w_bookies = 0.45
    - GW 4-15: w_internal = 0.75, w_bookies = 0.25
    - GW 16+: w_internal = 0.80, w_bookies = 0.20
    
    Thresholds:
    - D_pct < 0.25 -> NORMAL (OK)
    - 0.25 <= D_pct < 0.50 -> INCELEME GEREKLI (WARN)
    - D_pct >= 0.50 -> KRITIK SAPMA (CRITICAL) (Bookmaker weight overridden to 40%).
    """
    if current_gw <= 3:
        w_internal, w_bookies = 0.55, 0.45
    elif current_gw <= 15:
        w_internal, w_bookies = 0.75, 0.25
    else:
        w_internal, w_bookies = 0.80, 0.20

    d_pct = abs(xp_model - xp_bookies) / max(xp_model, xp_bookies, 1.0)
    
    if d_pct < 0.25:
        status = "NORMAL (OK)"
    elif d_pct < 0.50:
        status = "INCELEME GEREKLI (WARN)"
    else:
        status = "KRITIK SAPMA (CRITICAL)"
        w_internal = 0.60
        w_bookies = 0.40  # Override bookmaker weight to 40%
        
    xp_final = (w_internal * xp_model) + (w_bookies * xp_bookies)
    return round(xp_final, 3), status

def blend_xp_and_detect_anomaly(
    xp_model: float, 
    xp_bookies: float, 
    current_gw: int
) -> Tuple[float, str]:
    """Backward-compatible wrapper for standardized anomaly blending."""
    return blend_xp_and_detect_anomaly_standardized(xp_model, xp_bookies, current_gw)

class BettingOddsManager:
    """
    Betting Odds Calibration & Implied Probability Layer.
    Converts market closing odds (Implied Team Goals, Clean Sheet Odds, Goalscorer Odds)
    into calibrated expected goals and clean sheet probabilities for xP engine.
    Acts as ground-truth market consensus calibration.
    """

    @staticmethod
    def decimal_odds_to_probability(odds: float, overround_margin: float = 0.05) -> float:
        """Converts decimal odds to overround-adjusted fair probability."""
        if not odds or odds <= 1.0:
            return 0.0
        raw_prob = 1.0 / odds
        fair_prob = raw_prob / (1.0 + overround_margin)
        return round(max(0.0, min(1.0, fair_prob)), 4)

    @classmethod
    def calibrate_clean_sheet_prob(cls, team_id: int, base_cs_prob: float, cs_odds: Optional[float] = None) -> float:
        """
        Calibrates base clean sheet probability against market clean sheet odds if available.
        """
        if cs_odds and cs_odds > 1.0:
            market_cs_prob = cls.decimal_odds_to_probability(cs_odds)
            calibrated = (0.60 * market_cs_prob) + (0.40 * base_cs_prob)
            return round(max(0.0, min(0.95, calibrated)), 4)
        return base_cs_prob

    @classmethod
    def calibrate_anytime_goalscorer_xg(cls, base_xg: float, goalscorer_odds: Optional[float] = None) -> float:
        """
        Calibrates player xG against market anytime goalscorer odds.
        """
        if goalscorer_odds and goalscorer_odds > 1.0:
            market_goal_prob = cls.decimal_odds_to_probability(goalscorer_odds)
            if market_goal_prob < 0.95:
                implied_xg = -math.log(1.0 - market_goal_prob)
            else:
                implied_xg = 2.5
            calibrated_xg = (0.50 * implied_xg) + (0.50 * base_xg)
            return round(max(0.0, calibrated_xg), 3)
        return base_xg

    @classmethod
    def calibrate_and_blend_player_xp(
        cls,
        xp_model: float,
        current_gw: int,
        ags_odds: Optional[float] = None,
        cs_odds: Optional[float] = None,
        aa_odds: Optional[float] = None,
        market_odds_ags: Optional[List[float]] = None,
        market_odds_cs: Optional[List[float]] = None
    ) -> Tuple[float, str]:
        """
        Derives xP_bookies from market odds (AGS, CS, AA) clearing overround margins 
        and blends it with xp_model using standardized anomaly detection.
        """
        xp_bookies = 0.0
        has_data = False
        
        if ags_odds and ags_odds > 1.0:
            p_ags = calculate_true_probability(ags_odds, market_odds_ags or [ags_odds, 1.8])
            xp_bookies += p_ags * 4.5
            has_data = True
            
        if cs_odds and cs_odds > 1.0:
            p_cs = calculate_true_probability(cs_odds, market_odds_cs or [cs_odds, 1.5])
            xp_bookies += p_cs * 4.0
            has_data = True
            
        if aa_odds and aa_odds > 1.0:
            p_aa = 1.0 / (aa_odds * 1.05)
            xp_bookies += p_aa * 3.0
            has_data = True
            
        if not has_data:
            return xp_model, "NO_BOOKIE_DATA [OK]"
            
        return blend_xp_and_detect_anomaly_standardized(xp_model, xp_bookies, current_gw)

if __name__ == "__main__":
    print("--- SANITY CHECK: core/betting_odds.py ---")
    
    # 1. True probability calculation
    p_true = calculate_true_probability(2.0, [2.0, 1.90])
    print(f"True Probability for 2.0 (Market [2.0, 1.9]): {p_true}")
    assert p_true < 0.50
    
    # 2. Normal blending (D_pct < 0.25)
    # xp_model = 5.0, xp_bookies = 5.5 -> diff = 0.5, max = 5.5 -> D_pct = 0.09 < 0.25
    xp_n, stat_n = blend_xp_and_detect_anomaly_standardized(5.0, 5.5, current_gw=10)
    print(f"Normal Blended xP: {xp_n}, Status: {stat_n}")
    assert "NORMAL" in stat_n
    assert xp_n == round(0.75 * 5.0 + 0.25 * 5.5, 3)

    # 3. Warning anomaly (0.25 <= D_pct < 0.50)
    # xp_model = 5.0, xp_bookies = 7.0 -> diff = 2.0, max = 7.0 -> D_pct = 0.285 (WARN)
    xp_w, stat_w = blend_xp_and_detect_anomaly_standardized(5.0, 7.0, current_gw=10)
    print(f"Warning Blended xP: {xp_w}, Status: {stat_w}")
    assert "INCELEME GEREKLI" in stat_w
    assert xp_w == round(0.75 * 5.0 + 0.25 * 7.0, 3)
    
    # 4. Critical anomaly blending (D_pct >= 0.50)
    # xp_model = 3.0, xp_bookies = 8.0 -> diff = 5.0, max = 8.0 -> D_pct = 0.625 (CRITICAL)
    xp_c, stat_c = blend_xp_and_detect_anomaly_standardized(3.0, 8.0, current_gw=10)
    print(f"Critical Anomaly Blended xP: {xp_c}, Status: {stat_c}")
    assert "KRITIK SAPMA" in stat_c
    assert xp_c == round(0.60 * 3.0 + 0.40 * 8.0, 3)
    
    # 5. Zero xP edge case
    xp_z, stat_z = blend_xp_and_detect_anomaly_standardized(0.0, 0.0, current_gw=5)
    print(f"Zero xP Blended xP: {xp_z}, Status: {stat_z}")
    assert "NORMAL" in stat_z
    assert xp_z == 0.0

    print("[SUCCESS] Betting odds manager sanity checks passed.")

