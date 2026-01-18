#!/usr/bin/env python3
"""
Notion Track Queries
====================

Query tracks from Notion database for processing.
Supports filtering by fingerprint status, processing status, file paths, and metadata completeness.

Provides both batch and streaming (generator) interfaces for processing tracks as they're found.
"""

import logging
import json
from typing import List, Dict, Any, Optional, Iterator, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Sort mode rotation for query variety
SORT_MODES = [
    {"timestamp": "last_edited_time", "direction": "descending"},  # Mode 0: Last Edited Descending
    {"timestamp": "created_time", "direction": "descending"},       # Mode 1: Created Descending
    {"timestamp": "last_edited_time", "direction": "ascending"},    # Mode 2: Last Edited Ascending
    {"timestamp": "created_time", "direction": "ascending"},        # Mode 3: Created Ascending
]

SORT_MODE_STATE_FILE = Path(__file__).parent / ".sort_mode_state.json"


def _get_next_sort_mode() -> int:
    """Get the next sort mode index, rotating through 0-3."""
    current_mode = 0
    try:
        if SORT_MODE_STATE_FILE.exists():
            with open(SORT_MODE_STATE_FILE, "r") as f:
                state = json.load(f)
                current_mode = state.get("last_sort_mode", -1)
    except Exception as e:
        logger.debug(f"Could not read sort mode state: {e}")

    # Rotate to next mode (0 -> 1 -> 2 -> 3 -> 0)
    next_mode = (current_mode + 1) % len(SORT_MODES)

    # Save the new mode
    try:
        with open(SORT_MODE_STATE_FILE, "w") as f:
            json.dump({"last_sort_mode": next_mode}, f)
    except Exception as e:
        logger.debug(f"Could not save sort mode state: {e}")

    return next_mode


def get_sort_mode_description(mode_index: int) -> str:
    """Get human-readable description of sort mode."""
    descriptions = [
        "Last Edited Time: Descending (newest edits first)",
        "Created Time: Descending (newest first)",
        "Last Edited Time: Ascending (oldest edits first)",
        "Created Time: Ascending (oldest first)",
    ]
    return descriptions[mode_index] if 0 <= mode_index < len(descriptions) else "Unknown"

# Import per-format fingerprint schema
try:
    from shared_core.fingerprint_schema import (
        FINGERPRINT_PROPERTIES,
        FILE_PATH_PROPERTIES,
        LEGACY_FINGERPRINT_PROPERTIES,
        FORMAT_PRIORITY,
        extract_track_fingerprints,
        has_per_format_fingerprint,
        has_legacy_fingerprint_only,
    )
    FINGERPRINT_SCHEMA_AVAILABLE = True
except ImportError:
    FINGERPRINT_SCHEMA_AVAILABLE = False
    # Fallback constants
    FINGERPRINT_PROPERTIES = {
        "m4a": ["M4A Fingerprint", "M4A Fingerprint Part 2", "M4A Fingerprint Part 3"],
        "wav": ["WAV Fingerprint", "WAV Fingerprint Part 2", "WAV Fingerprint Part 3"],
        "aiff": ["AIFF Fingerprint", "AIFF Fingerprint Part 2", "AIFF Fingerprint Part 3"],
    }
    FILE_PATH_PROPERTIES = {
        "m4a": "M4A File Path",
        "wav": "WAV File Path",
        "aiff": "AIFF File Path",
    }
    # Legacy properties (Primary/Secondary/Tertiary renamed to AIFF/WAV/M4A)
    LEGACY_FINGERPRINT_PROPERTIES = [
        "Fingerprint", "Fingerprint Part 2", "Fingerprint SHA", "fingerprint_sha"
    ]
    # AIFF is primary format
    FORMAT_PRIORITY = ["aiff", "wav", "m4a"]

try:
    from shared_core.notion.token_manager import get_notion_client
    from unified_config import get_unified_config
except ImportError:
    get_notion_client = None
    get_notion_token = None


# Cache for database property types
_tracks_db_prop_types = None


def reset_cache() -> None:
    """Reset all cached state. Call this to force fresh queries."""
    global _tracks_db_prop_types
    _tracks_db_prop_types = None
    logger.info("Notion track queries cache has been reset")


