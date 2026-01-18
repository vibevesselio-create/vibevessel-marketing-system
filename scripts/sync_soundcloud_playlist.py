#!/usr/bin/env python3
"""
SoundCloud Playlist Synchronization and Download Script
─────────────────────────────────────────────────────────────────────────────────────
Complete end-to-end playlist processing:
1. Extract all tracks from SoundCloud playlist URL
2. Add tracks to Notion Music Tracks database (with deduplication)
3. Trigger download workflow for all tracks
4. Track progress and provide status updates

Usage:
    python sync_soundcloud_playlist.py <playlist_url> [--playlist-name NAME] [--max-tracks N] [--dry-run]

Example:
    python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --playlist-name "My Playlist"

Aligned with Seren Media Workspace Standards
Version: 2025-12-31
"""
import os
import sys
import json
import argparse
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
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
    logger = setup_unified_logging(session_id="soundcloud_playlist_sync")
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    print(f"Warning: unified_config unavailable ({unified_err}); using environment variables directly.", file=sys.stderr)
    unified_config = {}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("soundcloud_playlist_sync")

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
PLAYLISTS_DB_ID = (
    unified_config.get("playlists_db_id")
    or os.getenv("PLAYLISTS_DB_ID")
    or os.getenv("MUSIC_PLAYLISTS_DB_ID")
    or ""
).strip()

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
PLAYLISTS_DB_ID = format_database_id(PLAYLISTS_DB_ID) if PLAYLISTS_DB_ID else ""

notion_client = NotionClient(
    NOTION_TOKEN,
    NOTION_VERSION,
    max_retries=NOTION_MAX_RETRIES,
    rate_limit_per_minute=NOTION_RATE_LIMIT,
    timeout=NOTION_TIMEOUT,
    logger=logger,
)

_DB_PROPERTIES: Optional[Dict[str, Any]] = None
_PLAYLIST_DB_PROPERTIES: Optional[Dict[str, Any]] = None
_PLAYLIST_PAGE_CACHE: Dict[str, str] = {}


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


def get_playlist_database_properties() -> Dict[str, Any]:
    global _PLAYLIST_DB_PROPERTIES
    if _PLAYLIST_DB_PROPERTIES is None:
        if not PLAYLISTS_DB_ID:
            _PLAYLIST_DB_PROPERTIES = {}
        else:
            try:
                db_info = notion_client.get_database(PLAYLISTS_DB_ID)
                _PLAYLIST_DB_PROPERTIES = db_info.get("properties", {})
            except Exception as exc:
                logger.warning("Could not fetch playlists database schema: %s", exc)
                _PLAYLIST_DB_PROPERTIES = {}
    return _PLAYLIST_DB_PROPERTIES


def get_property_types() -> Dict[str, str]:
    props = get_database_properties()
    return {name: prop.get("type") for name, prop in props.items()}


def get_playlist_title_prop() -> Optional[str]:
    props = get_playlist_database_properties()
    for name, prop in props.items():
        if prop.get("type") == "title":
            return name
    return None


def ensure_playlist_page(playlist_name: str) -> Optional[str]:
    if not PLAYLISTS_DB_ID or not playlist_name:
        return None
    cached = _PLAYLIST_PAGE_CACHE.get(playlist_name)
    if cached:
        return cached

    title_prop = get_playlist_title_prop()
    if not title_prop:
        logger.warning("Playlist database missing title property; skipping relation.")
        return None

    query = {"filter": {"property": title_prop, "title": {"equals": playlist_name}}, "page_size": 1}
    try:
        result = notion_client.query_database(PLAYLISTS_DB_ID, query)
        results = result.get("results", [])
        if results:
            page_id = results[0].get("id")
            if page_id:
                _PLAYLIST_PAGE_CACHE[playlist_name] = page_id
                return page_id
    except Exception as exc:
        logger.warning("Failed to query playlist database: %s", exc)

    try:
        page = notion_client.create_page(
            PLAYLISTS_DB_ID,
            {title_prop: {"title": [{"text": {"content": playlist_name}}]}},
        )
        page_id = page.get("id")
        if page_id:
            _PLAYLIST_PAGE_CACHE[playlist_name] = page_id
            return page_id
    except Exception as exc:
        logger.warning("Failed to create playlist page: %s", exc)
    return None

