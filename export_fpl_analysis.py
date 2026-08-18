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
    6: "CHE", 7: "COV", 8: "CRY", 9: "EVE", 10: "FUL",
    11: "HUL", 12: "IPS", 13: "LEE", 14: "LIV", 15: "MCI",
    16: "MUN", 17: "NEW", 18: "NFO", 19: "TOT", 20: "SUN"
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

    # Ensure SQLite database schema and tables (e.g. api_cache_meta) are initialized
    from data.database import db_manager
    db_manager.init_db()

    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)

    # Check if command or raw team data was passed via environment variable (from Telegram / GitHub Action)
    raw_team_data = os.environ.get("RAW_TEAM_DATA", "").strip()
    cmd_lower = raw_team_data.lower()

    # Smart NLP intent matching for Turkish & English freeform sentences
    def matches_any(text: str, keywords: list) -> bool:
        return any(k in text for k in keywords)

    if matches_any(cmd_lower, ["yardim", "yardım", "help", "komut", "ne yapabilirsin", "nasıl kullanılır"]):
        send_telegram_report(format_telegram_help_report())
        return {}
    
    if matches_any(cmd_lower, ["optimal", "rüya", "ruya", "wildcard", "en iyi 15", "ideal kadro", "dream team"]):
        optimal_msg = solve_optimal_squad(horizon_gws=5)
        send_telegram_report(optimal_msg)
        return {}

    if cached_path.exists():
        try:
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if matches_any(cmd_lower, ["kaptan", "captain", "c kim", "kime verelim"]):
                send_telegram_report(format_telegram_captain_report(cached_data))
                return cached_data
            elif matches_any(cmd_lower, ["sakat", "revir", "sağlık", "saglik", "injury", "oynar mı"]):
                send_telegram_report(format_telegram_health_report(cached_data))
                return cached_data
            elif matches_any(cmd_lower, ["fikstür", "fikstur", "fixture", "schedule", "kolay maçlar"]):
                send_telegram_report(format_telegram_fixture_report(cached_data))
                return cached_data
            elif matches_any(cmd_lower, ["fiyat", "price", "zam", "düşüş", "artış"]):
                send_telegram_report(format_telegram_price_report(cached_data))
                return cached_data
        except Exception as e:
            app_logger.warning(f"Could not use cached analysis for {cmd_lower}: {e}")

    transfer_notification_text = ""
    squad_saved = False
    if raw_team_data:
        try:
            from ingestion.local_sync_server import save_synced_team_to_disk, load_synced_team_from_disk
            from ingestion.fpl_client import parse_raw_text_to_team_data
            import re
            from fuzzywuzzy import fuzz
            
            # Single transfer command: e.g. "/transfer Welbeck yerine Isak" or "/sat Haaland /al Watkins"
            if ("yerine" in cmd_lower or "/sat" in cmd_lower or "->" in cmd_lower or cmd_lower.startswith("/transfer") or cmd_lower.startswith("transfer")):
                synced = load_synced_team_from_disk()
                if synced and "team_data" in synced and "picks" in synced["team_data"]:
                    picks = synced["team_data"]["picks"]
                    bootstrap = await fpl_client.get_bootstrap_static()
                    parts = re.split(r'yerine|->|/sat|/al|/transfer|transfer|,', raw_team_data, flags=re.IGNORECASE)
                    parts = [p.strip() for p in parts if p.strip()]
                    if len(parts) >= 2:
                        p_out_str, p_in_str = parts[0], parts[1]
                        out_p = None
                        best_out_score = 0
                        for pick in picks:
                            p_obj = next((e for e in bootstrap.elements if e.id == pick["element"]), None)
                            if p_obj:
                                score = fuzz.token_sort_ratio(p_out_str.lower(), p_obj.web_name.lower())
                                if score > best_out_score and score >= 60:
                                    best_out_score = score
                                    out_p = p_obj
                        in_p = None
                        best_in_score = 0
                        for e in bootstrap.elements:
                            score = max(fuzz.token_sort_ratio(p_in_str.lower(), e.web_name.lower()), fuzz.token_sort_ratio(p_in_str.lower(), f"{e.first_name} {e.second_name}".lower()) if hasattr(e, 'first_name') else 0)
                            if score > best_in_score and score >= 65:
                                best_in_score = score
                                in_p = e
                        if out_p and in_p:
                            for pick in picks:
                                if pick["element"] == out_p.id:
                                    pick["element"] = in_p.id
                                    break
                            save_synced_team_to_disk({"manager_id": manager_id, "team_data": synced["team_data"]})
                            out_team = TEAM_NAMES.get(out_p.team, "")
                            in_team = TEAM_NAMES.get(in_p.team, "")
                            transfer_notification_text = (
                                f"🔄 <b>Transfer Başarıyla Uygulandı!</b>\n\n"
                                f"🔴 <b>Çıkan:</b> {out_p.web_name} ({out_team})\n"
                                f"🟢 <b>Giren:</b> {in_p.web_name} ({in_team})\n\n"
                                f"<i>Yeni kadronuzun strateji analizi için <b>/analiz</b> yazabilirsiniz.</i>\n\n"
                                f"🤖 <i>Kraiser61 AI Engine</i>"
                            )
                            send_telegram_report(transfer_notification_text)
                            app_logger.success(f"Updated squad transfer: {out_p.web_name} -> {in_p.web_name}")
                            return {}
            elif raw_team_data.startswith("{"):
                parsed_team = json.loads(raw_team_data)
                if isinstance(parsed_team, dict):
                    if "team_data" in parsed_team:
                        save_synced_team_to_disk(parsed_team)
                    elif "picks" in parsed_team:
                        save_synced_team_to_disk({"manager_id": manager_id, "team_data": parsed_team})
            elif len(raw_team_data) > 5 and not matches_any(cmd_lower, ["analiz", "analyze", "solve", "taktik", "kadrom", "durum", "strateji", "rapor"]):
                app_logger.info(f"Processing squad text from Telegram: {raw_team_data[:60]}...")
                bootstrap = await fpl_client.get_bootstrap_static()
                td = parse_raw_text_to_team_data(raw_team_data, bootstrap.elements)
                if td and td.get("picks") and len(td["picks"]) >= 11:
                    save_synced_team_to_disk({"manager_id": manager_id, "team_data": td})
                    squad_saved = True
                    app_logger.success(f"Successfully saved {len(td['picks'])} picks from Telegram message.")
                    send_telegram_report(f"✅ <b>{len(td['picks'])} Kişilik Kadronuz Başarıyla Kaydedildi!</b>\n\nHaftalık analizinizi almak için <b>/analiz</b> yazabilirsiniz.\n\n🤖 <i>Kraiser61 AI Engine</i>")
                    return {}
        except Exception as e:
            app_logger.error(f"Failed to parse RAW_TEAM_DATA from environment: {e}")

    # Check if the user specifically asked for full analysis or if it's a scheduled/direct trigger
    is_analysis_requested = (
        not raw_team_data or 
        raw_team_data.startswith("{") or 
        matches_any(cmd_lower, ["analiz", "analyze", "solve", "taktik", "kadrom", "durum", "strateji", "rapor", "öneri", "oner"])
    )

    if not is_analysis_requested:
        unrecog_msg = (
            "🤖 <b>Mesajınızı tam anlayamadım.</b>\n\n"
            "Kullanabileceğiniz komutlar:\n"
            "• <b>/analiz</b> ➔ Tam strateji ve 11 raporu\n"
            "• <b>/optimal</b> ➔ 100m'lik Rüya Takım\n"
            "• <b>/kaptan</b> ➔ Kaptan tavsiyesi\n"
            "• <b>/sakatlar</b> ➔ Sağlık ve sakatlık durumu\n"
            "• <b>/fikstur</b> ➔ Fikstür salıncağı\n"
            "• <b>/fiyat</b> ➔ Gece fiyat değişimleri\n"
            "• <b>/yardim</b> ➔ Detaylı komut rehberi"
        )
        send_telegram_report(unrecog_msg)
        return {}

    # Step 0: Scrape live FPL Review projections and build hybrid CSV
    try:
        from ingestion.fplreview_scraper import generate_hybrid_fplreview_csv
        await generate_hybrid_fplreview_csv(horizon_gws=horizon_gws)
    except Exception as e:
        app_logger.warning(f"FPL Review otomatik kazıma atlandı (yerleşik motor kullanılacak): {e}")
    
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

    # Format rich Telegram message
    tg_report = format_telegram_report(payload)
    payload["telegram_report"] = tg_report

    if output_path is None:
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_path = data_dir / "fpl_analysis.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    app_logger.success(f"Analysis JSON successfully generated at: {output_path}")

    # Send directly to Telegram if configured
    send_telegram_report(tg_report)

    return payload

