#!/usr/bin/env python3
"""
Per-Format Fingerprint Schema
=============================

Centralized mapping for per-format fingerprint properties in Notion.

New Schema (2026-01-14):
- File path properties: "M4A File Path", "WAV File Path", "AIFF File Path"
- Per-format fingerprint properties:
  - M4A: "M4A Fingerprint", "M4A Fingerprint Part 2", "M4A Fingerprint Part 3"
  - WAV: "WAV Fingerprint", "WAV Fingerprint Part 2", "WAV Fingerprint Part 3"
  - AIFF: "AIFF Fingerprint", "AIFF Fingerprint Part 2", "AIFF Fingerprint Part 3"

Legacy fields (DEPRECATED - read-only fallback):
- "Primary Fingerprint", "Secondary Fingerprint", "Tertiary Fingerprint"
- "Fingerprint", "Fingerprint Part 2", "Fingerprint Overflow 2"
- "Fingerprint SHA", "fingerprint_sha"

Matching Priority (when multiple formats exist):
1. WAV (highest quality, preferred for matching)
2. M4A (common format)
3. AIFF (alternative lossless)

Version: 2026-01-14
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS: Per-Format Fingerprint Schema
# =============================================================================

# File path property names by format
FILE_PATH_PROPERTIES = {
    "m4a": "M4A File Path",
    "wav": "WAV File Path",
    "aiff": "AIFF File Path",
}

# Per-format fingerprint properties (NEW - canonical schema)
FINGERPRINT_PROPERTIES = {
    "m4a": ["M4A Fingerprint", "M4A Fingerprint Part 2", "M4A Fingerprint Part 3"],
    "wav": ["WAV Fingerprint", "WAV Fingerprint Part 2", "WAV Fingerprint Part 3"],
    "aiff": ["AIFF Fingerprint", "AIFF Fingerprint Part 2", "AIFF Fingerprint Part 3"],
}

# Legacy fingerprint properties (DEPRECATED - read-only fallback)
# NOTE: "Primary Fingerprint" was renamed to "AIFF Fingerprint" (now in per-format schema)
LEGACY_FINGERPRINT_PROPERTIES = [
    "Fingerprint",
    "Fingerprint Part 2",
    "Fingerprint Overflow 2",
    "Fingerprint SHA",
    "fingerprint_sha",
    # "Primary Fingerprint" - REMOVED (renamed to AIFF Fingerprint)
    # "Secondary Fingerprint" - REMOVED (renamed to WAV Fingerprint)
    # "Tertiary Fingerprint" - REMOVED (renamed to M4A Fingerprint)
    "fingerprint",  # lowercase variant
]

# Matching priority order (AIFF first as lossless primary format)
FORMAT_PRIORITY = ["aiff", "wav", "m4a"]

# Maximum fingerprint length per property (Notion rich_text limit)
MAX_FINGERPRINT_CHUNK_LENGTH = 2000


@dataclass
class FormatFingerprint:
    """Fingerprint data for a specific format."""
    format: str
    file_path: Optional[str]
    fingerprint_parts: List[str]  # Up to 3 parts

    @property
    def full_fingerprint(self) -> Optional[str]:
        """Reconstruct full fingerprint from parts."""
        if not self.fingerprint_parts or not any(self.fingerprint_parts):
            return None
        return "".join(p for p in self.fingerprint_parts if p)

    @property
    def has_fingerprint(self) -> bool:
        """Check if any fingerprint data exists."""
        return bool(self.full_fingerprint)


@dataclass
class TrackFingerprints:
    """All fingerprint data for a track across formats."""
    m4a: Optional[FormatFingerprint] = None
    wav: Optional[FormatFingerprint] = None
    aiff: Optional[FormatFingerprint] = None
    legacy_fingerprint: Optional[str] = None  # Deprecated fallback

    def get_best_fingerprint(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the best available fingerprint following priority order.

        Returns:
            Tuple of (fingerprint, format) or (None, None) if no fingerprint found
        """
        # Check formats in priority order
        for fmt in FORMAT_PRIORITY:
            fmt_fp = getattr(self, fmt)
            if fmt_fp and fmt_fp.has_fingerprint:
                return (fmt_fp.full_fingerprint, fmt)

        # Fall back to legacy (DEPRECATED - log warning)
        if self.legacy_fingerprint:
            logger.warning(
                "Using DEPRECATED legacy fingerprint field. "
                "Track should be re-fingerprinted with per-format schema."
            )
            return (self.legacy_fingerprint, "legacy")

        return (None, None)

    def get_fingerprint_for_format(self, fmt: str) -> Optional[str]:
        """Get fingerprint for a specific format."""
        fmt_fp = getattr(self, fmt.lower(), None)
        if fmt_fp:
            return fmt_fp.full_fingerprint
        return None

    @property
    def has_any_fingerprint(self) -> bool:
        """Check if any fingerprint exists (including legacy)."""
        fp, _ = self.get_best_fingerprint()
        return fp is not None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_format_from_extension(file_path: str) -> Optional[str]:
    """
    Determine audio format from file extension.

    Args:
        file_path: Path to audio file

    Returns:
        Format string ('m4a', 'wav', 'aiff') or None if unsupported
    """
    if not file_path:
        return None

    ext = Path(file_path).suffix.lower()

    # Map extensions to canonical format names
    extension_map = {
        ".m4a": "m4a",
        ".mp4": "m4a",
        ".aac": "m4a",
        ".alac": "m4a",
        ".wav": "wav",
        ".aiff": "aiff",
        ".aif": "aiff",
    }

    return extension_map.get(ext)


