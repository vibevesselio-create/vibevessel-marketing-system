#!/usr/bin/env python3
"""
Google Apps Script Integration Endpoints
=========================================

FastAPI router providing webhook endpoints for Google Apps Script integration.
These endpoints allow GAS scripts to trigger local workflows and receive
notifications about sync status.

VERSION: 1.0.0
CREATED: 2026-01-30
AUTHOR: Claude Code Agent

ENDPOINTS:
    POST /gas/trigger-sync       - Trigger local music sync from GAS
    POST /gas/webhook            - Receive notifications from GAS
    GET  /gas/status             - Get current sync status
    POST /gas/config             - Update sync configuration

INTEGRATION:
    Add this router to the main FastAPI app:

    from gas_integration_endpoints import gas_router
    app.include_router(gas_router, prefix="/gas", tags=["Google Apps Script"])
"""

import os
import sys
import json
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

# Project imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Router
gas_router = APIRouter(prefix="/gas", tags=["Google Apps Script Integration"])

# Configuration
SYNC_STATE_FILE = PROJECT_ROOT / ".gas_sync_state.json"
PRODUCTION_SCRIPT = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
CRON_SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "cron_music_sync.py"


class SyncTriggerRequest(BaseModel):
    """Request to trigger a sync operation."""
    mode: str = "incremental"  # incremental, full, single
    source: str = "gas"
    limit: int = 10
    track_id: Optional[str] = None
    callback_url: Optional[str] = None


class GASWebhookPayload(BaseModel):
    """Payload from GAS webhook notifications."""
    event: str
    source: str
    timestamp: str
    data: Dict[str, Any] = {}


class ConfigUpdateRequest(BaseModel):
    """Request to update sync configuration."""
    trigger_interval_minutes: Optional[int] = None
    batch_size: Optional[int] = None
    enabled: Optional[bool] = None
    webhook_url: Optional[str] = None


def load_sync_state() -> Dict[str, Any]:
    """Load sync state from file."""
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE) as f:
                return json.load(f)
        except:
            pass

    return {
        "last_sync": None,
        "last_trigger": None,
        "total_synced": 0,
        "errors": 0,
        "config": {
            "trigger_interval_minutes": 5,
            "batch_size": 50,
            "enabled": True,
            "webhook_url": ""
        }
    }


