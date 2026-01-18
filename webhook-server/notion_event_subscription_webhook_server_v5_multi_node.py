#!/usr/bin/env python3
"""
Notion + Workspace Events Multi-Node Webhook Server (v5)
=======================================================

This is a thin multi-node entrypoint that reuses the proven v4 server implementation,
while making it explicit that this process is the **local node** (MM2) in the
overall architecture.

Key responsibilities (implemented in v4 and imported here):
- Notion event subscription webhook receiver + queue-based processing
- Workspace Events background Pub/Sub pull consumer (workspace_events_integration)
- CSV logging of Notion webhook payloads
- Loop-guard safeguards to prevent circular Notion↔Drive↔Notion flows
"""

import os

# Identify this node for downstream logging / loop-guard tagging.
os.environ.setdefault("WORKSPACE_EVENTS_NODE_ID", "local")

import uvicorn  # noqa: E402

from notion_event_subscription_webhook_server_v4_enhanced import (  # noqa: E402
    FASTAPI_HOST,
    FASTAPI_PORT,
    WEBHOOK_URL,
    app,
    webhook_logger,
)


if __name__ == "__main__":
    webhook_logger.info(f"🚀 Starting Multi-Node Webhook Server (v5) on {FASTAPI_HOST}:{FASTAPI_PORT}")
    webhook_logger.info(f"Network: Public URL: {WEBHOOK_URL}")
    uvicorn.run(app, host=FASTAPI_HOST, port=FASTAPI_PORT)