def get_fingerprint_properties_for_format(fmt: str) -> List[str]:
    """
    Get fingerprint property names for a specific format.

    Args:
        fmt: Format string ('m4a', 'wav', 'aiff')

    Returns:
        List of property names for fingerprint parts
    """
    return FINGERPRINT_PROPERTIES.get(fmt.lower(), [])


def get_file_path_property_for_format(fmt: str) -> Optional[str]:
    """
    Get file path property name for a specific format.

    Args:
        fmt: Format string ('m4a', 'wav', 'aiff')

    Returns:
        Property name for file path
    """
    return FILE_PATH_PROPERTIES.get(fmt.lower())


def split_fingerprint_for_storage(fingerprint: str) -> List[str]:
    """
    Split a fingerprint into chunks for storage in Notion properties.

    Args:
        fingerprint: Full fingerprint string

    Returns:
        List of up to 3 chunks (each max 2000 chars)
    """
    if not fingerprint:
        return ["", "", ""]

    chunks = []
    remaining = fingerprint

    for i in range(3):
        if remaining:
            chunks.append(remaining[:MAX_FINGERPRINT_CHUNK_LENGTH])
            remaining = remaining[MAX_FINGERPRINT_CHUNK_LENGTH:]
        else:
            chunks.append("")

    return chunks


def extract_property_text(prop: Dict[str, Any]) -> str:
    """
    Extract text value from a Notion property.

    Args:
        prop: Notion property dictionary

    Returns:
        Text value as string
    """
    if not prop:
        return ""

    prop_type = prop.get("type")

    if prop_type == "rich_text":
        rich_text = prop.get("rich_text", [])
        return "".join(rt.get("plain_text", "") for rt in rich_text)

    if prop_type == "title":
        title = prop.get("title", [])
        return "".join(t.get("plain_text", "") for t in title)

    if prop_type == "url":
        return prop.get("url") or ""

    return ""


def extract_track_fingerprints(properties: Dict[str, Any]) -> TrackFingerprints:
    """
    Extract all fingerprint data from Notion track properties.

    Args:
        properties: Notion page properties dictionary

    Returns:
        TrackFingerprints object with all fingerprint data
    """
    result = TrackFingerprints()

    # Extract per-format fingerprints
    for fmt in ["m4a", "wav", "aiff"]:
        file_path_prop = FILE_PATH_PROPERTIES.get(fmt)
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])

        file_path = None
        if file_path_prop and file_path_prop in properties:
            file_path = extract_property_text(properties[file_path_prop])

        fingerprint_parts = []
        for fp_prop in fp_props:
            if fp_prop in properties:
                part = extract_property_text(properties[fp_prop])
                fingerprint_parts.append(part)
            else:
                fingerprint_parts.append("")

        # Pad to 3 parts
        while len(fingerprint_parts) < 3:
            fingerprint_parts.append("")

        fmt_fp = FormatFingerprint(
            format=fmt,
            file_path=file_path if file_path else None,
            fingerprint_parts=fingerprint_parts
        )
        setattr(result, fmt, fmt_fp)

    # Extract legacy fingerprint (for backward compatibility - DEPRECATED)
    for legacy_prop in LEGACY_FINGERPRINT_PROPERTIES:
        if legacy_prop in properties:
            legacy_value = extract_property_text(properties[legacy_prop])
            if legacy_value:
                result.legacy_fingerprint = legacy_value
                break

    return result


