"""Authentication and session management."""

import json
import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages authentication state and session persistence."""

    def __init__(self, session_file: Optional[str] = None, zipcode: Optional[str] = None) -> None:
        """
        Initialize auth manager.

        Args:
            session_file: Path to session file (default: ~/.sklavenitis_session.json)
            zipcode: Postal code for delivery zone (sets HubID)
        """
        if session_file is None:
            session_file = str(Path.home() / ".sklavenitis_session.json")
        self.session_file = session_file
        self.zipcode = zipcode
        self.cookies: dict[str, str] = {}
        self.is_authenticated = False
        self._load_session()
        self._set_zone_cookie()

    def _load_session(self) -> None:
        """Load saved session from file."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file) as f:
                    data = json.load(f)
                    self.cookies = data.get("cookies", {})
                    self.is_authenticated = bool(self.cookies)
                    if self.is_authenticated:
                        logger.info(f"Loaded existing session from {self.session_file}")
                        return
            except Exception as e:
                logger.warning(f"Could not load session: {e}")

        # Try legacy cookie file for backward compatibility
        legacy_file = str(Path.home() / ".sklavenitis_cookies.json")
        if os.path.exists(legacy_file):
            try:
                with open(legacy_file) as f:
                    self.cookies = json.load(f)
                    self.is_authenticated = bool(self.cookies)
                    if self.is_authenticated:
                        logger.info(f"Loaded cookies from legacy file: {legacy_file}")
                        # Save to new format
                        self.save_session(self.cookies)
            except Exception as e:
                logger.warning(f"Could not load legacy cookies: {e}")

    def save_session(self, cookies: dict[str, str]) -> None:
        """Save session cookies to file."""
        self.cookies = cookies
        self.is_authenticated = bool(cookies)

        try:
            with open(self.session_file, 'w') as f:
                json.dump({"cookies": cookies}, f, indent=2)
            os.chmod(self.session_file, 0o600)  # Secure permissions
            logger.info(f"Session saved to {self.session_file}")
        except Exception as e:
            logger.error(f"Could not save session: {e}")

    def clear_session(self) -> None:
        """Clear session and delete file."""
        self.cookies = {}
        self.is_authenticated = False
        if os.path.exists(self.session_file):
            try:
                os.remove(self.session_file)
                logger.info("Session cleared")
            except Exception as e:
                logger.warning(f"Could not delete session file: {e}")

    def get_cookies(self) -> dict[str, str]:
        """Get current session cookies."""
        return self.cookies

    def _set_zone_cookie(self) -> None:
        """Set Zone cookie based on zipcode/HubID."""
        if not self.zipcode:
            return

        # Map zipcode ranges to HubIDs
        # For now, we'll use the zipcode directly as HubID if it's numeric
        # Users can customize this mapping as needed
        hub_id = self._get_hub_id_from_zipcode(self.zipcode)

        if hub_id:
            zone_value = json.dumps({"ShippingType": 1, "HubID": hub_id})
            self.cookies["Zone"] = zone_value
            logger.info(f"Set Zone cookie for HubID {hub_id} (zipcode: {self.zipcode})")

    def _get_hub_id_from_zipcode(self, zipcode: str) -> Optional[int]:
        """
        Map zipcode to HubID.

        For now, if zipcode is a number, use it as HubID directly.
        Users can extend this method to add custom zipcode->HubID mappings.
        """
        try:
            # If it's already a HubID number, use it directly
            return int(zipcode)
        except ValueError:
            # Could add custom zipcode mappings here, e.g.:
            # zipcode_map = {
            #     "10430": 11141,  # Example mapping
            #     "15231": 11141,  # Example mapping
            #     # ... more mappings
            # }
            # return zipcode_map.get(zipcode)
            logger.warning(f"Could not parse zipcode/HubID: {zipcode}")
            return None

