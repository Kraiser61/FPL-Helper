import math
from typing import List, Optional
from dataclasses import dataclass
from core.ownership_analyzer import RankBand, get_rank_band

def calculate_hybrid_captain_score(
    f_prot: float, 
    f_diff: float, 
    rank: int, 
    base_xp: float
) -> float:
    """
    Blends Protection and Differential captain scores using a smooth sigmoid transition.
    Formula: F_hyb = omega * F_prot + (1.0 - omega) * F_diff
    omega = 1.0 / (1.0 + exp((rank - 25000) / 5000))
    Safety Rule: If base_xp < 5.0, omega is forced to 1.0 (zeroing differential risk bonus).
    """
    omega = 1.0 / (1.0 + math.exp((rank - 25000.0) / 5000.0))
    if base_xp < 5.0:
        omega = 1.0
        
    f_hyb = (omega * f_prot) + ((1.0 - omega) * f_diff)
    return round(f_hyb, 3)

def calculate_rank_adaptive_captain_score(
    user_rank: int,
    base_xp: float,
    venue_multiplier: float,
    fdr_multiplier: float,
    eo_percent: float,
    ownership_percent: float
) -> float:
    """
    Calculates rank-adaptive captain score using continuous sigmoid hybrid mode.
    Blends Protection strategy (bonus to high EO) and Differential strategy (bonus to low ownership).
    """
    base_mult = base_xp * venue_multiplier * fdr_multiplier
    
    # Protection baseline
    eo_factor = 1.0 + (eo_percent / 80.0)
    f_prot = base_mult * eo_factor
    
    # Differential baseline
    own_ratio = max(0.0, ownership_percent / 100.0)
    diff_factor = 1.0 + (1.0 - own_ratio) * 0.40
    f_diff = base_mult * diff_factor
    
    return calculate_hybrid_captain_score(
        f_prot=f_prot,
        f_diff=f_diff,
        rank=user_rank,
        base_xp=base_xp
    )

@dataclass
class CaptaincyCandidate:
    id: int
    web_name: str
    element_type: int              # 1=GKP, 2=DEF, 3=MID, 4=FWD
    xp_next_gw: float              # Expected points specifically for next GW against upcoming opponent
    chance_of_playing: float       # 0.0 to 1.0
    is_home: bool = True
    fdr: int = 3                   # Opponent FDR (1 to 5)
    is_penalty_taker: bool = False
    is_force_captain: bool = False
    eo_percent: float = 0.0
    ownership_percent: float = 0.0

@dataclass
class CaptaincyResult:
    captain_id: int
    captain_name: str
    vice_captain_id: int
    vice_captain_name: str
    expected_extra_points: float   # Extra points from captain multiplier (1.0x extra)
    captain_score: float

