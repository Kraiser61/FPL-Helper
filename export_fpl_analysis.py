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

# 1. TRANSFER CARD (100% Inline Styled for iOS Rich Text)
def format_html_transfer(bundle: DecisionBundle) -> str:
    action = bundle.primary_action
    action_type = action.get("type", "roll_ft")

    html = []
    html.append(f"""
    <div style="background-color: #0b0f19; color: #ffffff; padding: 14px; font-family: -apple-system, sans-serif;">
      
      <!-- HEADER -->
      <div style="background-color: #151d30; padding: 14px; border-radius: 14px; border: 2px solid #28354f; margin-bottom: 12px;">
        <div style="font-size: 22px; font-weight: 900; color: #38bdf8; margin-bottom: 6px;">🎯 HAFTALIK TRANSFER</div>
        <div style="font-size: 15px; color: #94a3b8; font-weight: 600;">
          Gameweek: <strong style="color: #38bdf8; font-size: 16px;">GW{bundle.current_gw}</strong> │ Bütçe: <strong style="color: #4ade80; font-size: 16px;">£{bundle.bank_amount:.1f}m</strong>
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

        html.append(f"""
        <!-- OUT PLAYER -->
        <div style="background-color: #1e1318; border: 2px solid #ef4444; border-left: 8px solid #ef4444; padding: 14px; border-radius: 12px; margin-bottom: 8px;">
          <div style="font-size: 13px; font-weight: 900; color: #f87171; text-transform: uppercase;">❌ SATILACAK OYUNCU</div>
          <div style="font-size: 20px; font-weight: 900; color: #ffffff; margin: 4px 0;">{out_name}</div>
          <div style="font-size: 15px; color: #fca5a5; font-weight: 700;">{out_team} │ {out_pos} │ £{out_cost:.1f}m</div>
        </div>

        <!-- ARROW -->
        <div style="text-align: center; font-size: 26px; font-weight: 900; color: #38bdf8; margin: 4px 0;">⬇️ ⬇️ ⬇️</div>

        <!-- IN PLAYER -->
        <div style="background-color: #0d231a; border: 2px solid #10b981; border-left: 8px solid #10b981; padding: 14px; border-radius: 12px; margin-bottom: 12px;">
          <div style="font-size: 13px; font-weight: 900; color: #34d399; text-transform: uppercase;">✅ ALINACAK OYUNCU</div>
          <div style="font-size: 20px; font-weight: 900; color: #ffffff; margin: 4px 0;">{in_name}</div>
          <div style="font-size: 15px; color: #86efac; font-weight: 700;">{in_team} │ {in_pos} │ £{in_cost:.1f}m</div>
        </div>

        <!-- STATS BLOCK -->
        <div style="background-color: #151d30; border: 2px solid #28354f; padding: 14px; border-radius: 14px; margin-bottom: 12px;">
          <div style="font-size: 14px; font-weight: 800; color: #94a3b8; margin-bottom: 6px;">📊 OPTİMİZASYON KAZANCI:</div>
          <div style="font-size: 24px; font-weight: 900; color: #4ade80;">+{action.get('net_xp_gain', 0.0):.1f} xP Puan Artışı</div>
          <div style="font-size: 15px; font-weight: 700; color: #e2e8f0; margin-top: 4px;">Kalan Kasa: £{action.get('budget_remaining', 0.0):.1f}m</div>
        </div>

        <!-- REASONS -->
        <div style="background-color: #151d30; border: 2px solid #28354f; padding: 14px; border-radius: 14px;">
          <div style="font-size: 16px; font-weight: 900; color: #38bdf8; margin-bottom: 8px;">💡 NEDEN BU HAMLE?</div>
        """)
        for r in action.get("reasons", []):
            clean_r = r.replace("<b>", "<strong style='color:#ffffff; font-size:16px;'>").replace("</b>", "</strong>")
            html.append(f"<div style='font-size: 15px; color: #e2e8f0; margin-bottom: 8px; line-height: 1.4;'>• {clean_r}</div>")
        html.append("</div>")

    else:
        html.append(f"""
        <div style="background-color: #151d30; border: 2px solid #38bdf8; border-left: 8px solid #38bdf8; padding: 16px; border-radius: 14px; margin-bottom: 12px;">
          <div style="font-size: 14px; font-weight: 900; color: #38bdf8; text-transform: uppercase;">🛡️ STRATEJİK KARAR</div>
          <div style="font-size: 22px; font-weight: 900; color: #ffffff; margin: 4px 0;">Transfer Yapma (Roll FT)</div>
          <div style="font-size: 15px; color: #94a3b8; font-weight: 600;">Hakkınızı saklayarak sonraki haftaya 2 FT ile girin.</div>
        </div>

        <div style="background-color: #151d30; border: 2px solid #28354f; padding: 14px; border-radius: 14px;">
          <div style="font-size: 16px; font-weight: 900; color: #38bdf8; margin-bottom: 8px;">💡 GEREKÇE:</div>
          <div style="font-size: 15px; color: #e2e8f0; margin-bottom: 8px; line-height: 1.4;">• Mevcut ilk 11'inizin puan potansiyeli bu hafta için dengeli.</div>
          <div style="font-size: 15px; color: #e2e8f0; margin-bottom: 8px; line-height: 1.4;">• Acil transfer gerektiren kritik bir sakatlık bulunmuyor.</div>
          <div style="font-size: 15px; color: #e2e8f0; line-height: 1.4;">• Transfer hakkını saklayarak sonraki haftaya <strong style='color:#4ade80;'>2 FT esnekliğiyle</strong> girmek daha yüksek matematiksel değer üretiyor.</div>
        </div>
        """)

    html.append("</div>")
    return "".join(html)

# 2. LINEUP CARD
def format_html_lineup(bundle: DecisionBundle) -> str:
    lineup = bundle.lineup_summary
    cap = lineup.get("captain")
    vcap = lineup.get("vice_captain")
    starters = lineup.get("starters", [])
    bench = lineup.get("bench", [])

    html = []
    html.append("""
    <div style="background-color: #0b0f19; color: #ffffff; padding: 14px; font-family: -apple-system, sans-serif;">
      
      <!-- CAPTAIN BLOCK -->
      <div style="background-color: #1e1910; border: 2px solid #f59e0b; border-left: 8px solid #f59e0b; padding: 14px; border-radius: 14px; margin-bottom: 12px;">
        <div style="font-size: 13px; font-weight: 900; color: #fbbf24; text-transform: uppercase;">👑 KAPTAN SEÇİMİ (2x Puan)</div>
    """)

    if cap:
        c_name = cap.web_name if hasattr(cap, "web_name") else cap.get("name", "N/A")
        c_xp = cap.xp_next_gw if hasattr(cap, "xp_next_gw") else cap.get("xp_next_gw", 0.0)
        c_team = p_team(cap) if hasattr(cap, "team_id") else ""
        c_own = cap.ownership if hasattr(cap, "ownership") else 0.0
        html.append(f"""
        <div style="font-size: 24px; font-weight: 900; color: #ffffff; margin: 4px 0;">{c_name} ({c_team})</div>
        <div style="font-size: 16px; font-weight: 800; color: #fde047;">Puan Beklentisi: {c_xp * 2:.1f} xP │ %{c_own:.1f} Sahip</div>
        """)

    if vcap:
        vc_name = vcap.web_name if hasattr(vcap, "web_name") else vcap.get("name", "N/A")
        vc_xp = vcap.xp_next_gw if hasattr(vcap, "xp_next_gw") else vcap.get("xp_next_gw", 0.0)
        vc_team = p_team(vcap) if hasattr(vcap, "team_id") else ""
        html.append(f"""
        <div style="margin-top: 8px; font-size: 15px; color: #cbd5e1; font-weight: 700;">
          🥈 2. Kaptan: <strong>{vc_name} ({vc_team})</strong> ── {vc_xp:.1f} xP
        </div>
        """)

    html.append(f"""
      </div>

      <!-- SQUAD HEADER -->
      <div style="background-color: #151d30; padding: 12px 14px; border-radius: 14px; border: 2px solid #28354f; margin-bottom: 12px;">
        <span style="font-size: 20px; font-weight: 900; color: #38bdf8;">📋 İLK 11 KADROSU</span>
        <span style="float: right; font-size: 16px; font-weight: 800; color: #a855f7;">{lineup.get('formation', '3-5-2')}</span>
      </div>
    """)

    gkps = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 1]
    defs = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 2]
    mids = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 3]
    fwds = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 4]

    def _render_pos(p_list, title, emoji, border_color):
        html.append(f"""
        <div style="background-color: #151d30; border: 1.5px solid #28354f; border-left: 6px solid {border_color}; padding: 12px; border-radius: 12px; margin-bottom: 10px;">
          <div style="font-size: 15px; font-weight: 900; color: {border_color}; margin-bottom: 6px;">{emoji} {title}</div>
        """)
        for p in p_list:
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            p_is_cap = " 👑(C)" if cap and getattr(cap, 'player_id', None) == getattr(p, 'player_id', None) else ""
            html.append(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid #1e293b;">
              <span style="font-size: 17px; font-weight: 700; color: #ffffff;">{p_name}{p_is_cap} <small style="color:#94a3b8; font-size:13px;">({p_tm})</small></span>
              <span style="font-size: 16px; font-weight: 900; color: #38bdf8;">{p_x:.1f} xP</span>
            </div>
            """)
        html.append("</div>")

    _render_pos(gkps, "KALECİ", "🧤", "#f59e0b")
    _render_pos(defs, "DEFANS", "🛡️", "#3b82f6")
    _render_pos(mids, "ORTA SAHA", "⚙️", "#10b981")
    _render_pos(fwds, "FORVET", "⚡", "#a855f7")

    if bench:
        html.append("""
        <div style="background-color: #0f172a; border: 1.5px solid #28354f; padding: 12px; border-radius: 12px; margin-top: 12px;">
          <div style="font-size: 15px; font-weight: 900; color: #94a3b8; margin-bottom: 6px;">🪑 YEDEK KULÜBESİ</div>
        """)
        for idx, p in enumerate(bench):
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            html.append(f"""
            <div style="display: flex; justify-content: space-between; padding: 5px 0; font-size: 15px;">
              <span style="color: #cbd5e1; font-weight: 600;">{idx+1}. {p_name} ({p_tm})</span>
              <span style="color: #94a3b8; font-weight: 700;">{p_x:.1f} xP</span>
            </div>
            """)
        html.append("</div>")

    html.append("</div>")
    return "".join(html)

