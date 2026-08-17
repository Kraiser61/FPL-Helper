import os
from pathlib import Path

# Base Paths
APP_NAME = "FPL_Manager"
APPDATA_DIR = Path(os.getenv('APPDATA', Path.home())) / APP_NAME
DB_PATH = APPDATA_DIR / "fpl_data.db"
LOG_DIR = APPDATA_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"

# Default User Credentials / Config
DEFAULT_MANAGER_ID = 3842372

# Default Offline/Pre-season User Squad (15 Players)
# GKP: Palmer (301), Button (302)
# DEF: De Cuyper (115), O'Reilly (387), Fredricson (425), Davies (508), Rowswell (510)
# MID: Schade (94), O.Dango (95), Enzo (155), B.Fernandes (426), Mbeumo (427)
# FWD: Thiago (106), Calvert-Lewin (346), Haaland (411)
DEFAULT_SQUAD_ELEMENT_IDS = [
    301, 302,
    115, 387, 425, 508, 510,
    94, 95, 155, 426, 427,
    106, 346, 411
]

# Ensure directories exist
APPDATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# FPL API Base URLs
BASE_URL = "https://fantasy.premierleague.com/api"
LOGIN_URL = "https://users.premierleague.com/accounts/login/"

# Endpoints
ENDPOINTS = {
    "bootstrap": f"{BASE_URL}/bootstrap-static/",
    "fixtures": f"{BASE_URL}/fixtures/",
    "manager_info": f"{BASE_URL}/entry/{{manager_id}}/",
    "manager_history": f"{BASE_URL}/entry/{{manager_id}}/history/",
    "user_picks": f"{BASE_URL}/entry/{{manager_id}}/event/{{event_id}}/picks/",
    "my_team": f"{BASE_URL}/my-team/{{manager_id}}/",
    "live_gw": f"{BASE_URL}/event/{{event_id}}/live/",
    "player_detail": f"{BASE_URL}/element-summary/{{player_id}}/",
    "event_status": f"{BASE_URL}/event-status/",
    "me": f"{BASE_URL}/me/"
}

# HTTP Client Settings
HTTP_TIMEOUT = 15.0  # seconds
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 1.1  # seconds between requests to avoid 429

# Standard User-Agent is required to avoid 403 Forbidden
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}
