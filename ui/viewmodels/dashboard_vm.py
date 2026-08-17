import asyncio
from PySide6.QtCore import QObject, Signal
from utils.async_worker import Worker
from PySide6.QtCore import QThreadPool
from typing import Dict, Any
from utils.logger import app_logger
from data.repositories.player_repo import PlayerRepository
from data.repositories.fixture_repo import FixtureRepository

class DashboardViewModel(QObject):
    """
    ViewModel for the Dashboard View.
    Fetches real FPL API summary data (Manager Profile, Rank, Points, Bank) live.
    """
    
    data_updated = Signal(dict)
    error_occurred = Signal(str)
    loading_started = Signal()
    
    def __init__(self, fpl_client, manager_id: int):
        super().__init__()
        self.fpl_client = fpl_client
        self.manager_id = manager_id
        self.thread_pool = QThreadPool.globalInstance()

    def set_manager_id(self, manager_id: int):
        self.manager_id = manager_id

    def load_data(self):
        """Triggers the background loading of real live dashboard data."""
        self.loading_started.emit()
        worker = Worker(self._fetch_dashboard_data)
        worker.signals.result.connect(self._on_data_ready)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _fetch_dashboard_data(self) -> Dict[str, Any]:
        """Runs in background thread to query FPL API."""
        async def fetch():
            app_logger.info(f"Fetching live FPL data for Manager ID: {self.manager_id}")
            
            # 1. Fetch Bootstrap static
            bootstrap = await self.fpl_client.get_bootstrap_static()
            
            # Upsert Teams FIRST to satisfy Player Foreign Key constraints
            if bootstrap.teams:
                FixtureRepository.upsert_many_teams(bootstrap.teams, season_id=1)
            if bootstrap.events:
                FixtureRepository.upsert_many_gameweeks(bootstrap.events, season_id=1)
            if bootstrap.elements:
                PlayerRepository.upsert_many_players(bootstrap.elements, season_id=1)
                
            current_event = next((e for e in bootstrap.events if e.is_current), None)
            if not current_event:
                current_event = next((e for e in bootstrap.events if e.is_next), bootstrap.events[0])
                
            gw_number = current_event.id if current_event else 1
            
            # 2. Fetch Manager Profile Info
            info = {}
            try:
                info = await self.fpl_client.get_manager_info(self.manager_id)
            except Exception as e:
                app_logger.warning(f"Could not fetch live manager info for {self.manager_id}: {e}")

            overall_points = info.get("summary_overall_points", 0)
            overall_rank = info.get("summary_overall_rank", 0)
            gw_points = info.get("summary_event_points", 0)
            player_first_name = info.get("player_first_name", "FPL")
            player_last_name = info.get("player_last_name", "Manager")
            team_name = info.get("name", "Kadro")
            
            # 3. Fetch my_team for live financial data
            bank = 0.0
            team_value = 100.0
            try:
                my_team_dto = await self.fpl_client.get_my_team(self.manager_id)
                if my_team_dto and my_team_dto.transfers:
                    bank = my_team_dto.transfers.bank / 10.0
                    team_value = my_team_dto.transfers.value / 10.0
            except Exception as e:
                app_logger.debug(f"My team live data for manager {self.manager_id}: {e}")

            return {
                "manager_name": f"{player_first_name} {player_last_name}",
                "team_name": team_name,
                "overall_points": overall_points,
                "overall_rank": overall_rank,
                "gw_points": gw_points,
                "gw_average": current_event.average_entry_score if current_event else 0,
                "team_value": team_value,
                "bank": bank,
                "gw_number": gw_number,
                "captain_name": "Canlı Kadro Bağlı",
                "captain_xp": 0.0,
                "top_transfer_in": "Analiz Ediliyor",
                "top_transfer_out": "Analiz Ediliyor",
                "chip_suggestion": "Wildcard / FH Hazır"
            }
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(fetch())
        finally:
            loop.close()

    def _on_data_ready(self, data: Dict[str, Any]):
        self.data_updated.emit(data)

    def _on_error(self, err_tuple):
        err_msg = err_tuple[1] if isinstance(err_tuple, tuple) and len(err_tuple) > 1 else str(err_tuple)
        self.error_occurred.emit(str(err_msg))