# 3. GOLDEN PATH CARD
def format_html_golden_path(bundle: DecisionBundle) -> str:
    html = []
    html.append(f"""
    <div style="background-color: #0b0f19; color: #ffffff; padding: 14px; font-family: -apple-system, sans-serif;">
      <div style="background-color: #151d30; padding: 14px; border-radius: 14px; border: 2px solid #28354f; margin-bottom: 12px;">
        <div style="font-size: 22px; font-weight: 900; color: #a855f7;">🛣️ ÇOK HAFTALIK YOL HARİTASI</div>
        <div style="font-size: 14px; color: #94a3b8; font-weight: 600;">HiGHS MIP Çok Dönemli Matematiksel Plan</div>
      </div>
    """)

    for step in bundle.golden_path[:6]:
        gw_num = step.get("gw")
        act = step.get("action", "")
        target = step.get("target", "")
        html.append(f"""
        <div style="background-color: #151d30; border: 1.5px solid #28354f; border-left: 6px solid #38bdf8; padding: 14px; border-radius: 12px; margin-bottom: 10px;">
          <div style="font-size: 14px; font-weight: 900; color: #38bdf8;">GAMEWEEK {gw_num}</div>
          <div style="font-size: 17px; font-weight: 800; color: #ffffff; margin: 4px 0;">{act}</div>
          <div style="font-size: 14px; color: #cbd5e1; font-weight: 500;">{target}</div>
        </div>
        """)

    html.append("</div>")
    return "".join(html)

