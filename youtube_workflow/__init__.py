"""YouTube Workflow Module.

Provides comprehensive YouTube integration for the VibeVessel automation ecosystem:
- YouTube Data API v3 integration
- yt-dlp wrapper for downloads and search
- Multi-strategy search with duration matching
- Notion synchronization
- Multi-Google account routing

Architecture aligned with music_workflow and image_workflow patterns.
"""

__version__ = "0.1.0"
__author__ = "VibeVessel Automation"

from youtube_workflow.core.models import (
    VideoInfo,
    PlaylistInfo,
    ChannelInfo,
    SearchResult,
    DownloadResult,
)

__all__ = [
    "VideoInfo",
    "PlaylistInfo",
    "ChannelInfo",
    "SearchResult",
    "DownloadResult",
]