def _get_tracks_db_prop_types(notion_client: Any, tracks_db_id: str) -> Dict[str, str]:
    """Get property types from Notion database schema."""
    global _tracks_db_prop_types
    if _tracks_db_prop_types is None:
        try:
            db_meta = notion_client.databases.retrieve(database_id=tracks_db_id)
            props = db_meta.get("properties", {})
            _tracks_db_prop_types = {name: info.get("type") for name, info in props.items()}
            logger.debug(f"Cached Tracks DB property types: {len(_tracks_db_prop_types)} properties")
        except Exception as e:
            logger.warning(f"Could not fetch Tracks DB property types: {e}")
            _tracks_db_prop_types = {}
    return _tracks_db_prop_types


def _get_prop_value(prop: Dict[str, Any]) -> Optional[str]:
    """Extract text value from Notion property."""
    if not prop:
        return None
    
    prop_type = prop.get("type")
    if prop_type == "title":
        title_array = prop.get("title", [])
        if title_array:
            return title_array[0].get("plain_text", "")
    elif prop_type == "rich_text":
        rich_text_array = prop.get("rich_text", [])
        if rich_text_array:
            return rich_text_array[0].get("plain_text", "")
    elif prop_type == "url":
        return prop.get("url")
    elif prop_type == "number":
        num = prop.get("number")
        return str(num) if num is not None else None
    
    return None


def _filter_is_empty(prop_name: str, prop_types: Dict[str, str]) -> Optional[Dict]:
    """Create filter for empty property based on actual property type."""
    prop_type = prop_types.get(prop_name)
    if not prop_type:
        return None
    
    if prop_type == "url":
        return {"property": prop_name, "url": {"is_empty": True}}
    if prop_type == "rich_text":
        return {"property": prop_name, "rich_text": {"is_empty": True}}
    if prop_type == "title":
        return {"property": prop_name, "title": {"is_empty": True}}
    
    return None


def _filter_is_not_empty(prop_name: str, prop_types: Dict[str, str]) -> Optional[Dict]:
    """Create filter for non-empty property based on actual property type."""
    prop_type = prop_types.get(prop_name)
    if not prop_type:
        return None
    
    if prop_type == "url":
        return {"property": prop_name, "url": {"is_not_empty": True}}
    if prop_type == "rich_text":
        return {"property": prop_name, "rich_text": {"is_not_empty": True}}
    if prop_type == "title":
        return {"property": prop_name, "title": {"is_not_empty": True}}
    
    return None


def _filter_checkbox_equals(prop_name: str, value: bool, prop_types: Dict[str, str]) -> Optional[Dict]:
    """Create filter for checkbox property."""
    prop_type = prop_types.get(prop_name)
    if prop_type == "checkbox":
        return {"property": prop_name, "checkbox": {"equals": value}}
    return None


