# -*- coding: utf-8 -*-
import asyncio
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import requests
from loguru import logger

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import BASE_URL, DEFAULT_MANAGER_ID, USER_AGENT
from core.solver.paths import DATA_DIR
from ingestion.auth_manager import AuthManager
from ingestion.fpl_client import FPLClient


class FPLFormClient:
    EXPORT_URL = 'https://fplform.com/export-fpl-form-data.php'

    def __init__(self):
        self.fpl_client = FPLClient(auth_manager=AuthManager())

    async def fetch_and_generate_csv(
        self,
        output_path: Optional[Path] = None,
        first_gw: Optional[int] = None,
        last_gw: Optional[int] = None,
        horizon_gws: int = 8,
        force_refresh: bool = True
    ) -> Path:
        if output_path is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            output_path = DATA_DIR / 'fplform.csv'

        repo_fplform_path = BASE_DIR / 'data' / 'fplform.csv'
        appdata_fplform_path = DATA_DIR / 'fplform.csv'

        # 1. Fetch live official FPL elements and teams
        bootstrap = await self.fpl_client.get_bootstrap_static()
        elements_map = {e.id: e for e in bootstrap.elements}
        teams_map = {t.id: t.name for t in bootstrap.teams}

        # Dynamically determine GW range if not explicitly provided
        current_event = next((e for e in bootstrap.events if e.is_current), None)
        next_event = next((e for e in bootstrap.events if e.is_next), None)
        active_gw = next_event.id if next_event else (current_event.id if current_event else 1)

        if first_gw is None:
            first_gw = 1
        if last_gw is None:
            last_gw = min(38, max(active_gw + horizon_gws + 4, 12))

        logger.info(f'Fetching live projections from fplform.com (GW{first_gw} - GW{last_gw})...')

        # 2. Fetch CSV from fplform.com
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Referer': 'https://fplform.com/export-fpl-form-data',
        }
        payload = {
            'firstgw': str(first_gw),
            'lastgw': str(last_gw),
            'all': '1',
            'submit': 'submit',
        }

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(self.EXPORT_URL, data=payload, headers=headers, timeout=20.0)
        )
        resp.raise_for_status()

        # 3. Parse CSV
        df_raw = pd.read_csv(io.StringIO(resp.text))
        logger.info(f'Successfully downloaded {len(df_raw)} players from fplform.com')

        pos_map = {'GK': 'G', 'GKP': 'G', 'DEF': 'D', 'MID': 'M', 'FWD': 'F'}

        records: List[Dict[str, Any]] = []
        for _, row in df_raw.iterrows():
            p_id = int(row['ID'])
            fpl_elem = elements_map.get(p_id)
            
            is_unavailable = False
            if fpl_elem:
                status = getattr(fpl_elem, 'status', 'a')
                if status in ('u', 'n'):
                    is_unavailable = True

            web_name = fpl_elem.web_name if fpl_elem else str(row.get('Name', ''))
            team_id = fpl_elem.team if fpl_elem else 1
            team_name = teams_map.get(team_id, str(row.get('Team', '')))
            pos_str = pos_map.get(str(row.get('Pos', '')).upper(), 'M')
            price_val = float(row.get('Price', (fpl_elem.now_cost / 10.0) if fpl_elem else 5.0))

            rec: Dict[str, Any] = {
                'ID': p_id,
                'Name': web_name,
                'Pos': pos_str,
                'Value': price_val,
                'Team': team_name,
            }

            for gw in range(first_gw, last_gw + 1):
                prob_val = float(row.get(f'{gw}_prob', 0.85)) if not is_unavailable else 0.0
                pts_val = float(row.get(f'{gw}_with_prob', row.get(f'{gw}_pts', 0.0))) if not is_unavailable else 0.0
                xmins_val = int(round(prob_val * 90.0)) if not is_unavailable else 0

                rec[f'{gw}_Pts'] = round(pts_val, 2)
                rec[f'{gw}_xMins'] = xmins_val

            records.append(rec)

        df_clean = pd.DataFrame(records)

        # 4. Save standardized CSV files
        df_clean.to_csv(output_path, index=False, encoding='utf-8')
        df_clean.to_csv(repo_fplform_path, index=False, encoding='utf-8')
        df_clean.to_csv(appdata_fplform_path, index=False, encoding='utf-8')

        # 5. Write metadata
        meta = {
            'is_valid': True,
            'filename': 'fplform.csv',
            'original_name': 'fplform_export.csv',
            'file_path': str(output_path),
            'player_count': len(df_clean),
            'gameweeks': list(range(first_gw, last_gw + 1)),
            'gw_range_str': f'GW{first_gw} - GW{last_gw}',
            'updated_at': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            'size_kb': round(output_path.stat().st_size / 1024, 1),
            'source': 'fplform.com',
        }
        with open(DATA_DIR / 'projection_meta.json', 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        logger.success(f'Saved FPL Form standardized CSV ({len(df_clean)} players): {output_path}')
        return output_path


async def generate_fplform_csv(
    output_path: Optional[Path] = None,
    horizon_gws: int = 8,
    first_gw: Optional[int] = None,
    last_gw: Optional[int] = None
) -> Path:
    client = FPLFormClient()
    return await client.fetch_and_generate_csv(
        output_path=output_path,
        first_gw=first_gw,
        last_gw=last_gw,
        horizon_gws=horizon_gws
    )


if __name__ == '__main__':
    asyncio.run(generate_fplform_csv())