def extract_playlist_tracks(playlist_url: str) -> List[Dict[str, Any]]:
    """
    Extract all tracks from a SoundCloud playlist URL using yt-dlp.
    
    Returns:
        List of track dictionaries with title, artist, url, etc.
    """
    print(f"🔍 Extracting tracks from playlist: {playlist_url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,  # We need full track info
        'playlistend': None,  # Get all tracks
    }
    
    tracks = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract playlist info
            info = ydl.extract_info(playlist_url, download=False)
            
            if not info:
                raise RuntimeError("Failed to extract playlist information")
            
            playlist_name = info.get('title', 'Unknown Playlist')
            print(f"📋 Playlist: {playlist_name}")
            
            # Get playlist entries
            entries = info.get('entries', [])
            if not entries:
                print("⚠️  No tracks found in playlist")
                return []
            
            print(f"🎵 Found {len(entries)} tracks in playlist")
            
            # Extract track information
            for i, entry in enumerate(entries, 1):
                if not entry:
                    continue
                
                raw_url = entry.get('webpage_url') or entry.get('url', '')
                track_url = normalize_soundcloud_url(raw_url)
                title = entry.get('title', 'Unknown Track')
                artist = entry.get('artist') or entry.get('uploader', 'Unknown Artist')
                
                tracks.append({
                    'title': title,
                    'artist': artist,
                    'url': track_url or raw_url,
                    'original_url': raw_url,
                    'playlist_name': playlist_name,
                    'playlist_url': playlist_url,
                    'track_number': i,
                })
            
            print(f"✅ Extracted {len(tracks)} tracks")
            return tracks
            
    except Exception as e:
        print(f"❌ Error extracting playlist: {e}")
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


