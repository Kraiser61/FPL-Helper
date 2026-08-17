from pathlib import Path
import os
from config import APPDATA_DIR

# Solver directories
SOLVER_ROOT = Path(__file__).parent
DATA_DIR = APPDATA_DIR / "data"
RESULTS_DIR = DATA_DIR / "results"
IMAGES_DIR = DATA_DIR / "images"
CACHE_DIR = APPDATA_DIR / ".cache"

# Ensure all directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
