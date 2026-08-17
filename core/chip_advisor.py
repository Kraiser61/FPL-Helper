from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

@dataclass
class ChipAdvice:
    chip_name: str
    should_play: bool
    expected_gain: float
    reasoning: str

# ==============================================================================
# CHIP EFFICIENCY CALCULATOR FUNCTIONS
# ==============================================================================

def calculate_wildcard_efficiency(
    gw_weights: List[float], 
    xp_optimal_squad: List[float], 
    xp_current_squad: List[float]
) -> Tuple[float, bool]:
    """
    Calculates Wildcard (WC) efficiency over an 8-GW lookahead window.
    Formula: S_WC(GW) = Sum_{k=0..7} W_k * (xP_optimal_squad^(GW+k) - xP_current_squad^(GW+k))
    Threshold: S_WC > 30.0
    """
    if not (len(gw_weights) == len(xp_optimal_squad) == len(xp_current_squad)):
        raise ValueError("Parametre listelerinin uzunlukları eşit olmalıdır (beklenen 8 GW).")
        
    s_wc = sum(w * (opt - cur) for w, opt, cur in zip(gw_weights, xp_optimal_squad, xp_current_squad))
    signal = bool(s_wc > 30.0)
    return round(s_wc, 3), signal

def calculate_freehit_efficiency(
    xp_fh_optimal: float, 
    xp_current: float, 
    is_bgw: bool, 
    is_dgw: bool
) -> Tuple[float, bool]:
    """
    Calculates Free Hit (FH) efficiency for a given GW.
    Formula: S_FH(GW) = xP_FH_optimal^(GW) - xP_current^(GW)
    Threshold: > 15.0 in BGW, > 25.0 in DGW
    """
    s_fh = xp_fh_optimal - xp_current
    signal = False
    if is_bgw and s_fh > 15.0:
        signal = True
    elif is_dgw and s_fh > 25.0:
        signal = True
        
    return round(s_fh, 3), signal

def calculate_benchboost_efficiency(
    bench_xp: List[float], 
    bench_p_play: List[float], 
    dgw_multipliers: List[float]
) -> Tuple[float, bool]:
    """
    Calculates Bench Boost (BB) efficiency.
    Formula: S_BB(GW) = Sum_{j=12..15} xP_bench_player_j * P_play_j * DGW_Multiplier
    Threshold: S_BB > 15.0 AND all(P_play >= 0.75)
    """
    if not (len(bench_xp) == len(bench_p_play) == len(dgw_multipliers) == 4):
        raise ValueError("Yedek kulübesi için tam olarak 4 oyuncu verisi girilmelidir.")
        
    s_bb = sum(xp * p * dgw for xp, p, dgw in zip(bench_xp, bench_p_play, dgw_multipliers))
    signal = bool(s_bb > 15.0 and all(p >= 0.75 for p in bench_p_play))
    return round(s_bb, 3), signal

def calculate_triplecaptain_efficiency(
    captain_xp: float, 
    p_play: float, 
    is_dgw: bool, 
    fdr: float
) -> Tuple[float, bool]:
    """
    Calculates Triple Captain (TC) efficiency.
    Formula: S_TC(GW) = xP_captain * P_play * DGW_Multiplier * FDR_Factor
    Threshold: S_TC > 12.0 AND is_dgw AND P_play >= 0.99 AND FDR <= 3.0
    """
    dgw_multiplier = 2.0 if is_dgw else 1.0
    fdr_factor = 1.25 if fdr <= 2.0 else (1.0 if fdr <= 3.0 else 0.75)
    
    s_tc = captain_xp * p_play * dgw_multiplier * fdr_factor
    signal = bool(s_tc > 12.0 and is_dgw and p_play >= 0.99 and fdr <= 3.0)
    return round(s_tc, 3), signal

# ==============================================================================
# CHIP ADVISOR CLASS
# ==============================================================================

