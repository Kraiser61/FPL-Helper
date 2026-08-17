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
POS_COLORS = {1: "#f59e0b", 2: "#3b82f6", 3: "#10b981", 4: "#8b5cf6"}
TEAM_NAMES = {
    1: "ARS", 2: "AVL", 3: "BOU", 4: "BRE", 5: "BHA",
    6: "CHE", 7: "CRY", 8: "EVE", 9: "FUL", 10: "IPS",
    11: "LEI", 12: "LIV", 13: "MCI", 14: "MUN", 15: "NEW",
    16: "NFO", 17: "SOU", 18: "TOT", 19: "WHU", 20: "WOL"
}

HTML_BASE_CSS = """
<style>
  :root { color-scheme: dark; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
    background: #0f172a;
    color: #f8fafc;
    margin: 0;
    padding: 12px;
    font-size: 14px;
    line-height: 1.4;
  }
  .card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #334155;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }
  .title {
    font-size: 16px;
    font-weight: 700;
    color: #38bdf8;
  }
  .badge {
    background: #334155;
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
    display: inline-block;
  }
  .badge-green { background: #064e3b; color: #34d399; border: 1px solid #059669; }
  .badge-red { background: #7f1d1d; color: #f87171; border: 1px solid #dc2626; }
  .badge-gold { background: #78350f; color: #fbbf24; border: 1px solid #d97706; }
  .badge-blue { background: #1e3a8a; color: #60a5fa; border: 1px solid #2563eb; }
  .badge-purple { background: #581c87; color: #c084fc; border: 1px solid #9333ea; }
  
  .transfer-box {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 12px 0;
  }
  .player-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #0f172a;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #334155;
  }
  .player-info {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .player-name {
    font-weight: 600;
    font-size: 14px;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 12px 0;
  }
  .stat-card {
    background: #0f172a;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid #334155;
    text-align: center;
  }
  .stat-val {
    font-size: 16px;
    font-weight: 700;
    color: #38bdf8;
  }
  .stat-lbl {
    font-size: 11px;
    color: #94a3b8;
  }
  .reason-list {
    margin: 8px 0 0 0;
    padding-left: 18px;
    color: #cbd5e1;
    font-size: 13px;
  }
  .reason-list li { margin-bottom: 6px; }
  .pos-tag {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    color: #fff;
  }
  .timeline-step {
    border-left: 2px solid #38bdf8;
    padding-left: 12px;
    margin-bottom: 12px;
    position: relative;
  }
  .timeline-gw {
    font-weight: 700;
    color: #38bdf8;
    font-size: 13px;
  }
</style>
"""

def p_pos(p: PlayerAnalysis) -> str:
    return POS_NAMES.get(p.element_type, "MID") if p else "MID"

def p_team(p: PlayerAnalysis) -> str:
    return TEAM_NAMES.get(p.team_id, "FPL") if p else "FPL"

def p_color(p: PlayerAnalysis) -> str:
    return POS_COLORS.get(p.element_type, "#3b82f6") if p else "#3b82f6"

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

