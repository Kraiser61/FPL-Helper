import asyncio
from typing import Any, Dict, List
from PySide6.QtCore import QObject, QThreadPool, Signal

from core.strategy_engine import DecisionBundle, StrategyEngine
from utils.async_worker import Worker
from utils.logger import app_logger


class TransferViewModel(QObject):
    """
    ViewModel for the Transfer Recommendation View.
    Executes Open-FPL-Solver (HiGHS MIP) multi-period optimization in a background thread.
    """

    bundle_ready = Signal(object)  # Emits DecisionBundle object
    optimization_started = Signal()
    error_occurred = Signal(str)

    def __init__(self, fpl_client, manager_id: int, risk_profile: str = "balanced"):
        super().__init__()
        self.fpl_client = fpl_client
        self.manager_id = manager_id
        self.risk_profile = risk_profile
        self.strategy_engine = StrategyEngine(fpl_client, risk_profile=risk_profile)
        self.thread_pool = QThreadPool.globalInstance()
        self._is_analyzing = False

    def set_manager_id(self, manager_id: int):
        self.manager_id = manager_id

    def set_risk_profile(self, risk_profile: str):
        self.risk_profile = risk_profile
        self.strategy_engine.risk_profile = risk_profile

    def run_optimization(self, horizon_gws: int = 8):
        """Triggered when user opens Transfer tab or clicks Refresh."""
        if self._is_analyzing:
            return
        self._is_analyzing = True
        self.optimization_started.emit()
        worker = Worker(self._solve_strategy, horizon_gws)
        worker.signals.result.connect(self._on_optimization_done)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _solve_strategy(self, horizon_gws: int) -> DecisionBundle:
        """Background thread execution for Open-FPL-Solver StrategyEngine analysis."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.strategy_engine.analyze(self.manager_id, horizon_gws=horizon_gws)
            )
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    def _on_optimization_done(self, bundle: DecisionBundle):
        self._is_analyzing = False
        self.bundle_ready.emit(bundle)

    def _on_error(self, err_tuple):
        self._is_analyzing = False
        err_msg = err_tuple[1] if isinstance(err_tuple, tuple) and len(err_tuple) > 1 else str(err_tuple)
        app_logger.error(f"TransferViewModel optimization error: {err_msg}")
        self.error_occurred.emit(str(err_msg))