# 4. CHIPS & TIMING CARD
def format_html_chips(bundle: DecisionBundle) -> str:
    html = []
    html.append(f"""
    <div style="background-color: #0b0f19; color: #ffffff; padding: 14px; font-family: -apple-system, sans-serif;">
      
      <div style="background-color: #151d30; padding: 14px; border-radius: 14px; border: 2px solid #28354f; margin-bottom: 12px;">
        <div style="font-size: 22px; font-weight: 900; color: #fbbf24;">🃏 ÇİP & ZAMANLAMA</div>
        <div style="font-size: 15px; color: #fde047; font-weight: 700; margin-top: 4px;">Durum: {bundle.chips_status_str}</div>
      </div>

      <div style="background-color: #1e1910; border: 2px solid #f59e0b; border-left: 8px solid #f59e0b; padding: 14px; border-radius: 12px; margin-bottom: 12px;">
        <div style="font-size: 14px; font-weight: 900; color: #fbbf24; text-transform: uppercase;">🎯 ÇİP KULLANIM STRATEJİSİ</div>
        <div style="font-size: 16px; font-weight: 700; color: #ffffff; margin-top: 6px; line-height: 1.4;">{bundle.chip_advice}</div>
      </div>

      <div style="background-color: #0e1e2d; border: 2px solid #0284c7; border-left: 8px solid #0284c7; padding: 14px; border-radius: 12px;">
        <div style="font-size: 14px; font-weight: 900; color: #38bdf8; text-transform: uppercase;">⏱️ ZAMANLAMA KURALI</div>
        <div style="font-size: 16px; font-weight: 700; color: #ffffff; margin-top: 6px; line-height: 1.4;">{bundle.timing_advice}</div>
      </div>

    </div>
    """)
    return "".join(html)

