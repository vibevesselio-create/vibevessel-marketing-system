#!/usr/bin/env python3
"""
DEPRECATED: Use run_fingerprint_dedup_production.py instead
==============================================================

This script is DEPRECATED and will be removed in a future version.

Use the unified production script which includes djay Pro sync:
    python scripts/run_fingerprint_dedup_production.py

Or for djay-only sync:
    python scripts/run_fingerprint_dedup_production.py --djay-sync-only

The new script:
- Uses djay Pro as source of truth for Tempo/Key
- Syncs all djay Pro metadata (BPM, Key, Play Count, Last Played)
- Prevents Spotify/other sources from overwriting djay Pro data

Original description (deprecated):
----------------------------------
Direct sync of djay Pro BPM/Key data to Notion Tracks Database

This script directly queries the secondaryIndex_mediaItemIndex table
and syncs BPM/Key data to Notion tracks by matching file paths.

Addresses: BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete
Issue ID: 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8

DEPRECATED: 2026-01-18
"""

import warnings
warnings.warn(
    "sync_djay_bpm_key_direct.py is deprecated. "
    "Use run_fingerprint_dedup_production.py --djay-sync-only instead.",
    DeprecationWarning,
    stacklevel=2
)

import os
import sys
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
import time

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    NOTION_CLIENT_AVAILABLE = False
    Client = None

try:
    from shared_core.notion.token_manager import get_notion_token
    from shared_core.logging import setup_logging
    workspace_logger = setup_logging()
except ImportError:
    import logging
    workspace_logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

try:
    from unified_config import get_unified_config
    unified_config = get_unified_config()
except ImportError:
    unified_config = {}

# Database IDs
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID") or unified_config.get("tracks_db_id") or "27ce7361-6c27-80fb-b40e-fefdd47d6640"

# Default djay Pro database path
DEFAULT_DJAY_DB_PATH = Path.home() / "Music" / "djay" / "djay Media Library.djayMediaLibrary" / "MediaLibrary.db"

# Key signature mapping (musicalKeySignatureIndex to key name)
KEY_SIGNATURE_MAP = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B"
}


def extract_bpm_key_data(db_path: Path) -> List[Dict[str, Any]]:
    """Extract BPM/Key data from djay Pro database."""
    workspace_logger.info(f"📊 Extracting BPM/Key data from: {db_path}")
    
    tracks = []
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Query secondaryIndex_mediaItemIndex for BPM/Key data
        # Join with secondaryIndex_mediaItemLocationIndex for file paths via database2
        # The correct relationship chain is:
        #   1. secondaryIndex_mediaItemIndex.titleID = database2.key (where collection='localMediaItemLocations')
        #   2. database2.rowid = secondaryIndex_mediaItemLocationIndex.rowid
        # This properly maps through YapDatabase's localMediaItemLocations collection.
        # Previous rowid+1 approach had only 57% match rate; this approach achieves 86%+ match rate.
        # Fixed: 2026-01-16 (aligned with sync_djay_bpm_key_to_notion.py)
        query = """
            SELECT
                m.titleID,
                m.bpm,
                m.musicalKeySignatureIndex,
                l.fileName
            FROM secondaryIndex_mediaItemIndex m
            LEFT JOIN database2 d ON m.titleID = d.key AND d.collection = 'localMediaItemLocations'
            LEFT JOIN secondaryIndex_mediaItemLocationIndex l ON d.rowid = l.rowid
            WHERE m.bpm IS NOT NULL OR m.musicalKeySignatureIndex IS NOT NULL
        """
        
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        
        for row in rows:
            title_id = row["titleID"]
            bpm = row["bpm"]
            key_index = row["musicalKeySignatureIndex"]
            file_name = row["fileName"]
            
            # Convert key index to key name
            key = None
            if key_index is not None:
                key = KEY_SIGNATURE_MAP.get(int(key_index), str(key_index))
            
            if bpm is not None or key:
                tracks.append({
                    "titleID": title_id,
                    "bpm": float(bpm) if bpm else None,
                    "key": key,
                    "fileName": file_name
                })
        
        conn.close()
        workspace_logger.info(f"✅ Extracted {len(tracks)} tracks with BPM/Key data")
        return tracks
        
    except Exception as e:
        workspace_logger.error(f"❌ Error extracting data: {e}")
        raise


def find_notion_track_by_path(notion_client: Client, tracks_db_id: str, file_path: str) -> Optional[str]:
    """Find Notion track by file path."""
    try:
        # Try to find by file path (various property names)
        for prop_name in ["File Path", "FilePath", "iPad Path", "Path"]:
            try:
                response = notion_client.databases.query(
                    database_id=tracks_db_id,
                    filter={
                        "property": prop_name,
                        "rich_text": {"contains": file_path}
                    },
                    page_size=1
                )
                results = response.get("results", [])
                if results:
                    return results[0]["id"]
            except Exception:
                continue
        
        return None
    except Exception as e:
        workspace_logger.debug(f"Error finding track by path: {e}")
        return None


