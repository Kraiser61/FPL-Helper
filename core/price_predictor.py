import math
import sys
import os
from typing import List, Dict, Any, Set, Optional, Tuple
from data.models import PlayerDTO
from utils.logger import app_logger

def apply_deadline_time_effect(base_prob: float, hours_to_deadline: Optional[float]) -> float:
    """
    Modulates price change probability based on proximity to the GW deadline.
    Uses Inverse Sigmoid (Logit) to extract net transfer velocity ratio (x = V/R_threshold),
    then applies time-sensitive steepness (k_eff = 5.2 for <24h) and threshold drop (0.80x for <6h).
    """
    if hours_to_deadline is None or hours_to_deadline >= 24.0:
        return base_prob
        
    if base_prob <= 0.001:
        return 0.0
    if base_prob >= 0.999:
        return 1.0
        
    k_base = 4.0
    
    # 1. Inverse Sigmoid to retrieve relative net transfer ratio (x)
    logit = math.log((1.0 - base_prob) / base_prob)
    x = 1.0 - (logit / k_base)
    
    # 2. Time-sensitive dynamic factors
    k_eff = k_base * 1.30  # <24 hours: Sigmoid steepness increases by 30% (5.2)
    
    threshold_multiplier = 1.0
    if hours_to_deadline < 6.0:
        threshold_multiplier = 0.80  # <6 hours: Effective threshold drops by 20%
        
    x_eff = x / threshold_multiplier
    
    # 3. Recompute modulated probability
    exponent = -k_eff * (x_eff - 1.0)
    
    if exponent > 50.0:
        return 0.0
    if exponent < -50.0:
        return 1.0
        
    p_new = 1.0 / (1.0 + math.exp(exponent))
    return round(p_new, 3)