def format_telegram_report(payload: dict, custom_header: str = "") -> str:
    meta = payload.get("meta", {})
    gw = meta.get("current_gw", 1)
    lineup = payload.get("lineup", {})
    action = payload.get("primary_action", {})
    chips = payload.get("chip_strategy", {})
    health = payload.get("squad_health", [])

    def get_pname(p):
        if not p or not isinstance(p, dict):
            return ""
        name = str(p.get("name") or p.get("web_name") or p.get("id") or "")
        team = p.get("team") or TEAM_NAMES.get(p.get("team_id"), "")
        if team and name:
            return f"{name} ({team})"
        return name

    lines = []
    if custom_header:
        lines.append(custom_header)
    else:
        lines.append(f"🦁 <b>FPL STRATEJİ RAPORU (GW{gw})</b>")
    lines.append(f"<i>Yapay Zeka & Poisson-Elo Projeksiyon Çözümü</i>\n")

    # 1. Kaptan & 2. Kaptan
    cap = lineup.get("captain", {})
    vc = lineup.get("vice_captain", {})
    cap_name = get_pname(cap) or "Belirlenmedi"
    vc_name = get_pname(vc) or "Belirlenmedi"
    lines.append(f"👑 <b>Kaptan:</b> {cap_name}")
    lines.append(f"🥈 <b>2. Kaptan:</b> {vc_name}\n")

    # 2. Transfer Kararı
    t_type = action.get("type", "roll_ft")
    if t_type == "roll_ft":
        lines.append("🎯 <b>Transfer:</b> 🛡️ Transferi Pas Geç (Roll FT)")
        lines.append(f"   <i>Tavsiye: Gelecek hafta için 2 FT biriktir.</i>\n")
    elif t_type == "single_transfer":
        tin = get_pname(action.get("transfers_in", [{}])[0])
        tout = get_pname(action.get("transfers_out", [{}])[0])
        gain = action.get("net_xp_gain", 0.0)
        lines.append(f"🎯 <b>Transfer:</b> 🔴 {tout} ➔ 🟢 {tin}")
        lines.append(f"   <i>Beklenen Net Kazanç: +{gain:.2f} xPts</i>\n")
    elif t_type == "double_transfer":
        tins = ", ".join([get_pname(p) for p in action.get("transfers_in", []) if get_pname(p)])
        touts = ", ".join([get_pname(p) for p in action.get("transfers_out", []) if get_pname(p)])
        gain = action.get("net_xp_gain", 0.0)
        lines.append(f"🎯 <b>Çift Transfer:</b> 🔴 {touts} ➔ 🟢 {tins}")
        lines.append(f"   <i>Beklenen Net Kazanç: +{gain:.2f} xPts</i>\n")

    # 3. İdeal 11 & Diziliş
    formation = lineup.get("formation", "3-5-2")
    total_xp = lineup.get("total_xp", 0.0)
    lines.append(f"📋 <b>İdeal 11 ({formation}) - Toplam xP: {total_xp}:</b>")
    starters = lineup.get("starters", [])
    
    gkps = [get_pname(p) for p in starters if (p.get("element_type") == 1 or p.get("pos") in ("GKP", "GK")) and get_pname(p)]
    defs = [get_pname(p) for p in starters if (p.get("element_type") == 2 or p.get("pos") in ("DEF",)) and get_pname(p)]
    mids = [get_pname(p) for p in starters if (p.get("element_type") == 3 or p.get("pos") in ("MID",)) and get_pname(p)]
    fwds = [get_pname(p) for p in starters if (p.get("element_type") == 4 or p.get("pos") in ("FWD",)) and get_pname(p)]
    
    if gkps: lines.append(f"🧤 <b>KL:</b> {', '.join(gkps)}")
    if defs: lines.append(f"🛡️ <b>DF:</b> {', '.join(defs)}")
    if mids: lines.append(f"⚙️ <b>OS:</b> {', '.join(mids)}")
    if fwds: lines.append(f"⚡ <b>FV:</b> {', '.join(fwds)}")

    bench = [get_pname(p) for p in lineup.get("bench", []) if get_pname(p)]
    if bench:
        lines.append(f"🪑 <b>Yedekler:</b> {', '.join(bench)}\n")
    else:
        lines.append("")

    # 4. Çip Tavsiyesi
    chip_adv = chips.get("chip_advice")
    if chip_adv:
        lines.append(f"🚀 <b>Çip Stratejisi:</b> {chip_adv}\n")

    # 5. Sağlık / Sakatlık Radarı
    if health:
        lines.append("🏥 <b>Sağlık / Sakatlık Radarı:</b>")
        for h in health:
            w_name = h.get("web_name")
            t_id = h.get("team") or h.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            chance = h.get("chance")
            news = h.get("news", "Belirsiz")
            status_emoji = "🔴" if chance == 0 else "🟡"
            lines.append(f"{status_emoji} <b>{w_name}{team_str}:</b> %{chance if chance is not None else '?'} ({news})")
        lines.append("")

    lines.append("🤖 <i>Kraiser61 AI Engine</i>")
    return "\n".join(lines)

