#!/usr/bin/env python3
"""
Remediate Tracks Artist Metadata - Bulk Cleanup Script
=======================================================

This script fixes tracks in Notion that have incorrect artist metadata caused by:
1. Malformed SoundCloud API URLs being parsed incorrectly (Artist = "tracks")
2. SoundCloud auto-generated usernames (Artist = "user-123456789")

Root Causes:
- SoundCloud search returned API URLs like: api.soundcloud.com/tracks/soundcloud%3Atracks%3A...
  URL parser extracted "tracks" as the artist from the path segment
- SoundCloud users without custom usernames have auto-generated IDs like "user-123456789"
  These should not be used as artist names

This script:
1. Queries Notion for tracks with Artist = "tracks" (the bug value)
2. Queries Notion for tracks with Artist matching "user-*" pattern (auto-generated)
3. Queries Notion for tracks with malformed SoundCloud API URLs
4. Clears the malformed URLs and/or fixes the artist metadata
5. Optionally triggers re-processing to get correct metadata

Usage:
    python remediate_tracks_artist_metadata.py --dry-run    # Preview changes
    python remediate_tracks_artist_metadata.py --execute    # Apply fixes
    python remediate_tracks_artist_metadata.py --execute --clear-urls  # Also clear bad URLs
    python remediate_tracks_artist_metadata.py --execute --include-user-ids  # Also fix user-##### artists

Author: Claude Code Agent
Created: 2026-01-15
Updated: 2026-01-15 - Added user-######### pattern detection and remediation
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urlparse, unquote

# Add project paths
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from unified_config import load_unified_env, get_unified_config
    unified_config = get_unified_config()
    load_unified_env()
except ImportError:
    unified_config = {}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Notion client setup
try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    logger.error("notion-client not installed. Run: pip install notion-client")
    sys.exit(1)

# Configuration
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID") or unified_config.get("tracks_db_id", "27ce7361-6c27-80fb-b40e-fefdd47d6640")


def get_notion_client() -> Optional[Client]:
    """Get authenticated Notion client."""
    try:
        from shared_core.notion.token_manager import get_notion_token
        token = get_notion_token()
    except ImportError:
        token = None

    if not token:
        token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")

    if token:
        return Client(auth=token)

    logger.error("No Notion token found")
    return None


def is_soundcloud_auto_username(name: str) -> bool:
    """
    Detect SoundCloud auto-generated usernames like 'user-123456789'.

    These are assigned to users who haven't set a custom username and should
    not be used as artist names in the music library.

    Examples:
    - user-89644332 -> True
    - user-933123022 -> True
    - user-name -> False (not numeric)
    - artist-name -> False (doesn't start with user-)
    """
    if not name:
        return False
    import re
    # Pattern: 'user-' followed by 6+ digits (SoundCloud user IDs are typically 6-12 digits)
    return bool(re.match(r'^user-\d{6,}$', name.lower().strip()))


def is_invalid_artist_name(name: str) -> bool:
    """
    Check if an artist name is invalid and should be remediated.

    Invalid names include:
    - SoundCloud auto-generated usernames (user-123456789)
    - Reserved SoundCloud path segments (tracks, playlists, etc.)
    - Generic placeholders (Unknown, N/A, Various Artists)
    """
    if not name:
        return True
    name_lower = name.lower().strip()
    reserved = {'tracks', 'playlists', 'sets', 'albums', 'users', 'discover', 'search', 'stream'}
    placeholders = {'unknown', 'unknown artist', 'n/a', 'various artists', 'va', ''}
    if name_lower in reserved:
        return True
    if is_soundcloud_auto_username(name):
        return True
    if name_lower in placeholders:
        return True
    return False


def is_malformed_soundcloud_url(url: str) -> bool:
    """
    Check if a SoundCloud URL is malformed (API URL instead of webpage URL).

    Malformed examples:
    - https://api.soundcloud.com/tracks/soundcloud%3Atracks%3A295158487
    - https://api.soundcloud.com/tracks/12345

    Valid examples:
    - https://soundcloud.com/artist-name/track-name
    - https://m.soundcloud.com/artist-name/track-name
    """
    if not url:
        return False

    parsed = urlparse(url)

    # Check for API subdomain
    if 'api.soundcloud.com' in parsed.netloc:
        return True

    # Check for URL-encoded track IDs in path
    path = unquote(parsed.path)
    if path.startswith('/tracks/') and ('soundcloud:tracks:' in path or path.split('/')[-1].isdigit()):
        return True

    return False


def extract_track_id_from_api_url(url: str) -> Optional[str]:
    """
    Extract the SoundCloud track ID from a malformed API URL.

    Examples:
    - api.soundcloud.com/tracks/soundcloud%3Atracks%3A295158487 -> 295158487
    - api.soundcloud.com/tracks/12345 -> 12345
    """
    if not url:
        return None

    parsed = urlparse(url)
    path = unquote(parsed.path)

    # Pattern 1: /tracks/soundcloud:tracks:ID
    if 'soundcloud:tracks:' in path:
        parts = path.split('soundcloud:tracks:')
        if len(parts) > 1:
            return parts[-1].strip('/')

    # Pattern 2: /tracks/ID
    if path.startswith('/tracks/'):
        track_part = path.replace('/tracks/', '').strip('/')
        if track_part.isdigit():
            return track_part

    return None


def query_tracks_with_bad_artist(notion: Client, limit: int = 1000) -> List[Dict]:
    """Query tracks where Artist Name equals 'tracks' (the bug value)."""
    logger.info("Querying tracks with Artist = 'tracks'...")

    all_results = []
    start_cursor = None

    while True:
        query = {
            "filter": {
                "property": "Artist Name",
                "rich_text": {
                    "equals": "tracks"
                }
            },
            "page_size": 100
        }

        if start_cursor:
            query["start_cursor"] = start_cursor

        try:
            response = notion.databases.query(database_id=TRACKS_DB_ID, **query)
            results = response.get("results", [])
            all_results.extend(results)

            logger.info(f"  Found {len(results)} tracks in this batch (total: {len(all_results)})")

            if not response.get("has_more") or len(all_results) >= limit:
                break

            start_cursor = response.get("next_cursor")

        except Exception as e:
            logger.error(f"Query failed: {e}")
            break

    return all_results[:limit]


def query_tracks_with_auto_generated_artist(notion: Client, limit: int = 1000) -> List[Dict]:
    """
    Query tracks where Artist Name starts with 'user-' (SoundCloud auto-generated).

    Note: Notion's API doesn't support regex, so we use 'starts_with' filter and
    then validate in code that the name matches the user-##### pattern.
    """
    logger.info("Querying tracks with auto-generated artist names (user-######)...")

    all_results = []
    start_cursor = None

    while True:
        query = {
            "filter": {
                "property": "Artist Name",
                "rich_text": {
                    "starts_with": "user-"
                }
            },
            "page_size": 100
        }

        if start_cursor:
            query["start_cursor"] = start_cursor

        try:
            response = notion.databases.query(database_id=TRACKS_DB_ID, **query)
            results = response.get("results", [])

            # Filter to only include results that match the numeric pattern
            for result in results:
                props = result.get("properties", {})
                artist_prop = props.get("Artist Name", {})
                artist_text = ""
                if artist_prop.get("type") == "rich_text":
                    items = artist_prop.get("rich_text", [])
                    artist_text = "".join(item.get("plain_text", "") for item in items)

                if is_soundcloud_auto_username(artist_text):
                    all_results.append(result)

            logger.info(f"  Found {len(results)} 'user-' tracks, {len([r for r in results if is_soundcloud_auto_username(extract_track_info(r).get('artist', ''))])} are auto-generated (total: {len(all_results)})")

            if not response.get("has_more") or len(all_results) >= limit:
                break

            start_cursor = response.get("next_cursor")

        except Exception as e:
            logger.error(f"Query failed: {e}")
            break

    return all_results[:limit]


def query_tracks_with_malformed_urls(notion: Client, limit: int = 1000) -> List[Dict]:
    """Query tracks with SoundCloud URLs containing api.soundcloud.com."""
    logger.info("Querying tracks with malformed SoundCloud URLs...")

    all_results = []
    start_cursor = None

    while True:
        query = {
            "filter": {
                "property": "SoundCloud URL",
                "url": {
                    "contains": "api.soundcloud.com"
                }
            },
            "page_size": 100
        }

        if start_cursor:
            query["start_cursor"] = start_cursor

        try:
            response = notion.databases.query(database_id=TRACKS_DB_ID, **query)
            results = response.get("results", [])
            all_results.extend(results)

            logger.info(f"  Found {len(results)} tracks in this batch (total: {len(all_results)})")

            if not response.get("has_more") or len(all_results) >= limit:
                break

            start_cursor = response.get("next_cursor")

        except Exception as e:
            logger.error(f"Query failed: {e}")
            break

    return all_results[:limit]


def extract_track_info(page: Dict) -> Dict[str, Any]:
    """Extract relevant track information from a Notion page."""
    props = page.get("properties", {})

    def get_text(prop_name: str) -> str:
        prop = props.get(prop_name, {})
        prop_type = prop.get("type", "")

        if prop_type == "title":
            items = prop.get("title", [])
            return "".join(item.get("plain_text", "") for item in items)
        elif prop_type == "rich_text":
            items = prop.get("rich_text", [])
            return "".join(item.get("plain_text", "") for item in items)
        elif prop_type == "url":
            return prop.get("url") or ""

        return ""

    return {
        "page_id": page.get("id", ""),
        "title": get_text("Title") or get_text("Name"),
        "artist": get_text("Artist Name") or get_text("Artist"),
        "soundcloud_url": get_text("SoundCloud URL"),
        "spotify_id": get_text("Spotify ID"),
        "spotify_url": get_text("Spotify URL"),
    }


def fix_track_artist(notion: Client, page_id: str, new_artist: str, dry_run: bool = True) -> bool:
    """Update the artist name for a track."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would update artist to: '{new_artist}'")
        return True

    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Artist Name": {
                    "rich_text": [{"text": {"content": new_artist}}]
                }
            }
        )
        logger.info(f"  Updated artist to: '{new_artist}'")
        return True
    except Exception as e:
        logger.error(f"  Failed to update artist: {e}")
        return False


