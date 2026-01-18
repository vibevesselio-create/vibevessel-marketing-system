#!/usr/bin/env python3
"""
Relocate VIBES Tracks to Playlist Folders
==========================================

Moves tracks from VIBES directories to the correct playlist folders in the
playlist-tracks directory based on Notion database playlist assignments.

Source Directories:
- /Volumes/VIBES/Playlists
- /Volumes/VIBES/Apple-Music-Auto-Add (WAV files)
- /Volumes/VIBES/Djay-Pro-Auto-Import (M4A files)

Target Directory:
- /Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks/{playlist_name}/

The script:
1. Scans source directories for audio files
2. Matches files to Notion tracks by filename/title
3. Retrieves playlist assignments from Notion
4. Moves files to appropriate playlist folders

Usage:
    python relocate_vibes_tracks_to_playlist_folders.py --dry-run    # Preview changes
    python relocate_vibes_tracks_to_playlist_folders.py --execute    # Perform relocation

Version: 2026-01-18
"""

import os
import sys
import re
import argparse
import shutil
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from shared_core.logging import setup_logging
    logger = setup_logging(session_id="relocate_vibes_tracks", log_level="INFO")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger(__name__)

# Import Notion integration
try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
    unified_config = get_unified_config()
except Exception as e:
    logger.warning(f"Could not load unified_config: {e}")
    unified_config = {}

try:
    from shared_core.notion.token_manager import get_notion_token
    from notion_client import Client
    import requests
    import time
except ImportError as e:
    logger.error(f"Could not import required modules: {e}")
    sys.exit(1)

# Configuration
SOURCE_DIRS = [
    Path("/Volumes/VIBES/Playlists"),
    Path("/Volumes/VIBES/Apple-Music-Auto-Add"),
    Path("/Volumes/VIBES/Djay-Pro-Auto-Import"),
]
TARGET_DIR = Path("/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks")

# Audio file extensions
AUDIO_EXTENSIONS = {".wav", ".m4a", ".aiff", ".mp3", ".m4p"}

# Get Notion configuration
TRACKS_DB_ID = (unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID") or "").strip()
NOTION_TOKEN = get_notion_token()
NOTION_VERSION = unified_config.get("notion_version") or os.getenv("NOTION_VERSION", "2022-06-28")
NOTION_TIMEOUT = int(unified_config.get("notion_timeout") or os.getenv("NOTION_TIMEOUT", "60"))

if not TRACKS_DB_ID:
    logger.error("TRACKS_DB_ID is required. Set tracks_db_id in unified_config or export TRACKS_DB_ID.")
    sys.exit(1)

# Simple NotionManager class for this script
class NotionManager:
    """Notion API manager following workspace standards"""
    
    def __init__(self, token: str = NOTION_TOKEN):
        self.client = Client(auth=token)
        self.session = requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
    def _req(self, method: str, path: str, body: Optional[dict] = None, retry: int = 3):
        """Make API request with retry logic"""
        url = f"https://api.notion.com/v1{path}"
        timeout = max(5, min(120, NOTION_TIMEOUT))
        for attempt in range(1, retry + 1):
            try:
                resp = self.session.request(method, url, headers=self.headers, json=body, timeout=timeout)
                if 200 <= resp.status_code < 300:
                    return resp.json()
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 1))
                    time.sleep(wait or attempt)
                    continue
                if resp.status_code >= 500:
                    time.sleep(1 * attempt)
                    continue
                raise RuntimeError(f"Notion error {resp.status_code}: {resp.text}")
            except Exception as exc:
                if attempt == retry:
                    raise
                time.sleep(2 ** attempt)
                
    def query_database(self, database_id: str, query: dict) -> dict:
        """Query database with workspace-standard error handling"""
        try:
            return self._req("post", f"/databases/{database_id}/query", query)
        except Exception as exc:
            logger.error(f"Failed to query database {database_id}: {exc}")
            raise

# Initialize Notion manager
notion_manager = NotionManager(NOTION_TOKEN)


def clean_filename(filename: str) -> str:
    """Clean filename for matching (remove extension, normalize)."""
    # Remove extension
    name = Path(filename).stem
    # Remove common suffixes in parentheses/brackets
    name = re.sub(r'\s*\([^)]*\)', '', name)
    name = re.sub(r'\s*\[[^\]]*\]', '', name)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name.lower()


def clean_title_for_matching(title: str) -> str:
    """Clean track title for matching."""
    if not title:
        return ""
    # Remove common suffixes
    title = re.sub(r'\s*\([^)]*\)', '', title)
    title = re.sub(r'\s*\[[^\]]*\]', '', title)
    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    return title.lower()


def similarity_score(str1: str, str2: str) -> float:
    """Calculate similarity score between two strings."""
    return SequenceMatcher(None, str1, str2).ratio()


# Cache for all tracks (loaded once)
_tracks_cache: Optional[List[Dict]] = None

def load_all_tracks() -> List[Dict]:
    """Load all tracks from Notion database and cache them."""
    global _tracks_cache
    
    if _tracks_cache is not None:
        return _tracks_cache
    
    logger.info("Loading all tracks from Notion database (this may take a moment)...")
    all_tracks = []
    has_more = True
    start_cursor = None
    
    while has_more:
        query = {
            "page_size": 100
        }
        if start_cursor:
            query["start_cursor"] = start_cursor
        
        try:
            results = notion_manager.query_database(TRACKS_DB_ID, query)
            tracks = results.get("results", [])
            all_tracks.extend(tracks)
            
            has_more = results.get("has_more", False)
            start_cursor = results.get("next_cursor")
            
            logger.info(f"  Loaded {len(all_tracks)} tracks so far...")
        except Exception as e:
            logger.error(f"Error loading tracks: {e}")
            break
    
    _tracks_cache = all_tracks
    logger.info(f"Loaded {len(all_tracks)} tracks total")
    return all_tracks


def find_track_in_notion(filename: str, tracks_cache: List[Dict]) -> Optional[Dict]:
    """
    Find a track in cached tracks by matching filename to track title.
    
    Returns the best matching track page or None.
    """
    clean_name = clean_filename(filename)
    
    if not clean_name:
        return None
    
    try:
        # Find best match by similarity in cached tracks
        best_match = None
        best_score = 0.0
        
        for track in tracks_cache:
            # Extract title from track
            props = track.get("properties", {})
            title_prop = props.get("Title", {})
            if title_prop.get("type") == "title":
                title_items = title_prop.get("title", [])
                if title_items:
                    track_title = title_items[0].get("text", {}).get("content", "")
                    clean_track_title = clean_title_for_matching(track_title)
                    
                    if clean_track_title:
                        score = similarity_score(clean_name, clean_track_title)
                        if score > best_score:
                            best_score = score
                            best_match = track
        
        # Only return if similarity is high enough (>= 0.7)
        if best_match and best_score >= 0.7:
            logger.debug(f"Matched '{filename}' to track '{best_match.get('id')}' (score: {best_score:.2f})")
            return best_match
        
        return None
        
    except Exception as e:
        logger.warning(f"Error finding track for '{filename}': {e}")
        return None


def get_playlist_names_from_track(track_info: dict) -> List[str]:
    """
    Get playlist names from a track's playlist properties.
    This is a simplified version of the function from soundcloud_download_prod_merge-2.py
    """
    playlist_names = []
    
    if not track_info.get("id"):
        return playlist_names
    
    try:
        # Get the track page from Notion
        page = notion_manager._req("get", f"/pages/{track_info['id']}")
        props = page.get("properties", {})
        
        # Define all possible playlist property names to check
        playlist_property_candidates = [
            "Playlist",
            "Playlists", 
            "Playlist Title",
            "Playlist Name",
            "Playlist Names",
            "Playlist Relation",
            "Related Playlists"
        ]
        
        for prop_name in playlist_property_candidates:
            if prop_name not in props:
                continue
                
            prop = props[prop_name]
            prop_type = prop.get("type")
            
            try:
                # Handle relation properties (link to playlist pages)
                if prop_type == "relation":
                    relations = prop.get("relation", [])
                    
                    for relation in relations:
                        playlist_id = relation.get("id")
                        if playlist_id:
                            try:
                                # Get the playlist page
                                playlist_page = notion_manager._req("get", f"/pages/{playlist_id}")
                                # Try multiple title property names
                                for title_prop in ["Title", "Name", "Playlist Name"]:
                                    playlist_title_data = playlist_page.get("properties", {}).get(title_prop, {})
                                    if playlist_title_data.get("type") == "title":
                                        title_items = playlist_title_data.get("title", [])
                                        if title_items:
                                            playlist_name = title_items[0].get("text", {}).get("content", "")
                                            if playlist_name:
                                                playlist_names.append(playlist_name)
                                                break
                            except Exception as e:
                                logger.debug(f"Could not get playlist name for relation ID {playlist_id}: {e}")
                                continue
                
                # Handle rich_text properties (direct text input)
                elif prop_type == "rich_text":
                    rich_text_items = prop.get("rich_text", [])
                    if rich_text_items:
                        playlist_text = "".join([item.get("text", {}).get("content", "") for item in rich_text_items])
                        if playlist_text.strip():
                            # Handle comma-separated or semicolon-separated lists
                            for separator in [";", ","]:
                                if separator in playlist_text:
                                    playlist_names.extend([p.strip() for p in playlist_text.split(separator) if p.strip()])
                                    break
                            else:
                                # Single playlist name
                                playlist_names.append(playlist_text.strip())
                
                # Handle select properties (single selection)
                elif prop_type == "select":
                    select_item = prop.get("select")
                    if select_item:
                        playlist_name = select_item.get("name", "")
                        if playlist_name:
                            playlist_names.append(playlist_name)
                
                # Handle multi_select properties
                elif prop_type == "multi_select":
                    multi_select_items = prop.get("multi_select", [])
                    for item in multi_select_items:
                        playlist_name = item.get("name", "")
                        if playlist_name:
                            playlist_names.append(playlist_name)
            
            except Exception as e:
                logger.debug(f"Error processing playlist property '{prop_name}': {e}")
                continue
        
        # Deduplicate
        return list(dict.fromkeys(playlist_names))  # Preserves order
        
    except Exception as e:
        logger.warning(f"Error getting playlists for track {track_info.get('id')}: {e}")
        return []


def sanitize_folder_name(name: str) -> str:
    """Sanitize playlist name for use as folder name."""
    # Remove invalid characters for folder names
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    # Remove leading/trailing dots and spaces
    name = name.strip('. ')
    # Limit length
    if len(name) > 255:
        name = name[:255]
    return name or "Uncategorized"


def scan_source_directories() -> List[Tuple[Path, str]]:
    """Scan source directories and return list of (file_path, source_dir_name) tuples."""
    files = []
    
    for source_dir in SOURCE_DIRS:
        if not source_dir.exists():
            logger.warning(f"Source directory does not exist: {source_dir}")
            continue
        
        logger.info(f"Scanning {source_dir}...")
        count = 0
        
        for file_path in source_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
                # Skip .DS_Store and other system files
                if file_path.name.startswith('.'):
                    continue
                
                files.append((file_path, source_dir.name))
                count += 1
        
        logger.info(f"  Found {count} audio files")
    
    return files


def find_track_targeted(filename: str) -> Optional[Dict]:
    """For single-track mode: Try targeted search first before loading all tracks."""
    clean_name = clean_filename(filename)
    
    if not clean_name:
        return None
    
    try:
        # Try a targeted search first
        logger.info(f"Searching Notion for: {clean_name}")
        query = {
            "filter": {
                "property": "Title",
                "title": {"contains": clean_name[:50]}  # Use first 50 chars
            },
            "page_size": 100
        }
        
        results = notion_manager.query_database(TRACKS_DB_ID, query)
        tracks = results.get("results", [])
        
        if tracks:
            logger.info(f"Found {len(tracks)} potential matches, finding best match...")
            # Find best match
            best_match = None
            best_score = 0.0
            
            for track in tracks:
                props = track.get("properties", {})
                title_prop = props.get("Title", {})
                if title_prop.get("type") == "title":
                    title_items = title_prop.get("title", [])
                    if title_items:
                        track_title = title_items[0].get("text", {}).get("content", "")
                        clean_track_title = clean_title_for_matching(track_title)
                        
                        if clean_track_title:
                            score = similarity_score(clean_name, clean_track_title)
                            if score > best_score:
                                best_score = score
                                best_match = track
            
            if best_match and best_score >= 0.7:
                logger.info(f"✅ Found match with {best_score:.2%} similarity")
                return best_match
            else:
                logger.info(f"⚠️  Best match only {best_score:.2%} similarity (threshold: 70%)")
        
        return None
        
    except Exception as e:
        logger.warning(f"Error in targeted search: {e}")
        return None


def generate_relocation_plan(files: List[Tuple[Path, str]], dry_run: bool = True, single_mode: bool = False) -> List[Dict]:
    """Generate relocation plan for all files."""
    relocation_plan = []
    
    # Load all tracks once (unless in single mode, then we can be more selective)
    if single_mode:
        logger.info(f"\nUsing targeted search for single-track test...")
        tracks_cache = None  # Will use targeted search instead
    else:
        tracks_cache = load_all_tracks()
    
    logger.info(f"\nMatching {len(files)} files to Notion tracks...")
    
    matched_count = 0
    for i, (file_path, source_dir) in enumerate(files, 1):
        if not single_mode and i % 100 == 0:
            logger.info(f"  Processed {i}/{len(files)} files...")
        
        filename = file_path.name
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing file {i}/{len(files)}: {filename}")
        logger.info(f"Source: {file_path}")
        
        # Find matching track (use targeted search in single mode, cached in batch mode)
        if single_mode:
            track = find_track_targeted(filename)
        else:
            track = find_track_in_notion(filename, tracks_cache)
        
        if track:
            matched_count += 1
            logger.info(f"✅ MATCHED to Notion track: {track.get('id')}")
        
        if track:
            # Get playlist names from track
            logger.info(f"Retrieving playlist assignments from Notion...")
            playlist_names = get_playlist_names_from_track(track)
            
            if playlist_names:
                playlist_name = playlist_names[0]  # Use first playlist
                logger.info(f"✅ Found playlist assignment: {playlist_name}")
                if len(playlist_names) > 1:
                    logger.info(f"   (Note: Track has {len(playlist_names)} playlists, using first: {playlist_names})")
            else:
                playlist_name = "Uncategorized"
                logger.warning(f"⚠️  No playlist assigned in Notion -> 'Uncategorized'")
        else:
            playlist_name = "Uncategorized"
            logger.warning(f"⚠️  No Notion match found -> 'Uncategorized'")
        
        # Determine destination
        sanitized_playlist = sanitize_folder_name(playlist_name)
        dest_dir = TARGET_DIR / sanitized_playlist
        dest_path = dest_dir / filename
        
        logger.info(f"Destination: {dest_path}")
        logger.info(f"Playlist folder: {sanitized_playlist}")
        
        relocation_plan.append({
            "source": file_path,
            "source_dir": source_dir,
            "destination": dest_path,
            "playlist": playlist_name,
            "track_matched": track is not None,
            "already_exists": False,  # Will check during execution
        })
        logger.info(f"{'='*80}\n")
    
    logger.info(f"\n✅ Matching complete: {matched_count}/{len(files)} files matched to Notion tracks")
    return relocation_plan
        


def execute_relocation(relocation_plan: List[Dict], dry_run: bool = True, single_mode: bool = False) -> Dict:
    """Execute the relocation plan."""
    stats = {
        "total": len(relocation_plan),
        "moved": 0,
        "skipped_exists": 0,
        "skipped_no_match": 0,
        "errors": [],
    }
    
    for item in relocation_plan:
        source = item["source"]
        dest = item["destination"]
        playlist = item["playlist"]
        track_matched = item["track_matched"]
        
        # Check if file already exists at destination
        already_exists = dest.exists() if not dry_run else False
        
        logger.info(f"\n{'='*80}")
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Processing: {source.name}")
        logger.info(f"{'='*80}")
        logger.info(f"  Source: {source}")
        logger.info(f"  Destination: {dest}")
        logger.info(f"  Playlist: {playlist}")
        logger.info(f"  Matched to Notion: {'Yes' if track_matched else 'No'}")
        
        if already_exists:
            logger.warning(f"  ⏭️  SKIP: File already exists at destination")
            logger.info(f"  Existing file: {dest}")
            stats["skipped_exists"] += 1
            continue
        
        if not track_matched and playlist == "Uncategorized":
            logger.warning(f"  ⚠️  No Notion match - will move to 'Uncategorized'")
            stats["skipped_no_match"] += 1
        
        if not dry_run:
            try:
                logger.info(f"  Creating destination directory: {dest.parent}")
                # Create destination directory
                dest.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"  ✅ Directory created/verified")
                
                logger.info(f"  Moving file: {source} -> {dest}")
                # Move file
                shutil.move(str(source), str(dest))
                logger.info(f"  ✅ SUCCESS: File moved successfully")
                logger.info(f"  New location: {dest}")
                stats["moved"] += 1
                
            except Exception as e:
                error_msg = f"Error moving {source}: {e}"
                logger.error(f"  ❌ ERROR: {error_msg}")
                import traceback
                logger.error(f"  Traceback: {traceback.format_exc()}")
                stats["errors"].append(error_msg)
                if single_mode:
                    logger.error(f"\n❌ SINGLE-TRACK TEST FAILED. Please review errors before running full batch.")
                    return stats
        else:
            logger.info(f"  [DRY RUN] Would create directory: {dest.parent}")
            logger.info(f"  [DRY RUN] Would move file to: {dest}")
            stats["moved"] += 1  # Count for dry-run preview
        
        logger.info(f"{'='*80}\n")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Relocate VIBES tracks to playlist folders")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute the relocation")
    parser.add_argument("--single", action="store_true", help="Process only a single track for testing")
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        print("\nUsage:")
        print("  python relocate_vibes_tracks_to_playlist_folders.py --dry-run --single    # Test with one track")
        print("  python relocate_vibes_tracks_to_playlist_folders.py --dry-run              # Preview all changes")
        print("  python relocate_vibes_tracks_to_playlist_folders.py --execute --single  # Test execute with one track")
        print("  python relocate_vibes_tracks_to_playlist_folders.py --execute            # Perform full relocation")
        sys.exit(1)
    
    dry_run = args.dry_run
    single_mode = args.single
    
    logger.info("=" * 80)
    logger.info("RELOCATE VIBES TRACKS TO PLAYLIST FOLDERS")
    logger.info(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (making changes)'}")
    if single_mode:
        logger.info("TEST MODE: Processing single track only")
    logger.info("=" * 80)
    
    # Verify directories
    logger.info("\nChecking directories...")
    for source_dir in SOURCE_DIRS:
        exists = source_dir.exists()
        logger.info(f"  {source_dir}: {'(exists)' if exists else '(NOT FOUND)'}")
    
    logger.info(f"  {TARGET_DIR}: {'(exists)' if TARGET_DIR.exists() else '(will create)'}")
    
    # Verify Notion connection
    logger.info(f"\nNotion Configuration:")
    logger.info(f"  TRACKS_DB_ID: {TRACKS_DB_ID[:8]}...")
    
    # Scan source directories
    files = scan_source_directories()
    
    if not files:
        logger.warning("No audio files found in source directories.")
        sys.exit(0)
    
    logger.info(f"\nFound {len(files)} audio files total")
    
    # In single mode, process only the first file
    if single_mode:
        if files:
            logger.info(f"\n🧪 TEST MODE: Processing only the first file for validation")
            files = [files[0]]
            logger.info(f"Test file: {files[0][0].name}")
        else:
            logger.error("No files found to test")
            sys.exit(1)
    
    # Generate relocation plan
    relocation_plan = generate_relocation_plan(files, dry_run=dry_run, single_mode=single_mode)
    
    # Show plan summary
    playlist_counts = {}
    for item in relocation_plan:
        playlist = item["playlist"]
        playlist_counts[playlist] = playlist_counts.get(playlist, 0) + 1
    
    logger.info(f"\nRelocation Plan Summary:")
    logger.info(f"  Total files: {len(relocation_plan)}")
    logger.info(f"  Playlists affected: {len(playlist_counts)}")
    for playlist, count in sorted(playlist_counts.items()):
        logger.info(f"    - {playlist}: {count} files")
    
    # Execute relocation
    stats = execute_relocation(relocation_plan, dry_run=dry_run, single_mode=single_mode)
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("RELOCATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total files processed: {stats['total']}")
    logger.info(f"Files moved: {stats['moved']}")
    logger.info(f"Skipped (already exists): {stats['skipped_exists']}")
    logger.info(f"Skipped (no Notion match): {stats['skipped_no_match']}")
    
    if stats["errors"]:
        logger.warning(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"][:10]:  # Show first 10 errors
            logger.warning(f"  - {err}")
        if len(stats["errors"]) > 10:
            logger.warning(f"  ... and {len(stats['errors']) - 10} more errors")
    
    if dry_run:
        logger.info("\nThis was a DRY RUN. No changes were made.")
        if single_mode:
            logger.info("\n✅ SINGLE-TRACK TEST COMPLETE")
            logger.info("If this looks correct, run:")
            logger.info("  python scripts/relocate_vibes_tracks_to_playlist_folders.py --execute --single")
            logger.info("Then if successful, run the full batch:")
            logger.info("  python scripts/relocate_vibes_tracks_to_playlist_folders.py --execute")
        else:
            logger.info("Run with --execute to perform the relocation.")
    elif single_mode:
        if stats["errors"]:
            logger.error("\n❌ SINGLE-TRACK TEST FAILED WITH ERRORS")
            logger.error("Please review and fix errors before running full batch.")
        else:
            logger.info("\n✅ SINGLE-TRACK TEST SUCCESSFUL - No errors!")
            logger.info("You can now proceed with the full batch:")
            logger.info("  python scripts/relocate_vibes_tracks_to_playlist_folders.py --execute")


if __name__ == "__main__":
    main()
