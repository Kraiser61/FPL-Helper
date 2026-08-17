import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure root directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import DEFAULT_MANAGER_ID
from core.strategy_engine import StrategyEngine, DecisionBundle, PlayerAnalysis
from ingestion.fpl_client import FPLClient
from ingestion.auth_manager import AuthManager
from utils.logger import app_logger

POS_NAMES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
TEAM_NAMES = {
    1: "ARS", 2: "AVL", 3: "BOU", 4: "BRE", 5: "BHA",
    6: "CHE", 7: "CRY", 8: "EVE", 9: "FUL", 10: "IPS",
    11: "LEI", 12: "LIV", 13: "MCI", 14: "MUN", 15: "NEW",
    16: "NFO", 17: "SOU", 18: "TOT", 19: "WHU", 20: "WOL"
}

def p_pos(p: PlayerAnalysis) -> str:
    return POS_NAMES.get(p.element_type, "MID") if p else "MID"

def p_team(p: PlayerAnalysis) -> str:
    return TEAM_NAMES.get(p.team_id, "FPL") if p else "FPL"

def serialize_player(p: PlayerAnalysis) -> dict:
    if not p:
        return {}
    return {
        "id": p.player_id,
        "name": p.web_name,
        "element_type": p.element_type,
        "pos": p_pos(p),
        "team_id": p.team_id,
        "team": p_team(p),
        "cost": p.now_cost / 10.0,
        "xp_next_gw": round(p.xp_next_gw, 2),
        "form": p.w_form,
        "chance_playing": int(p.p_availability * 100),
        "status": p.status,
        "news": p.news,
        "ownership": p.ownership,
        "boom_index": round(p.boom_index, 1),
    }

def format_card_transfer(bundle: DecisionBundle) -> str:
    lines = []
    lines.append("╔══════════════════════════════════════╗")
    lines.append(f"║     🎯 HAFTALIK TRANSFER HAMLESİ     ║")
    lines.append("╚══════════════════════════════════════╝")
    lines.append(f"📅 Gameweek: GW{bundle.current_gw}  │  🕒 {bundle.generated_at[:16]}")
    lines.append(f"💰 Bütçe: £{bundle.bank_amount:.1f}m   │  🔄 Hak: {bundle.available_transfers_str}")
    lines.append("────────────────────────────────────────")

    action = bundle.primary_action
    action_type = action.get("type", "roll_ft")

    if action_type == "transfer" and action.get("transfers_in") and action.get("transfers_out"):
        p_in = action["transfers_in"][0]
        p_out = action["transfers_out"][0]
        in_name = p_in.web_name if hasattr(p_in, "web_name") else str(p_in)
        out_name = p_out.web_name if hasattr(p_out, "web_name") else str(p_out)
        in_cost = (p_in.now_cost / 10.0) if hasattr(p_in, "now_cost") else 0.0
        out_cost = (p_out.now_cost / 10.0) if hasattr(p_out, "now_cost") else 0.0
        in_team = p_team(p_in) if hasattr(p_in, "team_id") else ""
        out_team = p_team(p_out) if hasattr(p_out, "team_id") else ""

        lines.append("🔄 ÖNERİLEN HAMLE:")
        lines.append(f"  ❌ ÇIKAN : {out_name} ({out_team} - £{out_cost:.1f}m)")
        lines.append(f"  ✅ GİREN : {in_name} ({in_team} - £{in_cost:.1f}m)")
        lines.append("")
        lines.append("📊 HESAPLANAN VERİLER:")
        lines.append(f"  ├─ Net Puan Artışı : +{action.get('net_xp_gain', 0.0):.1f} xP")
        lines.append(f"  ├─ Kalan Kasa (£)  : £{action.get('budget_remaining', 0.0):.1f}m")
        lines.append(f"  └─ Ceza Puanı      : {action.get('hit_cost', 0)} Puan")
        lines.append("")
        lines.append("💡 STRATEJİK GEREKÇE:")
        for r in action.get("reasons", []):
            clean_r = r.replace("<b>", "").replace("</b>", "")
            lines.append(f"  • {clean_r}")
    else:
        lines.append("🛡️ ÖNERİLEN HAMLE: TRANSFER YAPMA (ROLL FT)")
        lines.append("")
        lines.append("📊 GEREKÇE:")
        lines.append("  • Mevcut ilk 11'inizin puan potansiyeli bu hafta için dengeli.")
        lines.append("  • Acil transfer gerektiren kritik bir sakatlık bulunmuyor.")
        lines.append(f"  • Transfer hakkını saklayarak sonraki haftaya çoklu transfer esnekliğiyle girmeniz matematiksel olarak daha yüksek değer üretiyor.")

    return "\n".join(lines)

