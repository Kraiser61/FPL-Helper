import asyncio
import httpx
from typing import Dict, Any, List, Optional
from httpx import HTTPStatusError, RequestError

from config import ENDPOINTS, HEADERS, HTTP_TIMEOUT, MAX_RETRIES, RATE_LIMIT_DELAY
from data.models import (
    BootstrapStaticDTO, 
    FixtureDTO, 
    UserPickDTO, 
    UserTeamDTO, 
    LiveGWDataDTO
)
from ingestion.auth_manager import AuthManager
from ingestion.cache_manager import CacheManager
from utils.logger import app_logger

def parse_raw_text_to_team_data(raw_text: str, elements: list) -> dict:
    import re
    from fuzzywuzzy import fuzz

    clean_raw = raw_text.strip()
    if clean_raw.lower().startswith("/kadro"):
        clean_raw = clean_raw[6:].strip()

    tokens = re.split(r'[\n\r,;]+', clean_raw)
    tokens = [t.strip() for t in tokens if t.strip()]

    found_players = []
    found_ids = set()
    pos_limits = {1: 2, 2: 5, 3: 5, 4: 3}
    pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    # Pass 1: exact web_name matches
    for token in tokens:
        clean = re.sub(r'[^a-zA-Z0-9\s\.\-]', '', token).strip()
        if not clean or len(clean) < 2:
            continue
        for p in elements:
            if p.id in found_ids or pos_counts[p.element_type] >= pos_limits[p.element_type]:
                continue
            if p.web_name.lower() == clean.lower():
                found_players.append(p)
                found_ids.add(p.id)
                pos_counts[p.element_type] += 1
                break

    # Pass 2: fuzzy match
    if len(found_players) < 15:
        for token in tokens:
            clean = re.sub(r'[^a-zA-Z0-9\s\.\-]', '', token).strip()
            if not clean or len(clean) < 2:
                continue
            for p in elements:
                if p.id in found_ids or pos_counts[p.element_type] >= pos_limits[p.element_type]:
                    continue
                if fuzz.token_sort_ratio(clean.lower(), p.web_name.lower()) >= 80:
                    found_players.append(p)
                    found_ids.add(p.id)
                    pos_counts[p.element_type] += 1
                    break
            if len(found_players) == 15:
                break

    found_players.sort(key=lambda x: x.element_type)
    picks = [{"element": p.id, "position": idx, "is_captain": idx == 8, "is_vice_captain": idx == 9} for idx, p in enumerate(found_players, 1)]
    return {"picks": picks, "chips": [], "transfers": {"bank": 0, "limit": 1, "made": 0}}