def clear_soundcloud_url(notion: Client, page_id: str, dry_run: bool = True) -> bool:
    """Clear the malformed SoundCloud URL."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would clear SoundCloud URL")
        return True

    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "SoundCloud URL": {
                    "url": None
                }
            }
        )
        logger.info(f"  Cleared SoundCloud URL")
        return True
    except Exception as e:
        logger.error(f"  Failed to clear URL: {e}")
        return False


def parse_artist_from_title(title: str) -> Optional[str]:
    """
    Try to extract artist name from title patterns like:
    - "Artist - Track Name"
    - "Artist Name - Track Name (feat. Someone)"

    Returns the artist portion if found, None otherwise.
    """
    if not title:
        return None

    # Pattern 1: "Artist - Track" or "Artist — Track"
    for separator in [' - ', ' — ', ' – ']:
        if separator in title:
            parts = title.split(separator, 1)
            if len(parts) >= 2:
                artist = parts[0].strip()
                # Validate it looks like an artist name (not just a word)
                if len(artist) > 1 and not artist.lower() in {'the', 'a', 'an', 'my', 'your'}:
                    return artist

    return None


def get_artist_from_spotify(spotify_id: str) -> Optional[str]:
    """
    Try to get the correct artist from Spotify API using the track ID.
    """
    if not spotify_id:
        return None

    try:
        # Try to import Spotify integration
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials

            client_id = os.getenv("SPOTIFY_CLIENT_ID")
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

            if client_id and client_secret:
                auth_manager = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret
                )
                sp = spotipy.Spotify(auth_manager=auth_manager)

                track = sp.track(spotify_id)
                if track and track.get("artists"):
                    artists = [a.get("name") for a in track["artists"] if a.get("name")]
                    if artists:
                        return ", ".join(artists)

        except ImportError:
            logger.debug("spotipy not available for Spotify lookup")
        except Exception as e:
            logger.debug(f"Spotify lookup failed: {e}")

    except Exception as e:
        logger.debug(f"Error in Spotify artist lookup: {e}")

    return None


def remediate_tracks(
    notion: Client,
    dry_run: bool = True,
    clear_urls: bool = False,
    fix_artist_to: Optional[str] = None,
    include_user_ids: bool = False,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Main remediation function.

    Args:
        notion: Authenticated Notion client
        dry_run: If True, only preview changes
        clear_urls: If True, clear malformed SoundCloud URLs
        fix_artist_to: If provided, set all bad artists to this value
        include_user_ids: If True, also fix user-######### artist names
        limit: Maximum tracks to process

    Returns:
        Summary of actions taken
    """
    results = {
        "tracks_with_bad_artist": 0,
        "tracks_with_auto_username": 0,
        "tracks_with_bad_url": 0,
        "artists_fixed": 0,
        "urls_cleared": 0,
        "errors": 0,
        "details": []
    }

    # Query tracks with bad artist (Artist = "tracks")
    bad_artist_tracks = query_tracks_with_bad_artist(notion, limit)
    results["tracks_with_bad_artist"] = len(bad_artist_tracks)

    # Query tracks with auto-generated usernames (Artist = "user-#######")
    auto_username_tracks = []
    if include_user_ids:
        auto_username_tracks = query_tracks_with_auto_generated_artist(notion, limit)
        results["tracks_with_auto_username"] = len(auto_username_tracks)

    # Query tracks with malformed URLs
    bad_url_tracks = query_tracks_with_malformed_urls(notion, limit)
    results["tracks_with_bad_url"] = len(bad_url_tracks)

    # Combine and deduplicate
    all_track_ids = set()
    all_tracks = []

    for track in bad_artist_tracks + auto_username_tracks + bad_url_tracks:
        page_id = track.get("id")
        if page_id not in all_track_ids:
            all_track_ids.add(page_id)
            all_tracks.append(track)

    logger.info(f"\n{'='*60}")
    logger.info(f"REMEDIATION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Tracks with Artist='tracks': {results['tracks_with_bad_artist']}")
    if include_user_ids:
        logger.info(f"Tracks with Artist='user-######': {results['tracks_with_auto_username']}")
    logger.info(f"Tracks with malformed URLs: {results['tracks_with_bad_url']}")
    logger.info(f"Total unique tracks to process: {len(all_tracks)}")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Clear URLs: {clear_urls}")
    logger.info(f"Include user-IDs: {include_user_ids}")
    logger.info(f"{'='*60}\n")

    # Process each track
    for i, track in enumerate(all_tracks, 1):
        info = extract_track_info(track)
        page_id = info["page_id"]

        logger.info(f"[{i}/{len(all_tracks)}] Processing: {info['title']}")
        logger.info(f"  Current artist: '{info['artist']}'")
        logger.info(f"  SoundCloud URL: {info['soundcloud_url'][:80] if info['soundcloud_url'] else 'None'}...")

        track_detail = {
            "page_id": page_id,
            "title": info["title"],
            "original_artist": info["artist"],
            "original_url": info["soundcloud_url"],
            "actions": []
        }

        # Fix artist if it's invalid ("tracks", "user-######", etc.)
        artist_needs_fix = info["artist"] == "tracks" or (include_user_ids and is_soundcloud_auto_username(info["artist"]))
        if artist_needs_fix:
            original_artist = info["artist"]
            # Try to determine correct artist using multiple sources
            new_artist = None

            # Priority 1: User-specified override
            if fix_artist_to:
                new_artist = fix_artist_to

            # Priority 2: Try Spotify API lookup
            if not new_artist and info["spotify_id"]:
                spotify_artist = get_artist_from_spotify(info["spotify_id"])
                if spotify_artist:
                    new_artist = spotify_artist
                    logger.info(f"  Found artist from Spotify: '{new_artist}'")

            # Priority 3: Parse artist from title (e.g., "Artist - Track Name")
            if not new_artist:
                title_artist = parse_artist_from_title(info["title"])
                if title_artist:
                    new_artist = title_artist
                    logger.info(f"  Parsed artist from title: '{new_artist}'")

            # Fallback: Unknown Artist
            if not new_artist:
                new_artist = "Unknown Artist"
                logger.info(f"  Using fallback: '{new_artist}'")

            if fix_track_artist(notion, page_id, new_artist, dry_run):
                results["artists_fixed"] += 1
                track_detail["actions"].append(f"Fixed artist: {original_artist} -> {new_artist}")
                track_detail["new_artist"] = new_artist
            else:
                results["errors"] += 1
                track_detail["actions"].append("ERROR: Failed to fix artist")

        # Clear malformed URL if requested
        if clear_urls and is_malformed_soundcloud_url(info["soundcloud_url"]):
            track_id = extract_track_id_from_api_url(info["soundcloud_url"])
            logger.info(f"  Extracted track ID: {track_id}")

            if clear_soundcloud_url(notion, page_id, dry_run):
                results["urls_cleared"] += 1
                track_detail["actions"].append(f"Cleared malformed URL (track ID: {track_id})")
            else:
                results["errors"] += 1
                track_detail["actions"].append("ERROR: Failed to clear URL")

        results["details"].append(track_detail)
        logger.info("")

    # Final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"REMEDIATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Artists fixed: {results['artists_fixed']}")
    logger.info(f"URLs cleared: {results['urls_cleared']}")
    logger.info(f"Errors: {results['errors']}")
    logger.info(f"{'='*60}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Remediate tracks with incorrect artist metadata ('tracks' or 'user-######')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually apply the fixes"
    )
    parser.add_argument(
        "--clear-urls",
        action="store_true",
        help="Clear malformed SoundCloud URLs (enables re-discovery)"
    )
    parser.add_argument(
        "--include-user-ids",
        action="store_true",
        help="Also fix 'user-######' auto-generated SoundCloud usernames"
    )
    parser.add_argument(
        "--fix-artist-to",
        type=str,
        default=None,
        help="Set all bad artists to this value (default: 'Unknown Artist')"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum tracks to process (default: 1000)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.dry_run and not args.execute:
        logger.error("Must specify either --dry-run or --execute")
        parser.print_help()
        sys.exit(1)

    dry_run = not args.execute

    logger.info(f"\n{'='*60}")
    logger.info(f"TRACKS ARTIST METADATA REMEDIATION")
    logger.info(f"{'='*60}")
    logger.info(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (applying changes)'}")
    logger.info(f"Clear URLs: {args.clear_urls}")
    logger.info(f"Include user-IDs: {args.include_user_ids}")
    logger.info(f"Limit: {args.limit}")
    logger.info(f"{'='*60}\n")

    # Get Notion client
    notion = get_notion_client()
    if not notion:
        sys.exit(1)

    # Run remediation
    results = remediate_tracks(
        notion=notion,
        dry_run=dry_run,
        clear_urls=args.clear_urls,
        fix_artist_to=args.fix_artist_to,
        include_user_ids=args.include_user_ids,
        limit=args.limit
    )

    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\nResults saved to: {output_path}")

    # Exit with error code if there were errors
    sys.exit(1 if results["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
