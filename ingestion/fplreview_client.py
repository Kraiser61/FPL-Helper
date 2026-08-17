import urllib.request
import csv
import io
import asyncio
from typing import Dict, Any, Optional
from utils.logger import app_logger

class FPLReviewClient:
    """
    Automated fetcher and parser for FPL Review free model projections using standard urllib.
    No manual CSV download required from user.
    """
    
    CSV_PROJECTIONS_URL = "https://fplreview.com/5-week-free-projections-csv/"

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def fetch_free_projections(self) -> Dict[str, float]:
        """
        Fetches free projections from FPL Review in an async-friendly executor thread.
        Returns dict mapping player key (name_team) to expected points.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_fetch)

    def _sync_fetch(self) -> Dict[str, float]:
        app_logger.info("Automated fetching of FPL Review free projections...")
        projections: Dict[str, float] = {}

        try:
            req = urllib.request.Request(self.CSV_PROJECTIONS_URL, headers=self.headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                if response.status == 200:
                    content = response.read().decode('utf-8', errors='ignore')
                    reader = csv.DictReader(io.StringIO(content))
                    for row in reader:
                        name = row.get("Name", "").strip()
                        team = row.get("Team", "").strip()
                        try:
                            ev_val = float(row.get("5_GW_EV", row.get("EV", 0.0)))
                        except (ValueError, TypeError):
                            ev_val = 0.0
                        
                        if name:
                            key = f"{name.lower()}_{team.lower()}"
                            projections[key] = ev_val
                            projections[name.lower()] = ev_val
                    app_logger.info(f"FPL Review projections successfully parsed ({len(projections)} entries).")
                    return projections
                else:
                    app_logger.warning(f"FPL Review fetch returned HTTP status {response.status}.")
        except Exception as e:
            app_logger.warning(f"FPL Review fetch note: {e}. Engine will proceed with 100% internal FPL Helper model.")

        return projections

    @classmethod
    def get_blended_xp(cls, internal_xp: float, fplreview_ev: Optional[float]) -> float:
        """
        Blends internal FPL Helper xP with FPL Review EV.
        Ratio: 80% Internal Advanced Engine + 20% FPL Review Free Baseline.
        """
        if fplreview_ev is None or fplreview_ev <= 0.0:
            return internal_xp
            
        blended = (0.80 * internal_xp) + (0.20 * fplreview_ev)
        return round(blended, 2)