class FPLClient:
    """
    Async HTTP client for interacting with the Fantasy Premier League API.
    Includes rate limiting, exponential backoff retries, and graceful degradation via CacheManager.
    """

    def __init__(self, auth_manager: Optional[AuthManager] = None):
        self.auth_manager = auth_manager or AuthManager()
        self.headers = HEADERS.copy()
        
    async def _request(self, method: str, url: str, authenticated: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Internal method to execute HTTP requests with retries, rate limiting, and fallback to cache on error.
        """
        request_headers = self.headers.copy()
        
        if authenticated:
            if not self.auth_manager.is_authenticated():
                app_logger.warning("Authentication required for endpoint. Attempting login...")
                success = await self.auth_manager.login()
                if not success:
                    app_logger.warning(f"Authentication failed for {url}. Raising PermissionError without serving stale authenticated cache.")
                    raise PermissionError("FPL hesabına giriş yapılmadı. Lütfen Ayarlar menüsünden FPL hesabınızla giriş yapın.")
            
            request_headers.update(self.auth_manager.get_auth_headers())

        client_kwargs = {
            "headers": request_headers,
            "timeout": HTTP_TIMEOUT,
            **kwargs
        }

        if authenticated and self.auth_manager.get_cookies():
            client_kwargs["cookies"] = self.auth_manager.get_cookies()

        async with httpx.AsyncClient(**client_kwargs) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    app_logger.debug(f"Requesting (Attempt {attempt + 1}/{MAX_RETRIES}): {method} {url}")
                    response = await client.request(method, url)
                    response.raise_for_status()
                    
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    data = response.json()
                    
                    CacheManager.save_cached_response(url, data, ttl_seconds=14400)
                    return data
                    
                except HTTPStatusError as e:
                    if e.response.status_code == 429:
                        app_logger.warning(f"Rate limited (429) on {url}. Retrying...")
                    elif e.response.status_code in (401, 403):
                        app_logger.error(f"Unauthorized/Forbidden ({e.response.status_code}) on {url}.")
                        if authenticated:
                            raise PermissionError("FPL oturumu geçersiz veya süresi dolmuş. Lütfen Ayarlar kısmından tekrar giriş yapın.")
                        break
                    elif e.response.status_code == 404:
                        app_logger.warning(f"Resource not found (404) for {url}. (Pre-season or invalid event).")
                        break
                    else:
                        app_logger.error(f"HTTP Error {e.response.status_code} for {url}")
                        
                except RequestError as e:
                    app_logger.error(f"Request error while accessing {url}: {e}")

                wait_time = (2 ** attempt) + RATE_LIMIT_DELAY
                app_logger.info(f"Waiting {wait_time} seconds before retrying...")
                await asyncio.sleep(wait_time)

            if not authenticated:
                cached = CacheManager.get_cached_response(url)
                if cached:
                    app_logger.warning(f"Returning cached data for {url}")
                    return cached
                
            raise ConnectionError(f"Failed to fetch data from {url} after {MAX_RETRIES} attempts.")

    async def get_bootstrap_static(self) -> BootstrapStaticDTO:
        """Fetches the master data snapshot."""
        url = ENDPOINTS["bootstrap"]
        app_logger.info("Fetching bootstrap-static data...")
        data = await self._request("GET", url)
        return BootstrapStaticDTO(**data)

    async def get_manager_info(self, manager_id: int) -> Dict[str, Any]:
        """Fetches general profile info for a given manager ID."""
        url = ENDPOINTS["manager_info"].format(manager_id=manager_id)
        app_logger.info(f"Fetching manager info for ID {manager_id}...")
        return await self._request("GET", url)

    async def get_manager_history(self, manager_id: int) -> Dict[str, Any]:
        """Fetches historical performance data for a given manager ID."""
        url = ENDPOINTS["manager_history"].format(manager_id=manager_id)
        app_logger.info(f"Fetching manager history for ID {manager_id}...")
        return await self._request("GET", url)

    async def get_fixtures(self, event_id: Optional[int] = None) -> List[FixtureDTO]:
        """Fetches fixtures, optionally filtered by a specific gameweek."""
        url = ENDPOINTS["fixtures"]
        if event_id:
            url += f"?event={event_id}"
            app_logger.info(f"Fetching fixtures for GW {event_id}...")
        else:
             app_logger.info("Fetching all fixtures...")
             
        data = await self._request("GET", url)
        if isinstance(data, list):
            return [FixtureDTO(**fixture) for fixture in data]
        return []

    async def get_user_picks(self, manager_id: int, event_id: int) -> UserPickDTO:
        """Fetches a manager's 15-player squad selection for a given GW."""
        url = ENDPOINTS["user_picks"].format(manager_id=manager_id, event_id=event_id)
        app_logger.info(f"Fetching user picks for Manager {manager_id}, GW {event_id}...")
        data = await self._request("GET", url)
        return UserPickDTO(**data)

    async def get_my_team(self, manager_id: int, chat_id: Optional[str] = None) -> UserTeamDTO:
        """Fetches the authenticated manager's current team (requires auth) with fallback to locally synced team."""
        url = ENDPOINTS["my_team"].format(manager_id=manager_id)
        app_logger.info(f"Fetching authenticated team data for Manager {manager_id} (chat_id: {chat_id})...")
        
        from ingestion.local_sync_server import load_synced_team_from_disk, save_synced_team_to_disk
        
        try:
            data = await self._request("GET", url, authenticated=True)
            if data and isinstance(data, dict) and "picks" in data:
                save_synced_team_to_disk({"manager_id": manager_id, "team_data": data}, chat_id=chat_id)
                return UserTeamDTO(**data)
        except Exception as e:
            app_logger.warning(f"Authenticated my-team request failed ({e}). Checking local sync cache...")
            synced = load_synced_team_from_disk(chat_id=chat_id)
            if synced:
                if "team_data" in synced and "picks" in synced["team_data"] and synced["team_data"]["picks"]:
                    app_logger.info(f"Successfully loaded squad from local browser sync cache (chat_id: {chat_id}).")
                    return UserTeamDTO(**synced["team_data"])
                
                # Check if raw_text exists from mobile DOM dump
                raw_text = synced.get("raw_text") or (synced.get("team_data", {}).get("raw_text") if isinstance(synced.get("team_data"), dict) else None)
                if raw_text:
                    app_logger.info("Parsing squad from mobile raw_text DOM dump...")
                    bootstrap = await self.get_bootstrap_static()
                    parsed_td = parse_raw_text_to_team_data(raw_text, bootstrap.elements)
                    if parsed_td and parsed_td.get("picks"):
                        app_logger.info(f"Extracted {len(parsed_td['picks'])} picks from mobile page text.")
                        save_synced_team_to_disk({"manager_id": manager_id, "team_data": parsed_td}, chat_id=chat_id)
                        return UserTeamDTO(**parsed_td)
            raise e
            
        return UserTeamDTO()
        
    async def get_live_gw(self, event_id: int) -> LiveGWDataDTO:
        """Fetches real-time performance data for all players in an active GW."""
        url = ENDPOINTS["event_status"]
        app_logger.info(f"Fetching live data for GW {event_id}...")
        data = await self._request("GET", url)
        return LiveGWDataDTO(**data)