# 5. HEALTH & PRICE RADAR CARD
def format_html_health_radar(bundle: DecisionBundle) -> str:
    html = []
    html.append("""
    <div style="background-color: #0b0f19; color: #ffffff; padding: 14px; font-family: -apple-system, sans-serif;">
      
      <div style="background-color: #151d30; padding: 14px; border-radius: 14px; border: 2px solid #28354f; margin-bottom: 12px;">
        <div style="font-size: 22px; font-weight: 900; color: #f87171;">🏥 SAĞLIK & FİYAT RADARI</div>
      </div>
    """)

    if bundle.squad_health_issues:
        html.append("""
        <div style="background-color: #1e1318; border: 2px solid #ef4444; border-left: 8px solid #ef4444; padding: 14px; border-radius: 12px; margin-bottom: 12px;">
          <div style="font-size: 14px; font-weight: 900; color: #f87171; text-transform: uppercase; margin-bottom: 8px;">⚠️ SAKATLIK / ŞÜPHELİ OYUNCULAR</div>
        """)
        for h in bundle.squad_health_issues:
            html.append(f"""
            <div style="padding: 8px 0; border-bottom: 1px solid #332026;">
              <div style="font-size: 18px; font-weight: 800; color: #ffffff;">{h.get('web_name')} ── <span style="color:#f87171;">%{h.get('chance', 0)}</span></div>
              <div style="font-size: 14px; color: #fca5a5; margin-top: 2px;">{h.get('news', 'Durumu belirsiz')}</div>
            </div>
            """)
        html.append("</div>")
    else:
        html.append("""
        <div style="background-color: #0d231a; border: 2px solid #10b981; border-left: 8px solid #10b981; padding: 14px; border-radius: 12px; margin-bottom: 12px;">
          <div style="font-size: 17px; font-weight: 800; color: #4ade80;">✅ Kadroda kritik bir sakatlık bulunmuyor (15/15 Sağlam).</div>
        </div>
        """)

    if bundle.price_alerts:
        html.append("""
        <div style="background-color: #151d30; border: 2px solid #28354f; padding: 14px; border-radius: 12px;">
          <div style="font-size: 15px; font-weight: 900; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px;">📈 FİYAT DEĞİŞİM ALARMLARI</div>
        """)
        for a in bundle.price_alerts[:4]:
            is_rise = a.get("direction") == "rise"
            color = "#4ade80" if is_rise else "#f87171"
            icon = "🔺 Fiyat Artışı" if is_rise else "🔻 Fiyat Düşüşü"
            html.append(f"""
            <div style="display: flex; justify-content: space-between; padding: 6px 0; font-size: 16px; border-bottom: 1px solid #1e293b;">
              <span style="font-weight: 700; color: #ffffff;">{a.get('web_name')}</span>
              <span style="font-weight: 800; color: {color};">{icon} (%{int(a.get('probability', 0)*100)})</span>
            </div>
            """)
        html.append("</div>")

    html.append("</div>")
    return "".join(html)

async def generate_analysis_json(manager_id: int = DEFAULT_MANAGER_ID, horizon_gws: int = 8, output_path: Path = None):
    app_logger.info(f"Starting headless analysis for Manager {manager_id}...")
    
    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)
    engine = StrategyEngine(fpl_client=fpl_client, risk_profile="balanced")

    bundle = await engine.analyze(manager_id=manager_id, horizon_gws=horizon_gws)

    # 100% Inline Styled HTML cards
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