def _track_needs_processing(track: Dict[str, Any], filter_mode: str = "all") -> bool:
    """
    Check if a track needs processing based on workflow completion status.

    FILTER MODES:
    - "all" (default): CONSERVATIVE - Returns True if ANY criteria is missing
    - "fingerprint_only": Returns True only if fingerprint-related criteria is missing

    CONSERVATIVE CRITERIA (all mode) - Returns True if ANY of these conditions are met:
    1. Missing per-format fingerprint for existing file paths
    2. Missing ALL file paths (M4A, WAV, AIFF - no output files exist)
    3. Missing Eagle ID (not imported to Eagle library)
    4. Missing BPM (audio analysis not complete)
    5. Missing Key (audio analysis not complete)
    6. Missing Title or Artist Name (incomplete metadata)

    FINGERPRINT-ONLY CRITERIA - Returns True if:
    1. Missing per-format fingerprint for existing file paths, OR
    2. Missing ALL file paths (M4A, WAV, AIFF - no output files exist)

    Per-format fingerprint schema (2026-01-14):
    - M4A File Path -> M4A Fingerprint, M4A Fingerprint Part 2, M4A Fingerprint Part 3
    - WAV File Path -> WAV Fingerprint, WAV Fingerprint Part 2, WAV Fingerprint Part 3
    - AIFF File Path -> AIFF Fingerprint, AIFF Fingerprint Part 2, AIFF Fingerprint Part 3

    Legacy fingerprint fields are deprecated but still checked for backward compatibility.
    """
    props = track.get("properties", {})

    # Check per-format fingerprint status (NEW SCHEMA)
    # A track needs fingerprinting if it has a file path but missing the corresponding fingerprint
    has_fingerprint = False
    needs_format_fingerprint = False

    # Check each format: if file path exists, corresponding fingerprint should exist
    for fmt in FORMAT_PRIORITY:
        file_path_prop = FILE_PATH_PROPERTIES.get(fmt)
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])

        if not file_path_prop or not fp_props:
            continue

        file_path_value = _get_prop_value(props.get(file_path_prop))

        if file_path_value:
            # File exists - check if fingerprint exists for this format
            primary_fp_prop = fp_props[0] if fp_props else None
            if primary_fp_prop:
                fp_value = _get_prop_value(props.get(primary_fp_prop))
                if fp_value:
                    has_fingerprint = True
                else:
                    # File exists but no fingerprint - needs processing
                    needs_format_fingerprint = True

    # Fallback: Check legacy fingerprint fields (DEPRECATED)
    if not has_fingerprint:
        for fp_prop_name in LEGACY_FINGERPRINT_PROPERTIES:
            fp_prop = props.get(fp_prop_name)
            if fp_prop and _get_prop_value(fp_prop):
                has_fingerprint = True
                # Log deprecation warning for legacy fields
                logger.debug(f"Track using DEPRECATED legacy fingerprint field: {fp_prop_name}")
                break

    # Check file path status - need at least ONE file path (REQUIRED)
    has_any_file_path = any(
        bool(_get_prop_value(props.get(prop_name)))
        for prop_name in ["M4A File Path", "WAV File Path", "AIFF File Path"]
    )

    # Check required metadata (Title + Artist)
    has_title = False
    for title_prop_name in ["Title", "Name"]:
        title_prop = props.get(title_prop_name)
        if title_prop and _get_prop_value(title_prop):
            has_title = True
            break

    has_artist = False
    for artist_prop_name in ["Artist Name", "Artist", "Artists"]:
        artist_prop = props.get(artist_prop_name)
        if artist_prop and _get_prop_value(artist_prop):
            has_artist = True
            break

    # Check Eagle ID status (REQUIRED for library integration)
    has_eagle_id = False
    for eagle_prop_name in ["Eagle ID", "Eagle File ID", "eagle_id", "EagleID"]:
        eagle_prop = props.get(eagle_prop_name)
        if eagle_prop and _get_prop_value(eagle_prop):
            has_eagle_id = True
            break

    # Check BPM status (REQUIRED for audio analysis completion)
    has_bpm = False
    for bpm_prop_name in ["BPM", "bpm", "Tempo"]:
        bpm_prop = props.get(bpm_prop_name)
        if bpm_prop:
            # BPM can be number or text
            prop_type = bpm_prop.get("type")
            if prop_type == "number" and bpm_prop.get("number") is not None:
                has_bpm = True
                break
            elif _get_prop_value(bpm_prop):
                has_bpm = True
                break

    # Check Key status (REQUIRED for audio analysis completion)
    has_key = False
    for key_prop_name in ["Key", "key", "Key ", "Musical Key"]:  # Note: "Key " has trailing space in some schemas
        key_prop = props.get(key_prop_name)
        if key_prop and _get_prop_value(key_prop):
            has_key = True
            break

    # Track needs processing based on filter_mode
    missing_properties = []

    # Always check fingerprint-related criteria
    if not has_fingerprint or needs_format_fingerprint:
        missing_properties.append("fingerprint" if not has_fingerprint else "per_format_fingerprint")
    if not has_any_file_path:
        missing_properties.append("file_paths")

    # For fingerprint_only mode, we only care about fingerprint and file path criteria
    if filter_mode == "fingerprint_only":
        needs_processing = len(missing_properties) > 0
        if needs_processing and logger.isEnabledFor(logging.DEBUG):
            track_id = track.get("id", "unknown")[:8]
            logger.debug(f"Track {track_id} needs fingerprint processing - missing: {', '.join(missing_properties)}")
        return needs_processing

    # For "all" mode, also check metadata and other criteria (Title, Artist, Eagle ID, BPM, Key)
    if not has_title:
        missing_properties.append("title")
    if not has_artist:
        missing_properties.append("artist")
    if not has_eagle_id:
        missing_properties.append("eagle_id")
    if not has_bpm:
        missing_properties.append("bpm")
    if not has_key:
        missing_properties.append("key")

    needs_processing = len(missing_properties) > 0

    if needs_processing and logger.isEnabledFor(logging.DEBUG):
        track_id = track.get("id", "unknown")[:8]
        logger.debug(f"Track {track_id} needs processing - missing: {', '.join(missing_properties)}")

    return needs_processing


