import asyncio
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fuzzywuzzy import fuzz
from loguru import logger
from playwright.async_api import async_playwright

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import BASE_URL, DEFAULT_MANAGER_ID
from core.solver.paths import DATA_DIR
from ingestion.fpl_client import FPLClient
from ingestion.auth_manager import AuthManager


TEAM_SHORT_TO_ID = {
    "ARS": 1, "AVL": 2, "BOU": 3, "BRE": 4, "BHA": 5,
    "CHE": 6, "CRY": 7, "EVE": 8, "FUL": 9, "IPS": 10,
    "LEI": 11, "LIV": 12, "MCI": 13, "MUN": 14, "NEW": 15,
    "NFO": 16, "SOU": 17, "TOT": 18, "WHU": 19, "WOL": 20
}

POS_NAMES = {1: "G", 2: "D", 3: "M", 4: "F"}
POS_STR_TO_INT = {
    "GKP": 1, "GK": 1, "G": 1,
    "DEF": 2, "D": 2,
    "MID": 3, "M": 3,
    "FWD": 4, "F": 4
}



class FPLReviewLiveScraper:
    """
    Automated Headless Scraper for FPL Review Projections.
    Extracts live elite expected points (xP) and minutes (xMins) directly from app.fplreview.com
    and matches with official FPL player identities.
    """

    def __init__(self, manager_id: int = DEFAULT_MANAGER_ID):
        self.manager_id = manager_id
        self.fpl_client = FPLClient(auth_manager=AuthManager())

    async def scrape_projections(self) -> List[Dict[str, Any]]:
        """Scrapes all available player projection rows from the FPL Review web interface."""
        logger.info(f"FPL Review web arayüzüne bağlanılıyor (Manager: {self.manager_id})...")
        scraped_raw: List[Dict[str, Any]] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                # 1. Navigate to free app
                await page.goto("https://app.fplreview.com/free", wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)

                # 2. Enter Manager ID if input exists
                inputs = page.locator("input[type='text'], input[placeholder*='123']")
                if await inputs.count() > 0:
                    await inputs.first.fill(str(self.manager_id))
                    connect_btn = page.locator("button:has-text('Connect')")
                    if await connect_btn.count() > 0:
                        await connect_btn.first.click()
                        await page.wait_for_timeout(5000)

                # 3. Switch to PROJECTIONS tab
                proj_btn = page.locator("button").filter(has_text="PROJECTIONS")
                if await proj_btn.count() > 0:
                    await proj_btn.first.click()
                    await page.wait_for_timeout(4000)

                # 4. Extract data from DOM table with scroll
                scraped_raw = await page.evaluate("""async () => {
                    const table = document.querySelector('table');
                    if (!table) return [];
                    const container = table.parentElement;
                    const results = new Map();
                    let lastScroll = -1;

                    for (let step = 0; step < 40; step++) {
                        const trs = Array.from(table.querySelectorAll('tbody tr'));
                        for (const tr of trs) {
                            const tds = Array.from(tr.querySelectorAll('td'));
                                const playerCell = tds.length >= 8 ? tds[1] : tds[0];
                                const headerLines = playerCell.innerText.trim().split('\\n');
                                const name = headerLines[0] || '';

                                const subLine = headerLines[1] || '';
                                const xMins = headerLines[2] || '';
                                
                                const price = tds.length >= 8 ? tds[2].innerText.trim() : (tds[1] ? tds[1].innerText.trim() : '');
                                const gw1 = tds.length >= 8 ? tds[3].innerText.trim() : (tds[2] ? tds[2].innerText.trim() : '');
                                const gw2 = tds.length >= 8 ? tds[4].innerText.trim() : (tds[3] ? tds[3].innerText.trim() : '');
                                const gw3 = tds.length >= 8 ? tds[5].innerText.trim() : (tds[4] ? tds[4].innerText.trim() : '');
                                const gw4 = tds.length >= 8 ? tds[6].innerText.trim() : (tds[5] ? tds[5].innerText.trim() : '');
                                const total = tds.length >= 8 ? tds[7].innerText.trim() : (tds[6] ? tds[6].innerText.trim() : '');
                                
                                if (name && !results.has(name)) {
                                    results.set(name, {
                                        name,
                                        subLine,
                                        xMins,
                                        price,
                                        gw1,
                                        gw2,
                                        gw3,
                                        gw4,
                                        total
                                    });
                                }

                        }

                        if (container) {
                            container.scrollTop += 700;
                            await new Promise(r => setTimeout(r, 150));
                            if (container.scrollTop === lastScroll) break;
                            lastScroll = container.scrollTop;
                        } else {
                            break;
                        }
                    }
                    return Array.from(results.values());
                }""")

                await browser.close()
                logger.success(f"FPL Review web arayüzünden {len(scraped_raw)} oyuncu başarıyla kazındı.")

        except Exception as e:
            logger.error(f"FPL Review web kazıma sırasında hata oluştu: {e}")
            return []

        return scraped_raw

    def match_and_build_dataframe(
        self,
        scraped_data: List[Dict[str, Any]],
        bootstrap_elements: List[Any],
        bootstrap_teams: List[Any]
    ) -> pd.DataFrame:
        """
        Defensively matches scraped player rows with official FPL elements to eliminate identity errors.
        """
        teams_by_id = {t.id: t.short_name for t in bootstrap_teams}
        teams_by_short = {t.short_name.upper(): t.id for t in bootstrap_teams}

        # Index FPL players by team_id
        fpl_by_team: Dict[int, List[Any]] = {t.id: [] for t in bootstrap_teams}
        for p in bootstrap_elements:
            fpl_by_team[p.team].append(p)

        matched_records: List[Dict[str, Any]] = []

        for item in scraped_data:
            raw_name = item.get("name", "").strip()
            sub_line = item.get("subLine", "")
            
            # Parse Team and Pos from subLine (e.g. "MUN • MID" or "MUN - MID")
            team_code = None
            pos_code = None
            parts = re.split(r'[\s•\-\|]+', sub_line.strip())
            for part in parts:
                clean_part = part.strip().upper()
                if clean_part in teams_by_short:
                    team_code = clean_part
                elif clean_part in POS_STR_TO_INT:
                    pos_code = clean_part

            team_id = teams_by_short.get(team_code) if team_code else None

            # Find candidate players
            candidates = fpl_by_team.get(team_id, bootstrap_elements) if team_id else bootstrap_elements
            if pos_code:
                expected_pos_int = POS_STR_TO_INT.get(pos_code)
                candidates = [c for c in candidates if c.element_type == expected_pos_int]

            best_match = None
            highest_score = -1

            for cand in candidates:
                # 1. Exact web_name match
                if cand.web_name.lower() == raw_name.lower():
                    best_match = cand
                    break
                
                # 2. Match with fuzz on web_name
                score = fuzz.token_sort_ratio(raw_name.lower(), cand.web_name.lower())
                if score > highest_score:
                    highest_score = score
                    best_match = cand

            if best_match and (highest_score >= 60 or best_match.web_name.lower() == raw_name.lower()):

                # Parse numeric projections
                def _to_float(val: Any, default: float = 0.0) -> float:
                    try:
                        clean = str(val).replace("£", "").replace("m", "").replace("%", "").strip()
                        return float(clean)
                    except (ValueError, TypeError):
                        return default

                gw1_pts = _to_float(item.get("gw1"))
                gw2_pts = _to_float(item.get("gw2"))
                gw3_pts = _to_float(item.get("gw3"))
                gw4_pts = _to_float(item.get("gw4"))
                xmins_val = _to_float(item.get("xMins"), default=85.0)

                matched_records.append({
                    "id": best_match.id,
                    "name": best_match.web_name,
                    "pos": POS_NAMES.get(best_match.element_type, "M"),
                    "team": teams_by_id.get(best_match.team, "FPL"),
                    "team_id": best_match.team,
                    "buy_price": best_match.now_cost / 10.0,
                    "sell_price": best_match.now_cost / 10.0,
                    "1_Pts": gw1_pts,
                    "2_Pts": gw2_pts,
                    "3_Pts": gw3_pts,
                    "4_Pts": gw4_pts,
                    "1_xMins": xmins_val,
                    "2_xMins": xmins_val,
                    "3_xMins": xmins_val,
                    "4_xMins": xmins_val,
                    "is_fplreview_scraped": True
                })

        df = pd.DataFrame(matched_records)
        logger.info(f"FPL resmi kimlikleriyle eşleşen oyuncu sayısı: {len(df)}")
        return df