def format_telegram_captain_report(payload: dict) -> str:
    meta = payload.get("meta", {})
    gw = meta.get("current_gw", 1)
    lineup = payload.get("lineup", {})
    cap = lineup.get("captain", {})
    vc = lineup.get("vice_captain", {})
    
    lines = []
    lines.append(f"👑 <b>KAPTAN & DİFERANSİYEL RADARI (GW{gw})</b>\n")
    if cap:
        c_name = cap.get("name") or cap.get("web_name")
        c_team = cap.get("team") or TEAM_NAMES.get(cap.get("team_id"), "")
        c_xp = cap.get("xp_next_gw", 0.0)
        c_boom = cap.get("boom_index", 0.0)
        lines.append(f"🥇 <b>1. Kaptan Tercihi:</b> {c_name} ({c_team})")
        lines.append(f"   • Beklenen Puan: <b>{c_xp:.1f} xP</b> (Kaptanlık: <b>{c_xp*2:.1f} xP</b>)")
        lines.append(f"   • Patlama İndeksi: <b>{c_boom:.1f}/10</b>\n")
    if vc:
        v_name = vc.get("name") or vc.get("web_name")
        v_team = vc.get("team") or TEAM_NAMES.get(vc.get("team_id"), "")
        v_xp = vc.get("xp_next_gw", 0.0)
        lines.append(f"🥈 <b>2. Kaptan (Güvenli):</b> {v_name} ({v_team})")
        lines.append(f"   • Beklenen Puan: <b>{v_xp:.1f} xP</b>\n")
    
    starters = lineup.get("starters", [])
    diffs = [p for p in starters if p.get("ownership", 100) < 20 and (not cap or p.get("id") != cap.get("id"))]
    if diffs:
        diffs.sort(key=lambda x: x.get("xp_next_gw", 0), reverse=True)
        d = diffs[0]
        d_name = d.get("name") or d.get("web_name")
        d_team = d.get("team") or TEAM_NAMES.get(d.get("team_id"), "")
        d_own = d.get("ownership", 0)
        d_xp = d.get("xp_next_gw", 0)
        lines.append(f"🔥 <b>Diferansiyel Adayı (Düşük Sahiplik):</b>")
        lines.append(f"   • <b>{d_name} ({d_team})</b> - %{d_own:.1f} Sahiplik ({d_xp:.1f} xP)\n")
        
    lines.append("🤖 <i>Kraiser61 AI Engine</i>")
    return "\n".join(lines)

