"""
Core data models for music workflow.

This module defines the central data structures used throughout the
music workflow system. TrackInfo is the primary data transfer object
passed between modules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


class TrackStatus(Enum):
    """Status of a track in the workflow."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    DEDUPLICATING = "deduplicating"
    IMPORTING = "importing"
    COMPLETE = "complete"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class AudioFormat(Enum):
    """Supported audio formats."""
    M4A = "m4a"
    WAV = "wav"
    AIFF = "aiff"
    MP3 = "mp3"
    FLAC = "flac"


@dataclass
class TrackInfo:
    """Represents a music track with all metadata.

    This is the central data structure passed between modules.
    All track-related information should be stored here.
    """
    # Identifiers
    id: str
    notion_page_id: Optional[str] = None
    spotify_id: Optional[str] = None
    soundcloud_url: Optional[str] = None
    eagle_id: Optional[str] = None

    # Basic metadata
    title: str = ""
    artist: str = ""
    album: Optional[str] = None
    duration: Optional[float] = None  # seconds
    release_date: Optional[str] = None

    # Audio analysis
    bpm: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[float] = None  # 0.0-1.0
    loudness: Optional[float] = None  # LUFS
    danceability: Optional[float] = None  # 0.0-1.0

    # File information
    source_url: Optional[str] = None
    source_platform: Optional[str] = None  # youtube, soundcloud, spotify
    file_paths: Dict[str, Path] = field(default_factory=dict)  # format -> path
    file_size: Optional[int] = None  # bytes

    # Organization
    playlist: Optional[str] = None
    playlist_position: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    folder_path: Optional[str] = None

    # Status tracking
    status: TrackStatus = TrackStatus.PENDING
    processed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Additional metadata (extensible)
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    def add_file(self, format: str, path: Path) -> None:
        """Add a file path for a specific format."""
        self.file_paths[format] = path

    def get_file(self, format: str) -> Optional[Path]:
        """Get file path for a specific format."""
        return self.file_paths.get(format)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.status = TrackStatus.FAILED

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def has_audio_analysis(self) -> bool:
        """Check if audio analysis has been performed."""
        return self.bpm is not None or self.key is not None

    def has_files(self) -> bool:
        """Check if any files exist for this track."""
        return len(self.file_paths) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "notion_page_id": self.notion_page_id,
            "spotify_id": self.spotify_id,
            "soundcloud_url": self.soundcloud_url,
            "eagle_id": self.eagle_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "bpm": self.bpm,
            "key": self.key,
            "energy": self.energy,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "file_paths": {k: str(v) for k, v in self.file_paths.items()},
            "playlist": self.playlist,
            "tags": self.tags,
            "status": self.status.value,
            "processed": self.processed,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrackInfo":
        """Create from dictionary."""
        track = cls(
            id=data.get("id", ""),
            notion_page_id=data.get("notion_page_id"),
            spotify_id=data.get("spotify_id"),
            soundcloud_url=data.get("soundcloud_url"),
            eagle_id=data.get("eagle_id"),
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album"),
            duration=data.get("duration"),
            bpm=data.get("bpm"),
            key=data.get("key"),
            energy=data.get("energy"),
            source_url=data.get("source_url"),
            source_platform=data.get("source_platform"),
            playlist=data.get("playlist"),
            tags=data.get("tags", []),
            processed=data.get("processed", False),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

        # Handle file paths
        if "file_paths" in data:
            track.file_paths = {k: Path(v) for k, v in data["file_paths"].items()}

        # Handle status
        if "status" in data:
            try:
                track.status = TrackStatus(data["status"])
            except ValueError:
                track.status = TrackStatus.PENDING

        return track


@dataclass
class AudioAnalysis:
    """Result of audio analysis."""
    bpm: float
    key: str
    duration: float  # seconds
    sample_rate: int
    channels: int
    loudness: Optional[float] = None  # LUFS
    energy: Optional[float] = None
    confidence: Optional[float] = None  # Analysis confidence 0-1


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    files: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    source_url: Optional[str] = None
    duration_seconds: Optional[float] = None


@dataclass
class OrganizeResult:
    """Result of a file organization operation."""
    success: bool
    source_path: Path
    destination_path: Path
    backup_paths: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class DeduplicationResult:
    """Result of a deduplication check."""
    is_duplicate: bool
    matching_track_id: Optional[str] = None
    matching_source: Optional[str] = None  # notion, eagle, file
    similarity_score: float = 0.0
    fingerprint_match: bool = False
    metadata_match: bool = False
