#!/usr/bin/env python3
"""
Music Library Remediation & Compliance System
=============================================

Capabilities:
- Volume-wide scan/index using MUSIC_DIRECTORIES_DB_ID (Notion) with fallbacks
- File-system dedupe planning (hash + metadata heuristics)
- Playlist consistency validation against Notion playlist relations
- Reconciliation reporting across Notion, disk, and optional Eagle API
- Optional remediation execution (move/copy/link + metadata writes)
- Backup before destructive operations
- Comprehensive error logging

Version: 2026-01-03
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

try:
    from unified_config import load_unified_env, get_unified_config
except (OSError, ModuleNotFoundError, TimeoutError):
    def load_unified_env() -> None:
        return None

    def get_unified_config() -> Dict[str, Any]:
        return {}

try:
    from shared_core.notion.token_manager import get_notion_client, get_notion_token
except (ImportError, ModuleNotFoundError):
    get_notion_client = None
    get_notion_token = None

# Mutagen for audio metadata handling (fingerprint embedding)
try:
    import mutagen
    from mutagen.mp4 import MP4
    from mutagen.id3 import ID3, TXXX
    from mutagen.flac import FLAC
    from mutagen.aiff import AIFF
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

MUSIC_EXTENSIONS = {".aiff", ".aif", ".wav", ".m4a", ".mp3", ".flac", ".alac"}
EXTENSION_PRIORITY = {
    ".wav": 5,
    ".aiff": 4,
    ".aif": 4,
    ".flac": 3,
    ".m4a": 2,
    ".alac": 2,
    ".mp3": 1,
}

# Minimum file size in bytes to consider valid (avoid corrupt/empty files)
MIN_VALID_FILE_SIZE = 1024  # 1KB

DEFAULT_VOLUME_PATHS = [
    "/Users/brianhellemn/Music/Downloads/SoundCloud",
    "/Users/brianhellemn/Music/Downloads/Spotify",
    "/Users/brianhellemn/Music/Downloads/YouTube",
    "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists",
    "/Volumes/SYSTEM_SSD/Dropbox/Music/m4A-tracks",
    "/Volumes/SYSTEM_SSD/Dropbox/Music/wav-tracks",
    "/Volumes/VIBES/Playlists",
    "/Volumes/VIBES/Djay-Pro-Auto-Import",
    "/Volumes/VIBES/Apple-Music-Auto-Add",
    # 2026-01-16: New playlist tracks directory for 3-file output structure
    "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks",
]

# 2026-01-16: New 3-file output structure directories
# WAV+AIFF -> Eagle Library (organized by playlist folder)
# WAV copy -> PLAYLIST_TRACKS_DIR/{playlist}/
PLAYLIST_TRACKS_DIR = Path(os.getenv("PLAYLIST_TRACKS_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks"))

DIR_PROP_CANDIDATES = [
    "Path",
    "Directory",
    "Folder",
    "Folder Path",
    "Volume Path",
    "Root Path",
    "Location",
    "Music Directory",
]

PLAYLIST_PROP_CANDIDATES = [
    "Playlist",
    "Playlists",
    "Playlist Name",
    "Playlist Title",
    "Playlist Names",
    "Playlist Relation",
]

TITLE_PROP_CANDIDATES = ["Title", "Name"]

TRACK_PATH_PROP_CANDIDATES = {
    "M4A File Path": ["M4A File Path", "M4A", "M4A Path"],
    "WAV File Path": ["WAV File Path", "WAV", "WAV Path"],
    "AIFF File Path": ["AIFF File Path", "AIFF", "AIFF Path"],
}

# Action modes for remediation
ACTION_MODE_COPY = "copy"
ACTION_MODE_MOVE = "move"
ACTION_MODE_LINK = "link"
ACTION_MODES = {ACTION_MODE_COPY, ACTION_MODE_MOVE, ACTION_MODE_LINK}


@dataclass
class FileRecord:
    path: str
    size: int
    mtime: float
    extension: str
    title: str
    artist: Optional[str]
    title_cleaned: str
    artist_cleaned: Optional[str]
    file_hash: Optional[str] = None
    is_valid: bool = True  # Flag for integrity check
    fingerprint: Optional[str] = None  # Fingerprint hash


@dataclass
class RemediationResult:
    """Track results of remediation operations."""
    planned: int = 0
    executed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    actions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)


def clean_title_advanced(title: str) -> str:
    if not title:
        return title
    cleaned = re.sub(r"^\d+\.?\s*", "", title)
    cleaned = re.sub(r"^(track|song|music)\s*[-_]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[-_]{2,}", " - ", cleaned)
    cleaned = re.sub(r"\s*-\s*", " - ", cleaned)
    match = re.search(r"^([^-]+?)\s*-\s*(.+)$", cleaned)
    if match:
        cleaned = match.group(2).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def clean_artist_name(artist: str) -> str:
    if not artist:
        return artist
    cleaned = re.sub(r"\s+(official|music|records|label|sounds)$", "", artist, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_filename_for_artist_title(stem: str) -> Tuple[Optional[str], str]:
    match = re.search(r"^(.+?)\s+-\s+(.+)$", stem)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, stem


def compute_file_hash(path: Path, fast: bool = False) -> Optional[str]:
    try:
        hasher = hashlib.sha256()
        size = path.stat().st_size
        if fast and size > 2 * 1024 * 1024:
            with path.open("rb") as handle:
                hasher.update(handle.read(1024 * 1024))
                handle.seek(max(0, size - 1024 * 1024))
                hasher.update(handle.read(1024 * 1024))
        else:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.warning(f"Failed to compute hash for {path}: {e}")
        return None


def compute_file_fingerprint(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a stable SHA-256 fingerprint for the provided audio file."""
    hash_obj = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def embed_fingerprint_in_metadata(file_path: str, fingerprint: str) -> tuple[bool, Optional[str]]:
    """
    Embed audio fingerprint directly into file metadata.

    Supports:
    - M4A/AAC/ALAC: Uses mutagen for MP4 tags (----:com.apple.iTunes:FINGERPRINT)
    - MP3: Uses ID3 TXXX frame (FINGERPRINT)
    - FLAC: Uses Vorbis comment (FINGERPRINT)
    - AIFF: Uses ID3 chunk

    Args:
        file_path: Path to audio file
        fingerprint: Fingerprint hash string

    Returns:
        Tuple of (success: bool, skip_reason: Optional[str]):
        - (True, None): Successfully embedded
        - (False, "unsupported_format"): Unsupported format (WAV, unknown extension) - should be counted as skipped
        - (False, None): Actual error occurred - should be counted as failed
    """
    if not MUTAGEN_AVAILABLE:
        logger.warning("mutagen not available - cannot embed fingerprint in file metadata")
        return (False, None)  # Actual error, not unsupported format

    try:
        ext = Path(file_path).suffix.lower()

        if ext in ['.m4a', '.mp4', '.aac', '.alac']:
            # M4A/MP4 files - use freeform atom
            audio = MP4(file_path)
            audio['----:com.apple.iTunes:FINGERPRINT'] = [fingerprint.encode('utf-8')]
            audio.save()
            logger.debug(f"✅ Embedded fingerprint in M4A metadata: {Path(file_path).name}")
            return (True, None)

        elif ext == '.mp3':
            # MP3 files - use TXXX frame
            try:
                audio = ID3(file_path)
            except mutagen.id3.ID3NoHeaderError:
                audio = ID3()
            audio.delall('TXXX:FINGERPRINT')
            audio.add(TXXX(encoding=3, desc='FINGERPRINT', text=fingerprint))
            audio.save(file_path)
            logger.debug(f"✅ Embedded fingerprint in MP3 metadata: {Path(file_path).name}")
            return (True, None)

        elif ext == '.flac':
            # FLAC files - use Vorbis comment
            audio = FLAC(file_path)
            audio['FINGERPRINT'] = fingerprint
            audio.save()
            logger.debug(f"✅ Embedded fingerprint in FLAC metadata: {Path(file_path).name}")
            return (True, None)

        elif ext in ['.aiff', '.aif']:
            # AIFF files - use ID3 chunk
            audio = AIFF(file_path)
            if audio.tags is None:
                audio.add_tags()
            if hasattr(audio.tags, 'delall'):
                audio.tags.delall('TXXX:FINGERPRINT')
            audio.tags.add(TXXX(encoding=3, desc='FINGERPRINT', text=fingerprint))
            audio.save()
            logger.debug(f"✅ Embedded fingerprint in AIFF metadata: {Path(file_path).name}")
            return (True, None)

        elif ext == '.wav':
            # WAV files have limited metadata support
            logger.debug(f"WAV files have limited metadata support, skipping: {Path(file_path).name}")
            return (False, "unsupported_format")  # Mark as skip, not failure

        else:
            logger.debug(f"Unsupported format for fingerprint embedding: {ext}")
            return (False, "unsupported_format")  # Mark as skip, not failure

    except Exception as e:
        logger.warning(f"Failed to embed fingerprint in {Path(file_path).name}: {e}")
        return (False, None)  # Actual error, not unsupported format


