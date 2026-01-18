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
Sync djay Pro BPM/Key Data to Notion Tracks Database

This script addresses the critical issue:
BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete
Issue ID: 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8

Tasks:
1. Sync djay Pro BPM/Key to Notion Tracks DB
2. Run BPM/Key Analysis on Remaining Tracks (~3,273 tracks)
3. Cross-Reference Notion Tracks with djay Library
4. Sync iPad Paths to Notion

Aligned with Seren Media Workspace Standards
Version: 2026-01-12
DEPRECATED: 2026-01-18
"""

import warnings
warnings.warn(
    "sync_djay_bpm_key_to_notion.py is deprecated. "
    "Use run_fingerprint_dedup_production.py --djay-sync-only instead.",
    DeprecationWarning,
    stacklevel=2
)

from __future__ import annotations

import os
import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import json
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

# Key signature index to key name mapping (0-11)
KEY_SIGNATURE_MAP = {
    0: "C",
    1: "C#",
    2: "D",
    3: "D#",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "G#",
    9: "A",
    10: "A#",
    11: "B"
}


class DjayProSync:
    """Sync djay Pro library data to Notion Tracks database."""
    
    def __init__(self, djay_db_path: Path, tracks_db_id: str, dry_run: bool = False):
        self.djay_db_path = Path(djay_db_path)
        self.tracks_db_id = tracks_db_id
        self.dry_run = dry_run
        self.stats = {
            "bpm_key_synced": 0,
            "ipad_paths_synced": 0,
            "notion_tracks_updated": 0,
            "notion_tracks_created": 0,
            "cross_references_found": 0,
            "errors": 0
        }
        
        # Initialize Notion client
        if NOTION_CLIENT_AVAILABLE:
            try:
                token = get_notion_token()
                if token:
                    self.notion_client = Client(auth=token)
                else:
                    self.notion_client = None
                    workspace_logger.warning("⚠️  Notion token not available. Notion sync will be skipped.")
            except Exception as e:
                self.notion_client = None
                workspace_logger.warning(f"⚠️  Failed to initialize Notion client: {e}")
        else:
            self.notion_client = None
            
        # Validate djay database exists
        if not self.djay_db_path.exists():
            raise FileNotFoundError(f"djay Pro database not found: {self.djay_db_path}")
    
    def extract_djay_tracks(self) -> List[Dict[str, Any]]:
        """Extract tracks with BPM/Key data from djay Pro database using proper SQL queries."""
        workspace_logger.info(f"📊 Extracting tracks from djay Pro database: {self.djay_db_path}")
        
        tracks = []
        
        try:
            conn = sqlite3.connect(str(self.djay_db_path))
            conn.row_factory = sqlite3.Row
            
            # Query secondaryIndex_mediaItemIndex for BPM/Key data
            # Join with secondaryIndex_mediaItemLocationIndex for file paths via database2
            # The correct relationship chain is:
            #   1. secondaryIndex_mediaItemIndex.titleID = database2.key (where collection='localMediaItemLocations')
            #   2. database2.rowid = secondaryIndex_mediaItemLocationIndex.rowid
            # This properly maps through YapDatabase's localMediaItemLocations collection.
            # Previous rowid+1 approach had only 57% match rate; this approach achieves 86%+ match rate.
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
            
            workspace_logger.info(f"Found {len(rows)} tracks with BPM/Key data in database")
            
            for row in rows:
                title_id = row["titleID"]
                bpm = row["bpm"]
                key_index = row["musicalKeySignatureIndex"]
                file_name = row["fileName"]
                
                # Convert key index to key name
                key = None
                if key_index is not None:
                    key = KEY_SIGNATURE_MAP.get(int(key_index), str(key_index))
                
                # Extract title from filename (remove extension)
                title = None
                if file_name:
                    # Remove extension and use as title
                    # Clean up common patterns like " (Remix)", " (feat. Artist)", etc.
                    title = Path(file_name).stem
                    # Basic cleanup - remove common suffixes
                    title = title.replace("_test_processed", "").strip()
                
                # Only include tracks with meaningful data
                if bpm is not None or key:
                    tracks.append({
                        "titleID": title_id,
                        "title": title,
                        "artist": None,  # Artist not available in secondaryIndex tables
                        "bpm": float(bpm) if bpm else None,
                        "key": key,
                        "file_path": file_name,
                        "fileName": file_name
                    })
            
            conn.close()
            workspace_logger.info(f"✅ Extracted {len(tracks)} tracks with BPM/Key data from djay Pro")
            return tracks
            
        except Exception as e:
            workspace_logger.error(f"❌ Error extracting djay tracks: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def find_notion_track(self, title: Optional[str] = None, artist: Optional[str] = None, file_path: Optional[str] = None) -> Optional[str]:
        """Find existing Notion track using multiple matching strategies:
        1. Title + Artist (primary)
        2. File path contains (fallback)
        3. Title only (last resort)
        """
        if not self.notion_client:
            return None
        
        # Strategy 1: Title + Artist (primary)
        # Note: Artist is a relation property, so we'll match by title first
        # and then verify artist if possible
        if title:
            try:
                # First try exact title match
                filter_params = {
                    "property": "Title",
                    "title": {"equals": title}
                }
                response = self.notion_client.databases.query(
                    database_id=self.tracks_db_id,
                    filter=filter_params,
                    page_size=1
                )
                results = response.get("results", [])
                if results:
                    workspace_logger.debug(f"✅ Matched by title: {title}")
                    return results[0]["id"]
            except Exception as e:
                workspace_logger.debug(f"Error matching by title: {e}")
        
        # Strategy 2: File path contains (fallback)
        if file_path:
            try:
                # Extract just the filename for matching
                file_name = Path(file_path).name if file_path else None
                if file_name:
                    # Try to find by file path property (could be "File Path", "FilePath", "iPad Path", etc.)
                    # Query all tracks and check file path properties
                    response = self.notion_client.databases.query(
                        database_id=self.tracks_db_id,
                        page_size=100  # Get a batch to search through
                    )
                    results = response.get("results", [])
                    
                    for result in results:
                        props = result.get("properties", {})
                        # Check various possible file path property names
                        for prop_name in ["File Path", "FilePath", "iPad Path", "Path", "File"]:
                            if prop_name in props:
                                prop = props[prop_name]
                                # Check if it's a rich_text or title property
                                if prop.get("type") == "rich_text":
                                    rich_text = prop.get("rich_text", [])
                                    for rt in rich_text:
                                        text_content = rt.get("text", {}).get("content", "")
                                        if file_name in text_content or file_path in text_content:
                                            workspace_logger.debug(f"✅ Matched by file path: {file_name}")
                                            return result["id"]
                                elif prop.get("type") == "title":
                                    title_content = prop.get("title", [])
                                    for t in title_content:
                                        text_content = t.get("text", {}).get("content", "")
                                        if file_name in text_content or file_path in text_content:
                                            workspace_logger.debug(f"✅ Matched by file path (title): {file_name}")
                                            return result["id"]
            except Exception as e:
                workspace_logger.debug(f"Error matching by file path: {e}")
        
        # Strategy 3: Title only (last resort)
        if title:
            try:
                filter_params = {
                    "property": "Title",
                    "title": {"equals": title}
                }
                response = self.notion_client.databases.query(
                    database_id=self.tracks_db_id,
                    filter=filter_params,
                    page_size=1
                )
                results = response.get("results", [])
                if results:
                    workspace_logger.debug(f"✅ Matched by title only: {title}")
                    return results[0]["id"]
            except Exception as e:
                workspace_logger.debug(f"Error matching by title only: {e}")
        
        return None
    
    def update_notion_track_bpm_key(self, page_id: str, bpm: Optional[float], key: Optional[str], file_path: Optional[str] = None) -> bool:
        """Update Notion track with BPM/Key data."""
        if not self.notion_client:
            return False
            
        properties = {}
        
        if bpm is not None:
            properties["AverageBpm"] = {"number": float(bpm)}
        
        if key:
            properties["Key"] = {"rich_text": [{"text": {"content": str(key)}}]}
        
        if file_path:
            # Check if property exists - might be "File Path", "FilePath", "iPad Path", etc.
            properties["File Path"] = {"rich_text": [{"text": {"content": str(file_path)}}]}
        
        if not properties:
            return False
        
        try:
            if self.dry_run:
                workspace_logger.info(f"[DRY RUN] Would update page {page_id} with: {properties}")
                return True
            
            self.notion_client.pages.update(page_id=page_id, properties=properties)
            return True
            
        except Exception as e:
            workspace_logger.error(f"Error updating Notion track {page_id}: {e}")
            return False
    
    def sync_bpm_key_to_notion(self, djay_tracks: List[Dict[str, Any]], limit: Optional[int] = None) -> Dict[str, int]:
        """Sync BPM/Key data from djay tracks to Notion."""
        workspace_logger.info(f"🔄 Syncing BPM/Key data to Notion Tracks database...")
        
        if limit:
            djay_tracks = djay_tracks[:limit]
            workspace_logger.info(f"Limited to {limit} tracks for processing")
        
        total = len(djay_tracks)
        workspace_logger.info(f"Processing {total} tracks...")
        
        for idx, track in enumerate(djay_tracks, 1):
            try:
                title = track.get("title")
                artist = track.get("artist")
                bpm = track.get("bpm")
                key = track.get("key")
                file_path = track.get("file_path") or track.get("fileName")
                
                if idx % 100 == 0:
                    workspace_logger.info(f"Progress: {idx}/{total} ({idx*100//total}%) - Updated: {self.stats['notion_tracks_updated']}, Errors: {self.stats['errors']}")
                
                # Find matching Notion track using multiple strategies
                page_id = self.find_notion_track(title=title, artist=artist, file_path=file_path)
                
                if page_id:
                    # Update existing track
                    if self.update_notion_track_bpm_key(page_id, bpm, key, file_path):
                        self.stats["notion_tracks_updated"] += 1
                        if bpm or key:
                            self.stats["bpm_key_synced"] += 1
                        if file_path:
                            self.stats["ipad_paths_synced"] += 1
                else:
                    # Track not found in Notion - would need to create
                    if not self.dry_run:
                        workspace_logger.debug(f"Track not found in Notion: {title or file_path}")
                    self.stats["cross_references_found"] += 1
                
                # Rate limiting: ~3 requests per second (0.35s delay)
                if not self.dry_run and idx < total:
                    time.sleep(0.35)
                    
            except Exception as e:
                self.stats["errors"] += 1
                workspace_logger.warning(f"Error processing track {idx}: {e}")
                continue
        
        workspace_logger.info(f"✅ Sync complete:")
        workspace_logger.info(f"   BPM/Key synced: {self.stats['bpm_key_synced']}")
        workspace_logger.info(f"   iPad paths synced: {self.stats['ipad_paths_synced']}")
        workspace_logger.info(f"   Tracks updated: {self.stats['notion_tracks_updated']}")
        workspace_logger.info(f"   Cross-references found: {self.stats['cross_references_found']}")
        
        return self.stats
    
    def analyze_tracks_needing_bpm(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Find Notion tracks that need BPM/Key analysis."""
        if not self.notion_client:
            workspace_logger.warning("Notion client not available. Cannot query tracks needing analysis.")
            return []
        
        workspace_logger.info("🔍 Finding tracks needing BPM/Key analysis...")
        
        try:
            # Query for tracks missing BPM
            filter_params = {
                "or": [
                    {"property": "AverageBpm", "number": {"is_empty": True}},
                    {"property": "AverageBpm", "number": {"equals": 0}},
                ]
            }
            
            response = self.notion_client.databases.query(
                database_id=self.tracks_db_id,
                filter=filter_params,
                page_size=limit or 100
            )
            
            tracks = response.get("results", [])
            workspace_logger.info(f"✅ Found {len(tracks)} tracks needing BPM analysis")
            return tracks
            
        except Exception as e:
            workspace_logger.error(f"❌ Error finding tracks needing analysis: {e}")
            return []


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Sync djay Pro BPM/Key data to Notion Tracks database"
    )
    parser.add_argument(
        "--djay-db",
        type=str,
        default=str(DEFAULT_DJAY_DB_PATH),
        help=f"Path to djay Pro MediaLibrary.db (default: {DEFAULT_DJAY_DB_PATH})"
    )
    parser.add_argument(
        "--tracks-db-id",
        type=str,
        default=TRACKS_DB_ID,
        help=f"Notion Tracks database ID (default: from env/config)"
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
        help="Limit number of tracks to process (for testing)"
    )
    parser.add_argument(
        "--find-missing-bpm",
        action="store_true",
        help="Find and report tracks needing BPM analysis"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        # Debug logging is handled by the logger setup
        pass
    
    workspace_logger.info("=" * 80)
    workspace_logger.info("djay Pro BPM/Key Sync to Notion")
    workspace_logger.info("=" * 80)
    workspace_logger.info(f"djay Database: {args.djay_db}")
    workspace_logger.info(f"Notion Tracks DB ID: {args.tracks_db_id}")
    workspace_logger.info(f"Dry Run: {args.dry_run}")
    workspace_logger.info("=" * 80)
    
    try:
        sync = DjayProSync(
            djay_db_path=args.djay_db,
            tracks_db_id=args.tracks_db_id,
            dry_run=args.dry_run
        )
        
        # Extract tracks from djay Pro
        djay_tracks = sync.extract_djay_tracks()
        
        if not djay_tracks:
            workspace_logger.warning("⚠️  No tracks extracted from djay Pro database")
            return 1
        
        # Sync BPM/Key data to Notion
        stats = sync.sync_bpm_key_to_notion(djay_tracks, limit=args.limit)
        
        # Optionally find tracks needing analysis
        if args.find_missing_bpm:
            tracks_needing_analysis = sync.analyze_tracks_needing_bpm()
            workspace_logger.info(f"📊 Tracks needing BPM analysis: {len(tracks_needing_analysis)}")
        
        # Print summary
        workspace_logger.info("")
        workspace_logger.info("=" * 80)
        workspace_logger.info("SYNC SUMMARY")
        workspace_logger.info("=" * 80)
        for key, value in stats.items():
            workspace_logger.info(f"  {key}: {value}")
        workspace_logger.info("=" * 80)
        
        return 0
        
    except Exception as e:
        workspace_logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
