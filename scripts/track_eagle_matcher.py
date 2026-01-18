#!/usr/bin/env python3
"""
Track-to-Eagle Matcher
======================

Match Notion tracks to Eagle items using cascading strategy:
1. File path matching (primary)
2. Filename/title matching (fallback 1)
3. Fuzzy metadata matching with artist, BPM, Key (fallback 2)
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

try:
    from scripts.eagle_path_resolution import resolve_eagle_item_path, get_eagle_library_path
except ImportError:
    def resolve_eagle_item_path(item: dict, library_path=None):
        return item.get("path")
    def get_eagle_library_path():
        return None


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


def _normalize_path(path_str: str) -> Optional[Path]:
    """Normalize and resolve file path."""
    try:
        if not path_str:
            return None
        path = Path(path_str).expanduser().resolve()
        return path if path.exists() else None
    except Exception:
        return None


def _fuzzy_similarity(str1: str, str2: str) -> float:
    """Calculate fuzzy similarity between two strings."""
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def match_by_file_path(track: Dict[str, Any], eagle_items: List[Dict[str, Any]]) -> Optional[Tuple[Dict, str]]:
    """
    Match track to Eagle item by file path properties.

    Returns:
        (eagle_item, match_type) or None
    """
    props = track.get("properties", {})
    library_path = get_eagle_library_path()

    # Check M4A/WAV/AIFF File Path properties
    path_properties = ["M4A File Path", "WAV File Path", "AIFF File Path"]

    for prop_name in path_properties:
        path_prop = props.get(prop_name)
        if not path_prop:
            continue

        file_path_str = _get_prop_value(path_prop)
        if not file_path_str:
            continue

        normalized_path = _normalize_path(file_path_str)
        if not normalized_path:
            continue

        # Try to match against Eagle item paths
        for eagle_item in eagle_items:
            # Try direct path from item
            item_path = eagle_item.get("path", "")
            if item_path:
                try:
                    eagle_path = Path(item_path).expanduser().resolve()
                    if eagle_path == normalized_path:
                        logger.debug(f"Matched by file path: {normalized_path}")
                        return (eagle_item, "file_path")
                except Exception:
                    pass

            # Try resolved path using workaround
            try:
                resolved_path = resolve_eagle_item_path(eagle_item, library_path)
                if resolved_path and resolved_path.resolve() == normalized_path.resolve():
                    logger.debug(f"Matched by resolved file path: {normalized_path}")
                    return (eagle_item, "file_path")
            except Exception:
                continue

    return None


def match_by_filename(
    track: Dict[str, Any],
    eagle_items: List[Dict[str, Any]],
    threshold: float = 0.85
) -> Optional[Tuple[Dict, str]]:
    """
    Match track to Eagle item by filename/title.

    Returns:
        (eagle_item, match_type) or None
    """
    props = track.get("properties", {})

    # Extract filename from title or file path
    title = _get_prop_value(props.get("Title") or props.get("title"))
    if not title:
        # Try to get from file path
        for prop_name in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
            path_prop = props.get(prop_name)
            if path_prop:
                path_str = _get_prop_value(path_prop)
                if path_str:
                    title = Path(path_str).stem
                    break

    if not title:
        return None

    # Normalize title for matching
    title_normalized = title.lower().strip()

    best_match = None
    best_score = 0.0
    # High threshold for filename matching (default matches existing behavior)
    threshold = max(min(threshold, 1.0), 0.0)

    for eagle_item in eagle_items:
        item_name = eagle_item.get("name", "").lower().strip()
        if not item_name:
            continue

        # Calculate similarity
        score = _fuzzy_similarity(title_normalized, item_name)

        if score >= threshold and score > best_score:
            best_score = score
            best_match = eagle_item

    if best_match:
        logger.debug(f"Matched by filename: {title} -> {best_match.get('name')} (score: {best_score:.2f})")
        return (best_match, "filename")

    return None


def match_by_metadata(
    track: Dict[str, Any],
    eagle_items: List[Dict[str, Any]],
    threshold: float = 0.6
) -> Optional[Tuple[Dict, str]]:
    """
    Match track to Eagle item by fuzzy metadata matching (artist, BPM, Key).

    Priority: artist (weight 0.5) > BPM (weight 0.3) > Key (weight 0.2)

    Returns:
        (eagle_item, match_type) or None
    """
    props = track.get("properties", {})

    # Extract metadata from track
    artist = _get_prop_value(props.get("Artist Name") or props.get("Artist"))
    bpm_prop = props.get("BPM") or props.get("bpm")
    bpm = None
    if bpm_prop and bpm_prop.get("type") == "number":
        bpm = bpm_prop.get("number")

    key_prop = props.get("Key") or props.get("key")
    key = _get_prop_value(key_prop)

    if not artist and not bpm and not key:
        return None

    best_match = None
    best_score = 0.0
    # Combined score threshold (default matches existing behavior)
    threshold = max(min(threshold, 1.0), 0.0)

    for eagle_item in eagle_items:
        item_name = eagle_item.get("name", "").lower()
        item_tags = [tag.lower() for tag in eagle_item.get("tags", [])]

        score = 0.0

        # Artist matching (weight 0.5)
        if artist:
            artist_lower = artist.lower().strip()
            artist_in_name = artist_lower in item_name
            artist_in_tags = any(artist_lower in tag for tag in item_tags)

            if artist_in_name or artist_in_tags:
                score += 0.5
            else:
                # Try fuzzy match
                artist_similarity = max(
                    _fuzzy_similarity(artist_lower, item_name),
                    max([_fuzzy_similarity(artist_lower, tag) for tag in item_tags], default=0.0)
                )
                if artist_similarity >= 0.7:
                    score += 0.5 * artist_similarity

        # BPM matching (weight 0.3)
        if bpm is not None:
            # Look for BPM in tags (e.g., "bpm:120", "120bpm")
            bpm_str = str(int(bpm))
            bpm_found = any(
                bpm_str in tag or f"bpm:{bpm_str}" in tag or f"{bpm_str}bpm" in tag
                for tag in item_tags
            )
            if bpm_found:
                score += 0.3

        # Key matching (weight 0.2)
        if key:
            key_lower = key.lower().strip()
            key_found = any(
                key_lower in tag or f"key:{key_lower}" in tag
                for tag in item_tags
            )
            if key_found:
                score += 0.2

        if score >= threshold and score > best_score:
            best_score = score
            best_match = eagle_item

    if best_match:
        logger.debug(f"Matched by metadata: artist={artist}, BPM={bpm}, Key={key} -> {best_match.get('name')} (score: {best_score:.2f})")
        return (best_match, "metadata")

    return None


def find_eagle_item_for_track(
    track: Dict[str, Any],
    eagle_items: List[Dict[str, Any]],
    filename_threshold: float = 0.85,
    metadata_threshold: float = 0.6
) -> Optional[Tuple[Dict, str]]:
    """
    Find matching Eagle item for a Notion track using cascading strategy.

    Strategy order:
    1. File path matching (primary)
    2. Filename/title matching (fallback 1)
    3. Fuzzy metadata matching with artist, BPM, Key (fallback 2)

    Args:
        track: Notion track page dictionary
        eagle_items: List of Eagle item dictionaries
        filename_threshold: Similarity threshold for filename/title matching
        metadata_threshold: Combined score threshold for metadata matching

    Returns:
        (eagle_item, match_type) or None if no match found
    """
    if not track or not eagle_items:
        return None

    # Strategy 1: File path matching
    match = match_by_file_path(track, eagle_items)
    if match:
        return match

    # Strategy 2: Filename/title matching
    match = match_by_filename(track, eagle_items, threshold=filename_threshold)
    if match:
        return match

    # Strategy 3: Fuzzy metadata matching
    match = match_by_metadata(track, eagle_items, threshold=metadata_threshold)
    if match:
        return match

    return None
