"""
Social gateway clients (Mixpost, Postiz, etc.).

These are thin HTTP wrappers intended to be called from a higher-level orchestrator
that reads jobs from Notion and writes statuses/logs back.
"""

from .types import (
    SocialGatewayError,
    SocialGatewayAuthError,
    SocialGatewayRequestError,
    SocialAccountRef,
    CreatePostRequest,
    CreatePostResult,
)
from .mixpost import MixpostClient, MixpostConfig
from .postiz import PostizClient, PostizConfig

__all__ = [
    "SocialGatewayError",
    "SocialGatewayAuthError",
    "SocialGatewayRequestError",
    "SocialAccountRef",
    "CreatePostRequest",
    "CreatePostResult",
    "MixpostClient",
    "MixpostConfig",
    "PostizClient",
    "PostizConfig",
]