def format_telegram_health_report(payload: dict) -> str:
    health = payload.get("squad_health", [])
    lines = []
    lines.append("🏥 <b>SQUAD SAĞLIK & SAKATLIK RADARI</b>\n")
    if not health:
        lines.append("✅ <b>Harika Haber:</b> Kadronuzdaki 15 oyuncunun tamamı %100 oynamaya hazır (Available) durumda!\n")
    else:
        lines.append("⚠️ <b>Şüpheli veya Sakat Oyuncularınız:</b>")
        for h in health:
            w_name = h.get("web_name")
            t_id = h.get("team") or h.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            chance = h.get("chance")
            news = h.get("news", "Belirsiz")
            status_emoji = "🔴" if chance == 0 else "🟡"
            lines.append(f"{status_emoji} <b>{w_name}{team_str}:</b> %{chance if chance is not None else '?'} ({news})")
        lines.append("\n<i>Diğer tüm oyuncularınız oynamaya hazırdır.</i>\n")
    lines.append("🤖 <i>Kraiser61 AI Engine</i>")
    return "\n".join(lines)

def format_telegram_fixture_report(payload: dict) -> str:
    swings = payload.get("fixture_swings", [])
    lines = []
    lines.append("📈 <b>FİKSTÜR SALINCAĞI (ÖNÜMÜZDEKİ 5 HAFTA)</b>\n")
    if isinstance(swings, list) and swings:
        lines.append("🔄 <b>Önemli Fikstür Dönüşü Yaşayan Takımlar:</b>")
        for idx, item in enumerate(swings[:5], 1):
            t_name = item.get("team_name") or TEAM_NAMES.get(item.get("team_id"), f"Team {item.get('team_id')}")
            near = item.get("near_fdr", 2.5)
            far = item.get("far_fdr", 3.5)
            lines.append(f"  {idx}. <b>{t_name}</b> ➔ Yakın Zorluk: <b>{near:.1f}</b> | İleri Zorluk: <b>{far:.1f}</b>")
        lines.append("")
    else:
        lines.append("📊 Önümüzdeki 5 hafta için dengeli bir fikstür dağılımı mevcut.\n")
    lines.append("🤖 <i>Kraiser61 AI Engine</i>")
    return "\n".join(lines)