def extract_fingerprint_from_metadata(file_path: str) -> Optional[str]:
    """
    Extract fingerprint from audio file metadata.

    Args:
        file_path: Path to audio file

    Returns:
        Fingerprint string if found, None otherwise
    """
    if not MUTAGEN_AVAILABLE:
        return None

    try:
        if not Path(file_path).exists():
            return None

        ext = Path(file_path).suffix.lower()

        if ext in ['.m4a', '.mp4', '.aac', '.alac']:
            audio = MP4(file_path)
            fp_data = audio.get('----:com.apple.iTunes:FINGERPRINT')
            if fp_data:
                val = fp_data[0]
                return val.decode('utf-8') if isinstance(val, bytes) else str(val)

        elif ext == '.mp3':
            try:
                audio = ID3(file_path)
                for frame in audio.getall('TXXX'):
                    if frame.desc == 'FINGERPRINT':
                        return str(frame.text[0]) if frame.text else None
            except mutagen.id3.ID3NoHeaderError:
                return None

        elif ext == '.flac':
            audio = FLAC(file_path)
            fp = audio.get('FINGERPRINT')
            if fp:
                return fp[0] if isinstance(fp, list) else str(fp)

        elif ext in ['.aiff', '.aif']:
            audio = AIFF(file_path)
            if audio.tags:
                for frame in audio.tags.getall('TXXX'):
                    if frame.desc == 'FINGERPRINT':
                        return str(frame.text[0]) if frame.text else None

        return None

    except Exception as e:
        logger.debug(f"Could not extract fingerprint from {file_path}: {e}")
        return None


def validate_audio_file(path: Path) -> bool:
    """Basic integrity check for audio files.

    Checks:
    - File exists and is readable
    - File size is above minimum threshold
    - File has expected audio header bytes (basic check)
    """
    try:
        if not path.exists():
            return False

        size = path.stat().st_size
        if size < MIN_VALID_FILE_SIZE:
            logger.warning(f"File too small ({size} bytes): {path}")
            return False

        # Basic header validation for common formats
        with path.open("rb") as f:
            header = f.read(12)

        ext = path.suffix.lower()

        # AIFF: starts with "FORM" and contains "AIFF" or "AIFC"
        if ext in (".aiff", ".aif"):
            if not (header[:4] == b"FORM" and (b"AIFF" in header or b"AIFC" in header)):
                logger.warning(f"Invalid AIFF header: {path}")
                return False

        # WAV: starts with "RIFF" and contains "WAVE"
        elif ext == ".wav":
            if not (header[:4] == b"RIFF" and header[8:12] == b"WAVE"):
                logger.warning(f"Invalid WAV header: {path}")
                return False

        # MP3: starts with ID3 tag or sync bytes
        elif ext == ".mp3":
            if not (header[:3] == b"ID3" or header[:2] == b"\xff\xfb" or header[:2] == b"\xff\xfa"):
                logger.warning(f"Invalid MP3 header: {path}")
                return False

        # M4A/ALAC: starts with ftyp box
        elif ext in (".m4a", ".alac"):
            if b"ftyp" not in header[:8]:
                logger.warning(f"Invalid M4A header: {path}")
                return False

        # FLAC: starts with "fLaC"
        elif ext == ".flac":
            if header[:4] != b"fLaC":
                logger.warning(f"Invalid FLAC header: {path}")
                return False

        return True

    except Exception as e:
        logger.warning(f"Failed to validate {path}: {e}")
        return False


def _prop_text_value(prop: dict) -> str:
    if not prop:
        return ""
    prop_type = prop.get("type")
    if prop_type == "url":
        return prop.get("url") or ""
    if prop_type == "rich_text":
        return "".join(segment.get("plain_text", "") for segment in prop.get("rich_text", []))
    if prop_type == "title":
        return "".join(segment.get("plain_text", "") for segment in prop.get("title", []))
    if not prop_type:
        if "url" in prop:
            return prop.get("url") or ""
        if "rich_text" in prop:
            return "".join(
                segment.get("plain_text")
                or (segment.get("text", {}) or {}).get("content", "")
                for segment in prop.get("rich_text", [])
            )
        if "title" in prop:
            return "".join(
                segment.get("plain_text")
                or (segment.get("text", {}) or {}).get("content", "")
                for segment in prop.get("title", [])
            )
    return ""


def query_database_all(notion: Any, database_id: str, filter_payload: Optional[dict] = None) -> List[dict]:
    results: List[dict] = []
    cursor: Optional[str] = None
    while True:
        payload: Dict[str, Any] = {"database_id": database_id, "page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        if filter_payload:
            payload["filter"] = filter_payload
        try:
            data = notion.databases.query(**payload)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        except Exception as e:
            logger.error(f"Failed to query database {database_id}: {e}")
            break
    return results


def load_music_directories(notion: Optional[Any], db_id: str) -> List[str]:
    paths: List[str] = []
    if notion and db_id:
        try:
            pages = query_database_all(notion, db_id)
            for page in pages:
                props = page.get("properties", {})
                for candidate in DIR_PROP_CANDIDATES:
                    if candidate in props:
                        value = _prop_text_value(props.get(candidate))
                        if value:
                            paths.append(value)
                            break
        except Exception as e:
            logger.warning(f"Failed to load directories from Notion: {e}")

    env_paths = os.getenv("MUSIC_DIRECTORY_PATHS", "")
    if env_paths:
        for entry in re.split(r"[,\n]+", env_paths):
            entry = entry.strip()
            if entry:
                paths.append(entry)

    if not paths:
        paths = DEFAULT_VOLUME_PATHS.copy()

    # De-duplicate while preserving order
    seen = set()
    unique_paths = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)
    return unique_paths


def scan_directories(
    paths: Iterable[str],
    with_hash: bool,
    fast_hash: bool,
    validate_integrity: bool = False
) -> Tuple[List[FileRecord], List[str]]:
    records: List[FileRecord] = []
    missing_paths: List[str] = []
    for raw_path in paths:
        base = Path(raw_path).expanduser()
        if not base.exists():
            missing_paths.append(str(base))
            logger.warning(f"Directory not found: {base}")
            continue
        logger.info(f"Scanning directory: {base}")
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file_name in files:
                if file_name.startswith("."):
                    continue
                path = Path(root) / file_name
                ext = path.suffix.lower()
                if ext not in MUSIC_EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                except OSError as e:
                    logger.warning(f"Cannot stat file {path}: {e}")
                    continue
                stem = path.stem
                artist, title = parse_filename_for_artist_title(stem)
                clean_title = clean_title_advanced(title)
                clean_artist = clean_artist_name(artist) if artist else None
                file_hash = compute_file_hash(path, fast=fast_hash) if with_hash else None

                # Validate integrity if requested
                is_valid = True
                if validate_integrity:
                    is_valid = validate_audio_file(path)

                records.append(
                    FileRecord(
                        path=str(path),
                        size=int(stat.st_size),
                        mtime=float(stat.st_mtime),
                        extension=ext,
                        title=title,
                        artist=artist,
                        title_cleaned=clean_title,
                        artist_cleaned=clean_artist,
                        file_hash=file_hash,
                        is_valid=is_valid,
                    )
                )
    logger.info(f"Scanned {len(records)} files across {len(paths) - len(missing_paths)} directories")
    return records, missing_paths


def choose_master(records: List[FileRecord]) -> FileRecord:
    """Select the best quality file as the master.

    Scoring:
    1. Format priority (WAV > AIFF > FLAC > M4A > MP3)
    2. File validity (valid files preferred)
    3. File size (larger generally better for lossless)
    4. Modification time (newer preferred as tiebreaker)
    """
    def score(item: FileRecord) -> Tuple[int, int, int, float]:
        priority = EXTENSION_PRIORITY.get(item.extension, 0)
        validity = 1 if item.is_valid else 0
        return (priority, validity, item.size, item.mtime)

    return sorted(records, key=score, reverse=True)[0]


def dedupe_inventory(records: List[FileRecord]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    groups: Dict[str, List[FileRecord]] = {}
    for record in records:
        if record.file_hash:
            key = f"hash:{record.file_hash}"
        else:
            key = f"name:{record.artist_cleaned or ''}|{record.title_cleaned}|{record.size}"
        groups.setdefault(key, []).append(record)

    dedupe_groups: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) == 1:
            continue
        master = choose_master(items)
        dupes = [item for item in items if item.path != master.path]
        dedupe_groups.append(
            {
                "key": key,
                "master": master.path,
                "master_valid": master.is_valid,
                "duplicates": [item.path for item in dupes],
            }
        )
        for item in dupes:
            duplicates.append(
                {
                    "path": item.path,
                    "master": master.path,
                    "reason": key,
                }
            )
    logger.info(f"Found {len(dedupe_groups)} duplicate groups with {len(duplicates)} total duplicates")
    return dedupe_groups, duplicates


