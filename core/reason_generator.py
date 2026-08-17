from typing import List, Dict, Any, Optional, Tuple
from core.strategy_engine import PlayerAnalysis, ScenarioResult
from utils.logger import app_logger

def apply_nlg_tone_modulation(layer_id: int, original_text: str) -> str:
    """
    Modulates NLG (Natural Language Generation) tone based on the layer function.
    - Layer 1 & 2 (xP & Fixture): "📊 ANALİTİK:"
    - Layer 3 & 4 (Risk & Price): "⚠️ DİKKAT:"
    - Layer 5 & 6 (Form & Rank): "🎯 STRATEJİK İSABET:"
    """
    if layer_id in (1, 2):
        prefix = "📊 ANALİTİK:"
    elif layer_id in (3, 4):
        prefix = "⚠️ DİKKAT:"
    elif layer_id in (5, 6):
        prefix = "🎯 STRATEJİK İSABET:"
    else:
        prefix = "📌 NOT:"
        
    return f"{prefix} {original_text}"

def resolve_layer_conflicts(
    reasons: List[str],
    xp_diff: float,
    price_rise_prob: float,
    chance_of_playing: float,
    is_template: bool,
    eo_risk: float
) -> Tuple[List[str], str]:
    """
    Analyzes multi-layer data (xP, price, health, EO risk) to resolve conflicts and output a Net Value Summary.
    """
    # Durum 1: xP vs. Fiyat/Sağlık Çelişkisi
    if xp_diff > 1.0 and (price_rise_prob < 0.30 or chance_of_playing < 0.75):
        net_sentence = f"⚡ NET DEĞER ÖZETİ: Oyuncunun +{xp_diff:.1f} xP avantajı yüksek, ancak fiyat düşüşü veya sağlık riski nedeniyle transfer zamanlaması dikkatle değerlendirilmelidir."
    
    # Durum 2: xP vs. EO Risk Çelişkisi
    elif xp_diff > 1.5 and not is_template and eo_risk > 30.0:
        net_sentence = "🛡️ NET DEĞER ÖZETİ: Yüksek xP kazancına rağmen rakiplerin yüksek sahipliği (EO riski) nedeniyle sıralama koruması önceliklendirilmelidir."
        
    # Durum 3: Çelişki Yoksa
    else:
        net_sentence = "✅ NET DEĞER ÖZETİ: Tüm katmanlar pozitif ve birbiriyle uyumlu sinyaller üretmektedir."
        
    return reasons, net_sentence

def generate_6_layer_reasoning(
    player_in_name: str,
    player_out_name: str,
    xp_diff: float,
    fdr_in: float,
    is_home_in: bool,
    eo_risk_in: float,
    is_template_in: bool,
    price_rise_prob: float,
    form_in: float,
    chance_of_playing: float,
    rank_impact_band: str
) -> List[str]:
    """
    Generates structured 6-layer analytical decision justification with NLG tone modulation & layer conflict resolution:
    Katman 1: xP Karşılaştırma (Analitik)
    Katman 2: Fikstür Analizi (Analitik)
    Katman 3: EO Risk Uyarısı (Dikkat)
    Katman 4: Fiyat Hareketi (Dikkat)
    Katman 5: Form & Sağlık (Stratejik İsabet)
    Katman 6: Sıralama Etkisi (Stratejik İsabet)
    """
    reasons = []
    
    # Katman 1 (xP Karşılaştırma)
    t1 = f"[Katman 1 - xP]: {player_in_name}, {player_out_name} yerine +{xp_diff:.1f} xP beklentisi sagliyor."
    reasons.append(apply_nlg_tone_modulation(1, t1))
    
    # Katman 2 (Fikstür Analizi)
    venue = "Ev Sahibi" if is_home_in else "Deplasman"
    t2 = f"[Katman 2 - Fikstur]: Yeni oyuncu {venue} avantajina sahip ve zorluk derecesi (FDR) {fdr_in:.1f}."
    reasons.append(apply_nlg_tone_modulation(2, t2))
    
    # Katman 3 (EO Risk Uyarısı)
    if is_template_in:
        t3 = f"[Katman 3 - Risk]: Yuksek EO nedeniyle template kacirma riski (Risk Skoru: {eo_risk_in:.1f}). Transfer, siralama dususune karsi koruma sagliyor."
    else:
        t3 = f"[Katman 3 - Risk]: Dusuk EO ile Differential firsati (Risk Skoru: {eo_risk_in:.1f}). Siralama tirmanisi icin asimetrik getiri potansiyeli."
    reasons.append(apply_nlg_tone_modulation(3, t3))
        
    # Katman 4 (Fiyat Hareketi)
    if price_rise_prob >= 0.70:
        t4 = f"[Katman 4 - Fiyat]: Oyuncunun fiyatinin artma ihtimali cok yuksek (%{price_rise_prob*100:.0f}). Erken transfer yapilmasi onerilir."
    elif price_rise_prob <= 0.30:
        t4 = f"[Katman 4 - Fiyat]: Fiyat artis ivmesi zayif (%{price_rise_prob*100:.0f}), transfer aciliyeti bulunmuyor (Cumaya kadar beklenebilir)."
    else:
        t4 = f"[Katman 4 - Fiyat]: Fiyat stabil gorunuyor (%{price_rise_prob*100:.0f} artis ihtimali)."
    reasons.append(apply_nlg_tone_modulation(4, t4))
        
    # Katman 5 (Form & Sağlık)
    health = "Saglik durumu belirsiz/riskli" if chance_of_playing < 1.0 else "Tamamen saglikli"
    t5 = f"[Katman 5 - Form & Saglik]: Son form skoru {form_in:.1f}. {health} (Oynama Ihtimali: %{chance_of_playing*100:.0f})."
    reasons.append(apply_nlg_tone_modulation(5, t5))
    
    # Katman 6 (Sıralama Etkisi)
    t6 = f"[Katman 6 - Siralama]: Bu hamlenin tahmini siralama etkisi: {rank_impact_band}."
    reasons.append(apply_nlg_tone_modulation(6, t6))
    
    # Layer Conflict Resolution & Net Value Summary
    reasons, net_summary = resolve_layer_conflicts(
        reasons=reasons,
        xp_diff=xp_diff,
        price_rise_prob=price_rise_prob,
        chance_of_playing=chance_of_playing,
        is_template=is_template_in,
        eo_risk=eo_risk_in
    )
    reasons.append(net_summary)
    
    return reasons

