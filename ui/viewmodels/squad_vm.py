import asyncio
from typing import Any, Dict, List
from PySide6.QtCore import QObject, QThreadPool, Signal

from config import APPDATA_DIR, DEFAULT_SQUAD_ELEMENT_IDS
from core.solver import FPLSolverService
from data.repositories.fixture_repo import FixtureRepository
from data.repositories.player_repo import PlayerRepository
from utils.async_worker import Worker
from utils.logger import app_logger


class SquadViewModel(QObject):
    """
    ViewModel for Squad Analysis & Pitch View.
    Powered by Open-FPL-Solver (HiGHS MIP Engine).
    Evaluates real user squad and calculates mathematically optimal 11, bench ordering,
    and captaincy based on multi-week mathematical optimization.
    """

    squad_loaded = Signal(list)
    lineup_optimized = Signal(dict)
    error_occurred = Signal(str)
    loading_started = Signal()

    def __init__(self, fpl_client, player_repo, user_repo, manager_id: int):
        super().__init__()
        self.fpl_client = fpl_client
        self.player_repo = player_repo
        self.user_repo = user_repo
        self.manager_id = manager_id
        self.solver_service = FPLSolverService()
        self.thread_pool = QThreadPool.globalInstance()

    def set_manager_id(self, manager_id: int):
        self.manager_id = manager_id

    def load_squad(self, gw_id: int = 1):
        self.loading_started.emit()
        worker = Worker(self._process_squad_data, gw_id)
        worker.signals.result.connect(self._on_squad_ready)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def toggle_player_lock(self, player_id: int, lock_type: str):
        worker = Worker(self._db_toggle_lock, player_id, lock_type)
        worker.signals.finished.connect(lambda: self.load_squad(gw_id=1))
        self.thread_pool.start(worker)

    def _process_squad_data(self, gw_id: int) -> Dict[str, Any]:
        """Async fetching of actual user picks and solving optimal lineup using Open-FPL-Solver."""
        async def fetch():
            app_logger.info(f"Kadro ve Open-FPL-Solver optimizasyonu yükleniyor (Manager: {self.manager_id})")

            bootstrap = await self.fpl_client.get_bootstrap_static()

            # Upsert master data to SQLite
            if bootstrap.teams:
                FixtureRepository.upsert_many_teams(bootstrap.teams, season_id=1)
            if bootstrap.elements:
                PlayerRepository.upsert_many_players(bootstrap.elements, season_id=1)

            players_dict = {p.id: p for p in bootstrap.elements}
            teams_dict = {t.id: t.name for t in bootstrap.teams}

            # 1. Fetch user picks via my-team (authenticated or local synced_team.json)
            picks = []
            my_team_raw: Dict[str, Any] = {}
            try:
                my_team_dto = await self.fpl_client.get_my_team(self.manager_id)
                if my_team_dto and getattr(my_team_dto, 'picks', None):
                    picks = my_team_dto.picks
                    my_team_raw = {
                        "picks": [
                            {
                                "element": p.element,
                                "position": p.position,
                                "is_captain": getattr(p, 'is_captain', False),
                                "is_vice_captain": getattr(p, 'is_vice_captain', False),
                                "selling_price": getattr(p, 'selling_price', None) or (players_dict[p.element].now_cost if p.element in players_dict else 50),
                                "purchase_price": getattr(p, 'purchase_price', None) or (players_dict[p.element].now_cost if p.element in players_dict else 50),
                                "element_type": players_dict[p.element].element_type if p.element in players_dict else 3
                            }
                            for p in picks
                        ],
                        "chips": getattr(my_team_dto, 'chips', []),
                        "transfers": {
                            "bank": getattr(getattr(my_team_dto, 'transfers', None), 'bank', 0),
                            "limit": getattr(getattr(my_team_dto, 'transfers', None), 'limit', 1),
                            "made": getattr(getattr(my_team_dto, 'transfers', None), 'made', 0),
                        }
                    }
            except Exception as e:
                app_logger.warning(f"my-team verisi çekilemedi ({self.manager_id}): {e}")

            # 2. Fallback to public user_picks endpoint if my-team failed
            if not picks:
                current_event = next((e for e in bootstrap.events if e.is_current), None) or next(
                    (e for e in bootstrap.events if e.is_next), bootstrap.events[0]
                )
                gw_to_try = current_event.id if current_event else 1
                try:
                    user_picks_dto = await self.fpl_client.get_user_picks(self.manager_id, gw_to_try)
                    if user_picks_dto and getattr(user_picks_dto, 'picks', None):
                        picks = user_picks_dto.picks
                except Exception as e:
                    app_logger.warning(f"user_picks çekilemedi (GW {gw_to_try}): {e}")

            # 3. Fallback: User Configured Default Squad if pre-season or missing picks
            if not picks and bootstrap.elements:
                app_logger.info("Varsayılan kadro şablonu devreye alınıyor...")
                from dataclasses import dataclass

                @dataclass
                class DummyPick:
                    element: int
                    position: int
                    is_captain: bool = False
                    is_vice_captain: bool = False
                    selling_price: int = 50

                ordered_ids = [
                    301, 115, 387, 508, 94, 95, 155, 426, 427, 106, 411,
                    302, 346, 425, 510
                ]
                picks = []
                for idx, elem_id in enumerate(ordered_ids):
                    p_match = players_dict.get(elem_id)
                    picks.append(
                        DummyPick(
                            element=elem_id,
                            position=idx + 1,
                            is_captain=(elem_id == 411),
                            is_vice_captain=(elem_id == 426),
                            selling_price=p_match.now_cost if p_match else 50,
                        )
                    )

            squad_list: List[Dict[str, Any]] = []
            POS_NAMES = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

            if picks:
                sorted_picks = sorted(picks, key=lambda x: getattr(x, 'position', 99))
                for pick in sorted_picks:
                    p_info = players_dict.get(pick.element)
                    if not p_info:
                        continue

                    # Basic player stats
                    next_gw_xp = float(p_info.ep_next or p_info.form or p_info.points_per_game or 2.0)
                    pick_pos = getattr(pick, 'position', 99)

                    p_dict = {
                        "id": p_info.id,
                        "web_name": p_info.web_name,
                        "team_name": teams_dict.get(p_info.team_id, ""),
                        "pos": POS_NAMES.get(p_info.element_type, "MID"),
                        "element_type": p_info.element_type,
                        "price": getattr(pick, 'selling_price', p_info.now_cost) / 10.0,
                        "xp": round(next_gw_xp, 1),
                        "xp_3gw": round(next_gw_xp * 3, 1),
                        "blended_score": round(next_gw_xp, 2),
                        "form": p_info.form,
                        "xg": getattr(p_info, 'expected_goals', 0.0) or getattr(p_info, 'expected_goals_per_90', 0.0) or 0.0,
                        "xa": getattr(p_info, 'expected_assists', 0.0) or getattr(p_info, 'expected_assists_per_90', 0.0) or 0.0,
                        "status": p_info.status,
                        "selected_by_percent": getattr(p_info, 'selected_by_percent', 0.0),
                        "threat": getattr(p_info, 'threat', 0.0),
                        "influence": getattr(p_info, 'influence', 0.0),
                        "bonus": getattr(p_info, 'bonus', 0),
                        "bps": getattr(p_info, 'bps', 0),
                        "clean_sheets": getattr(p_info, 'clean_sheets', 0),
                        "cbi": getattr(p_info, 'clearances_blocks_interceptions', 0) or 0,
                        "recoveries": getattr(p_info, 'recoveries', 0) or 0,
                        "defensive_actions": (getattr(p_info, 'clearances_blocks_interceptions', 0) or 0) + (
                            getattr(p_info, 'recoveries', 0) or 0
                        ),
                        "xgc": getattr(p_info, 'expected_goals_conceded', 0.0),
                        "fdr": 3,
                        "is_home": True,
                        "locked": False,
                        "is_captain": getattr(pick, 'is_captain', False),
                        "is_vice_captain": getattr(pick, 'is_vice_captain', False),
                        "pick_position": pick_pos,
                    }
                    squad_list.append(p_dict)

            # Preserve User's Real FPL Captain / Vice Captain from Picks for squad_list (Ana Sayfa)
            real_c_id = next((p["id"] for p in squad_list if p.get("is_captain")), None)
            real_vc_id = next((p["id"] for p in squad_list if p.get("is_vice_captain")), None)

            if not real_c_id and squad_list:
                for p in squad_list:
                    if p.get("pick_position", 99) == 1:
                        p["is_captain"] = True
                        real_c_id = p["id"]

            # --- RUN OPEN-FPL-SOLVER FOR OPTIMAL 11, BENCH, & CAPTAINS ---
            lineup_dict: Dict[str, Any] = {
                "starting_11": [],
                "bench_order": [],
                "formation": "0-0-0",
                "total_xp": 0.0,
                "captain_id": None,
                "vice_captain_id": None,
                "user_captain_id": real_c_id,
                "user_vice_id": real_vc_id,
                "promoted_to_starters": [],
                "demoted_to_bench": [],
            }

            if squad_list:
                try:
                    # Construct team_data dictionary for Open-FPL-Solver
                    if not my_team_raw or "picks" not in my_team_raw or len(my_team_raw["picks"]) != 15:
                        my_team_raw = {
                            "picks": [
                                {
                                    "element": p["id"],
                                    "position": p["pick_position"],
                                    "is_captain": p["is_captain"],
                                    "is_vice_captain": p["is_vice_captain"],
                                    "selling_price": int(p["price"] * 10),
                                    "purchase_price": int(p["price"] * 10),
                                    "element_type": p["element_type"],
                                }
                                for p in squad_list
                            ],
                            "chips": [],
                            "transfers": {"bank": 0, "limit": 1, "made": 0},
                        }

                    # Determine is_preseason
                    current_event = next((e for e in bootstrap.events if e.is_current), None)
                    if not current_event:
                        current_event = next((e for e in bootstrap.events if e.is_next), bootstrap.events[0] if bootstrap.events else None)
                    is_preseason = not bootstrap.events[0].finished if bootstrap.events else True

                    # Execute Open-FPL-Solver with unified datasource and options
                    solver_results = self.solver_service.run_optimization(
                        team_data=my_team_raw,
                        options_override={
                            "horizon": 8,
                            "verbose": False,
                            "datasource": "fplreview",
                            "preseason": is_preseason,
                        },
                    )

                    if solver_results:
                        best_res = solver_results[0]
                        first_gw = int(best_res.picks["week"].min())
                        lineup_df, bench_df, cap_info, vcap_info = self.solver_service.extract_gameweek_squad(
                            best_res, gameweek=first_gw
                        )

                        starting_11 = lineup_df["id"].tolist()
                        bench_order = bench_df["id"].tolist()
                        opt_c_id = cap_info["id"] if cap_info else (starting_11[0] if starting_11 else None)
                        opt_vc_id = vcap_info["id"] if vcap_info else (starting_11[1] if len(starting_11) > 1 else None)

                        # Update squad_list xP with the solver projection data if present
                        picks_map = {row["id"]: row for _, row in best_res.picks[best_res.picks["week"] == first_gw].iterrows()}
                        for p in squad_list:
                            if p["id"] in picks_map:
                                p["raw_xp"] = float(picks_map[p["id"]]["xP"])
                                p["xp"] = round(p["raw_xp"], 1)
                                p["blended_score"] = p["xp"]

                        def_count = len(lineup_df[lineup_df["type"] == 2])
                        mid_count = len(lineup_df[lineup_df["type"] == 3])
                        fwd_count = len(lineup_df[lineup_df["type"] == 4])
                        formation_str = f"{def_count}-{mid_count}-{fwd_count}"

                        user_starter_ids = {p["id"] for p in squad_list if p.get("pick_position", 99) <= 11}
                        opt_starter_ids = set(starting_11)

                        promoted_to_starters = list(opt_starter_ids - user_starter_ids)
                        demoted_to_bench = list(user_starter_ids - opt_starter_ids)

                        cap_bonus = float(picks_map[opt_c_id]["xP"]) if opt_c_id and opt_c_id in picks_map else 0.0

                        lineup_dict = {
                            "starting_11": starting_11,
                            "bench_order": bench_order,
                            "formation": formation_str,
                            "total_xp": round(float(lineup_df["xP"].sum()) + cap_bonus, 1),
                            "captain_id": opt_c_id,
                            "vice_captain_id": opt_vc_id,
                            "user_captain_id": real_c_id,
                            "user_vice_id": real_vc_id,
                            "promoted_to_starters": promoted_to_starters,
                            "demoted_to_bench": demoted_to_bench,
                        }
                except Exception as e:
                    app_logger.error(f"Open-FPL-Solver dizilim optimizasyonu hatası: {e}")

            return {"squad": squad_list, "lineup": lineup_dict}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(fetch())
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def _db_toggle_lock(self, player_id: int, lock_type: str):
        locks = PlayerRepository.get_all_player_locks()
        existing = next((l for l in locks if l['player_id'] == player_id), None)
        if existing:
            PlayerRepository.remove_player_lock(player_id)
        else:
            PlayerRepository.add_player_lock(player_id, lock_type)

    def _on_squad_ready(self, data: Dict[str, Any]):
        self.squad_loaded.emit(data.get("squad", []))
        self.lineup_optimized.emit(data.get("lineup", {}))

    def _on_error(self, err):
        err_msg = err[1] if isinstance(err, tuple) and len(err) > 1 else str(err)
        app_logger.error(f"SquadViewModel error: {err_msg}")
        self.error_occurred.emit(str(err_msg))