async def generate_hybrid_fplreview_csv(output_path: Optional[Path] = None, horizon_gws: int = 8) -> Path:
    """
    Main Orchestrator:
    1. Scrapes all available live players from FPL Review web.
    2. Matches them with FPL API identities.
    3. Fills all remaining 550+ players and GW5-GW8 projections using our built-in Poisson/Elo engine.
    4. Exports a complete, unified `data/fplreview.csv`.
    """
    if output_path is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DATA_DIR / "fplreview.csv"

    # Step 1: Generate built-in full baseline projections (600+ players, full horizon)
    from core.solver.projection_generator import generate_builtin_projections
    builtin_csv = generate_builtin_projections(horizon_gws=horizon_gws)
    df_baseline = pd.read_csv(builtin_csv)
    logger.info(f"Yerleşik matematiksel temel oluşturuldu ({len(df_baseline)} oyuncu).")

    # Step 2: Scrape live FPL Review players
    scraper = FPLReviewLiveScraper()
    raw_scraped = await scraper.scrape_projections()

    if raw_scraped:
        auth_mgr = AuthManager()
        fpl_client = FPLClient(auth_manager=auth_mgr)
        bootstrap = await fpl_client.get_bootstrap_static()

        df_scraped = scraper.match_and_build_dataframe(
            raw_scraped, bootstrap.elements, bootstrap.teams
        )

        if not df_scraped.empty:
            # Step 3: Merge FPL Review projections on top of baseline
            logger.info("FPL Review canlı verileri yerleşik modelle birleştiriliyor...")
            scraped_lookup = {row["id"]: row for _, row in df_scraped.iterrows()}

            for idx, row in df_baseline.iterrows():
                p_id = row.get("id") or row.get("ID")
                if p_id in scraped_lookup:
                    rev_data = scraped_lookup[p_id]
                    # Override GW1-GW4 with scraped FPL Review values
                    for gw in range(1, 5):
                        pts_col = f"{gw}_Pts"
                        mins_col = f"{gw}_xMins"
                        if pts_col in rev_data and rev_data[pts_col] > 0:
                            df_baseline.at[idx, pts_col] = rev_data[pts_col]
                        if mins_col in rev_data and rev_data[mins_col] > 0:
                            df_baseline.at[idx, mins_col] = rev_data[mins_col]

            logger.success(f"Hibrit FPL Review CSV başarıyla harmanlandı ({len(df_scraped)} FPL Review oyuncusu güncellendi).")

    # Save to target CSV and local repo data dir
    df_baseline.to_csv(output_path, index=False, encoding="utf-8")
    repo_data_csv = BASE_DIR / "data" / "fplreview.csv"
    try:
        repo_data_csv.parent.mkdir(parents=True, exist_ok=True)
        df_baseline.to_csv(repo_data_csv, index=False, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Repo data dizinine kopyalanamadı: {e}")

    logger.success(f"Final Hibrit Projeksiyon CSV kaydedildi: {output_path} ve {repo_data_csv}")
    return output_path



if __name__ == "__main__":
    asyncio.run(generate_hybrid_fplreview_csv())
