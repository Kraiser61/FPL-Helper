import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from data.database import db_manager
from utils.logger import app_logger

class CacheManager:
    """
    Manages API Caching using SQLite database tables: `api_cache_meta` and `api_cache_data`.
    Enforces TTL, handles stale fallbacks, and uses deterministic SHA-256 hashes.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def get_cache_meta(endpoint: str) -> Optional[Dict[str, Any]]:
        try:
            query = "SELECT * FROM api_cache_meta WHERE endpoint = ?"
            with db_manager.get_connection() as conn:
                cursor = conn.execute(query, (endpoint,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            app_logger.warning(f"Cache lookup failed for {endpoint}: {e}")
        return None

    @staticmethod
    def update_cache_meta(endpoint: str, ttl_seconds: int, status: str = 'ok', response_hash: Optional[str] = None):
        try:
            query = """
            INSERT INTO api_cache_meta (endpoint, last_fetched, ttl_seconds, response_hash, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                last_fetched = excluded.last_fetched,
                ttl_seconds = excluded.ttl_seconds,
                response_hash = excluded.response_hash,
                status = excluded.status
            """
            now_str = CacheManager._now().isoformat()
            with db_manager.get_connection() as conn:
                conn.execute(query, (endpoint, now_str, ttl_seconds, response_hash, status))
                conn.commit()
        except Exception as e:
            app_logger.warning(f"Cache update failed for {endpoint}: {e}")

    @staticmethod
    def save_cached_response(endpoint: str, data: Dict[str, Any], ttl_seconds: int):
        """Saves a JSON response to the database and updates metadata using deterministic SHA-256."""
        try:
            json_str = json.dumps(data)
            response_hash = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            
            # Update meta FIRST to satisfy Foreign Key constraint in api_cache_data
            CacheManager.update_cache_meta(endpoint, ttl_seconds, status='ok', response_hash=response_hash)
            
            query_data = """
            INSERT INTO api_cache_data (endpoint, json_data)
            VALUES (?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
                json_data = excluded.json_data
            """
            
            with db_manager.get_connection() as conn:
                conn.execute(query_data, (endpoint, json_str))
                conn.commit()
                app_logger.debug(f"Cached response for {endpoint} with TTL {ttl_seconds}s")
        except Exception as e:
            app_logger.warning(f"Failed to cache response data for {endpoint}: {e}")

    @staticmethod
    def get_cached_response(endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached JSON response for an endpoint regardless of TTL (used for graceful degradation).
        """
        query = "SELECT json_data FROM api_cache_data WHERE endpoint = ?"
        with db_manager.get_connection() as conn:
            cursor = conn.execute(query, (endpoint,))
            row = cursor.fetchone()
            if row and row['json_data']:
                try:
                    return json.loads(row['json_data'])
                except Exception as e:
                    app_logger.error(f"Failed to parse cached JSON for {endpoint}: {e}")
        return None

    @staticmethod
    def is_cache_valid(endpoint: str) -> bool:
        """Checks if the cached data for the given endpoint is still within its TTL."""
        meta = CacheManager.get_cache_meta(endpoint)
        if not meta or meta['status'] != 'ok':
            return False
            
        try:
            last_fetched = datetime.fromisoformat(meta['last_fetched'])
            if last_fetched.tzinfo is None:
                last_fetched = last_fetched.replace(tzinfo=timezone.utc)
                
            elapsed = (CacheManager._now() - last_fetched).total_seconds()
            return elapsed < meta['ttl_seconds']
        except Exception as e:
            app_logger.error(f"Error checking cache validity for {endpoint}: {e}")
            return False

    @staticmethod
    def invalidate_cache(endpoint: str):
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM api_cache_data WHERE endpoint = ?", (endpoint,))
            conn.execute("DELETE FROM api_cache_meta WHERE endpoint = ?", (endpoint,))
            conn.commit()
            app_logger.info(f"Invalidated cache for {endpoint}")
