import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

TEAM_FULL_NAMES = {
    1: "Arsenal", 2: "Aston Villa", 3: "Bournemouth", 4: "Brentford", 5: "Brighton",
    6: "Chelsea", 7: "Coventry", 8: "Crystal Palace", 9: "Everton", 10: "Fulham",
    11: "Hull", 12: "Ipswich", 13: "Leeds", 14: "Liverpool", 15: "Man City",
    16: "Man Utd", 17: "Newcastle", 18: "Nott'm Forest", 19: "Tottenham", 20: "Sunderland"
}

def format_kickoff_tr(dt_val) -> tuple[str, str, str]:
    """
    Converts UTC datetime string/object to Turkey Time (UTC+3 / TSİ)
    and returns (day_str, time_str, sort_key).
    """
    from datetime import datetime, timezone, timedelta
    if isinstance(dt_val, str):
        clean_str = dt_val.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_str)
        except Exception:
            return ("Tarih Belirsiz", "Saat Belirsiz", "9999")
    elif isinstance(dt_val, datetime):
        dt = dt_val
    else:
        return ("Tarih Belirsiz", "Saat Belirsiz", "9999")
    
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tr_tz = timezone(timedelta(hours=3))
    dt_tr = dt.astimezone(tr_tz)
    
    months_tr = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    days_tr = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
        4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    
    day_str = f"{dt_tr.day} {months_tr.get(dt_tr.month, '')} {days_tr.get(dt_tr.weekday(), '')}"
    time_str = dt_tr.strftime("%H:%M")
    sort_key = dt_tr.strftime("%Y-%m-%d %H:%M")
    return (day_str, time_str, sort_key)

def is_fixture_finished(fix: dict) -> bool:
    if fix.get("finished") or fix.get("finished_provisional") or fix.get("minutes", 0) >= 90:
        return True
    if fix.get("started"):
        ko_str = fix.get("kickoff_time")
        if ko_str:
            try:
                from datetime import datetime, timezone
                clean_str = ko_str.replace("Z", "+00:00")
                ko_dt = datetime.fromisoformat(clean_str)
                if ko_dt.tzinfo is None:
                    ko_dt = ko_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                if (now_utc - ko_dt).total_seconds() > 110 * 60:
                    return True
            except Exception:
                pass
    return False