class PricePredictor:
    """
    FPL Price Rise & Fall Prediction Engine based on transfer velocity and acceleration models.
    Implements v3.0 Acceleration-Weighted Sigmoid, Time-to-Deadline Modulation & Early/Late Transfer Cost Function.
    """

    BASE_NET_TRANSFER_THRESHOLD = 25_000  # Average net transfers needed for price change
    ACCELERATION_LAMBDA = 0.30            # Acceleration coefficient (lambda = 0.30)

    @classmethod
    def predict_rise_probability(
        cls, 
        player: PlayerDTO, 
        prev_net_transfers: Optional[float] = None,
        hours_to_deadline: Optional[float] = None
    ) -> float:
        """
        Calculates acceleration-weighted probability (0.0 to 1.0) of price rise, modulated by time-to-deadline.
        V_t = NetTransfers_t
        A_t = V_t - V_{t-1} (If V_{t-1} is unknown, A_t = 0.0)
        P(Rise) = 1 / (1 + exp(-4.0 * ((V_t + lambda * A_t) / R_threshold - 1.0)))
        """
        net_transfers = float((player.transfers_in_event or 0) - (player.transfers_out_event or 0))
        if net_transfers <= 0:
            return 0.0

        velocity = net_transfers
        acceleration = (velocity - prev_net_transfers) if prev_net_transfers is not None else 0.0

        ownership_scaling = max(0.4, min(2.5, (player.selected_by_percent or 5.0) / 10.0))
        r_threshold = cls.BASE_NET_TRANSFER_THRESHOLD * ownership_scaling

        adjusted_velocity = velocity + (cls.ACCELERATION_LAMBDA * acceleration)
        x = (adjusted_velocity / r_threshold) - 1.0
        prob = 1.0 / (1.0 + math.exp(-4.0 * x))
        base_prob = round(min(0.99, max(0.0, prob)), 3)
        
        return apply_deadline_time_effect(base_prob, hours_to_deadline)

    @classmethod
    def predict_fall_probability(
        cls, 
        player: PlayerDTO, 
        prev_net_transfers: Optional[float] = None,
        hours_to_deadline: Optional[float] = None
    ) -> float:
        """
        Calculates acceleration-weighted probability (0.0 to 1.0) of price fall, modulated by time-to-deadline.
        V_{t, fall} = NetTransfersOut_t
        A_{t, fall} = V_{t, fall} - V_{t-1, fall} (If V_{t-1} is unknown, A_t = 0.0)
        """
        net_transfers = float((player.transfers_out_event or 0) - (player.transfers_in_event or 0))
        if net_transfers <= 0:
            return 0.0

        velocity = net_transfers
        acceleration = (velocity - prev_net_transfers) if prev_net_transfers is not None else 0.0

        ownership_scaling = max(0.4, min(2.5, (player.selected_by_percent or 5.0) / 10.0))
        r_threshold = (cls.BASE_NET_TRANSFER_THRESHOLD * 0.80) * ownership_scaling

        adjusted_velocity = velocity + (cls.ACCELERATION_LAMBDA * acceleration)
        x = (adjusted_velocity / r_threshold) - 1.0
        prob = 1.0 / (1.0 + math.exp(-4.0 * x))
        base_prob = round(min(0.99, max(0.0, prob)), 3)
        
        return apply_deadline_time_effect(base_prob, hours_to_deadline)

    @classmethod
    def should_make_early_transfer(
        cls, 
        player: PlayerDTO, 
        prev_net_transfers: Optional[float] = None,
        injury_prob: Optional[float] = None,
        hours_to_deadline: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Evaluates Early vs. Late Transfer Trade-off Cost Function (C_early vs C_late).
        Decision Rule:
        - If P(Rise) >= 0.85 AND P(Injury) < 0.10: Return (True, "Erken Transfer Yap")
        - Otherwise: Return (False, "Cuma'ya Kadar Bekle")
        """
        p_rise = cls.predict_rise_probability(player, prev_net_transfers, hours_to_deadline)

        if injury_prob is None:
            p_fpl = player.get_normalized_chance_next()
            p_injury = 1.0 - p_fpl
        else:
            p_injury = injury_prob

        if p_rise >= 0.85 and p_injury < 0.10:
            reason = (
                f"⚡ ERKEN TRANSFER TAVSİYESİ: {player.web_name} için bu gece %{int(p_rise*100)} ihtimalle "
                f"£0.1m artış bekleniyor ve sakatlık riski düşük (%{int(p_injury*100)})."
            )
            return True, reason
        else:
            reason = (
                f"📌 TOP 10K ZAMANLAMA KURALI: {player.web_name} için fiyat artış riski (%{int(p_rise*100)}) "
                f"veya sakatlık riski (%{int(p_injury*100)}) Cuma basın toplantılarını beklemeyi gerektiriyor."
            )
            return False, reason

    @classmethod
    def predict_5day_rise_probability(cls, player: PlayerDTO) -> float:
        """
        Calculates 5-day cumulative horizon rise probability based on net inbound transfers and momentum.
        """
        net_transfers = float((player.transfers_in_event or 0) - (player.transfers_out_event or 0))
        if net_transfers <= 0:
            return 0.0
        ownership_scaling = max(0.4, min(2.5, (player.selected_by_percent or 5.0) / 10.0))
        r_threshold = cls.BASE_NET_TRANSFER_THRESHOLD * ownership_scaling
        
        projected_5d_velocity = net_transfers * 1.85
        x = (projected_5d_velocity / r_threshold) - 1.0
        prob = 1.0 / (1.0 + math.exp(-4.0 * x))
        return round(min(0.99, max(0.0, prob)), 3)

    @classmethod
    def predict_5day_fall_probability(cls, player: PlayerDTO) -> float:
        """
        Calculates 5-day cumulative horizon fall probability based on net outbound transfers.
        """
        net_transfers = float((player.transfers_out_event or 0) - (player.transfers_in_event or 0))
        if net_transfers <= 0:
            return 0.0
        ownership_scaling = max(0.4, min(2.5, (player.selected_by_percent or 5.0) / 10.0))
        r_threshold = (cls.BASE_NET_TRANSFER_THRESHOLD * 0.80) * ownership_scaling
        
        projected_5d_velocity = net_transfers * 1.85
        x = (projected_5d_velocity / r_threshold) - 1.0
        prob = 1.0 / (1.0 + math.exp(-4.0 * x))
        return round(min(0.99, max(0.0, prob)), 3)

    @classmethod
    def get_price_alerts(
        cls, 
        squad_ids: Set[int], 
        players: List[PlayerDTO], 
        threshold: float = 0.45,
        hours_to_deadline: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates actionable price movement alerts for current squad and targets across a 5-day horizon.
        Categorizes players into high likelihood (1-2 days / tonight) and medium likelihood (3-5 days).
        """
        alerts = []
        for p in players:
            rise_p_1d = cls.predict_rise_probability(p, hours_to_deadline=hours_to_deadline)
            rise_p_5d = cls.predict_5day_rise_probability(p)
            
            fall_p_1d = cls.predict_fall_probability(p, hours_to_deadline=hours_to_deadline)
            fall_p_5d = cls.predict_5day_fall_probability(p)
            
            in_squad = p.id in squad_ids

            effective_rise_p = max(rise_p_1d, rise_p_5d)
            if effective_rise_p >= threshold:
                is_high = (rise_p_1d >= 0.80 or rise_p_5d >= 0.90)
                likelihood = "high" if is_high else "medium"
                horizon_text = "1-2 Gün İçinde" if is_high else "3-5 Gün İçinde"
                should_early, timing_text = cls.should_make_early_transfer(p, hours_to_deadline=hours_to_deadline)
                alerts.append({
                    "player_id": p.id,
                    "web_name": p.web_name,
                    "team": p.team,
                    "team_id": p.team,
                    "element_type": p.element_type,
                    "direction": "rise",
                    "probability": effective_rise_p,
                    "probability_1d": rise_p_1d,
                    "probability_5d": rise_p_5d,
                    "likelihood": likelihood,
                    "horizon_text": horizon_text,
                    "price": p.now_cost / 10.0,
                    "in_squad": in_squad,
                    "urgency": "high" if is_high else "medium",
                    "should_early_transfer": should_early,
                    "timing_advice": timing_text,
                    "action_text": f"📈 {p.web_name} (%{int(effective_rise_p*100)} Artış - {horizon_text})"
                })

            effective_fall_p = max(fall_p_1d, fall_p_5d)
            if effective_fall_p >= threshold:
                is_high = (fall_p_1d >= 0.80 or fall_p_5d >= 0.90)
                likelihood = "high" if is_high else "medium"
                horizon_text = "1-2 Gün İçinde" if is_high else "3-5 Gün İçinde"
                alerts.append({
                    "player_id": p.id,
                    "web_name": p.web_name,
                    "team": p.team,
                    "team_id": p.team,
                    "element_type": p.element_type,
                    "direction": "fall",
                    "probability": effective_fall_p,
                    "probability_1d": fall_p_1d,
                    "probability_5d": fall_p_5d,
                    "likelihood": likelihood,
                    "horizon_text": horizon_text,
                    "price": p.now_cost / 10.0,
                    "in_squad": in_squad,
                    "urgency": "high" if is_high else "medium",
                    "should_early_transfer": False,
                    "timing_advice": "📉 Satış Uyarısı: Değer kaybını önlemek için fiyat düşmeden kadrodan çıkarın.",
                    "action_text": f"📉 {p.web_name} (%{int(effective_fall_p*100)} Düşüş - {horizon_text})"
                })

        alerts.sort(key=lambda x: (1 if x["in_squad"] else 0, x["probability"]), reverse=True)
        return alerts

    @classmethod
    def log_velocity(cls, players: List[PlayerDTO]):
        """Logs current transfer velocity snapshot to database for historical tracking."""
        try:
            from data.database import db_manager
            query = """
            INSERT INTO transfer_velocity_log (player_id, transfers_in, transfers_out, net_velocity, price_at_time, rise_prob, fall_prob)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            records = []
            for p in players:
                net = (p.transfers_in_event or 0) - (p.transfers_out_event or 0)
                rise_p = cls.predict_rise_probability(p)
                fall_p = cls.predict_fall_probability(p)
                records.append((p.id, p.transfers_in_event or 0, p.transfers_out_event or 0, float(net), p.now_cost, rise_p, fall_p))

            with db_manager.get_connection() as conn:
                conn.executemany(query, records)
                conn.commit()
        except Exception as e:
            app_logger.error(f"Failed to log velocity snapshot: {e}")


if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data.models import PlayerDTO

    print("Running PricePredictor Sanity Checks...")

    # 1. High velocity + positive acceleration
    p1 = PlayerDTO(id=1, web_name="Salah", team=1, element_type=3, now_cost=125, transfers_in_event=35000, transfers_out_event=5000, chance_of_playing_next_round=100)
    p_rise1 = PricePredictor.predict_rise_probability(p1, prev_net_transfers=20000)
    assert p_rise1 >= 0.85, f"Expected P(Rise) >= 0.85, got {p_rise1}"

    should_early1, reason1 = PricePredictor.should_make_early_transfer(p1, prev_net_transfers=20000)
    assert should_early1 is True, f"Expected should_make_early_transfer True, got {should_early1}"

    # 2. Time-to-deadline modulation tests
    p_base = 0.50
    p_48h = apply_deadline_time_effect(p_base, 48.0)
    p_12h = apply_deadline_time_effect(p_base, 12.0)
    p_4h = apply_deadline_time_effect(p_base, 4.0)
    
    print(f"Base P: {p_base}, 48h deadline P: {p_48h}, 12h deadline P: {p_12h}, 4h deadline P: {p_4h}")
    assert p_48h == 0.50
    assert p_4h > 0.70, "Near deadline (<6h) must boost rise probability significantly!"

    # 3. High rise probability but high injury risk
    p2 = PlayerDTO(id=2, web_name="Palmer", team=2, element_type=3, now_cost=105, transfers_in_event=35000, transfers_out_event=5000, chance_of_playing_next_round=50)
    should_early2, reason2 = PricePredictor.should_make_early_transfer(p2, prev_net_transfers=20000)
    assert should_early2 is False, f"Expected should_make_early_transfer False due to injury risk, got {should_early2}"

    # 4. Fall probability
    p3 = PlayerDTO(id=3, web_name="OutofFormDef", team=3, element_type=2, now_cost=50, transfers_in_event=1000, transfers_out_event=30000)
    p_fall = PricePredictor.predict_fall_probability(p3, prev_net_transfers=10000)
    assert p_fall >= 0.70, f"Expected P(Fall) >= 0.70, got {p_fall}"

    print("[SUCCESS] All PricePredictor Sanity Checks Passed Successfully!")


