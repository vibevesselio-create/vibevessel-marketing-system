"""Shared utilities - logging, errors, validators, file operations."""

from music_workflow.utils.errors import (
    MusicWorkflowError,
    DownloadError,
    DRMProtectionError,
    ProcessingError,
    IntegrationError,
    NotionIntegrationError,
    EagleIntegrationError,
    SpotifyIntegrationError,
    DuplicateFoundError,
    ConfigurationError,
    FileOperationError,
    ValidationError,
)
from music_workflow.utils.logging import (
    MusicWorkflowLogger,
    get_logger,
    log_execution,
)
from music_workflow.utils.file_ops import (
    ensure_directory,
    safe_copy,
    safe_move,
    safe_delete,
    calculate_file_hash,
    get_file_size,
    find_files,
    create_backup,
)
from music_workflow.utils.validators import (
    validate_url,
    validate_audio_file,
    validate_bpm,
    validate_key,
    validate_track_metadata,
    validate_notion_page_id,
    validate_spotify_id,
    sanitize_filename,
)

__all__ = [
    # Errors
    "MusicWorkflowError",
    "DownloadError",
    "DRMProtectionError",
    "ProcessingError",
    "IntegrationError",
    "NotionIntegrationError",
    "EagleIntegrationError",
    "SpotifyIntegrationError",
    "DuplicateFoundError",
    "ConfigurationError",
    "FileOperationError",
    "ValidationError",
    # Logging
    "MusicWorkflowLogger",
    "get_logger",
    "log_execution",
    # File operations
    "ensure_directory",
    "safe_copy",
    "safe_move",
    "safe_delete",
    "calculate_file_hash",
    "get_file_size",
    "find_files",
    "create_backup",
    # Validators
    "validate_url",
    "validate_audio_file",
    "validate_bpm",
    "validate_key",
    "validate_track_metadata",
    "validate_notion_page_id",
    "validate_spotify_id",
    "sanitize_filename",
]
