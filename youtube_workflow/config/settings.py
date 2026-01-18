"""Settings and configuration for YouTube workflow.

Environment-based configuration aligned with unified_config patterns.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


@dataclass
class YouTubeSettings:
    """YouTube workflow configuration settings."""

    # API Configuration
    youtube_api_key: Optional[str] = None
    enable_youtube_api: bool = True
    api_quota_daily: int = 10000

    # yt-dlp Configuration
    enable_ytdlp: bool = True
    ytdlp_quiet: bool = True

    # Download Settings
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "downloads")
    audio_format: str = "wav"
    video_format: str = "mp4"

    # Search Settings
    enable_youtube_search: bool = True
    enable_youtube_fallback: bool = True
    max_search_results: int = 5
    duration_tolerance_seconds: int = 10

    # Google Account Routing
    youtube_api_account: str = "brian@serenmedia.co"
    google_oauth_token_dir: Optional[Path] = None

    # Notion Integration
    notion_music_db_id: Optional[str] = None

    # Search Strategies (ordered by preference)
    search_strategies: List[str] = field(default_factory=lambda: [
        "official_audio",
        "exact",
        "audio_only",
        "title_only",
        "cleaned",
        "first_artist",
    ])

    def __post_init__(self):
        """Ensure paths are Path objects."""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.google_oauth_token_dir, str):
            self.google_oauth_token_dir = Path(self.google_oauth_token_dir)


@lru_cache(maxsize=1)
def get_settings() -> YouTubeSettings:
    """Get YouTube settings from environment variables.

    Uses unified_config patterns for environment loading.
    """
    return YouTubeSettings(
        # API
        youtube_api_key=os.getenv("YOUTUBE_API_KEY"),
        enable_youtube_api=os.getenv("ENABLE_YOUTUBE_API", "true").lower() == "true",
        api_quota_daily=int(os.getenv("YOUTUBE_API_QUOTA_DAILY", "10000")),

        # yt-dlp
        enable_ytdlp=os.getenv("ENABLE_YTDLP", "true").lower() == "true",
        ytdlp_quiet=os.getenv("YTDLP_QUIET", "true").lower() == "true",

        # Downloads
        output_dir=Path(os.getenv("YOUTUBE_OUTPUT_DIR", str(Path.cwd() / "downloads"))),
        audio_format=os.getenv("YOUTUBE_AUDIO_FORMAT", "wav"),
        video_format=os.getenv("YOUTUBE_VIDEO_FORMAT", "mp4"),

        # Search
        enable_youtube_search=os.getenv("ENABLE_YOUTUBE_SEARCH", "true").lower() == "true",
        enable_youtube_fallback=os.getenv("ENABLE_YOUTUBE_FALLBACK", "true").lower() == "true",
        max_search_results=int(os.getenv("YOUTUBE_MAX_SEARCH_RESULTS", "5")),
        duration_tolerance_seconds=int(os.getenv("YOUTUBE_DURATION_TOLERANCE", "10")),

        # Google Account
        youtube_api_account=os.getenv("YOUTUBE_API_ACCOUNT", "brian@serenmedia.co"),
        google_oauth_token_dir=Path(os.getenv(
            "GOOGLE_OAUTH_TOKEN_DIR",
            str(Path.home() / ".credentials" / "google-oauth")
        )) if os.getenv("GOOGLE_OAUTH_TOKEN_DIR") else None,

        # Notion
        notion_music_db_id=os.getenv("NOTION_MUSIC_TRACKS_DB_ID"),
    )


def clear_settings_cache() -> None:
    """Clear the settings cache for testing."""
    get_settings.cache_clear()
