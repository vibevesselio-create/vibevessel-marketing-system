from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .http import request_json
from .types import CreatePostRequest, CreatePostResult


@dataclass(frozen=True)
class MixpostConfig:
    base_url: str
    access_token: str
    api_prefix: str = "/api"
    timeout_s: float = 30.0


class MixpostClient:
    """
    Minimal Mixpost REST client.

    Notes:
    - The conversation spec references endpoints like:
      - `GET /api/accounts`
      - `POST /api/posts` with `accounts`, `content`, `scheduled_at`
    - Mixpost deployments differ depending on whether the REST API add-on is used.
      Keep `api_prefix` configurable for that reason.
    """

    def __init__(self, config: MixpostConfig):
        self._cfg = config

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._cfg.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_accounts(self) -> List[Dict[str, Any]]:
        resp = request_json(
            method="GET",
            base_url=self._cfg.base_url,
            path=f"{self._cfg.api_prefix}/accounts",
            headers=self._headers(),
            timeout_s=self._cfg.timeout_s,
        )
        # Mixpost may return {data:[...]} or {accounts:[...]} depending on version.
        payload = resp.json or {}
        if "data" in payload and isinstance(payload["data"], list):
            return payload["data"]
        if "accounts" in payload and isinstance(payload["accounts"], list):
            return payload["accounts"]
        if isinstance(payload.get("_json"), list):
            return payload["_json"]  # type: ignore[return-value]
        return []

    def create_post(self, req: CreatePostRequest) -> CreatePostResult:
        body: Dict[str, Any] = {
            "accounts": req.account_ids,
            "content": req.text,
        }

        # Schedule if provided; otherwise create as immediate (provider-specific behavior).
        if req.scheduled_at:
            if not isinstance(req.scheduled_at, datetime):
                raise TypeError("scheduled_at must be a datetime")
            body["scheduled_at"] = req.scheduled_at.isoformat()

        if req.media_urls:
            # Keep provider-agnostic naming; deployments may expect `media`, `media_urls`, etc.
            body["media_urls"] = req.media_urls

        if req.metadata:
            body["metadata"] = req.metadata

        resp = request_json(
            method="POST",
            base_url=self._cfg.base_url,
            path=f"{self._cfg.api_prefix}/posts",
            headers=self._headers(),
            json_body=body,
            timeout_s=self._cfg.timeout_s,
        )
        payload = resp.json or {}

        # Attempt common id locations.
        post_id = (
            payload.get("id")
            or (payload.get("data") or {}).get("id")
            or (payload.get("post") or {}).get("id")
        )
        if not post_id:
            # As a fallback, keep the raw response and throw a stable error upstream.
            raise ValueError(f"Mixpost create_post response missing post id: {payload}")

        post_url = payload.get("url") or (payload.get("data") or {}).get("url")

        return CreatePostResult(provider="mixpost", post_id=str(post_id), post_url=post_url, raw=payload)

    def get_post(self, post_id: str) -> Dict[str, Any]:
        resp = request_json(
            method="GET",
            base_url=self._cfg.base_url,
            path=f"{self._cfg.api_prefix}/posts/{post_id}",
            headers=self._headers(),
            timeout_s=self._cfg.timeout_s,
        )
        return resp.json or {}

