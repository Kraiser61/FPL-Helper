import os
import httpx
from typing import Optional, Dict
from utils.logger import app_logger
from config import LOGIN_URL, HEADERS
import keyring
from keyring.errors import KeyringError

class AuthManager:
    """
    Manages authentication with the Fantasy Premier League API.
    Supports traditional email/password login, Session Cookies, and Bearer Tokens (Authorization headers).
    """
    
    def __init__(self):
        self._cookies: Dict[str, str] = {}
        self._custom_headers: Dict[str, str] = {}
        self._email: Optional[str] = None
        self._password: Optional[str] = None
        
        # Priority 1: Environment Variables (e.g. CI/CD GitHub Actions Secrets)
        env_email = os.environ.get("FPL_EMAIL")
        env_password = os.environ.get("FPL_PASSWORD")
        env_token = os.environ.get("FPL_AUTH_TOKEN")
        if env_email and env_password:
            self.set_credentials(env_email, env_password)
            app_logger.info("Loaded FPL credentials from environment variables.")
        if env_token:
            self.set_auth_token(env_token)
            app_logger.info("Loaded FPL auth token from environment variables.")

        # Priority 2: Keyring / Disk cache
        if not self._email or not self._password:
            saved_email = self._safe_get_password("fpl_email")
            saved_password = self._safe_get_password("fpl_password")
            if saved_email and saved_password:
                self.set_credentials(saved_email, saved_password)

        if not self._custom_headers and not self._cookies:
            saved_auth = self._safe_get_password("fpl_auth_token") or self._load_token_from_disk()
            if saved_auth:
                self.set_auth_token(saved_auth)

    @staticmethod
    def _safe_get_password(username: str) -> Optional[str]:
        try:
            return keyring.get_password("FPL_Manager", username)
        except (KeyringError, RuntimeError) as exc:
            app_logger.warning(f"Secure credential store unavailable; continuing without saved {username}: {exc}")
            return None
    
    def set_credentials(self, email: str, password: str) -> None:
        """Sets the credentials to be used for authentication."""
        self._email = email
        self._password = password

    def set_auth_token(self, token_or_cookie: str) -> None:
        """
        Intelligently parses and supports direct pasting of:
        - Full cURL commands (e.g. `curl '...' -H 'X-API-Authorization: Bearer eyJ...'`)
        - Full HTTP Header blocks (e.g. `Cookie: pl_profile=...; ...`)
        - Bearer Tokens ("Bearer eyJ...")
        - Raw Cookie Strings ("pl_profile=...; sessionid=...")
        """
        if not token_or_cookie:
            return
            
        token_str = token_or_cookie.strip()
        import re
        
        # 1. If it contains a JWT token (Bearer eyJ...)
        jwt_match = re.search(r'(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', token_str)
        if jwt_match:
            jwt = jwt_match.group(1).strip()
            self._custom_headers["Authorization"] = f"Bearer {jwt}"
            self._custom_headers["X-Api-Authorization"] = f"Bearer {jwt}"
            app_logger.info("Bearer Authorization JWT token extracted and set directly.")
            self._save_token_to_disk(f"Bearer {jwt}")
            return

        # 2. If it's a cURL command with Cookie, extract -H 'cookie: ...'
        if "curl" in token_str.lower():
            cookie_match = re.search(r"-H\s+['\"]cookie:\s*([^'\"]+)['\"]", token_str, re.IGNORECASE)
            if cookie_match:
                token_str = cookie_match.group(1).strip()

        # 3. If it has "Cookie:" or "cookie:" prefix
        if token_str.lower().startswith("cookie:"):
            token_str = token_str.split(":", 1)[1].strip()

        cookie_dict = {}
        if "=" in token_str:
            parts = token_str.split(";")
            for part in parts:
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookie_dict[k.strip()] = v.strip()
        else:
            cookie_dict['pl_profile'] = token_str
            
        self._cookies.update(cookie_dict)
        self._custom_headers["Cookie"] = token_str
        app_logger.info(f"Custom Cookie headers set ({len(cookie_dict)} cookies parsed).")
        self._save_token_to_disk(token_str)

    def _save_token_to_disk(self, token_val: str) -> None:
        try:
            from config import APPDATA_DIR
            token_file = APPDATA_DIR / "auth_token.dat"
            token_file.write_text(token_val, encoding="utf-8")
        except Exception as e:
            app_logger.warning(f"Could not write auth_token.dat: {e}")

    def _load_token_from_disk(self) -> Optional[str]:
        try:
            from config import APPDATA_DIR
            token_file = APPDATA_DIR / "auth_token.dat"
            if token_file.exists():
                return token_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            app_logger.warning(f"Could not read auth_token.dat: {e}")
        return None
        
    def get_cookies(self) -> Dict[str, str]:
        """Returns the current session cookies."""
        return self._cookies

    def get_auth_headers(self) -> Dict[str, str]:
        """Returns additional custom headers for authenticated API requests."""
        return self._custom_headers
        
    def is_authenticated(self) -> bool:
        """Checks if valid session cookies, credentials or Bearer tokens are present."""
        return bool(self._cookies or "Authorization" in self._custom_headers or "Cookie" in self._custom_headers or (self._email and self._password))

    async def login(self) -> bool:
        """
        Authenticates with the FPL server using stored credentials or existing tokens.
        """
        if self._cookies or "Authorization" in self._custom_headers:
            return True
            
        if not self._email or not self._password:
            app_logger.error("Authentication failed: Credentials, Tokens or Cookies not set.")
            return False

        payload = {
            "login": self._email,
            "password": self._password,
            "app": "plfpl-web",
            "redirect_uri": "https://fantasy.premierleague.com/a/login"
        }

        app_logger.info(f"Attempting to authenticate user: {self._email}")

        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=False) as client:
                response = await client.post(
                    LOGIN_URL, 
                    data=payload, 
                    timeout=10.0
                )
                
                if response.status_code in (200, 302):
                    cookies = response.cookies
                    if 'pl_profile' in cookies or 'pl_session' in cookies:
                        self._cookies = {k: v for k, v in cookies.items()}
                        app_logger.info("Authentication successful. Cookies stored.")
                        return True
                    else:
                        app_logger.error("Authentication failed: Cookies not found in response.")
                        return False
                else:
                    app_logger.error(f"Authentication failed with status code: {response.status_code}")
                    return False

        except httpx.RequestError as e:
            app_logger.exception(f"An error occurred while requesting {e.request.url!r}.")
            return False
        except Exception as e:
             app_logger.exception("An unexpected error occurred during login.")
             return False

    def clear_session(self) -> None:
        """Clears all in-memory and saved credentials and cookies."""
        self._cookies.clear()
        self._custom_headers.clear()
        self._email = None
        self._password = None
        try:
            keyring.delete_password("FPL_Manager", "fpl_auth_token")
        except Exception:
            pass
        try:
            keyring.delete_password("FPL_Manager", "fpl_email")
        except Exception:
            pass
        try:
            keyring.delete_password("FPL_Manager", "fpl_password")
        except Exception:
            pass
        app_logger.info("FPL session and credentials cleared.")

    async def fetch_user_profile(self) -> Optional[Dict]:
        """Fetches profile details (including Manager ID) from /api/me/."""
        if not self.is_authenticated():
            return None
        try:
            headers = self.get_auth_headers()
            cookies = self.get_cookies()
            async with httpx.AsyncClient(headers=headers, cookies=cookies, timeout=8.0) as client:
                res = await client.get("https://fantasy.premierleague.com/api/me/")
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            app_logger.warning(f"Failed to fetch user profile from /api/me/: {e}")
        return None
