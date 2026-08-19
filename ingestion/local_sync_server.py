import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Dict, Any
try:
    from PySide6.QtCore import QObject, Signal
    class SyncSignalEmitter(QObject):
        team_synced = Signal(dict)
    sync_signals = SyncSignalEmitter()
except ImportError:
    class DummyEmitter:
        def emit(self, *args, **kwargs):
            pass
    sync_signals = DummyEmitter()

from utils.logger import app_logger

# Path to persist synced team data
SYNC_CACHE_PATH = os.path.join(
    os.getenv("APPDATA", os.path.expanduser("~")),
    "FPL_Manager",
    "synced_team.json"
)
LOCAL_REPO_SYNC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "synced_team.json"
)

def get_user_sync_path(chat_id: Optional[str] = None) -> Optional[str]:
    """Returns user-specific squad file path if chat_id is provided."""
    if not chat_id:
        return None
    clean_id = "".join(c for c in str(chat_id) if c.isalnum() or c in ("-", "_"))
    if not clean_id:
        return None
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "users",
        f"team_{clean_id}.json"
    )

def save_synced_team_to_disk(data: Dict[str, Any], chat_id: Optional[str] = None):
    """Persists synced team data to disk so it survives app restarts. Supports per-user isolation."""
    user_path = get_user_sync_path(chat_id)
    if user_path:
        paths = [user_path]
    else:
        paths = [SYNC_CACHE_PATH, LOCAL_REPO_SYNC_PATH]

    for path in paths:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            app_logger.info(f"Synced team saved to {path}")
        except Exception as e:
            app_logger.error(f"Failed to save synced team to disk at {path}: {e}")

def load_synced_team_from_disk(chat_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads previously synced team data from disk if available. Checks user-specific squad first."""
    paths_to_check = []
    user_path = get_user_sync_path(chat_id)
    if user_path:
        paths_to_check.append(user_path)
    paths_to_check.extend([LOCAL_REPO_SYNC_PATH, SYNC_CACHE_PATH])

    for path in paths_to_check:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data and "team_data" in data:
                        return data
            except Exception as e:
                app_logger.error(f"Failed to load synced team from disk at {path}: {e}")
    return None




class SyncRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler that supports CORS & Private Network Access (PNA)
    for seamless communication from web browsers (fantasy.premierleague.com) to localhost.
    """

    def _send_cors_headers(self, status=200):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        """Handle CORS preflight requests from browser."""
        self._send_cors_headers(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        """Health check endpoint."""
        if self.path in ("/", "/api/status"):
            self._send_cors_headers(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "running", "server": "FPL_Local_Sync_Server", "version": "2.0"}
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self._send_cors_headers(404)
            self.end_headers()

    def do_POST(self):
        """Handle incoming synced squad payload from bookmarklet."""
        if self.path == "/api/sync_team":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body)

                manager_id = payload.get("manager_id", 3842372)
                team_data = payload.get("team_data", payload)

                # Persist to disk
                save_synced_team_to_disk({
                    "manager_id": manager_id,
                    "team_data": team_data
                })

                app_logger.info(f"Received live squad sync for Manager {manager_id} ({len(team_data.get('picks', []))} picks).")

                # Emit Qt signal to trigger UI refresh
                sync_signals.team_synced.emit({
                    "manager_id": manager_id,
                    "team_data": team_data
                })

                self._send_cors_headers(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                response = {
                    "status": "success",
                    "message": "Kadro başarıyla aktarıldı!",
                    "picks_count": len(team_data.get("picks", []))
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))

            except Exception as e:
                app_logger.error(f"Error processing sync payload: {e}")
                self._send_cors_headers(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_resp = {"status": "error", "message": str(e)}
                self.wfile.write(json.dumps(err_resp).encode("utf-8"))
        else:
            self._send_cors_headers(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Silence standard HTTP server console spam."""
        pass


class LocalSyncServer:
    """
    Lightweight background HTTP server listening on localhost for bookmarklet sync events.
    """
    def __init__(self, port: int = 8765):
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return

        try:
            self.server = HTTPServer(("127.0.0.1", self.port), SyncRequestHandler)
            self._is_running = True
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            app_logger.info(f"Local FPL Sync Server started successfully on http://127.0.0.1:{self.port}")
        except Exception as e:
            app_logger.error(f"Failed to start Local FPL Sync Server on port {self.port}: {e}")

    def stop(self):
        if self.server and self._is_running:
            app_logger.info("Stopping Local FPL Sync Server...")
            self._is_running = False
            self.server.shutdown()
            self.server.server_close()

# Global server instance
local_sync_server = LocalSyncServer()
