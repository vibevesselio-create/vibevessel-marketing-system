#!/usr/bin/env python3
"""
Process Track Workflow
======================

Execute all workflow steps for a single Notion track:
1. Validate track properties
2. Find matching Eagle item
3. Embed fingerprint in file metadata (if needed)
4. Sync fingerprint to Eagle tags
5. Update Notion track properties
6. Validate completeness
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from scripts.music_library_remediation import (
        compute_file_fingerprint,
        embed_fingerprint_in_metadata,
        extract_fingerprint_from_metadata,
        update_notion_track_fingerprint,
        eagle_update_tags
    )
    from scripts.eagle_path_resolution import resolve_eagle_item_path, get_eagle_library_path
    from scripts.track_eagle_matcher import find_eagle_item_for_track
    from scripts.notion_track_validator import validate_track_properties_complete
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    raise

# File path property names to check and clear
FILE_PATH_PROPERTIES = {
    "aiff": "AIFF File Path",
    "wav": "WAV File Path",
    "m4a": "M4A File Path",
}


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


def _get_track_file_path(track: Dict[str, Any]) -> Optional[Path]:
    """Get FIRST file path from track properties (AIFF/WAV/M4A - AIFF is primary)."""
    props = track.get("properties", {})
    # AIFF is primary format
    path_properties = ["AIFF File Path", "WAV File Path", "M4A File Path"]

    for prop_name in path_properties:
        path_prop = props.get(prop_name)
        if path_prop:
            path_str = _get_prop_value(path_prop)
            if path_str:
                try:
                    path = Path(path_str).expanduser().resolve()
                    if path.exists():
                        return path
                except Exception:
                    continue

    return None


def _get_all_track_file_paths(track: Dict[str, Any]) -> Dict[str, Path]:
    """
    Get ALL file paths from track properties (AIFF/WAV/M4A File Path).

    Returns:
        Dictionary mapping format to Path if file exists.
        Order: AIFF first (primary format), then WAV, then M4A.
    """
    props = track.get("properties", {})
    # AIFF is primary format - process first
    format_to_prop = [
        ("aiff", "AIFF File Path"),
        ("wav", "WAV File Path"),
        ("m4a", "M4A File Path"),
    ]

    result = {}
    for fmt, prop_name in format_to_prop:
        path_prop = props.get(prop_name)
        if path_prop:
            path_str = _get_prop_value(path_prop)
            if path_str:
                try:
                    path = Path(path_str).expanduser().resolve()
                    if path.exists():
                        result[fmt] = path
                except Exception:
                    continue

    return result


def _get_track_title(track: Dict[str, Any]) -> str:
    """Get track title from properties."""
    props = track.get("properties", {})
    title = _get_prop_value(props.get("Title") or props.get("title"))
    return title or "Unknown Track"


def _get_invalid_file_paths(track: Dict[str, Any]) -> Dict[str, str]:
    """
    Get file path properties where the file does NOT exist AND fingerprint is empty.

    Only returns paths that need FILE_MISSING to be set (fingerprint empty + file missing).
    Does NOT return paths where fingerprint already exists (even if file is missing).

    Returns:
        Dictionary mapping format to file path string for paths where:
        - File path is set in Notion
        - File does NOT exist on disk
        - Fingerprint is EMPTY (not already set)
    """
    props = track.get("properties", {})
    invalid_paths = {}

    # Fingerprint property names by format
    FINGERPRINT_PROPERTIES = {
        "aiff": "AIFF Fingerprint",
        "wav": "WAV Fingerprint",
        "m4a": "M4A Fingerprint",
    }

    for fmt, prop_name in FILE_PATH_PROPERTIES.items():
        path_prop = props.get(prop_name)
        if path_prop:
            path_str = _get_prop_value(path_prop)
            if path_str:
                # Check if fingerprint is already set
                fp_prop_name = FINGERPRINT_PROPERTIES.get(fmt)
                fp_prop = props.get(fp_prop_name, {})
                fp_value = _get_prop_value(fp_prop)

                # Skip if fingerprint already exists (don't overwrite existing fingerprints)
                if fp_value:
                    continue

                # Check if file exists
                try:
                    path = Path(path_str).expanduser().resolve()
                    if not path.exists():
                        invalid_paths[fmt] = path_str
                except Exception:
                    # Path parsing failed, treat as invalid
                    invalid_paths[fmt] = path_str

    return invalid_paths


def _set_file_missing_fingerprints(
    notion_client: Any,
    track_id: str,
    invalid_paths: Dict[str, str],
    execute: bool = False
) -> bool:
    """
    Set FILE_MISSING sentinel in fingerprint properties for files that don't exist.

    This prevents tracks from being re-queried when their files are missing,
    WITHOUT clearing the file path (preserving the original path for reference).

    Args:
        notion_client: Notion API client
        track_id: Notion page ID
        invalid_paths: Dict of format -> path_str for missing files
        execute: If True, actually update; otherwise dry-run

    Returns:
        True if updated successfully (or would update in dry-run)
    """
    if not notion_client or not track_id or not invalid_paths:
        return False

    # Fingerprint property names by format
    FINGERPRINT_PROPERTIES = {
        "aiff": "AIFF Fingerprint",
        "wav": "WAV Fingerprint",
        "m4a": "M4A Fingerprint",
    }

    # Build update payload to set FILE_MISSING sentinel in fingerprint properties
    update_props = {}
    for fmt, path_str in invalid_paths.items():
        fp_prop_name = FINGERPRINT_PROPERTIES.get(fmt)
        if fp_prop_name:
            # Set sentinel value instead of clearing path
            update_props[fp_prop_name] = {"rich_text": [{"text": {"content": "FILE_MISSING"}}]}
            logger.info(f"    Setting {fp_prop_name} to FILE_MISSING (file not found: {path_str[:40]}...)")

    if not update_props:
        return False

    if execute:
        try:
            notion_client.pages.update(page_id=track_id, properties=update_props)
            logger.info(f"  ✅ Set FILE_MISSING for {len(update_props)} format(s) in Notion")
            return True
        except Exception as e:
            logger.error(f"  ❌ Failed to set FILE_MISSING fingerprints: {e}")
            return False
    else:
        logger.info(f"  [DRY-RUN] Would set FILE_MISSING for {len(update_props)} format(s) in Notion")
        return True


def process_single_track_workflow(
    track: Dict[str, Any],
    eagle_item: Optional[Dict[str, Any]],
    execute: bool = False,
    notion_client: Any = None,
    tracks_db_id: Optional[str] = None,
    eagle_base: Optional[str] = None,
    eagle_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a single track through the complete workflow for ALL file formats.

    Steps for EACH format (M4A, WAV, AIFF):
    1. Validate track has required properties
    2. Find or validate Eagle item
    3. Embed fingerprint in file metadata (if needed)
    4. Sync fingerprint to Eagle tags
    5. Update Notion track properties with per-format fingerprint

    Args:
        track: Notion track page dictionary
        eagle_item: Matching Eagle item (or None if not found)
        execute: If True, actually perform updates; otherwise dry-run
        notion_client: Notion API client
        tracks_db_id: Notion tracks database ID
        eagle_base: Eagle API base URL
        eagle_token: Eagle API token

    Returns:
        Dictionary with processing statistics:
        {
            "track_id": str,
            "track_title": str,
            "eagle_item_found": bool,
            "eagle_item_id": Optional[str],
            "file_path": Optional[str],  # First file path (for compatibility)
            "file_paths_processed": Dict[str, str],  # All formats processed
            "fingerprint_embedded": bool,
            "fingerprint_synced": bool,
            "notion_updated": bool,
            "formats_processed": int,  # Count of formats processed
            "validation": Dict,
            "success": bool,
            "errors": List[str]
        }
    """
    stats = {
        "track_id": track.get("id", "unknown"),
        "track_title": _get_track_title(track),
        "eagle_item_found": False,
        "eagle_item_id": None,
        "file_path": None,
        "file_paths_processed": {},
        "invalid_paths_cleared": [],  # Formats where invalid paths were cleared
        "fingerprint_embedded": False,
        "fingerprint_synced": False,
        "notion_updated": False,
        "formats_processed": 0,
        "validation": {},
        "success": False,
        "errors": []
    }

    try:
        # Step 1: Validate track properties
        validation = validate_track_properties_complete(track)
        stats["validation"] = validation

        if not validation.get("has_file_path"):
            stats["errors"].append("Track missing file path properties")
            logger.warning(f"Track {stats['track_title']} missing file path properties")
            return stats

        # Step 2: Get ALL file paths (M4A, WAV, AIFF) - only returns existing files
        all_file_paths = _get_all_track_file_paths(track)

        # Step 2a: Check for invalid file paths (paths set in Notion but files don't exist)
        # Set FILE_MISSING sentinel to prevent the track from being re-queried indefinitely
        invalid_paths = _get_invalid_file_paths(track)
        if invalid_paths:
            logger.warning(f"Track {stats['track_title']} has {len(invalid_paths)} missing file(s)")
            for fmt, path_str in invalid_paths.items():
                logger.warning(f"  - {fmt.upper()}: {path_str} (FILE NOT FOUND)")

            # Set FILE_MISSING sentinel in fingerprint properties to prevent re-processing
            # This preserves the original file path for reference
            if notion_client and tracks_db_id:
                marked = _set_file_missing_fingerprints(
                    notion_client,
                    stats["track_id"],
                    invalid_paths,
                    execute=execute
                )
                if marked:
                    stats["invalid_paths_cleared"] = list(invalid_paths.keys())

        if not all_file_paths:
            stats["errors"].append("No valid file paths - all files missing or paths invalid")
            logger.warning(f"Track {stats['track_title']} has no valid file paths (all files missing)")
            # Mark as success if we set FILE_MISSING (track won't be re-queried)
            if invalid_paths and notion_client and tracks_db_id:
                stats["success"] = True  # Track is handled - FILE_MISSING set
                logger.info(f"✅ Track {stats['track_title']} marked as handled (FILE_MISSING set)")
            return stats

        # Set first file path for compatibility
        first_fmt = list(all_file_paths.keys())[0]
        stats["file_path"] = str(all_file_paths[first_fmt])
        logger.info(f"Found {len(all_file_paths)} file format(s) to process: {', '.join(all_file_paths.keys())}")

        # Step 3: Validate Eagle item
        if not eagle_item:
            stats["errors"].append("No matching Eagle item found")
            logger.warning(f"Track {stats['track_title']} has no matching Eagle item - skipping")
            return stats

        stats["eagle_item_found"] = True
        stats["eagle_item_id"] = eagle_item.get("id")

        # Track which formats were successfully processed
        formats_embedded = []
        formats_synced = []
        formats_notion_updated = []
        eagle_fingerprint_synced = False

        # Process EACH file format
        for fmt, file_path in all_file_paths.items():
            logger.info(f"  Processing {fmt.upper()} format: {file_path.name}")

            # Step 4: Check if fingerprint already exists in file
            existing_fingerprint = extract_fingerprint_from_metadata(str(file_path))

            # Step 5: Embed fingerprint if needed
            fingerprint = existing_fingerprint
            if not fingerprint:
                if execute:
                    logger.info(f"    Computing fingerprint for {file_path.name}...")
                    fingerprint = compute_file_fingerprint(file_path)

                    if fingerprint:
                        logger.info(f"    Embedding fingerprint in metadata...")
                        if embed_fingerprint_in_metadata(str(file_path), fingerprint):
                            formats_embedded.append(fmt)
                            logger.info(f"    ✅ {fmt.upper()} fingerprint embedded: {fingerprint[:32]}...")
                        else:
                            stats["errors"].append(f"Failed to embed {fmt} fingerprint in metadata")
                    else:
                        stats["errors"].append(f"Failed to compute {fmt} fingerprint")
                else:
                    logger.info(f"    Would compute and embed fingerprint for {file_path.name}")
                    formats_embedded.append(fmt)  # Count as would-be embedded in dry-run
            else:
                logger.debug(f"    {fmt.upper()} fingerprint already exists: {fingerprint[:32]}...")
                formats_embedded.append(fmt)  # Already has fingerprint

            if not fingerprint:
                logger.warning(f"    ⚠️  No fingerprint available for {fmt.upper()}")
                continue  # Skip to next format

            # Track this format as processed
            stats["file_paths_processed"][fmt] = str(file_path)
            stats["formats_processed"] += 1

            # Step 6: Sync fingerprint to Eagle tags (once per track, using first fingerprint)
            if not eagle_fingerprint_synced:
                eagle_item_tags = eagle_item.get("tags", [])
                fp_tag = f"fingerprint:{fingerprint.lower()}"
                has_fp_tag = any(tag.lower().startswith("fingerprint:") for tag in eagle_item_tags)

                if not has_fp_tag:
                    if execute:
                        if eagle_base and eagle_token:
                            new_tags = list(eagle_item_tags) + [fp_tag]
                            if eagle_update_tags(eagle_base, eagle_token, stats["eagle_item_id"], new_tags):
                                eagle_fingerprint_synced = True
                                formats_synced.append(fmt)
                                logger.info(f"    ✅ Fingerprint synced to Eagle tags")
                            else:
                                stats["errors"].append("Failed to sync fingerprint to Eagle tags")
                        else:
                            stats["errors"].append("Eagle API configuration missing")
                    else:
                        logger.info(f"    Would sync fingerprint tag to Eagle")
                        eagle_fingerprint_synced = True
                        formats_synced.append(fmt)
                else:
                    logger.debug(f"    Fingerprint tag already exists in Eagle")
                    eagle_fingerprint_synced = True
                    formats_synced.append(fmt)

            # Step 7: Update Notion track properties with per-format fingerprint
            if notion_client and tracks_db_id:
                if execute:
                    if update_notion_track_fingerprint(notion_client, tracks_db_id, str(file_path), fingerprint):
                        formats_notion_updated.append(fmt)
                        logger.info(f"    ✅ Notion {fmt.upper()} fingerprint updated")
                    else:
                        stats["errors"].append(f"Failed to update Notion {fmt} fingerprint")
                else:
                    logger.info(f"    Would update Notion track with {fmt} fingerprint")
                    formats_notion_updated.append(fmt)

        # Update aggregate stats
        stats["fingerprint_embedded"] = len(formats_embedded) > 0
        stats["fingerprint_synced"] = eagle_fingerprint_synced or len(formats_synced) > 0
        stats["notion_updated"] = len(formats_notion_updated) > 0

        # Step 8: Final validation
        if notion_client and tracks_db_id:
            # When Notion is available, require at least one format fully processed
            if stats["fingerprint_embedded"] and stats["fingerprint_synced"] and stats["notion_updated"]:
                stats["success"] = True
                logger.info(f"✅ Successfully processed track: {stats['track_title']} ({stats['formats_processed']} format(s))")
            else:
                stats["errors"].append("Workflow incomplete (missing fingerprint, sync, or Notion update)")
        else:
            # When Notion is not available, fingerprint embedded + synced is sufficient
            if stats["fingerprint_embedded"] and stats["fingerprint_synced"]:
                stats["success"] = True
                logger.info(f"✅ Successfully processed track: {stats['track_title']} (Notion update skipped - client not available)")
            else:
                stats["errors"].append("Workflow incomplete")

    except Exception as e:
        logger.error(f"Error processing track {stats['track_title']}: {e}")
        import traceback
        traceback.print_exc()
        stats["errors"].append(str(e))
    
    return stats
