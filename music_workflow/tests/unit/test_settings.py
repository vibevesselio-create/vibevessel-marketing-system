"""
Unit tests for the settings/config module.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, '.')

from music_workflow.config.settings import (
    DownloadConfig,
    ProcessingConfig,
    DeduplicationConfig,
    NotionConfig,
    EagleConfig,
    SpotifyConfig,
    FeatureFlags,
    WorkflowSettings,
    get_settings,
    reset_settings,
    Settings,
)


class TestDownloadConfig:
    """Test DownloadConfig dataclass."""

    def test_default_values(self):
        """Test default download config values."""
        config = DownloadConfig()
        # Default formats changed to wav, aiff for lossless workflow
        assert "wav" in config.default_formats or "aiff" in config.default_formats
        assert config.max_retries == 3
        assert config.timeout == 300
        assert config.youtube_fallback is True
        assert config.output_template == "%(title)s.%(ext)s"

    def test_custom_values(self):
        """Test custom download config values."""
        config = DownloadConfig(
            default_formats=["mp3"],
            max_retries=5,
            timeout=600,
            youtube_fallback=False
        )
        assert config.default_formats == ["mp3"]
        assert config.max_retries == 5
        assert config.timeout == 600
        assert config.youtube_fallback is False


class TestProcessingConfig:
    """Test ProcessingConfig dataclass."""

    def test_default_values(self):
        """Test default processing config values."""
        config = ProcessingConfig()
        assert config.target_lufs == -14.0
        assert config.analyze_bpm is True
        assert config.analyze_key is True
        assert config.preserve_original is True

    def test_custom_values(self):
        """Test custom processing config values."""
        config = ProcessingConfig(
            target_lufs=-16.0,
            analyze_bpm=False,
            analyze_key=False
        )
        assert config.target_lufs == -16.0
        assert config.analyze_bpm is False


class TestDeduplicationConfig:
    """Test DeduplicationConfig dataclass."""

    def test_default_values(self):
        """Test default deduplication config values."""
        config = DeduplicationConfig()
        assert config.enabled is True
        assert config.fingerprint_threshold == 0.95
        assert config.check_notion is True
        assert config.check_eagle is True
        assert config.check_file_hash is True

    def test_custom_values(self):
        """Test custom deduplication config values."""
        config = DeduplicationConfig(
            enabled=False,
            fingerprint_threshold=0.9,
            check_notion=False
        )
        assert config.enabled is False
        assert config.fingerprint_threshold == 0.9
        assert config.check_notion is False


class TestNotionConfig:
    """Test NotionConfig dataclass."""

    def setup_method(self):
        """Clean environment before each test."""
        for key in ['TRACKS_DB_ID', 'PLAYLISTS_DB_ID', 'EXECUTION_LOGS_DB_ID', 'ISSUES_DB_ID']:
            if key in os.environ:
                del os.environ[key]

    def teardown_method(self):
        """Clean environment after each test."""
        for key in ['TRACKS_DB_ID', 'PLAYLISTS_DB_ID', 'EXECUTION_LOGS_DB_ID', 'ISSUES_DB_ID']:
            if key in os.environ:
                del os.environ[key]

    def test_default_values(self):
        """Test default Notion config values."""
        config = NotionConfig()
        assert config.timeout == 30
        assert config.max_retries == 3

    def test_loads_from_env(self):
        """Test Notion config loads from environment."""
        os.environ['TRACKS_DB_ID'] = 'test-tracks-db'
        os.environ['PLAYLISTS_DB_ID'] = 'test-playlists-db'

        config = NotionConfig()
        assert config.tracks_db_id == 'test-tracks-db'
        assert config.playlists_db_id == 'test-playlists-db'


class TestEagleConfig:
    """Test EagleConfig dataclass."""

    def setup_method(self):
        """Clean environment before each test."""
        if 'EAGLE_LIBRARY_PATH' in os.environ:
            del os.environ['EAGLE_LIBRARY_PATH']

    def teardown_method(self):
        """Clean environment after each test."""
        if 'EAGLE_LIBRARY_PATH' in os.environ:
            del os.environ['EAGLE_LIBRARY_PATH']

    def test_default_values(self):
        """Test default Eagle config values."""
        config = EagleConfig()
        assert config.library_path is None
        assert config.auto_import is True
        assert config.default_tags == []

    def test_loads_from_env(self):
        """Test Eagle config loads from environment."""
        os.environ['EAGLE_LIBRARY_PATH'] = '/path/to/eagle/library'

        config = EagleConfig()
        assert config.library_path == Path('/path/to/eagle/library')


class TestSpotifyConfig:
    """Test SpotifyConfig dataclass."""

    def setup_method(self):
        """Clean environment before each test."""
        for key in ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET']:
            if key in os.environ:
                del os.environ[key]

    def teardown_method(self):
        """Clean environment after each test."""
        for key in ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET']:
            if key in os.environ:
                del os.environ[key]

    def test_default_values(self):
        """Test default Spotify config values."""
        config = SpotifyConfig()
        assert config.enrich_metadata is True
        assert config.client_id is None
        assert config.client_secret is None

    def test_loads_from_env(self):
        """Test Spotify config loads from environment."""
        os.environ['SPOTIFY_CLIENT_ID'] = 'test-client-id'
        os.environ['SPOTIFY_CLIENT_SECRET'] = 'test-client-secret'

        config = SpotifyConfig()
        assert config.client_id == 'test-client-id'
        assert config.client_secret == 'test-client-secret'


class TestFeatureFlags:
    """Test FeatureFlags dataclass."""

    def setup_method(self):
        """Clean environment before each test."""
        for key in ['MUSIC_WORKFLOW_USE_MODULAR', 'MUSIC_WORKFLOW_YOUTUBE_FALLBACK', 'MUSIC_WORKFLOW_DEDUP_ENABLED']:
            if key in os.environ:
                del os.environ[key]

    def teardown_method(self):
        """Clean environment after each test."""
        for key in ['MUSIC_WORKFLOW_USE_MODULAR', 'MUSIC_WORKFLOW_YOUTUBE_FALLBACK', 'MUSIC_WORKFLOW_DEDUP_ENABLED']:
            if key in os.environ:
                del os.environ[key]

    def test_default_values(self):
        """Test default feature flag values."""
        flags = FeatureFlags()
        assert flags.use_modular is False
        assert flags.youtube_fallback is True
        assert flags.dedup_enabled is True

    def test_use_modular_true_values(self):
        """Test use_modular accepts various true values."""
        for value in ['true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES']:
            os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = value
            flags = FeatureFlags()
            assert flags.use_modular is True, f"Failed for value: {value}"

    def test_use_modular_false_values(self):
        """Test use_modular rejects non-true values."""
        for value in ['false', 'False', '0', 'no', 'No', 'invalid', '']:
            os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = value
            flags = FeatureFlags()
            assert flags.use_modular is False, f"Failed for value: {value}"

    def test_youtube_fallback_disabled(self):
        """Test youtube_fallback can be disabled."""
        os.environ['MUSIC_WORKFLOW_YOUTUBE_FALLBACK'] = 'false'
        flags = FeatureFlags()
        assert flags.youtube_fallback is False

    def test_dedup_disabled(self):
        """Test dedup_enabled can be disabled."""
        os.environ['MUSIC_WORKFLOW_DEDUP_ENABLED'] = 'false'
        flags = FeatureFlags()
        assert flags.dedup_enabled is False


class TestWorkflowSettings:
    """Test WorkflowSettings dataclass."""

    def setup_method(self):
        """Reset settings and clean environment."""
        reset_settings()
        for key in ['MUSIC_WORKFLOW_LOG_LEVEL', 'MUSIC_WORKFLOW_OUTPUT_DIR',
                    'MUSIC_WORKFLOW_TEMP_DIR', 'MUSIC_WORKFLOW_USE_MODULAR']:
            if key in os.environ:
                del os.environ[key]

    def teardown_method(self):
        """Clean up after each test."""
        reset_settings()
        for key in ['MUSIC_WORKFLOW_LOG_LEVEL', 'MUSIC_WORKFLOW_OUTPUT_DIR',
                    'MUSIC_WORKFLOW_TEMP_DIR', 'MUSIC_WORKFLOW_USE_MODULAR']:
            if key in os.environ:
                del os.environ[key]

    def test_default_values(self):
        """Test default workflow settings."""
        settings = WorkflowSettings()
        assert settings.log_level == "INFO"
        assert isinstance(settings.download, DownloadConfig)
        assert isinstance(settings.processing, ProcessingConfig)
        assert isinstance(settings.deduplication, DeduplicationConfig)
        assert isinstance(settings.notion, NotionConfig)
        assert isinstance(settings.eagle, EagleConfig)
        assert isinstance(settings.spotify, SpotifyConfig)
        assert isinstance(settings.features, FeatureFlags)

    def test_log_level_from_env(self):
        """Test log level loads from environment."""
        os.environ['MUSIC_WORKFLOW_LOG_LEVEL'] = 'DEBUG'
        settings = WorkflowSettings()
        assert settings.log_level == 'DEBUG'

    def test_output_dir_from_env(self):
        """Test output directory loads from environment."""
        os.environ['MUSIC_WORKFLOW_OUTPUT_DIR'] = '/custom/output'
        settings = WorkflowSettings()
        assert settings.output_dir == Path('/custom/output')

    def test_temp_dir_from_env(self):
        """Test temp directory loads from environment."""
        os.environ['MUSIC_WORKFLOW_TEMP_DIR'] = '/custom/temp'
        settings = WorkflowSettings()
        assert settings.temp_dir == Path('/custom/temp')

    def test_should_use_modular_default(self):
        """Test should_use_modular defaults to False."""
        settings = WorkflowSettings()
        assert settings.should_use_modular() is False

    def test_should_use_modular_enabled(self):
        """Test should_use_modular when enabled."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        settings = WorkflowSettings()
        assert settings.should_use_modular() is True


class TestGetSettings:
    """Test get_settings function."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Reset settings after each test."""
        reset_settings()

    def test_get_settings_returns_instance(self):
        """Test get_settings returns WorkflowSettings."""
        settings = get_settings()
        assert isinstance(settings, WorkflowSettings)

    def test_get_settings_singleton(self):
        """Test get_settings returns same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reset_settings(self):
        """Test reset_settings clears singleton."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()
        assert settings1 is not settings2


class TestSettingsAlias:
    """Test Settings alias."""

    def test_settings_alias_is_workflow_settings(self):
        """Test Settings alias points to WorkflowSettings."""
        assert Settings is WorkflowSettings

    def test_settings_alias_works(self):
        """Test Settings alias can be used."""
        settings = Settings()
        assert isinstance(settings, WorkflowSettings)
