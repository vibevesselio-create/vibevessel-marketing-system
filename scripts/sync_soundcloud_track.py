#!/usr/bin/env python3
"""
SoundCloud Single Track Synchronization and Download Script
─────────────────────────────────────────────────────────────────────────────────────
Complete end-to-end single track processing:
1. Extract track metadata from SoundCloud track URL
2. Add track to Notion Music Tracks database (with deduplication)
3. Trigger download workflow for the track
4. Track progress and provide status updates

Usage:
    python sync_soundcloud_track.py <track_url>

Example:
    python sync_soundcloud_track.py "https://soundcloud.com/therust/arches"

Aligned with Seren Media Workspace Standards
Version: 2025-01-27
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

# Load unified environment
try:
    from unified_config import load_unified_env, get_unified_config, setup_unified_logging
    load_unified_env()
    unified_config = get_unified_config()
    logger = setup_unified_logging(session_id="soundcloud_track_sync")
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    print(f"Warning: unified_config unavailable ({unified_err}); using environment variables directly.", file=sys.stderr)
    unified_config = {}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("soundcloud_track_sync")

def get_notion_token() -> Optional[str]:
    """Get Notion API token using canonical shared_core.notion.token_manager"""
    # Use the canonical token manager from shared_core
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_token
        token = _get_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback: direct environment check
    token = (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    if token:
        return token

    try:
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        if token:
            return token
    except Exception:
        pass

    return None

# Import required modules
import yt_dlp

from music_workflow_common import (
    NotionClient,
    build_text_filter,
    normalize_soundcloud_url,
    resolve_property_name,
)

NOTION_TOKEN = get_notion_token()
NOTION_VERSION = unified_config.get("notion_version") or os.getenv("NOTION_VERSION", "2022-06-28")
TRACKS_DB_ID = (unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID") or "").strip()
NOTION_MAX_RETRIES = int(unified_config.get("notion_max_retries") or os.getenv("NOTION_MAX_RETRIES", "5"))
NOTION_RATE_LIMIT = int(unified_config.get("notion_rate_limit") or os.getenv("NOTION_RATE_LIMIT", "60"))
NOTION_TIMEOUT = int(unified_config.get("notion_timeout") or os.getenv("NOTION_TIMEOUT", "30"))

if not NOTION_TOKEN:
    print("❌ NOTION_TOKEN not found in environment or unified_config")
    print("   Checked: NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN")
    sys.exit(1)

if not TRACKS_DB_ID:
    print("❌ TRACKS_DB_ID not found in environment or unified_config")
    sys.exit(1)

# Format database ID
def format_database_id(db_id: str) -> str:
    """Convert 32-char hex to UUID format for Notion API"""
    if not db_id or len(db_id) != 32:
        return db_id
    if '-' in db_id:
        return db_id
    return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"

TRACKS_DB_ID = format_database_id(TRACKS_DB_ID)

notion_client = NotionClient(
    NOTION_TOKEN,
    NOTION_VERSION,
    max_retries=NOTION_MAX_RETRIES,
    rate_limit_per_minute=NOTION_RATE_LIMIT,
    timeout=NOTION_TIMEOUT,
    logger=logger,
)

_DB_PROPERTIES: Optional[Dict[str, Any]] = None


def get_database_properties() -> Dict[str, Any]:
    global _DB_PROPERTIES
    if _DB_PROPERTIES is None:
        try:
            db_info = notion_client.get_database(TRACKS_DB_ID)
            _DB_PROPERTIES = db_info.get("properties", {})
        except Exception as exc:
            logger.warning("Could not fetch tracks database schema: %s", exc)
            _DB_PROPERTIES = {}
    return _DB_PROPERTIES


def get_property_types() -> Dict[str, str]:
    props = get_database_properties()
    return {name: prop.get("type") for name, prop in props.items()}

def extract_track_info(track_url: str) -> Dict[str, Any]:
    """
    Extract track metadata from a SoundCloud track URL using yt-dlp.
    
    Returns:
        Track dictionary with title, artist, url, duration, etc.
    """
    print(f"🔍 Extracting track metadata from: {track_url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,  # We need full track info
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract track info
            info = ydl.extract_info(track_url, download=False)
            
            if not info:
                raise RuntimeError("Failed to extract track information")
            
            raw_url = info.get('webpage_url') or info.get('url', track_url)
            clean_url = normalize_soundcloud_url(raw_url) or raw_url
            
            title = info.get('title', 'Unknown Track')
            artist = info.get('artist') or info.get('uploader') or info.get('creator', 'Unknown Artist')
            duration = info.get('duration', 0)
            
            track_info = {
                'title': title,
                'artist': artist,
                'url': clean_url,
                'duration': duration,
                'original_url': track_url,
            }
            
            print(f"✅ Extracted track info:")
            print(f"   Title: {title}")
            print(f"   Artist: {artist}")
            print(f"   Duration: {duration:.1f}s" if duration else "   Duration: Unknown")
            print(f"   URL: {clean_url}")
            
            return track_info
            
    except Exception as e:
        print(f"❌ Error extracting track info: {e}")
        raise

def check_track_exists(title: str, artist: str, soundcloud_url: str = None) -> Optional[str]:
    """
    Check if a track already exists in Notion database.
    
    Returns page_id if found, None otherwise.
    """
    try:
        prop_types = get_property_types()
        title_prop = resolve_property_name(prop_types, ["Title", "Name"])
        artist_prop = resolve_property_name(prop_types, ["Artist Name", "Artist"])
        url_prop = resolve_property_name(prop_types, ["SoundCloud URL", "SoundCloud"])

        filters = []
        if title and artist and title_prop and artist_prop:
            title_filter = build_text_filter(title_prop, prop_types.get(title_prop, ""), title)
            artist_filter = build_text_filter(artist_prop, prop_types.get(artist_prop, ""), artist)
            if title_filter and artist_filter:
                filters.append({"and": [title_filter, artist_filter]})
        elif title and title_prop:
            title_filter = build_text_filter(title_prop, prop_types.get(title_prop, ""), title)
            if title_filter:
                filters.append(title_filter)

        if soundcloud_url and url_prop:
            candidates = []
            normalized = normalize_soundcloud_url(soundcloud_url)
            for candidate in (soundcloud_url, normalized):
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
            for candidate in candidates:
                url_filter = build_text_filter(url_prop, prop_types.get(url_prop, ""), candidate)
                if url_filter:
                    filters.append(url_filter)

        for filter_payload in filters:
            query = {"filter": filter_payload, "page_size": 1}
            result = notion_client.query_database(TRACKS_DB_ID, query)
            results = result.get("results", [])
            if results:
                return results[0].get("id")
        return None

    except Exception as e:
        logger.warning("Error checking for existing track: %s", e)
        return None

def add_track_to_notion(
    track: Dict[str, Any],
    dry_run: bool = False,
    skip_duplicate_check: bool = False,
) -> Optional[str]:
    """
    Add a track to Notion Music Tracks database.
    
    Returns page_id if created, None if skipped or error.
    """
    title = track.get('title', 'Unknown')
    artist = track.get('artist', 'Unknown')
    url = track.get('url', '')
    
    # Check if track already exists
    if not skip_duplicate_check:
        existing_id = check_track_exists(title, artist, url)
        if existing_id:
            print(f"   ⏭️  Track already exists in Notion (ID: {existing_id})")
            return existing_id
    
    if dry_run:
        print(f"   [DRY RUN] Would create: {title} by {artist}")
        return None
    
    prop_types = get_property_types()
    
    # Build properties
    props = {}
    
    # Title
    for title_name in ["Title", "Name"]:
        if title_name in prop_types:
            if prop_types[title_name] == "title":
                props[title_name] = {"title": [{"text": {"content": title}}]}
                break
            elif prop_types[title_name] == "rich_text":
                props[title_name] = {"rich_text": [{"text": {"content": title}}]}
                break
    
    # Artist Name
    for artist_name in ["Artist Name", "Artist"]:
        if artist_name in prop_types:
            if prop_types[artist_name] == "title":
                props[artist_name] = {"title": [{"text": {"content": artist}}]}
                break
            elif prop_types[artist_name] == "rich_text":
                props[artist_name] = {"rich_text": [{"text": {"content": artist}}]}
                break
    
    # SoundCloud URL
    for sc_name in ["SoundCloud URL", "SoundCloud"]:
        if sc_name in prop_types and url:
            if prop_types[sc_name] == "url":
                props[sc_name] = {"url": url}
                break
            elif prop_types[sc_name] == "rich_text":
                props[sc_name] = {"rich_text": [{"text": {"content": url}}]}
                break
    
    # Create page
    try:
        page = notion_client.create_page(TRACKS_DB_ID, props)
        page_id = page.get("id", "")
        print(f"   ✅ Created track in Notion: {title} by {artist}")
        print(f"   Page ID: {page_id}")
        return page_id
    except Exception as e:
        print(f"   ❌ Failed to create Notion page: {e}")
        return None

def trigger_download_workflow() -> bool:
    """
    Trigger the download workflow to process synced tracks.
    
    Returns True if workflow started successfully.
    """
    print(f"\n{'='*80}")
    print(f"📥 TRIGGERING DOWNLOAD WORKFLOW")
    print(f"{'='*80}\n")
    
    # Import the download script function
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        print(f"❌ Download script not found: {script_path}")
        return False
    
    # Build command - use single mode to process the newest track
    cmd = ["python3", str(script_path), "--mode", "single"]
    
    print(f"🚀 Running: {' '.join(cmd)}\n")
    
    import subprocess
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Failed to run download workflow: {e}")
        return False

def sync_and_download_track(
    track_url: str,
    dry_run: bool = False,
    auto_download: bool = True
) -> Dict[str, Any]:
    """
    Complete track synchronization and download workflow.
    
    This is the main function that handles:
    1. Extract track metadata from URL
    2. Sync track to Notion (with deduplication)
    3. Optionally trigger download workflow
    
    Returns complete statistics.
    """
    print(f"\n{'='*80}")
    print(f"🎵 SOUNDCLOUD TRACK SYNC & DOWNLOAD")
    print(f"{'='*80}\n")
    
    # Step 1: Extract track info
    try:
        track_info = extract_track_info(track_url)
    except Exception as e:
        print(f"❌ Failed to extract track info: {e}")
        return {
            "success": False,
            "error": str(e),
            "track_added": False,
            "download_triggered": False
        }
    
    # Step 2: Add track to Notion
    print(f"\n{'='*80}")
    print(f"📤 ADDING TRACK TO NOTION")
    print(f"{'='*80}\n")
    
    existing_id = check_track_exists(track_info["title"], track_info["artist"], track_info["url"])
    if existing_id:
        print(f"   ⏭️  Track already exists in Notion (ID: {existing_id})")
        page_id = existing_id
    else:
        page_id = add_track_to_notion(track_info, dry_run=dry_run, skip_duplicate_check=True)
    
    if not page_id:
        if dry_run:
            print("\n⚠️  DRY RUN: Track not added to Notion")
            return {
                "success": True,
                "track_added": False,
                "download_triggered": False,
                "track_info": track_info,
                "is_new_track": existing_id is None,
            }
        print("\n❌ Failed to add track to Notion")
        return {
            "success": False,
            "error": "Failed to add track to Notion",
            "track_added": False,
            "download_triggered": False
        }
    
    # Check if this was a new track or existing
    is_new_track = existing_id is None
    
    # Step 3: Trigger download workflow (if requested and not dry run)
    download_triggered = False
    if auto_download and not dry_run:
        if is_new_track:
            download_success = trigger_download_workflow()
            download_triggered = download_success
        else:
            print("\n⚠️  Track already exists - download workflow not triggered")
            print("   (Run download workflow manually if needed)")
    else:
        if dry_run:
            print("\n⚠️  DRY RUN: Download workflow not triggered")
        elif not is_new_track:
            print("\n⚠️  Track already exists - download workflow not triggered")
    
    return {
        "success": True,
        "track_added": True,
        "page_id": page_id,
        "is_new_track": is_new_track,
        "download_triggered": download_triggered,
        "track_info": track_info
    }

def main():
    parser = argparse.ArgumentParser(
        description="Sync and download SoundCloud track",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync and download a track
  python sync_soundcloud_track.py "https://soundcloud.com/therust/arches"
  
  # Dry run (see what would be done without making changes)
  python sync_soundcloud_track.py "https://soundcloud.com/therust/arches" --dry-run
  
  # Sync only (don't trigger download)
  python sync_soundcloud_track.py "https://soundcloud.com/therust/arches" --no-download
        """
    )
    
    parser.add_argument(
        "track_url",
        help="SoundCloud track URL (e.g., https://soundcloud.com/user/track-name)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - show what would be done without making changes"
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Sync to Notion only, don't trigger download workflow"
    )
    parser.add_argument(
        "--results-file",
        help="Optional path to write a JSON results summary"
    )
    
    args = parser.parse_args()
    
    # Validate track URL
    if "soundcloud.com" not in args.track_url.lower():
        print("❌ Error: URL must be a SoundCloud track URL")
        print("   Example: https://soundcloud.com/user/track-name")
        sys.exit(1)

    # Detect playlist URLs (contain /sets/ in the path)
    if "/sets/" in args.track_url.lower():
        print("❌ Error: This appears to be a SoundCloud PLAYLIST URL (contains /sets/)")
        print("   This script is for single tracks only.")
        print("")
        print("   For playlists, use: python sync_soundcloud_playlist.py <playlist_url>")
        print(f"   Example: python sync_soundcloud_playlist.py \"{args.track_url}\"")
        print("")
        print("   Or if you want to process a single track from the playlist,")
        print("   copy the individual track URL from SoundCloud.")
        sys.exit(1)
    
    # Run sync and download
    try:
        stats = sync_and_download_track(
            track_url=args.track_url,
            dry_run=args.dry_run,
            auto_download=not args.no_download
        )

        if args.results_file:
            try:
                results_path = Path(args.results_file)
                results_path.parent.mkdir(parents=True, exist_ok=True)
                with results_path.open("w", encoding="utf-8") as handle:
                    json.dump(stats, handle, indent=2, ensure_ascii=True)
                stats["results_path"] = str(results_path)
            except Exception as exc:
                logger.warning("Failed to write results file %s: %s", args.results_file, exc)
        
        # Print summary
        print(f"\n{'='*80}")
        print(f"📊 SUMMARY")
        print(f"{'='*80}")
        print(f"Track: {stats.get('track_info', {}).get('title', 'Unknown')} by {stats.get('track_info', {}).get('artist', 'Unknown')}")
        print(f"Added to Notion: {'Yes' if stats.get('track_added') else 'No'}")
        print(f"New Track: {'Yes' if stats.get('is_new_track') else 'No (already existed)'}")
        print(f"Download Triggered: {'Yes' if stats.get('download_triggered') else 'No'}")
        if stats.get('page_id'):
            print(f"Notion Page ID: {stats.get('page_id')}")
        print(f"{'='*80}\n")
        
        # Exit with appropriate code
        if stats.get("success"):
            print("✅ Track sync completed successfully!")
            sys.exit(0)
        else:
            print(f"❌ Track sync completed with errors: {stats.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()










































































