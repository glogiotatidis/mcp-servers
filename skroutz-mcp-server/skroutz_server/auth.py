"""Authentication manager for skroutz.gr."""

import json
import os
from pathlib import Path
from typing import Optional
import logging

from .models import AuthCredentials, SessionData

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages authentication state and session persistence."""

    def __init__(self, session_file: Optional[str] = None) -> None:
        """
        Initialize the authentication manager.

        Args:
            session_file: Path to store session data. Defaults to ~/.skroutz_session.json
        """
        if session_file is None:
            session_file = str(Path.home() / ".skroutz_session.json")
        self.session_file = session_file
        self.session: SessionData = self._load_session()

        # Load cookies from environment variables
        self._load_cookies_from_env()

    def _load_session(self) -> SessionData:
        """Load session data from file if it exists."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r") as f:
                    data = json.load(f)
                    return SessionData(**data)
            except (json.JSONDecodeError, ValueError):
                # If file is corrupted, start fresh
                pass
        return SessionData()

    def _save_session(self) -> None:
        """Save session data to file."""
        with open(self.session_file, "w") as f:
            json.dump(self.session.model_dump(), f, default=str)
        # Set restrictive permissions on session file
        os.chmod(self.session_file, 0o600)

    def save_session(self, cookies: dict[str, str], user_email: Optional[str] = None) -> None:
        """
        Save authentication session.

        Args:
            cookies: Session cookies from successful login
            user_email: User's email address
        """
        self.session = SessionData(
            cookies=cookies,
            user_email=user_email,
            is_authenticated=True,
        )
        self._save_session()

    def get_session(self) -> SessionData:
        """Get current session data."""
        return self.session

    def clear_session(self) -> None:
        """Clear the current session."""
        self.session = SessionData()
        if os.path.exists(self.session_file):
            os.remove(self.session_file)

    def is_authenticated(self) -> bool:
        """Check if there's an active authenticated session."""
        return self.session.is_authenticated and bool(self.session.cookies)

    def get_cookies(self) -> dict[str, str]:
        """Get session cookies."""
        return self.session.cookies

    def _load_cookies_from_env(self) -> None:
        """
        Load cookies from environment variables.

        Cookie names are based on actual Skroutz.gr cookies (verified from network traffic):
        - _helmet_couch: Main session cookie (required)
        - cf_clearance: Cloudflare clearance token (required)
        - dd: Device/session identifier (required)
        - logged_in: Login status flag (optional, defaults to "true")
        - __zlcmid: Zendesk chat widget ID (optional)

        Environment variable mapping:
        - SKROUTZ_HELMET_COUCH → _helmet_couch
        - SKROUTZ_CF_CLEARANCE → cf_clearance
        - SKROUTZ_DD → dd
        - SKROUTZ_LOGGED_IN → logged_in (optional)
        - SKROUTZ_ZLCMID → __zlcmid (optional)

        Also supports JSON format via SKROUTZ_COOKIES for advanced users.
        """
        cookies = {}

        # Method 1: Individual environment variables (recommended)
        helmet_couch = os.environ.get("SKROUTZ_HELMET_COUCH")
        cf_clearance = os.environ.get("SKROUTZ_CF_CLEARANCE")
        dd = os.environ.get("SKROUTZ_DD")
        logged_in = os.environ.get("SKROUTZ_LOGGED_IN", "true")
        zlcmid = os.environ.get("SKROUTZ_ZLCMID")

        if helmet_couch:
            cookies["_helmet_couch"] = helmet_couch
            logger.info("Loaded _helmet_couch cookie")

        if cf_clearance:
            cookies["cf_clearance"] = cf_clearance
            logger.info("Loaded cf_clearance cookie")

        if dd:
            cookies["dd"] = dd
            logger.info("Loaded dd cookie")

        if logged_in:
            cookies["logged_in"] = logged_in

        if zlcmid:
            cookies["__zlcmid"] = zlcmid
            logger.info("Loaded __zlcmid cookie")

        # Method 2: JSON format (fallback)
        if not cookies:
            cookies_json = os.environ.get("SKROUTZ_COOKIES")
            if cookies_json:
                try:
                    cookies = json.loads(cookies_json)
                    if isinstance(cookies, dict) and cookies:
                        logger.info(f"Loaded {len(cookies)} cookie(s) from SKROUTZ_COOKIES")
                    else:
                        cookies = {}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SKROUTZ_COOKIES: {e}")
                    cookies = {}

        # Update session if cookies were loaded
        if cookies:
            logger.info(f"✓ Loaded {len(cookies)} authentication cookie(s) from environment")
            self.session = SessionData(
                cookies=cookies,
                is_authenticated=True,
            )
            self._save_session()
        else:
            logger.debug("No cookies found in environment variables")