def update_track_playlist_relation(
    page_id: str,
    playlist_name: str,
    playlist_url: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """
    Update an existing track's playlist relation to include the new playlist.

    For relation properties: appends the playlist (doesn't replace existing relations)
    For multi_select: adds the option (doesn't replace existing selections)

    Returns True if updated successfully.
    """
    if not page_id or not playlist_name:
        return False

    if not notion_client:
        logger.warning("Notion client not available for playlist relation update")
        return False

    try:
        prop_types = get_property_types()
        if not prop_types:
            return False

        playlist_prop_name = resolve_property_name(
            prop_types,
            [
                "Playlist",
                "Playlists",
                "Playlist Name",
                "Playlist Names",
                "Playlist Title",
                "Playlist Relation",
                "Related Playlists",
            ],
        )

        if not playlist_prop_name:
            logger.debug("No playlist property found in database")
            return False

        playlist_prop_type = prop_types.get(playlist_prop_name)

        # Get current page to read existing relation values
        try:
            current_page = notion_client.get_page(page_id)
            current_props = current_page.get("properties", {})
        except Exception as e:
            logger.warning(f"Failed to get current page for relation update: {e}")
            return False

        update_props = {}

        if playlist_prop_type == "relation":
            playlist_page_id = ensure_playlist_page(playlist_name)
            if playlist_page_id:
                # Get existing relations
                existing_relations = current_props.get(playlist_prop_name, {}).get("relation", [])
                existing_ids = {r.get("id") for r in existing_relations}

                # Only add if not already linked
                if playlist_page_id not in existing_ids:
                    new_relations = list(existing_relations) + [{"id": playlist_page_id}]
                    update_props[playlist_prop_name] = {"relation": new_relations}
                else:
                    logger.debug(f"Track already linked to playlist {playlist_name}")
                    return True  # Already linked, no update needed

        elif playlist_prop_type == "multi_select":
            # Get existing selections
            existing_selections = current_props.get(playlist_prop_name, {}).get("multi_select", [])
            existing_names = {s.get("name") for s in existing_selections}

            # Only add if not already selected
            if playlist_name not in existing_names:
                new_selections = list(existing_selections) + [{"name": playlist_name}]
                update_props[playlist_prop_name] = {"multi_select": new_selections}
            else:
                logger.debug(f"Track already has playlist {playlist_name} selected")
                return True

        elif playlist_prop_type == "select":
            # Select can only have one value - overwrite if different
            current_select = current_props.get(playlist_prop_name, {}).get("select", {})
            current_name = current_select.get("name") if current_select else None
            if current_name != playlist_name:
                update_props[playlist_prop_name] = {"select": {"name": playlist_name}}
            else:
                return True

        elif playlist_prop_type == "rich_text":
            # Append to existing text
            existing_text = ""
            rt = current_props.get(playlist_prop_name, {}).get("rich_text", [])
            if rt:
                existing_text = "".join(t.get("plain_text", "") for t in rt)

            if playlist_name not in existing_text:
                new_text = f"{existing_text}, {playlist_name}" if existing_text else playlist_name
                update_props[playlist_prop_name] = {"rich_text": [{"text": {"content": new_text}}]}
            else:
                return True

        if not update_props:
            return True  # No update needed

        if dry_run:
            logger.info(f"[DRY RUN] Would update playlist relation for {page_id[:8]}")
            return True

        # Update the page
        notion_client.update_page(page_id, update_props)
        logger.info(f"✅ Updated playlist relation to include: {playlist_name}")
        return True

    except Exception as e:
        logger.warning(f"Error updating playlist relation: {e}")
        return False


def add_track_to_notion(
    track: Dict[str, Any],
    dry_run: bool = False,
    skip_duplicate_check: bool = False
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
            print(f"   ⏭️  Skipped (exists): {title} by {artist}")
            return existing_id
    
    if dry_run:
        print(f"   [DRY RUN] Would create: {title} by {artist}")
        return None
    
    prop_types = get_property_types()
    db_props = get_database_properties()
    
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
    
    # Playlist metadata (if available)
    playlist_name = track.get("playlist_name")
    playlist_url = track.get("playlist_url")
    playlist_prop_name = resolve_property_name(
        prop_types,
        [
            "Playlist",
            "Playlists",
            "Playlist Name",
            "Playlist Names",
            "Playlist Title",
            "Playlist Relation",
            "Related Playlists",
        ],
    )
    if playlist_prop_name and playlist_name:
        playlist_prop_type = prop_types.get(playlist_prop_name)
        if playlist_prop_type == "relation":
            playlist_page_id = ensure_playlist_page(playlist_name)
            if playlist_page_id:
                props[playlist_prop_name] = {"relation": [{"id": playlist_page_id}]}
        elif playlist_prop_type == "multi_select":
            props[playlist_prop_name] = {"multi_select": [{"name": playlist_name}]}
        elif playlist_prop_type == "select":
            options = db_props.get(playlist_prop_name, {}).get("select", {}).get("options", [])
            option_names = {opt.get("name") for opt in options}
            if playlist_name in option_names:
                props[playlist_prop_name] = {"select": {"name": playlist_name}}
            else:
                logger.warning("Playlist select option '%s' missing; skipping", playlist_name)
        elif playlist_prop_type == "rich_text":
            props[playlist_prop_name] = {"rich_text": [{"text": {"content": playlist_name}}]}
        elif playlist_prop_type == "title":
            props[playlist_prop_name] = {"title": [{"text": {"content": playlist_name}}]}

    playlist_url_prop = resolve_property_name(
        prop_types,
        ["Playlist URL", "SoundCloud Playlist URL", "Playlist Link"],
    )
    if playlist_url and playlist_url_prop:
        playlist_url_type = prop_types.get(playlist_url_prop)
        if playlist_url_type == "url":
            props[playlist_url_prop] = {"url": playlist_url}
        elif playlist_url_type == "rich_text":
            props[playlist_url_prop] = {"rich_text": [{"text": {"content": playlist_url}}]}

    # Create page
    try:
        page = notion_client.create_page(TRACKS_DB_ID, props)
        page_id = page.get("id", "")
        print(f"   ✅ Created: {title} by {artist}")
        return page_id
    except Exception as e:
        print(f"   ❌ Failed: {title} by {artist} - {e}")
        return None


def default_checkpoint_path(playlist_name: Optional[str]) -> Path:
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "playlist"
    if playlist_name:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", playlist_name.strip().lower()).strip("-") or "playlist"
    return logs_dir / f"playlist_sync_checkpoint_{safe_name}.json"


def load_checkpoint(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load checkpoint %s: %s", path, exc)
    return {}


def save_checkpoint(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
    except Exception as exc:
        logger.warning("Failed to save checkpoint %s: %s", path, exc)


def default_results_path() -> Path:
    logs_dir = Path(__file__).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return logs_dir / f"playlist_sync_results_{ts}.json"

def get_checkpoint_key(track: Dict[str, Any]) -> str:
    return (
        track.get("url")
        or track.get("original_url")
        or f"{track.get('title', '')}::{track.get('artist', '')}::{track.get('track_number', '')}"
    )


def sync_playlist_to_notion(
    playlist_url: str,
    playlist_name: Optional[str] = None,
    max_tracks: Optional[int] = None,
    dry_run: bool = False,
    checkpoint_path: Optional[Path] = None,
    resume: bool = False,
    use_checkpoint: bool = True,
) -> Dict[str, Any]:
    """
    Synchronize a SoundCloud playlist to Notion.
    
    Returns sync statistics.
    """
    print(f"\n{'='*80}")
    print(f"🔄 SYNCING PLAYLIST TO NOTION")
    print(f"{'='*80}")
    print(f"Playlist URL: {playlist_url}")
    if playlist_name:
        print(f"Playlist Name: {playlist_name}")
    if max_tracks:
        print(f"Max Tracks: {max_tracks}")
    if dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print(f"{'='*80}\n")
    
    # Extract tracks from playlist
    try:
        tracks = extract_playlist_tracks(playlist_url)
    except Exception as e:
        print(f"❌ Failed to extract playlist tracks: {e}")
        return {
            "success": False,
            "error": str(e),
            "tracks_added": 0,
            "tracks_skipped": 0,
            "tracks_updated": 0,
            "errors": 1
        }
    
    if not tracks:
        print("⚠️  No tracks found in playlist")
        return {
            "success": True,
            "tracks_added": 0,
            "tracks_skipped": 0,
            "tracks_updated": 0,
            "errors": 0
        }

    if not playlist_name:
        playlist_name = tracks[0].get("playlist_name") or playlist_name

    if use_checkpoint and checkpoint_path is None:
        checkpoint_path = default_checkpoint_path(playlist_name)

    if checkpoint_path:
        checkpoint_state = "resume" if resume else "new"
        print(f"Checkpoint: {checkpoint_path} ({checkpoint_state})")
    
    # Limit tracks if specified
    if max_tracks and max_tracks > 0:
        tracks = tracks[:max_tracks]
        print(f"📊 Limited to {max_tracks} tracks\n")
    
    default_stats = {
        "tracks_added": 0,
        "tracks_skipped": 0,
        "tracks_updated": 0,
        "errors": 0,
        "track_ids": [],
        "tracks_processed": 0,
    }

    checkpoint_payload: Dict[str, Any] = {}
    processed_keys: set[str] = set()

    if checkpoint_path:
        if resume:
            checkpoint_payload = load_checkpoint(checkpoint_path)
            processed_keys = set(checkpoint_payload.get("processed", {}).keys())
            stats = checkpoint_payload.get("stats", default_stats)
            if checkpoint_payload.get("playlist_url") and checkpoint_payload.get("playlist_url") != playlist_url:
                logger.warning(
                    "Checkpoint playlist URL mismatch (%s != %s)",
                    checkpoint_payload.get("playlist_url"),
                    playlist_url,
                )
            if "track_ids" not in stats:
                stats["track_ids"] = []
            if "tracks_processed" not in stats:
                stats["tracks_processed"] = len(processed_keys)
        else:
            stats = default_stats
            checkpoint_payload = {
                "playlist_url": playlist_url,
                "playlist_name": playlist_name,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "processed": {},
                "stats": stats,
            }
            save_checkpoint(checkpoint_path, checkpoint_payload)
    else:
        stats = default_stats

    stats["tracks_total"] = len(tracks)
    
    print(f"📤 Adding {len(tracks)} tracks to Notion...\n")
    
    for i, track in enumerate(tracks, 1):
        print(f"[{i}/{len(tracks)}] {track['title']} by {track['artist']}")

        checkpoint_key = get_checkpoint_key(track)
        if checkpoint_key in processed_keys:
            continue
        
        existing_id = check_track_exists(track["title"], track["artist"], track.get("url"))
        status = "skipped"
        if existing_id:
            print(f"   ⏭️  Exists: {track['title']} by {track['artist']}")
            # UPDATE: Link existing track to this playlist
            playlist_name = track.get("playlist_name")
            if playlist_name and not dry_run:
                if update_track_playlist_relation(existing_id, playlist_name, track.get("playlist_url"), dry_run):
                    print(f"      ✅ Linked to playlist: {playlist_name}")
                    status = "linked"
                else:
                    print(f"      ⚠️  Could not link to playlist: {playlist_name}")
            stats["tracks_skipped"] += 1
            stats["track_ids"].append(existing_id)
            page_id = existing_id
        else:
            page_id = add_track_to_notion(track, dry_run=dry_run, skip_duplicate_check=True)

            if page_id:
                stats["tracks_added"] += 1
                stats["track_ids"].append(page_id)
                status = "added"
            else:
                status = "error"
                if not dry_run:
                    stats["errors"] += 1

        stats["tracks_processed"] += 1
        if checkpoint_path:
            checkpoint_payload.setdefault("processed", {})[checkpoint_key] = {
                "status": status,
                "page_id": page_id,
            }
            checkpoint_payload["stats"] = stats
            save_checkpoint(checkpoint_path, checkpoint_payload)
    
    print(f"\n{'='*80}")
    print(f"✅ SYNC COMPLETE")
    print(f"{'='*80}")
    print(f"Tracks Added: {stats['tracks_added']}")
    print(f"Tracks Skipped: {stats['tracks_skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"{'='*80}\n")
    
    stats["success"] = stats["errors"] == 0
    return stats

def trigger_download_workflow(max_tracks: Optional[int] = None) -> bool:
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
    
    # Build command
    cmd = ["python3", str(script_path), "--mode", "playlist"]
    if max_tracks:
        cmd.extend(["--limit", str(max_tracks)])
    
    print(f"🚀 Running: {' '.join(cmd)}\n")
    
    import subprocess
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Failed to run download workflow: {e}")
        return False

def sync_and_download_playlist(
    playlist_url: str,
    playlist_name: Optional[str] = None,
    max_tracks: Optional[int] = None,
    dry_run: bool = False,
    auto_download: bool = True,
    checkpoint_path: Optional[Path] = None,
    resume: bool = False,
    use_checkpoint: bool = True,
    results_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Complete playlist synchronization and download workflow.
    
    This is the main function that handles:
    1. Extract tracks from playlist URL
    2. Sync tracks to Notion (with deduplication)
    3. Optionally trigger download workflow
    
    Returns complete statistics.
    """
    print(f"\n{'='*80}")
    print(f"🎵 SOUNDCLOUD PLAYLIST SYNC & DOWNLOAD")
    print(f"{'='*80}\n")
    
    # Step 1: Sync playlist to Notion
    sync_stats = sync_playlist_to_notion(
        playlist_url=playlist_url,
        playlist_name=playlist_name,
        max_tracks=max_tracks,
        dry_run=dry_run,
        checkpoint_path=checkpoint_path,
        resume=resume,
        use_checkpoint=use_checkpoint,
    )
    
    if not sync_stats.get("success"):
        return sync_stats
    
    # Step 2: Trigger download workflow (if requested and not dry run)
    if auto_download and not dry_run and sync_stats["tracks_added"] > 0:
        download_success = trigger_download_workflow(max_tracks=max_tracks)
        sync_stats["download_triggered"] = download_success
    else:
        sync_stats["download_triggered"] = False
        if dry_run:
            print("\n⚠️  DRY RUN: Download workflow not triggered")
        elif sync_stats["tracks_added"] == 0:
            print("\n⚠️  No new tracks added - download workflow not triggered")
    
    if results_path:
        try:
            results_path.parent.mkdir(parents=True, exist_ok=True)
            with results_path.open("w", encoding="utf-8") as handle:
                json.dump(sync_stats, handle, indent=2, ensure_ascii=True)
            sync_stats["results_path"] = str(results_path)
        except Exception as exc:
            logger.warning("Failed to write results file %s: %s", results_path, exc)

    return sync_stats

def main():
    parser = argparse.ArgumentParser(
        description="Sync and download SoundCloud playlist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync a playlist (adds tracks to Notion, triggers download)
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id"
  
  # Sync with custom playlist name
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --playlist-name "My Playlist"
  
  # Sync first 50 tracks only
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --max-tracks 50
  
  # Dry run (see what would be synced without making changes)
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --dry-run
  
  # Sync only (don't trigger download)
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --no-download
  
  # Resume from a previous checkpoint
  python sync_soundcloud_playlist.py "https://soundcloud.com/user/sets/playlist-id" --resume
        """
    )
    
    parser.add_argument(
        "playlist_url",
        help="SoundCloud playlist URL (e.g., https://soundcloud.com/user/sets/playlist-id)"
    )
    parser.add_argument(
        "--playlist-name",
        help="Optional playlist name (will be extracted from URL if not provided)"
    )
    parser.add_argument(
        "--max-tracks",
        type=int,
        help="Maximum number of tracks to process (default: all tracks)"
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
        "--checkpoint-file",
        help="Optional checkpoint file path for resume/progress tracking"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint (if available)"
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable checkpoint tracking"
    )
    parser.add_argument(
        "--results-file",
        help="Optional path to write a JSON results summary"
    )
    
    args = parser.parse_args()
    
    # Validate playlist URL
    if "soundcloud.com" not in args.playlist_url.lower():
        print("❌ Error: URL must be a SoundCloud playlist URL")
        print("   Example: https://soundcloud.com/user/sets/playlist-id")
        sys.exit(1)
    
    # Run sync and download
    try:
        use_checkpoint = not args.no_checkpoint
        checkpoint_path = None
        if use_checkpoint:
            checkpoint_path = Path(args.checkpoint_file) if args.checkpoint_file else None
        results_path = Path(args.results_file) if args.results_file else default_results_path()
        stats = sync_and_download_playlist(
            playlist_url=args.playlist_url,
            playlist_name=args.playlist_name,
            max_tracks=args.max_tracks,
            dry_run=args.dry_run,
            auto_download=not args.no_download,
            checkpoint_path=checkpoint_path,
            resume=args.resume,
            use_checkpoint=use_checkpoint,
            results_path=results_path,
        )
        
        # Exit with appropriate code
        if stats.get("success"):
            print("\n✅ Playlist sync completed successfully!")
            sys.exit(0)
        else:
            print(f"\n❌ Playlist sync completed with errors: {stats.get('error', 'Unknown error')}")
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





















































































