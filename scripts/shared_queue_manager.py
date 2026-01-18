#!/usr/bin/env python3
"""
Shared Queue Manager (Notion or Redis)
=====================================

Provides a unified interface for claiming and updating jobs across multiple
nodes (MM1/MM2) and cloud workers (GitHub Actions).

This module is intentionally conservative and schema-tolerant:
- Notion backend: infers property names when not provided via env vars.
- Redis backend: uses atomic list moves for claim semantics (RPOPLPUSH).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Job:
    job_id: str
    job_type: str
    payload: Dict[str, Any]
    forward_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    # For Redis backend: preserve the exact raw JSON claimed from the queue.
    raw: Optional[str] = None


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def _truncate(s: str, n: int = 1800) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


class SharedQueueManager:
    """
    Runtime-selected queue manager.

    Expected interface (used by `scripts/github_actions_webhook_processor.py`):
    - claim_jobs(worker_id, max_jobs) -> List[Job]
    - mark_complete(job, result)
    - mark_failed(job, error)
    """

    @classmethod
    def from_env(cls, *, queue_source: str) -> "SharedQueueManager":
        if queue_source == "notion":
            return NotionQueue.from_env()
        if queue_source == "redis":
            return RedisQueue.from_env()
        raise ValueError(f"Unsupported queue_source: {queue_source}")


class NotionQueue(SharedQueueManager):
    def __init__(
        self,
        *,
        notion_token: str,
        database_id: str,
        status_pending: str,
        status_processing: str,
        status_complete: str,
        status_failed: str,
        status_property: Optional[str] = None,
        payload_property: Optional[str] = None,
        type_property: Optional[str] = None,
        worker_property: Optional[str] = None,
        result_property: Optional[str] = None,
        error_property: Optional[str] = None,
        forward_url_property: Optional[str] = None,
        headers_property: Optional[str] = None,
    ):
        from notion_client import Client  # local import to keep optional

        self.notion = Client(auth=notion_token)
        self.database_id = database_id

        self.status_pending = status_pending
        self.status_processing = status_processing
        self.status_complete = status_complete
        self.status_failed = status_failed

        self._status_property = status_property
        self._payload_property = payload_property
        self._type_property = type_property
        self._worker_property = worker_property
        self._result_property = result_property
        self._error_property = error_property
        self._forward_url_property = forward_url_property
        self._headers_property = headers_property

        self._schema = self.notion.databases.retrieve(database_id=self.database_id)
        self._prop_by_type = {
            name: meta.get("type") for name, meta in (self._schema.get("properties") or {}).items()
        }

        self._resolve_properties()
        self._validate_status_options()

    @classmethod
    def from_env(cls) -> "NotionQueue":
        token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
        if not token:
            raise RuntimeError("NOTION_TOKEN/NOTION_API_KEY not set")

        db_id = os.getenv("NOTION_WEBHOOK_JOBS_DB_ID")
        if not db_id:
            raise RuntimeError("NOTION_WEBHOOK_JOBS_DB_ID not set")

        return cls(
            notion_token=token,
            database_id=db_id,
            status_pending=os.getenv("NOTION_WEBHOOK_JOBS_STATUS_PENDING", "Pending"),
            status_processing=os.getenv("NOTION_WEBHOOK_JOBS_STATUS_PROCESSING", "Processing"),
            status_complete=os.getenv("NOTION_WEBHOOK_JOBS_STATUS_COMPLETE", "Complete"),
            status_failed=os.getenv("NOTION_WEBHOOK_JOBS_STATUS_FAILED", "Failed"),
            status_property=os.getenv("NOTION_WEBHOOK_JOBS_STATUS_PROPERTY"),
            payload_property=os.getenv("NOTION_WEBHOOK_JOBS_PAYLOAD_PROPERTY"),
            type_property=os.getenv("NOTION_WEBHOOK_JOBS_TYPE_PROPERTY"),
            worker_property=os.getenv("NOTION_WEBHOOK_JOBS_WORKER_PROPERTY"),
            result_property=os.getenv("NOTION_WEBHOOK_JOBS_RESULT_PROPERTY"),
            error_property=os.getenv("NOTION_WEBHOOK_JOBS_ERROR_PROPERTY"),
            forward_url_property=os.getenv("NOTION_WEBHOOK_JOBS_FORWARD_URL_PROPERTY"),
            headers_property=os.getenv("NOTION_WEBHOOK_JOBS_HEADERS_PROPERTY"),
        )

    def _resolve_properties(self) -> None:
        props = self._schema.get("properties") or {}

        def infer_status() -> Optional[str]:
            for name, meta in props.items():
                if meta.get("type") == "status":
                    return name
            return None

        def infer_payload() -> Optional[str]:
            # prefer rich_text named like payload
            candidates = []
            for name, meta in props.items():
                if meta.get("type") == "rich_text":
                    candidates.append(name)
            for n in candidates:
                if "payload" in n.lower():
                    return n
            return candidates[0] if candidates else None

        def infer_select_named(substr: str) -> Optional[str]:
            for name, meta in props.items():
                if meta.get("type") == "select" and substr in name.lower():
                    return name
            return None

        def infer_text_named(substr: str) -> Optional[str]:
            for name, meta in props.items():
                if meta.get("type") == "rich_text" and substr in name.lower():
                    return name
            return None

        def infer_url_named(substr: str) -> Optional[str]:
            for name, meta in props.items():
                if meta.get("type") == "url" and substr in name.lower():
                    return name
            return None

        self._status_property = self._status_property or infer_status()
        self._payload_property = self._payload_property or infer_payload()
        self._type_property = self._type_property or infer_select_named("type") or infer_select_named("job")
        self._worker_property = self._worker_property or infer_text_named("worker") or infer_text_named("node")
        self._result_property = self._result_property or infer_text_named("result") or infer_text_named("output")
        self._error_property = self._error_property or infer_text_named("error") or infer_text_named("fail")
        self._forward_url_property = self._forward_url_property or infer_url_named("forward") or infer_url_named("url")
        self._headers_property = self._headers_property or infer_text_named("headers")

        if not self._status_property or not self._payload_property:
            raise RuntimeError(
                "Notion queue schema missing required properties. "
                f"status_property={self._status_property}, payload_property={self._payload_property}"
            )

    def _validate_status_options(self) -> None:
        props = self._schema.get("properties") or {}
        meta = props.get(self._status_property) or {}
        if meta.get("type") != "status":
            raise RuntimeError(f"Status property '{self._status_property}' is not a status field")

        options = (meta.get("status") or {}).get("options") or []
        valid = {o.get("name") for o in options if o.get("name")}
        required = {self.status_pending, self.status_processing, self.status_complete, self.status_failed}
        missing = sorted([s for s in required if s not in valid])
        if missing:
            raise RuntimeError(
                f"Notion status options missing: {missing}. "
                f"Valid options: {sorted(valid)}. "
                "Set NOTION_WEBHOOK_JOBS_STATUS_* env vars to match your DB."
            )

    def _rich_text_to_str(self, rich_prop: Dict[str, Any]) -> str:
        if not isinstance(rich_prop, dict):
            return ""
        if rich_prop.get("type") != "rich_text":
            return ""
        rt = rich_prop.get("rich_text") or []
        parts = []
        for item in rt:
            txt = (item.get("plain_text") or "") if isinstance(item, dict) else ""
            if txt:
                parts.append(txt)
        return "".join(parts)

    def _get_prop(self, page: Dict[str, Any], name: Optional[str]) -> Dict[str, Any]:
        if not name:
            return {}
        return (page.get("properties") or {}).get(name) or {}

    def _extract_job(self, page: Dict[str, Any]) -> Job:
        page_id = page.get("id") or "unknown"

        payload_raw = self._rich_text_to_str(self._get_prop(page, self._payload_property)).strip()
        payload = _safe_json_loads(payload_raw) or {}

        job_type = "forward"
        if self._type_property:
            type_prop = self._get_prop(page, self._type_property)
            if type_prop.get("type") == "select" and type_prop.get("select"):
                job_type = (type_prop["select"].get("name") or job_type)

        forward_url = None
        if self._forward_url_property:
            url_prop = self._get_prop(page, self._forward_url_property)
            if url_prop.get("type") == "url":
                forward_url = url_prop.get("url")

        headers = None
        if self._headers_property:
            headers_raw = self._rich_text_to_str(self._get_prop(page, self._headers_property)).strip()
            if headers_raw:
                headers = _safe_json_loads(headers_raw)
                if headers and not isinstance(headers, dict):
                    headers = None

        return Job(
            job_id=str(page_id),
            job_type=str(job_type),
            payload=payload,
            forward_url=str(forward_url) if forward_url else None,
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else None,
        )

    def claim_jobs(self, worker_id: str, max_jobs: int) -> List[Job]:
        # Query for pending jobs
        resp = self.notion.databases.query(
            database_id=self.database_id,
            filter={
                "property": self._status_property,
                "status": {"equals": self.status_pending},
            },
            page_size=min(max_jobs * 2, 100),
        )
        results = resp.get("results") or []

        claimed: List[Job] = []
        for page in results:
            if len(claimed) >= max_jobs:
                break
            page_id = page.get("id")
            if not page_id:
                continue

            # Best-effort claim by flipping status to Processing and recording worker id.
            props: Dict[str, Any] = {
                self._status_property: {"status": {"name": self.status_processing}}
            }
            if self._worker_property:
                props[self._worker_property] = {
                    "rich_text": [{"type": "text", "text": {"content": str(worker_id)}}]
                }

            try:
                self.notion.pages.update(page_id=page_id, properties=props)
                # re-fetch to extract payload reliably
                full = self.notion.pages.retrieve(page_id=page_id)
                claimed.append(self._extract_job(full))
            except Exception:
                continue

        return claimed

    def mark_complete(self, job: Job, result: Dict[str, Any]) -> None:
        props: Dict[str, Any] = {
            self._status_property: {"status": {"name": self.status_complete}},
        }
        if self._result_property:
            props[self._result_property] = {
                "rich_text": [{"type": "text", "text": {"content": _truncate(json.dumps(result))}}]
            }
        try:
            self.notion.pages.update(page_id=job.job_id, properties=props)
        except Exception:
            return

    def mark_failed(self, job: Job, error: str) -> None:
        props: Dict[str, Any] = {
            self._status_property: {"status": {"name": self.status_failed}},
        }
        if self._error_property:
            props[self._error_property] = {
                "rich_text": [{"type": "text", "text": {"content": _truncate(str(error))}}]
            }
        try:
            self.notion.pages.update(page_id=job.job_id, properties=props)
        except Exception:
            return


class RedisQueue(SharedQueueManager):
    def __init__(self, *, redis_url: str, namespace: str = "webhook_jobs"):
        try:
            import redis  # type: ignore
        except Exception as e:
            raise RuntimeError("redis package not installed (pip install redis)") from e

        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self.ns = namespace
        self.key_pending = f"{self.ns}:pending"
        self.key_processing = f"{self.ns}:processing"
        self.key_failed = f"{self.ns}:failed"
        self.key_complete = f"{self.ns}:complete"

    @classmethod
    def from_env(cls) -> "RedisQueue":
        url = os.getenv("REDIS_URL")
        if not url:
            raise RuntimeError("REDIS_URL not set")
        ns = os.getenv("REDIS_QUEUE_NAMESPACE", "webhook_jobs")
        return cls(redis_url=url, namespace=ns)

    def _parse_job(self, raw: str) -> Job:
        obj = _safe_json_loads(raw) or {}
        job_id = obj.get("job_id") or f"redis_{int(time.time() * 1000)}"
        job_type = obj.get("job_type") or "forward"
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
        forward_url = obj.get("forward_url")
        headers = obj.get("headers")
        return Job(
            job_id=str(job_id),
            job_type=str(job_type),
            payload=payload if isinstance(payload, dict) else {},
            forward_url=str(forward_url) if forward_url else None,
            headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else None,
            raw=raw,
        )

    def claim_jobs(self, worker_id: str, max_jobs: int) -> List[Job]:
        claimed: List[Job] = []
        for _ in range(max_jobs):
            raw = self.redis.rpoplpush(self.key_pending, self.key_processing)
            if not raw:
                break
            claimed.append(self._parse_job(raw))
        return claimed

    def mark_complete(self, job: Job, result: Dict[str, Any]) -> None:
        # Remove from processing and append to complete list (best-effort)
        try:
            if job.raw:
                self.redis.lrem(self.key_processing, 1, job.raw)
        except Exception:
            pass
        record = {"job_id": job.job_id, "result": result, "completed_at": _utc_iso()}
        self.redis.lpush(self.key_complete, json.dumps(record))

    def mark_failed(self, job: Job, error: str) -> None:
        try:
            if job.raw:
                self.redis.lrem(self.key_processing, 1, job.raw)
        except Exception:
            pass
        record = {"job_id": job.job_id, "error": error, "failed_at": _utc_iso()}
        self.redis.lpush(self.key_failed, json.dumps(record))

