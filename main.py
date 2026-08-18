import sys
import os
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QApplication
from utils.logger import app_logger
from data.database import db_manager
from config import DEFAULT_MANAGER_ID

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Enable High-FPS Hardware Acceleration Attributes BEFORE QApplication
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

# ViewModels
from ui.viewmodels.dashboard_vm import DashboardViewModel
from ui.viewmodels.squad_vm import SquadViewModel
from ui.viewmodels.transfer_vm import TransferViewModel

# Views
from ui.main_window import MainWindow
from ui.views.dashboard_view import TeamView
from ui.views.squad_view import SquadView
from ui.views.transfer_view import TransferView
from ui.views.fixture_view import FixtureView
from ui.views.settings_view import SettingsView

from ingestion.fpl_client import FPLClient
from ingestion.auth_manager import AuthManager
from data.repositories.player_repo import PlayerRepository
from data.repositories.user_repo import UserRepository
from ingestion.scheduler import FPLScheduler

def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to log unhandled crashes."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    app_logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Unhandled Exception caught by excepthook")

def mock_data_fetcher(job_type):
    """Callback for APScheduler"""
    app_logger.info(f"Background fetch triggered for {job_type}")

def main():
    sys.excepthook = handle_exception
    app_logger.info("=== Starting FPL Akıllı Kadro Yöneticisi v2.0 ===")
    
    # 1. Initialize Database
    try:
        db_manager.init_db()
    except Exception as e:
        app_logger.critical(f"Database initialization failed: {e}")
        sys.exit(1)
        
    # 2. Setup Qt Application
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 3. Initialize Ingestion, Repositories & Scheduler
    auth_manager = AuthManager()
    fpl_client = FPLClient(auth_manager=auth_manager)
    player_repo = PlayerRepository()
    user_repo = UserRepository()
    
    scheduler = FPLScheduler(data_fetcher_callback=mock_data_fetcher)
    scheduler.start()
    
    from ingestion.local_sync_server import local_sync_server, sync_signals
    local_sync_server.start()
    
    try:
        # 4. Initialize ViewModels with User's FPL Manager ID (3842372)
        manager_id = DEFAULT_MANAGER_ID
        app_logger.info(f"Initialized application with Manager ID: {manager_id}")
        
        dash_vm = DashboardViewModel(fpl_client, manager_id)
        squad_vm = SquadViewModel(fpl_client, player_repo, user_repo, manager_id)
        transfer_vm = TransferViewModel(fpl_client, manager_id, risk_profile="balanced")
        
        # 5. Initialize Main Window & All 5 Views
        main_window = MainWindow()
        
        team_view = TeamView(dash_vm, squad_vm)
        squad_view = SquadView(squad_vm)
        trans_view = TransferView(transfer_vm)
        fixture_view = FixtureView()
        settings_view = SettingsView(auth_manager=auth_manager)
        
        main_window.stacked_widget.addWidget(team_view)      # Index 0: 🏠 ANA SAYFA
        main_window.stacked_widget.addWidget(squad_view)     # Index 1: 📋 KADRO
        main_window.stacked_widget.addWidget(trans_view)     # Index 2: 💡 ÖNERİLER
        main_window.stacked_widget.addWidget(fixture_view)   # Index 3: 📊 FDR
        main_window.stacked_widget.addWidget(settings_view)  # Index 4: ⚙ AYARLAR
        
        # 6. Connect Global Refresh Handler
        def on_global_refresh():
            app_logger.info("Global refresh requested by user...")
            dash_vm.load_data()
            squad_vm.load_squad(gw_id=1)
            transfer_vm.run_optimization(horizon_gws=8)

        def on_browser_squad_synced(payload):
            app_logger.info("Live squad received from browser bookmarklet. Triggering instant refresh...")
            main_window.set_refresh_completed("● Kadro Tarayıcıdan Senkronize Edildi")
            on_global_refresh()

        def on_transfer_bundle_ready(bundle):
            main_window.set_refresh_completed("● Canlı Veri")

        main_window.refresh_requested.connect(on_global_refresh)
        settings_view.session_changed.connect(on_global_refresh)
        sync_signals.team_synced.connect(on_browser_squad_synced)
        transfer_vm.bundle_ready.connect(on_transfer_bundle_ready)
        transfer_vm.error_occurred.connect(lambda err: main_window.set_refresh_completed(f"❌ Hata: {err}"))
        
        main_window.show()
        
        # Initial live data trigger (delayed slightly to allow UI to render first)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, on_global_refresh)
        
        exit_code = app.exec()
    finally:
        app_logger.info("Shutting down application gracefully...")
        local_sync_server.stop()
        scheduler.stop()
        
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