def format_card_lineup(bundle: DecisionBundle) -> str:
    lines = []
    lineup = bundle.lineup_summary
    cap = lineup.get("captain")
    vcap = lineup.get("vice_captain")
    starters = lineup.get("starters", [])
    bench = lineup.get("bench", [])

    lines.append("╔══════════════════════════════════════╗")
    lines.append("║        👑 KAPTAN TERCİHLERİ          ║")
    lines.append("╚══════════════════════════════════════╝")
    if cap:
        c_name = cap.web_name if hasattr(cap, "web_name") else cap.get("name", "N/A")
        c_xp = cap.xp_next_gw if hasattr(cap, "xp_next_gw") else cap.get("xp_next_gw", 0.0)
        c_team = p_team(cap) if hasattr(cap, "team_id") else ""
        c_own = cap.ownership if hasattr(cap, "ownership") else 0.0
        lines.append(f"👑 (C)  {c_name} ({c_team})  │ {c_xp * 2:.1f} xP (2x) │ %{c_own:.1f} Sahip")
    if vcap:
        vc_name = vcap.web_name if hasattr(vcap, "web_name") else vcap.get("name", "N/A")
        vc_xp = vcap.xp_next_gw if hasattr(vcap, "xp_next_gw") else vcap.get("xp_next_gw", 0.0)
        vc_team = p_team(vcap) if hasattr(vcap, "team_id") else ""
        lines.append(f"🥈 (VC) {vc_name} ({vc_team}) │ {vc_xp:.1f} xP      │ Güvenli Yedek")

    lines.append("")
    lines.append("╔══════════════════════════════════════╗")
    lines.append(f"║       📋 SAHAYA ÇIKACAK İLK 11       ║")
    lines.append(f"║           (Diziliş: {lineup.get('formation', '3-5-2')})            ║")
    lines.append("╚══════════════════════════════════════╝")

    # Group starters
    gkps = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 1]
    defs = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 2]
    mids = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 3]
    fwds = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 4]

    def _fmt(p_list, title, emoji):
        lines.append(f"{emoji} {title}")
        for idx, p in enumerate(p_list):
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            prefix = "└─" if idx == len(p_list) - 1 else "├─"
            lines.append(f"  {prefix} {p_name:<12} ({p_tm:<3}) ──► {p_x:.1f} xP")

    _fmt(gkps, "KALECİ", "🧤")
    _fmt(defs, "DEFANS", "🛡️")
    _fmt(mids, "ORTA SAHA", "⚙️")
    _fmt(fwds, "FORVET", "⚡")

    if bench:
        lines.append("")
        lines.append("────────────────────────────────────────")
        lines.append("🪑 YEDEK KULÜBESİ (Sıralama):")
        for idx, p in enumerate(bench):
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            lines.append(f"  {idx + 1}. {p_name:<12} ({p_tm:<3}) ──► {p_x:.1f} xP")

    return "\n".join(lines)

def format_card_golden_path(bundle: DecisionBundle) -> str:
    lines = []
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║     🛣️ STRATEJİK YOL HARİTASI        ║")
    lines.append("║        (Çok Haftalık Plan)           ║")
    lines.append("╚══════════════════════════════════════╝")
    for step in bundle.golden_path[:6]:
        gw_num = step.get("gw")
        act = step.get("action", "")
        target = step.get("target", "")
        lines.append(f"GW{gw_num:<2} │ {act}")
        if target:
            lines.append(f"     │ ↳ {target}")
        lines.append("─────┼──────────────────────────────────")
    return "\n".join(lines)

def format_card_chips(bundle: DecisionBundle) -> str:
    lines = []
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║      🃏 ÇİP & ZAMANLAMA REHBERİ      ║")
    lines.append("╚══════════════════════════════════════╝")
    lines.append(f"📌 Çip Durumu: {bundle.chips_status_str}")
    lines.append("")
    lines.append("🎯 ÇİP TAVSİYESİ:")
    lines.append(f"  {bundle.chip_advice}")
    lines.append("")
    lines.append("⏱️ ZAMANLAMA TAVSİYESİ:")
    lines.append(f"  {bundle.timing_advice}")
    return "\n".join(lines)

