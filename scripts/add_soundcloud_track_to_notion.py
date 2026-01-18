#!/usr/bin/env python3
"""
Quick script to add a SoundCloud track to Notion Music Tracks database
Then triggers the download workflow
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env files first
load_dotenv()

# Load unified environment and configuration
try:
    from unified_config import load_unified_env, get_unified_config, setup_unified_logging
    load_unified_env()
    unified_config = get_unified_config()
    logger = setup_unified_logging(session_id="add_soundcloud_track")
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    print(f"Warning: unified_config unavailable ({unified_err}); using environment variables directly.", file=sys.stderr)
    unified_config = {}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("add_soundcloud_track")

# Import required modules
from music_workflow_common import (
    NotionClient,
    build_text_filter,
    normalize_soundcloud_url,
    resolve_property_name,
)

def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )

# Load configuration using proper pattern
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

def check_track_exists(title: str, artist: str, soundcloud_url: str = None) -> Optional[str]:
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
    except Exception as exc:
        logger.warning("Error checking for existing track: %s", exc)
        return None


def add_track_to_notion(title: str, artist: str, soundcloud_url: str) -> str:
    """Add a track to Notion Music Tracks database"""
    prop_types = get_property_types()
    
    # Build properties - try common property names
    props = {}
    
    # Title - usually a title property
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
        if sc_name in prop_types:
            if prop_types[sc_name] == "url":
                props[sc_name] = {"url": normalize_soundcloud_url(soundcloud_url) or soundcloud_url}
                break
            elif prop_types[sc_name] == "rich_text":
                props[sc_name] = {"rich_text": [{"text": {"content": soundcloud_url}}]}
                break
    
    # Create page
    try:
        page = notion_client.create_page(TRACKS_DB_ID, props)
        page_id = page.get("id", "")
        print(f"✅ Created track page in Notion: {title} by {artist}")
        print(f"   Page ID: {page_id}")
        return page_id
    except Exception as e:
        print(f"❌ Failed to create Notion page: {e}")
        raise

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python add_soundcloud_track_to_notion.py <title> <artist> <soundcloud_url>")
        sys.exit(1)
    
    title = sys.argv[1]
    artist = sys.argv[2]
    soundcloud_url = sys.argv[3]
    
    try:
        existing_id = check_track_exists(title, artist, soundcloud_url)
        if existing_id:
            print(f"⏭️  Track already exists in Notion (ID: {existing_id})")
            sys.exit(0)

        page_id = add_track_to_notion(title, artist, soundcloud_url)
        print(f"\n✅ Track added successfully!")
        print(f"   You can now run the download workflow with:")
        print(f"   python monolithic-scripts/soundcloud_download_prod_merge-2.py --mode single")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