def build_fingerprint_update_properties(
    fingerprint: str,
    file_path: str,
    properties: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build Notion properties update payload for fingerprint.

    Routes fingerprint to correct per-format properties based on file path.

    Args:
        fingerprint: Full fingerprint string
        file_path: Path to the audio file (determines format)
        properties: Optional existing properties (to check available props)

    Returns:
        Dictionary of Notion property updates
    """
    fmt = get_format_from_extension(file_path)

    if not fmt:
        logger.warning(f"Cannot determine format for file: {file_path}")
        return {}

    fp_props = get_fingerprint_properties_for_format(fmt)

    if not fp_props:
        logger.warning(f"No fingerprint properties defined for format: {fmt}")
        return {}

    # Split fingerprint into chunks
    chunks = split_fingerprint_for_storage(fingerprint)

    # Build update payload
    update_props = {}
    for i, (prop_name, chunk) in enumerate(zip(fp_props, chunks)):
        # Only include properties that have content or need to be cleared
        if chunk or (properties and prop_name in properties):
            update_props[prop_name] = {
                "rich_text": [{"text": {"content": chunk}}] if chunk else []
            }

    logger.debug(f"Built fingerprint update for {fmt}: {list(update_props.keys())}")
    return update_props


def build_fingerprint_query_filter(
    available_properties: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Build Notion query filter for tracks missing fingerprints.

    Checks if ANY per-format fingerprint is empty for tracks that have
    the corresponding file path.

    Args:
        available_properties: List of available property names (optional)

    Returns:
        Notion filter dictionary
    """
    or_conditions = []

    for fmt in FORMAT_PRIORITY:
        file_path_prop = FILE_PATH_PROPERTIES.get(fmt)
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])

        if not file_path_prop or not fp_props:
            continue

        # Skip if properties not available
        if available_properties:
            if file_path_prop not in available_properties:
                continue
            if fp_props[0] not in available_properties:
                continue

        # Condition: File path exists AND primary fingerprint is empty
        # This catches tracks that have a file but need fingerprinting
        condition = {
            "and": [
                {"property": file_path_prop, "url": {"is_not_empty": True}},
                {"property": fp_props[0], "rich_text": {"is_empty": True}}
            ]
        }
        or_conditions.append(condition)

    # Also check for file paths stored as rich_text
    for fmt in FORMAT_PRIORITY:
        file_path_prop = FILE_PATH_PROPERTIES.get(fmt)
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])

        if not file_path_prop or not fp_props:
            continue

        if available_properties and file_path_prop not in available_properties:
            continue

        condition = {
            "and": [
                {"property": file_path_prop, "rich_text": {"is_not_empty": True}},
                {"property": fp_props[0], "rich_text": {"is_empty": True}}
            ]
        }
        or_conditions.append(condition)

    if not or_conditions:
        return {}

    return {"or": or_conditions}


def get_all_fingerprint_property_names() -> List[str]:
    """
    Get list of all fingerprint property names (new + legacy).

    Returns:
        List of all fingerprint property names
    """
    all_props = []

    # Add per-format properties
    for fp_props in FINGERPRINT_PROPERTIES.values():
        all_props.extend(fp_props)

    # Add legacy properties
    all_props.extend(LEGACY_FINGERPRINT_PROPERTIES)

    return list(set(all_props))


def has_per_format_fingerprint(properties: Dict[str, Any]) -> bool:
    """
    Check if track has any per-format fingerprint (not legacy).

    Args:
        properties: Notion page properties

    Returns:
        True if any per-format fingerprint exists
    """
    for fmt in FORMAT_PRIORITY:
        fp_props = FINGERPRINT_PROPERTIES.get(fmt, [])
        for fp_prop in fp_props:
            if fp_prop in properties:
                value = extract_property_text(properties[fp_prop])
                if value:
                    return True
    return False


def has_legacy_fingerprint_only(properties: Dict[str, Any]) -> bool:
    """
    Check if track only has legacy fingerprint (needs migration).

    Args:
        properties: Notion page properties

    Returns:
        True if only legacy fingerprint exists (no per-format)
    """
    has_legacy = False

    for legacy_prop in LEGACY_FINGERPRINT_PROPERTIES:
        if legacy_prop in properties:
            value = extract_property_text(properties[legacy_prop])
            if value:
                has_legacy = True
                break

    if not has_legacy:
        return False

    return not has_per_format_fingerprint(properties)


# =============================================================================
# MATCHING HELPERS
# =============================================================================

def get_fingerprint_for_file_path(
    file_path: str,
    track_fingerprints: TrackFingerprints
) -> Optional[str]:
    """
    Get the fingerprint that corresponds to a specific file path's format.

    Args:
        file_path: Path to audio file
        track_fingerprints: TrackFingerprints object

    Returns:
        Fingerprint string if found for the format, None otherwise
    """
    fmt = get_format_from_extension(file_path)

    if not fmt:
        return None

    return track_fingerprints.get_fingerprint_for_format(fmt)


def fingerprints_match(
    file_fingerprint: str,
    track_fingerprints: TrackFingerprints,
    file_path: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Check if a file fingerprint matches any track fingerprint.

    If file_path is provided, prioritizes matching against that format.
    Otherwise, checks all formats in priority order.

    Args:
        file_fingerprint: Computed fingerprint from file
        track_fingerprints: TrackFingerprints object from Notion
        file_path: Optional file path to determine format priority

    Returns:
        Tuple of (is_match, matched_format)
    """
    if not file_fingerprint:
        return (False, None)

    # If file path provided, check that format first
    if file_path:
        fmt = get_format_from_extension(file_path)
        if fmt:
            track_fp = track_fingerprints.get_fingerprint_for_format(fmt)
            if track_fp and track_fp == file_fingerprint:
                return (True, fmt)

    # Check all formats in priority order
    for fmt in FORMAT_PRIORITY:
        track_fp = track_fingerprints.get_fingerprint_for_format(fmt)
        if track_fp and track_fp == file_fingerprint:
            return (True, fmt)

    # Check legacy fingerprint
    if track_fingerprints.legacy_fingerprint:
        if track_fingerprints.legacy_fingerprint == file_fingerprint:
            logger.warning("Matched against DEPRECATED legacy fingerprint field")
            return (True, "legacy")

    return (False, None)
