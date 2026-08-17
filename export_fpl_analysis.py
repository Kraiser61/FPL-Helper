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
POS_COLORS = {1: "#d97706", 2: "#2563eb", 3: "#059669", 4: "#7c3aed"}
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

HTML_HEADER = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }
    html, body {
      background-color: #070a12 !important;
      color: #ffffff;
      margin: 0;
      padding: 12px;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
      line-height: 1.45;
    }
    .card {
      background: #111827;
      border: 1.5px solid #1f293d;
      border-radius: 16px;
      padding: 14px;
      margin-bottom: 12px;
      box-shadow: 0 4px 14px rgba(0,0,0,0.4);
    }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 13px;
    }
    .player-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #0b1120;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid #1f293d;
      margin-bottom: 6px;
    }
  </style>
</head>
<body>
"""

HTML_FOOTER = """
</body>
</html>
"""

# 1. TRANSFER CARD (Balanced Native iOS Size)
def format_html_transfer(bundle: DecisionBundle) -> str:
    action = bundle.primary_action
    action_type = action.get("type", "roll_ft")

    body = []
    body.append(f"""
    <div class="card">
      <div style="font-size: 20px; font-weight: 800; color: #38bdf8;">🎯 HAFTALIK TRANSFER</div>
      <div style="font-size: 14px; font-weight: 600; color: #94a3b8; margin-top: 4px;">
        Gameweek: <strong style="color: #38bdf8; font-size: 15px;">GW{bundle.current_gw}</strong> │ Bütçe: <strong style="color: #4ade80; font-size: 15px;">£{bundle.bank_amount:.1f}m</strong>
      </div>
      <div style="margin-top: 8px;">
        <span class="badge" style="background:#2e1065; color:#c084fc; border: 1px solid #7c3aed;">{bundle.available_transfers_str}</span>
      </div>
    </div>
    """)

    if action_type == "transfer" and action.get("transfers_in") and action.get("transfers_out"):
        p_in = action["transfers_in"][0]
        p_out = action["transfers_out"][0]
        in_name = p_in.web_name if hasattr(p_in, "web_name") else str(p_in)
        out_name = p_out.web_name if hasattr(p_out, "web_name") else str(p_out)
        in_cost = (p_in.now_cost / 10.0) if hasattr(p_in, "now_cost") else 0.0
        out_cost = (p_out.now_cost / 10.0) if hasattr(p_out, "now_cost") else 0.0
        in_team = p_team(p_in) if hasattr(p_in, "team_id") else ""
        out_team = p_team(p_out) if hasattr(p_out, "team_id") else ""
        in_pos = p_pos(p_in) if hasattr(p_in, "element_type") else "MID"
        out_pos = p_pos(p_out) if hasattr(p_out, "element_type") else "MID"

        body.append(f"""
        <!-- OUT PLAYER -->
        <div class="card" style="background:#220e14; border: 1.5px solid #ef4444; border-left: 6px solid #ef4444; margin-bottom: 6px;">
          <div style="font-size: 13px; font-weight: 800; color: #f87171; text-transform: uppercase;">❌ SATILACAK OYUNCU</div>
          <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 3px 0;">{out_name}</div>
          <div style="font-size: 14px; font-weight: 600; color: #fca5a5;">{out_team} │ {out_pos} │ £{out_cost:.1f}m</div>
        </div>

        <!-- ARROW -->
        <div style="text-align: center; font-size: 22px; font-weight: 900; color: #38bdf8; margin: 4px 0;">⬇️</div>

        <!-- IN PLAYER -->
        <div class="card" style="background:#07271b; border: 1.5px solid #10b981; border-left: 6px solid #10b981; margin-bottom: 10px;">
          <div style="font-size: 13px; font-weight: 800; color: #34d399; text-transform: uppercase;">✅ ALINACAK OYUNCU</div>
          <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 3px 0;">{in_name}</div>
          <div style="font-size: 14px; font-weight: 600; color: #86efac;">{in_team} │ {in_pos} │ £{in_cost:.1f}m</div>
        </div>

        <!-- STATS BLOCK -->
        <div class="card">
          <div style="font-size: 13px; font-weight: 700; color: #94a3b8;">📊 NET PUAN BEKLENTİSİ:</div>
          <div style="font-size: 28px; font-weight: 900; color: #4ade80; margin: 3px 0;">+{action.get('net_xp_gain', 0.0):.1f} xP</div>
          <div style="font-size: 15px; font-weight: 600; color: #e2e8f0;">Kalan Banka Bütçesi: £{action.get('budget_remaining', 0.0):.1f}m</div>
        </div>

        <!-- REASONS -->
        <div class="card">
          <div style="font-size: 15px; font-weight: 800; color: #38bdf8; margin-bottom: 8px;">💡 STRATEJİK GEREKÇELER:</div>
        """)
        for r in action.get("reasons", []):
            clean_r = r.replace("<b>", "<strong style='color:#ffffff;'>").replace("</b>", "</strong>")
            body.append(f"<div style='font-size: 14px; color: #e2e8f0; margin-bottom: 6px; line-height: 1.4;'>• {clean_r}</div>")
        body.append("</div>")

    else:
        body.append(f"""
        <div class="card" style="border: 1.5px solid #38bdf8; border-left: 6px solid #38bdf8;">
          <div style="font-size: 13px; font-weight: 800; color: #38bdf8; text-transform: uppercase;">🛡️ STRATEJİK KARAR</div>
          <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 4px 0;">Transfer Yapma (Roll FT)</div>
          <div style="font-size: 14px; color: #94a3b8; font-weight: 500;">Hakkınızı saklayarak sonraki haftaya 2 FT ile girin.</div>
        </div>

        <div class="card">
          <div style="font-size: 15px; font-weight: 800; color: #38bdf8; margin-bottom: 8px;">💡 STRATEJİK GEREKÇE:</div>
          <div style="font-size: 14px; color: #e2e8f0; margin-bottom: 6px; line-height: 1.4;'>• Mevcut ilk 11'inizin puan potansiyeli bu hafta için dengeli.</div>
          <div style="font-size: 14px; color: #e2e8f0; margin-bottom: 6px; line-height: 1.4;'>• Acil transfer gerektiren kritik bir sakatlık bulunmuyor.</div>
          <div style="font-size: 14px; color: #e2e8f0; line-height: 1.4;'>• Transfer hakkını saklayarak sonraki haftaya <strong style='color:#4ade80;'>2 FT esnekliğiyle</strong> girmek daha yüksek puan getirisi sağlar.</div>
        </div>
        """)

    return HTML_HEADER + "".join(body) + HTML_FOOTER

# 2. LINEUP CARD
def format_html_lineup(bundle: DecisionBundle) -> str:
    lineup = bundle.lineup_summary
    cap = lineup.get("captain")
    vcap = lineup.get("vice_captain")
    starters = lineup.get("starters", [])
    bench = lineup.get("bench", [])

    body = []
    body.append(f"""
    <!-- CAPTAIN BLOCK -->
    <div class="card" style="background:#261a07; border: 1.5px solid #f59e0b; border-left: 6px solid #f59e0b;">
      <div style="font-size: 13px; font-weight: 800; color: #fbbf24; text-transform: uppercase;">👑 KAPTAN SEÇİMİ (2x Puan)</div>
    """)

    if cap:
        c_name = cap.web_name if hasattr(cap, "web_name") else cap.get("name", "N/A")
        c_xp = cap.xp_next_gw if hasattr(cap, "xp_next_gw") else cap.get("xp_next_gw", 0.0)
        c_team = p_team(cap) if hasattr(cap, "team_id") else ""
        c_own = cap.ownership if hasattr(cap, "ownership") else 0.0
        body.append(f"""
        <div style="font-size: 24px; font-weight: 800; color: #ffffff; margin: 3px 0;">{c_name} ({c_team})</div>
        <div style="font-size: 15px; font-weight: 700; color: #fde047;">Puan Beklentisi: {c_xp * 2:.1f} xP │ %{c_own:.1f} Sahip</div>
        """)

    if vcap:
        vc_name = vcap.web_name if hasattr(vcap, "web_name") else vcap.get("name", "N/A")
        vc_xp = vcap.xp_next_gw if hasattr(vcap, "xp_next_gw") else vcap.get("xp_next_gw", 0.0)
        vc_team = p_team(vcap) if hasattr(vcap, "team_id") else ""
        body.append(f"""
        <div style="margin-top: 8px; font-size: 14px; color: #cbd5e1; font-weight: 600; border-top: 1px solid #452c0a; padding-top: 6px;">
          🥈 2. Kaptan: <strong>{vc_name} ({vc_team})</strong> ── {vc_xp:.1f} xP
        </div>
        """)

    body.append(f"""
    </div>

    <!-- SQUAD HEADER -->
    <div class="card" style="padding: 10px 14px;">
      <span style="font-size: 18px; font-weight: 800; color: #38bdf8;">📋 İLK 11 KADROSU</span>
      <span style="float: right; font-size: 15px; font-weight: 700; color: #c084fc;">Diziliş: {lineup.get('formation', '3-5-2')}</span>
    </div>
    """)

    gkps = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 1]
    defs = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 2]
    mids = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 3]
    fwds = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 4]

    def _render_pos(p_list, title, emoji, border_color):
        body.append(f"""
        <div class="card" style="border-left: 5px solid {border_color}; padding: 10px 12px; margin-bottom: 8px;">
          <div style="font-size: 14px; font-weight: 800; color: {border_color}; margin-bottom: 6px;">{emoji} {title}</div>
        """)
        for p in p_list:
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            p_is_cap = " 👑(C)" if cap and getattr(cap, 'player_id', None) == getattr(p, 'player_id', None) else ""
            body.append(f"""
            <div class="player-row">
              <span style="font-size: 16px; font-weight: 700; color: #ffffff;">{p_name}{p_is_cap} <small style="color:#94a3b8; font-size:12px;">({p_tm})</small></span>
              <span style="font-size: 15px; font-weight: 800; color: #38bdf8;">{p_x:.1f} xP</span>
            </div>
            """)
        body.append("</div>")

    _render_pos(gkps, "KALECİ", "🧤", "#f59e0b")
    _render_pos(defs, "DEFANS", "🛡️", "#3b82f6")
    _render_pos(mids, "ORTA SAHA", "⚙️", "#10b981")
    _render_pos(fwds, "FORVET", "⚡", "#a855f7")

    if bench:
        body.append("""
        <div class="card" style="background:#0a0f1d; padding: 10px 12px;">
          <div style="font-size: 14px; font-weight: 800; color: #94a3b8; margin-bottom: 6px;">🪑 YEDEK KULÜBESİ</div>
        """)
        for idx, p in enumerate(bench):
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            body.append(f"""
            <div class="player-row" style="background:#060a14; padding: 7px 10px;">
              <span style="color: #cbd5e1; font-weight: 600; font-size: 14px;">{idx+1}. {p_name} ({p_tm})</span>
              <span style="color: #94a3b8; font-weight: 700; font-size: 14px;">{p_x:.1f} xP</span>
            </div>
            """)
        body.append("</div>")

    return HTML_HEADER + "".join(body) + HTML_FOOTER

# 3. GOLDEN PATH CARD
def format_html_golden_path(bundle: DecisionBundle) -> str:
    body = []
    body.append(f"""
    <div class="card">
      <div style="font-size: 20px; font-weight: 800; color: #c084fc;">🛣️ STRATEJİK YOL HARİTASI</div>
      <div style="font-size: 13px; color: #94a3b8; font-weight: 600; margin-top: 3px;">HiGHS MIP Çok Dönemli Plan</div>
    </div>
    """)

    for step in bundle.golden_path[:6]:
        gw_num = step.get("gw")
        act = step.get("action", "")
        target = step.get("target", "")
        body.append(f"""
        <div class="card" style="border-left: 5px solid #38bdf8; padding: 10px 12px; margin-bottom: 8px;">
          <div style="font-size: 13px; font-weight: 800; color: #38bdf8;">GAMEWEEK {gw_num}</div>
          <div style="font-size: 16px; font-weight: 700; color: #ffffff; margin: 3px 0;">{act}</div>
          <div style="font-size: 13px; color: #cbd5e1;">{target}</div>
        </div>
        """)

    return HTML_HEADER + "".join(body) + HTML_FOOTER

# 4. CHIPS & TIMING CARD
def format_html_chips(bundle: DecisionBundle) -> str:
    body = []
    body.append(f"""
    <div class="card">
      <div style="font-size: 20px; font-weight: 800; color: #fbbf24;">🃏 ÇİP & ZAMANLAMA</div>
      <div style="font-size: 14px; color: #fde047; font-weight: 700; margin-top: 4px;">Durum: {bundle.chips_status_str}</div>
    </div>

    <div class="card" style="background:#261a07; border: 1.5px solid #f59e0b; border-left: 6px solid #f59e0b;">
      <div style="font-size: 13px; font-weight: 800; color: #fbbf24; text-transform: uppercase;">🎯 ÇİP STRATEJİSİ</div>
      <div style="font-size: 15px; font-weight: 700; color: #ffffff; margin-top: 4px; line-height: 1.4;">{bundle.chip_advice}</div>
    </div>

    <div class="card" style="background:#0c2333; border: 1.5px solid #0284c7; border-left: 6px solid #0284c7;">
      <div style="font-size: 13px; font-weight: 800; color: #38bdf8; text-transform: uppercase;">⏱️ ZAMANLAMA KURALI</div>
      <div style="font-size: 15px; font-weight: 700; color: #ffffff; margin-top: 4px; line-height: 1.4;">{bundle.timing_advice}</div>
    </div>
    """)
    return HTML_HEADER + "".join(body) + HTML_FOOTER

# 5. HEALTH & PRICE RADAR CARD
def format_html_health_radar(bundle: DecisionBundle) -> str:
    body = []
    body.append("""
    <div class="card">
      <div style="font-size: 20px; font-weight: 800; color: #f87171;">🏥 SAĞLIK & FİYAT RADARI</div>
    </div>
    """)

    if bundle.squad_health_issues:
        body.append("""
        <div class="card" style="background:#220e14; border: 1.5px solid #ef4444; border-left: 6px solid #ef4444;">
          <div style="font-size: 13px; font-weight: 800; color: #f87171; text-transform: uppercase; margin-bottom: 8px;">⚠️ SAKATLIK / ŞÜPHELİ OYUNCULAR</div>
        """)
        for h in bundle.squad_health_issues:
            body.append(f"""
            <div style="padding: 6px 0; border-bottom: 1px solid #3d1b24;">
              <div style="font-size: 17px; font-weight: 800; color: #ffffff;">{h.get('web_name')} ── <span style="color:#f87171;">%{h.get('chance', 0)}</span></div>
              <div style="font-size: 13px; color: #fca5a5; margin-top: 2px;">{h.get('news', 'Durumu belirsiz')}</div>
            </div>
            """)
        body.append("</div>")
    else:
        body.append("""
        <div class="card" style="background:#07271b; border: 1.5px solid #10b981;">
          <div style="color: #4ade80; font-weight: 700; font-size: 16px;">✅ Kadroda sakatlık bulunmuyor (15/15 Sağlam).</div>
        </div>
        """)

    if bundle.price_alerts:
        body.append("""
        <div class="card">
          <div style="font-size: 14px; font-weight: 800; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px;">📈 FİYAT DEĞİŞİM ALARMLARI</div>
        """)
        for a in bundle.price_alerts[:4]:
            is_rise = a.get("direction") == "rise"
            color = "#4ade80" if is_rise else "#f87171"
            icon = "🔺 Artış" if is_rise else "🔻 Düşüş"
            body.append(f"""
            <div style="display: flex; justify-content: space-between; padding: 6px 0; font-size: 15px; border-bottom: 1px solid #1f293d;">
              <span style="font-weight: 700; color: #ffffff;">{a.get('web_name')}</span>
              <span style="font-weight: 800; color: {color};">{icon} (%{int(a.get('probability', 0)*100)})</span>
            </div>
            """)
        body.append("</div>")

    return HTML_HEADER + "".join(body) + HTML_FOOTER

async def generate_analysis_json(manager_id: int = DEFAULT_MANAGER_ID, horizon_gws: int = 8, output_path: Path = None):
    app_logger.info(f"Starting headless analysis for Manager {manager_id}...")
    
    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)
    engine = StrategyEngine(fpl_client=fpl_client, risk_profile="balanced")

    bundle = await engine.analyze(manager_id=manager_id, horizon_gws=horizon_gws)

    cards_html = {
        "transfer": format_html_transfer(bundle),
        "lineup": format_html_lineup(bundle),
        "golden_path": format_html_golden_path(bundle),
        "chips": format_html_chips(bundle),
        "health_radar": format_html_health_radar(bundle),
    }

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
        "cards": cards_html,
        "cards_html": cards_html,
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
