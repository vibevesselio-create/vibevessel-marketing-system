from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .http import request_json
from .types import CreatePostRequest, CreatePostResult


@dataclass(frozen=True)
class PostizConfig:
    base_url: str
    access_token: str
    api_prefix: str = "/api"
    timeout_s: float = 30.0


class PostizClient:
    """
    Minimal Postiz REST client.

    Postiz is open source and self-hostable, but its API surface can vary by version
    and may not be fully documented publicly. This client intentionally keeps:
    - configurable `api_prefix`
    - conservative request/response parsing

    If your deployment uses a different auth mechanism (cookie/session), adapt
    `_headers()` and/or add a session-capable variant.
    """

    def __init__(self, config: PostizConfig):
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

        if req.scheduled_at:
            if not isinstance(req.scheduled_at, datetime):
                raise TypeError("scheduled_at must be a datetime")
            body["scheduled_at"] = req.scheduled_at.isoformat()

        if req.media_urls:
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

        post_id = (
            payload.get("id")
            or (payload.get("data") or {}).get("id")
            or (payload.get("post") or {}).get("id")
        )
        if not post_id:
            raise ValueError(f"Postiz create_post response missing post id: {payload}")

        post_url = payload.get("url") or (payload.get("data") or {}).get("url")
        return CreatePostResult(provider="postiz", post_id=str(post_id), post_url=post_url, raw=payload)

    def get_post(self, post_id: str) -> Dict[str, Any]:
        resp = request_json(
            method="GET",
            base_url=self._cfg.base_url,
            path=f"{self._cfg.api_prefix}/posts/{post_id}",
            headers=self._headers(),
            timeout_s=self._cfg.timeout_s,
        )
        return resp.json or {}