def format_telegram_price_report(payload: dict) -> str:
    alerts = payload.get("price_alerts", [])
    lines = []
    lines.append("💰 <b>FİYAT DEĞİŞİM RADARI (BU GECE)</b>\n")
    if isinstance(alerts, list) and alerts:
        lines.append("📊 <b>Fiyat Değişim Riski/Fırsatı Olan Oyuncular:</b>")
        for a in alerts[:6]:
            p_name = a.get("web_name") or a.get("name", "Oyuncu")
            change = a.get("type", "artış/düşüş")
            t_id = a.get("team") or a.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            lines.append(f"  • <b>{p_name}{team_str}</b>: {change}")
        lines.append("")
    else:
        lines.append("📈 Bu gece kadronuzu etkileyen kritik bir fiyat değişimi riski bulunmuyor.\n")
    lines.append("🤖 <i>Kraiser61 AI Engine</i>")
    return "\n".join(lines)

def format_telegram_help_report() -> str:
    lines = [
        "📖 <b>FPL AI BOT KOMUT REHBERİ</b>\n",
        "🔹 <b>/analiz</b> ➔ Kayıtlı kadronuzun haftalık tam strateji analizi (Kaptan, İdeal 11, Transfer, Çip, Sakatlıklar).",
        "🔹 <b>/optimal</b> (veya <b>/ruyatimi</b>) ➔ £100m bütçe ile 590 oyuncu arasından çözülen en ideal 15 kişilik kadro.",
        "🔹 <b>/kaptan</b> ➔ O haftanın en iyi 2 kaptan tercihi ve patlama indeksi yüksek diferansiyel oyuncu.",
        "🔹 <b>/sakatlar</b> (veya <b>/revir</b>) ➔ Kadronuzdaki şüpheli/sakat oyuncuların son basın toplantısı raporları.",
        "🔹 <b>/fikstur</b> ➔ Önümüzdeki 5 hafta fikstürü en çok kolaylaşan ve zorlaşan takımlar.",
        "🔹 <b>/fiyat</b> ➔ O gece fiyatı artması veya düşmesi beklenen piyasa alarmları.",
        "🔹 <b>/transfer [Çıkan] yerine [Giren]</b> ➔ Kadrodan tek bir oyuncuyu değiştirir (Örn: <code>/transfer Welbeck yerine Isak</code>).",
        "🔹 <b>/kadro [15 Oyuncu]</b> ➔ Tüm 15 kişilik kadronuzu sıfırdan kaydeder.",
        "🔹 <b>/yardim</b> ➔ Bu komut listesini ekrana getirir.\n",
        "⏰ <i>Otomatik Deadline Alarmları: Maç saatine 4 saat ve 1 saat kala otomatik rapor cebinize gelir.</i>\n",
        "🤖 <i>Kraiser61 AI Engine</i>"
    ]
    return "\n".join(lines)