def calculate_chip_option_value_and_deferral(
    current_v_chip: float, 
    future_v_chips: List[float]
) -> Tuple[bool, str]:
    """
    Calculates Chip Option Value (OV_chip) and deferral signal over future gameweeks.
    Formula: OV_chip = max(V_chip(gw+1), ..., V_chip(gw+7))
    Decision Rule: If OV_chip > current_v_chip * 1.15 -> Signal deferral recommendation.
    """
    if not future_v_chips:
        return False, "Kullanım Uygun: Gelecek verisi yok."
        
    ov_chip = max(future_v_chips)
    
    if ov_chip > current_v_chip * 1.15:
        best_idx = future_v_chips.index(ov_chip)
        return True, f"Erteleme Önerisi: GW+{best_idx + 1} haftasında daha yüksek getiri imkanı var (Beklenen: {ov_chip:.2f} xP)."
        
    return False, "Kullanım Uygun: Gelecek haftalarda belirgin bir avantaj görülmedi."

# ==============================================================================
# CHIP ADVISOR CLASS
# ==============================================================================

class ChipAdvisor:
    """
    Evaluates chip usage strategies using 8-GW lookahead simulation matrices & Option Value deferral logic.
    """
    
    @staticmethod
    def evaluate_wildcard(
        is_available: bool, 
        current_squad_8gw_xp: float, 
        optimal_squad_8gw_xp: float,
        injuries_in_squad: int = 0,
        gws_remaining_in_half: int = 19
    ) -> ChipAdvice:
        if not is_available:
            return ChipAdvice("Wildcard", False, 0.0, "Chip not available.")
            
        xp_diff = optimal_squad_8gw_xp - current_squad_8gw_xp
        should_play = False
        reason = ""
        
        if xp_diff > 30.0:
            should_play = True
            reason = f"Optimal squad provides +{xp_diff:.1f} xP over next 8 GWs (>30 threshold)."
        elif injuries_in_squad >= 5:
            should_play = True
            reason = f"Squad has {injuries_in_squad} injuries/flags. Wildcard recommended."
        elif gws_remaining_in_half <= 2:
            should_play = True
            reason = "Use it or lose it! Only 2 or fewer GWs remaining in this half of the season."
            
        return ChipAdvice("Wildcard", should_play, xp_diff, reason if should_play else "Conditions not met.")

    @staticmethod
    def evaluate_free_hit(
        is_available: bool,
        is_bgw: bool,
        current_squad_1gw_xp: float,
        optimal_squad_1gw_xp: float,
        is_dgw: bool = False
    ) -> ChipAdvice:
        if not is_available:
            return ChipAdvice("Free Hit", False, 0.0, "Chip not available.")
            
        s_fh, signal = calculate_freehit_efficiency(optimal_squad_1gw_xp, current_squad_1gw_xp, is_bgw, is_dgw)
        
        reason = ""
        if signal:
            reason = f"Free Hit yields +{s_fh:.1f} xP upside (Threshold met)."
        else:
            reason = f"Upside (+{s_fh:.1f} xP) does not meet threshold for current GW state."
            
        return ChipAdvice("Free Hit", signal, s_fh, reason)

    @staticmethod
    def evaluate_bench_boost(
        is_available: bool,
        is_dgw: bool,
        bench_players_xp: List[float],
        bench_players_play_prob: List[float],
        dgw_multipliers: Optional[List[float]] = None
    ) -> ChipAdvice:
        if not is_available:
            return ChipAdvice("Bench Boost", False, 0.0, "Chip not available.")
            
        dgw_mults = dgw_multipliers or ([2.0 if is_dgw else 1.0] * 4)
        s_bb, signal = calculate_benchboost_efficiency(bench_players_xp, bench_players_play_prob, dgw_mults)
        
        all_play = all(p >= 0.75 for p in bench_players_play_prob)
        if signal:
            reason = f"Bench Boost active: +{s_bb:.1f} xP value across 4 playing bench options."
        elif not all_play:
            reason = "Not all bench players have >= 75% chance of playing."
        else:
            reason = f"Bench xP ({s_bb:.1f}) is below the 15.0 threshold."
            
        return ChipAdvice("Bench Boost", signal, s_bb, reason)

    @staticmethod
    def evaluate_triple_captain(
        is_available: bool,
        is_dgw: bool,
        top_captain_xp: float,
        top_captain_prob: float,
        fdr_average: float
    ) -> ChipAdvice:
        if not is_available:
            return ChipAdvice("Triple Captain", False, 0.0, "Chip not available.")
            
        s_tc, signal = calculate_triplecaptain_efficiency(top_captain_xp, top_captain_prob, is_dgw, fdr_average)
        
        if signal:
            reason = f"DGW active: Captain score {s_tc:.1f} > 12 threshold with 100% play probability & easy FDR."
        else:
            reason = f"Conditions for optimal Triple Captain not met (Score: {s_tc:.1f}, requires DGW, high xP, low FDR)."
            
        return ChipAdvice("Triple Captain", signal, s_tc, reason)

    @classmethod
    def recommend_chips(
        cls,
        available_chips: Dict[str, bool],
        simulation_matrix: Dict[str, Any]
    ) -> List[ChipAdvice]:
        """
        Scans an 8-GW simulation matrix and recommends the highest ROI chip strategy with Option Value deferral check.
        """
        recommendations = []
        
        # Wildcard evaluation
        if available_chips.get("wildcard", False) and "wc_weights" in simulation_matrix:
            s_wc, sig_wc = calculate_wildcard_efficiency(
                simulation_matrix["wc_weights"],
                simulation_matrix["wc_optimal_xp"],
                simulation_matrix["wc_current_xp"]
            )
            reason_wc = f"8-GW Wildcard Simulation Score: {s_wc:.1f}"
            if sig_wc and "future_wc_scores" in simulation_matrix:
                defer, def_reason = calculate_chip_option_value_and_deferral(s_wc, simulation_matrix["future_wc_scores"])
                if defer:
                    sig_wc = False
                    reason_wc += f" | {def_reason}"
                    
            recommendations.append(ChipAdvice("Wildcard", sig_wc, s_wc, reason_wc))

        # Free Hit evaluation
        if available_chips.get("freehit", False) and "fh_optimal_xp" in simulation_matrix:
            s_fh, sig_fh = calculate_freehit_efficiency(
                simulation_matrix["fh_optimal_xp"],
                simulation_matrix["fh_current_xp"],
                simulation_matrix.get("is_bgw", False),
                simulation_matrix.get("is_dgw", False)
            )
            reason_fh = f"Free Hit Simulation Score: {s_fh:.1f}"
            if sig_fh and "future_fh_scores" in simulation_matrix:
                defer, def_reason = calculate_chip_option_value_and_deferral(s_fh, simulation_matrix["future_fh_scores"])
                if defer:
                    sig_fh = False
                    reason_fh += f" | {def_reason}"
                    
            recommendations.append(ChipAdvice("Free Hit", sig_fh, s_fh, reason_fh))

        # Bench Boost evaluation
        if available_chips.get("benchboost", False) and "bench_xp" in simulation_matrix:
            s_bb, sig_bb = calculate_benchboost_efficiency(
                simulation_matrix["bench_xp"],
                simulation_matrix["bench_p_play"],
                simulation_matrix.get("dgw_multipliers", [1.0, 1.0, 1.0, 1.0])
            )
            reason_bb = f"Bench Boost Simulation Score: {s_bb:.1f}"
            if sig_bb and "future_bb_scores" in simulation_matrix:
                defer, def_reason = calculate_chip_option_value_and_deferral(s_bb, simulation_matrix["future_bb_scores"])
                if defer:
                    sig_bb = False
                    reason_bb += f" | {def_reason}"
                    
            recommendations.append(ChipAdvice("Bench Boost", sig_bb, s_bb, reason_bb))

        # Triple Captain evaluation
        if available_chips.get("triplecaptain", False) and "captain_xp" in simulation_matrix:
            s_tc, sig_tc = calculate_triplecaptain_efficiency(
                simulation_matrix["captain_xp"],
                simulation_matrix.get("captain_p_play", 1.0),
                simulation_matrix.get("is_dgw", False),
                simulation_matrix.get("fdr", 2.0)
            )
            reason_tc = f"Triple Captain Simulation Score: {s_tc:.1f}"
            if sig_tc and "future_tc_scores" in simulation_matrix:
                defer, def_reason = calculate_chip_option_value_and_deferral(s_tc, simulation_matrix["future_tc_scores"])
                if defer:
                    sig_tc = False
                    reason_tc += f" | {def_reason}"
                    
            recommendations.append(ChipAdvice("Triple Captain", sig_tc, s_tc, reason_tc))
            
        return recommendations