class ReasonGenerator:
    """
    Generates human-readable strategic justifications ('Why this move?') 
    based on Top 10k & Hall-of-Fame FPL Manager Principles.
    """

    @classmethod
    def generate_transfer_reasons(cls, player_in: PlayerAnalysis, player_out: PlayerAnalysis, horizon_gws: int = 5) -> List[str]:
        """
        Generates structured 6-layer bullet points explaining why player_in replaces player_out,
        including tone modulation and conflict resolution summary.
        """
        xp_diff = player_in.xp_horizon - player_out.xp_horizon
        is_home = "v " in player_in.fixture_string or "vs" in player_in.fixture_string or not ("@" in player_in.fixture_string)
        is_template = player_in.ownership > 35.0
        rank_band = "Top 10k Koruma [SHIELD]" if is_template else "Siralama Tirmanisi [BOOST]"

        # Call 6-layer reasoning engine
        return generate_6_layer_reasoning(
            player_in_name=player_in.web_name,
            player_out_name=player_out.web_name,
            xp_diff=xp_diff,
            fdr_in=player_in.avg_fdr,
            is_home_in=is_home,
            eo_risk_in=player_in.eo_risk,
            is_template_in=is_template,
            price_rise_prob=player_in.price_rise_prob,
            form_in=player_in.w_form,
            chance_of_playing=player_in.p_availability,
            rank_impact_band=rank_band
        )

    @classmethod
    def populate_scenario_reasons(cls, scenario: ScenarioResult, horizon_gws: int = 5):
        """
        Populates reasons for all transfers in a scenario result.
        """
        if not scenario.transfers_in:
            scenario.reasons = [
                "🛡️ Top 10k Disiplin Kuralı: Mevcut kadronuz dengeli. Transfer harcamayıp devretmek (Roll FT) önümüzdeki haftalarda 2-3 FT esnekliği sağlar."
            ]
            return

        all_reasons = []
        for p_in, p_out in zip(scenario.transfers_in, scenario.transfers_out):
            all_reasons.extend(cls.generate_transfer_reasons(p_in, p_out, horizon_gws))

        if scenario.hit_cost > 0:
            all_reasons.append(f"⚠️ Hit Cezası (-{scenario.hit_cost}): Bu hamle -{scenario.hit_cost} puan maliyet gerektirir. Ancak net xP kazancı (+{scenario.net_xp_gain:.1f}) bu cezayı telafi etmektedir.")

        scenario.reasons = all_reasons

    @classmethod
    def generate_concise_human_reason(cls, player_in: PlayerAnalysis, player_out: PlayerAnalysis) -> str:
        """
        Generates a clean, 1-2 sentence human-readable justification for the recommended transfer.
        """
        xp_gain = player_in.xp_horizon - player_out.xp_horizon
        next_gain = player_in.xp_next_gw - player_out.xp_next_gw
        
        # 1. Health / Availability Issue
        if player_out.p_availability < 0.75 or player_out.status != "a":
            avail_pct = int(player_out.p_availability * 100)
            return (
                f"{player_out.web_name}'ın oynama riski (%{avail_pct} ihtimal) bulunuyor. "
                f"{player_in.web_name}, {player_in.fixture_string} fikstürüyle bu hafta "
                f"+{next_gain:.1f} net xP artışı sağlıyor."
            )
            
        # 2. Major Fixture Swing
        if player_in.avg_fdr <= player_out.avg_fdr - 0.7:
            return (
                f"{player_out.web_name} zorlu bir fikstüre sahipken, "
                f"{player_in.web_name} elverişli maç takvimi ile bu hafta "
                f"+{next_gain:.1f} net xP avantajı sunuyor."
            )
            
        # 3. Price Urgency
        if player_in.price_rise_prob >= 0.75:
            return (
                f"{player_in.web_name} için yakın dönemde fiyat artışı (%{int(player_in.price_rise_prob*100)}) bekleniyor. "
                f"{player_out.web_name} yerine yapılarak hem bütçe değerini korur hem de bu hafta +{next_gain:.1f} xP kazancı sağlar."
            )
            
        # 4. Standard Form & xP Upgrade
        return (
            f"{player_in.web_name}, {player_out.web_name} yerine bu haftanın fikstüründe "
            f"+{next_gain:.1f} net xP avantajı ve form grafiği vadediyor."
        )

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print("--- SANITY CHECK: core/reason_generator.py ---")
    
    # 1. Tone modulation test
    t1 = apply_nlg_tone_modulation(1, "xP testi")
    t3 = apply_nlg_tone_modulation(3, "Risk testi")
    t5 = apply_nlg_tone_modulation(5, "Form testi")
    assert t1.startswith("📊 ANALİTİK:")
    assert t3.startswith("⚠️ DİKKAT:")
    assert t5.startswith("🎯 STRATEJİK İSABET:")
    print("NLG Tone modulation tests passed.")

    # 2. Conflict resolution test
    _, net1 = resolve_layer_conflicts([], xp_diff=1.5, price_rise_prob=0.20, chance_of_playing=1.0, is_template=True, eo_risk=10.0)
    assert "fiyat düşüşü veya sağlık riski" in net1
    
    _, net2 = resolve_layer_conflicts([], xp_diff=2.0, price_rise_prob=0.80, chance_of_playing=1.0, is_template=False, eo_risk=40.0)
    assert "sıralama koruması" in net2
    
    _, net3 = resolve_layer_conflicts([], xp_diff=0.5, price_rise_prob=0.50, chance_of_playing=1.0, is_template=True, eo_risk=10.0)
    assert "uyumlu sinyaller" in net3
    print("Layer conflict resolution tests passed.")

    # 3. Test standalone 6-layer generator (6 layers + 1 summary line = 7 lines)
    reasons_7 = generate_6_layer_reasoning(
        player_in_name="Salah",
        player_out_name="Saka",
        xp_diff=3.5,
        fdr_in=2.0,
        is_home_in=True,
        eo_risk_in=40.0,
        is_template_in=True,
        price_rise_prob=0.85,
        form_in=7.5,
        chance_of_playing=1.0,
        rank_impact_band="Top 10k Koruma [SHIELD]"
    )
    print(f"\nGenerated {len(reasons_7)} total reason lines:")
    for r in reasons_7:
        print("  -", r)
        
    assert len(reasons_7) == 7
    assert "📊 ANALİTİK:" in reasons_7[0]
    assert "⚡ NET DEĞER ÖZETİ" in reasons_7[6] or "✅ NET DEĞER ÖZETİ" in reasons_7[6]
    
    # 4. Test ReasonGenerator.generate_transfer_reasons
    p_in = PlayerAnalysis(
        player_id=1, web_name="Salah", element_type=3, team_id=1, now_cost=130, selling_price=130,
        in_squad=False, is_locked=False, xp_next_gw=8.0, xp_horizon=24.0, w_form=7.5, p_availability=1.0,
        p_card_risk=0.0, price_rise_prob=0.85, price_fall_prob=0.0, predicted_price_gain=0.1,
        ownership=50.0, eo=80.0, template_score=40.0, differential_score=10.0, eo_risk=40.0,
        fixture_string="LIV v MUN", avg_fdr=2.0, yellow_cards=0, news="", status="a"
    )
    p_out = PlayerAnalysis(
        player_id=2, web_name="Saka", element_type=3, team_id=2, now_cost=100, selling_price=100,
        in_squad=True, is_locked=False, xp_next_gw=5.0, xp_horizon=15.0, w_form=5.0, p_availability=1.0,
        p_card_risk=0.0, price_rise_prob=0.1, price_fall_prob=0.5, predicted_price_gain=-0.1,
        ownership=40.0, eo=60.0, template_score=30.0, differential_score=10.0, eo_risk=20.0,
        fixture_string="ARS @ MCI", avg_fdr=4.0, yellow_cards=0, news="", status="a"
    )
    
    reasons_transfer = ReasonGenerator.generate_transfer_reasons(p_in, p_out)
    assert len(reasons_transfer) == 7
    print(f"\nTransfer Reasons Test Passed with {len(reasons_transfer)} output lines.")
    print("[SUCCESS] Reason generator sanity checks passed.")


