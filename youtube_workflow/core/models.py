"""Core data models for YouTube workflow.

Aligned with music_workflow and image_workflow patterns for consistent
cross-module architecture.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class VideoStatus(Enum):
    """Processing status for YouTube videos."""

    PENDING = "pending"
    SEARCHING = "searching"
    FOUND = "found"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSED = "processed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class SearchStrategy(Enum):
    """Search strategies for finding YouTube videos."""

    EXACT = "exact"                    # artist + title exact
    OFFICIAL_AUDIO = "official_audio"  # + "official audio"
    AUDIO_ONLY = "audio_only"          # + "audio"
    TITLE_ONLY = "title_only"          # title without artist
    CLEANED = "cleaned"                # remove featuring, remix info
    FIRST_ARTIST = "first_artist"      # first artist only


@dataclass
class VideoInfo:
    """Core YouTube video representation.

    Stores video metadata from YouTube Data API or yt-dlp extraction.
    """

    # YouTube identifiers
    video_id: str
    url: str

    # Basic metadata
    title: str
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None

    # Duration (critical for matching)
    duration_seconds: Optional[int] = None
    duration_str: Optional[str] = None

    # Quality metadata
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: Optional[datetime] = None

    # Thumbnails
    thumbnail_url: Optional[str] = None

    # Description and tags
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Processing state
    status: VideoStatus = VideoStatus.PENDING
    download_path: Optional[str] = None

    # Notion integration
    notion_page_id: Optional[str] = None

    # Matching metadata (for search results)
    match_score: float = 0.0
    match_strategy: Optional[SearchStrategy] = None
    duration_diff_seconds: Optional[int] = None

    # Timestamps
    discovered_at: Optional[datetime] = None
    downloaded_at: Optional[datetime] = None

    @property
    def duration(self) -> Optional[timedelta]:
        """Get duration as timedelta."""
        if self.duration_seconds:
            return timedelta(seconds=self.duration_seconds)
        return None

    @property
    def is_available(self) -> bool:
        """Check if video is available for download."""
        return self.status not in (VideoStatus.UNAVAILABLE, VideoStatus.FAILED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "video_id": self.video_id,
            "url": self.url,
            "title": self.title,
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "duration_seconds": self.duration_seconds,
            "duration_str": self.duration_str,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "upload_date": self.upload_date.isoformat() if self.upload_date else None,
            "thumbnail_url": self.thumbnail_url,
            "description": self.description,
            "tags": self.tags,
            "status": self.status.value,
            "download_path": self.download_path,
            "notion_page_id": self.notion_page_id,
            "match_score": self.match_score,
            "match_strategy": self.match_strategy.value if self.match_strategy else None,
            "duration_diff_seconds": self.duration_diff_seconds,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
            "downloaded_at": self.downloaded_at.isoformat() if self.downloaded_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoInfo":
        """Create from dictionary."""
        if data.get("upload_date"):
            data["upload_date"] = datetime.fromisoformat(data["upload_date"])
        if data.get("discovered_at"):
            data["discovered_at"] = datetime.fromisoformat(data["discovered_at"])
        if data.get("downloaded_at"):
            data["downloaded_at"] = datetime.fromisoformat(data["downloaded_at"])
        if data.get("status"):
            data["status"] = VideoStatus(data["status"])
        if data.get("match_strategy"):
            data["match_strategy"] = SearchStrategy(data["match_strategy"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_yt_dlp(cls, info: Dict[str, Any]) -> "VideoInfo":
        """Create from yt-dlp info dict."""
        upload_date = None
        if info.get("upload_date"):
            try:
                upload_date = datetime.strptime(info["upload_date"], "%Y%m%d")
            except ValueError:
                pass

        return cls(
            video_id=info.get("id", ""),
            url=info.get("webpage_url", info.get("url", "")),
            title=info.get("title", ""),
            channel_name=info.get("channel", info.get("uploader", "")),
            channel_id=info.get("channel_id", ""),
            duration_seconds=info.get("duration"),
            duration_str=info.get("duration_string"),
            view_count=info.get("view_count"),
            like_count=info.get("like_count"),
            upload_date=upload_date,
            thumbnail_url=info.get("thumbnail"),
            description=info.get("description"),
            tags=info.get("tags", []),
            discovered_at=datetime.now(),
        )


@dataclass
class PlaylistInfo:
    """YouTube playlist representation."""

    playlist_id: str
    url: str
    title: str

    channel_name: Optional[str] = None
    channel_id: Optional[str] = None

    video_count: int = 0
    videos: List[VideoInfo] = field(default_factory=list)

    description: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Notion integration
    notion_page_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "playlist_id": self.playlist_id,
            "url": self.url,
            "title": self.title,
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "video_count": self.video_count,
            "videos": [v.to_dict() for v in self.videos],
            "description": self.description,
            "thumbnail_url": self.thumbnail_url,
            "notion_page_id": self.notion_page_id,
        }


@dataclass
class ChannelInfo:
    """YouTube channel representation."""

    channel_id: str
    url: str
    name: str

    subscriber_count: Optional[int] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None

    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    banner_url: Optional[str] = None

    # Notion integration
    notion_page_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_id": self.channel_id,
            "url": self.url,
            "name": self.name,
            "subscriber_count": self.subscriber_count,
            "video_count": self.video_count,
            "view_count": self.view_count,
            "description": self.description,
            "thumbnail_url": self.thumbnail_url,
            "banner_url": self.banner_url,
            "notion_page_id": self.notion_page_id,
        }


@dataclass
class SearchResult:
    """Result from YouTube search operation."""

    query: str
    strategy: SearchStrategy
    results: List[VideoInfo] = field(default_factory=list)

    # Search metadata
    target_duration_seconds: Optional[int] = None
    best_match: Optional[VideoInfo] = None

    # Performance
    search_time_ms: Optional[int] = None
    api_used: str = "yt_dlp"  # "yt_dlp" or "youtube_api"

    def find_best_match(self, tolerance_seconds: int = 10) -> Optional[VideoInfo]:
        """Find best matching video by duration."""
        if not self.target_duration_seconds or not self.results:
            return self.results[0] if self.results else None

        best = None
        best_diff = float("inf")

        for video in self.results:
            if video.duration_seconds:
                diff = abs(video.duration_seconds - self.target_duration_seconds)
                if diff <= tolerance_seconds and diff < best_diff:
                    best = video
                    best_diff = diff
                    video.duration_diff_seconds = diff

        self.best_match = best
        return best


@dataclass
class DownloadResult:
    """Result from YouTube download operation."""

    video: VideoInfo
    success: bool

    # Output paths
    audio_path: Optional[str] = None
    video_path: Optional[str] = None

    # Quality info
    audio_format: Optional[str] = None
    video_format: Optional[str] = None
    file_size_bytes: Optional[int] = None

    # Error info
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    # Timing
    download_time_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "video": self.video.to_dict(),
            "success": self.success,
            "audio_path": self.audio_path,
            "video_path": self.video_path,
            "audio_format": self.audio_format,
            "video_format": self.video_format,
            "file_size_bytes": self.file_size_bytes,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "download_time_seconds": self.download_time_seconds,
        }
