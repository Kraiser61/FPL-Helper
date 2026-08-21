import json
import random
import string
import time
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from loguru import logger

from core.solver.paths import CACHE_DIR, DATA_DIR

CACHE_FILE = CACHE_DIR / "http_cache.json"
CACHE_EXPIRATION = 300  # 5 minutes in seconds


def get_default_options() -> Dict[str, Any]:
    """Returns safe default options for the FPL solver model."""
    return {
        "horizon": 8,
        "decay_base": 0.9,
        "ft_value": 1.5,
        "ft_value_list": {
            "2": 2.0,
            "3": 1.6,
            "4": 1.3,
            "5": 1.1,
        },
        "bench_weights": {
            "0": 0.03,
            "1": 0.21,
            "2": 0.06,
            "3": 0.002,
        },
        "vcap_weight": 0.1,
        "ft_use_penalty": 0.2,
        "itb_value": 0.08,
        "itb_loss_per_transfer": 0.0,
        "no_future_transfer": False,
        "no_transfer_last_gws": 2,
        "no_transfer_by_position": [],
        "force_ft_state_lb": [],
        "force_ft_state_ub": [],
        "randomized": False,
        "randomization_seed": None,
        "randomization_strength": 1.0,
        "xmin_lb": 300,
        "ev_per_price_cutoff": 30,
        "keep_top_ev_percent": 5,
        "banned": [],
        "banned_next_gw": [],
        "locked": [],
        "locked_next_gw": [],
        "price_changes": [],
        "keep": [],
        "delete_tmp": True,
        "single_solve": True,
        "solver": "highs",
        "secs": 60,
        "gap": 0.001,
        "num_transfers": None,
        "hit_limit": None,
        "weekly_hit_limit": 0,
        "hit_cost": 4,
        "use_wc": [],
        "use_bb": [],
        "use_fh": [],
        "use_tc": [],
        "chip_limits": {
            "bb": 0,
            "wc": 0,
            "fh": 0,
            "tc": 0,
        },
        "no_chip_gws": [],
        "allowed_chip_gws": {
            "bb": [],
            "wc": [],
            "fh": [],
            "tc": [],
        },
        "forced_chip_gws": {
            "bb": [],
            "wc": [],
            "fh": [],
            "tc": [],
        },
        "future_transfer_limit": None,
        "no_transfer_gws": [],
        "booked_transfers": [],
        "only_booked_transfers": False,
        "no_trs_except_wc": False,
        "preseason": False,
        "no_opposing_play": False,
        "opposing_play_group": "position",
        "opposing_play_penalty": 0.5,
        "pick_prices": {
            "G": "",
            "D": "",
            "M": "",
            "F": "",
        },
        "no_gk_rotation_after": None,
        "max_defenders_per_team": 3,
        "double_defense_pick": False,
        "transfer_itb_buffer": None,
        "num_iterations": 1,
        "iteration_criteria": "this_gw_transfer_in_out",
        "iteration_difference": 1,
        "iteration_target": [],
        "report_decay_base": [0.85, 1.0, 1.017],
        "datasource": "projections",
        "data_weights": {
            "projections": 1,
        },
        "export_data": "mixed.csv",
        "team_data": "json",
        "team_id": None,
        "team_json": None,
        "export_image": False,
        "solve_name": "regular",
        "override_next_gw": None,
        "generate_binary_files": False,
        "binary_file_weights": {},
        "binary_fixture_settings": {},
        "verbose": False,
        "print_result_table": False,
        "print_decay_metrics": False,
        "print_transfer_chip_summary": False,
        "print_squads": False,
        "dataframe_format": "plain",
        "hide_transfers": False,
        "solutions_file": "",
        "save_squads": True,
        "solutions_file_player_type": "name",
    }


def load_settings(custom_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads configuration options merging defaults with custom settings if present."""
    options = get_default_options()
    settings_file = custom_path or (DATA_DIR / "user_settings.json")

    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                user_opts = json.load(f)
                if isinstance(user_opts, dict):
                    options.update(user_opts)
        except Exception as e:
            logger.warning(f"Failed to parse user settings file {settings_file}: {e}")

    return options


def get_random_id(n: int = 5) -> str:
    """Generates an alphanumeric random string of length n."""
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def xmin_to_prob(xmin: float, sub_on: float = 0.5, sub_off: float = 0.3) -> float:
    """Calculates appearance probability given expected minutes."""
    start = min(max((xmin - 25 * sub_on) / (90 * (1 - sub_off) + 65 * sub_off - 25 * sub_on), 0.001), 0.999)
    return start + (1 - start) * sub_on


def get_dict_combinations(my_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generates non-conflicting combinations from a dictionary of lists."""
    dict_copy = dict(my_dict)
    for key in dict_copy.keys():
        if dict_copy[key] is None or len(dict_copy[key]) == 0:
            dict_copy[key] = [None]
    all_combs = [dict(zip(dict_copy.keys(), values, strict=False)) for values in product(*dict_copy.values())]
    feasible_combs = []
    for comb in all_combs:
        c_values = [i for i in comb.values() if i is not None]
        if len(c_values) == len(set(c_values)):
            feasible_combs.append({k: [v] for k, v in comb.items() if v is not None})
    return feasible_combs


def load_config_files(config_paths: str) -> Dict[str, Any]:
    """Loads and merges multiple semicolon-separated config JSON files."""
    merged_config: Dict[str, Any] = {}
    if not config_paths:
        return merged_config

    paths = config_paths.split(";")
    for path in paths:
        stripped_path = path.strip()
        if not stripped_path:
            continue
        try:
            with open(stripped_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                if isinstance(config, dict):
                    merged_config.update(config)
        except Exception as e:
            logger.warning(f"Could not load config file {stripped_path}: {e}")

    return merged_config


def cached_request(url: str, custom_cache_file: Optional[Path] = None, timeout: float = 15.0, force_refresh: bool = False) -> Any:
    """
    Fetches JSON data from URL with caching support.
    Returns cached data if available and fresh (< 5 mins old) unless force_refresh is True.
    Falls back to expired cache on network error.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = custom_cache_file or CACHE_FILE
    cache: Dict[str, Any] = {}

    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            cache = {}

    current_time = time.time()
    if not force_refresh and url in cache:
        cached_entry = cache[url]
        timestamp = cached_entry.get("timestamp", 0)
        if current_time - timestamp < CACHE_EXPIRATION:
            return cached_entry["data"]

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FPLHelper/2.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        cache[url] = {"data": data, "timestamp": current_time}
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
        except IOError as e:
            logger.debug(f"Could not write cache file: {e}")

        return data

    except requests.RequestException as e:
        if url in cache:
            logger.warning(f"Failed to fetch {url}, using expired cache. Error: {e}")
            return cache[url]["data"]
        raise RuntimeError(f"Network request to {url} failed: {e}") from e