def format_card_health_radar(bundle: DecisionBundle) -> str:
    lines = []
    lines.append("╔══════════════════════════════════════╗")
    lines.append("║    🏥 SAKATLIK & FİYAT RADARI        ║")
    lines.append("╚══════════════════════════════════════╝")
    if bundle.squad_health_issues:
        lines.append("⚠️ SAKATLIK / ŞÜPHELİ OYUNCULAR:")
        for h in bundle.squad_health_issues:
            lines.append(f"  • {h.get('web_name')}: %{h.get('chance', 0)} ({h.get('news', 'Durumu belirsiz')})")
    else:
        lines.append("✅ Kadroda kritik bir sakatlık veya şüphe bulunmuyor (15/15 Sağlam).")

    lines.append("")
    if bundle.price_alerts:
        lines.append("📈 FİYAT DEĞİŞİM BEKLENTİLERİ:")
        for a in bundle.price_alerts[:4]:
            arrow = "🔺" if a.get("direction") == "rise" else "🔻"
            lines.append(f"  {arrow} {a.get('web_name')}: %{int(a.get('probability', 0)*100)} İhtimal")
    return "\n".join(lines)

def format_summary_text(bundle: DecisionBundle, manager_id: int) -> str:
    parts = [
        format_card_transfer(bundle),
        "",
        format_card_lineup(bundle),
        "",
        format_card_golden_path(bundle),
        "",
        format_card_chips(bundle),
    ]
    return "\n".join(parts)

async def generate_analysis_json(manager_id: int = DEFAULT_MANAGER_ID, horizon_gws: int = 8, output_path: Path = None):
    app_logger.info(f"Starting headless analysis for Manager {manager_id}...")
    
    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)
    engine = StrategyEngine(fpl_client=fpl_client, risk_profile="balanced")

    bundle = await engine.analyze(manager_id=manager_id, horizon_gws=horizon_gws)

    # Format JSON payload
    payload = {
        "meta": {
            "manager_id": manager_id,
            "current_gw": bundle.current_gw,
            "is_preseason": bundle.is_preseason,
            "generated_at": bundle.generated_at,
            "free_transfers": bundle.free_transfers_count,
            "bank": bundle.bank_amount,
            "chips_status": bundle.chips_status_str,
            "available_transfers_str": bundle.available_transfers_str,
        },
        "cards": {
            "transfer": format_card_transfer(bundle),
            "lineup": format_card_lineup(bundle),
            "golden_path": format_card_golden_path(bundle),
            "chips": format_card_chips(bundle),
            "health_radar": format_card_health_radar(bundle),
        },
        "summary_text": format_summary_text(bundle, manager_id),
        "primary_action": {
            "type": bundle.primary_action.get("type", "roll_ft"),
            "decision_code": bundle.primary_action.get("decision_code", ""),
            "transfers_in": [serialize_player(p) for p in bundle.primary_action.get("transfers_in", [])],
            "transfers_out": [serialize_player(p) for p in bundle.primary_action.get("transfers_out", [])],
            "net_xp_gain": bundle.primary_action.get("net_xp_gain", 0.0),
            "hit_cost": bundle.primary_action.get("hit_cost", 0),
            "budget_remaining": bundle.primary_action.get("budget_remaining", 0.0),
            "summary_reason": bundle.primary_action.get("summary_reason", ""),
            "reasons": bundle.primary_action.get("reasons", []),
        },
        "lineup": {
            "formation": bundle.lineup_summary.get("formation", "3-5-2"),
            "total_xp": round(bundle.lineup_summary.get("total_xp", 0.0), 2),
            "captain": serialize_player(bundle.lineup_summary.get("captain")),
            "vice_captain": serialize_player(bundle.lineup_summary.get("vice_captain")),
            "starters": [serialize_player(p) for p in bundle.lineup_summary.get("starters", [])],
            "bench": [serialize_player(p) for p in bundle.lineup_summary.get("bench", [])],
        },
        "golden_path": bundle.golden_path,
        "chip_strategy": {
            "chip_advice": bundle.chip_advice,
            "active_chip": bundle.active_chip,
            "available_chips": bundle.available_chips,
        },
        "timing_advice": bundle.timing_advice,
        "captain_picks": [
            {
                "player": serialize_player(cp.player),
                "captain_score": cp.captain_score,
                "is_differential": cp.is_differential,
                "boom_index": cp.boom_index,
                "reason": cp.reason,
            }
            for cp in bundle.captain_picks
        ],
        "squad_health": [
            {
                "web_name": h.get("web_name"),
                "element_type": h.get("element_type"),
                "chance": h.get("chance"),
                "news": h.get("news"),
                "status": h.get("status"),
            }
            for h in bundle.squad_health_issues
        ],
        "price_alerts": bundle.price_alerts,
        "fixture_swings": bundle.fixture_swings,
    }

    if output_path is None:
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_path = data_dir / "fpl_analysis.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    app_logger.success(f"Analysis JSON successfully generated at: {output_path}")
    return payload

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    mgr_id = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MANAGER_ID
    asyncio.run(generate_analysis_json(manager_id=mgr_id))
