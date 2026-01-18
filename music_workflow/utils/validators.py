"""
Input validation utilities for music workflow.

This module provides validation functions for URLs, file paths,
metadata, and other inputs.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from music_workflow.utils.errors import ValidationError
from music_workflow.config.constants import (
    SUPPORTED_AUDIO_FORMATS,
    MIN_BPM,
    MAX_BPM,
    Platform,
)


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """Validate and classify a URL.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, platform)

    Raises:
        ValidationError: If URL is invalid
    """
    if not url or not isinstance(url, str):
        raise ValidationError(
            "URL cannot be empty",
            field="url",
            value=url,
        )

    # Clean URL
    url = url.strip()

    # Parse URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError(
                "Invalid URL format",
                field="url",
                value=url,
                details={"hint": "URL must include scheme (http/https)"},
            )
    except Exception as e:
        raise ValidationError(
            f"Failed to parse URL: {e}",
            field="url",
            value=url,
        )

    # Classify platform
    domain = parsed.netloc.lower()
    platform = Platform.UNKNOWN

    if "youtube.com" in domain or "youtu.be" in domain:
        platform = Platform.YOUTUBE
    elif "soundcloud.com" in domain:
        platform = Platform.SOUNDCLOUD
    elif "spotify.com" in domain or "open.spotify.com" in domain:
        platform = Platform.SPOTIFY
    elif "bandcamp.com" in domain:
        platform = Platform.BANDCAMP

    return True, platform


def validate_audio_file(path: Path) -> bool:
    """Validate an audio file path.

    Args:
        path: File path to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If file is invalid
    """
    if not path.exists():
        raise ValidationError(
            "File does not exist",
            field="file_path",
            value=str(path),
        )

    if not path.is_file():
        raise ValidationError(
            "Path is not a file",
            field="file_path",
            value=str(path),
        )

    extension = path.suffix.lower().lstrip(".")
    if extension not in SUPPORTED_AUDIO_FORMATS:
        raise ValidationError(
            f"Unsupported audio format: {extension}",
            field="file_path",
            value=str(path),
            details={"supported_formats": list(SUPPORTED_AUDIO_FORMATS)},
        )

    # Check file size (must be > 0)
    if path.stat().st_size == 0:
        raise ValidationError(
            "File is empty",
            field="file_path",
            value=str(path),
        )

    return True


def validate_bpm(bpm: float) -> float:
    """Validate and normalize BPM value.

    Args:
        bpm: BPM value to validate

    Returns:
        Validated BPM value

    Raises:
        ValidationError: If BPM is invalid
    """
    if bpm is None:
        raise ValidationError(
            "BPM cannot be None",
            field="bpm",
            value=bpm,
        )

    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        raise ValidationError(
            "BPM must be a number",
            field="bpm",
            value=bpm,
        )

    if bpm < MIN_BPM or bpm > MAX_BPM:
        raise ValidationError(
            f"BPM must be between {MIN_BPM} and {MAX_BPM}",
            field="bpm",
            value=bpm,
            details={"min": MIN_BPM, "max": MAX_BPM},
        )

    return bpm


def validate_key(key: str) -> str:
    """Validate musical key notation.

    Args:
        key: Key to validate (e.g., "Am", "C", "F#m")

    Returns:
        Validated key

    Raises:
        ValidationError: If key is invalid
    """
    if not key or not isinstance(key, str):
        raise ValidationError(
            "Key cannot be empty",
            field="key",
            value=key,
        )

    # Valid key pattern: letter + optional # or b + optional m
    key_pattern = re.compile(r"^[A-Ga-g][#b]?m?$")
    key = key.strip()

    if not key_pattern.match(key):
        raise ValidationError(
            "Invalid key notation",
            field="key",
            value=key,
            details={"hint": "Expected format: C, Am, F#, Bbm, etc."},
        )

    # Normalize to uppercase root with lowercase modifier
    root = key[0].upper()
    modifier = key[1:].replace("M", "m")

    return root + modifier


def validate_track_metadata(
    title: Optional[str],
    artist: Optional[str],
    require_both: bool = True,
) -> Tuple[str, str]:
    """Validate track metadata.

    Args:
        title: Track title
        artist: Track artist
        require_both: Whether both fields are required

    Returns:
        Tuple of (validated_title, validated_artist)

    Raises:
        ValidationError: If metadata is invalid
    """
    errors = []

    if not title or not title.strip():
        if require_both:
            errors.append("Title is required")
        title = ""
    else:
        title = title.strip()

    if not artist or not artist.strip():
        if require_both:
            errors.append("Artist is required")
        artist = ""
    else:
        artist = artist.strip()

    if errors:
        raise ValidationError(
            "Invalid track metadata",
            field="metadata",
            details={"errors": errors},
        )

    return title, artist


def validate_notion_page_id(page_id: str) -> str:
    """Validate Notion page ID format.

    Args:
        page_id: Page ID to validate

    Returns:
        Validated page ID

    Raises:
        ValidationError: If page ID is invalid
    """
    if not page_id or not isinstance(page_id, str):
        raise ValidationError(
            "Page ID cannot be empty",
            field="page_id",
            value=page_id,
        )

    # Remove hyphens for validation
    clean_id = page_id.replace("-", "")

    # Notion page IDs are 32 hex characters
    if len(clean_id) != 32:
        raise ValidationError(
            "Invalid Notion page ID length",
            field="page_id",
            value=page_id,
            details={"expected_length": 32, "actual_length": len(clean_id)},
        )

    # Must be valid hex
    try:
        int(clean_id, 16)
    except ValueError:
        raise ValidationError(
            "Invalid Notion page ID format",
            field="page_id",
            value=page_id,
            details={"hint": "Must be 32 hexadecimal characters"},
        )

    return page_id


def validate_spotify_id(spotify_id: str) -> str:
    """Validate Spotify track ID format.

    Args:
        spotify_id: Spotify ID to validate

    Returns:
        Validated Spotify ID

    Raises:
        ValidationError: If Spotify ID is invalid
    """
    if not spotify_id or not isinstance(spotify_id, str):
        raise ValidationError(
            "Spotify ID cannot be empty",
            field="spotify_id",
            value=spotify_id,
        )

    # Spotify IDs are 22 base62 characters
    spotify_id = spotify_id.strip()
    if len(spotify_id) != 22:
        raise ValidationError(
            "Invalid Spotify ID length",
            field="spotify_id",
            value=spotify_id,
            details={"expected_length": 22, "actual_length": len(spotify_id)},
        )

    # Must be alphanumeric
    if not spotify_id.isalnum():
        raise ValidationError(
            "Invalid Spotify ID format",
            field="spotify_id",
            value=spotify_id,
            details={"hint": "Must be 22 alphanumeric characters"},
        )

    return spotify_id


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize a string for use as a filename.

    Args:
        filename: String to sanitize
        max_length: Maximum filename length

    Returns:
        Sanitized filename
    """
    if not filename:
        return "untitled"

    # Remove or replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Replace multiple spaces/underscores
    filename = re.sub(r"[_\s]+", " ", filename)

    # Trim whitespace
    filename = filename.strip()

    # Truncate if too long
    if len(filename) > max_length:
        filename = filename[:max_length].rsplit(" ", 1)[0]

    return filename or "untitled"
