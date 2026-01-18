from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


class SocialGatewayError(RuntimeError):
    """Base error for social gateway operations."""


class SocialGatewayAuthError(SocialGatewayError):
    """Authentication/authorization failure (401/403)."""


class SocialGatewayRequestError(SocialGatewayError):
    """Non-auth request failure (4xx/5xx) or invalid response."""


@dataclass(frozen=True)
class SocialAccountRef:
    """
    Reference to a provider-side account.

    For Mixpost this is typically an account ID returned from `GET /api/accounts`.
    For Postiz the shape/ID may differ; use the provider's account identifier.
    """

    provider: str  # e.g. "mixpost", "postiz"
    account_id: str


@dataclass(frozen=True)
class CreatePostRequest:
    """
    Provider-agnostic "create/schedule a post" request.

    Keep this intentionally small; provider clients can expand/translate as needed.
    """

    text: str
    account_ids: List[str]
    scheduled_at: Optional[datetime] = None
    media_urls: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CreatePostResult:
    provider: str
    post_id: str
    post_url: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