def _build_processing_query_filter(prop_types: Dict[str, str], filter_mode: str = "all") -> Optional[Dict]:
    """
    Build Notion query filter for tracks needing processing.

    FILTER MODES:
    - "all" (default): CONSERVATIVE - Matches tracks missing ANY criteria
    - "fingerprint_only": Only matches tracks missing fingerprint-related criteria

    CONSERVATIVE CRITERIA (all mode) - Matches tracks missing ANY of:
    1. Per-format fingerprint for file paths that exist (NEW SCHEMA 2026-01-14)
    2. ALL file paths (M4A AND WAV AND AIFF all empty)
    3. Eagle ID (any variant)
    4. BPM
    5. Key
    6. Title or Artist Name (incomplete metadata)

    FINGERPRINT-ONLY CRITERIA - Matches tracks where:
    1. Per-format fingerprint is missing for file paths that exist, OR
    2. ALL file paths are empty

    Per-format fingerprint schema:
    - M4A File Path -> M4A Fingerprint (primary check)
    - WAV File Path -> WAV Fingerprint (primary check)
    - AIFF File Path -> AIFF Fingerprint (primary check)

    This is an OR filter - tracks matching ANY condition are included.
    """
    or_filters = []

    # Condition 1: Per-format fingerprint is empty when file path exists (NEW SCHEMA)
    # For each format: if file path is NOT empty AND fingerprint IS empty -> needs processing
    for fmt in FORMAT_PRIORITY:
        file_path_prop = FILE_PATH_PROPERTIES.get(fmt)
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])

        if not file_path_prop or not fp_props:
            continue

        primary_fp_prop = fp_props[0]  # Primary fingerprint property

        # Check if both properties exist in the database
        if file_path_prop in prop_types and primary_fp_prop in prop_types:
            file_path_type = prop_types.get(file_path_prop)
            fp_type = prop_types.get(primary_fp_prop)

            # Build: file_path NOT empty AND fingerprint IS empty
            not_empty_filter = _filter_is_not_empty(file_path_prop, prop_types)
            empty_fp_filter = _filter_is_empty(primary_fp_prop, prop_types)

            if not_empty_filter and empty_fp_filter:
                or_filters.append({
                    "and": [not_empty_filter, empty_fp_filter]
                })

    # Legacy fallback: Also check legacy fingerprint fields (DEPRECATED)
    # Only if no per-format fingerprints are configured
    if not or_filters:
        fingerprint_empty_filters = []
        for prop_name in LEGACY_FINGERPRINT_PROPERTIES:
            if prop_name in prop_types:
                empty_filter = _filter_is_empty(prop_name, prop_types)
                if empty_filter:
                    fingerprint_empty_filters.append(empty_filter)

        if fingerprint_empty_filters:
            if len(fingerprint_empty_filters) == 1:
                or_filters.append(fingerprint_empty_filters[0])
            else:
                or_filters.append({"or": fingerprint_empty_filters})

    # Condition 2: ALL file paths are empty (track has no output files)
    file_path_empty_filters = []
    for prop_name in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        if prop_name in prop_types:
            empty_filter = _filter_is_empty(prop_name, prop_types)
            if empty_filter:
                file_path_empty_filters.append(empty_filter)

    if file_path_empty_filters:
        if len(file_path_empty_filters) == 1:
            or_filters.append(file_path_empty_filters[0])
        else:
            or_filters.append({"and": file_path_empty_filters})

    # For fingerprint_only mode, skip the remaining filters (Title/Artist, Eagle ID, BPM, Key)
    if filter_mode == "fingerprint_only":
        logger.info(f"Built fingerprint-only query filter with {len(or_filters)} OR conditions")
        return {"or": or_filters} if or_filters else None

    # Condition 3: Title or Artist is empty (all mode only)
    title_empty_filters = []
    for prop_name in ["Title", "Name"]:
        if prop_name in prop_types:
            empty_filter = _filter_is_empty(prop_name, prop_types)
            if empty_filter:
                title_empty_filters.append(empty_filter)
    if title_empty_filters:
        if len(title_empty_filters) == 1:
            or_filters.append(title_empty_filters[0])
        else:
            or_filters.append({"or": title_empty_filters})

    artist_empty_filters = []
    for prop_name in ["Artist Name", "Artist", "Artists"]:
        if prop_name in prop_types:
            empty_filter = _filter_is_empty(prop_name, prop_types)
            if empty_filter:
                artist_empty_filters.append(empty_filter)
    if artist_empty_filters:
        if len(artist_empty_filters) == 1:
            or_filters.append(artist_empty_filters[0])
        else:
            or_filters.append({"or": artist_empty_filters})

    # Condition 4: Eagle ID is empty/missing (all mode only)
    eagle_id_empty_filters = []
    for prop_name in ["Eagle ID", "Eagle File ID", "eagle_id", "EagleID"]:
        if prop_name in prop_types:
            empty_filter = _filter_is_empty(prop_name, prop_types)
            if empty_filter:
                eagle_id_empty_filters.append(empty_filter)

    if eagle_id_empty_filters:
        if len(eagle_id_empty_filters) == 1:
            or_filters.append(eagle_id_empty_filters[0])
        else:
            or_filters.append({"or": eagle_id_empty_filters})

    # Condition 5: BPM is empty/missing (all mode only)
    bpm_empty_filters = []
    for prop_name in ["BPM", "bpm", "Tempo"]:
        if prop_name in prop_types:
            prop_type = prop_types.get(prop_name)
            if prop_type == "number":
                bpm_empty_filters.append({"property": prop_name, "number": {"is_empty": True}})
            elif prop_type in ["rich_text", "title"]:
                empty_filter = _filter_is_empty(prop_name, prop_types)
                if empty_filter:
                    bpm_empty_filters.append(empty_filter)

    if bpm_empty_filters:
        if len(bpm_empty_filters) == 1:
            or_filters.append(bpm_empty_filters[0])
        else:
            or_filters.append({"or": bpm_empty_filters})

    # Condition 6: Key is empty/missing (all mode only)
    key_empty_filters = []
    for prop_name in ["Key", "key", "Key ", "Musical Key"]:
        if prop_name in prop_types:
            empty_filter = _filter_is_empty(prop_name, prop_types)
            if empty_filter:
                key_empty_filters.append(empty_filter)

    if key_empty_filters:
        if len(key_empty_filters) == 1:
            or_filters.append(key_empty_filters[0])
        else:
            or_filters.append({"or": key_empty_filters})

    logger.info(f"Built processing query filter with {len(or_filters)} OR conditions")
    return {"or": or_filters} if or_filters else None


