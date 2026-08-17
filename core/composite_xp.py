import math
from typing import List, Optional, Dict, Any, Tuple
from core.xp_calculator import XPCalculator, FixtureContext
from data.models import PlayerDTO
from utils.logger import app_logger

def apply_injury_ramp_up_penalty(base_p_play: float, mins_last_3_gws: List[float]) -> float:
    """
    Applies a 20% match-fitness (ramp-up) penalty (0.80x) to P_play if the player 
    has played 0 minutes in their last 3 gameweeks despite having a high (>=75%) chance of playing.
    """
    if mins_last_3_gws and len(mins_last_3_gws) > 0 and sum(mins_last_3_gws) == 0.0 and base_p_play >= 0.75:
        return round(base_p_play * 0.80, 4)
    return base_p_play

class CompositeXPCalculator:
    """
    Multi-Factor Dynamic Expected Points (xP) Calculator tailored for Top 10k Manager Strategy.
    Features:
    - Dynamic Multi-Gameweek Horizon Decay with DGW/BGW/Wildcard/Late-season adaptation.
    - Expected Bonus Points (E[Bonus]) calculation using Normal Distribution CDF.
    - Mathematical Set-Piece Duty Expectations.
    - Continuous Probabilistic Crellin Minutes & Rotation Risk Curve with Injury Ramp-up Penalty.
    - Elite Finisher Calibrated xGI Regression Radar.
    """

    HORIZON_DECAY_WEIGHTS = [1.00, 0.50, 0.15]
    FORM_MIX_ALPHA = 0.70

    ELITE_FINISHERS = {
        "haaland", "salah", "palmer", "isak", "watkins", 
        "saka", "son", "mbeumo", "solanke", "joão pedro", "pedro", "wood"
    }

    @staticmethod
    def calculate_expected_bonus_points(
        avg_bps_per90: float,
        position: str,
        opponent_bps_resistance: float = 0.0
    ) -> float:
        """
        Calculates Expected Bonus Points (E[Bonus]) using right-skewed Lognormal distribution model.
        
        Args:
            avg_bps_per90 (float): Player's average BPS per 90 minutes.
            position (str): Player position ('GKP', 'DEF', 'MID', 'FWD') or element_type string.
            opponent_bps_resistance (float): Opponent BPS suppression factor (default 0.0).
            
        Returns:
            float: Expected bonus points per match.
        """
        if avg_bps_per90 is None or avg_bps_per90 <= 0.0:
            return 0.0

        pos_str = str(position).upper()
        position_bases = {
            'GKP': 20.0, '1': 20.0,
            'DEF': 23.0, '2': 23.0,
            'MID': 26.0, '3': 26.0,
            'FWD': 23.0, '4': 23.0
        }
        base_bps = position_bases.get(pos_str, 23.0)
        mu = max(5.0, (avg_bps_per90 * 0.8) + (base_bps * 0.2))
        sigma = 7.5

        # Right-skewed Lognormal parameterization
        variance = sigma ** 2
        sigma_ln = math.sqrt(math.log(1.0 + (variance / (mu ** 2))))
        mu_ln = math.log(mu) - (0.5 * (sigma_ln ** 2))

        res = opponent_bps_resistance or 0.0
        t1 = max(1.0, 26.0 + res)
        t2 = max(1.0, 29.0 + res)
        t3 = max(1.0, 33.0 + res)

        def lognormal_survival(threshold: float) -> float:
            z = (math.log(threshold) - mu_ln) / (sigma_ln * math.sqrt(2.0))
            return 0.5 * math.erfc(z)

        p1 = max(0.0, min(1.0, lognormal_survival(t1)))
        p2 = max(0.0, min(1.0, lognormal_survival(t2)))
        p3 = max(0.0, min(1.0, lognormal_survival(t3)))

        return round(p1 + p2 + p3, 3)

    @classmethod
    def calculate_boom_metrics(
        cls,
        player: PlayerDTO,
        next_gw_xp: float,
        fixture: Optional[FixtureContext] = None
    ) -> Tuple[float, float]:
        """
        Calculates Boom Probability (P(Points >= 10)) and Boom Index (0.0 - 5.0).
        Calibrated on FPL haul distribution using exponential tail modeling based on
        xP, attacking position, penalty duties, elite finisher status, and fixture difficulty.
        """
        if next_gw_xp <= 1.0:
            return 0.02, 0.2

        elem = player.element_type or 3
        p_name = (player.web_name or "").lower()
        is_elite = any(elite in p_name for elite in cls.ELITE_FINISHERS)
        
        pen_takers = {"haaland", "fernandes", "mbeumo", "joão pedro", "pedro", "saka", "salah", "palmer", "isak", "solanke", "eze", "watkins", "wood"}
        is_pen = any(name in p_name for name in pen_takers)
        
        # Base probability from exponential tail of Poisson haul distribution
        base_prob = 1.0 - math.exp(- math.pow(max(0.1, next_gw_xp) / 5.2, 2.2) * 0.28)
        
        if elem == 4: # FWD
            pos_mult = 1.15
        elif elem == 3: # MID
            pos_mult = 1.10
        elif elem == 2: # DEF
            pos_mult = 0.65
        else:
            pos_mult = 0.40
            
        if is_elite:
            pos_mult *= 1.20
        if is_pen:
            pos_mult *= 1.15
        if fixture and fixture.is_home:
            pos_mult *= 1.10
        if fixture and fixture.fdr <= 2:
            pos_mult *= 1.15
            
        final_prob = max(0.01, min(0.65, base_prob * pos_mult))
        boom_index = round(final_prob * 10.0, 1)
        return round(final_prob, 3), boom_index

    @staticmethod
    def calculate_dynamic_time_decay(
        horizon_weeks: int,
        current_gw: int,
        team_fixtures: List[Dict[str, Any]],
        is_wildcard_active: bool = False
    ) -> List[float]:
        """
        Calculates dynamic Time Decay weight vector for multi-week xP projections.
        Adjusts weights for DGW, BGW, Wildcard, and late season (GW >= 35).
        """
        horizon_weeks = max(1, horizon_weeks)
        
        if current_gw >= 35:
            base_weights = [1.00, 0.70, 0.50, 0.40, 0.30]
        else:
            base_weights = [1.00, 0.50, 0.15, 0.05, 0.01]

        if is_wildcard_active:
            base_weights = [0.60] * max(5, horizon_weeks)

        decay_vector = []
        for i in range(horizon_weeks):
            w = base_weights[i] if i < len(base_weights) else 0.01
            fixture_ctx = team_fixtures[i] if (team_fixtures and i < len(team_fixtures)) else {}

            if isinstance(fixture_ctx, dict):
                is_dgw = fixture_ctx.get('is_dgw', False)
                is_bgw = fixture_ctx.get('is_bgw', False)
                has_match = fixture_ctx.get('has_match', True)
            else:
                matches_cnt = getattr(fixture_ctx, 'matches_in_gw', 1)
                is_dgw = matches_cnt > 1
                is_bgw = matches_cnt == 0
                has_match = matches_cnt > 0

            if is_dgw:
                w *= 1.6
            elif is_bgw:
                if has_match:
                    w *= 2.0
                else:
                    w *= 0.1

            decay_vector.append(round(w, 3))

        return decay_vector

    @classmethod
    def calculate_card_risk(cls, player: PlayerDTO, current_gw: int = 1) -> float:
        """Calculates Yellow Card Accumulation Risk Penalty."""
        yellows = player.yellow_cards or 0
        if current_gw <= 16 and yellows == 4:
            return 0.90
        elif yellows == 9:
            return 0.85
        elif player.status in ("s", "u"):
            return 0.0
        return 1.0

    @classmethod
    def calculate_availability(
        cls, 
        player: PlayerDTO, 
        avg_mins_last_5: float = 90.0, 
        missed_gws_last_10: int = 0,
        mins_last_3_gws: Optional[List[float]] = None
    ) -> float:
        """
        Calculates 3-Layered Availability Probability using a continuous probabilistic Crellin curve and Injury Ramp-up Penalty.
        """
        p_fpl = player.get_normalized_chance_next()
        
        if player.status in ('d', 'i') or p_fpl < 1.0:
            ramp_factor = 0.60 if p_fpl <= 0.50 else 0.80
        else:
            ramp_factor = 1.0

        missed_ratio = max(0, min(10, missed_gws_last_10)) / 10.0
        p_injury_trend = 1.0 - (0.25 * missed_ratio)
        
        total_mins = getattr(player, 'minutes', 0) or 0
        avg_mins = max(0.0, min(90.0, avg_mins_last_5 if avg_mins_last_5 is not None else 90.0))
        p_start = 1.0 / (1.0 + math.exp(-0.09 * (avg_mins - 55.0)))
        expected_mins_if_fit = (p_start * 82.0) + ((1.0 - p_start) * 18.0)
        p_rotation = max(0.20, expected_mins_if_fit / 90.0)

        # If a player has very low total minutes history (<450 mins), reflect bench rotation status
        if 0 < total_mins < 450:
            sample_rot = max(0.25, total_mins / 550.0)
            p_rotation = min(p_rotation, sample_rot)
        elif total_mins == 0:
            p_rotation = min(p_rotation, 0.20)
        
        p_avail = p_fpl * p_injury_trend * p_rotation * ramp_factor
        
        # Apply injury ramp-up penalty for returning players with 0 mins in last 3 GWs
        p_avail_final = apply_injury_ramp_up_penalty(p_avail, mins_last_3_gws or [])
        return round(max(0.0, min(1.0, p_avail_final)), 3)

    @classmethod
    def calculate_set_piece_boost(cls, player: PlayerDTO) -> float:
        """
        Calculates Dynamic Set-Piece Expectation Boost.
        """
        boost = 0.0
        p_name = (player.web_name or "").lower()
        elem = player.element_type or 3
        goal_pts = {1: 6, 2: 6, 3: 5, 4: 4}.get(elem, 5)
        
        pen_takers = {"haaland", "fernandes", "mbeumo", "joão pedro", "pedro", "saka", "salah", "palmer", "isak", "solanke", "eze", "watkins", "wood"}
        if any(name in p_name for name in pen_takers):
            boost += 0.11 * 0.78 * goal_pts
            
        corner_takers = {"fernandes", "szoboszlai", "rice", "ward-prowse", "trippier", "madueke", "savinho", "palmer", "saka", "eze", "mgw", "porro"}
        if any(name in p_name for name in corner_takers):
            boost += 0.04 * 3.0

        return round(boost, 3)

    @classmethod
    def calculate_defensive_base_boost(cls, player: PlayerDTO) -> float:
        """
        Calculates Defensive Base & BPS Boost for Defenders (DEF) based on CBI + Recoveries.
        """
        if player.element_type != 2:
            return 0.0
            
        cbi = getattr(player, 'clearances_blocks_interceptions', 0) or 0
        rec = getattr(player, 'recoveries', 0) or 0
        total_def_actions = cbi + rec
        
        if total_def_actions >= 100:
            return 0.35
        elif total_def_actions >= 60:
            return 0.20
        elif total_def_actions >= 30:
            return 0.10
        return 0.0

    @classmethod
    def calculate_xgi_regression_factor(cls, player: PlayerDTO) -> Tuple[float, str]:
        """
        Calibrated xGI Regression Radar (Skill vs Luck Distinction).
        """
        xgi = (player.expected_goals or 0.0) + (player.expected_assists or 0.0)
        actual_gi = (player.goals_scored or 0) + (player.assists or 0)
        p_name = (player.web_name or "").lower()
        
        diff = actual_gi - xgi
        is_elite = any(elite in p_name for elite in cls.ELITE_FINISHERS)
        
        if diff >= 3.0:
            if is_elite:
                return 1.00, "⭐ Elit Bitirici: Yüksek xGI üstü verim yetenekten kaynaklı (Cezasız)"
            else:
                return 0.95, "⚠️ Geçici Şans: Ürettiği xGI'dan 3+ fazla gol katkısı (Hafif Kalibrasyon)"
        elif diff <= -2.0 and xgi >= 2.5:
            return 1.05, "🚀 Fırsat Hedefi: xGI üretimine göre şanssız (Pozitif Dönüş Beklentisi)"
            
        return 1.0, "Ölçülü"

    @classmethod
    def calculate_form_momentum(cls, player: PlayerDTO, recent_xps: Optional[List[float]] = None) -> float:
        """Calculates Form Momentum Weight gently bounded around 1.0 by [0.88, 1.12]."""
        ema_form = XPCalculator.calculate_form_weight(recent_xps or [])
        
        raw_form = player.form if player.form > 0 else (player.points_per_game if player.points_per_game > 0 else 4.0)
        norm_season = 1.0 + ((raw_form - 4.5) / 25.0)
        
        blended = (cls.FORM_MIX_ALPHA * ema_form) + ((1.0 - cls.FORM_MIX_ALPHA) * norm_season)
        return max(0.88, min(1.12, blended))

    @classmethod
    def calculate_fixture_weight(cls, fixtures: List[FixtureContext], element_type: int) -> float:
        """Calculates weighted fixture difficulty multiplier over position-specific 3-GW horizon using dynamic decay."""
        if not fixtures:
            return 1.0
            
        weighted_sum = 0.0
        weight_total = 0.0
        
        decay_weights = cls.calculate_dynamic_time_decay(
            horizon_weeks=len(fixtures[:3]),
            current_gw=1,
            team_fixtures=[{"matches_in_gw": getattr(f, 'matches_in_gw', 1)} for f in fixtures[:3]]
        )
        
        for k, fixture in enumerate(fixtures[:3]):
            discount = decay_weights[k] if k < len(decay_weights) else 0.10
            fdr_attack = XPCalculator.calculate_fdr_factor(fixture.fdr, fixture.opponent_strength_defence, is_attack=True)
            fdr_defence = XPCalculator.calculate_fdr_factor(fixture.fdr, fixture.opponent_strength_attack, is_attack=False)
            
            fdr_mult = fdr_defence if element_type in (1, 2) else fdr_attack
            weighted_sum += discount * fdr_mult
            weight_total += discount
            
        return (weighted_sum / weight_total) if weight_total > 0 else 1.0

    @classmethod
    def calculate_xp_horizon(
        cls,
        player: PlayerDTO,
        fixtures: List[FixtureContext],
        horizon_gws: int = 3,
        current_gw: int = 1,
        recent_xps: Optional[List[float]] = None,
        avg_mins_last_5: float = 90.0,
        is_wildcard_active: bool = False,
        mins_last_3_gws: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Calculates multi-Gameweek composite Expected Points (xP) horizon with 
        dynamic time decay factors and expected bonus points model.
        """
        effective_horizon = min(5, max(1, horizon_gws))

        if not fixtures or effective_horizon <= 0:
            base_xp = player.form if player.form > 0 else 2.0
            return {
                "total_xp_horizon": round(base_xp * effective_horizon, 2),
                "next_gw_xp": round(base_xp, 2),
                "w_form": 1.0,
                "p_availability": 1.0,
                "p_card_risk": 1.0,
                "w_fixture": 1.0,
                "xgi_factor": 1.0,
                "xgi_status": "Ölçülü",
                "effective_horizon": effective_horizon
            }
            
        w_form = cls.calculate_form_momentum(player, recent_xps)
        p_avail = cls.calculate_availability(player, avg_mins_last_5=avg_mins_last_5, mins_last_3_gws=mins_last_3_gws)
        p_card_risk = cls.calculate_card_risk(player, current_gw)
        set_piece_boost = cls.calculate_set_piece_boost(player)
        xgi_factor, xgi_status = cls.calculate_xgi_regression_factor(player)
        
        pos_map = {1: 'GKP', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        pos_str = pos_map.get(player.element_type, 'MID')
        mins_val = getattr(player, 'minutes', 0) or 0
        bps_val = getattr(player, 'bps', 0) or 0
        avg_bps_per90 = (bps_val / (mins_val / 90.0)) if mins_val > 0 else (bps_val * 1.0 if bps_val > 0 else 20.0)
        opp_bps_res = getattr(player, 'opponent_bps_resistance', 0.0) or 0.0
        
        # Calibrate expected bonus to realistic FPL range [0.0 - 1.25]
        raw_bonus = cls.calculate_expected_bonus_points(avg_bps_per90, pos_str, opp_bps_res)
        expected_bonus_pts = round(min(1.25, raw_bonus * 0.45), 2)

        fixture_dicts = []
        for idx, f in enumerate(fixtures[:effective_horizon]):
            matches_cnt = getattr(f, 'matches_in_gw', 1) if not isinstance(f, dict) else f.get('matches_in_gw', 1)
            f_gw = getattr(f, 'gw', current_gw + idx) if not isinstance(f, dict) else f.get('gw', current_gw + idx)
            fixture_dicts.append({
                'gw': f_gw,
                'is_dgw': matches_cnt > 1,
                'is_bgw': matches_cnt == 0,
                'has_match': matches_cnt > 0
            })

        decay_weights = cls.calculate_dynamic_time_decay(
            horizon_weeks=effective_horizon,
            current_gw=current_gw,
            team_fixtures=fixture_dicts,
            is_wildcard_active=is_wildcard_active
        )
        
        total_horizon_xp = 0.0
        next_gw_xp = 0.0
        
        mins_played = getattr(player, 'minutes', 0) or 0
        n90s = max(0.1, mins_played / 90.0)

        # Positional priors for Bayesian shrinkage on small samples (<500 mins)
        priors_xg = {1: 0.0, 2: 0.04, 3: 0.16, 4: 0.32}
        priors_xa = {1: 0.0, 2: 0.06, 3: 0.14, 4: 0.12}

        raw_xg90 = (getattr(player, 'expected_goals', 0.0) or 0.0) / n90s if mins_played > 0 else priors_xg.get(player.element_type, 0.10)
        raw_xa90 = (getattr(player, 'expected_assists', 0.0) or 0.0) / n90s if mins_played > 0 else priors_xa.get(player.element_type, 0.10)

        # Bayesian shrinkage: Regress to positional mean if sample size is small
        sample_weight = min(1.0, mins_played / 500.0) if mins_played > 0 else 0.0
        xg_per90 = (sample_weight * raw_xg90) + ((1.0 - sample_weight) * priors_xg.get(player.element_type, 0.10))
        xa_per90 = (sample_weight * raw_xa90) + ((1.0 - sample_weight) * priors_xa.get(player.element_type, 0.10))

        raw_xgc90 = (getattr(player, 'expected_goals_conceded', 0.0) or 0.0) / n90s if mins_played > 0 else 1.25
        team_xgc_per90 = max(0.5, min(2.8, raw_xgc90))

        for k, fixture in enumerate(fixtures[:effective_horizon]):
            discount = decay_weights[k] if k < len(decay_weights) else 0.10
            
            match_multiplier = getattr(fixture, 'matches_in_gw', 1)
            if match_multiplier == 0:
                composite_gw_xp = 0.0
            else:
                effective_mins = p_avail * (avg_mins_last_5 if avg_mins_last_5 is not None else 90.0)
                base_xp = XPCalculator.calculate_xp_single_fixture(
                    element_type=player.element_type,
                    xg_per90=xg_per90,
                    xa_per90=xa_per90,
                    team_xgc_per90=team_xgc_per90,
                    expected_mins=effective_mins,
                    fixture_ctx=fixture
                )
                
                defensive_base_boost = cls.calculate_defensive_base_boost(player)
                
                # Single-fixture points calculation with balanced additive bonuses
                single_match_xp = (base_xp * w_form * xgi_factor) + (defensive_base_boost * 0.5) + (set_piece_boost * 0.5) + expected_bonus_pts
                single_match_xp = max(0.0, single_match_xp)
                
                composite_gw_xp = single_match_xp * p_card_risk * match_multiplier
            
            if k == 0:
                next_gw_xp = composite_gw_xp
                
            total_horizon_xp += discount * composite_gw_xp
            
        w_fixture = cls.calculate_fixture_weight(fixtures[:effective_horizon], player.element_type)
        first_fix = fixtures[0] if fixtures else None
        boom_prob, boom_index = cls.calculate_boom_metrics(player, next_gw_xp, first_fix)
        
        return {
            "total_xp_horizon": round(max(0.0, total_horizon_xp), 2),
            "next_gw_xp": round(max(0.0, next_gw_xp), 2),
            "w_form": round(w_form, 2),
            "p_availability": round(p_avail, 2),
            "p_card_risk": round(p_card_risk, 2),
            "w_fixture": round(w_fixture, 2),
            "xgi_factor": round(xgi_factor, 2),
            "xgi_status": xgi_status,
            "effective_horizon": effective_horizon,
            "boom_prob": boom_prob,
            "boom_index": boom_index
        }


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.models import PlayerDTO
    from core.xp_calculator import FixtureContext

    print("Running CompositeXPCalculator Sanity Checks...")
    
    # 1. Test apply_injury_ramp_up_penalty
    p_pen = apply_injury_ramp_up_penalty(0.80, [0.0, 0.0, 0.0])
    p_no_pen = apply_injury_ramp_up_penalty(0.80, [90.0, 0.0, 0.0])
    print(f"Ramp-up penalty test: 0.80 -> {p_pen} (with 0 mins), {p_no_pen} (with 90 mins)")
    assert p_pen == 0.64
    assert p_no_pen == 0.80

    # 2. Test calculate_expected_bonus_points
    b1 = CompositeXPCalculator.calculate_expected_bonus_points(28.0, 'MID', 0.0)
    assert b1 > 0.3, f"Expected bonus > 0.3, got {b1}"
    b_zero = CompositeXPCalculator.calculate_expected_bonus_points(0.0, 'DEF', 0.0)
    assert b_zero == 0.0, f"Expected 0.0 for 0 BPS, got {b_zero}"
    
    # 3. Test calculate_dynamic_time_decay
    fixtures_test = [
        {'gw': 1, 'is_dgw': False, 'is_bgw': False, 'has_match': True},
        {'gw': 2, 'is_dgw': True, 'is_bgw': False, 'has_match': True},
        {'gw': 3, 'is_dgw': False, 'is_bgw': True, 'has_match': False}
    ]
    decay_res = CompositeXPCalculator.calculate_dynamic_time_decay(3, 10, fixtures_test, is_wildcard_active=False)
    assert len(decay_res) == 3, "Decay vector length mismatch"
    assert decay_res[1] == 0.8, f"Expected 0.8 for DGW week 2, got {decay_res[1]}"
    
    # 4. Test PlayerDTO & calculate_xp_horizon integration
    p_dummy = PlayerDTO(
        id=999,
        web_name="TestPlayer",
        team=1,
        element_type=3,
        now_cost=80,
        bps=350,
        minutes=1200,
        expected_goals=0.4,
        expected_assists=0.3
    )
    fix_ctx = [FixtureContext(fdr=2, is_home=True, opponent_strength_attack=3, opponent_strength_defence=3)]
    res = CompositeXPCalculator.calculate_xp_horizon(p_dummy, fix_ctx, horizon_gws=1, mins_last_3_gws=[0.0, 0.0, 0.0])
    assert "total_xp_horizon" in res, "Missing total_xp_horizon in result"
    assert res["total_xp_horizon"] > 0, "Expected positive xP horizon"
    
    print("[SUCCESS] All CompositeXPCalculator Sanity Checks Passed Successfully!")



