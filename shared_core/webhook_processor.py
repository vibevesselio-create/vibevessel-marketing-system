"""
Shared Webhook Processing Utilities
==================================

This module centralizes small, reusable primitives that are needed across:
- MM1 webhook server (coordinator)
- MM2 webhook server (worker)
- GitHub Actions cloud workers

It intentionally avoids importing the large webhook server modules to keep it
safe to use in constrained environments (e.g., GitHub Actions runners).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_idempotency_key(prefix: str, payload: Dict[str, Any]) -> str:
    """
    Stable idempotency key for any JSON payload.
    """
    data = _canonical_json(payload).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    return f"{prefix}:{digest}"


def validate_hmac_signature(
    *,
    body: bytes,
    signature: str,
    secret: str,
    digestmod: str = "sha256",
    prefix: Optional[str] = None,
) -> bool:
    """
    Generic HMAC validator.

    If `prefix` is provided (e.g. 'v0='), it will be stripped from signature before compare.
    """
    if not secret or not signature:
        return False
    sig = signature.strip()
    if prefix and sig.startswith(prefix):
        sig = sig[len(prefix) :]

    mac = hmac.new(secret.encode("utf-8"), body, digestmod=getattr(hashlib, digestmod))
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, sig)


def forward_json(
    *,
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout_s: int = 5,
) -> Tuple[bool, Dict[str, Any], str]:
    """
    Best-effort HTTP JSON POST using stdlib only.
    Returns (ok, response_dict, error_string).
    """
    try:
        req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            req_headers.update({str(k): str(v) for k, v in headers.items()})

        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )
        with urlopen(req, timeout=timeout_s) as resp:  # nosec - caller controls URL
            body = resp.read().decode("utf-8", errors="replace")
            status_code = getattr(resp, "status", 200)

        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"text": body[:5000]}

        ok = 200 <= int(status_code) < 300
        return ok, {"status_code": int(status_code), "body": parsed}, ""
    except Exception as e:
        return False, {}, str(e)


@dataclass
class ProcessResult:
    ok: bool
    status: str
    run_id: str
    node_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "details": self.details or {},
            "error": self.error,
        }


def ensure_run_id(payload: Dict[str, Any], *, prefix: str) -> str:
    run_id = payload.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return run_id
    run_id = f"{prefix}-{int(time.time() * 1000)}"
    payload["run_id"] = run_id
    return run_id


def process_notion_webhook(
    payload: Dict[str, Any],
    *,
    forward_url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> ProcessResult:
    """
    Minimal portable Notion webhook processor.

    In cloud/worker contexts, this function forwards to a coordinator/worker endpoint.
    In local server contexts, the full processing lives in the webhook server module.
    """
    run_id = ensure_run_id(payload, prefix="notion-webhook")
    if dry_run:
        return ProcessResult(ok=True, status="dry_run", run_id=run_id, details={"forward_url": forward_url})
    if not forward_url:
        return ProcessResult(ok=False, status="no_forward_url", run_id=run_id, error="forward_url not set")

    ok, resp, err = forward_json(url=forward_url, payload=payload, headers=headers)
    return ProcessResult(ok=ok, status="forwarded" if ok else "forward_failed", run_id=run_id, details=resp, error=err or None)


def process_workspace_event(
    event: Dict[str, Any],
    *,
    forward_url: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> ProcessResult:
    run_id = ensure_run_id(event, prefix="workspace-event")
    if dry_run:
        return ProcessResult(ok=True, status="dry_run", run_id=run_id, details={"forward_url": forward_url})
    if not forward_url:
        return ProcessResult(ok=False, status="no_forward_url", run_id=run_id, error="forward_url not set")

    ok, resp, err = forward_json(url=forward_url, payload=event, headers=headers)
    return ProcessResult(ok=ok, status="forwarded" if ok else "forward_failed", run_id=run_id, details=resp, error=err or None)

