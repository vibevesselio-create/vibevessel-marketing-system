"""
Adobe Lightroom OAuth Module

Handles secure OAuth 2.0 token exchange and refresh for Adobe Lightroom API.
This module handles the client_secret securely on the server side.

VERSION: 1.0.0
CREATED: 2026-01-18
AUTHOR: Claude Code Agent

SECURITY NOTE:
- client_secret is ONLY used in this Python module
- Never expose client_secret to GAS or client-side code
- Tokens are stored in environment variables or secure storage
"""

import os
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class TokenResponse:
    """OAuth token response."""
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    expires_at: int = field(default=0)

    def __post_init__(self):
        """Calculate expiry timestamp if not set."""
        if self.expires_at == 0:
            # Add 5-minute buffer
            self.expires_at = int(time.time()) + self.expires_in - 300

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return int(time.time()) >= self.expires_at

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
        }


class AdobeLightroomOAuth:
    """
    Adobe Lightroom OAuth 2.0 handler.

    Handles token exchange and refresh with secure client_secret management.

    Usage:
        oauth = AdobeLightroomOAuth(
            client_id="your_client_id",
            client_secret="your_client_secret"  # NEVER expose this
        )

        # Exchange authorization code for tokens
        tokens = oauth.exchange_code(code, redirect_uri)

        # Refresh tokens
        new_tokens = oauth.refresh_token(tokens.refresh_token)
    """

    # Adobe OAuth endpoints
    AUTH_URL = "https://ims-na1.adobelogin.com/ims/authorize/v2"
    TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
    REVOKE_URL = "https://ims-na1.adobelogin.com/ims/revoke"

    # Default scopes for Lightroom API
    DEFAULT_SCOPES = ["openid", "lr_partner_apis", "lr_partner_rendition_apis"]

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        scopes: Optional[list[str]] = None,
    ):
        """
        Initialize OAuth handler.

        Args:
            client_id: Adobe OAuth client ID (env: ADOBE_CLIENT_ID)
            client_secret: Adobe OAuth client secret (env: ADOBE_CLIENT_SECRET)
            scopes: OAuth scopes (default: Lightroom API scopes)
        """
        self.client_id = client_id or os.environ.get("ADOBE_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("ADOBE_CLIENT_SECRET")
        self.scopes = scopes or self.DEFAULT_SCOPES

        if not self.client_id:
            raise ValueError("client_id is required (or set ADOBE_CLIENT_ID env var)")
        if not self.client_secret:
            raise ValueError("client_secret is required (or set ADOBE_CLIENT_SECRET env var)")

        self._http_client = httpx.Client(timeout=30.0)

    def __del__(self):
        """Cleanup HTTP client."""
        if hasattr(self, "_http_client"):
            self._http_client.close()

    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: OAuth redirect URI
            state: CSRF protection state parameter

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": ",".join(self.scopes),
            "response_type": "code",
        }
        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query}"

    def exchange_code(self, code: str, redirect_uri: str) -> TokenResponse:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Redirect URI used in authorization

        Returns:
            TokenResponse with access and refresh tokens

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        logger.info("Exchanging authorization code for tokens")

        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        response = self._http_client.post(
            self.TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        data = response.json()
        logger.info("Token exchange successful")

        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data.get("expires_in", 3600),
            token_type=data.get("token_type", "bearer"),
        )

    def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Refresh access token.

        Args:
            refresh_token: Refresh token from previous token response

        Returns:
            TokenResponse with new access and refresh tokens

        Raises:
            httpx.HTTPStatusError: If token refresh fails
        """
        logger.info("Refreshing access token")

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        response = self._http_client.post(
            self.TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        data = response.json()
        logger.info("Token refresh successful")

        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in", 3600),
            token_type=data.get("token_type", "bearer"),
        )

    def revoke_token(self, token: str, token_type: str = "access_token") -> bool:
        """
        Revoke a token.

        Args:
            token: Token to revoke
            token_type: Type of token ("access_token" or "refresh_token")

        Returns:
            True if revocation successful
        """
        logger.info(f"Revoking {token_type}")

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token": token,
            "token_type_hint": token_type,
        }

        try:
            response = self._http_client.post(
                self.REVOKE_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            logger.info("Token revoked successfully")
            return True
        except httpx.HTTPStatusError as e:
            logger.warning(f"Token revocation failed: {e}")
            return False

    def validate_token(self, access_token: str) -> bool:
        """
        Validate an access token by making a test API call.

        Args:
            access_token: Token to validate

        Returns:
            True if token is valid
        """
        try:
            response = self._http_client.get(
                "https://lr.adobe.io/v2/account",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-API-Key": self.client_id,
                },
            )
            return response.status_code == 200
        except Exception:
            return False


# FastAPI/Flask integration helper
def create_token_exchange_endpoint(oauth: AdobeLightroomOAuth):
    """
    Create a token exchange endpoint handler.

    Usage with FastAPI:
        oauth = AdobeLightroomOAuth()
        exchange_handler = create_token_exchange_endpoint(oauth)

        @app.post("/api/adobe/token")
        async def exchange_token(request: TokenExchangeRequest):
            return exchange_handler(request.code, request.redirect_uri, request.client_id)
    """
    def handler(code: str, redirect_uri: str, client_id: str) -> dict:
        # Validate client_id matches
        if client_id != oauth.client_id:
            raise ValueError("Invalid client_id")

        tokens = oauth.exchange_code(code, redirect_uri)
        return tokens.to_dict()

    return handler


def create_token_refresh_endpoint(oauth: AdobeLightroomOAuth):
    """
    Create a token refresh endpoint handler.

    Usage with FastAPI:
        oauth = AdobeLightroomOAuth()
        refresh_handler = create_token_refresh_endpoint(oauth)

        @app.post("/api/adobe/refresh")
        async def refresh_token(request: TokenRefreshRequest):
            return refresh_handler(request.refresh_token, request.client_id)
    """
    def handler(refresh_token: str, client_id: str) -> dict:
        # Validate client_id matches
        if client_id != oauth.client_id:
            raise ValueError("Invalid client_id")

        tokens = oauth.refresh_token(refresh_token)
        return tokens.to_dict()

    return handler
