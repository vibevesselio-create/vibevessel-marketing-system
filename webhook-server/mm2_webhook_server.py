#!/usr/bin/env python3
"""
MM2 Webhook Server (Worker Node)
================================

Runs the proven v4 FastAPI webhook server implementation on a dedicated
worker port (default: 5002) and exposes worker-friendly endpoints for
MM1 coordination.

Key goals:
- Same processing logic as MM1 (shared v4 implementation)
- Separate port and node identity (MM2)
- Safe forwarding entrypoint (/webhook/process) for coordinator assignment
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import uvicorn
from fastapi import Body

# Identify this node for downstream loop-guard tagging/logging.
os.environ.setdefault("WORKSPACE_EVENTS_NODE_ID", "mm2")

# Force worker port (v4 reads PORT via SERVER_CONFIG).
os.environ.setdefault("PORT", os.getenv("MM2_PORT", "5002"))

# Import v4 app (shared implementation).
from notion_event_subscription_webhook_server_v4_enhanced import (  # noqa: E402
    FASTAPI_HOST,
    FASTAPI_PORT,
    app,
    webhook_logger,
    webhook_queue,
)


@app.post("/webhook/process")
async def process_assigned_webhook(payload: Dict[str, Any] = Body(...)):
    """
    MM1 → MM2 worker assignment endpoint.

    The coordinator should POST the *already-verified* payload here.
    This endpoint queues the payload for controlled sequential processing
    and returns immediately.
    """
    run_id = payload.get("run_id") or f"mm2-webhook-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    payload["run_id"] = run_id
    payload.setdefault("__source", "mm1_coordinator")
    payload.setdefault("received_at", datetime.now(timezone.utc).isoformat())

    webhook_queue.add_webhook(payload, request_id=run_id)
    return {"ok": True, "run_id": run_id, "status": "queued", "node_id": os.getenv("WORKSPACE_EVENTS_NODE_ID", "mm2")}


@app.get("/status")
async def status():
    """
    Lightweight worker status for MM1 coordinator polling.
    """
    return {
        "node_id": os.getenv("WORKSPACE_EVENTS_NODE_ID", "mm2"),
        "host": FASTAPI_HOST,
        "port": FASTAPI_PORT,
        "queue_processing": getattr(webhook_queue, "processing", None),
        "queue_depth": len(getattr(webhook_queue, "queue", []) or []),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    webhook_logger.info(f"🚀 Starting MM2 Worker Webhook Server on {FASTAPI_HOST}:{FASTAPI_PORT}")
    uvicorn.run(app, host=FASTAPI_HOST, port=FASTAPI_PORT)

