#!/usr/bin/env python3
"""
Notion Track Validator
======================

Validate that Notion track properties are complete and populated.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


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
    elif prop_type == "checkbox":
        return prop.get("checkbox", False)
    
    return None


def validate_track_properties_complete(track: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that all expected properties are populated for a Notion track.
    
    Expected properties:
    - Title (required)
    - Artist Name (required)
    - At least one file path (M4A/WAV/AIFF File Path)
    - Fingerprint (optional but preferred)
    - BPM, Key (optional)
    
    Args:
        track: Notion track page dictionary
    
    Returns:
        Dictionary with validation results:
        {
            "is_complete": bool,
            "missing_properties": List[str],
            "has_file_path": bool,
            "has_fingerprint": bool,
            "has_metadata": bool
        }
    """
    if not track:
        return {
            "is_complete": False,
            "missing_properties": ["track"],
            "has_file_path": False,
            "has_fingerprint": False,
            "has_metadata": False
        }
    
    props = track.get("properties", {})
    missing = []
    
    # Check required properties
    title = _get_prop_value(props.get("Title") or props.get("title"))
    if not title:
        missing.append("Title")
    
    artist = _get_prop_value(props.get("Artist Name") or props.get("Artist"))
    if not artist:
        missing.append("Artist Name")
    
    # Check file paths (at least one required)
    file_path_properties = ["M4A File Path", "WAV File Path", "AIFF File Path"]
    has_file_path = False
    for prop_name in file_path_properties:
        path_prop = props.get(prop_name)
        if path_prop:
            path_value = _get_prop_value(path_prop)
            if path_value:
                has_file_path = True
                break
    
    if not has_file_path:
        missing.append("File Path (M4A/WAV/AIFF)")
    
    # Check optional but preferred properties
    fingerprint_props = ["Fingerprint", "fingerprint", "Fingerprint SHA", "fingerprint_sha"]
    has_fingerprint = False
    for prop_name in fingerprint_props:
        fp_prop = props.get(prop_name)
        if fp_prop:
            fp_value = _get_prop_value(fp_prop)
            if fp_value:
                has_fingerprint = True
                break
    
    # Check metadata (BPM, Key - optional)
    bpm_prop = props.get("BPM") or props.get("bpm")
    bpm = None
    if bpm_prop and bpm_prop.get("type") == "number":
        bpm = bpm_prop.get("number")
    
    key_prop = props.get("Key") or props.get("key")
    key = _get_prop_value(key_prop)
    
    has_metadata = bpm is not None or key is not None
    
    is_complete = len(missing) == 0
    
    return {
        "is_complete": is_complete,
        "missing_properties": missing,
        "has_file_path": has_file_path,
        "has_fingerprint": has_fingerprint,
        "has_metadata": has_metadata,
        "title": title,
        "artist": artist,
        "bpm": bpm,
        "key": key
    }