def format_html_transfer(bundle: DecisionBundle) -> str:
    action = bundle.primary_action
    action_type = action.get("type", "roll_ft")

    content = []
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">🎯 HAFTALIK TRANSFER HAMLESİ</span>
        <span class="badge badge-blue">GW{bundle.current_gw}</span>
      </div>
      <div style="display: flex; gap: 8px; margin-bottom: 12px;">
        <span class="badge">💰 Bütçe: £{bundle.bank_amount:.1f}m</span>
        <span class="badge">{bundle.available_transfers_str}</span>
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

        content.append(f"""
        <div class="transfer-box">
          <div class="player-row" style="border-left: 3px solid #ef4444;">
            <div class="player-info">
              <span class="badge badge-red">❌ ÇIK</span>
              <span class="player-name">{out_name}</span>
              <span class="pos-tag" style="background:{POS_COLORS.get(getattr(p_out, 'element_type', 3), '#3b82f6')};">{out_pos}</span>
            </div>
            <span class="badge">{out_team} • £{out_cost:.1f}m</span>
          </div>

          <div style="text-align: center; color: #38bdf8; font-size: 16px; font-weight: bold;">⬇️</div>

          <div class="player-row" style="border-left: 3px solid #10b981;">
            <div class="player-info">
              <span class="badge badge-green">✅ AL</span>
              <span class="player-name">{in_name}</span>
              <span class="pos-tag" style="background:{POS_COLORS.get(getattr(p_in, 'element_type', 3), '#10b981')};">{in_pos}</span>
            </div>
            <span class="badge">{in_team} • £{in_cost:.1f}m</span>
          </div>
        </div>

        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-val" style="color: #34d399;">+{action.get('net_xp_gain', 0.0):.1f} xP</div>
            <div class="stat-lbl">Net Beklenti Artışı</div>
          </div>
          <div class="stat-card">
            <div class="stat-val">£{action.get('budget_remaining', 0.0):.1f}m</div>
            <div class="stat-lbl">Kalan Banka Bütçesi</div>
          </div>
        </div>

        <div style="font-weight: 600; color: #94a3b8; font-size: 12px; margin-top: 10px;">💡 STRATEJİK GEREKÇE:</div>
        <ul class="reason-list">
        """)
        for r in action.get("reasons", []):
            clean_r = r.replace("<b>", "<strong style='color:#f8fafc;'>").replace("</b>", "</strong>")
            content.append(f"<li>{clean_r}</li>")
        content.append("</ul>")
    else:
        content.append(f"""
        <div class="player-row" style="border-left: 3px solid #38bdf8; margin: 12px 0;">
          <div class="player-info">
            <span class="badge badge-blue">🛡️ STRATEJİ</span>
            <span class="player-name">Transfer Yapma (Roll FT)</span>
          </div>
        </div>
        <div style="font-weight: 600; color: #94a3b8; font-size: 12px; margin-top: 10px;">💡 STRATEJİK GEREKÇE:</div>
        <ul class="reason-list">
          <li>Mevcut ilk 11'inizin puan potansiyeli bu hafta için yeterince dengeli.</li>
          <li>Acil transfer gerektiren kritik bir sakatlık veya değer kaybı bulunmuyor.</li>
          <li>Transfer hakkını saklayarak gelecek haftaya <strong>2 FT esnekliğiyle</strong> girmek daha yüksek matematiksel getiri sunuyor.</li>
        </ul>
        """)

    content.append("</div>")
    return HTML_BASE_CSS + "".join(content)

