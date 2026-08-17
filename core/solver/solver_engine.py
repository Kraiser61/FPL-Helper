from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import highspy
import numpy as np
import pandas as pd
from loguru import logger

from core.solver.data_parser import read_data
from core.solver.utils import cached_request, get_random_id

BINARY_THRESHOLD = 0.5
BASE_URL = "https://fantasy.premierleague.com/api"
SQUAD_SIZE = 15
LINEUP_SIZE = 11
MAX_GAMEWEEK = 38
MAX_PLAYERS_PER_TEAM = 3

BIN = highspy.HighsVarType.kInteger
INT = highspy.HighsVarType.kInteger
CONT = highspy.HighsVarType.kContinuous


@dataclass
class SolverResult:
    iter: int
    picks: pd.DataFrame
    total_xp: float
    summary: str
    statistics: Dict[int, Dict[str, Any]]
    buy: str
    sell: str
    chip: str
    score: float
    decay_metrics: Dict[float, float] = field(default_factory=dict)


def generate_team_json(team_id: int, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Generates team structure using FPL public API for the specified team_id."""
    static_url = f"{BASE_URL}/bootstrap-static/"
    static = cached_request(static_url)
    element_to_type_dict = {x["id"]: x["element_type"] for x in static["elements"]}
    next_gw = next(x for x in static["events"] if x.get("is_next", False))["id"]

    start_prices = {x["id"]: x["now_cost"] - x.get("cost_change_start", 0) for x in static["elements"]}

    transfers_url = f"{BASE_URL}/entry/{team_id}/transfers/"
    transfers_raw = cached_request(transfers_url)
    transfers = transfers_raw[::-1] if isinstance(transfers_raw, list) else []

    history_url = f"{BASE_URL}/entry/{team_id}/history/"
    history = cached_request(history_url)
    chips = history.get("chips", [])
    fh_gws = [x["event"] for x in chips if x.get("name") == "freehit"]
    wc_gws = [x["event"] for x in chips if x.get("name") == "wildcard"]

    current_history = history.get("current", [])
    first_gw = current_history[0]["event"] if current_history else 1
    first_gw_url = f"{BASE_URL}/entry/{team_id}/event/{first_gw}/picks/"
    first_gw_data = cached_request(first_gw_url)

    squad = {x["element"]: start_prices.get(x["element"], 50) for x in first_gw_data.get("picks", [])}
    itb = 1000 - sum(squad.values())

    for t in transfers:
        if t["event"] in fh_gws:
            continue
        itb += t.get("element_out_cost", 0)
        itb -= t.get("element_in_cost", 0)
        if t.get("element_in"):
            squad[t["element_in"]] = t.get("element_in_cost", 0)
        if t.get("element_out") and t["element_out"] in squad:
            del squad[t["element_out"]]

    fts = calculate_fts(transfers, first_gw, next_gw, fh_gws, wc_gws)
    my_data: Dict[str, Any] = {
        "chips": chips,
        "picks": [],
        "team_id": team_id,
        "transfers": {"bank": itb, "limit": fts, "made": 0},
    }

    for player_id, purchase_price in squad.items():
        element = next((x for x in static["elements"] if x["id"] == player_id), None)
        now_cost = element["now_cost"] if element else purchase_price

        diff = now_cost - purchase_price
        selling_price = purchase_price + (diff // 2) if diff > 0 else now_cost

        my_data["picks"].append({
            "element": player_id,
            "purchase_price": purchase_price,
            "selling_price": selling_price,
            "element_type": element_to_type_dict.get(player_id, 3),
        })

    return my_data


def calculate_fts(transfers: List[Dict[str, Any]], first_gw: int, next_gw: int, fh_gws: List[int], wc_gws: List[int]) -> int:
    """Calculates current free transfers according to 2024/25+ rules (1-5 FT limit, non-loss on chips)."""
    n_transfers = dict.fromkeys(range(2, next_gw + 1), 0)
    for t in transfers:
        ev = t.get("event")
        if ev and ev in n_transfers:
            n_transfers[ev] += 1

    fts = dict.fromkeys(range(first_gw + 1, next_gw + 2), 0)
    fts[first_gw + 1] = 1
    for i in range(first_gw + 2, next_gw + 1):
        if (i - 1) in fh_gws or (i - 1) in wc_gws:
            fts[i] = fts[i - 1]
            continue
        fts[i] = fts[i - 1]
        fts[i] -= n_transfers.get(i - 1, 0)
        fts[i] = max(fts[i], 0)
        fts[i] += 1
        fts[i] = min(fts[i], 5)

    return fts.get(next_gw, 1)


def prep_data(my_data: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    """Prepares and validates the data model for the HiGHS solver."""
    fpl_data = cached_request("https://fantasy.premierleague.com/api/bootstrap-static/")
    valid_ids = [x["id"] for x in fpl_data["elements"]]

    for pid, change in options.get("price_changes", []):
        if pid in valid_ids:
            player = next(x for x in fpl_data["elements"] if x["id"] == pid)
            player["now_cost"] += change

    if options.get("override_next_gw"):
        gw = int(options["override_next_gw"])
    else:
        gw = 1
        for e in fpl_data.get("events", []):
            if e.get("is_next", False):
                gw = e["id"]
                break

    horizon = int(options.get("horizon", 8))

    element_data = pd.DataFrame(fpl_data["elements"])
    team_data = pd.DataFrame(fpl_data["teams"])
    elements_team = pd.merge(element_data, team_data, left_on="team", right_on="id")

    element_to_team = {x["id"]: x["team"] for x in fpl_data["elements"]}
    picks_elements = [x["element"] for x in my_data.get("picks", [])]
    max_players_from_team = (
        Counter([element_to_team[x] for x in picks_elements if x in element_to_team]).most_common(1)[0][1]
        if picks_elements
        else 3
    )

    data = read_data(options)
    if "Pos" in data.columns:
        data["Pos"] = data["Pos"].replace({"GKP": "G", "GK": "G", "DEF": "D", "MID": "M", "FWD": "F"})

    merged_data = pd.merge(elements_team, data, left_on="id_x", right_on="ID")
    merged_data.set_index(["id_x"], inplace=True)
    merged_data = merged_data.drop_duplicates(subset=["ID"], keep="first")

    # Verify prediction data coverage
    for week in range(gw, min(39, gw + horizon)):
        if f"{week}_Pts" not in data.columns:
            raise ValueError(
                f"{week}_Pts projeksiyon verisi bulunamadı. Lütfen projeksiyon dosyanızı güncelleyin veya horizon ayarını küçültün."
            )

    original_keys = merged_data.columns.to_list()
    keys = [k for k in original_keys if "_Pts" in k]
    min_keys = [k for k in original_keys if "_xMins" in k]

    totals = pd.DataFrame(
        {
            "total_ev": merged_data[keys].sum(axis=1),
            "total_min": merged_data[min_keys].sum(axis=1) if min_keys else 90 * len(keys),
        },
        index=merged_data.index,
    )
    merged_data = pd.concat([merged_data, totals], axis=1)
    merged_data.sort_values(by=["total_ev"], ascending=False, inplace=True)

    locked_next_gw = [int(i[0]) if isinstance(i, list) else int(i) for i in options.get("locked_next_gw", [])]
    safe_players_due_price: List[int] = []
    for pos, vals in options.get("pick_prices", {}).items():
        if vals:
            price_vals = [float(i) for i in str(vals).split(",") if i.strip()]
            pp = merged_data[(merged_data["Pos"] == pos) & (merged_data["now_cost"].div(10).isin(price_vals))]["ID"].to_list()
            safe_players_due_price += pp

    keep_pct = float(options.get("keep_top_ev_percent", 5))
    cutoff = merged_data["total_ev"].quantile((100 - keep_pct) / 100)
    safe_players_due_ev = merged_data[(merged_data["total_ev"] > cutoff)]["ID"].tolist()

    initial_squad = [int(i["element"]) for i in my_data.get("picks", [])]
    safe_players = (
        initial_squad
        + options.get("locked", [])
        + options.get("keep", [])
        + locked_next_gw
        + safe_players_due_price
        + safe_players_due_ev
    )

    for bt in options.get("booked_transfers", []):
        if bt.get("transfer_in"):
            safe_players.append(int(bt["transfer_in"]))
        if bt.get("transfer_out"):
            safe_players.append(int(bt["transfer_out"]))

    # Filter player pool for high performance
    xmin_lb = options.get("xmin_lb", 300)
    merged_data = merged_data[(merged_data["total_min"] >= xmin_lb) | (merged_data["ID"].isin(safe_players))].copy()

    ev_per_price_cutoff = options.get("ev_per_price_cutoff", 30)
    if ev_per_price_cutoff > 0:
        ev_per_price = merged_data["total_ev"].div(merged_data["now_cost"])
        ev_cutoff = ev_per_price.quantile(ev_per_price_cutoff / 100)
        merged_data = merged_data[(ev_per_price > ev_cutoff) | (merged_data["ID"].isin(safe_players))].copy()

    if options.get("randomized", False):
        rng = np.random.default_rng(seed=options.get("randomization_seed"))
        gws = list(range(gw, min(39, gw + horizon)))
        for w in gws:
            noise = merged_data[f"{w}_Pts"] * (92 - merged_data.get(f"{w}_xMins", 90)) / 134 * rng.standard_normal(size=len(merged_data))
            merged_data[f"{w}_Pts"] = merged_data[f"{w}_Pts"] + noise * options.get("randomization_strength", 1.0)

    type_data = pd.DataFrame(fpl_data["element_types"]).set_index(["id"])

    buy_price = merged_data["now_cost"].div(10).to_dict()
    sell_price = {i["element"]: i["selling_price"] / 10 for i in my_data.get("picks", [])}
    price_modified_players: List[int] = []

    preseason = options.get("preseason", False)
    if not preseason:
        for i in my_data.get("picks", []):
            el_id = i["element"]
            if el_id in buy_price and el_id in sell_price:
                if buy_price[el_id] != sell_price[el_id]:
                    price_modified_players.append(el_id)

    transfers_info = my_data.get("transfers", {})
    itb = transfers_info.get("bank", 0) / 10
    limit = transfers_info.get("limit")
    made = transfers_info.get("made", 0)

    if limit is None:
        ft = 1
        ft_base = 1
    else:
        ft = max(limit - made, 0)
        ft_base = limit

    for c in my_data.get("chips", []):
        c_name = c.get("name") if isinstance(c, dict) else getattr(c, "name", "")
        c_status = c.get("status_for_entry") if isinstance(c, dict) else getattr(c, "status_for_entry", "")
        if c_name == "wildcard" and c_status == "active":
            options["use_wc"] = [gw]
            if options.get("chip_limits", {}).get("wc", 0) == 0:
                options["chip_limits"]["wc"] = 1
            break

    team_code_dict = team_data.set_index("id")["name"].to_dict()
    fixture_data = cached_request("https://fantasy.premierleague.com/api/fixtures/")
    fixtures = [
        {"gw": f["event"], "home": team_code_dict.get(f["team_h"], ""), "away": team_code_dict.get(f["team_a"], "")}
        for f in fixture_data
        if f.get("event") is not None
    ]

    return {
        "merged_data": merged_data,
        "team_data": team_data,
        "my_data": my_data,
        "type_data": type_data,
        "next_gw": gw,
        "initial_squad": initial_squad,
        "sell_price": sell_price,
        "buy_price": buy_price,
        "price_modified_players": price_modified_players,
        "itb": itb,
        "ft": ft,
        "ft_base": ft_base,
        "fixtures": fixtures,
        "max_players_from_team": max_players_from_team,
    }


def solve_multi_period_fpl(data: Dict[str, Any], options: Dict[str, Any]) -> List[SolverResult]:
    """
    Builds and solves the multi-period MIP model using HiGHS.
    Returns a list of structured SolverResult dataclasses.
    """
    horizon = int(options.get("horizon", 8))
    objective = options.get("objective", "decay")
    decay_base = float(options.get("decay_base", 0.9))
    bench_weights = options.get("bench_weights", {"0": 0.03, "1": 0.21, "2": 0.06, "3": 0.002})
    bench_weights = {int(k): float(v) for k, v in bench_weights.items()}

    ft_value = float(options.get("ft_value", 1.5))
    ft_value_list = options.get("ft_value_list", {"2": 2.0, "3": 1.6, "4": 1.3, "5": 1.1})
    ft_use_penalty = options.get("ft_use_penalty", 0.2)
    itb_value = float(options.get("itb_value", 0.08))
    itb_loss_per_transfer = float(options.get("itb_loss_per_transfer", 0.0))

    initial_ft = max(0, data.get("ft", 1))
    ft_base = data.get("ft_base", 1)
    chip_limits = dict(options.get("chip_limits", {}))
    allowed_chip_gws = options.get("allowed_chip_gws", {})
    forced_chip_gws = options.get("forced_chip_gws", {})
    booked_transfers = options.get("booked_transfers", [])
    preseason = options.get("preseason", False)

    merged_data = data["merged_data"]
    team_data = data["team_data"]
    type_data = data["type_data"]
    next_gw = int(data["next_gw"])
    initial_squad = data["initial_squad"]
    itb = float(data["itb"])
    fixtures = data["fixtures"]

    if preseason:
        itb = 100.0
        initial_ft = 0

    players = merged_data.index.to_list()
    el_types = type_data.index.to_list()
    teams = team_data["name"].to_list()
    last_gw = min(next_gw + horizon - 1, MAX_GAMEWEEK)
    horizon = last_gw + 1 - next_gw
    gws = list(range(next_gw, last_gw + 1))
    all_gw = [next_gw - 1, *gws]
    order = [0, 1, 2, 3]
    price_modified_players = data["price_modified_players"]
    ft_states = [0, 1, 2, 3, 4, 5]

    # Initialize HiGHS Model
    m = highspy.Highs()
    sum_ = m.qsum
    verbose = bool(options.get("verbose", False))
    m.setOptionValue("output_flag", verbose)
    m.setOptionValue("log_to_console", verbose)

    def bin_vars(*sets, name):
        return m.addVariables(*sets, lb=0, ub=1, type=BIN, name_prefix=name)

    def int_vars(*sets, name, lb=0, ub=None):
        kwargs = {"lb": lb, "type": INT, "name_prefix": name}
        if ub is not None:
            kwargs["ub"] = ub
        return m.addVariables(*sets, **kwargs)

    def cont_vars(*sets, name, lb=0, ub=None):
        kwargs = {"lb": lb, "type": CONT, "name_prefix": name}
        if ub is not None:
            kwargs["ub"] = ub
        return m.addVariables(*sets, **kwargs)

    # Variables
    squad = bin_vars(players, all_gw, name="squad")
    squad_fh = bin_vars(players, gws, name="squad_fh")
    lineup = bin_vars(players, gws, name="lineup")
    captain = bin_vars(players, gws, name="captain")
    vicecap = bin_vars(players, gws, name="vicecap")
    bench = bin_vars(players, gws, order, name="bench")
    transfer_in = bin_vars(players, gws, name="transfer_in")
    transfer_out_first = bin_vars(price_modified_players, gws, name="tr_out_first")
    transfer_out_regular = bin_vars(players, gws, name="tr_out_reg")
    transfer_out = {
        (p, w): transfer_out_regular[p, w] + (transfer_out_first[p, w] if p in price_modified_players else 0)
        for p in players
        for w in gws
    }
    in_the_bank = cont_vars(all_gw, name="itb", lb=0)
    fts = int_vars(all_gw, name="ft", lb=0, ub=5)
    ft_above_ub = bin_vars(gws, name="ft_above")
    ft_below_lb = bin_vars(gws, name="ft_below")
    fts_state = bin_vars(gws, ft_states, name="ft_state")
    penalized_transfers = int_vars(gws, name="pt", lb=0)
    aux = bin_vars(gws, name="aux")
    transfer_count = int_vars(gws, name="trc", lb=0, ub=SQUAD_SIZE)

    use_wc = bin_vars(gws, name="use_wc")
    use_bb = bin_vars(gws, name="use_bb")
    use_fh = bin_vars(gws, name="use_fh")
    use_tc = bin_vars(players, gws, name="use_tc")

    player_type = merged_data["element_type"].to_dict()
    player_pos = merged_data["Pos"].to_dict()
    lineup_type_count = {(t, w): sum_(lineup[p, w] for p in players if player_type[p] == t) for t in el_types for w in gws}
    squad_type_count = {(t, w): sum_(squad[p, w] for p in players if player_type[p] == t) for t in el_types for w in gws}
    squad_fh_type_count = {(t, w): sum_(squad_fh[p, w] for p in players if player_type[p] == t) for t in el_types for w in gws}
    sell_price = data["sell_price"]
    buy_price = data["buy_price"]
    sold_amount = {
        w: (
            sum_(sell_price[p] * transfer_out_first[p, w] for p in price_modified_players)
            + sum_(buy_price[p] * transfer_out_regular[p, w] for p in players)
        )
        for w in gws
    }
    fh_sell_price = {p: sell_price[p] if p in price_modified_players else buy_price[p] for p in players}
    bought_amount = {w: sum_(buy_price[p] * transfer_in[p, w] for p in players) for w in gws}
    pts_by_week = {w: merged_data[f"{w}_Pts"].to_dict() for w in gws}
    xmins_by_week = {
        w: merged_data[f"{w}_xMins"].to_dict() if f"{w}_xMins" in merged_data.columns else dict.fromkeys(players, 90)
        for w in gws
    }
    points_player_week = {(p, w): pts_by_week[w][p] for p in players for w in gws}
    minutes_player_week = {(p, w): xmins_by_week[w][p] for p in players for w in gws}
    player_team = merged_data["name"].to_dict()
    squad_count = {w: sum_(squad[p, w] for p in players) for w in gws}
    squad_fh_count = {w: sum_(squad_fh[p, w] for p in players) for w in gws}
    num_transfers = {w: sum_(transfer_out[p, w] for p in players) for w in gws}
    transfer_diff = {w: num_transfers[w] - fts[w] - SQUAD_SIZE * use_wc[w] for w in gws}
    use_tc_gw = {w: sum_(use_tc[p, w] for p in players) for w in gws}

    # Initial conditions
    m.addConstrs([squad[p, next_gw - 1] == 1 for p in initial_squad if p in players])
    m.addConstrs([squad[p, next_gw - 1] == 0 for p in players if p not in initial_squad])
    m.addConstr(in_the_bank[next_gw - 1] == itb)
    m.addConstr(fts[next_gw] == initial_ft * (1 - use_wc[next_gw]) + ft_base * use_wc[next_gw])
    m.addConstrs([fts[w] >= 1 for w in gws if w > next_gw])

    # Core Constraints
    m.addConstrs([squad_count[w] == SQUAD_SIZE for w in gws])
    m.addConstrs([squad_fh_count[w] == SQUAD_SIZE * use_fh[w] for w in gws])
    m.addConstrs([sum_(lineup[p, w] for p in players) == LINEUP_SIZE + (SQUAD_SIZE - LINEUP_SIZE) * use_bb[w] for w in gws])
    m.addConstrs([sum_(bench[p, w, 0] for p in players if player_type[p] == 1) == 1 - use_bb[w] for w in gws])
    m.addConstrs([sum_(bench[p, w, o] for p in players) == 1 - use_bb[w] for w in gws for o in [1, 2, 3]])
    m.addConstrs([sum_(captain[p, w] for p in players) == 1 for w in gws])
    m.addConstrs([sum_(vicecap[p, w] for p in players) == 1 for w in gws])
    m.addConstrs([lineup[p, w] <= squad[p, w] + use_fh[w] for p in players for w in gws])
    m.addConstrs([bench[p, w, o] <= squad[p, w] + use_fh[w] for p in players for w in gws for o in order])
    m.addConstrs([lineup[p, w] <= squad_fh[p, w] + 1 - use_fh[w] for p in players for w in gws])
    m.addConstrs([bench[p, w, o] <= squad_fh[p, w] + 1 - use_fh[w] for p in players for w in gws for o in order])
    m.addConstrs([captain[p, w] <= lineup[p, w] for p in players for w in gws])
    m.addConstrs([vicecap[p, w] <= lineup[p, w] for p in players for w in gws])
    m.addConstrs([captain[p, w] + vicecap[p, w] <= 1 for p in players for w in gws])
    m.addConstrs([lineup[p, w] + sum_(bench[p, w, o] for o in order) <= 1 for p in players for w in gws])

    squad_min_play = type_data["squad_min_play"].astype(int).to_dict()
    squad_max_play = type_data["squad_max_play"].astype(int).to_dict()
    squad_select = type_data["squad_select"].astype(int).to_dict()

    m.addConstrs([lineup_type_count[t, w] >= squad_min_play[t] for t in el_types for w in gws])
    m.addConstrs([lineup_type_count[t, w] <= squad_max_play[t] + use_bb[w] for t in el_types for w in gws])
    m.addConstrs([squad_type_count[t, w] == squad_select[t] for t in el_types for w in gws])
    m.addConstrs([squad_fh_type_count[t, w] == squad_select[t] * use_fh[w] for t in el_types for w in gws])

    if data.get("max_players_from_team", 3) > MAX_PLAYERS_PER_TEAM:
        no_transfer = bin_vars(gws, name="no_transfer")
        m.addConstrs([transfer_count[w] <= SQUAD_SIZE * (1 - no_transfer[w]) for w in gws])
        m.addConstrs([transfer_count[w] >= 1 - SQUAD_SIZE * no_transfer[w] for w in gws])
        m.addConstrs([
            sum_(squad[p, w] for p in players if player_team[p] == t) <= MAX_PLAYERS_PER_TEAM + no_transfer[w]
            for t in teams
            for w in gws
        ])
    else:
        m.addConstrs([
            sum_(squad[p, w] for p in players if player_team[p] == t) <= MAX_PLAYERS_PER_TEAM
            for t in teams
            for w in all_gw
        ])

    m.addConstrs([
        sum_(squad_fh[p, w] for p in players if player_team[p] == t) <= MAX_PLAYERS_PER_TEAM * use_fh[w]
        for t in teams
        for w in gws
    ])

    # Transfer & Budget constraints
    m.addConstrs([squad[p, w] == squad[p, w - 1] + transfer_in[p, w] - transfer_out[p, w] for p in players for w in gws])
    m.addConstrs([
        in_the_bank[w] == in_the_bank[w - 1] + sold_amount[w] - bought_amount[w] - (transfer_count[w] * itb_loss_per_transfer if w > next_gw else 0)
        for w in gws
    ])
    m.addConstrs([
        sum_(fh_sell_price[p] * squad[p, w - 1] for p in players) + in_the_bank[w - 1] >= sum_(fh_sell_price[p] * squad_fh[p, w] for p in players)
        for w in gws
    ])
    m.addConstrs([transfer_in[p, w] <= 1 - use_fh[w] for p in players for w in gws])
    m.addConstrs([transfer_out[p, w] <= 1 - use_fh[w] for p in players for w in gws])

    # Big-M Free Transfer Clamping [1, 5]
    raw_gw_ft = {w: fts[w] - transfer_count[w] + 1 - use_wc[w] - use_fh[w] for w in gws}
    big_m = 20

    m.addConstrs([raw_gw_ft[w] >= 6 - big_m * (1 - ft_above_ub[w]) for w in gws])
    m.addConstrs([raw_gw_ft[w] <= 5 + big_m * ft_above_ub[w] for w in gws])
    m.addConstrs([raw_gw_ft[w] <= 0 + big_m * (1 - ft_below_lb[w]) for w in gws])
    m.addConstrs([raw_gw_ft[w] >= 1 - big_m * ft_below_lb[w] for w in gws])

    m.addConstrs([fts[w + 1] <= 5 + big_m * (1 - ft_above_ub[w]) for w in gws if w + 1 in gws])
    m.addConstrs([fts[w + 1] >= 5 - big_m * (1 - ft_above_ub[w]) for w in gws if w + 1 in gws])
    m.addConstrs([fts[w + 1] <= 1 + big_m * (1 - ft_below_lb[w]) for w in gws if w + 1 in gws])
    m.addConstrs([fts[w + 1] >= 1 - big_m * (1 - ft_below_lb[w]) for w in gws if w + 1 in gws])
    m.addConstrs([fts[w + 1] - raw_gw_ft[w] <= big_m * (ft_above_ub[w] + ft_below_lb[w]) for w in gws if w + 1 in gws])
    m.addConstrs([raw_gw_ft[w] - fts[w + 1] <= big_m * (ft_above_ub[w] + ft_below_lb[w]) for w in gws if w + 1 in gws])

    m.addConstrs([fts[w] == sum_(fts_state[w, s] * s for s in ft_states) for w in gws])
    m.addConstrs([sum_(fts_state[w, s] for s in ft_states) == 1 for w in gws])
    m.addConstrs([penalized_transfers[w] >= transfer_diff[w] for w in gws])

    # Chip Constraints
    m.addConstrs([use_wc[w] + use_fh[w] + use_bb[w] + use_tc_gw[w] <= 1 for w in gws])
    m.addConstrs([aux[w] <= 1 - use_wc[w - 1] for w in gws if w > next_gw])
    m.addConstrs([aux[w] <= 1 - use_fh[w - 1] for w in gws if w > next_gw])
    m.addConstrs([use_tc[p, w] <= captain[p, w] for p in players for w in gws])

    wc = options.get("use_wc", [])
    if wc:
        m.addConstrs([use_wc[w] == 1 for w in wc])
        chip_limits["wc"] = len(wc)

    bb = options.get("use_bb", [])
    if bb:
        m.addConstrs([use_bb[w] == 1 for w in bb])
        chip_limits["bb"] = len(bb)

    fh = options.get("use_fh", [])
    if fh:
        m.addConstrs([use_fh[w] == 1 for w in fh])
        chip_limits["fh"] = len(fh)

    tc = options.get("use_tc", [])
    if tc:
        m.addConstrs([use_tc_gw[w] == 1 for w in tc])
        chip_limits["tc"] = len(tc)

    for chip_k in ["wc", "bb", "fh", "tc"]:
        if chip_k in forced_chip_gws and forced_chip_gws[chip_k]:
            target_var = {"wc": use_wc, "bb": use_bb, "fh": use_fh, "tc": use_tc_gw}[chip_k]
            m.addConstr(sum_(target_var[w] for w in forced_chip_gws[chip_k]) == 1)
            chip_limits[chip_k] = 1

    m.addConstr(sum_(use_wc[w] for w in gws) <= chip_limits.get("wc", 0))
    m.addConstr(sum_(use_bb[w] for w in gws) <= chip_limits.get("bb", 0))
    m.addConstr(sum_(use_fh[w] for w in gws) <= chip_limits.get("fh", 0))
    m.addConstr(sum_(use_tc_gw[w] for w in gws) <= chip_limits.get("tc", 0))
    m.addConstrs([squad_fh[p, w] <= use_fh[w] for p in players for w in gws])

    # Multiple sell tracking fix
    m.addConstrs([transfer_out_first[p, w] + transfer_out_regular[p, w] <= 1 for p in price_modified_players for w in gws])
    m.addConstrs([
        horizon * sum_(transfer_out_first[p, w] for w in gws if w <= wbar) >= sum_(transfer_out_regular[p, w] for w in gws if w >= wbar)
        for p in price_modified_players
        for wbar in gws
    ])
    m.addConstrs([sum_(transfer_out_first[p, w] for w in gws) <= 1 for p in price_modified_players])
    m.addConstrs([transfer_in[p, w] + transfer_out[p, w] <= 1 for p in players for w in gws])

    # Transfer Count & Penalties
    m.addConstrs([transfer_count[w] >= num_transfers[w] - SQUAD_SIZE * use_wc[w] for w in gws])
    m.addConstrs([transfer_count[w] <= num_transfers[w] for w in gws])
    m.addConstrs([transfer_count[w] <= SQUAD_SIZE * (1 - use_wc[w]) for w in gws])
    ft_penalty = {w: (ft_use_penalty or 0) * transfer_count[w] for w in gws}

    # Optional Constraints (Banned, Locked, No Future, etc.)
    if options.get("banned"):
        banned_players = [p for p in options["banned"] if p in players]
        m.addConstrs([sum_(squad[p, w] for w in gws) == 0 for p in banned_players])
        m.addConstrs([sum_(squad_fh[p, w] for w in gws) == 0 for p in banned_players])

    if options.get("locked"):
        locked_players = [p for p in options["locked"] if p in players]
        m.addConstrs([squad[p, w] + squad_fh[p, w] == 1 for p in locked_players for w in gws])

    if options.get("no_future_transfer"):
        m.addConstr(sum_(transfer_in[p, w] for p in players for w in gws if w > next_gw and w not in options.get("use_wc", [])) == 0)

    no_tr_last = options.get("no_transfer_last_gws", 0)
    if no_tr_last and horizon > no_tr_last:
        m.addConstrs([sum_(transfer_in[p, w] for p in players) <= SQUAD_SIZE * use_wc[w] for w in gws if w > last_gw - no_tr_last])

    if options.get("num_transfers") is not None:
        m.addConstr(sum_(transfer_in[p, next_gw] for p in players) == int(options["num_transfers"]))

    if options.get("hit_limit") is not None:
        m.addConstr(sum_(penalized_transfers[w] for w in gws) <= int(options["hit_limit"]))

    if options.get("weekly_hit_limit") is not None:
        m.addConstrs([penalized_transfers[w] <= int(options["weekly_hit_limit"]) for w in gws])

    max_defs_per_team = int(options.get("max_defenders_per_team", 3))
    if max_defs_per_team < MAX_PLAYERS_PER_TEAM:
        m.addConstrs([
            sum_(squad[p, w] for p in players if player_team[p] == t and player_pos[p] in {"G", "D"}) <= max_defs_per_team
            for t in teams
            for w in gws
        ])
        m.addConstrs([
            sum_(squad_fh[p, w] for p in players if player_team[p] == t and player_pos[p] in {"G", "D"}) <= max_defs_per_team * use_fh[w]
            for t in teams
            for w in gws
        ])

    for bt in booked_transfers:
        tr_gw = bt.get("gw")
        if tr_gw and tr_gw in gws:
            p_in = bt.get("transfer_in")
            p_out = bt.get("transfer_out")
            if p_in and p_in in players:
                m.addConstr(transfer_in[p_in, tr_gw] == 1)
            if p_out and p_out in players:
                m.addConstr(transfer_out[p_out, tr_gw] == 1)

    # Opposing play logic
    cp_penalty: Dict[int, Any] = {}
    if options.get("no_opposing_play") is True:
        gw_opp_teams = {
            w: [(f["home"], f["away"]) for f in fixtures if f["gw"] == w] + [(f["away"], f["home"]) for f in fixtures if f["gw"] == w]
            for w in gws
        }
        for gw_idx in gws:
            if options.get("opposing_play_group", "position") == "position":
                opposing_positions = [(1, 3), (1, 4), (2, 3), (2, 4), (3, 1), (4, 1), (3, 2), (4, 2)]
                opposing_players = [
                    (p1, p2)
                    for p1 in players
                    for p2 in players
                    if (player_team[p1], player_team[p2]) in gw_opp_teams[gw_idx] and (player_type[p1], player_type[p2]) in opposing_positions
                ]
            else:
                opposing_players = [
                    (p1, p2) for p1 in players for p2 in players if (player_team[p1], player_team[p2]) in gw_opp_teams[gw_idx]
                ]
            m.addConstrs([lineup[p1, gw_idx] + lineup[p2, gw_idx] <= 1 for (p1, p2) in opposing_players])

    # FT State Values
    ft_state_value: Dict[int, float] = {}
    for s in ft_states:
        ft_state_value[s] = ft_state_value.get(s - 1, 0.0) + float(ft_value_list.get(str(s), ft_value))

    gw_ft_value = {w: sum_(ft_state_value[s] * fts_state[w, s] for s in ft_states) for w in gws}
    gw_ft_gain = {w: gw_ft_value[w] - gw_ft_value.get(w - 1, 0) for w in gws}

    # Objective Expressions
    hit_cost = float(options.get("hit_cost", 4))
    vcap_weight = float(options.get("vcap_weight", 0.1))
    gw_xp = {
        w: sum_(
            points_player_week[p, w]
            * (lineup[p, w] + captain[p, w] + vcap_weight * vicecap[p, w] + use_tc[p, w] + sum_(bench_weights[o] * bench[p, w, o] for o in order))
            for p in players
        )
        for w in gws
    }

    gw_total = {
        w: gw_xp[w] - hit_cost * penalized_transfers[w] + gw_ft_gain[w] - ft_penalty[w] + itb_value * in_the_bank[w] - cp_penalty.get(w, 0)
        for w in gws
    }

    if objective == "regular":
        objective_expr = sum_(gw_total[w] for w in gws)
    else:
        objective_expr = sum_(gw_total[w] * pow(decay_base, w - next_gw) for w in gws)

    m.setObjective(objective_expr, sense=highspy.ObjSense.kMaximize)

    report_decay_base = options.get("report_decay_base", [0.85, 1.0, 1.017])
    decay_metrics = {i: sum_(gw_total[w] * pow(i, w - next_gw) for w in gws) for i in report_decay_base}

    secs = int(options.get("secs", 300))
    gap = float(options.get("gap", 0.0))
    m.setOptionValue("parallel", "on")
    m.setOptionValue("time_limit", secs)
    m.setOptionValue("mip_rel_gap", gap)

    def make_val(values_array):
        def val(x):
            if isinstance(x, (int, float)):
                return float(x)
            if isinstance(x, highspy.highs_var):
                return values_array[x.index]
            return x.evaluate(values_array)
        return val

    num_iterations = int(options.get("num_iterations", 1))
    iteration_criteria = options.get("iteration_criteria", "this_gw_transfer_in_out")
    solutions: List[SolverResult] = []

    for iteration in range(num_iterations):
        m.run()
        val = make_val(list(m.getSolution().col_value))

        picks: List[Dict[str, Any]] = []
        for w in gws:
            for p in players:
                if val(squad[p, w]) + val(squad_fh[p, w]) + val(transfer_out[p, w]) > BINARY_THRESHOLD:
                    lp = merged_data.loc[p]
                    is_captain = 1 if val(captain[p, w]) > BINARY_THRESHOLD else 0
                    is_squad = (
                        1
                        if (val(use_fh[w]) < BINARY_THRESHOLD and val(squad[p, w]) > BINARY_THRESHOLD)
                        or (val(use_fh[w]) > BINARY_THRESHOLD and val(squad_fh[p, w]) > BINARY_THRESHOLD)
                        else 0
                    )
                    is_lineup = 1 if val(lineup[p, w]) > BINARY_THRESHOLD else 0
                    is_vice = 1 if val(vicecap[p, w]) > BINARY_THRESHOLD else 0
                    is_tc = 1 if val(use_tc[p, w]) > BINARY_THRESHOLD else 0
                    is_transfer_in = 1 if val(transfer_in[p, w]) > BINARY_THRESHOLD else 0
                    is_transfer_out = 1 if val(transfer_out[p, w]) > BINARY_THRESHOLD else 0

                    bench_value = -1
                    for o in order:
                        if val(bench[p, w, o]) > BINARY_THRESHOLD:
                            bench_value = o

                    position = type_data.loc[lp["element_type"], "singular_name_short"]
                    player_buy_price = 0 if not is_transfer_in else buy_price[p]
                    player_sell_price = (
                        0
                        if not is_transfer_out
                        else (sell_price[p] if p in price_modified_players and val(transfer_out_first[p, w]) > BINARY_THRESHOLD else buy_price[p])
                    )
                    multiplier = (1 if is_lineup else 0) + (1 if is_captain else 0) + (1 if is_tc else 0)
                    xp_cont = points_player_week[p, w] * multiplier

                    chip_text = ""
                    if val(use_wc[w]) > BINARY_THRESHOLD:
                        chip_text = "WC"
                    elif val(use_fh[w]) > BINARY_THRESHOLD:
                        chip_text = "FH"
                    elif val(use_bb[w]) > BINARY_THRESHOLD:
                        chip_text = "BB"
                    elif val(use_tc[p, w]) > BINARY_THRESHOLD:
                        chip_text = "TC"

                    picks.append({
                        "id": p,
                        "week": w,
                        "name": lp["web_name"],
                        "pos": position,
                        "type": lp["element_type"],
                        "team": lp["name"],
                        "buy_price": player_buy_price,
                        "sell_price": player_sell_price,
                        "xP": round(float(points_player_week[p, w]), 2),
                        "xMin": int(minutes_player_week[p, w]),
                        "squad": is_squad,
                        "lineup": is_lineup,
                        "bench": bench_value,
                        "captain": is_captain,
                        "vicecaptain": is_vice,
                        "transfer_in": is_transfer_in,
                        "transfer_out": is_transfer_out,
                        "multiplier": multiplier,
                        "xp_cont": xp_cont,
                        "chip": chip_text,
                        "iter": iteration,
                        "ft": val(fts[w]),
                        "transfer_count": val(num_transfers[w]),
                    })

        picks_df = pd.DataFrame(picks)
        if not picks_df.empty:
            picks_df.sort_values(by=["week", "squad", "lineup", "bench", "type"], ascending=[True, False, False, True, True], inplace=True)

        total_xp = float(val(sum_((lineup[p, w] + captain[p, w]) * points_player_week[p, w] for p in players for w in gws)))
        summary_of_actions = ""
        move_summary = {"chip": [], "buy": [], "sell": []}
        statistics: Dict[int, Dict[str, Any]] = {}

        for w in all_gw:
            if w == all_gw[0]:
                statistics[int(w)] = {"itb": float(val(in_the_bank[w])), "ft": float(val(fts[w]))}
                continue

            summary_of_actions += f"** GW {w}:\n"
            chip_decision = (
                ("WC" if val(use_wc[w]) > BINARY_THRESHOLD else "")
                + ("FH" if val(use_fh[w]) > BINARY_THRESHOLD else "")
                + ("BB" if val(use_bb[w]) > BINARY_THRESHOLD else "")
                + ("TC" if val(use_tc_gw[w]) > BINARY_THRESHOLD else "")
            )
            if chip_decision:
                summary_of_actions += f"CHIP {chip_decision}\n"
                move_summary["chip"].append(f"{chip_decision}{w}")

            summary_of_actions += (
                f"ITB={round(val(in_the_bank[w - 1]), 1)}->{round(val(in_the_bank[w]), 1)}, "
                f"FT={round(val(fts[w]))}, "
                f"PT={round(val(penalized_transfers[w]))}, "
                f"NT={round(val(num_transfers[w]))}\n"
            )

            for p in players:
                if val(transfer_in[p, w]) > BINARY_THRESHOLD:
                    summary_of_actions += f"Buy {p} - {merged_data['web_name'][p]}\n"
                    if w == next_gw:
                        move_summary["buy"].append(merged_data["web_name"][p])

            for p in players:
                if val(transfer_out[p, w]) > BINARY_THRESHOLD:
                    summary_of_actions += f"Sell {p} - {merged_data['web_name'][p]}\n"
                    if w == next_gw:
                        move_summary["sell"].append(merged_data["web_name"][p])

            lineup_players = picks_df[(picks_df["week"] == w) & (picks_df["lineup"] == 1)] if not picks_df.empty else pd.DataFrame()
            bench_players = picks_df[(picks_df["week"] == w) & (picks_df["bench"] >= 0)] if not picks_df.empty else pd.DataFrame()

            statistics[int(w)] = {
                "itb": float(val(in_the_bank[w])),
                "ft": float(val(fts[w])),
                "pt": float(val(penalized_transfers[w])),
                "nt": float(val(num_transfers[w])),
                "xP": float(lineup_players["xp_cont"].sum()) if not lineup_players.empty else 0.0,
                "obj": round(float(val(gw_total[w])), 2),
                "chip": chip_decision if chip_decision else None,
            }

        buy_decisions = ", ".join(move_summary["buy"]) if move_summary["buy"] else "-"
        sell_decisions = ", ".join(move_summary["sell"]) if move_summary["sell"] else "-"
        chip_decisions = ", ".join(move_summary["chip"]) if move_summary["chip"] else "-"

        solutions.append(
            SolverResult(
                iter=iteration,
                picks=picks_df,
                total_xp=total_xp,
                summary=summary_of_actions,
                statistics=statistics,
                buy=buy_decisions,
                sell=sell_decisions,
                chip=chip_decisions,
                score=float(val(objective_expr)),
                decay_metrics={k: float(val(v)) for k, v in decay_metrics.items()},
            )
        )

        if num_iterations > 1:
            if iteration_criteria == "this_gw_transfer_in_out":
                actions = (
                    sum_(1 - transfer_in[p, next_gw] for p in players if val(transfer_in[p, next_gw]) > BINARY_THRESHOLD)
                    + sum_(transfer_in[p, next_gw] for p in players if val(transfer_in[p, next_gw]) < BINARY_THRESHOLD)
                    + sum_(1 - transfer_out[p, next_gw] for p in players if val(transfer_out[p, next_gw]) > BINARY_THRESHOLD)
                    + sum_(transfer_out[p, next_gw] for p in players if val(transfer_out[p, next_gw]) < BINARY_THRESHOLD)
                )
                m.addConstr(actions >= 1)

    return solutions