def solve_optimal_squad(horizon_gws: int = 5) -> str:
    from core.solver.service import FPLSolverService
    try:
        solver = FPLSolverService()
        results = solver.run_optimization(
            team_data={"picks": [], "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}},
            options_override={"preseason": True, "horizon": horizon_gws}
        )
        if not results:
            return "❌ Optimal kadro çözülemedi."
        r = results[0]
        df = r.picks[r.picks["week"] == 1]
        
        gkps = df[df["pos"] == "GKP"]
        defs = df[df["pos"] == "DEF"]
        mids = df[df["pos"] == "MID"]
        fwds = df[df["pos"] == "FWD"]
        
        total_cost = df["buy_price"].sum()
        total_xp = df[df["lineup"] == 1]["xP"].sum()
        cap_row = df[df["captain"] == 1]
        if not cap_row.empty:
            total_xp += cap_row.iloc[0]["xP"]
            
        def fmt_group(sub_df):
            items = []
            for _, row in sub_df.iterrows():
                star = "⭐ " if row.get("captain") == 1 else ""
                items.append(f"{star}<b>{row['name']}</b> ({row['team']} - £{row['buy_price']:.1f}m)")
            return ", ".join(items)
            
        lines = []
        lines.append(f"✨ <b>MATEMATİKSEL EN OPTİMAL 15 (WILDCARD / RÜYA TAKIM)</b>")
        lines.append(f"<i>£100.0m Bütçe Kısıtı | 590 Oyuncu Arasından MIP Çözümü</i>\n")
        lines.append(f"🧤 <b>KL:</b> {fmt_group(gkps)}")
        lines.append(f"🛡️ <b>DF:</b> {fmt_group(defs)}")
        lines.append(f"⚙️ <b>OS:</b> {fmt_group(mids)}")
        lines.append(f"⚡ <b>FV:</b> {fmt_group(fwds)}\n")
        lines.append(f"💰 <b>Toplam Harcanan:</b> £{total_cost:.1f}m (Kalan Bütçe: £{100.0 - total_cost:.1f}m)")
        lines.append(f"📈 <b>11 Kişilik Beklenen Puan (GW1):</b> <b>{total_xp:.1f} xP</b>")
        lines.append(f"📊 <b>{horizon_gws} Haftalık Toplam xP:</b> <b>{r.total_xp:.1f} xP</b>\n")
        lines.append("🤖 <i>Kraiser61 AI Engine</i>")
        return "\n".join(lines)
    except Exception as e:
        app_logger.error(f"Optimal squad solve error: {e}")
        return f"❌ Optimal kadro hesaplanırken hata oluştu: {e}"

def send_telegram_report(report_text: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        app_logger.info("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured in environment.")
        return False
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": report_text,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                app_logger.success("Telegram analysis report sent successfully!")
                return True
    except Exception as e:
        app_logger.error(f"Failed to send Telegram message: {e}")
    return False

def check_deadline_window() -> tuple[bool, str]:
    """
    Checks if the upcoming GW deadline is in ~4h or ~1h window.
    Returns (should_run, headline_label).
    """
    import urllib.request
    from datetime import datetime, timezone
    try:
        req = urllib.request.Request("https://fantasy.premierleague.com/api/bootstrap-static/", headers={"User-Agent": "FPL-Deadline-Checker"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        events = data.get("events", [])
        now_epoch = datetime.now(timezone.utc).timestamp()
        next_event = next((e for e in events if e.get("is_next") or not e.get("finished")), None)
        if next_event:
            deadline_epoch = next_event.get("deadline_time_epoch")
            hours_left = (deadline_epoch - now_epoch) / 3600.0
            gw_name = next_event.get("name", "Gameweek")
            
            if 3.0 <= hours_left < 4.5:
                return True, f"⏰ <b>DEADLINE'A 4 SAAT KALDI ({gw_name})</b>"
            elif 0.2 <= hours_left < 1.5:
                return True, f"🚨 <b>SON 1 SAAT - NİHAİ KADRO RAPORU ({gw_name})</b>"
            else:
                app_logger.info(f"{gw_name} deadline'ına {hours_left:.1f} saat var. Otomatik bildirim penceresi (4h / 1h) dışında. İşlem atlanıyor.")
                return False, ""
    except Exception as e:
        app_logger.warning(f"Could not check deadline window: {e}")
    return False, ""

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    
    # Check if scheduled deadline check
    if "--check-deadline" in sys.argv:
        should_run, deadline_label = check_deadline_window()
        if not should_run:
            sys.exit(0)
    
    mgr_id = DEFAULT_MANAGER_ID
    for arg in sys.argv[1:]:
        if arg.isdigit():
            mgr_id = int(arg)
            break

    asyncio.run(generate_analysis_json(manager_id=mgr_id))
