import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from core.solver.paths import DATA_DIR
from core.solver.utils import cached_request

# FPL Scoring Rules Constants
GOAL_PTS = {1: 6, 2: 6, 3: 5, 4: 4}
ASSIST_PTS = 3
CLEAN_SHEET_PTS = {1: 4, 2: 4, 3: 1, 4: 0}
APPEARANCE_60_PTS = 2
APPEARANCE_SUB_PTS = 1

# Calibrated Premier League Baseline Elo Ratings (Fallback & Baseline)
DEFAULT_EPL_ELO: Dict[str, float] = {
    "Man City": 2040.0,
    "Arsenal": 1990.0,
    "Liverpool": 1980.0,
    "Chelsea": 1840.0,
    "Aston Villa": 1830.0,
    "Tottenham": 1810.0,
    "Spurs": 1810.0,
    "Newcastle": 1810.0,
    "Brighton": 1760.0,
    "Man Utd": 1760.0,
    "Man United": 1760.0,
    "West Ham": 1720.0,
    "Bournemouth": 1720.0,
    "Fulham": 1710.0,
    "Crystal Palace": 1700.0,
    "Brentford": 1700.0,
    "Wolves": 1690.0,
    "Everton": 1690.0,
    "Nottingham Forest": 1680.0,
    "Forest": 1680.0,
    "Leicester": 1620.0,
    "Ipswich": 1590.0,
    "Southampton": 1580.0,
}

# Average EPL Goals per Match
EPL_BASE_HOME_XG = 1.60
EPL_BASE_AWAY_XG = 1.25
HOME_ELO_ADVANTAGE = 65.0  # Equivalent to ~+65 Elo points for home advantage


def get_team_elo_map(teams: Dict[int, Dict[str, Any]]) -> Dict[int, float]:
    """Returns dynamic Elo ratings for each FPL team id."""
    elo_map: Dict[int, float] = {}

    for t_id, t_info in teams.items():
        name = t_info.get("name", "")
        short_name = t_info.get("short_name", "")
        
        matched_elo = None
        for key, elo_val in DEFAULT_EPL_ELO.items():
            if key.lower() in name.lower() or key.lower() == short_name.lower():
                matched_elo = elo_val
                break
        
        if matched_elo is None:
            strength = float(t_info.get("strength_overall_home") or 3.0)
            matched_elo = 1500.0 + (strength * 100.0)

        elo_map[t_id] = matched_elo

    return elo_map


def calculate_match_poisson_xgs(
    home_elo: float,
    away_elo: float,
) -> Tuple[float, float, float, float]:
    """
    Calculates home team xG, away team xG, home clean sheet probability,
    and away clean sheet probability using Elo difference and Poisson distribution.
    """
    delta_home = (home_elo + HOME_ELO_ADVANTAGE) - away_elo
    delta_away = away_elo - (home_elo + HOME_ELO_ADVANTAGE)

    home_mult = max(0.25, min(3.5, 10.0 ** (delta_home / 750.0)))
    away_mult = max(0.20, min(3.0, 10.0 ** (delta_away / 750.0)))

    home_xg = max(0.35, min(4.5, EPL_BASE_HOME_XG * home_mult))
    away_xg = max(0.25, min(3.8, EPL_BASE_AWAY_XG * away_mult))

    home_cs_prob = math.exp(-away_xg)
    away_cs_prob = math.exp(-home_xg)

    return home_xg, away_xg, home_cs_prob, away_cs_prob