def format_html_lineup(bundle: DecisionBundle) -> str:
    lineup = bundle.lineup_summary
    cap = lineup.get("captain")
    vcap = lineup.get("vice_captain")
    starters = lineup.get("starters", [])
    bench = lineup.get("bench", [])

    content = []
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">👑 KAPTAN SEÇİMLERİ</span>
        <span class="badge badge-gold">GW{bundle.current_gw}</span>
      </div>
    """)

    if cap:
        c_name = cap.web_name if hasattr(cap, "web_name") else cap.get("name", "N/A")
        c_xp = cap.xp_next_gw if hasattr(cap, "xp_next_gw") else cap.get("xp_next_gw", 0.0)
        c_team = p_team(cap) if hasattr(cap, "team_id") else ""
        c_own = cap.ownership if hasattr(cap, "ownership") else 0.0
        content.append(f"""
        <div class="player-row" style="border-left: 3px solid #f59e0b; margin-bottom: 8px;">
          <div class="player-info">
            <span class="badge badge-gold">👑 (C)</span>
            <span class="player-name">{c_name}</span>
            <span class="badge">{c_team}</span>
          </div>
          <div style="text-align: right;">
            <span class="badge badge-gold">{c_xp * 2:.1f} xP</span>
            <span style="font-size: 11px; color: #94a3b8; display: block;">%{c_own:.1f} Sahip</span>
          </div>
        </div>
        """)

    if vcap:
        vc_name = vcap.web_name if hasattr(vcap, "web_name") else vcap.get("name", "N/A")
        vc_xp = vcap.xp_next_gw if hasattr(vcap, "xp_next_gw") else vcap.get("xp_next_gw", 0.0)
        vc_team = p_team(vcap) if hasattr(vcap, "team_id") else ""
        content.append(f"""
        <div class="player-row" style="border-left: 3px solid #94a3b8;">
          <div class="player-info">
            <span class="badge">🥈 (VC)</span>
            <span class="player-name">{vc_name}</span>
            <span class="badge">{vc_team}</span>
          </div>
          <span class="badge">{vc_xp:.1f} xP</span>
        </div>
        """)

    content.append("</div>")

    # Starters Card
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">📋 İLK 11 KADROSU</span>
        <span class="badge badge-blue">Diziliş: {lineup.get('formation', '3-5-2')}</span>
      </div>
    """)

    gkps = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 1]
    defs = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 2]
    mids = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 3]
    fwds = [p for p in starters if (p.element_type if hasattr(p, "element_type") else p.get("element_type")) == 4]

    def _render_group(p_list, title, emoji, color):
        content.append(f"<div style='font-weight:700; color:{color}; font-size:12px; margin:10px 0 6px 0;'>{emoji} {title}</div>")
        for p in p_list:
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            p_is_cap = " (C)" if cap and getattr(cap, 'player_id', None) == getattr(p, 'player_id', None) else ""
            content.append(f"""
            <div class="player-row" style="padding: 6px 10px; margin-bottom: 4px;">
              <div class="player-info">
                <span class="player-name">{p_name}{p_is_cap}</span>
                <span class="badge" style="font-size:10px; padding:2px 5px;">{p_tm}</span>
              </div>
              <span class="badge badge-blue">{p_x:.1f} xP</span>
            </div>
            """)

    _render_group(gkps, "KALECİ", "🧤", "#f59e0b")
    _render_group(defs, "DEFANS", "🛡️", "#3b82f6")
    _render_group(mids, "ORTA SAHA", "⚙️", "#10b981")
    _render_group(fwds, "FORVET", "⚡", "#8b5cf6")

    if bench:
        content.append("<div style='font-weight:700; color:#94a3b8; font-size:12px; margin:14px 0 6px 0;'>🪑 YEDEK KULÜBESİ</div>")
        for idx, p in enumerate(bench):
            p_name = p.web_name if hasattr(p, "web_name") else p.get("name", "")
            p_tm = p_team(p) if hasattr(p, "team_id") else p.get("team", "")
            p_x = p.xp_next_gw if hasattr(p, "xp_next_gw") else p.get("xp_next_gw", 0.0)
            content.append(f"""
            <div class="player-row" style="padding: 5px 10px; margin-bottom: 4px; background:#0b1120;">
              <div class="player-info">
                <span style="color:#64748b; font-size:11px; font-weight:700;">{idx+1}.</span>
                <span class="player-name" style="color:#cbd5e1;">{p_name}</span>
                <span class="badge" style="font-size:10px;">{p_tm}</span>
              </div>
              <span class="badge">{p_x:.1f} xP</span>
            </div>
            """)

    content.append("</div>")
    return HTML_BASE_CSS + "".join(content)

