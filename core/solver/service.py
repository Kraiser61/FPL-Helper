import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from core.solver.paths import DATA_DIR
from core.solver.solver_engine import SolverResult, prep_data, solve_multi_period_fpl
from core.solver.utils import load_settings


class FPLSolverService:
    """
    High-level, thread-safe service bridging FPL Helper with the Open-FPL-Solver optimization engine.
    """

    def __init__(self, custom_settings_path: Optional[Path] = None):
        self.custom_settings_path = custom_settings_path

    def run_optimization(
        self,
        team_data: Dict[str, Any],
        csv_file_path: Optional[str | Path] = None,
        options_override: Optional[Dict[str, Any]] = None,
    ) -> List[SolverResult]:
        """
        Executes multi-period optimization with defensive validation.

        Args:
            team_data: The dictionary loaded from synced_team.json or FPL API.
            csv_file_path: Optional path to the projection CSV file (e.g. Solio, FPLReview).
            options_override: Optional solver parameter overrides.

        Returns:
            List of SolverResult objects for each iteration.
        """
        logger.info("FPL Solver optimizasyon süreci başlatılıyor...")

        # 1. Base options
        options = load_settings(self.custom_settings_path)
        if options_override:
            options.update(options_override)

        # 2. Assign CSV path
        if csv_file_path:
            csv_path = Path(csv_file_path)
            if not csv_path.exists():
                raise FileNotFoundError(f"Belirtilen projeksiyon CSV dosyası mevcut değil: {csv_path}")
            options["data_path"] = str(csv_path)
            options["datasource"] = csv_path.stem

        # 3. Validate team data
        if not team_data or "picks" not in team_data:
            raise ValueError("Kullanıcı takım verisi boş veya geçersiz. Lütfen FPL Kadromu Aktar yer imini çalıştırın.")

        if len(team_data["picks"]) != 15 and not options.get("preseason", False):
            logger.warning(f"Kadroda 15 yerine {len(team_data['picks'])} oyuncu bulundu. Preseason modu devreye alınıyor.")
            options["preseason"] = True

        # 4. Prepare data
        logger.debug("Veriler HiGHS modelleme formatına hazırlanıyor (prep_data)...")
        prepared_data = prep_data(team_data, options)

        # 5. Solve MIP
        logger.debug(f"HiGHS optimizasyonu çalıştırılıyor (Horizon: {options.get('horizon', 8)})...")
        results = solve_multi_period_fpl(prepared_data, options)

        if not results:
            raise RuntimeError("Optimizasyon motoru bir çözüm üretemedi. Kısıtlar aşırı sıkı olabilir.")

        logger.success(
            f"FPL Solver optimizasyonu başarıyla tamamlandı. En iyi çözüm skoru: {results[0].score:.2f}, xP: {results[0].total_xp:.2f}"
        )
        return results

    @staticmethod
    def extract_gameweek_squad(
        result: SolverResult,
        gameweek: int,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Extracts starting XI, bench, captain, and vice-captain for a specific gameweek.

        Returns:
            Tuple of (lineup_df, bench_df, captain_dict, vicecaptain_dict)
        """
        df = result.picks
        gw_df = df[df["week"] == gameweek]

        lineup_df = gw_df[gw_df["lineup"] == 1].sort_values(by=["type", "xP"], ascending=[True, False])
        bench_df = gw_df[gw_df["bench"] >= 0].sort_values(by=["bench", "type"], ascending=[True, True])

        cap_rows = gw_df[gw_df["captain"] == 1]
        vcap_rows = gw_df[gw_df["vicecaptain"] == 1]

        captain = cap_rows.iloc[0].to_dict() if not cap_rows.empty else None
        vice_captain = vcap_rows.iloc[0].to_dict() if not vcap_rows.empty else None

        return lineup_df, bench_df, captain, vice_captain

    @staticmethod
    def extract_transfer_plan(result: SolverResult) -> List[Dict[str, Any]]:
        """
        Extracts chronological multi-period transfer and chip plan across all horizon weeks.
        """
        df = result.picks
        gws = sorted(df["week"].unique())
        plan: List[Dict[str, Any]] = []

        for gw in gws:
            gw_df = df[df["week"] == gw]
            chip = gw_df["chip"].dropna()
            chip_name = chip.iloc[0] if not chip.empty and chip.iloc[0] != "" else None

            transfers_in = gw_df[gw_df["transfer_in"] == 1][["id", "name", "pos", "team", "buy_price", "xP"]].to_dict(orient="records")
            transfers_out = gw_df[gw_df["transfer_out"] == 1][["id", "name", "pos", "team", "sell_price", "xP"]].to_dict(orient="records")

            stat = result.statistics.get(int(gw), {})
            plan.append({
                "gameweek": int(gw),
                "chip": chip_name,
                "transfers_in": transfers_in,
                "transfers_out": transfers_out,
                "is_roll": len(transfers_in) == 0 and not chip_name,
                "itb": stat.get("itb", 0.0),
                "ft": stat.get("ft", 1),
                "pt": stat.get("pt", 0),
                "nt": stat.get("nt", 0),
                "xp": stat.get("xP", 0.0),
            })

        return plan
