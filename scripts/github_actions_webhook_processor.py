#!/usr/bin/env python3
"""
GitHub Actions Webhook Processor
================================

Cloud worker designed to run in GitHub Actions runners to increase throughput and
reliability of webhook processing by distributing work across parallel jobs.

This worker supports two modes:
1) payload mode: process a single repository_dispatch payload file
2) queue mode: claim and process jobs from a shared queue (Notion or Redis)

The "shared queue" abstraction is implemented in `scripts/shared_queue_manager.py`.
This script provides a fallback minimal Notion queue implementation if that
module is not available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


def _strtobool(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_json_file(path: str) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


@dataclass
class Job:
    job_id: str
    job_type: str
    payload: Dict[str, Any]
    forward_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class JobQueue:
    def claim_jobs(self, worker_id: str, max_jobs: int) -> List[Job]:
        raise NotImplementedError

    def mark_complete(self, job: Job, result: Dict[str, Any]) -> None:
        raise NotImplementedError

    def mark_failed(self, job: Job, error: str) -> None:
        raise NotImplementedError


def _maybe_build_queue(queue_source: str) -> Optional[JobQueue]:
    """
    Prefer the shared queue manager; fall back to None and require payload mode.
    """
    try:
        from scripts.shared_queue_manager import SharedQueueManager  # type: ignore

        return SharedQueueManager.from_env(queue_source=queue_source)
    except Exception:
        return None


def _job_from_dispatch_payload(dispatch_payload: Dict[str, Any]) -> Optional[Job]:
    """
    Expected shapes:
    - { "job_id": "...", "job_type": "...", "payload": {...}, "forward_url": "...", "headers": {...} }
    - { "payload": {...}, "forward_url": "..." }  (job_id auto)
    """
    if not isinstance(dispatch_payload, dict) or not dispatch_payload:
        return None

    payload = dispatch_payload.get("payload")
    if not isinstance(payload, dict):
        # allow direct payload at top-level for convenience
        payload = dispatch_payload

    job_type = dispatch_payload.get("job_type") or payload.get("job_type") or "forward"
    job_id = dispatch_payload.get("job_id") or payload.get("job_id") or f"dispatch_{int(time.time() * 1000)}"
    forward_url = dispatch_payload.get("forward_url") or payload.get("forward_url")
    headers = dispatch_payload.get("headers") or payload.get("headers")
    if headers is not None and not isinstance(headers, dict):
        headers = None

    return Job(
        job_id=str(job_id),
        job_type=str(job_type),
        payload=payload if isinstance(payload, dict) else {},
        forward_url=str(forward_url) if forward_url else None,
        headers={str(k): str(v) for k, v in headers.items()} if isinstance(headers, dict) else None,
    )


def _forward_job(job: Job, default_forward_url: Optional[str], timeout_s: int = 30) -> Tuple[bool, Dict[str, Any], str]:
    """
    Forward to MM1 coordinator (or any HTTP endpoint).
    """
    url = job.forward_url or default_forward_url
    if not url:
        return False, {}, "No forward_url provided"

    headers = {"Content-Type": "application/json"}
    if job.headers:
        headers.update(job.headers)

    try:
        r = requests.post(url, json=job.payload, headers=headers, timeout=timeout_s)
        ok = 200 <= r.status_code < 300
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text[:5000]}
        if ok:
            return True, {"status_code": r.status_code, "body": body}, ""
        return False, {"status_code": r.status_code, "body": body}, f"HTTP {r.status_code}"
    except Exception as e:
        return False, {}, str(e)


def process_job(job: Job, *, dry_run: bool, default_forward_url: Optional[str]) -> Tuple[bool, Dict[str, Any], str]:
    """
    For now, the cloud worker focuses on reliable distributed execution by:
    - forwarding work to a coordinator endpoint, OR
    - acting on jobs defined in the queue once shared handlers are extracted.
    """
    if dry_action := job.payload.get("dry_run"):
        # honor per-job dry_run override if provided
        dry_run = _strtobool(str(dry_action))

    if job.job_type in {"forward", "notion_webhook", "workspace_event"}:
        if dry_run:
            return True, {"dry_run": True, "forward_url": job.forward_url or default_forward_url}, ""
        # default behavior: forward to coordinator endpoint
        return _forward_job(job, default_forward_url=default_forward_url)

    # Unknown job types are treated as failures (explicit > implicit).
    return False, {}, f"Unsupported job_type: {job.job_type}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--queue-source", default="notion", choices=["notion", "redis", "payload"])
    parser.add_argument("--max-jobs", default="25")
    parser.add_argument("--dry-run", default="false")
    parser.add_argument("--payload-file", default="repo_dispatch_payload.json")
    args = parser.parse_args()

    worker_id = str(args.worker_id)
    max_jobs = int(str(args.max_jobs))
    dry_run = _strtobool(str(args.dry_run))

    # Coordinator endpoint (preferred for now). In Phase 2+ we can execute locally.
    default_forward_url = os.getenv("MM1_COORDINATOR_URL") or os.getenv("COORDINATOR_URL")
    if default_forward_url and default_forward_url.endswith("/"):
        default_forward_url = default_forward_url[:-1]
    if default_forward_url and not default_forward_url.endswith("/webhook"):
        # If user points at base server URL, default to /webhook/process for worker-style forwarding
        # (MM1 can expose /webhook directly too).
        default_forward_url = f"{default_forward_url}/webhook"

    # Payload mode: process dispatch payload if present and non-empty.
    dispatch_payload = _load_json_file(args.payload_file)
    if args.queue_source == "payload" or (dispatch_payload and os.getenv("GITHUB_EVENT_NAME") == "repository_dispatch"):
        job = _job_from_dispatch_payload(dispatch_payload or {})
        if not job:
            print("No valid payload job found; exiting.")
            return 0

        ok, result, err = process_job(job, dry_run=dry_run, default_forward_url=default_forward_url)
        print(json.dumps({"job_id": job.job_id, "ok": ok, "result": result, "error": err}, indent=2))
        return 0 if ok else 2

    # Queue mode: claim up to N jobs and process.
    queue = _maybe_build_queue(args.queue_source)
    if not queue:
        print(
            "Queue backend not available. "
            "Set NOTION_WEBHOOK_JOBS_DB_ID/NOTION_TOKEN (notion) or REDIS_URL (redis), "
            "or use --queue-source payload."
        )
        return 2

    jobs = queue.claim_jobs(worker_id=worker_id, max_jobs=max_jobs)
    if not jobs:
        print("No jobs claimed.")
        return 0

    processed = 0
    failed = 0
    for job in jobs:
        ok, result, err = process_job(job, dry_run=dry_run, default_forward_url=default_forward_url)
        if ok:
            queue.mark_complete(job, result=result)
            processed += 1
        else:
            queue.mark_failed(job, error=err or "unknown error")
            failed += 1

    print(json.dumps({"worker_id": worker_id, "processed": processed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

