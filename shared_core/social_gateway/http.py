from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

from .types import (
    SocialGatewayAuthError,
    SocialGatewayRequestError,
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    json: Optional[Dict[str, Any]]
    text: str
    headers: Dict[str, str]


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {"_json": obj}
    except Exception:
        return None


def request_json(
    *,
    method: str,
    base_url: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_s: float = 30.0,
) -> HttpResponse:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    resp = requests.request(
        method=method.upper(),
        url=url,
        headers=headers or {},
        params=params,
        json=json_body,
        timeout=timeout_s,
    )

    text = resp.text or ""
    parsed = _try_parse_json(text)
    response = HttpResponse(
        status_code=resp.status_code,
        json=parsed,
        text=text,
        headers={k: v for k, v in resp.headers.items()},
    )

    if resp.status_code in (401, 403):
        raise SocialGatewayAuthError(
            f"{method.upper()} {url} failed with {resp.status_code}: {text[:500]}"
        )
    if resp.status_code >= 400:
        raise SocialGatewayRequestError(
            f"{method.upper()} {url} failed with {resp.status_code}: {text[:500]}"
        )

    return response