def save_sync_state(state: Dict[str, Any]):
    """Save sync state to file."""
    try:
        with open(SYNC_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Failed to save state: {e}")


async def run_sync_background(request: SyncTriggerRequest):
    """Run sync operation in background."""
    state = load_sync_state()
    state["last_trigger"] = datetime.now(timezone.utc).isoformat()
    state["trigger_source"] = request.source
    save_sync_state(state)

    # Determine which script/mode to run
    if request.mode == "incremental":
        cmd = ["python3", str(CRON_SYNC_SCRIPT), "--mode", "incremental"]
    elif request.mode == "full":
        cmd = ["python3", str(PRODUCTION_SCRIPT), "--mode", "library-sync", "--limit", str(request.limit)]
    elif request.mode == "single" and request.track_id:
        cmd = ["python3", str(PRODUCTION_SCRIPT), "--mode", "single"]
    else:
        cmd = ["python3", str(PRODUCTION_SCRIPT), "--mode", "batch", "--limit", str(request.limit)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(PROJECT_ROOT)
        )

        # Update state
        state = load_sync_state()
        state["last_sync"] = datetime.now(timezone.utc).isoformat()

        if result.returncode == 0:
            state["total_synced"] += 1
        else:
            state["errors"] += 1
            state["last_error"] = result.stderr[-500:] if result.stderr else "Unknown error"

        save_sync_state(state)

        # Send callback if provided
        if request.callback_url:
            await send_callback(request.callback_url, {
                "event": "sync_complete",
                "success": result.returncode == 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    except subprocess.TimeoutExpired:
        state = load_sync_state()
        state["errors"] += 1
        state["last_error"] = "Sync timed out"
        save_sync_state(state)
    except Exception as e:
        state = load_sync_state()
        state["errors"] += 1
        state["last_error"] = str(e)
        save_sync_state(state)


async def send_callback(url: str, data: Dict[str, Any]):
    """Send HTTP callback to specified URL."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                print(f"Callback sent to {url}: {resp.status}")
    except Exception as e:
        print(f"Callback failed: {e}")


@gas_router.post("/trigger-sync")
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger a music sync operation from Google Apps Script.

    This endpoint allows GAS to trigger local sync operations
    and optionally receive a callback when complete.
    """
    state = load_sync_state()

    # Check if sync is enabled
    if not state.get("config", {}).get("enabled", True):
        raise HTTPException(status_code=503, detail="Sync is currently disabled")

    # Queue background sync
    background_tasks.add_task(run_sync_background, request)

    return {
        "success": True,
        "message": f"Sync triggered ({request.mode})",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@gas_router.post("/webhook")
async def receive_gas_webhook(payload: GASWebhookPayload):
    """
    Receive webhook notifications from Google Apps Script.

    GAS scripts can send notifications about:
    - sync_started: Sync operation started in GAS
    - sync_complete: Sync operation completed
    - sync_error: Error occurred during sync
    - token_refreshed: Spotify token was refreshed
    - tracks_added: New tracks added to Notion
    """
    print(f"GAS Webhook: {payload.event} from {payload.source}")

    state = load_sync_state()
    state["last_gas_webhook"] = {
        "event": payload.event,
        "timestamp": payload.timestamp,
        "source": payload.source
    }
    save_sync_state(state)

    # Handle specific events
    if payload.event == "sync_complete":
        # Log sync completion from GAS
        print(f"GAS sync complete: {payload.data}")

    elif payload.event == "sync_error":
        # Log error from GAS
        print(f"GAS sync error: {payload.data.get('error', 'Unknown')}")
        state["errors"] += 1
        save_sync_state(state)

    elif payload.event == "tracks_added":
        # Optionally trigger local processing for newly added tracks
        tracks = payload.data.get("tracks", [])
        if tracks:
            print(f"GAS added {len(tracks)} tracks, may need local processing")

    return {
        "received": True,
        "event": payload.event,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@gas_router.get("/status")
async def get_sync_status():
    """
    Get current sync status and configuration.

    Returns:
    - Last sync timestamp
    - Total synced count
    - Error count
    - Configuration settings
    - Last GAS webhook received
    """
    state = load_sync_state()

    return {
        "status": "enabled" if state.get("config", {}).get("enabled", True) else "disabled",
        "last_sync": state.get("last_sync"),
        "last_trigger": state.get("last_trigger"),
        "total_synced": state.get("total_synced", 0),
        "errors": state.get("errors", 0),
        "last_error": state.get("last_error"),
        "last_gas_webhook": state.get("last_gas_webhook"),
        "config": state.get("config", {}),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@gas_router.post("/config")
async def update_config(request: ConfigUpdateRequest):
    """
    Update sync configuration.

    Allows updating:
    - trigger_interval_minutes: Time between syncs
    - batch_size: Number of tracks per batch
    - enabled: Enable/disable sync
    - webhook_url: URL for sending notifications
    """
    state = load_sync_state()
    config = state.get("config", {})

    if request.trigger_interval_minutes is not None:
        config["trigger_interval_minutes"] = request.trigger_interval_minutes

    if request.batch_size is not None:
        config["batch_size"] = request.batch_size

    if request.enabled is not None:
        config["enabled"] = request.enabled

    if request.webhook_url is not None:
        config["webhook_url"] = request.webhook_url

    state["config"] = config
    state["config_updated"] = datetime.now(timezone.utc).isoformat()
    save_sync_state(state)

    return {
        "success": True,
        "config": config,
        "updated_at": state["config_updated"]
    }


@gas_router.get("/health")
async def health_check():
    """Health check endpoint for GAS to verify local server is running."""
    return {
        "status": "healthy",
        "service": "gas-integration",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Export router for use in main app
__all__ = ["gas_router"]
