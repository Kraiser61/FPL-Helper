import math
from enum import Enum
from typing import Dict, Any, List, Optional
from data.models import PlayerDTO
from utils.logger import app_logger

class RankBand(Enum):
    TOP_1K = "Top 1k"
    TOP_10K = "Top 10k"
    TOP_100K = "Top 100k"
    OUTSIDE_100K = "100k+"

def get_rank_band(user_rank: int) -> RankBand:
    """
    Evaluates the user's current overall rank and returns the corresponding RankBand.
    """
    if user_rank <= 1_000:
        return RankBand.TOP_1K
    elif user_rank <= 10_000:
        return RankBand.TOP_10K
    elif user_rank <= 100_000:
        return RankBand.TOP_100K
    else:
        return RankBand.OUTSIDE_100K

def calculate_continuous_gamma(
    rank: int, 
    gamma_min: float = 0.7, 
    gamma_max: float = 1.5, 
    r_ref: float = 5000.0, 
    sigma: float = 1.2
) -> float:
    """
    Calculates a smooth (continuous) Gaussian curve-based Gamma factor based on rank.
    Prevents abrupt step-wise jumps between rank bands.
    Formula: gamma(R) = gamma_min + (gamma_max - gamma_min) * exp(- (ln(R / R_ref))^2 / (2 * sigma^2))
    """
    if rank <= 0:
        return 1.0
        
    ln_r = math.log(rank / r_ref)
    exponent = - (ln_r ** 2) / (2 * (sigma ** 2))
    gamma = gamma_min + (gamma_max - gamma_min) * math.exp(exponent)
    return round(max(gamma_min, min(gamma_max, gamma)), 4)

def calculate_enhanced_eo_risk(
    user_rank: int,
    eo_percent: float,
    xp_next_gw: float,
    is_top_3_captain: bool = False
) -> float:
    """
    Calculates Dynamic EO Risk based on continuous rank-based gamma scaling using Nash Equilibrium.
    
    Formula:
    EO_Risk_i = (EO_i / 100)^gamma(R) * xP_next_gw,i * Positional_EO_Weight
    """
    gamma = calculate_continuous_gamma(user_rank)
    positional_eo_weight = 2.0 if is_top_3_captain else 1.0
    
    if eo_percent <= 0:
        return 0.0
        
    eo_ratio = eo_percent / 100.0
    eo_risk = math.pow(eo_ratio, gamma) * xp_next_gw * positional_eo_weight
    return round(eo_risk, 3)

class OwnershipAnalyzer:
    """
    Game Theory & Risk Management Analyzer for Effective Ownership (EO), 
    Template Scoring, and Differential Advantage.
    """

    @classmethod
    def calculate_eo(cls, player: PlayerDTO, captaincy_percent: float = 0.0) -> float:
        """
        Calculates Effective Ownership (EO):
        EO = ownership% * (1.0 + captain_ownership_ratio)
        """
        ownership = player.selected_by_percent or 0.0
        captain_ratio = max(0.0, captaincy_percent / 100.0)
        
        if captain_ratio == 0.0 and ownership > 40.0:
            captain_ratio = (ownership - 40.0) / 100.0
            
        eo = ownership * (1.0 + captain_ratio)
        return round(eo, 2)

    @classmethod
    def calculate_template_score(cls, player: PlayerDTO, xp_horizon: float) -> float:
        """
        Calculates Template Score (Must-Have Index):
        Template_Score = EO * xp_horizon
        High template score (>25) indicates non-ownership carries extreme rank risk.
        """
        eo = cls.calculate_eo(player)
        return round(eo * (xp_horizon / 10.0), 2)

    @classmethod
    def calculate_differential_score(cls, player: PlayerDTO, xp_horizon: float) -> float:
        """
        Calculates Differential Advantage Score:
        Diff_Score = xp_horizon * (1.0 - ownership%)
        High diff score (>20) indicates high reward potential for rank climbing.
        """
        ownership_ratio = min(1.0, max(0.0, (player.selected_by_percent or 0.0) / 100.0))
        return round(xp_horizon * (1.0 - ownership_ratio), 2)

    @classmethod
    def get_eo_risk(
        cls, 
        player: PlayerDTO, 
        xp_horizon: float, 
        user_rank: Optional[int] = None,
        is_top_3_captain: bool = False,
        captaincy_percent: float = 0.0
    ) -> float:
        """
        Calculates Rank Loss Risk Penalty if player is NOT in user's squad using continuous gamma scaling.
        Defaults to user_rank=50000 (Top 100k) if not specified.
        """
        rank = user_rank if user_rank is not None else 50000
        eo = cls.calculate_eo(player, captaincy_percent)
        return calculate_enhanced_eo_risk(
            user_rank=rank,
            eo_percent=eo,
            xp_next_gw=xp_horizon,
            is_top_3_captain=is_top_3_captain
        )

    @classmethod
    def get_risk_profile_thresholds(cls, risk_profile: str) -> Dict[str, float]:
        """
        Returns parameters and thresholds based on user risk profile: 'safe', 'balanced', 'aggressive'.
        """
        profiles = {
            "safe": {
                "beta_eo_risk": 1.5,
                "template_threshold": 15.0,
                "differential_threshold": 30.0,
                "max_hits": 0
            },
            "balanced": {
                "beta_eo_risk": 1.0,
                "template_threshold": 25.0,
                "differential_threshold": 20.0,
                "max_hits": 1
            },
            "aggressive": {
                "beta_eo_risk": 0.3,
                "template_threshold": 40.0,
                "differential_threshold": 12.0,
                "max_hits": 2
            }
        }
        return profiles.get(risk_profile.lower(), profiles["balanced"])

if __name__ == "__main__":
    print("--- SANITY CHECK: core/ownership_analyzer.py ---")
    
    # Dummy PlayerDTO mock
    class DummyPlayerDTO:
        def __init__(self, selected_by_percent: float):
            self.selected_by_percent = selected_by_percent

    player_high_eo = DummyPlayerDTO(selected_by_percent=80.0) # EO approx 112%
    
    # 1. Continuous Gamma tests
    g_0 = calculate_continuous_gamma(0)
    g_5k = calculate_continuous_gamma(5000)
    g_50k = calculate_continuous_gamma(50000)
    g_500k = calculate_continuous_gamma(500000)
    
    print(f"Continuous Gamma at rank 0 (fallback): {g_0}")
    print(f"Continuous Gamma at rank 5,000 (peak): {g_5k}")
    print(f"Continuous Gamma at rank 50,000: {g_50k}")
    print(f"Continuous Gamma at rank 500,000: {g_500k}")
    
    assert g_0 == 1.0
    assert abs(g_5k - 1.5) < 0.05
    assert g_5k > g_50k > g_500k
    
    # 2. EO Risk tests with continuous gamma
    risk_5k = OwnershipAnalyzer.get_eo_risk(player_high_eo, xp_horizon=10.0, user_rank=5000, is_top_3_captain=True)
    risk_500k = OwnershipAnalyzer.get_eo_risk(player_high_eo, xp_horizon=10.0, user_rank=500000, is_top_3_captain=True)
    
    print(f"Rank 5k EO Risk: {risk_5k}")
    print(f"Rank 500k EO Risk: {risk_500k}")
    
    assert risk_5k > risk_500k, "Peak rank risk penalty must be strictly greater than 500k rank penalty!"
    assert get_rank_band(500) == RankBand.TOP_1K
    
    print("[SUCCESS] All ownership analyzer continuous gamma sanity checks passed.")

