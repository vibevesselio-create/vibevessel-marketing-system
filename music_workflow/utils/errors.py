"""
Custom error classes for music workflow.

These error classes provide a standardized way to handle errors throughout
the music workflow system, enabling proper error classification, logging,
and recovery strategies.
"""

from dataclasses import dataclass
from typing import Optional, Any


class MusicWorkflowError(Exception):
    """Base exception for music workflow errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class DownloadError(MusicWorkflowError):
    """Error during audio download.

    Raised when:
    - URL is invalid or inaccessible
    - Network errors occur
    - Content is DRM-protected
    - Format conversion fails
    """

    def __init__(self, message: str, url: Optional[str] = None,
                 source: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.url = url
        self.source = source  # e.g., "youtube", "soundcloud", "spotify"


class DRMProtectionError(DownloadError):
    """Error when content is DRM-protected.

    Raised when attempting to download DRM-protected content that cannot
    be accessed directly. May trigger YouTube search fallback.
    """

    def __init__(self, message: str, url: Optional[str] = None,
                 platform: Optional[str] = None):
        super().__init__(message, url, platform)
        self.platform = platform


class ProcessingError(MusicWorkflowError):
    """Error during audio processing.

    Raised when:
    - Audio analysis fails (BPM, key detection)
    - Format conversion fails
    - Audio normalization fails
    - File corruption detected
    """

    def __init__(self, message: str, file_path: Optional[str] = None,
                 operation: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.file_path = file_path
        self.operation = operation  # e.g., "bpm_analysis", "conversion", "normalize"


class IntegrationError(MusicWorkflowError):
    """Error with external service integration.

    Raised when:
    - API authentication fails
    - API rate limits exceeded
    - Service unavailable
    - Invalid response received
    """

    def __init__(self, message: str, service: Optional[str] = None,
                 status_code: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.service = service  # e.g., "notion", "eagle", "spotify"
        self.status_code = status_code


class NotionIntegrationError(IntegrationError):
    """Notion-specific integration error."""

    def __init__(self, message: str, database_id: Optional[str] = None,
                 page_id: Optional[str] = None, **kwargs):
        super().__init__(message, service="notion", **kwargs)
        self.database_id = database_id
        self.page_id = page_id


class EagleIntegrationError(IntegrationError):
    """Eagle-specific integration error."""

    def __init__(self, message: str, library_path: Optional[str] = None, **kwargs):
        super().__init__(message, service="eagle", **kwargs)
        self.library_path = library_path


class SpotifyIntegrationError(IntegrationError):
    """Spotify-specific integration error."""

    def __init__(self, message: str, track_id: Optional[str] = None, **kwargs):
        super().__init__(message, service="spotify", **kwargs)
        self.track_id = track_id


@dataclass
class DuplicateFoundError(MusicWorkflowError):
    """Track is a duplicate of an existing track.

    Contains reference to the existing track for resolution.
    """
    existing_track_id: Optional[str] = None
    existing_track_title: Optional[str] = None
    existing_track_source: Optional[str] = None  # notion, eagle, file
    similarity_score: float = 0.0

    def __init__(self, message: str, existing_track_id: Optional[str] = None,
                 existing_track_title: Optional[str] = None,
                 existing_track_source: Optional[str] = None,
                 similarity_score: float = 0.0):
        super().__init__(message)
        self.existing_track_id = existing_track_id
        self.existing_track_title = existing_track_title
        self.existing_track_source = existing_track_source
        self.similarity_score = similarity_score


class ConfigurationError(MusicWorkflowError):
    """Configuration or environment error.

    Raised when:
    - Required environment variable missing
    - Invalid configuration value
    - Configuration file not found or invalid
    """

    def __init__(self, message: str, config_key: Optional[str] = None,
                 config_file: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.config_key = config_key
        self.config_file = config_file


class FileOperationError(MusicWorkflowError):
    """Error during file system operations.

    Raised when:
    - File not found
    - Permission denied
    - Disk full
    - Path traversal detected
    """

    def __init__(self, message: str, file_path: Optional[str] = None,
                 operation: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.file_path = file_path
        self.operation = operation  # e.g., "read", "write", "move", "delete"


class ValidationError(MusicWorkflowError):
    """Input validation error.

    Raised when:
    - Invalid URL format
    - Invalid file format
    - Missing required fields
    - Invalid data type
    """

    def __init__(self, message: str, field: Optional[str] = None,
                 value: Optional[Any] = None, details: Optional[dict] = None):
        super().__init__(message, details)
        self.field = field
        self.value = value