class CaptainSelector:
    """
    Evaluates starting 11 candidates to pick the Captain (👑) and Vice-Captain (🥈) 
    maximizing the probability of achieving the highest individual score in the NEXT GAMEWEEK.
    
    Factors evaluated per candidate for next GW:
    1. Single-Match Expected Points against Next Opponent (xp_next_gw)
    2. Home Advantage (1.18x multiplier for home fixtures)
    3. Penalty/Set-Piece Duty (1.15x multiplier for primary penalty takers)
    4. FDR Weakness (Opponent defense vulnerability bonus for FDR 1 or 2)
    5. Availability Probability (p_avail)
    6. Continuous Sigmoid Hybrid EO Strategy Factor (Protection vs Differential)
    """

    def __init__(self, candidates: List[CaptaincyCandidate], user_rank: Optional[int] = None):
        if not candidates:
            raise ValueError("No candidates provided for captaincy selection.")
        self.candidates = candidates
        self.user_rank = user_rank if user_rank is not None else 50000

    def calculate_captaincy_index(self, c: CaptaincyCandidate, user_rank: Optional[int] = None) -> float:
        """Calculates single-match explosiveness & captaincy score for next GW with ceiling probability."""
        if c.chance_of_playing < 0.50:
            return 0.0

        rank = user_rank if user_rank is not None else self.user_rank
        base = max(0.0, c.xp_next_gw)

        home_bonus = 1.18 if c.is_home else 1.00
        pen_bonus = 1.15 if c.is_penalty_taker else 1.00
        fdr_bonus = 1.25 if c.fdr <= 2 else (1.05 if c.fdr == 3 else 0.90)
        avail_mult = 1.00 if c.chance_of_playing >= 0.99 else (0.85 if c.chance_of_playing >= 0.75 else 0.60)
        pos_ceiling = 1.10 if c.element_type in (3, 4) else 0.90

        # Poisson Haul Probability (Probability of scoring >= 10 points)
        p_haul = max(0.0, 1.0 - math.exp(-max(0.0, base - 1.5) / 3.2))
        haul_factor = 1.0 + (0.25 * p_haul)

        # Rank-adaptive score baseline
        adaptive_base = calculate_rank_adaptive_captain_score(
            user_rank=rank,
            base_xp=base,
            venue_multiplier=home_bonus,
            fdr_multiplier=fdr_bonus,
            eo_percent=c.eo_percent,
            ownership_percent=c.ownership_percent
        )

        # Harmonize adaptive baseline with explosiveness, position, and availability
        score = adaptive_base * pen_bonus * pos_ceiling * avail_mult * haul_factor
        return round(score, 3)

    def select(self, user_rank: Optional[int] = None) -> CaptaincyResult:
        rank = user_rank if user_rank is not None else self.user_rank

        forced = [c for c in self.candidates if c.is_force_captain]
        if forced:
            captain = forced[0]
            rest = [c for c in self.candidates if c.id != captain.id]
            rest.sort(key=lambda c: self.calculate_captaincy_index(c, rank), reverse=True)
            vice = rest[0] if rest else captain
            return CaptaincyResult(
                captain_id=captain.id,
                captain_name=captain.web_name,
                vice_captain_id=vice.id,
                vice_captain_name=vice.web_name,
                expected_extra_points=round(captain.xp_next_gw, 1),
                captain_score=self.calculate_captaincy_index(captain, rank)
            )

        scored = [(self.calculate_captaincy_index(c, rank), c) for c in self.candidates]
        scored.sort(key=lambda x: (x[0], x[1].xp_next_gw), reverse=True)

        captain_score, captain = scored[0]
        vice = scored[1][1] if len(scored) > 1 else captain

        return CaptaincyResult(
            captain_id=captain.id,
            captain_name=captain.web_name,
            vice_captain_id=vice.id,
            vice_captain_name=vice.web_name,
            expected_extra_points=round(captain.xp_next_gw, 1),
            captain_score=captain_score
        )

if __name__ == "__main__":
    print("--- SANITY CHECK: core/captain_selector.py ---")
    
    # Candidate 1: High EO Template Captain (Haaland)
    c_template = CaptaincyCandidate(
        id=1, web_name="Haaland", element_type=4, xp_next_gw=8.5,
        chance_of_playing=1.0, is_home=True, fdr=2, is_penalty_taker=True,
        eo_percent=180.0, ownership_percent=90.0
    )
    # Candidate 2: Low Ownership Differential Captain (Palmer)
    c_differential = CaptaincyCandidate(
        id=2, web_name="Palmer", element_type=3, xp_next_gw=8.5,
        chance_of_playing=1.0, is_home=True, fdr=2, is_penalty_taker=True,
        eo_percent=20.0, ownership_percent=15.0
    )
    
    # 1. Hybrid Sigmoid Score test
    # Rank 5k (mostly protection)
    sc_5k = calculate_hybrid_captain_score(15.0, 20.0, 5000, 7.0)
    # Rank 50k (mostly differential)
    sc_50k = calculate_hybrid_captain_score(15.0, 20.0, 50000, 7.0)
    # Base xP < 5.0 (safety override -> force protection)
    sc_safe = calculate_hybrid_captain_score(15.0, 20.0, 50000, 4.0)
    
    print(f"Hybrid Score at 5k (prot weighted): {sc_5k}")
    print(f"Hybrid Score at 50k (diff weighted): {sc_50k}")
    print(f"Hybrid Score at 50k with base_xp < 5.0 (forced prot): {sc_safe}")
    
    assert sc_5k < sc_50k, "50k rank should give higher score to differential upside!"
    assert sc_safe == 15.0, "Low base xP must override differential risk and return f_prot!"

    # 2. Captain Selection tests
    selector_5k = CaptainSelector([c_template, c_differential], user_rank=5000)
    res_5k = selector_5k.select()
    
    selector_200k = CaptainSelector([c_template, c_differential], user_rank=200000)
    res_200k = selector_200k.select()
    
    print(f"5k Captain Pick: {res_5k.captain_name} (Score: {res_5k.captain_score})")
    print(f"200k Captain Pick: {res_200k.captain_name} (Score: {res_200k.captain_score})")
    
    assert res_5k.captain_id == 1, "5k rank must pick Template captain (Haaland)!"
    assert res_200k.captain_id == 2, "200k rank must pick Differential captain (Palmer)!"
    
    print("[SUCCESS] All captain selector hybrid mode sanity checks passed.")