def format_html_golden_path(bundle: DecisionBundle) -> str:
    content = []
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">🛣️ STRATEJİK YOL HARİTASI</span>
        <span class="badge badge-purple">Golden Path</span>
      </div>
    """)

    for step in bundle.golden_path[:6]:
        gw_num = step.get("gw")
        act = step.get("action", "")
        target = step.get("target", "")
        content.append(f"""
        <div class="timeline-step">
          <div class="timeline-gw">Gameweek {gw_num}</div>
          <div style="font-weight: 600; font-size: 13px; color: #f8fafc; margin: 2px 0;">{act}</div>
          <div style="font-size: 11px; color: #94a3b8;">{target}</div>
        </div>
        """)

    content.append("</div>")
    return HTML_BASE_CSS + "".join(content)

def format_html_chips(bundle: DecisionBundle) -> str:
    content = []
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">🃏 ÇİP VE ZAMANLAMA</span>
        <span class="badge badge-gold">Strateji</span>
      </div>

      <div style="margin-bottom: 12px;">
        <span class="badge badge-purple">📌 {bundle.chips_status_str}</span>
      </div>

      <div style="background:#0f172a; padding:10px 12px; border-radius:10px; border:1px solid #334155; margin-bottom:10px;">
        <div style="font-weight:700; color:#fbbf24; font-size:12px; margin-bottom:4px;">🎯 ÇİP KULLANIM TAVSİYESİ:</div>
        <div style="font-size:13px; color:#e2e8f0;">{bundle.chip_advice}</div>
      </div>

      <div style="background:#0f172a; padding:10px 12px; border-radius:10px; border:1px solid #334155;">
        <div style="font-weight:700; color:#38bdf8; font-size:12px; margin-bottom:4px;">⏱️ TRANSFER ZAMANLAMA KURALI:</div>
        <div style="font-size:13px; color:#e2e8f0;">{bundle.timing_advice}</div>
      </div>
    </div>
    """)
    return HTML_BASE_CSS + "".join(content)

def format_html_health_radar(bundle: DecisionBundle) -> str:
    content = []
    content.append(f"""
    <div class="card">
      <div class="header">
        <span class="title">🏥 KADRO SAĞLIK & FİYAT</span>
        <span class="badge badge-red">Radar</span>
      </div>
    """)

    if bundle.squad_health_issues:
        content.append("<div style='font-weight:700; color:#f87171; font-size:12px; margin-bottom:6px;'>⚠️ SAKATLIK / ŞÜPHE TAKİBİ</div>")
        for h in bundle.squad_health_issues:
            content.append(f"""
            <div class="player-row" style="margin-bottom: 6px; border-left:3px solid #ef4444;">
              <div class="player-info">
                <span class="player-name">{h.get('web_name')}</span>
                <span class="badge badge-red">%{h.get('chance', 0)}</span>
              </div>
              <span style="font-size:11px; color:#94a3b8;">{h.get('news', 'Belirsiz')}</span>
            </div>
            """)
    else:
        content.append("""
        <div class="player-row" style="border-left:3px solid #10b981; margin-bottom:12px;">
          <span style="color:#34d399; font-weight:600;">✅ Kadroda kritik bir sakatlık bulunmuyor (15/15 Sağlam).</span>
        </div>
        """)

    if bundle.price_alerts:
        content.append("<div style='font-weight:700; color:#38bdf8; font-size:12px; margin:12px 0 6px 0;'>📈 FİYAT DEĞİŞİM BEKLENTİLERİ</div>")
        for a in bundle.price_alerts[:4]:
            is_rise = a.get("direction") == "rise"
            badge_cls = "badge-green" if is_rise else "badge-red"
            icon = "🔺 Artış" if is_rise else "🔻 Düşüş"
            content.append(f"""
            <div class="player-row" style="margin-bottom: 4px;">
              <span class="player-name">{a.get('web_name')}</span>
              <span class="badge {badge_cls}">{icon} (%{int(a.get('probability', 0)*100)})</span>
            </div>
            """)

    content.append("</div>")
    return HTML_BASE_CSS + "".join(content)

async def generate_analysis_json(manager_id: int = DEFAULT_MANAGER_ID, horizon_gws: int = 8, output_path: Path = None):
    app_logger.info(f"Starting headless analysis for Manager {manager_id}...")
    
    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)
    engine = StrategyEngine(fpl_client=fpl_client, risk_profile="balanced")

    bundle = await engine.analyze(manager_id=manager_id, horizon_gws=horizon_gws)

    # Generate both HTML and Text cards
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