if __name__ == "__main__":
    print("--- SANITY CHECK: core/chip_advisor.py ---")
    
    # 1. Option Value Deferral test
    defer_yes, msg_yes = calculate_chip_option_value_and_deferral(20.0, [15.0, 25.0, 18.0])
    defer_no, msg_no = calculate_chip_option_value_and_deferral(20.0, [21.0, 19.0, 22.0])
    
    print(f"Deferral test 1 (yes): defer={defer_yes}, msg={msg_yes}")
    print(f"Deferral test 2 (no): defer={defer_no}, msg={msg_no}")
    
    assert defer_yes is True
    assert "GW+2" in msg_yes
    assert defer_no is False

    # 2. Test functions
    weights = [1.0] * 8
    opt_xp = [60.0] * 8
    cur_xp = [50.0] * 8
    
    s_wc, sig_wc = calculate_wildcard_efficiency(weights, opt_xp, cur_xp)
    print(f"Wildcard Score: {s_wc}, Signal: {sig_wc}")
    assert s_wc == 80.0
    assert sig_wc is True
    
    s_fh, sig_fh = calculate_freehit_efficiency(60.0, 40.0, is_bgw=True, is_dgw=False)
    print(f"Free Hit Score: {s_fh}, Signal: {sig_fh}")
    assert s_fh == 20.0
    assert sig_fh is True
    
    s_bb, sig_bb = calculate_benchboost_efficiency([4.0, 4.0, 4.0, 4.0], [1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0])
    print(f"Bench Boost Score: {s_bb}, Signal: {sig_bb}")
    assert s_bb == 16.0
    assert sig_bb is True
    
    s_tc, sig_tc = calculate_triplecaptain_efficiency(9.0, 1.0, is_dgw=True, fdr=2.0)
    print(f"Triple Captain Score: {s_tc}, Signal: {sig_tc}")
    assert s_tc == 22.5
    assert sig_tc is True
    
    # 3. Test recommend_chips with future scores
    sim_matrix = {
        "wc_weights": weights,
        "wc_optimal_xp": opt_xp,
        "wc_current_xp": cur_xp,
        "future_wc_scores": [70.0, 100.0, 75.0], # 100.0 > 80.0 * 1.15 -> should trigger deferral!
        "fh_optimal_xp": 60.0,
        "fh_current_xp": 40.0,
        "is_bgw": True,
        "is_dgw": False,
        "bench_xp": [4.0, 4.0, 4.0, 4.0],
        "bench_p_play": [1.0, 1.0, 1.0, 1.0],
        "captain_xp": 9.0,
        "captain_p_play": 1.0,
        "fdr": 2.0
    }
    avail = {"wildcard": True, "freehit": True, "benchboost": True, "triplecaptain": True}
    advices = ChipAdvisor.recommend_chips(avail, sim_matrix)
    print(f"Total recommendations generated: {len(advices)}")
    for a in advices:
        print(f"  - {a.chip_name}: play={a.should_play}, gain={a.expected_gain}, reason={a.reasoning}")
        
    wc_advice = next(a for a in advices if a.chip_name == "Wildcard")
    assert wc_advice.should_play is False, "Wildcard play should be deferred due to higher future score!"
    assert "Erteleme Önerisi" in wc_advice.reasoning
    
    print("[SUCCESS] Chip advisor option value sanity checks passed.")

