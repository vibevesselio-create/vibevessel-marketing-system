"""
Configuration settings for music workflow.

This module provides centralized configuration management using environment
variables and configuration files.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class DownloadConfig:
    """Download-related configuration."""
    # 2026-01-16: Updated default formats for new 3-file output structure
    # Primary outputs: WAV (Eagle), AIFF (Eagle), WAV copy (playlist-tracks)
    # M4A no longer in default output chain
    default_formats: List[str] = field(default_factory=lambda: ["wav", "aiff"])
    max_retries: int = 3
    timeout: int = 300  # seconds
    youtube_fallback: bool = True
    output_template: str = "%(title)s.%(ext)s"


@dataclass
class ProcessingConfig:
    """Audio processing configuration."""
    target_lufs: float = -14.0
    analyze_bpm: bool = True
    analyze_key: bool = True
    preserve_original: bool = True


@dataclass
class DeduplicationConfig:
    """Deduplication configuration."""
    enabled: bool = True
    fingerprint_threshold: float = 0.95
    check_notion: bool = True
    check_eagle: bool = True
    check_file_hash: bool = True


@dataclass
class NotionConfig:
    """Notion integration configuration."""
    timeout: int = 30
    max_retries: int = 3
    tracks_db_id: Optional[str] = None
    playlists_db_id: Optional[str] = None
    calendar_db_id: Optional[str] = None
    execution_logs_db_id: Optional[str] = None
    issues_db_id: Optional[str] = None

    def __post_init__(self):
        """Load from environment variables."""
        self.tracks_db_id = os.environ.get("TRACKS_DB_ID", self.tracks_db_id)
        self.playlists_db_id = os.environ.get("PLAYLISTS_DB_ID", self.playlists_db_id)
        self.calendar_db_id = os.environ.get("CALENDAR_DB_ID", self.calendar_db_id)
        self.execution_logs_db_id = os.environ.get("EXECUTION_LOGS_DB_ID", self.execution_logs_db_id)
        self.issues_db_id = os.environ.get("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")


@dataclass
class EagleConfig:
    """Eagle library configuration."""
    library_path: Optional[Path] = None
    auto_import: bool = True
    default_tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Load from environment variables."""
        library_path_env = os.environ.get("EAGLE_LIBRARY_PATH")
        if library_path_env:
            self.library_path = Path(library_path_env)


@dataclass
class SpotifyConfig:
    """Spotify integration configuration."""
    enrich_metadata: bool = True
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

    def __post_init__(self):
        """Load from environment variables."""
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID", self.client_id)
        self.client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", self.client_secret)


@dataclass
class FeatureFlags:
    """Feature flags for gradual rollout."""
    use_modular: bool = False
    youtube_fallback: bool = True
    dedup_enabled: bool = True

    def __post_init__(self):
        """Load from environment variables."""
        use_modular_env = os.environ.get("MUSIC_WORKFLOW_USE_MODULAR", "false")
        self.use_modular = use_modular_env.lower() in ("true", "1", "yes")

        youtube_fallback_env = os.environ.get("MUSIC_WORKFLOW_YOUTUBE_FALLBACK", "true")
        self.youtube_fallback = youtube_fallback_env.lower() in ("true", "1", "yes")

        dedup_enabled_env = os.environ.get("MUSIC_WORKFLOW_DEDUP_ENABLED", "true")
        self.dedup_enabled = dedup_enabled_env.lower() in ("true", "1", "yes")


@dataclass
class WorkflowSettings:
    """Main workflow settings container."""
    log_level: str = "INFO"

    download: DownloadConfig = field(default_factory=DownloadConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)
    eagle: EagleConfig = field(default_factory=EagleConfig)
    spotify: SpotifyConfig = field(default_factory=SpotifyConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)

    # Directories
    output_dir: Path = field(default_factory=lambda: Path.home() / "Music" / "Downloads")
    temp_dir: Path = field(default_factory=lambda: Path("/tmp/music_workflow"))
    # 2026-01-16: New playlist tracks directory for 3-file output structure
    playlist_tracks_dir: Path = field(default_factory=lambda: Path("/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks"))

    def __post_init__(self):
        """Load from environment variables."""
        self.log_level = os.environ.get("MUSIC_WORKFLOW_LOG_LEVEL", "INFO")

        # Load directory overrides from env
        output_dir_env = os.environ.get("MUSIC_WORKFLOW_OUTPUT_DIR")
        if output_dir_env:
            self.output_dir = Path(output_dir_env)

        temp_dir_env = os.environ.get("MUSIC_WORKFLOW_TEMP_DIR")
        if temp_dir_env:
            self.temp_dir = Path(temp_dir_env)

        # 2026-01-16: Load playlist tracks directory from env
        playlist_tracks_dir_env = os.environ.get("PLAYLIST_TRACKS_DIR")
        if playlist_tracks_dir_env:
            self.playlist_tracks_dir = Path(playlist_tracks_dir_env)

    def should_use_modular(self) -> bool:
        """Check if modular workflow should be used."""
        return self.features.use_modular


# Global settings instance
_settings: Optional[WorkflowSettings] = None


def get_settings() -> WorkflowSettings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = WorkflowSettings()
    return _settings


def reset_settings() -> None:
    """Reset settings (useful for testing)."""
    global _settings
    _settings = None


# Alias for backwards compatibility with CLI
Settings = WorkflowSettings
