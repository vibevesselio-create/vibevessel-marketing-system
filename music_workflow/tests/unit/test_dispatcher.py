"""
Unit tests for the workflow dispatcher and feature flags.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '.')

from music_workflow.dispatcher import (
    WorkflowDispatcher,
    dispatch_workflow,
    get_active_workflow,
)
from music_workflow.config.settings import (
    FeatureFlags,
    WorkflowSettings,
    get_settings,
    reset_settings,
)


class TestFeatureFlags:
    """Test FeatureFlags dataclass."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up environment after each test."""
        # Remove any test env vars
        for key in ['MUSIC_WORKFLOW_USE_MODULAR', 'MUSIC_WORKFLOW_YOUTUBE_FALLBACK', 'MUSIC_WORKFLOW_DEDUP_ENABLED']:
            if key in os.environ:
                del os.environ[key]
        reset_settings()

    def test_default_values(self):
        """Test default feature flag values."""
        flags = FeatureFlags()
        assert flags.use_modular is False
        assert flags.youtube_fallback is True
        assert flags.dedup_enabled is True

    def test_use_modular_from_env_true(self):
        """Test use_modular reads from environment."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        flags = FeatureFlags()
        assert flags.use_modular is True

    def test_use_modular_from_env_false(self):
        """Test use_modular reads false from environment."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'false'
        flags = FeatureFlags()
        assert flags.use_modular is False

    def test_use_modular_from_env_1(self):
        """Test use_modular accepts '1' as true."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = '1'
        flags = FeatureFlags()
        assert flags.use_modular is True

    def test_use_modular_from_env_yes(self):
        """Test use_modular accepts 'yes' as true."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'yes'
        flags = FeatureFlags()
        assert flags.use_modular is True

    def test_youtube_fallback_disabled(self):
        """Test disabling YouTube fallback."""
        os.environ['MUSIC_WORKFLOW_YOUTUBE_FALLBACK'] = 'false'
        flags = FeatureFlags()
        assert flags.youtube_fallback is False

    def test_dedup_disabled(self):
        """Test disabling deduplication."""
        os.environ['MUSIC_WORKFLOW_DEDUP_ENABLED'] = 'false'
        flags = FeatureFlags()
        assert flags.dedup_enabled is False


class TestWorkflowSettings:
    """Test WorkflowSettings with feature flags."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up after each test."""
        for key in ['MUSIC_WORKFLOW_USE_MODULAR']:
            if key in os.environ:
                del os.environ[key]
        reset_settings()

    def test_should_use_modular_default(self):
        """Test should_use_modular returns False by default."""
        settings = WorkflowSettings()
        assert settings.should_use_modular() is False

    def test_should_use_modular_enabled(self):
        """Test should_use_modular when feature flag is enabled."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        settings = WorkflowSettings()
        assert settings.should_use_modular() is True

    def test_features_attribute_exists(self):
        """Test that features attribute exists and is FeatureFlags."""
        settings = WorkflowSettings()
        assert hasattr(settings, 'features')
        assert isinstance(settings.features, FeatureFlags)


class TestGetActiveWorkflow:
    """Test get_active_workflow function."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up after each test."""
        if 'MUSIC_WORKFLOW_USE_MODULAR' in os.environ:
            del os.environ['MUSIC_WORKFLOW_USE_MODULAR']
        reset_settings()

    def test_default_returns_monolithic(self):
        """Test default returns monolithic."""
        assert get_active_workflow() == "monolithic"

    def test_with_flag_returns_modular(self):
        """Test with flag enabled returns modular."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        reset_settings()
        assert get_active_workflow() == "modular"


class TestWorkflowDispatcher:
    """Test WorkflowDispatcher class."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up after each test."""
        if 'MUSIC_WORKFLOW_USE_MODULAR' in os.environ:
            del os.environ['MUSIC_WORKFLOW_USE_MODULAR']
        reset_settings()

    def test_dispatcher_initialization(self):
        """Test dispatcher can be initialized."""
        dispatcher = WorkflowDispatcher()
        assert dispatcher is not None
        assert dispatcher.settings is not None

    def test_should_use_modular_default(self):
        """Test dispatcher defaults to monolithic."""
        dispatcher = WorkflowDispatcher()
        assert dispatcher.should_use_modular() is False

    def test_should_use_modular_with_flag(self):
        """Test dispatcher uses modular with flag."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        reset_settings()
        dispatcher = WorkflowDispatcher()
        assert dispatcher.should_use_modular() is True

    @patch('music_workflow.core.workflow.MusicWorkflow')
    def test_process_url_routes_to_modular(self, mock_workflow_class):
        """Test process_url routes to modular when flag is set."""
        os.environ['MUSIC_WORKFLOW_USE_MODULAR'] = 'true'
        reset_settings()

        # Setup mock
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.track.id = "test-id"
        mock_result.track.title = "Test Track"
        mock_result.track.artist = "Test Artist"
        mock_result.track.bpm = 128.0
        mock_result.track.key = "Am"
        mock_result.track.duration = 180.0
        mock_result.errors = []
        mock_result.warnings = []
        mock_result.execution_time_seconds = 1.5

        mock_workflow = MagicMock()
        mock_workflow.process_url.return_value = mock_result
        mock_workflow_class.return_value = mock_workflow

        dispatcher = WorkflowDispatcher()
        result = dispatcher.process_url("https://soundcloud.com/test/track")

        assert result["workflow"] == "modular"
        assert result["success"] is True


class TestDispatchWorkflowFunction:
    """Test dispatch_workflow convenience function."""

    def setup_method(self):
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self):
        """Clean up after each test."""
        if 'MUSIC_WORKFLOW_USE_MODULAR' in os.environ:
            del os.environ['MUSIC_WORKFLOW_USE_MODULAR']
        reset_settings()

    @patch('music_workflow.dispatcher.WorkflowDispatcher')
    def test_dispatch_workflow_creates_dispatcher(self, mock_dispatcher_class):
        """Test dispatch_workflow creates a dispatcher."""
        mock_dispatcher = MagicMock()
        mock_dispatcher.process_url.return_value = {"success": True}
        mock_dispatcher_class.return_value = mock_dispatcher

        result = dispatch_workflow("https://example.com/track")

        mock_dispatcher_class.assert_called_once()
        mock_dispatcher.process_url.assert_called_once()