def fetch_playlist_names(notion: Any, page_id: str) -> List[str]:
    if not notion or not page_id:
        return []
    try:
        page = notion.pages.retrieve(page_id=page_id)
    except Exception as e:
        logger.warning(f"Failed to fetch page {page_id}: {e}")
        return []
    props = page.get("properties", {})
    names: List[str] = []
    for candidate in PLAYLIST_PROP_CANDIDATES:
        prop = props.get(candidate)
        if not prop:
            continue
        prop_type = prop.get("type")
        if prop_type == "relation":
            for rel in prop.get("relation", []):
                rel_id = rel.get("id")
                if not rel_id:
                    continue
                try:
                    rel_page = notion.pages.retrieve(page_id=rel_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch related page {rel_id}: {e}")
                    continue
                rel_props = rel_page.get("properties", {})
                for title_prop in ["Title", "Name", "Playlist Name"]:
                    title_data = rel_props.get(title_prop, {})
                    if title_data.get("type") == "title":
                        title_items = title_data.get("title", [])
                        if title_items:
                            name = title_items[0].get("plain_text") or title_items[0].get("text", {}).get("content", "")
                            if name:
                                names.append(name)
                                break
        elif prop_type == "rich_text":
            text = _prop_text_value(prop)
            if text:
                names.append(text)
        elif prop_type == "multi_select":
            names.extend([item.get("name") for item in prop.get("multi_select", []) if item.get("name")])
        elif prop_type == "select":
            selected = prop.get("select", {})
            if selected and selected.get("name"):
                names.append(selected.get("name"))
    # De-dup while preserving order
    seen = set()
    deduped = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def get_track_file_paths(props: dict) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, candidates in TRACK_PATH_PROP_CANDIDATES.items():
        for candidate in candidates:
            if candidate in props:
                value = _prop_text_value(props.get(candidate))
                if value:
                    result[key] = value
                break
    return result


def get_first_prop_text(props: dict, candidates: List[str]) -> str:
    for candidate in candidates:
        if candidate in props:
            value = _prop_text_value(props.get(candidate))
            if value:
                return value
    return ""


def validate_playlist_consistency(notion: Optional[Any], tracks_db_id: str, out_dir: Path) -> Dict[str, Any]:
    if not notion or not tracks_db_id:
        return {"error": "Notion client or tracks DB ID unavailable", "mismatches": []}
    results: List[Dict[str, Any]] = []
    pages = query_database_all(notion, tracks_db_id)
    for page in pages:
        props = page.get("properties", {})
        track_name = get_first_prop_text(props, TITLE_PROP_CANDIDATES) or page.get("id")
        file_paths = get_track_file_paths(props)
        playlist_names = fetch_playlist_names(notion, page.get("id"))
        expected_dirs = [out_dir / name for name in playlist_names] if playlist_names else [out_dir / "Unassigned"]
        for label, file_path in file_paths.items():
            path = Path(file_path)
            if not path.exists():
                results.append(
                    {
                        "track": track_name,
                        "path": file_path,
                        "issue": "missing_file",
                        "playlist": playlist_names,
                    }
                )
                continue
            if not any(str(path).startswith(str(expected_dir)) for expected_dir in expected_dirs):
                results.append(
                    {
                        "track": track_name,
                        "path": file_path,
                        "issue": "playlist_folder_mismatch",
                        "expected_dirs": [str(d) for d in expected_dirs],
                        "playlist": playlist_names,
                    }
                )
    logger.info(f"Found {len(results)} playlist consistency issues")
    return {"mismatches": results, "count": len(results)}


# Import path resolution utilities from shared module
try:
    from scripts.eagle_path_resolution import (
        get_eagle_item_file_path,
        resolve_eagle_item_path
    )
except ImportError:
    # Fallback implementation if shared module not available
    # This should not happen in normal operation
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("Could not import eagle_path_resolution, using fallback implementation")
    
    def get_eagle_item_file_path(item_id: str, ext: str, library_path: Optional[Path] = None) -> Optional[Path]:
        """Fallback implementation - should use shared utility."""
        from scripts.eagle_path_resolution import get_eagle_item_file_path as _get_path
        return _get_path(item_id, ext, library_path)
    
    def resolve_eagle_item_path(item: dict, library_path: Optional[Path] = None) -> Optional[Path]:
        """Fallback implementation - should use shared utility."""
        from scripts.eagle_path_resolution import resolve_eagle_item_path as _resolve
        return _resolve(item, library_path)


def eagle_fetch_all_items(eagle_base: str, eagle_token: str, limit: int = 50000) -> List[dict]:
    """
    Fetch all items from Eagle library.
    
    Args:
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        limit: Maximum number of items to fetch (default 50000 to ensure full library scan)
    
    Returns:
        List of item dictionaries from Eagle library
    """
    if not eagle_base:
        return []
    url = eagle_base.rstrip("/") + "/api/item/list"
    params = []
    if eagle_token:
        params.append(f"token={eagle_token}")
    if limit:
        params.append(f"limit={limit}")
    if params:
        url += "?" + "&".join(params)
    try:
        import requests

        resp = requests.get(url, timeout=60)
        data = resp.json() if resp.status_code == 200 else {}
        items = data.get("data", []) if isinstance(data, dict) else []
        logger.info(f"📊 Fetched {len(items)} items from Eagle library")
        return items
    except Exception as e:
        logger.error(f"Failed to fetch Eagle items: {e}")
        return []


def reconcile_eagle(items: List[dict], files: List[FileRecord]) -> Dict[str, Any]:
    if not items:
        return {"missing_in_eagle": [], "count": 0}
    eagle_paths = {item.get("path") for item in items if item.get("path")}
    missing = [record.path for record in files if record.path not in eagle_paths]
    return {"missing_in_eagle": missing, "count": len(missing)}


def build_report(
    scan_paths: List[str],
    records: List[FileRecord],
    missing_paths: List[str],
    dedupe_groups: List[Dict[str, Any]],
    playlist_check: Dict[str, Any],
    eagle_check: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "scan_paths": scan_paths,
        "missing_paths": missing_paths,
        "file_count": len(records),
        "valid_file_count": sum(1 for r in records if r.is_valid),
        "invalid_file_count": sum(1 for r in records if not r.is_valid),
        "dedupe_groups": dedupe_groups,
        "playlist_consistency": playlist_check,
        "eagle_reconciliation": eagle_check,
    }


def write_report(report: Dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"music_library_remediation_report_{ts}.json"
    with path.open("w") as handle:
        json.dump(report, handle, indent=2)
    return path


def backup_file(source: Path, backup_dir: Path) -> Optional[Path]:
    """Create a backup of a file before deletion/modification.

    Returns the backup path if successful, None otherwise.
    """
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{source.stem}_{ts}{source.suffix}"
        backup_path = backup_dir / backup_name
        shutil.copy2(source, backup_path)
        logger.info(f"Backed up {source} to {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to backup {source}: {e}")
        return None


def eagle_update_tags(eagle_base: str, eagle_token: str, item_id: str, tags: List[str]) -> bool:
    """Update tags on an existing Eagle item using the direct REST API."""
    if not eagle_base or not item_id or not tags:
        return False
    try:
        import requests
        update_url = f"{eagle_base.rstrip('/')}/api/item/update"
        payload = {"id": item_id, "tags": tags}
        resp = requests.post(
            update_url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("status") == "success":
                logger.debug(f"✅ Tags updated in Eagle for {item_id}")
                return True
        logger.warning(f"⚠️  Eagle tag update failed (status={resp.status_code})")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Exception during Eagle tag update: {e}")
        return False


def update_notion_track_fingerprint(
    notion: Any,
    tracks_db_id: str,
    file_path: str,
    fingerprint: str
) -> bool:
    """Update Notion track page with fingerprint if file path matches."""
    if not notion or not tracks_db_id or not file_path or not fingerprint:
        logger.debug(f"Skipping Notion update - missing required params: notion={notion is not None}, tracks_db_id={bool(tracks_db_id)}, file_path={bool(file_path)}, fingerprint={bool(fingerprint)}")
        return False

    try:
        # Normalize file path for matching (resolve to absolute, normalize separators)
        normalized_path = str(Path(file_path).resolve())

        # Generate path variants including file:// protocol (Notion stores paths with file:// prefix)
        path_variants = [
            normalized_path,
            file_path,  # Original path
            str(Path(file_path)),  # Normalized but not resolved
            f"file://{normalized_path}",  # file:// protocol variant (two slashes)
            f"file:///{normalized_path}",  # file:/// protocol variant (three slashes for absolute paths)
        ]

        # Also strip file:// prefix if input already has it, to support reverse matching
        if file_path.startswith("file://"):
            stripped_path = file_path.replace("file:///", "/").replace("file://", "/")
            path_variants.extend([
                stripped_path,
                str(Path(stripped_path).resolve()),
            ])
        
        # Query tracks database for file path matches
        # Check all file path properties (some are rich_text, some are url type)
        # Notion limits to 2 OR conditions per query, so we need multiple queries
        path_properties = [
            "M4A File Path",           # rich_text
            "WAV File Path",           # rich_text
            "AIFF File Path",          # rich_text
            "Enhanced AIFF File Path", # url
            "YouTube AIFF File Path",  # url
            "SoundCloud AIFF File Path", # url
            "M4A Backup File Path",    # url
            "Rekordbox Path",          # rich_text
        ]
        property_types = ["rich_text", "url"]  # File paths can be stored as either type
        
        pages = []
        
        # Try each property separately (since Notion limits OR conditions)
        for prop_name in path_properties:
            if pages:
                break  # Found a match, stop searching
                
            for prop_type in property_types:
                if pages:
                    break
                    
                # Try each path variant
                for path_variant in path_variants:
                    try:
                        query = {
                            "filter": {
                                "property": prop_name,
                                prop_type: {"equals": path_variant}
                            },
                            "page_size": 1
                        }
                        result = notion.databases.query(database_id=tracks_db_id, **query)
                        found_pages = result.get("results", [])
                        if found_pages:
                            pages = found_pages
                            logger.debug(f"Found Notion track matching {prop_name} ({prop_type}): {path_variant[:50]}...")
                            break
                    except Exception as query_error:
                        # Property might not exist or be wrong type, continue
                        logger.debug(f"Query failed for {prop_name} ({prop_type}): {query_error}")
                        continue
                    
                if pages:
                    break
            if pages:
                break

        if not pages:
            logger.debug(f"No Notion track found matching file path: {file_path[:80]}...")
            logger.debug(f"  Searched properties: {path_properties}")
            logger.debug(f"  Searched variants: {len(path_variants)} path formats")
            return False

        page = pages[0]
        page_id = page.get("id")
        props = page.get("properties", {})
        
        # Get page title for logging
        page_title = "Unknown"
        title_prop = props.get("Title") or props.get("title")
        if title_prop:
            if title_prop.get("type") == "title" and title_prop.get("title"):
                page_title = title_prop["title"][0].get("text", {}).get("content", "Unknown")
            elif title_prop.get("type") == "rich_text" and title_prop.get("rich_text"):
                page_title = title_prop["rich_text"][0].get("text", {}).get("content", "Unknown")

        # NEW SCHEMA (2026-01-14): Use per-format fingerprint properties
        # Route fingerprint to correct property based on file format
        try:
            from shared_core.fingerprint_schema import (
                build_fingerprint_update_properties,
                get_format_from_extension,
                FINGERPRINT_PROPERTIES,
                LEGACY_FINGERPRINT_PROPERTIES,
            )

            # Determine format from file path and build update properties
            update_data = build_fingerprint_update_properties(fingerprint, file_path, props)

            if update_data:
                notion.pages.update(page_id=page_id, properties=update_data)
                fmt = get_format_from_extension(file_path)
                logger.info(f"✅ Updated Notion track {fmt.upper()} fingerprint: {page_title} ({page_id[:8]}...)")
                return True

            # Fall back to legacy if per-format properties not available
            logger.debug(f"Per-format fingerprint properties not available, trying legacy fallback")

        except ImportError:
            logger.debug("Per-format fingerprint schema not available, using legacy fallback")

        # LEGACY FALLBACK (DEPRECATED): Find and update legacy fingerprint property
        fingerprint_prop = None
        legacy_candidates = ["Fingerprint", "fingerprint", "Fingerprint SHA", "fingerprint_sha"]
        for candidate in legacy_candidates:
            if candidate in props:
                prop_type = props[candidate].get("type")
                if prop_type in ["rich_text", "title"]:
                    fingerprint_prop = candidate
                    logger.warning(f"Using DEPRECATED legacy fingerprint field: {candidate}")
                    break

        if not fingerprint_prop:
            logger.warning(f"No fingerprint property found in Notion track: {page_id} (Title: {page_title})")
            logger.debug(f"Available properties: {list(props.keys())}")
            return False

        # Update legacy fingerprint property (DEPRECATED - writes only as fallback)
        prop_type = props[fingerprint_prop].get("type")
        update_data = {}
        if prop_type == "rich_text":
            update_data[fingerprint_prop] = {"rich_text": [{"text": {"content": fingerprint}}]}
        elif prop_type == "title":
            update_data[fingerprint_prop] = {"title": [{"text": {"content": fingerprint}}]}
        else:
            logger.warning(f"Fingerprint property '{fingerprint_prop}' has unsupported type: {prop_type}")
            return False

        if update_data:
            notion.pages.update(page_id=page_id, properties=update_data)
            logger.info(f"✅ Updated Notion track fingerprint (LEGACY): {page_title} ({page_id[:8]}...)")
            return True

        return False
    except Exception as e:
        logger.error(f"Failed to update Notion track fingerprint for {file_path[:50]}...: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


def execute_fingerprint_remediation(
    records: List[FileRecord],
    execute: bool,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None,
    notion: Optional[Any] = None,
    tracks_db_id: Optional[str] = None,
    action_limit: int = 100
) -> RemediationResult:
    """
    Execute fingerprint computation and embedding for existing files.

    Args:
        records: List of file records to process
        execute: If True, actually perform actions; otherwise dry-run
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token
        notion: Notion client (optional)
        tracks_db_id: Notion tracks database ID (optional)
        action_limit: Maximum number of actions to execute

    Returns:
        RemediationResult with fingerprint processing statistics
    """
    result = RemediationResult()
    eagle_items_by_path = {}

    # Fetch Eagle items if Eagle integration enabled
    if eagle_base and eagle_token:
        try:
            eagle_items = eagle_fetch_all_items(eagle_base, eagle_token)
            # Build mapping using resolved paths (workaround for API not returning paths)
            eagle_items_by_path = {}
            for item in eagle_items:
                resolved_path = resolve_eagle_item_path(item)
                if resolved_path:
                    eagle_items_by_path[str(resolved_path)] = item
            logger.info(f"Loaded {len(eagle_items_by_path)} Eagle items for fingerprint sync")
        except Exception as e:
            logger.warning(f"Failed to fetch Eagle items: {e}")

    # Process each file
    for record in records:
        file_path = Path(record.path)
        if not file_path.exists():
            continue

        # Check if fingerprint already exists in metadata
        existing_fp = extract_fingerprint_from_metadata(str(file_path))
        if existing_fp:
            result.skipped += 1
            logger.debug(f"Skipping {file_path.name} - fingerprint already exists")
            continue

        # Check format support early to avoid unnecessary fingerprint computation
        ext = file_path.suffix.lower()
        SUPPORTED_FORMATS = {'.m4a', '.mp4', '.aac', '.alac', '.mp3', '.flac', '.aiff', '.aif'}
        if ext not in SUPPORTED_FORMATS:
            # Unsupported format - skip early (don't compute fingerprint)
            action = {
                "action": "add_fingerprint",
                "path": str(file_path),
                "status": "skipped",
                "skip_reason": "unsupported_format"
            }
            result.actions.append(action)
            result.skipped += 1
            logger.debug(f"Skipping unsupported format: {file_path.name} ({ext})")
            continue

        # Plan fingerprint computation and embedding
        action = {
            "action": "add_fingerprint",
            "path": str(file_path),
            "status": "planned"
        }
        result.actions.append(action)
        result.planned += 1

        if execute and result.executed < action_limit:
            try:
                # Compute fingerprint
                fingerprint = compute_file_fingerprint(file_path)
                action["fingerprint"] = fingerprint

                # Embed fingerprint in file metadata
                success, skip_reason = embed_fingerprint_in_metadata(str(file_path), fingerprint)
                
                if success:
                    action["status"] = "executed"
                    result.executed += 1
                    result.succeeded += 1
                    logger.info(f"✅ Added fingerprint to {file_path.name}")

                    # Sync to Eagle tags
                    if str(file_path) in eagle_items_by_path:
                        eagle_item = eagle_items_by_path[str(file_path)]
                        eagle_item_id = eagle_item.get("id")
                        existing_tags = eagle_item.get("tags", [])
                        fp_tag = f"fingerprint:{fingerprint}"

                        # Check if fingerprint tag already exists
                        has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in existing_tags)
                        if not has_fp_tag:
                            # Add fingerprint tag
                            new_tags = existing_tags + [fp_tag]
                            if eagle_update_tags(eagle_base, eagle_token, eagle_item_id, new_tags):
                                logger.debug(f"✅ Synced fingerprint to Eagle tags: {file_path.name}")
                            else:
                                logger.warning(f"⚠️  Failed to sync fingerprint to Eagle tags: {file_path.name}")

                    # Update Notion track if linked
                    if notion and tracks_db_id:
                        if update_notion_track_fingerprint(notion, tracks_db_id, str(file_path), fingerprint):
                            logger.debug(f"✅ Updated Notion track fingerprint: {file_path.name}")
                
                elif skip_reason == "unsupported_format":
                    # Unsupported format (WAV, unknown extension) - count as skipped, not failed
                    action["status"] = "skipped"
                    action["skip_reason"] = skip_reason
                    result.skipped += 1
                    logger.debug(f"⏭️  Skipped unsupported format: {file_path.name} ({Path(file_path).suffix})")
                
                else:
                    # Actual error occurred - count as failed
                    action["status"] = "failed"
                    action["error"] = "Failed to embed fingerprint in metadata"
                    result.failed += 1
                    result.errors.append({
                        "action": "add_fingerprint",
                        "path": str(file_path),
                        "error": "Failed to embed fingerprint in metadata"
                    })
                    logger.warning(f"⚠️  Failed to embed fingerprint in {file_path.name}")

            except Exception as e:
                action["status"] = "failed"
                action["error"] = str(e)
                result.failed += 1
                result.errors.append({
                    "action": "add_fingerprint",
                    "path": str(file_path),
                    "error": str(e)
                })
                logger.error(f"❌ Error processing {file_path.name}: {e}")

    return result


def execute_remediation(
    dedupe_groups: List[Dict[str, Any]],
    playlist_mismatches: List[Dict[str, Any]],
    execute: bool,
    action_limit: int,
    action_mode: str = ACTION_MODE_COPY,
    backup_dir: Optional[Path] = None,
) -> RemediationResult:
    """Execute remediation actions with proper error handling and backups.

    Args:
        dedupe_groups: Duplicate file groups to process
        playlist_mismatches: Playlist folder mismatches to fix
        execute: If True, actually perform actions; otherwise dry-run
        action_limit: Maximum number of actions to execute
        action_mode: One of 'copy', 'move', or 'link'
        backup_dir: Directory for backups before deletions (required if execute=True)
    """
    result = RemediationResult()

    # Process duplicate removals
    for group in dedupe_groups:
        master = group["master"]
        for dupe in group["duplicates"]:
            action = {
                "action": "remove_duplicate",
                "path": dupe,
                "master": master,
                "status": "planned"
            }
            result.actions.append(action)
            result.planned += 1

            if execute and result.executed < action_limit:
                result.executed += 1
                dupe_path = Path(dupe)

                # Backup before deletion
                if backup_dir:
                    backup_result = backup_file(dupe_path, backup_dir)
                    if not backup_result:
                        action["status"] = "failed"
                        action["error"] = "Backup failed"
                        result.failed += 1
                        result.errors.append({
                            "action": "remove_duplicate",
                            "path": dupe,
                            "error": "Failed to create backup before deletion"
                        })
                        continue
                    action["backup_path"] = str(backup_result)

                try:
                    dupe_path.unlink()
                    action["status"] = "executed"
                    result.succeeded += 1
                    logger.info(f"Removed duplicate: {dupe}")
                except Exception as e:
                    action["status"] = "failed"
                    action["error"] = str(e)
                    result.failed += 1
                    result.errors.append({
                        "action": "remove_duplicate",
                        "path": dupe,
                        "error": str(e)
                    })
                    logger.error(f"Failed to remove duplicate {dupe}: {e}")

    # Process playlist folder mismatches - copy/move/link to ALL expected directories
    for mismatch in playlist_mismatches:
        if mismatch.get("issue") != "playlist_folder_mismatch":
            continue
        source = mismatch.get("path")
        expected_dirs = mismatch.get("expected_dirs") or []
        if not source or not expected_dirs:
            continue

        source_path = Path(source)

        # Process ALL expected directories, not just the first one
        for index, expected_dir_str in enumerate(expected_dirs):
            dest_dir = Path(expected_dir_str)
            dest_path = dest_dir / source_path.name

            # Skip if destination already exists
            if dest_path.exists():
                result.skipped += 1
                continue

            effective_mode = action_mode
            if action_mode == ACTION_MODE_MOVE and index > 0:
                effective_mode = ACTION_MODE_COPY

            action = {
                "action": f"{effective_mode}_to_playlist",
                "source": str(source_path),
                "dest": str(dest_path),
                "playlist": mismatch.get("playlist", []),
                "status": "planned"
            }
            result.actions.append(action)
            result.planned += 1

            if execute and result.executed < action_limit:
                result.executed += 1
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    if effective_mode == ACTION_MODE_COPY:
                        shutil.copy2(source_path, dest_path)
                    elif effective_mode == ACTION_MODE_MOVE:
                        shutil.move(source_path, dest_path)
                        source_path = dest_path
                    elif effective_mode == ACTION_MODE_LINK:
                        dest_path.symlink_to(source_path.resolve())

                    action["status"] = "executed"
                    result.succeeded += 1
                    logger.info(f"{effective_mode.title()}d {action['source']} to {dest_path}")
                except Exception as e:
                    action["status"] = "failed"
                    action["error"] = str(e)
                    result.failed += 1
                    result.errors.append({
                        "action": f"{effective_mode}_to_playlist",
                        "source": str(source_path),
                        "dest": str(dest_path),
                        "error": str(e)
                    })
                    logger.error(f"Failed to {effective_mode} {source_path} to {dest_path}: {e}")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Music Library Remediation & Compliance System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run with hash-based deduplication
  python music_library_remediation.py --with-hash --fast-hash

  # Execute remediation with backups
  python music_library_remediation.py --execute --backup-dir ./backups

  # Use move mode instead of copy for playlist fixes
  python music_library_remediation.py --execute --action-mode move

  # Validate file integrity during scan
  python music_library_remediation.py --validate-integrity
        """
    )
    parser.add_argument("--tracks-db-id", default=os.getenv("TRACKS_DB_ID", ""))
    parser.add_argument("--directories-db-id", default=os.getenv("MUSIC_DIRECTORIES_DB_ID", ""))
    parser.add_argument("--out-dir", default=os.getenv("OUT_DIR", "/Volumes/VIBES/Playlists"))
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--backup-dir", default=None, help="Directory for backups before deletions")
    parser.add_argument("--with-hash", action="store_true", help="Compute SHA-256 hashes for dedupe")
    parser.add_argument("--fast-hash", action="store_true", help="Use partial hashing for large files")
    parser.add_argument("--validate-integrity", action="store_true", help="Validate audio file integrity")
    parser.add_argument("--include-eagle", action="store_true", help="Check Eagle for missing items")
    parser.add_argument("--execute", action="store_true", help="Execute remediation actions")
    parser.add_argument("--max-actions", type=int, default=25, help="Limit executed actions")
    parser.add_argument("--fingerprints", action="store_true", help="Add fingerprints to files missing them")
    parser.add_argument("--fingerprint-limit", type=int, default=100, help="Maximum files to fingerprint (default: 100)")
    parser.add_argument(
        "--action-mode",
        choices=list(ACTION_MODES),
        default=ACTION_MODE_COPY,
        help="Action mode for playlist fixes: copy, move, or link (default: copy)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate backup-dir requirement for execute mode
    backup_path = None
    if args.execute:
        if not args.backup_dir:
            # Use default backup directory
            args.backup_dir = os.path.join(args.report_dir, "backups")
            logger.info(f"Using default backup directory: {args.backup_dir}")
        backup_path = Path(args.backup_dir)

    load_unified_env()
    unified_config = get_unified_config()

    notion = None
    if get_notion_client and (get_notion_token or os.getenv("NOTION_TOKEN")):
        try:
            notion = get_notion_client()
        except Exception as e:
            logger.warning(f"Failed to initialize Notion client: {e}")
            notion = None

    directories_db_id = (
        args.directories_db_id
        or unified_config.get("music_directories_db_id")
        or os.getenv("MUSIC_DIRECTORIES_DB_ID", "")
    )
    tracks_db_id = args.tracks_db_id or unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID", "")
    scan_paths = load_music_directories(notion, directories_db_id)

    logger.info(f"Starting scan of {len(scan_paths)} directories")
    records, missing_paths = scan_directories(
        scan_paths,
        args.with_hash,
        args.fast_hash,
        args.validate_integrity
    )
    dedupe_groups, duplicates = dedupe_inventory(records)

    # Skip playlist consistency check if only doing fingerprint remediation
    # This avoids querying the entire Notion database unnecessarily
    playlist_check: Dict[str, Any] = {"mismatches": []}
    playlist_mismatches: List[Dict[str, Any]] = []
    if not args.fingerprints:
        # Only run playlist check if not doing fingerprint-only mode
        playlist_check = validate_playlist_consistency(notion, tracks_db_id, Path(args.out_dir))
        playlist_mismatches = playlist_check.get("mismatches", []) if isinstance(playlist_check, dict) else []

    eagle_check: Dict[str, Any] = {"missing_in_eagle": [], "count": 0}
    if args.include_eagle:
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
        eagle_items = eagle_fetch_all_items(eagle_base, eagle_token)
        eagle_check = reconcile_eagle(eagle_items, records)

    # Execute fingerprint remediation if requested
    fingerprint_remediation = None
    if args.fingerprints:
        logger.info("Starting fingerprint remediation...")
        eagle_base = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "")
        eagle_token = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
        fingerprint_remediation = execute_fingerprint_remediation(
            records,
            args.execute,
            eagle_base if args.include_eagle else None,
            eagle_token if args.include_eagle else None,
            notion,
            tracks_db_id,
            args.fingerprint_limit
        )
        logger.info(f"Fingerprint remediation: {fingerprint_remediation.planned} planned, "
                   f"{fingerprint_remediation.executed} executed, "
                   f"{fingerprint_remediation.succeeded} succeeded, "
                   f"{fingerprint_remediation.failed} failed, "
                   f"{fingerprint_remediation.skipped} skipped")

    remediation = execute_remediation(
        dedupe_groups,
        playlist_mismatches,
        args.execute,
        args.max_actions,
        args.action_mode,
        backup_path
    )

    report = build_report(scan_paths, records, missing_paths, dedupe_groups, playlist_check, eagle_check)
    report["remediation"] = {
        "planned": remediation.planned,
        "executed": remediation.executed,
        "succeeded": remediation.succeeded,
        "failed": remediation.failed,
        "skipped": remediation.skipped,
        "actions": remediation.actions,
        "errors": remediation.errors,
    }
    if fingerprint_remediation:
        report["fingerprint_remediation"] = {
            "planned": fingerprint_remediation.planned,
            "executed": fingerprint_remediation.executed,
            "succeeded": fingerprint_remediation.succeeded,
            "failed": fingerprint_remediation.failed,
            "skipped": fingerprint_remediation.skipped,
            "actions": fingerprint_remediation.actions,
            "errors": fingerprint_remediation.errors,
        }
    report_path = write_report(report, Path(args.report_dir))

    # Summary output
    print(f"\n{'='*60}")
    print(f"MUSIC LIBRARY REMEDIATION REPORT")
    print(f"{'='*60}")
    print(f"Files scanned: {len(records)}")
    if args.validate_integrity:
        valid = sum(1 for r in records if r.is_valid)
        invalid = len(records) - valid
        print(f"Valid files: {valid}, Invalid: {invalid}")
    print(f"Duplicate groups: {len(dedupe_groups)}")
    print(f"Playlist mismatches: {len(playlist_mismatches)}")
    print(f"Actions planned: {remediation.planned}")
    if args.execute:
        print(f"Actions executed: {remediation.executed}")
        print(f"Succeeded: {remediation.succeeded}, Failed: {remediation.failed}")
    if args.fingerprints and fingerprint_remediation:
        print(f"\nFingerprint remediation:")
        print(f"  Planned: {fingerprint_remediation.planned}")
        if args.execute:
            print(f"  Executed: {fingerprint_remediation.executed}")
            print(f"  Succeeded: {fingerprint_remediation.succeeded}, Failed: {fingerprint_remediation.failed}")
        print(f"  Skipped (already has fingerprint): {fingerprint_remediation.skipped}")
    print(f"Report written: {report_path}")
    print(f"{'='*60}\n")

    if remediation.errors:
        logger.warning(f"Completed with {len(remediation.errors)} errors")
        return 1

    logger.info("Remediation completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
