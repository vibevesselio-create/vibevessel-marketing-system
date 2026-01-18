"""
Shared constants for music workflow.

This module defines constants used throughout the music workflow system.
"""

from pathlib import Path

# Version
VERSION = "0.1.0"

# Supported audio formats
SUPPORTED_AUDIO_FORMATS = frozenset(["m4a", "mp3", "wav", "aiff", "flac", "ogg"])
LOSSLESS_FORMATS = frozenset(["wav", "aiff", "flac"])
LOSSY_FORMATS = frozenset(["m4a", "mp3", "ogg"])

# Default output formats for downloads
DEFAULT_OUTPUT_FORMATS = ["m4a", "aiff", "wav"]

# Audio analysis constants
DEFAULT_TARGET_LUFS = -14.0
MIN_BPM = 20.0
MAX_BPM = 300.0

# Key notation mapping (Camelot system)
KEY_NOTATION = {
    # Minor keys
    "Am": "1A", "Em": "2A", "Bm": "3A", "F#m": "4A",
    "Dbm": "5A", "Abm": "6A", "Ebm": "7A", "Bbm": "8A",
    "Fm": "9A", "Cm": "10A", "Gm": "11A", "Dm": "12A",
    # Major keys
    "C": "1B", "G": "2B", "D": "3B", "A": "4B",
    "E": "5B", "B": "6B", "Gb": "7B", "Db": "8B",
    "Ab": "9B", "Eb": "10B", "Bb": "11B", "F": "12B",
}

# Spotify key mapping (numeric to musical)
SPOTIFY_KEY_MAP = {
    0: "C", 1: "Db", 2: "D", 3: "Eb", 4: "E", 5: "F",
    6: "Gb", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B",
}

# Mode mapping (0 = minor, 1 = major)
SPOTIFY_MODE_MAP = {0: "m", 1: ""}

# Platform identifiers
class Platform:
    """Platform identifier constants."""
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"
    SPOTIFY = "spotify"
    BANDCAMP = "bandcamp"
    UNKNOWN = "unknown"

# Status values for tracking
class ProcessStatus:
    """Processing status constants."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    IMPORTING = "importing"
    COMPLETE = "complete"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"

# Notion property names (standard across databases)
class NotionProperties:
    """Standard Notion property names."""
    TITLE = "Name"
    STATUS = "Status"
    TRACK_TITLE = "Track Title"
    ARTIST = "Artist"
    ALBUM = "Album"
    BPM = "BPM"
    KEY = "Key"
    DURATION = "Duration"
    SPOTIFY_ID = "Spotify ID"
    SOUNDCLOUD_URL = "SoundCloud URL"
    EAGLE_ID = "Eagle ID"
    FILE_PATHS = "File Paths"
    PLAYLIST = "Playlist"
    TAGS = "Tags"
    PROCESSED = "Processed"
    CREATED_AT = "Created At"
    UPDATED_AT = "Updated At"

# File organization paths
class DefaultPaths:
    """Default file paths."""
    MUSIC_ROOT = Path("/Volumes/VIBES/Music")
    EAGLE_LIBRARY = Path("/Volumes/VIBES/Music-Library-2.library")
    BACKUP_ROOT = Path("/Volumes/VIBES/Music-Backups")
    TEMP_DOWNLOAD = Path("/tmp/music_downloads")

# API timeouts (seconds)
class Timeouts:
    """API timeout constants."""
    NOTION_DEFAULT = 30
    EAGLE_DEFAULT = 15
    SPOTIFY_DEFAULT = 10
    DOWNLOAD_DEFAULT = 300

# Retry configuration
class RetryConfig:
    """Retry configuration constants."""
    MAX_RETRIES = 3
    INITIAL_DELAY = 1.0  # seconds
    MAX_DELAY = 30.0  # seconds
    EXPONENTIAL_BASE = 2.0

# Deduplication thresholds
class DedupThresholds:
    """Deduplication threshold constants."""
    FINGERPRINT_MATCH = 0.95
    METADATA_MATCH = 0.85
    FUZZY_TITLE_MATCH = 0.90
