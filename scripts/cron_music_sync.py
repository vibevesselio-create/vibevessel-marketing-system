#!/usr/bin/env python3
"""
Cron Music Sync - Local Automated Music Track Synchronization
==============================================================

This script is designed to run via cron job for automatic music track
synchronization. It integrates with the production workflow and supports
webhook notifications to Google Apps Script.

VERSION: 1.0.0
CREATED: 2026-01-30
AUTHOR: Claude Code Agent

CRON SETUP:
    # Run every 5 minutes
    */5 * * * * /usr/bin/python3 /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py --mode incremental

    # Run full sync daily at 3am
    0 3 * * * /usr/bin/python3 /Users/brianhellemn/Projects/github-production/scripts/cron_music_sync.py --mode full

FEATURES:
    - Incremental sync (5-minute intervals)
    - Full library sync (daily)
    - Webhook notifications to GAS
    - State persistence for resumption
    - Lock file to prevent concurrent runs
"""

import os
import sys
import json
import argparse
import logging
import fcntl
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "monolithic-scripts"))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Configure logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "cron_music_sync.log")
    ]
)
logger = logging.getLogger(__name__)

# Configuration
LOCK_FILE = PROJECT_ROOT / ".cron_music_sync.lock"
STATE_FILE = PROJECT_ROOT / ".cron_music_sync_state.json"
WEBHOOK_URL = os.getenv("GAS_WEBHOOK_URL", "")
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")

# Use centralized token manager (MANDATORY per CLAUDE.md)
try:
    from shared_core.notion.token_manager import get_notion_token
    NOTION_TOKEN = get_notion_token()
except ImportError:
    # Fallback for backwards compatibility
    NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")


class CronMusicSync:
    """Automated music sync for cron execution."""

    def __init__(self, mode: str = "incremental"):
        self.mode = mode
        self.state = self._load_state()
        self.stats = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "processed": 0,
            "created": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0
        }

    def _load_state(self) -> Dict[str, Any]:
        """Load sync state from file."""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")

        return {
            "last_sync": None,
            "batch_index": 0,
            "total_synced": 0,
            "last_track_id": None
        }

    def _save_state(self):
        """Save sync state to file."""
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _send_webhook(self, event: str, data: Dict[str, Any]):
        """Send webhook notification to GAS or other endpoints."""
        if not WEBHOOK_URL:
            return

        try:
            import urllib.request
            payload = json.dumps({
                "event": event,
                "source": "cron_music_sync",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data
            }).encode('utf-8')

            req = urllib.request.Request(
                WEBHOOK_URL,
                data=payload,
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Webhook sent: {event} -> {resp.status}")
        except Exception as e:
            logger.warning(f"Webhook failed: {e}")

    def run_incremental(self) -> Dict[str, Any]:
        """Run incremental sync - process unprocessed tracks."""
        logger.info("Starting incremental sync...")

        try:
            # Import production workflow
            from soundcloud_download_prod_merge_2 import (
                query_unprocessed_tracks,
                process_single_track,
                NOTION_CLIENT
            )
        except ImportError:
            # Fallback to subprocess
            return self._run_via_subprocess("--mode single --limit 10")

        try:
            # Get batch of unprocessed tracks
            batch_size = 10
            tracks = query_unprocessed_tracks(limit=batch_size)

            if not tracks:
                logger.info("No unprocessed tracks found")
                self.state["last_sync"] = datetime.now(timezone.utc).isoformat()
                self._save_state()
                return {"success": True, "message": "No tracks to process"}

            logger.info(f"Found {len(tracks)} tracks to process")

            for track in tracks:
                try:
                    result = process_single_track(track)
                    if result.get("success"):
                        self.stats["processed"] += 1
                        if result.get("created"):
                            self.stats["created"] += 1
                        else:
                            self.stats["updated"] += 1
                    else:
                        self.stats["errors"] += 1
                except Exception as e:
                    logger.error(f"Track processing error: {e}")
                    self.stats["errors"] += 1

            # Update state
            self.state["last_sync"] = datetime.now(timezone.utc).isoformat()
            self.state["total_synced"] += self.stats["processed"]
            self._save_state()

            # Send webhook
            self._send_webhook("sync_complete", self.stats)

            return {
                "success": self.stats["errors"] == 0,
                "stats": self.stats
            }

        except Exception as e:
            logger.error(f"Incremental sync error: {e}")
            self._send_webhook("sync_error", {"error": str(e)})
            return {"success": False, "error": str(e)}

    def run_full(self) -> Dict[str, Any]:
        """Run full library sync."""
        logger.info("Starting full library sync...")
        return self._run_via_subprocess("--mode library-sync --limit 100")

    def _run_via_subprocess(self, args: str) -> Dict[str, Any]:
        """Run production script via subprocess."""
        import subprocess

        script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
        cmd = f"python3 {script_path} {args}"

        logger.info(f"Running: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(PROJECT_ROOT)
            )

            if result.returncode == 0:
                logger.info("Subprocess completed successfully")
                self.state["last_sync"] = datetime.now(timezone.utc).isoformat()
                self._save_state()
                self._send_webhook("sync_complete", {"mode": args})
                return {"success": True, "output": result.stdout[-1000:]}
            else:
                logger.error(f"Subprocess failed: {result.stderr[-500:]}")
                self._send_webhook("sync_error", {"error": result.stderr[-500:]})
                return {"success": False, "error": result.stderr[-500:]}

        except subprocess.TimeoutExpired:
            logger.error("Subprocess timed out")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            logger.error(f"Subprocess error: {e}")
            return {"success": False, "error": str(e)}

    def run(self) -> Dict[str, Any]:
        """Run sync based on mode."""
        if self.mode == "incremental":
            return self.run_incremental()
        elif self.mode == "full":
            return self.run_full()
        else:
            return {"success": False, "error": f"Unknown mode: {self.mode}"}


def acquire_lock() -> Optional[int]:
    """Acquire exclusive lock to prevent concurrent runs."""
    try:
        lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (OSError, IOError):
        return None


def release_lock(lock_fd: int):
    """Release the lock."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    except:
        pass


def main():
    parser = argparse.ArgumentParser(description="Cron Music Sync")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Sync mode (default: incremental)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run even if another instance is running"
    )
    args = parser.parse_args()

    # Acquire lock
    if not args.force:
        lock_fd = acquire_lock()
        if lock_fd is None:
            logger.warning("Another instance is running, exiting")
            sys.exit(0)
    else:
        lock_fd = None

    try:
        logger.info(f"=== Cron Music Sync Started (mode: {args.mode}) ===")

        sync = CronMusicSync(mode=args.mode)
        result = sync.run()

        if result.get("success"):
            logger.info(f"Sync completed: {json.dumps(result.get('stats', {}))}")
        else:
            logger.error(f"Sync failed: {result.get('error')}")
            sys.exit(1)

    finally:
        if lock_fd is not None:
            release_lock(lock_fd)

        logger.info("=== Cron Music Sync Finished ===")


if __name__ == "__main__":
    main()