def calculate_expected_gc_penalty(expected_gc: float) -> float:
    """Calculates expected penalty for conceding 2+ goals in FPL."""
    penalty = 0.0
    exp_neg = math.exp(-expected_gc)
    for k in range(2, 10):
        prob_k = (expected_gc ** k * exp_neg) / math.factorial(k)
        penalty -= (k // 2) * prob_k
    return penalty


def compute_team_hierarchies(elements: List[Dict[str, Any]]) -> Tuple[Dict[int, int], Dict[int, int]]:
    """
    Computes total matches played per team and identifies the primary starting goalkeeper for each team.
    Returns:
        team_max_starts: Dict[team_id -> int] (Total league matches played by the team)
        team_primary_gk: Dict[team_id -> player_id] (The primary active #1 Goalkeeper)
    """
    team_max_starts: Dict[int, int] = {}
    team_gks: Dict[int, List[Dict[str, Any]]] = {}

    for p in elements:
        t_id = p.get("team", 1)
        starts = int(p.get("starts") or 0)
        el_type = p.get("element_type", 3)

        team_max_starts[t_id] = max(team_max_starts.get(t_id, 0), starts)

        if el_type == 1:
            team_gks.setdefault(t_id, []).append(p)

    # Determine primary starter GK per team (most starts among available GKs)
    team_primary_gk: Dict[int, int] = {}
    for t_id, gks in team_gks.items():
        # Sort available GKs by starts descending, then minutes descending, then cost descending
        sorted_gks = sorted(
            gks,
            key=lambda x: (
                1 if x.get("status") == "a" else 0,
                int(x.get("starts") or 0),
                int(x.get("minutes") or 0),
                int(x.get("now_cost") or 0),
            ),
            reverse=True,
        )
        if sorted_gks:
            team_primary_gk[t_id] = sorted_gks[0]["id"]

    return team_max_starts, team_primary_gk


def generate_builtin_projections(
    horizon_gws: int = 8,
    output_filename: str = "projections.csv",
    force_refresh: bool = False,
) -> Path:
    """
    Generates high-precision multi-week xP and xMins projection CSV
    leveraging Opta underlying metrics, Team Hierarchy Minutes modeling,
    Poisson match distributions, calibrated Elo ratings, and live FPL availability data.
    """
    target_path = DATA_DIR / output_filename
    meta_path = DATA_DIR / "projection_meta.json"

    if not force_refresh and target_path.exists() and target_path.stat().st_size > 1000:
        logger.debug(f"Mevcut projeksiyon dosyası kullanılıyor: {target_path}")
        return target_path

    logger.info(f"Hiyerarşik FPL Opta & Poisson-Elo Projeksiyon Motoru çalıştırılıyor ({horizon_gws} haftalık model)...")

    # 1. Fetch live FPL bootstrap-static and fixtures
    bootstrap = cached_request("https://fantasy.premierleague.com/api/bootstrap-static/", force_refresh=force_refresh)
    fixtures = cached_request("https://fantasy.premierleague.com/api/fixtures/", force_refresh=force_refresh)

    elements = bootstrap.get("elements", [])
    teams = {t["id"]: t for t in bootstrap.get("teams", [])}
    events = bootstrap.get("events", [])

    # Determine current/next gameweek
    current_gw = 1
    for e in events:
        if e.get("is_next"):
            current_gw = e["id"]
            break
        elif e.get("is_current") and not e.get("finished"):
            current_gw = e["id"]
            break

    # Dynamic horizon buffer: ensure full coverage from GW1 through current_gw + horizon_gws + 4 (up to GW38)
    max_gw = min(38, max(current_gw + horizon_gws + 4, 12))
    target_gws = list(range(1, max_gw + 1))

    # 2. Build Team Hierarchies & Elo Map
    team_max_starts, team_primary_gk = compute_team_hierarchies(elements)
    team_elo_map = get_team_elo_map(teams)

    # 3. Build Match-Level Probabilistic Projections Map
    team_gw_matches: Dict[int, Dict[int, List[Dict[str, Any]]]] = {t_id: {} for t_id in teams}
    for f in fixtures:
        ev = f.get("event")
        if ev and ev in target_gws:
            t_h = f["team_h"]
            t_a = f["team_a"]
            fdr_h = f.get("team_h_difficulty", 3)
            fdr_a = f.get("team_a_difficulty", 3)

            elo_h = team_elo_map.get(t_h, 1700.0)
            elo_a = team_elo_map.get(t_a, 1700.0)

            home_xg, away_xg, home_cs_prob, away_cs_prob = calculate_match_poisson_xgs(elo_h, elo_a)

            opp_a_info = teams.get(t_a, {})
            opp_h_info = teams.get(t_h, {})

            if t_h in team_gw_matches:
                team_gw_matches[t_h].setdefault(ev, []).append({
                    "is_home": True,
                    "fdr": fdr_h,
                    "opponent_id": t_a,
                    "opponent_name": opp_a_info.get("name", ""),
                    "team_xg": home_xg,
                    "team_xgc": away_xg,
                    "cs_prob": home_cs_prob,
                    "gc_penalty": calculate_expected_gc_penalty(away_xg),
                })
            if t_a in team_gw_matches:
                team_gw_matches[t_a].setdefault(ev, []).append({
                    "is_home": False,
                    "fdr": fdr_a,
                    "opponent_id": t_h,
                    "opponent_name": opp_h_info.get("name", ""),
                    "team_xg": away_xg,
                    "team_xgc": home_xg,
                    "cs_prob": away_cs_prob,
                    "gc_penalty": calculate_expected_gc_penalty(home_xg),
                })

    pos_map = {1: "G", 2: "D", 3: "M", 4: "F"}
    rows: List[Dict[str, Any]] = []

    for p in elements:
        p_id = p["id"]
        name = p["web_name"]
        el_type = p["element_type"]
        pos_str = pos_map.get(el_type, "M")
        now_cost = p["now_cost"] / 10.0
        team_id = p.get("team", 1)
        team_info = teams.get(team_id, {})
        team_name = team_info.get("name", "")

        team_total_games = max(1, team_max_starts.get(team_id, 38))

        # --- A. Live Health & Availability ---
        status = p.get("status", "a")
        chance_playing = p.get("chance_of_playing_next_round")
        if status in ("u", "n"):
            chance_factor = 0.0
        elif status == "i" and (chance_playing is None or chance_playing == 0):
            chance_factor = 0.0
        elif chance_playing is None:
            chance_factor = 1.0 if status == "a" else 0.75
        else:
            chance_factor = max(0.0, min(1.0, chance_playing / 100.0))

        # --- B. Professional Hierarchical xMins Model ---
        mins_played = float(p.get("minutes") or 0.0)
        starts = float(p.get("starts") or 0.0)
        n_90s = max(0.1, mins_played / 90.0)

        if el_type == 1:
            # Goalkeeper Hierarchy: Only the primary starter gets full minutes
            is_primary_gk = (team_primary_gk.get(team_id) == p_id)
            if is_primary_gk:
                base_expected_mins = 90.0
            else:
                # Backup GK: 0 mins unless primary is injured
                base_expected_mins = 0.0
        else:
            # Outfield Players: Start rate evaluated against TEAM TOTAL MATCHES
            start_rate = starts / team_total_games
            sub_appearances = max(0.0, (mins_played / max(1.0, starts)) if starts > 0 else (mins_played / 30.0))

            if team_total_games >= 8:
                if starts > 0:
                    avg_mins_when_starting = min(90.0, max(65.0, mins_played / starts))
                else:
                    avg_mins_when_starting = 75.0

                if start_rate >= 0.75:
                    # Nailed core starter (e.g. Saka, Haaland, Saliba)
                    base_expected_mins = avg_mins_when_starting * (0.85 + (start_rate * 0.15))
                elif start_rate >= 0.40:
                    # Regular rotation starter
                    base_expected_mins = (start_rate * avg_mins_when_starting) + (0.20 * 20.0)
                elif start_rate >= 0.15:
                    # Occasional bench/fringe player
                    base_expected_mins = (start_rate * avg_mins_when_starting) + (0.35 * 15.0)
                else:
                    # Rare substitute / youth (<15% starts)
                    base_expected_mins = max(0.0, min(15.0, (mins_played / team_total_games)))
            else:
                # Early season / pre-season heuristics by cost and starts
                if starts > 0:
                    base_expected_mins = min(90.0, max(60.0, mins_played / starts))
                else:
                    base_expected_mins = 85.0 if now_cost >= 7.0 else (60.0 if now_cost >= 5.0 else 10.0)

        # Hard ceiling for low-cost bench fodder with zero recent activity
        if starts == 0 and mins_played < 90 and now_cost <= 4.5 and el_type != 1:
            base_expected_mins = min(base_expected_mins, 8.0)

        # --- C. Underlying Attack Metrics (Opta xG / xA per 90) ---
        raw_xg = float(p.get("expected_goals") or 0.0)
        raw_xa = float(p.get("expected_assists") or 0.0)

        xg_per90 = raw_xg / n_90s if raw_xg > 0 else 0.0
        xa_per90 = raw_xa / n_90s if raw_xa > 0 else 0.0

        # Prior distribution blending for low sample size
        if n_90s < 4.0:
            default_xg = 0.35 if pos_str == "F" else (0.16 if pos_str == "M" else 0.03)
            default_xa = 0.20 if pos_str in ("M", "F") else 0.06
            blend_w = n_90s / 4.0
            xg_per90 = (xg_per90 * blend_w) + (default_xg * (1.0 - blend_w))
            xa_per90 = (xa_per90 * blend_w) + (default_xa * (1.0 - blend_w))

        # --- D. Set-Piece & Penalty Boosts ---
        is_penalty_taker = p.get("penalties_order") == 1
        is_freekick_taker = p.get("direct_freekicks_order") == 1
        is_corner_taker = p.get("corners_and_indirect_freekicks_order") in (1, 2)

        pen_boost_xp = 0.80 if is_penalty_taker else 0.0
        fk_boost_xp = 0.20 if is_freekick_taker else 0.0
        corner_boost_xa = 0.14 if is_corner_taker else 0.0
        xa_per90 += corner_boost_xa

        # --- E. BPS and Goalkeeper Saves ---
        raw_bps = float(p.get("bps") or 0.0)
        bps_per90 = raw_bps / n_90s if raw_bps > 0 else 12.0
        bonus_per90 = max(0.0, min(1.3, (bps_per90 - 10.0) * 0.055))
        saves_per90 = (float(p.get("saves") or 0.0) / n_90s) if el_type == 1 else 0.0

        row: Dict[str, Any] = {
            "ID": p_id,
            "Name": name,
            "Pos": pos_str,
            "Value": now_cost,
            "Team": team_name,
        }

        # --- F. Calculate Projections for each Horizon Gameweek ---
        for i_gw, gw in enumerate(target_gws):
            gw_matches = team_gw_matches.get(team_id, {}).get(gw, [])

            if not gw_matches:
                row[f"{gw}_Pts"] = 0.0
                row[f"{gw}_xMins"] = 0
                continue

            gw_pts_total = 0.0
            gw_mins_total = 0

            # Progressive recovery for future gameweek availability
            if status in ("u", "n"):
                gw_avail = 0.0
            elif i_gw == 0:
                gw_avail = chance_factor
            else:
                gw_avail = min(1.0, chance_factor + (i_gw * 0.25)) if chance_factor > 0 else 0.0

            for match in gw_matches:
                team_xg = match["team_xg"]
                team_xgc = match["team_xgc"]
                cs_prob = match["cs_prob"]
                gc_penalty = match["gc_penalty"]

                match_mins = int(base_expected_mins * gw_avail)
                min_ratio = match_mins / 90.0

                if match_mins <= 0:
                    continue

                # 1. Base Appearance Points
                appearance_pts = APPEARANCE_60_PTS if match_mins >= 60 else (APPEARANCE_SUB_PTS if match_mins >= 15 else 0.0)

                # 2. Attack Points using Poisson Player Expectancy
                team_xg_scale = team_xg / 1.40
                player_match_xg = xg_per90 * team_xg_scale * min_ratio
                player_match_xa = xa_per90 * team_xg_scale * min_ratio

                attack_pts = (
                    (player_match_xg * GOAL_PTS.get(el_type, 4))
                    + (player_match_xa * ASSIST_PTS)
                    + (pen_boost_xp * min_ratio)
                    + (fk_boost_xp * min_ratio)
                )

                # 3. Clean Sheet & Defensive Points (Poisson distribution)
                clean_sheet_pts = (cs_prob * CLEAN_SHEET_PTS.get(el_type, 0)) if match_mins >= 60 else 0.0
                def_penalty_pts = gc_penalty if el_type in (1, 2) and match_mins >= 60 else 0.0

                # 4. Saves & Bonus Points
                save_pts = (saves_per90 / 3.0) * min_ratio if el_type == 1 else 0.0
                bonus_pts = bonus_per90 * min_ratio

                match_total_xp = appearance_pts + attack_pts + clean_sheet_pts + def_penalty_pts + save_pts + bonus_pts
                match_total_xp = max(0.5, match_total_xp) if match_mins >= 45 else max(0.0, match_total_xp)

                gw_pts_total += match_total_xp
                gw_mins_total = max(gw_mins_total, match_mins)

            row[f"{gw}_Pts"] = round(min(18.0, gw_pts_total), 2)
            row[f"{gw}_xMins"] = int(gw_mins_total)

        rows.append(row)

    df = pd.DataFrame(rows)
    df.sort_values(by=["Value", "ID"], ascending=[False, True], inplace=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(target_path, index=False, encoding="utf-8")

    meta = {
        "is_valid": True,
        "filename": output_filename,
        "original_name": "Hiyerarşik Opta & Poisson-Elo Canlı Motoru",
        "file_path": str(target_path),
        "player_count": len(df),
        "gameweeks": target_gws,
        "gw_range_str": f"GW{min(target_gws)} - GW{max(target_gws)}" if target_gws else "Bilinmiyor",
        "updated_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "size_kb": round(target_path.stat().st_size / 1024, 1),
        "source_type": "built_in_hierarchical_poisson_elo",
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.success(f"Hiyerarşik Opta & Poisson-Elo projeksiyonları başarıyla üretildi ({len(df)} oyuncu, GW{min(target_gws)}-GW{max(target_gws)}): {target_path}")
    return target_path