def update_notion_track(notion_client: Client, page_id: str, bpm: Optional[float], key: Optional[str], dry_run: bool = False) -> bool:
    """Update Notion track with BPM/Key data."""
    properties = {}
    
    if bpm is not None:
        properties["AverageBpm"] = {"number": float(bpm)}
    
    if key:
        properties["Key"] = {"rich_text": [{"text": {"content": str(key)}}]}
    
    if not properties:
        return False
    
    try:
        if dry_run:
            workspace_logger.info(f"[DRY RUN] Would update page {page_id} with: {properties}")
            return True
        
        notion_client.pages.update(page_id=page_id, properties=properties)
        return True
        
    except Exception as e:
        workspace_logger.warning(f"Error updating Notion track {page_id}: {e}")
        return False


def sync_to_notion(djay_tracks: List[Dict[str, Any]], tracks_db_id: str, dry_run: bool = False, limit: Optional[int] = None) -> Dict[str, int]:
    """Sync BPM/Key data to Notion."""
    if not NOTION_CLIENT_AVAILABLE:
        workspace_logger.warning("⚠️  Notion client not available")
        return {"synced": 0, "updated": 0, "not_found": 0, "errors": 0}
    
    try:
        token = get_notion_token()
        if not token:
            workspace_logger.warning("⚠️  Notion token not available")
            return {"synced": 0, "updated": 0, "not_found": 0, "errors": 0}
        
        notion_client = Client(auth=token)
        workspace_logger.info("✅ Notion client initialized")
    except Exception as e:
        workspace_logger.error(f"❌ Failed to initialize Notion client: {e}")
        return {"synced": 0, "updated": 0, "not_found": 0, "errors": 0}
    
    stats = {"synced": 0, "updated": 0, "not_found": 0, "errors": 0}
    
    tracks_to_process = djay_tracks[:limit] if limit else djay_tracks
    total = len(tracks_to_process)
    
    workspace_logger.info(f"🔄 Syncing {total} tracks to Notion...")
    
    for i, track in enumerate(tracks_to_process, 1):
        if i % 100 == 0:
            workspace_logger.info(f"   Progress: {i}/{total}...")
        
        file_name = track.get("fileName")
        bpm = track.get("bpm")
        key = track.get("key")
        
        if not file_name:
            stats["not_found"] += 1
            continue
        
        # Find Notion track by file path
        page_id = find_notion_track_by_path(notion_client, tracks_db_id, file_name)
        
        if page_id:
            if update_notion_track(notion_client, page_id, bpm, key, dry_run):
                stats["updated"] += 1
                stats["synced"] += 1
            else:
                stats["errors"] += 1
        else:
            stats["not_found"] += 1
        
        # Rate limiting
        if not dry_run:
            time.sleep(0.35)  # ~3 requests per second
    
    workspace_logger.info("")
    workspace_logger.info("=" * 80)
    workspace_logger.info("SYNC SUMMARY")
    workspace_logger.info("=" * 80)
    workspace_logger.info(f"Synced: {stats['synced']}")
    workspace_logger.info(f"Updated: {stats['updated']}")
    workspace_logger.info(f"Not Found: {stats['not_found']}")
    workspace_logger.info(f"Errors: {stats['errors']}")
    workspace_logger.info("=" * 80)
    
    return stats


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Sync djay Pro BPM/Key data to Notion Tracks database"
    )
    parser.add_argument(
        "--djay-db",
        type=str,
        default=str(DEFAULT_DJAY_DB_PATH),
        help=f"Path to djay Pro MediaLibrary.db"
    )
    parser.add_argument(
        "--tracks-db-id",
        type=str,
        default=TRACKS_DB_ID,
        help="Notion Tracks database ID"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't actually update Notion"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tracks to process"
    )
    
    args = parser.parse_args()
    
    workspace_logger.info("=" * 80)
    workspace_logger.info("djay Pro BPM/Key Direct Sync to Notion")
    workspace_logger.info("=" * 80)
    workspace_logger.info(f"djay Database: {args.djay_db}")
    workspace_logger.info(f"Notion Tracks DB ID: {args.tracks_db_id}")
    workspace_logger.info(f"Dry Run: {args.dry_run}")
    workspace_logger.info("=" * 80)
    
    try:
        # Extract BPM/Key data from djay
        djay_tracks = extract_bpm_key_data(Path(args.djay_db))
        
        if not djay_tracks:
            workspace_logger.warning("⚠️  No tracks with BPM/Key data found")
            return 1
        
        # Sync to Notion
        stats = sync_to_notion(
            djay_tracks,
            args.tracks_db_id,
            dry_run=args.dry_run,
            limit=args.limit
        )
        
        return 0
        
    except Exception as e:
        workspace_logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
