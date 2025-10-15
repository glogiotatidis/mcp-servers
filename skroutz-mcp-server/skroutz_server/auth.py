"""Authentication manager for skroutz.gr."""

import json
import os
from pathlib import Path
from typing import Optional

from .models import AuthCredentials, SessionData


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
