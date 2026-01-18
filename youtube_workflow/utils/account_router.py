"""Google account routing for YouTube workflow.

Routes API requests to the correct Google account based on service type
and configured preferences. Aligns with the unified configuration system.
"""

import logging
import os
import pickle
from pathlib import Path
from typing import Optional

from youtube_workflow.utils.errors import AccountRoutingError, AuthenticationError

logger = logging.getLogger(__name__)


# Account configuration
ACCOUNTS = {
    "brian@serenmedia.co": {
        "project_id": "seventh-atom-435416-u5",
        "services": ["youtube_api", "apps_script", "drive_admin"],
        "priority": 1,  # Primary account for API operations
    },
    "vibe.vessel.io@gmail.com": {
        "project_id": None,  # Legacy OAuth
        "services": ["drive_storage", "photos"],
        "priority": 2,  # Secondary account for storage
    },
}

# Service to account mapping
SERVICE_ACCOUNT_MAP = {
    "youtube_api": "brian@serenmedia.co",
    "youtube_search": "brian@serenmedia.co",
    "youtube_download": None,  # No account needed (yt-dlp)
    "drive_storage": "vibe.vessel.io@gmail.com",
    "apps_script": "brian@serenmedia.co",
}


class GoogleAccountRouter:
    """Routes requests to appropriate Google account.

    Uses email-based token files following the pattern:
    google_oauth_token_{safe_email}.pickle
    """

    def __init__(self, token_dir: Optional[Path] = None):
        """Initialize the account router.

        Args:
            token_dir: Directory containing OAuth token files.
                       Defaults to GOOGLE_OAUTH_TOKEN_DIR env var.
        """
        self.token_dir = token_dir or Path(
            os.getenv(
                "GOOGLE_OAUTH_TOKEN_DIR",
                Path.home() / ".credentials" / "google-oauth"
            )
        )

    def get_account_for_service(self, service: str) -> Optional[str]:
        """Get the appropriate account email for a service.

        Args:
            service: Service identifier (e.g., "youtube_api")

        Returns:
            Email address of account to use, or None if no account needed
        """
        return SERVICE_ACCOUNT_MAP.get(service)

    def get_credentials(self, email: Optional[str] = None, service: str = None):
        """Load OAuth credentials for an account.

        Args:
            email: Specific email to load credentials for
            service: Service to route to appropriate account

        Returns:
            Google OAuth credentials object

        Raises:
            AccountRoutingError: If account cannot be determined
            AuthenticationError: If credentials cannot be loaded
        """
        # Determine which account to use
        if not email and service:
            email = self.get_account_for_service(service)

        if not email:
            raise AccountRoutingError(
                "Cannot determine account: provide email or service",
                requested_account=service
            )

        # Load token file
        safe_email = email.replace("@", "_at_").replace(".", "_")
        token_filename = f"google_oauth_token_{safe_email}.pickle"
        token_path = self.token_dir / token_filename

        if not token_path.exists():
            raise AuthenticationError(
                f"Token file not found for {email}",
                account=email
            )

        try:
            with open(token_path, "rb") as f:
                credentials = pickle.load(f)

            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
                self._save_credentials(credentials, email)

            logger.info(f"Loaded credentials for {email}")
            return credentials

        except Exception as e:
            raise AuthenticationError(
                f"Failed to load credentials for {email}: {e}",
                account=email
            )

    def _save_credentials(self, credentials, email: str) -> None:
        """Save refreshed credentials back to token file."""
        safe_email = email.replace("@", "_at_").replace(".", "_")
        token_filename = f"google_oauth_token_{safe_email}.pickle"
        token_path = self.token_dir / token_filename

        try:
            with open(token_path, "wb") as f:
                pickle.dump(credentials, f)
            logger.debug(f"Saved refreshed credentials for {email}")
        except Exception as e:
            logger.warning(f"Failed to save refreshed credentials: {e}")

    def list_available_accounts(self) -> list:
        """List accounts with available token files.

        Returns:
            List of email addresses with valid token files
        """
        accounts = []

        if not self.token_dir.exists():
            return accounts

        for token_file in self.token_dir.glob("google_oauth_token_*.pickle"):
            # Extract email from filename
            name = token_file.stem.replace("google_oauth_token_", "")
            email = name.replace("_at_", "@").replace("_", ".")
            accounts.append(email)

        return accounts


def get_youtube_credentials():
    """Get credentials for YouTube API operations.

    Convenience function that routes to the correct account.

    Returns:
        Google OAuth credentials for YouTube API
    """
    router = GoogleAccountRouter()
    return router.get_credentials(service="youtube_api")