def stream_tracks_for_processing(
    batch_size: int = 100,
    limit: Optional[int] = None,
    process_batch: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    filter_mode: str = "all"
) -> Iterator[List[Dict[str, Any]]]:
    """
    Stream tracks from Notion database that need processing, yielding batches.

    This is a GENERATOR function that yields batches of validated tracks as they're
    fetched from Notion. Use this for processing tracks as they're found instead of
    loading everything into memory first.

    FILTER MODES:
    - "all" (default): CONSERVATIVE - Yields tracks missing ANY of the following
    - "fingerprint_only": FINGERPRINT-FOCUSED - Only yields tracks missing fingerprints

    CRITERIA for "all" mode - Yields tracks missing ANY of:
    - Per-format fingerprint (NEW SCHEMA 2026-01-14):
      - M4A File Path exists but M4A Fingerprint empty
      - WAV File Path exists but WAV Fingerprint empty
      - AIFF File Path exists but AIFF Fingerprint empty
    - Legacy fingerprint fields (DEPRECATED, fallback only)
    - ALL output file paths empty (M4A, WAV, AIFF - need at least one)
    - Eagle ID (any variant: Eagle ID, Eagle File ID, eagle_id, EagleID)
    - BPM (any variant: BPM, bpm, Tempo)
    - Key (any variant: Key, key, Musical Key)

    CRITERIA for "fingerprint_only" mode - Yields tracks where:
    - Per-format fingerprint is missing for file paths that exist, OR
    - ALL file paths are empty (no output files yet)

    The "DL" checkbox is NOT used as a filter - it is unreliable and should be
    validated by actual file existence at processing time.

    Args:
        batch_size: Number of tracks per batch (max 100 for Notion API)
        limit: Maximum total number of tracks to yield (None for all)
        process_batch: Optional callback to process each batch immediately
        filter_mode: "all" for full workflow, "fingerprint_only" for fingerprint processing

    Yields:
        Lists of track page dictionaries with properties (batch_size at a time)
    """
    try:
        notion = get_notion_client()
        if not notion:
            logger.error("Notion client not available")
            return

        unified_config = get_unified_config()
        tracks_db_id = unified_config.get("tracks_db_id") or None

        if not tracks_db_id:
            logger.error("TRACKS_DB_ID not configured")
            return

        # Get property types first
        prop_types = _get_tracks_db_prop_types(notion, tracks_db_id)

        # Build query filter based on filter_mode
        query_filter = _build_processing_query_filter(prop_types, filter_mode=filter_mode)

        # Get rotating sort mode for query variety
        sort_mode_index = _get_next_sort_mode()
        sort_config = SORT_MODES[sort_mode_index]
        sort_description = get_sort_mode_description(sort_mode_index)

        # Build query with rotating sort order
        query = {
            "sorts": [sort_config],
            "page_size": min(batch_size, 100)  # Notion API max is 100
        }
        if query_filter:
            query["filter"] = query_filter

        # Pagination state
        has_more = True
        start_cursor = None
        page_count = 0
        total_yielded = 0

        mode_desc = "fingerprint only" if filter_mode == "fingerprint_only" else "all criteria"
        logger.info(f"Streaming tracks needing processing (mode: {mode_desc})...")
        logger.info(f"  Batch size: {batch_size}")
        logger.info(f"  Sort Mode [{sort_mode_index}]: {sort_description}")
        if limit:
            logger.info(f"  Limit: {limit} tracks")

        while has_more:
            if start_cursor:
                query["start_cursor"] = start_cursor

            try:
                response = notion.databases.query(database_id=tracks_db_id, **query)
                results = response.get("results", [])
                page_count += 1

                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")

                # Validate and filter tracks using appropriate validation function
                validated_tracks = [t for t in results if _track_needs_processing(t, filter_mode=filter_mode)]

                if validated_tracks:
                    # Apply limit if needed
                    if limit and total_yielded + len(validated_tracks) > limit:
                        validated_tracks = validated_tracks[:limit - total_yielded]
                        has_more = False  # Stop after this batch

                    total_yielded += len(validated_tracks)
                    logger.info(f"  Page {page_count}: yielding {len(validated_tracks)} tracks (total: {total_yielded})")

                    # Call process_batch callback if provided
                    if process_batch:
                        process_batch(validated_tracks)

                    yield validated_tracks

                    # Check if we've hit the limit
                    if limit and total_yielded >= limit:
                        logger.info(f"  Reached limit: {limit}")
                        break
                else:
                    logger.debug(f"  Page {page_count}: no valid tracks in batch")

            except Exception as e:
                logger.error(f"Error querying Notion database: {e}")
                break

        logger.info(f"Stream complete: {total_yielded} tracks yielded from {page_count} pages")
        logger.info(f"  - DL checkbox: IGNORED (validated by file existence at processing time)")

    except Exception as e:
        logger.error(f"Failed to stream tracks from Notion: {e}")
        import traceback
        traceback.print_exc()


def query_tracks_for_processing(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Query tracks from Notion database that need processing (batch mode).

    This collects ALL matching tracks into memory. For large databases,
    consider using stream_tracks_for_processing() instead.

    STRICT CRITERIA - Returns ALL tracks where:
    - Fingerprint property is empty/missing, OR
    - ALL output file paths are empty/missing (M4A, WAV, AIFF)

    The "DL" checkbox is NOT used as a filter - it is unreliable and should be
    validated by actual file existence at processing time.

    Args:
        limit: Maximum number of tracks to return (None for all)

    Returns:
        List of track page dictionaries with properties
    """
    # Use streaming function and collect all results
    all_tracks = []
    for batch in stream_tracks_for_processing(batch_size=100, limit=limit):
        all_tracks.extend(batch)

    logger.info(f"Batch query complete: {len(all_tracks)} tracks collected")
    return all_tracks
