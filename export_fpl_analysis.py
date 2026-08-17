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

def serialize_player(p: PlayerAnalysis) -> dict:
    if not p:
        return {}
    return {
        "id": p.player_id,
        "name": p.web_name,
        "element_type": p.element_type,
        "team_id": p.team_id,
        "cost": p.now_cost / 10.0,
        "xp_next_gw": round(p.xp_next_gw, 2),
        "form": p.w_form,
        "chance_playing": int(p.p_availability * 100),
        "status": p.status,
        "news": p.news,
        "ownership": p.ownership,
        "boom_index": round(p.boom_index, 1),
    }

def format_summary_text(bundle: DecisionBundle, manager_id: int) -> str:
    """Creates a beautifully formatted text report ideal for iPhone 13 mini display."""
    lines = []
    lines.append(f"⚽ FPL STRATEJİ RAPORU (GW{bundle.current_gw})")
    lines.append(f"🕒 {bundle.generated_at}")
    lines.append("─────────────────────────")
    
    # 1. Primary Action
    action = bundle.primary_action
    action_type = action.get("type", "roll_ft")
    if action_type == "transfer" and action.get("transfers_in") and action.get("transfers_out"):
        p_in = action["transfers_in"][0].web_name if hasattr(action["transfers_in"][0], "web_name") else str(action["transfers_in"][0])
        p_out = action["transfers_out"][0].web_name if hasattr(action["transfers_out"][0], "web_name") else str(action["transfers_out"][0])
        lines.append("🎯 BU HAFTAKİ HAMLE:")
        lines.append(f"  ❌ ÇIK: {p_out}")
        lines.append(f"  ✅ AL : {p_in}")
        lines.append(f"  📈 Net Beklenti: +{action.get('net_xp_gain', 0.0):.1f} xP")
    else:
        lines.append("🎯 BU HAFTAKİ HAMLE:")
        lines.append("  🛡️ Transfer Yapma (Roll FT)")
        lines.append(f"  💡 Haftaya {bundle.free_transfers_count + 1 if bundle.free_transfers_count < 5 else 5} FT esnekliği kalacak.")

    lines.append(f"  💰 Kalan Bütçe: £{bundle.bank_amount:.1f}m | FT: {bundle.available_transfers_str}")
    lines.append("─────────────────────────")

    # 2. Lineup & Captains
    lineup = bundle.lineup_summary
    cap = lineup.get("captain")
    vcap = lineup.get("vice_captain")
    cap_name = cap.web_name if hasattr(cap, "web_name") else (cap.get("name", "N/A") if isinstance(cap, dict) else "N/A")
    cap_xp = cap.xp_next_gw if hasattr(cap, "xp_next_gw") else (cap.get("xp_next_gw", 0.0) if isinstance(cap, dict) else 0.0)
    vcap_name = vcap.web_name if hasattr(vcap, "web_name") else (vcap.get("name", "N/A") if isinstance(vcap, dict) else "N/A")
    vcap_xp = vcap.xp_next_gw if hasattr(vcap, "xp_next_gw") else (vcap.get("xp_next_gw", 0.0) if isinstance(vcap, dict) else 0.0)

    lines.append("👑 KAPTAN TERCİHLERİ:")
    lines.append(f"  (C)  {cap_name} ({cap_xp:.1f} xP)")
    lines.append(f"  (VC) {vcap_name} ({vcap_xp:.1f} xP)")
    lines.append(f"  📋 Diziliş: {lineup.get('formation', '3-5-2')}")
    lines.append("─────────────────────────")

    # 3. Golden Path (Next 4 Gameweeks)
    lines.append("🛣️ ÇOK HAFTALIK YOL HARİTASI:")
    for step in bundle.golden_path[:4]:
        gw_num = step.get("gw")
        act = step.get("action", "")
        # Clean icons for concise phone view
        lines.append(f"  GW{gw_num}: {act}")
    lines.append("─────────────────────────")

    # 4. Chip & Timing Advice
    lines.append("🃏 ÇİP & ZAMANLAMA STRATEJİSİ:")
    lines.append(f"  {bundle.chip_advice}")
    lines.append(f"  {bundle.timing_advice}")

    # 5. Health alerts if any
    if bundle.squad_health_issues:
        lines.append("─────────────────────────")
        lines.append("⚠️ SAKATLIK / ŞÜPHE UYARISI:")
        for h in bundle.squad_health_issues[:3]:
            lines.append(f"  • {h.get('web_name')}: %{h.get('chance', 0)} ({h.get('news', '')})")

    return "\n".join(lines)

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
if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    mgr_id = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MANAGER_ID
    asyncio.run(generate_analysis_json(manager_id=mgr_id))