def format_telegram_matches_report(fixtures: list, gw_num: int = 1, deadline_val = None) -> str:
    if not fixtures:
        return f"⚠️ GW{gw_num} için fikstür verisi bulunamadı."

    from collections import defaultdict
    grouped = defaultdict(list)

    for f in fixtures:
        ko_str = f.get("kickoff_time")
        day_str, time_str, sort_key = format_kickoff_tr(ko_str)
        grouped[day_str].append((sort_key, time_str, f))

    lines = [
        f"🦁 <b>PREMIER LEAGUE GW{gw_num} MAÇ PROGRAMI (TSİ)</b>"
    ]
    if deadline_val:
        dl_day, dl_time, _ = format_kickoff_tr(deadline_val)
        if dl_day != "Tarih Belirsiz":
            is_past = False
            try:
                from datetime import datetime, timezone
                if isinstance(deadline_val, str):
                    d_obj = datetime.fromisoformat(deadline_val.replace("Z", "+00:00"))
                elif isinstance(deadline_val, datetime):
                    d_obj = deadline_val
                else:
                    d_obj = None
                if d_obj:
                    if d_obj.tzinfo is None:
                        d_obj = d_obj.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > d_obj:
                        is_past = True
            except Exception:
                pass
            status_note = " <i>(Süre doldu)</i>" if is_past else ""
            lines.append(f"⏰ <b>Son Değişiklik (Deadline):</b> {dl_day}, {dl_time}{status_note}\n")
        else:
            lines.append("")
    else:
        lines.append("")

    for day_str, match_list in grouped.items():
        match_list.sort(key=lambda x: x[0])
        lines.append(f"🗓️ <b>{day_str}</b>")
        for _, time_str, fix in match_list:
            h_id = fix.get("team_h")
            a_id = fix.get("team_a")
            h_team = fix.get("team_h_name") or TEAM_FULL_NAMES.get(h_id, f"Takım {h_id}")
            a_team = fix.get("team_a_name") or TEAM_FULL_NAMES.get(a_id, f"Takım {a_id}")
            
            finished = is_fixture_finished(fix)
            started = fix.get("started", False)
            h_score = fix.get("team_h_score")
            a_score = fix.get("team_a_score")

            if finished and h_score is not None and a_score is not None:
                match_str = f"• <b>{time_str}</b> ➔ {h_team} <b>{h_score} - {a_score}</b> {a_team} (Bitti)"
            elif started and h_score is not None and a_score is not None:
                match_str = f"• <b>{time_str}</b> ➔ {h_team} <b>{h_score} - {a_score}</b> {a_team} (🔴 Canlı)"
            else:
                match_str = f"• <b>{time_str}</b> ➔ <b>{h_team}</b> vs <b>{a_team}</b>"
            
            lines.append(match_str)
        lines.append("")

    lines.append("⏰ <i>Tüm başlama saatleri Türkiye saati (TSİ / GMT+3) ile verilmiştir.</i>")
    return "\n".join(lines)

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
        t_ins = action["transfers_in"]
        t_outs = action["transfers_out"]
        for idx in range(max(len(t_ins), len(t_outs))):
            p_out = t_outs[idx] if idx < len(t_outs) else None
            p_in = t_ins[idx] if idx < len(t_ins) else None
            if p_out:
                out_name = p_out.web_name if hasattr(p_out, "web_name") else (p_out.get("name") if isinstance(p_out, dict) else str(p_out))
                out_cost = (p_out.now_cost / 10.0) if hasattr(p_out, "now_cost") else (p_out.get("cost", 0.0) if isinstance(p_out, dict) else 0.0)
                out_team = p_team(p_out) if hasattr(p_out, "team_id") else (p_out.get("team", "") if isinstance(p_out, dict) else "")
                out_pos = p_pos(p_out) if hasattr(p_out, "element_type") else (p_out.get("pos", "MID") if isinstance(p_out, dict) else "MID")
                body.append(f"""
                <!-- OUT PLAYER -->
                <div class="card" style="background:#220e14; border: 1.5px solid #ef4444; border-left: 6px solid #ef4444; margin-bottom: 6px;">
                  <div style="font-size: 13px; font-weight: 800; color: #f87171; text-transform: uppercase;">❌ SATILACAK OYUNCU</div>
                  <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 3px 0;">{out_name}</div>
                  <div style="font-size: 14px; font-weight: 600; color: #fca5a5;">{out_team} │ {out_pos} │ £{out_cost:.1f}m</div>
                </div>

                <!-- ARROW -->
                <div style="text-align: center; font-size: 22px; font-weight: 900; color: #38bdf8; margin: 4px 0;">⬇️</div>
                """)
            if p_in:
                in_name = p_in.web_name if hasattr(p_in, "web_name") else (p_in.get("name") if isinstance(p_in, dict) else str(p_in))
                in_cost = (p_in.now_cost / 10.0) if hasattr(p_in, "now_cost") else (p_in.get("cost", 0.0) if isinstance(p_in, dict) else 0.0)
                in_team = p_team(p_in) if hasattr(p_in, "team_id") else (p_in.get("team", "") if isinstance(p_in, dict) else "")
                in_pos = p_pos(p_in) if hasattr(p_in, "element_type") else (p_in.get("pos", "MID") if isinstance(p_in, dict) else "MID")
                body.append(f"""
                <!-- IN PLAYER -->
                <div class="card" style="background:#07271b; border: 1.5px solid #10b981; border-left: 6px solid #10b981; margin-bottom: 10px;">
                  <div style="font-size: 13px; font-weight: 800; color: #34d399; text-transform: uppercase;">✅ ALINACAK OYUNCU</div>
                  <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 3px 0;">{in_name}</div>
                  <div style="font-size: 14px; font-weight: 600; color: #86efac;">{in_team} │ {in_pos} │ £{in_cost:.1f}m</div>
                </div>
                """)

        body.append(f"""
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
        if bundle.is_preseason or bundle.current_gw == 1:
            title = "Kadroyu Koru (Değişiklik Yok)"
            subtitle = "Sezonun 1. haftasına mevcut 15 kişilik kadronuzla başlayın."
            r3 = "GW1 teslim saati (deadline) sonrası GW2 için 1 Serbest Transfer (1 FT) hakkınız tanımlanacaktır."
        else:
            title = "Transfer Yapma (Roll FT)"
            subtitle = "Hakkınızı saklayarak sonraki haftaya devredin."
            r3 = "Transfer hakkını saklayarak sonraki haftaya <strong style='color:#4ade80;'>çoklu FT esnekliğiyle</strong> girmek daha yüksek puan getirisi sağlar."

        body.append(f"""
        <div class="card" style="border: 1.5px solid #38bdf8; border-left: 6px solid #38bdf8;">
          <div style="font-size: 13px; font-weight: 800; color: #38bdf8; text-transform: uppercase;">🛡️ STRATEJİK KARAR</div>
          <div style="font-size: 22px; font-weight: 800; color: #ffffff; margin: 4px 0;">{title}</div>
          <div style="font-size: 14px; color: #94a3b8; font-weight: 500;">{subtitle}</div>
        </div>

        <div class="card">
          <div style="font-size: 15px; font-weight: 800; color: #38bdf8; margin-bottom: 8px;">💡 STRATEJİK GEREKÇE:</div>
          <div style="font-size: 14px; color: #e2e8f0; margin-bottom: 6px; line-height: 1.4;'>• Mevcut ilk 11'inizin puan potansiyeli bu hafta için dengeli.</div>
          <div style="font-size: 14px; color: #e2e8f0; margin-bottom: 6px; line-height: 1.4;'>• Acil transfer gerektiren kritik bir sakatlık bulunmuyor.</div>
          <div style="font-size: 14px; color: #e2e8f0; line-height: 1.4;'>• {r3}</div>
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
      <div style="font-size: 13px; color: #94a3b8; font-weight: 600; margin-top: 3px;">Haftalık Strateji Planı</div>
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

def is_analysis_fresh(cached_data: dict, max_hours: float = 2.0) -> bool:
    if not cached_data or not cached_data.get("meta"):
        return False
    meta = cached_data["meta"]
    gen_epoch = meta.get("generated_at_epoch")
    if gen_epoch:
        diff_hours = (time.time() - gen_epoch) / 3600.0
        return diff_hours <= max_hours
    gen_iso = meta.get("generated_at_iso") or meta.get("generated_at")
    if gen_iso:
        try:
            from datetime import datetime, timezone
            clean_str = str(gen_iso).replace("Z", "+00:00").replace(" ", "T")
            gen_dt = datetime.fromisoformat(clean_str)
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            diff_hours = (now_dt - gen_dt).total_seconds() / 3600.0
            return diff_hours <= max_hours
        except Exception:
            pass
    return False

def get_stale_warning_message(cached_data: dict) -> str:
    gen_str = cached_data.get("meta", {}).get("generated_at", "2 saatten önce") if cached_data else "2 saatten önce"
    return (
        f"⚠️ <b>Analiz Verileri Güncel Değil:</b>\n"
        f"Kayıtlı son analiz <b>{gen_str}</b> tarihinde oluşturulmuş (2 saatlik geçerlilik süresi doldu).\n\n"
        f"En güncel transfer trendleri, sakatlıklar ve maç verileriyle yanıt alabilmek için lütfen önce <b>/analiz</b> komutunu çalıştırın.\n\n"
        f"<i>💡 <b>/analiz</b> ve <b>/optimal</b> komutları her zaman motoru canlı tetikleyerek verileri sıfırdan hesaplar.</i>"
    )

async def generate_analysis_json(manager_id: int = DEFAULT_MANAGER_ID, horizon_gws: int = 8, output_path: Path = None):
    app_logger.info(f"Starting headless analysis for Manager {manager_id}...")

    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = data_dir / "fpl_analysis.json"
    cached_path = output_path

    # Single User Mode: Always prioritize primary fpl_analysis.json
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # Ensure SQLite database schema and tables (e.g. api_cache_meta) are initialized
    from data.database import db_manager
    db_manager.init_db()

    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)

    # Check if command or raw team data was passed via environment variable (from Telegram / GitHub Action)
    raw_team_data = os.environ.get("RAW_TEAM_DATA", "").strip()
    cmd_lower = raw_team_data.lower()

    # Exact and keyword intent matching helper
    def matches_any(text: str, keywords: list) -> bool:
        return any(k in text for k in keywords)

    # 1. HELP / YARDIM COMMAND
    if matches_any(cmd_lower, ["/yardim", "/help", "yardim", "yardım", "help", "komutlar", "komut"]):
        send_telegram_report(format_telegram_help_report())
        return {}

    # 1.1 FT / TRANSFER HAKKI AYARLAMA (/ft, /ft 2, /ft 3, ft 1, /hak 2 vb.)
    if cmd_lower.startswith("/ft") or cmd_lower.startswith("ft ") or cmd_lower == "ft" or cmd_lower.startswith("/hak") or cmd_lower.startswith("hak ") or cmd_lower == "hak":
        from ingestion.local_sync_server import load_synced_team_from_disk, save_synced_team_to_disk, rollover_free_transfers
        synced = load_synced_team_from_disk(chat_id=chat_id)
        if not synced or "team_data" not in synced:
            synced = {"manager_id": manager_id, "team_data": {"picks": [], "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}}}
        
        bootstrap = await fpl_client.get_bootstrap_static()
        current_event = next((e for e in bootstrap.events if e.is_current), None)
        next_event = next((e for e in bootstrap.events if e.is_next), None)
        active_gw = (next_event.id if next_event else (current_event.id if current_event and not current_event.finished else 1))

        # Check and apply rollover if gameweek advanced
        synced, _ = rollover_free_transfers(synced, active_gw, is_preseason=False)

        import re
        m_num = re.search(r'\b([0-5])\b', raw_team_data)
        if m_num:
            new_ft = int(m_num.group(1))
            if "transfers" not in synced["team_data"]:
                synced["team_data"]["transfers"] = {"bank": 0, "limit": new_ft, "made": 0, "last_updated_gw": active_gw}
            else:
                synced["team_data"]["transfers"]["limit"] = new_ft
                synced["team_data"]["transfers"]["made"] = 0
                synced["team_data"]["transfers"]["last_updated_gw"] = active_gw
            save_synced_team_to_disk(synced, chat_id=chat_id)
            
            ft_resp = (
                f"✅ <b>Serbest Transfer Hakkınız Güncellendi!</b>\n\n"
                f"🎯 <b>Tanımlanan Hak:</b> <b>{new_ft} FT</b> (GW{active_gw} İçin)\n\n"
                f"<i>Yeni haftaya (deadline) girildiğinde haklarınız kurallara uygun olarak otomatik +1 devredecektir (max 5 FT).</i>\n\n"
                f"<i>Strateji analizi için <b>/analiz</b> yazabilirsiniz.</i>"
            )
            send_telegram_report(ft_resp)
            return {"ft_updated": new_ft, "gw": active_gw}
        else:
            current_ft = synced.get("team_data", {}).get("transfers", {}).get("limit", 1)
            last_gw_info = synced.get("team_data", {}).get("transfers", {}).get("last_updated_gw", active_gw)
            ft_info = (
                f"ℹ️ <b>Kayıtlı Serbest Transfer Hakkınız:</b> <b>{current_ft} FT</b> (GW{last_gw_info})\n\n"
                f"Hakkınızı değiştirmek için:\n"
                f"👉 <b>/ft [sayı]</b> (Örnek: <b>/ft 2</b> veya <b>/ft 3</b>)\n\n"
                f"<i>FPL kuralları gereği her hafta +1 eklenir ve 1 ile 5 arasında serbest transfer biriktirilebilir.</i>"
            )
            send_telegram_report(ft_info)
            return {"current_ft": current_ft}

    # 2. DREAM TEAM / OPTIMAL WILDCARD SOLVER
    if matches_any(cmd_lower, ["/optimal", "/ruyatimi", "/ruya", "/rüya", "optimal", "rüya takım", "ruya takim", "wildcard", "ideal kadro", "dream team"]):
        optimal_msg = solve_optimal_squad(horizon_gws=5)
        send_telegram_report(optimal_msg)
        return {}

    # 3. SQUAD LIST COMMAND (/kadrom, /takim, /15, /oyuncular)
    if matches_any(cmd_lower, ["/kadrom", "/takim", "/15", "/oyuncular", "kadromuz", "takımım", "takimim", "kadromu göster", "kadromu goster"]):
        from ingestion.local_sync_server import load_synced_team_from_disk
        synced = load_synced_team_from_disk(chat_id=chat_id)
        if synced and "team_data" in synced and "picks" in synced["team_data"]:
            picks = synced["team_data"]["picks"]
            bootstrap = await fpl_client.get_bootstrap_static()
            el_map = {e.id: e for e in bootstrap.elements}
            
            gkps, defs, mids, fwds = [], [], [], []
            total_cost = 0.0
            for p in picks:
                el = el_map.get(p.get("element"))
                if not el:
                    continue
                team_s = TEAM_NAMES.get(el.team, "")
                price = el.now_cost / 10.0
                total_cost += price
                price_str = f"£{price:.1f}m"
                p_text = f"• <b>{el.web_name}</b> ({team_s}) ➔ <b>{price_str}</b>"
                if el.element_type == 1: gkps.append(p_text)
                elif el.element_type == 2: defs.append(p_text)
                elif el.element_type == 3: mids.append(p_text)
                elif el.element_type == 4: fwds.append(p_text)
            
            transfers = synced["team_data"].get("transfers", {})
            bank = transfers.get("bank", 0) / 10.0 if isinstance(transfers.get("bank"), (int, float)) else 0.0
            ft_limit = transfers.get("limit", 1)

            lines = [
                "📋 <b>MEVCUT 15 KİŞİLİK KADRONUZ</b>\n",
                "🧤 <b>Kaleciler (GK):</b>",
                *(gkps if gkps else ["• <i>Veri yok</i>"]),
                "",
                "🛡️ <b>Defanslar (DEF):</b>",
                *(defs if defs else ["• <i>Veri yok</i>"]),
                "",
                "⚙️ <b>Orta Sahalar (MID):</b>",
                *(mids if mids else ["• <i>Veri yok</i>"]),
                "",
                "⚡ <b>Forvetler (FWD):</b>",
                *(fwds if fwds else ["• <i>Veri yok</i>"]),
                "",
                f"💰 <b>Kadro Değeri:</b> £{total_cost:.1f}m | <b>Banka:</b> £{bank:.1f}m",
                f"🎟️ <b>Serbest Transfer:</b> {ft_limit} FT"
            ]
            squad_msg = "\n".join(lines)
            send_telegram_report(squad_msg)
            return {"squad_report": squad_msg}
        else:
            send_telegram_report("⚠️ Kayıtlı bir kadro bulunamadı. Lütfen önce <b>/kadro [15 oyuncu]</b> veya <b>/analiz</b> komutunu çalıştırın.")
            return {}

    # 4. ADOPT DREAM TEAM AS ACTIVE SQUAD
    if matches_any(cmd_lower, ["rüya takım ile değiştir", "ruya takim ile degistir", "kadromu rüya", "kadromu ruya", "kadroyu rüya", "kadroyu ruya", "kadroyu optimal", "kadromu optimal", "rüya kadroyu yaptım", "ruya kadroyu yaptim", "rüya takımı kurdum", "ruya takimi kurdum", "kadrom rüya takım", "kadrom ruya takim"]):
        from core.solver.service import FPLSolverService
        from ingestion.local_sync_server import save_synced_team_to_disk
        proj_path = get_hybrid_projection_path(horizon_gws=5)
        solver = FPLSolverService()
        results = solver.run_optimization(
            team_data={"picks": [], "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}},
            csv_file_path=proj_path,
            options_override={"preseason": True, "horizon": 5, "optimal_squad": True}
        )
        if results:
            r = results[0]
            first_w = int(r.picks["week"].min()) if not r.picks.empty else 1
            df = r.picks[r.picks["week"] == first_w]
            picks = [{"element": int(row["id"]), "position": idx, "is_captain": row.get("captain") == 1, "is_vice_captain": row.get("vicecaptain") == 1} for idx, (_, row) in enumerate(df.iterrows(), 1)]
            save_synced_team_to_disk({"manager_id": manager_id, "team_data": {"picks": picks, "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}}}, chat_id=chat_id)
            
            names = [f"<b>{row['name']}</b> ({row['team']})" for _, row in df.iterrows()]
            msg = (
                "✅ <b>Kadronuz Rüya Takım (Optimal 15) ile Başarıyla Güncellendi!</b>\n\n"
                f"📋 <b>Yeni 15 Kişilik Kadronuz:</b>\n{', '.join(names)}\n\n"
                "<i>Yeni kadronuzun strateji analizi için <b>/analiz</b> yazabilirsiniz.</i>"
            )
            send_telegram_report(msg)
            return {}

    # 4. INSTANT CACHED COMMANDS (Captain, Health, Fixtures, Prices)
    if matches_any(cmd_lower, ["/kaptan", "kaptan", "captain", "c kim", "kime verelim"]):
        if cached_path.exists():
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if not is_analysis_fresh(cached_data, 2.0):
                send_telegram_report(get_stale_warning_message(cached_data))
                return {}
            send_telegram_report(format_telegram_captain_report(cached_data))
            return cached_data
        else:
            send_telegram_report("⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.")
            return {}

    if matches_any(cmd_lower, ["/sakatlar", "/revir", "sakatlar", "revir", "sağlık", "saglik", "injury"]):
        if cached_path.exists():
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if not is_analysis_fresh(cached_data, 2.0):
                send_telegram_report(get_stale_warning_message(cached_data))
                return {}
            send_telegram_report(format_telegram_health_report(cached_data))
            return cached_data
        else:
            send_telegram_report("⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.")
            return {}

    # MATCH SCHEDULE (Live match fixtures & scores directly from FPL API)
    if matches_any(cmd_lower, ["/maclar", "/maçlar", "maclar", "maçlar", "/fikstur", "/fikstür", "fikstur", "fikstür", "/program", "program", "maç programı", "mac programi", "haftanın maçları", "haftanin maclari", "bu haftanın maçları"]):
        try:
            bootstrap = await fpl_client.get_bootstrap_static()
            current_event = next((e for e in bootstrap.events if e.is_current), None)
            next_event = next((e for e in bootstrap.events if e.is_next), None)
            
            if current_event and not current_event.finished:
                gw_val = current_event.id
            elif next_event:
                gw_val = next_event.id
            elif current_event:
                gw_val = current_event.id
            else:
                gw_val = 1
                
            raw_fixtures = await fpl_client.get_fixtures(event_id=gw_val)
            fix_list = []
            for fix in raw_fixtures:
                fix_list.append({
                    "id": fix.id, "event": fix.event,
                    "team_h": fix.team_h,
                    "team_h_name": TEAM_FULL_NAMES.get(fix.team_h, f"Takım {fix.team_h}"),
                    "team_h_short": TEAM_NAMES.get(fix.team_h, ""),
                    "team_a": fix.team_a,
                    "team_a_name": TEAM_FULL_NAMES.get(fix.team_a, f"Takım {fix.team_a}"),
                    "team_a_short": TEAM_NAMES.get(fix.team_a, ""),
                    "team_h_difficulty": fix.team_h_difficulty, "team_a_difficulty": fix.team_a_difficulty,
                    "team_h_score": fix.team_h_score, "team_a_score": fix.team_a_score,
                    "finished": fix.finished,
                    "finished_provisional": getattr(fix, "finished_provisional", False),
                    "minutes": getattr(fix, "minutes", 0),
                    "started": fix.started,
                    "kickoff_time": fix.kickoff_time.isoformat() if fix.kickoff_time else None
                })

            if current_event and gw_val == current_event.id and fix_list and all(is_fixture_finished(f) for f in fix_list) and next_event:
                gw_val = next_event.id
                raw_fixtures = await fpl_client.get_fixtures(event_id=gw_val)
                fix_list = []
                for fix in raw_fixtures:
                    fix_list.append({
                        "id": fix.id, "event": fix.event,
                        "team_h": fix.team_h,
                        "team_h_name": TEAM_FULL_NAMES.get(fix.team_h, f"Takım {fix.team_h}"),
                        "team_h_short": TEAM_NAMES.get(fix.team_h, ""),
                        "team_a": fix.team_a,
                        "team_a_name": TEAM_FULL_NAMES.get(fix.team_a, f"Takım {fix.team_a}"),
                        "team_a_short": TEAM_NAMES.get(fix.team_a, ""),
                        "team_h_difficulty": fix.team_h_difficulty, "team_a_difficulty": fix.team_a_difficulty,
                        "team_h_score": fix.team_h_score, "team_a_score": fix.team_a_score,
                        "finished": fix.finished,
                        "finished_provisional": getattr(fix, "finished_provisional", False),
                        "minutes": getattr(fix, "minutes", 0),
                        "started": fix.started,
                        "kickoff_time": fix.kickoff_time.isoformat() if fix.kickoff_time else None
                    })

            active_ev = next((e for e in bootstrap.events if e.id == gw_val), None)
            deadline_val = getattr(active_ev, "deadline_time", None) if active_ev else None
            rep = format_telegram_matches_report(fix_list, gw_val, deadline_val=deadline_val)
            send_telegram_report(rep)
            return {"matches_report": rep, "fixtures": fix_list, "fixture_gw": gw_val}
        except Exception as e:
            app_logger.error(f"Fikstür canlı çekilirken hata: {e}")
            send_telegram_report(f"❌ Canlı fikstür verileri alınamadı: {e}")
            return {}

    # FIXTURE SWING RADAR (Difficulty swing analysis)
    if matches_any(cmd_lower, ["/salincak", "/kolaymaclar", "/kolayfikstur", "/swings", "salıncak", "salincak", "kolay fikstür", "kolay fikstur"]):
        if cached_path.exists():
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if not is_analysis_fresh(cached_data, 2.0):
                send_telegram_report(get_stale_warning_message(cached_data))
                return {}
            send_telegram_report(format_telegram_fixture_report(cached_data))
            return cached_data
        else:
            send_telegram_report("⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.")
            return {}

    if matches_any(cmd_lower, ["/fiyat", "fiyat", "fiyatlar", "price", "zam", "düşüş", "artış"]):
        if cached_path.exists():
            with open(cached_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if not is_analysis_fresh(cached_data, 2.0):
                send_telegram_report(get_stale_warning_message(cached_data))
                return {}
            if cached_data.get("reports", {}).get("fiyat"):
                send_telegram_report(cached_data["reports"]["fiyat"])
                return cached_data
            elif cached_data.get("price_alerts"):
                send_telegram_report(format_telegram_price_report(cached_data))
                return cached_data
        
        send_telegram_report("⚠️ Henüz kayıtlı analiz verisi bulunamadı. Lütfen önce <b>/analiz</b> komutunu çalıştırın.")
        return {}

    # 5. SQUAD & TRANSFER MANIPULATION
    transfer_notification_text = ""
    if raw_team_data:
        try:
            from ingestion.local_sync_server import save_synced_team_to_disk, load_synced_team_from_disk
            from ingestion.fpl_client import parse_raw_text_to_team_data
            import re
            from fuzzywuzzy import fuzz
            
            # Multi & Single transfer command: e.g. "/transfer Welbeck yerine Isak, Pedro Porro yerine F. Kadioglu"
            if ("yerine" in cmd_lower or "/sat" in cmd_lower or "->" in cmd_lower or "=>" in cmd_lower or cmd_lower.startswith("/transfer") or cmd_lower.startswith("transfer")):
                synced = load_synced_team_from_disk(chat_id=chat_id)
                if synced and "team_data" in synced and "picks" in synced["team_data"]:
                    picks = synced["team_data"]["picks"]
                    bootstrap = await fpl_client.get_bootstrap_static()
                    
                    raw_clean = re.sub(r'^\s*/?transfer\s*', '', raw_team_data, flags=re.IGNORECASE).strip()
                    clauses = re.split(r'[,;\n]|\s+ve\s+|\s+and\s+', raw_clean, flags=re.IGNORECASE)
                    
                    pairs = []
                    for c in clauses:
                        c = c.strip()
                        if not c:
                            continue
                        parts = re.split(r'\byerine\b|->|=>|/sat|/al|\bfor\b', c, flags=re.IGNORECASE)
                        parts = [p.strip() for p in parts if p.strip()]
                        if len(parts) >= 2:
                            pairs.append((parts[0], parts[1]))
                    
                    if pairs:
                        applied = []
                        failed = []
                        for p_out_str, p_in_str in pairs:
                            out_p = None
                            best_out_score = 0
                            for pick in picks:
                                p_obj = next((e for e in bootstrap.elements if e.id == pick["element"]), None)
                                if p_obj:
                                    fname = getattr(p_obj, 'first_name', '')
                                    sname = getattr(p_obj, 'second_name', '')
                                    full = (fname + ' ' + sname).strip()
                                    score = max(
                                        fuzz.token_sort_ratio(p_out_str.lower(), p_obj.web_name.lower()),
                                        fuzz.token_set_ratio(p_out_str.lower(), p_obj.web_name.lower()),
                                        fuzz.token_sort_ratio(p_out_str.lower(), full.lower()),
                                        fuzz.token_set_ratio(p_out_str.lower(), full.lower())
                                    )
                                    if score > best_out_score and score >= 60:
                                        best_out_score = score
                                        out_p = p_obj

                            in_p = None
                            best_in_score = 0
                            for e in bootstrap.elements:
                                fname = getattr(e, 'first_name', '')
                                sname = getattr(e, 'second_name', '')
                                full = (fname + ' ' + sname).strip()
                                score = max(
                                    fuzz.token_sort_ratio(p_in_str.lower(), e.web_name.lower()),
                                    fuzz.token_set_ratio(p_in_str.lower(), e.web_name.lower()),
                                    fuzz.token_sort_ratio(p_in_str.lower(), full.lower()),
                                    fuzz.token_set_ratio(p_in_str.lower(), full.lower())
                                )
                                if score > best_in_score and score >= 60:
                                    best_in_score = score
                                    in_p = e

                            if out_p and in_p:
                                for pick in picks:
                                    if pick["element"] == out_p.id:
                                        pick["element"] = in_p.id
                                        break
                                applied.append((out_p, in_p))
                            else:
                                reason_parts = []
                                if not out_p: reason_parts.append(f"kadronuzda '{p_out_str}' bulunamadı")
                                if not in_p: reason_parts.append(f"FPL veritabanında '{p_in_str}' bulunamadı")
                                failed.append((p_out_str, p_in_str, ", ".join(reason_parts)))

                        if applied:
                            tr_dict = synced["team_data"].get("transfers", {})
                            cur_limit = tr_dict.get("limit", 1)
                            new_limit = max(0, cur_limit - len(applied))
                            tr_dict["limit"] = new_limit
                            tr_dict["made"] = tr_dict.get("made", 0) + len(applied)
                            synced["team_data"]["transfers"] = tr_dict
                            save_synced_team_to_disk({"manager_id": manager_id, "team_data": synced["team_data"]}, chat_id=chat_id)
                            
                            lines = []
                            if len(applied) == 1:
                                o_p, i_p = applied[0]
                                o_team = TEAM_NAMES.get(o_p.team, "")
                                i_team = TEAM_NAMES.get(i_p.team, "")
                                lines.append("🔄 <b>Transfer Başarıyla Uygulandı!</b>\n")
                                lines.append(f"🔴 <b>Çıkan:</b> {o_p.web_name} ({o_team})")
                                lines.append(f"🟢 <b>Giren:</b> {i_p.web_name} ({i_team})")
                                lines.append(f"🎟️ <b>Kalan Transfer Hakkı:</b> <b>{new_limit} FT</b>\n")
                            else:
                                lines.append(f"🔄 <b>{len(applied)} Transfer Başarıyla Uygulandı!</b>\n")
                                for idx, (o_p, i_p) in enumerate(applied, 1):
                                    o_team = TEAM_NAMES.get(o_p.team, "")
                                    i_team = TEAM_NAMES.get(i_p.team, "")
                                    lines.append(f"{idx}. 🔴 <b>Çıkan:</b> {o_p.web_name} ({o_team}) ➔ 🟢 <b>Giren:</b> {i_p.web_name} ({i_team})")
                                lines.append(f"\n🎟️ <b>Kalan Transfer Hakkı:</b> <b>{new_limit} FT</b>\n")
                            
                            if failed:
                                lines.append("⚠️ <b>Uygulanamayanlar:</b>")
                                for f_out, f_in, f_reason in failed:
                                    lines.append(f"• {f_out} ➔ {f_in} ({f_reason})")
                                lines.append("")

                            lines.append("<i>Yeni kadronuzun strateji analizi için <b>/analiz</b> yazabilirsiniz.</i>")
                            
                            transfer_notification_text = "\n".join(lines)
                            send_telegram_report(transfer_notification_text)
                            app_logger.success(f"Applied {len(applied)} transfers (chat_id: {chat_id}, remaining FT: {new_limit})")
                            return {}
                        elif failed:
                            lines = ["❌ <b>Transferler Uygulanamadı:</b>\n"]
                            for f_out, f_in, f_reason in failed:
                                lines.append(f"• {f_out} ➔ {f_in} ({f_reason})")
                            send_telegram_report("\n".join(lines))
                            return {}
            elif raw_team_data.startswith("{"):
                parsed_team = json.loads(raw_team_data)
                if isinstance(parsed_team, dict):
                    if "team_data" in parsed_team:
                        save_synced_team_to_disk(parsed_team, chat_id=chat_id)
                    elif "picks" in parsed_team:
                        save_synced_team_to_disk({"manager_id": manager_id, "team_data": parsed_team}, chat_id=chat_id)
            elif len(raw_team_data) > 5 and not matches_any(cmd_lower, ["analiz", "analyze", "solve", "taktik", "kadrom", "durum", "strateji", "rapor"]):
                app_logger.info(f"Processing squad text from Telegram (chat_id: {chat_id}): {raw_team_data[:60]}...")
                bootstrap = await fpl_client.get_bootstrap_static()
                td = parse_raw_text_to_team_data(raw_team_data, bootstrap.elements)
                if td and td.get("picks"):
                    p_count = len(td["picks"])
                    if p_count == 15:
                        save_synced_team_to_disk({"manager_id": manager_id, "team_data": td}, chat_id=chat_id)
                        app_logger.success(f"Successfully saved 15 picks from Telegram message.")
                        send_telegram_report(f"✅ <b>15 Kişilik Kadronuz Eksiksiz Kaydedildi!</b>\n\nHaftalık analizinizi almak için <b>/analiz</b> yazabilirsiniz.")
                        return {}
                    elif p_count >= 11:
                        save_synced_team_to_disk({"manager_id": manager_id, "team_data": td}, chat_id=chat_id)
                        missing = 15 - p_count
                        send_telegram_report(f"⚠️ <b>{p_count} Oyuncu Kaydedildi ({missing} Oyuncu Eksik):</b>\n\nFPL kuralları gereği tam analiz için 15 oyuncu gereklidir. Eksik kalan oyuncuları <b>/transfer</b> ile veya 15 ismi <b>/kadro</b> ile tekrar girerek tamamlayabilirsiniz.")
                        return {}
                    else:
                        send_telegram_report(f"❌ <b>Kadronuz Kaydedilemedi:</b> Yalnızca {p_count} oyuncu tespit edilebildi. Lütfen en az 11 (tercihen 15) oyuncu ismini virgülle ayırarak girin.")
                        return {}
        except Exception as e:
            app_logger.error(f"Failed to parse RAW_TEAM_DATA from environment: {e}")

    # 6. FULL ANALYSIS GATE
    is_analysis_requested = (
        not raw_team_data or 
        raw_team_data.startswith("{") or 
        matches_any(cmd_lower, ["/analiz", "analiz", "analyze", "solve", "taktik", "kadrom", "durum", "strateji", "rapor"])
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

    # Step 0: Fetch live standardized FPL Form projections
    try:
        from ingestion.fplform_client import generate_fplform_csv
        await generate_fplform_csv(horizon_gws=horizon_gws)
    except Exception as e:
        app_logger.warning(f"FPL Form projeksiyon güncellemesi atlandı: {e}")
    
    engine = StrategyEngine(fpl_client=fpl_client, risk_profile="balanced")

    bundle = await engine.analyze(manager_id=manager_id, horizon_gws=horizon_gws, chat_id=chat_id)


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
            "generated_at_epoch": int(time.time()),
            "generated_at_iso": datetime.now(timezone.utc).isoformat(),
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

    # Fetch and attach match fixtures for the active gameweek
    gw_fixtures = []
    matches_report = ""
    fix_gw = bundle.current_gw
    try:
        bootstrap = await fpl_client.get_bootstrap_static()
        current_event = next((e for e in bootstrap.events if e.is_current), None)
        next_event = next((e for e in bootstrap.events if e.is_next), None)
        
        if current_event and not current_event.finished:
            fix_gw = current_event.id
        elif next_event:
            fix_gw = next_event.id
        elif current_event:
            fix_gw = current_event.id
        else:
            fix_gw = bundle.current_gw
            
        raw_fixtures = await fpl_client.get_fixtures(event_id=fix_gw)
        if current_event and fix_gw == current_event.id and raw_fixtures and all(f.finished for f in raw_fixtures) and next_event:
            fix_gw = next_event.id
            raw_fixtures = await fpl_client.get_fixtures(event_id=fix_gw)

        for fix in raw_fixtures:
            gw_fixtures.append({
                "id": fix.id, "event": fix.event,
                "team_h": fix.team_h,
                "team_h_name": TEAM_FULL_NAMES.get(fix.team_h, f"Takım {fix.team_h}"),
                "team_h_short": TEAM_NAMES.get(fix.team_h, ""),
                "team_a": fix.team_a,
                "team_a_name": TEAM_FULL_NAMES.get(fix.team_a, f"Takım {fix.team_a}"),
                "team_a_short": TEAM_NAMES.get(fix.team_a, ""),
                "team_h_difficulty": fix.team_h_difficulty, "team_a_difficulty": fix.team_a_difficulty,
                "team_h_score": fix.team_h_score, "team_a_score": fix.team_a_score,
                "finished": fix.finished, "started": fix.started,
                "kickoff_time": fix.kickoff_time.isoformat() if fix.kickoff_time else None
            })
        matches_report = format_telegram_matches_report(gw_fixtures, fix_gw)
    except Exception as e:
        app_logger.warning(f"Fikstür maç listesi oluşturulamadı: {e}")

    payload["fixture_gw"] = fix_gw
    payload["fixtures"] = gw_fixtures
    payload["matches_report"] = matches_report

    # Format rich Telegram message
    tg_report = format_telegram_report(payload)
    payload["telegram_report"] = tg_report

    # Pre-render all instant Telegram command reports for the generic webhook router
    help_rep = format_telegram_help_report()
    cap_rep = format_telegram_captain_report(payload)
    health_rep = format_telegram_health_report(payload)
    swing_rep = format_telegram_fixture_report(payload)
    price_rep = format_telegram_price_report(payload)

    payload["reports"] = {
        "analiz": tg_report,
        "taktik": tg_report,
        "kadrom": tg_report,
        "rapor": tg_report,
        "yardim": help_rep,
        "help": help_rep,
        "komutlar": help_rep,
        "maclar": matches_report,
        "maçlar": matches_report,
        "fikstur": matches_report,
        "fikstür": matches_report,
        "program": matches_report,
        "kaptan": cap_rep,
        "captain": cap_rep,
        "sakatlar": health_rep,
        "revir": health_rep,
        "saglik": health_rep,
        "sağlık": health_rep,
        "salincak": swing_rep,
        "salıncak": swing_rep,
        "swings": swing_rep,
        "kolayfikstur": swing_rep,
        "kolayfikstür": swing_rep,
        "fiyat": price_rep,
        "price": price_rep,
        "zam": price_rep
    }

    if output_path is None:
        data_dir = BASE_DIR / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_path = data_dir / "fpl_analysis.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    app_logger.success(f"Analysis JSON successfully generated at: {output_path}")

    # Single User Mode: Primary data/fpl_analysis.json is the single source of truth

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

    ft_count = meta.get("free_transfers", 1)
    if meta.get("is_preseason", False) or (isinstance(ft_count, int) and ft_count >= 90):
        ft_display = "∞ Sınırsız (Sezon Öncesi)"
    else:
        ft_display = f"{ft_count} FT"

    lines = []
    if custom_header:
        lines.append(custom_header)
    else:
        lines.append(f"🦁 <b>FPL STRATEJİ RAPORU (GW{gw})</b>")
    lines.append(f"🎟️ <b>Mevcut Hak:</b> <b>{ft_display}</b> (Serbest Transfer)\n")

    # 1. Kaptan & 2. Kaptan
    cap = lineup.get("captain", {})
    vc = lineup.get("vice_captain", {})
    cap_name = get_pname(cap) or "Belirlenmedi"
    vc_name = get_pname(vc) or "Belirlenmedi"
    lines.append(f"👑 <b>Kaptan:</b> {cap_name}")
    lines.append(f"🥈 <b>2. Kaptan:</b> {vc_name}\n")

    # 2. Transfer Kararı
    t_ins_list = action.get("transfers_in", [])
    t_outs_list = action.get("transfers_out", [])
    gain = action.get("net_xp_gain", 0.0)

    if t_ins_list and t_outs_list:
        min_len = min(len(t_ins_list), len(t_outs_list))
        if min_len == 1:
            tin = get_pname(t_ins_list[0])
            tout = get_pname(t_outs_list[0])
            lines.append(f"🎯 <b>Transfer Kararı ({ft_display} Mevcut):</b>")
            lines.append(f"   🔴 {tout} ➔ 🟢 {tin}")
            lines.append(f"   <i>Beklenen Net Kazanç: +{gain:.2f} xPts</i>\n")
        else:
            lines.append(f"🎯 <b>Çoklu Transfer Kararı ({ft_display} Mevcut):</b>")
            for i in range(min_len):
                tin = get_pname(t_ins_list[i])
                tout = get_pname(t_outs_list[i])
                lines.append(f"   • 🔴 {tout} ➔ 🟢 {tin}")
            lines.append(f"   <i>Beklenen Net Kazanç: +{gain:.2f} xPts</i>\n")
    else:
        is_pre = meta.get("is_preseason", False) or gw == 1
        if is_pre:
            lines.append(f"🎯 <b>Transfer Kararı ({ft_display}):</b> 🛡️ Kadroyu Koru")
            lines.append("   <i>Tavsiye: 1. haftaya mevcut kadroyla başla (GW2 için 1 FT tanımlanacak).</i>\n")
        else:
            lines.append(f"🎯 <b>Transfer Kararı ({ft_display} Mevcut):</b> 🛡️ Transferi Pas Geç (Roll FT)")
            next_ft_est = min(5, ft_count + 1) if isinstance(ft_count, int) else 2
            lines.append(f"   <i>Tavsiye: Hakkını gelecek haftaya devret (GW{gw+1}'e {next_ft_est} FT ile başla).</i>\n")

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
    return "\n".join(lines)

def format_telegram_price_report(payload: dict) -> str:
    alerts = payload.get("price_alerts", [])
    lines = []
    lines.append("💰 <b>5 GÜNLÜK FİYAT DEĞİŞİM RADARI</b>")
    lines.append("<i>Önümüzdeki 5 günlük transfer trendi ve fiyat değişim olasılıkları:</i>\n")
    
    if not isinstance(alerts, list) or not alerts:
        lines.append("📊 Önümüzdeki 5 gün için piyasada kritik bir fiyat değişimi riski veya fırsatı bulunmuyor.\n")
        return "\n".join(lines)

    rises = [a for a in alerts if a.get("direction") == "rise"]
    falls = [a for a in alerts if a.get("direction") == "fall"]

    # 1. Fiyat Artışları
    lines.append("📈 <b>FİYAT ARTIŞI BEKLENENLER (+£0.1m)</b>")
    high_rises = [a for a in rises if a.get("likelihood") == "high" or a.get("probability_1d", 0) >= 0.80 or a.get("probability", 0) >= 0.85]
    med_rises = [a for a in rises if a not in high_rises and a.get("probability", 0) >= 0.45]

    if high_rises:
        lines.append("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b>")
        for a in high_rises[:5]:
            p_name = a.get("web_name") or a.get("name", "Oyuncu")
            t_id = a.get("team") or a.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            price_str = f"£{a.get('price', 0):.1f}m" if a.get('price') else ""
            prob = int(a.get("probability", 0) * 100)
            squad_flag = " 👤 <i>(Kadronuzda)</i>" if a.get("in_squad") else ""
            lines.append(f"  • <b>{p_name}{team_str}</b> - {price_str} ➔ <b>%{prob}</b>{squad_flag}")
    else:
        lines.append("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b> <i>Acil artış adayı yok</i>")

    if med_rises:
        lines.append("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b>")
        for a in med_rises[:5]:
            p_name = a.get("web_name") or a.get("name", "Oyuncu")
            t_id = a.get("team") or a.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            price_str = f"£{a.get('price', 0):.1f}m" if a.get('price') else ""
            prob = int(a.get("probability", 0) * 100)
            squad_flag = " 👤 <i>(Kadronuzda)</i>" if a.get("in_squad") else ""
            lines.append(f"  • <b>{p_name}{team_str}</b> - {price_str} ➔ <b>%{prob}</b>{squad_flag}")
    else:
        lines.append("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b> <i>Trend takibinde olan oyuncu yok</i>")
        
    lines.append("")

    # 2. Fiyat Düşüşleri
    lines.append("📉 <b>FİYAT DÜŞÜŞÜ BEKLENENLER (-£0.1m)</b>")
    high_falls = [a for a in falls if a.get("likelihood") == "high" or a.get("probability_1d", 0) >= 0.80 or a.get("probability", 0) >= 0.85]
    med_falls = [a for a in falls if a not in high_falls and a.get("probability", 0) >= 0.45]

    if high_falls:
        lines.append("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b>")
        for a in high_falls[:5]:
            p_name = a.get("web_name") or a.get("name", "Oyuncu")
            t_id = a.get("team") or a.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            price_str = f"£{a.get('price', 0):.1f}m" if a.get('price') else ""
            prob = int(a.get("probability", 0) * 100)
            squad_flag = " 👤 <i>(Kadronuzda!)</i>" if a.get("in_squad") else ""
            lines.append(f"  • <b>{p_name}{team_str}</b> - {price_str} ➔ <b>%{prob}</b>{squad_flag}")
    else:
        lines.append("🔴 <b>Yüksek İhtimal (1-2 Gün İçinde):</b> <i>Acil düşüş adayı yok</i>")

    if med_falls:
        lines.append("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b>")
        for a in med_falls[:5]:
            p_name = a.get("web_name") or a.get("name", "Oyuncu")
            t_id = a.get("team") or a.get("team_id")
            team_str = f" ({TEAM_NAMES.get(t_id)})" if t_id in TEAM_NAMES else ""
            price_str = f"£{a.get('price', 0):.1f}m" if a.get('price') else ""
            prob = int(a.get("probability", 0) * 100)
            squad_flag = " 👤 <i>(Kadronuzda!)</i>" if a.get("in_squad") else ""
            lines.append(f"  • <b>{p_name}{team_str}</b> - {price_str} ➔ <b>%{prob}</b>{squad_flag}")
    else:
        lines.append("🟡 <b>Orta İhtimal (3-5 Gün İçinde):</b> <i>Düşüş baskısında olan oyuncu yok</i>")

    lines.append("\n💡 <b>Strateji Tavsiyesi:</b>")
    lines.append("<i>Kadro değerini korumak için yüksek ihtimalli düşüş adaylarını erken elden çıkarmayı, transfer hedeflerinizi ise sakatlık riski yoksa fiyat artmadan almayı değerlendirin.</i>")
    
    return "\n".join(lines)

def format_telegram_help_report() -> str:
    lines = [
        "📖 <b>FPL AI BOT KOMUT REHBERİ</b>\n",
        "🔹 <b>/analiz</b> ➔ Kayıtlı kadronuzun haftalık tam strateji analizi (Kaptan, İdeal 11, Transfer, Çip, Sakatlıklar).",
        "🔹 <b>/kadro</b> (veya <b>/kadrom</b>) ➔ Kayıtlı 15 kişilik kadronuzu mevki mevki, anlık değer ve takımlarıyla listeler.",
        "🔹 <b>/yeni [15 Oyuncu]</b> ➔ 15 kişilik yeni kadronuzu sıfırdan kaydeder (Örn: <code>/yeni Raya, Gabriel, Saka, Haaland...</code>).",
        "🔹 <b>/ft [0-5]</b> ➔ Serbest transfer (FT) hakkınızı günceller / görüntüler.",
        "🔹 <b>/maclar</b> (veya <b>/fikstur</b>) ➔ O haftanın tüm Premier League maç takvimi, gün ve başlama saatleri (TSİ).",
        "🔹 <b>/optimal</b> ➔ £100m bütçe ile en ideal 15 kişilik Rüya Takım.",
        "🔹 <b>/kaptan</b> ➔ O haftanın en iyi 2 kaptan tercihi ve patlama indeksi.",
        "🔹 <b>/sakatlar</b> (veya <b>/revir</b>) ➔ Kadronuzdaki şüpheli/sakat oyuncuların sağlık durumu.",
        "🔹 <b>/salincak</b> ➔ Önümüzdeki 5 hafta fikstürü en çok kolaylaşan takımlar.",
        "🔹 <b>/fiyat</b> ➔ Önümüzdeki 5 gün içinde beklenen yüksek ve orta ihtimalli fiyat değişim radarı.",
        "🔹 <b>/transfer [Çıkan] yerine [Giren]</b> ➔ Kadroda oyuncu değiştirir.",
        "🔹 <b>/yardim</b> ➔ Bu komut listesini ekrana getirir."
    ]
    return "\n".join(lines)

def get_hybrid_projection_path(horizon_gws: int = 5) -> Path:
    from core.solver.paths import DATA_DIR
    fplreview_path = BASE_DIR / "data" / "fplreview.csv"
    if fplreview_path.exists() and fplreview_path.stat().st_size > 10000:
        return fplreview_path

    appdata_path = DATA_DIR / "fplreview.csv"
    if appdata_path.exists() and appdata_path.stat().st_size > 10000:
        return appdata_path

    from ingestion.fplreview_scraper import generate_hybrid_fplreview_csv
    try:
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except Exception:
            pass
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, generate_hybrid_fplreview_csv(horizon_gws=horizon_gws)).result()
        else:
            return asyncio.run(generate_hybrid_fplreview_csv(horizon_gws=horizon_gws))
    except Exception as e:
        app_logger.warning(f"Hybrid FPL Review üretilirken hata: {e}")

    from core.solver.projection_generator import generate_builtin_projections
    return generate_builtin_projections(horizon_gws=horizon_gws)

def solve_optimal_squad(horizon_gws: int = 5) -> str:
    from core.solver.service import FPLSolverService
    try:
        proj_path = get_hybrid_projection_path(horizon_gws=horizon_gws)
        solver = FPLSolverService()
        results = solver.run_optimization(
            team_data={"picks": [], "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}},
            csv_file_path=proj_path,
            options_override={"preseason": True, "horizon": horizon_gws, "optimal_squad": True}
        )
        if not results:
            return "❌ Optimal kadro çözülemedi."
        r = results[0]
        first_w = int(r.picks["week"].min()) if not r.picks.empty else 1
        df = r.picks[r.picks["week"] == first_w]
        
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
                bench_tag = " (Yedek)" if row.get("bench", -1) >= 0 else ""
                items.append(f"{star}<b>{row['name']}</b> ({row['team']} - £{row['buy_price']:.1f}m{bench_tag})")
            return ", ".join(items)
            
        lines = []
        lines.append(f"✨ <b>EN OPTİMAL 15 (RÜYA TAKIM)</b>\n")
        lines.append(f"🧤 <b>KL:</b> {fmt_group(gkps)}")
        lines.append(f"🛡️ <b>DF:</b> {fmt_group(defs)}")
        lines.append(f"⚙️ <b>OS:</b> {fmt_group(mids)}")
        lines.append(f"⚡ <b>FV:</b> {fmt_group(fwds)}\n")
        lines.append(f"💰 <b>Toplam Harcanan:</b> £{total_cost:.1f}m (Kalan Bütçe: £{100.0 - total_cost:.1f}m)")
        lines.append(f"📈 <b>11 Kişilik Beklenen Puan (GW{first_w}):</b> <b>{total_xp:.1f} xP</b>")
        lines.append(f"📊 <b>{horizon_gws} Haftalık Toplam xP:</b> <b>{r.total_xp:.1f} xP</b>\n")
        return "\n".join(lines)
    except Exception as e:
        app_logger.error(f"Optimal squad solve error: {e}")
        return f"❌ Optimal kadro hesaplanırken hata oluştu: {e}"

def send_telegram_report(report_text: str, custom_chat_id: Optional[str] = None):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or "8315284284:AAF4HjtfP1kW5rNUPRe5n1J1KBg4PsT83Jg"
    chat_id = custom_chat_id or os.environ.get("TELEGRAM_CHAT_ID") or "8827315431"
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

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    
    mgr_id = DEFAULT_MANAGER_ID
    for arg in sys.argv[1:]:
        if arg.isdigit():
            mgr_id = int(arg)
            break

    asyncio.run(generate_analysis_json(manager_id=mgr_id))
