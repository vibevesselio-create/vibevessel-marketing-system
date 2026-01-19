"""
Unit tests for the errors module.
"""

import pytest

import sys
sys.path.insert(0, '.')

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


class TestMusicWorkflowError:
    """Test base MusicWorkflowError."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = MusicWorkflowError("Test error")
        assert error.message == "Test error"
        assert error.details == {}
        assert str(error) == "Test error"

    def test_error_with_details(self):
        """Test error with details dict."""
        error = MusicWorkflowError("Test error", details={"key": "value"})
        assert error.details == {"key": "value"}
        # Implementation uses dict literal format in __str__
        assert "'key': 'value'" in str(error)

    def test_error_is_exception(self):
        """Test error is a proper exception."""
        error = MusicWorkflowError("Test")
        assert isinstance(error, Exception)

    def test_error_can_be_raised(self):
        """Test error can be raised and caught."""
        with pytest.raises(MusicWorkflowError) as exc_info:
            raise MusicWorkflowError("Raised error")
        assert "Raised error" in str(exc_info.value)


class TestDownloadError:
    """Test DownloadError class."""

    def test_basic_download_error(self):
        """Test basic download error."""
        error = DownloadError("Download failed")
        assert error.message == "Download failed"
        assert error.url is None
        assert error.source is None

    def test_download_error_with_url(self):
        """Test download error with URL."""
        error = DownloadError(
            "Download failed",
            url="https://example.com/track",
            source="soundcloud"
        )
        assert error.url == "https://example.com/track"
        assert error.source == "soundcloud"

    def test_download_error_inheritance(self):
        """Test download error inherits from base."""
        error = DownloadError("Test")
        assert isinstance(error, MusicWorkflowError)


class TestDRMProtectionError:
    """Test DRMProtectionError class."""

    def test_drm_error(self):
        """Test DRM protection error."""
        error = DRMProtectionError(
            "Content is DRM protected",
            url="https://soundcloud.com/track",
            platform="soundcloud"
        )
        assert error.platform == "soundcloud"
        assert error.url == "https://soundcloud.com/track"

    def test_drm_error_inheritance(self):
        """Test DRM error inherits from DownloadError."""
        error = DRMProtectionError("Test")
        assert isinstance(error, DownloadError)
        assert isinstance(error, MusicWorkflowError)


class TestProcessingError:
    """Test ProcessingError class."""

    def test_basic_processing_error(self):
        """Test basic processing error."""
        error = ProcessingError("Processing failed")
        assert error.message == "Processing failed"
        assert error.file_path is None
        assert error.operation is None

    def test_processing_error_with_context(self):
        """Test processing error with context."""
        error = ProcessingError(
            "BPM detection failed",
            file_path="/path/to/file.m4a",
            operation="bpm_analysis",
            details={"bpm_range": "60-200"}
        )
        assert error.file_path == "/path/to/file.m4a"
        assert error.operation == "bpm_analysis"
        assert error.details == {"bpm_range": "60-200"}

    def test_processing_error_inheritance(self):
        """Test processing error inherits from base."""
        error = ProcessingError("Test")
        assert isinstance(error, MusicWorkflowError)


class TestIntegrationError:
    """Test IntegrationError class."""

    def test_basic_integration_error(self):
        """Test basic integration error."""
        error = IntegrationError("API failed")
        assert error.service is None
        assert error.status_code is None

    def test_integration_error_with_service(self):
        """Test integration error with service info."""
        error = IntegrationError(
            "Rate limit exceeded",
            service="notion",
            status_code=429
        )
        assert error.service == "notion"
        assert error.status_code == 429


class TestNotionIntegrationError:
    """Test NotionIntegrationError class."""

    def test_notion_error(self):
        """Test Notion-specific error."""
        error = NotionIntegrationError(
            "Page not found",
            database_id="db-123",
            page_id="page-456"
        )
        assert error.service == "notion"
        assert error.database_id == "db-123"
        assert error.page_id == "page-456"

    def test_notion_error_inheritance(self):
        """Test Notion error inherits correctly."""
        error = NotionIntegrationError("Test")
        assert isinstance(error, IntegrationError)
        assert isinstance(error, MusicWorkflowError)


class TestEagleIntegrationError:
    """Test EagleIntegrationError class."""

    def test_eagle_error(self):
        """Test Eagle-specific error."""
        error = EagleIntegrationError(
            "Library not found",
            library_path="/path/to/library"
        )
        assert error.service == "eagle"
        assert error.library_path == "/path/to/library"


class TestSpotifyIntegrationError:
    """Test SpotifyIntegrationError class."""

    def test_spotify_error(self):
        """Test Spotify-specific error."""
        error = SpotifyIntegrationError(
            "Track not found",
            track_id="spotify:track:123"
        )
        assert error.service == "spotify"
        assert error.track_id == "spotify:track:123"


class TestDuplicateFoundError:
    """Test DuplicateFoundError class."""

    def test_duplicate_error(self):
        """Test duplicate found error."""
        error = DuplicateFoundError(
            "Track is duplicate",
            existing_track_id="track-123",
            existing_track_title="Original Track",
            existing_track_source="notion",
            similarity_score=0.95
        )
        assert error.existing_track_id == "track-123"
        assert error.existing_track_title == "Original Track"
        assert error.existing_track_source == "notion"
        assert error.similarity_score == 0.95


class TestConfigurationError:
    """Test ConfigurationError class."""

    def test_config_error(self):
        """Test configuration error."""
        error = ConfigurationError(
            "Missing API key",
            config_key="NOTION_API_KEY",
            config_file=".env"
        )
        assert error.config_key == "NOTION_API_KEY"
        assert error.config_file == ".env"


class TestFileOperationError:
    """Test FileOperationError class."""

    def test_file_error(self):
        """Test file operation error."""
        error = FileOperationError(
            "Permission denied",
            file_path="/protected/file.txt",
            operation="write"
        )
        assert error.file_path == "/protected/file.txt"
        assert error.operation == "write"


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError(
            "Invalid URL format",
            field="url",
            value="not-a-url"
        )
        assert error.field == "url"
        assert error.value == "not-a-url"

    def test_validation_error_with_none_value(self):
        """Test validation error with None value."""
        error = ValidationError(
            "Required field missing",
            field="title",
            value=None
        )
        assert error.value is None
