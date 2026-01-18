"""
Core data models for image workflow.

Aligned with music_workflow/core/models.py patterns for consistency.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ImageStatus(Enum):
    """Status of an image in the workflow pipeline."""
    PENDING = "pending"
    PROCESSING = "processing"
    SYNCED = "synced"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    ORPHANED = "orphaned"


class SourceType(Enum):
    """Source environment types."""
    LIGHTROOM = "lightroom"
    EAGLE = "eagle"
    GOOGLE_DRIVE = "google_drive"
    LOCAL = "local"
    NOTION = "notion"


@dataclass
class SourceLocation:
    """Represents an image's location in a specific environment."""
    source_type: SourceType
    source_id: str
    path: Optional[str] = None
    url: Optional[str] = None
    is_master: bool = False
    last_modified: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "path": self.path,
            "url": self.url,
            "is_master": self.is_master,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "metadata": self.metadata,
        }


@dataclass
class ImageMetadata:
    """
    Comprehensive image metadata from all sources.

    Mirrors the structure used in eagle_to_notion_sync.py and
    lightroom_to_google_drive_sql_sync.py for consistency.
    """
    # File information
    file_name: str
    file_extension: str
    file_size: Optional[int] = None
    file_path: Optional[str] = None

    # Dates
    date_created: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    date_digitized: Optional[datetime] = None  # EXIF DateTimeOriginal

    # Camera information (EXIF)
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None

    # Camera settings (EXIF)
    aperture: Optional[float] = None
    shutter_speed: Optional[str] = None
    iso: Optional[int] = None
    focal_length: Optional[float] = None

    # Location (GPS)
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    city: Optional[str] = None
    country: Optional[str] = None

    # Image properties
    width: Optional[int] = None
    height: Optional[int] = None
    color_space: Optional[str] = None
    bit_depth: Optional[int] = None

    # Lightroom-specific
    rating: Optional[int] = None  # 0-5 stars
    color_label: Optional[str] = None  # red, yellow, green, blue, purple
    pick_status: Optional[int] = None  # -1 rejected, 0 none, 1 picked
    collections: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Eagle-specific
    eagle_tags: List[str] = field(default_factory=list)
    eagle_folders: List[str] = field(default_factory=list)
    eagle_annotation: Optional[str] = None

    # Workflow
    creator: Optional[str] = None
    copyright: Optional[str] = None
    caption: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_name": self.file_name,
            "file_extension": self.file_extension,
            "file_size": self.file_size,
            "file_path": self.file_path,
            "date_created": self.date_created.isoformat() if self.date_created else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "date_digitized": self.date_digitized.isoformat() if self.date_digitized else None,
            "camera_make": self.camera_make,
            "camera_model": self.camera_model,
            "lens_model": self.lens_model,
            "aperture": self.aperture,
            "shutter_speed": self.shutter_speed,
            "iso": self.iso,
            "focal_length": self.focal_length,
            "gps_latitude": self.gps_latitude,
            "gps_longitude": self.gps_longitude,
            "city": self.city,
            "country": self.country,
            "width": self.width,
            "height": self.height,
            "color_space": self.color_space,
            "bit_depth": self.bit_depth,
            "rating": self.rating,
            "color_label": self.color_label,
            "pick_status": self.pick_status,
            "collections": self.collections,
            "keywords": self.keywords,
            "eagle_tags": self.eagle_tags,
            "eagle_folders": self.eagle_folders,
            "eagle_annotation": self.eagle_annotation,
            "creator": self.creator,
            "copyright": self.copyright,
            "caption": self.caption,
        }


@dataclass
class ImageInfo:
    """
    Core image representation with multi-source identity management.

    Mirrors TrackInfo from music_workflow for consistency.
    Each image can exist in multiple environments simultaneously.
    """
    # Universal Image Identifier (SHA256 fingerprint, first 16 chars)
    uii: str

    # Perceptual hash for similarity matching
    perceptual_hash: Optional[str] = None

    # Multi-source identity fields (like TrackInfo pattern)
    notion_page_id: Optional[str] = None
    lightroom_id: Optional[str] = None  # id_global from Lightroom
    eagle_id: Optional[str] = None
    google_drive_id: Optional[str] = None

    # Master location tracking
    master_location: Optional[SourceType] = None
    master_path: Optional[str] = None

    # All known locations
    locations: List[SourceLocation] = field(default_factory=list)

    # Aggregated metadata from all sources
    metadata: Optional[ImageMetadata] = None

    # Workflow status
    status: ImageStatus = ImageStatus.PENDING
    sync_timestamp: Optional[datetime] = None

    # Error tracking (like TrackInfo pattern)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Extra data for extensions
    extra: Dict[str, Any] = field(default_factory=dict)

    def add_location(self, location: SourceLocation) -> None:
        """Add a source location, avoiding duplicates."""
        existing = next(
            (loc for loc in self.locations
             if loc.source_type == location.source_type and loc.source_id == location.source_id),
            None
        )
        if existing:
            # Update existing location
            existing.path = location.path or existing.path
            existing.url = location.url or existing.url
            existing.is_master = location.is_master or existing.is_master
            existing.last_modified = location.last_modified or existing.last_modified
            existing.metadata.update(location.metadata)
        else:
            self.locations.append(location)

        # Update source-specific IDs
        if location.source_type == SourceType.LIGHTROOM:
            self.lightroom_id = location.source_id
        elif location.source_type == SourceType.EAGLE:
            self.eagle_id = location.source_id
        elif location.source_type == SourceType.GOOGLE_DRIVE:
            self.google_drive_id = location.source_id
        elif location.source_type == SourceType.NOTION:
            self.notion_page_id = location.source_id

    def get_location(self, source_type: SourceType) -> Optional[SourceLocation]:
        """Get location for a specific source type."""
        return next(
            (loc for loc in self.locations if loc.source_type == source_type),
            None
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "uii": self.uii,
            "perceptual_hash": self.perceptual_hash,
            "notion_page_id": self.notion_page_id,
            "lightroom_id": self.lightroom_id,
            "eagle_id": self.eagle_id,
            "google_drive_id": self.google_drive_id,
            "master_location": self.master_location.value if self.master_location else None,
            "master_path": self.master_path,
            "locations": [loc.to_dict() for loc in self.locations],
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "status": self.status.value,
            "sync_timestamp": self.sync_timestamp.isoformat() if self.sync_timestamp else None,
            "errors": self.errors,
            "warnings": self.warnings,
            "extra": self.extra,
        }


@dataclass
class ImageMatch:
    """
    Represents a match found during deduplication.

    Mirrors Match pattern from music_workflow/deduplication/matcher.py
    """
    matched_image: ImageInfo
    match_source: SourceType
    match_method: str  # "exact_hash", "perceptual_hash", "metadata", etc.
    similarity_score: float  # 0.0 to 1.0
    confidence: str  # "high", "medium", "low"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched_uii": self.matched_image.uii,
            "match_source": self.match_source.value,
            "match_method": self.match_method,
            "similarity_score": self.similarity_score,
            "confidence": self.confidence,
            "details": self.details,
        }


@dataclass
class WorkflowResult:
    """
    Result of a workflow operation.

    Mirrors WorkflowResult from music_workflow for consistency.
    """
    success: bool
    image: Optional[ImageInfo] = None
    matches: List[ImageMatch] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "image": self.image.to_dict() if self.image else None,
            "matches": [m.to_dict() for m in self.matches],
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }
