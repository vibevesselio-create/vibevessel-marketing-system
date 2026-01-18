"""
Unit tests for the logging module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import logging
import tempfile

import sys
sys.path.insert(0, '.')

from music_workflow.utils.logging import (
    MusicWorkflowLogger,
    get_logger,
    log_execution,
)


class TestMusicWorkflowLogger:
    """Test MusicWorkflowLogger class."""

    def test_logger_initialization(self):
        """Test logger can be initialized."""
        logger = MusicWorkflowLogger("test_module")
        assert logger is not None
        assert logger.name == "test_module"

    def test_logger_with_log_level(self):
        """Test logger with different log levels."""
        logger = MusicWorkflowLogger("test", level="DEBUG")
        assert logger.logger.level == logging.DEBUG

        logger = MusicWorkflowLogger("test2", level="WARNING")
        assert logger.logger.level == logging.WARNING

    def test_logger_without_timestamp(self):
        """Test logger without timestamps."""
        logger = MusicWorkflowLogger("test", include_timestamp=False)
        assert logger._include_timestamp is False

    def test_logger_with_file(self):
        """Test logger with file output."""
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_file = Path(f.name)

        try:
            logger = MusicWorkflowLogger("test", log_file=log_file)
            logger.info("Test message")

            # Check file has content
            assert log_file.exists()
            content = log_file.read_text()
            assert "Test message" in content
        finally:
            log_file.unlink(missing_ok=True)

    def test_debug_method(self):
        """Test debug logging."""
        logger = MusicWorkflowLogger("test", level="DEBUG")
        with patch.object(logger.logger, 'debug') as mock_debug:
            logger.debug("Debug message")
            mock_debug.assert_called_once()

    def test_info_method(self):
        """Test info logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger.logger, 'info') as mock_info:
            logger.info("Info message")
            mock_info.assert_called_once()

    def test_warning_method(self):
        """Test warning logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger.logger, 'warning') as mock_warning:
            logger.warning("Warning message")
            mock_warning.assert_called_once()

    def test_error_method(self):
        """Test error logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger.logger, 'error') as mock_error:
            logger.error("Error message")
            mock_error.assert_called_once()

    def test_critical_method(self):
        """Test critical logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger.logger, 'critical') as mock_critical:
            logger.critical("Critical message")
            mock_critical.assert_called_once()

    def test_format_message_without_context(self):
        """Test message formatting without context."""
        logger = MusicWorkflowLogger("test")
        result = logger._format_message("Test message", {})
        assert result == "Test message"

    def test_format_message_with_context(self):
        """Test message formatting with context."""
        logger = MusicWorkflowLogger("test")
        result = logger._format_message("Test", {"key1": "value1", "key2": "value2"})
        assert "Test" in result
        assert "key1=value1" in result
        assert "key2=value2" in result

    def test_track_start(self):
        """Test track_start logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger, 'info') as mock_info:
            logger.track_start("My Track", "download")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "[START]" in call_args
            assert "download" in call_args

    def test_track_complete(self):
        """Test track_complete logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger, 'info') as mock_info:
            logger.track_complete("My Track", "download")
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "[COMPLETE]" in call_args

    def test_track_error(self):
        """Test track_error logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger, 'error') as mock_error:
            logger.track_error("My Track", "download", "Connection failed")
            mock_error.assert_called_once()
            call_args = mock_error.call_args[0][0]
            assert "[ERROR]" in call_args

    def test_workflow_start(self):
        """Test workflow_start logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger, 'info') as mock_info:
            logger.workflow_start("batch_download", 10)
            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Starting" in call_args[0][0]

    def test_workflow_complete(self):
        """Test workflow_complete logging."""
        logger = MusicWorkflowLogger("test")
        with patch.object(logger, 'info') as mock_info:
            logger.workflow_complete("batch_download", processed=8, failed=1, skipped=1)
            mock_info.assert_called_once()
            call_args = mock_info.call_args[0][0]
            assert "Completed" in call_args


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_default(self):
        """Test getting default logger."""
        logger = get_logger()
        assert logger is not None
        assert logger.name == "music_workflow"

    def test_get_logger_with_name(self):
        """Test getting logger with custom name."""
        logger = get_logger(name="custom_module")
        assert logger.name == "custom_module"

    def test_get_logger_with_level(self):
        """Test getting logger with custom level."""
        logger = get_logger(name="test_level", level="DEBUG")
        assert logger.logger.level == logging.DEBUG

    def test_get_logger_caches_instance(self):
        """Test logger caching behavior."""
        # Note: This tests the caching mechanism
        logger1 = get_logger(name="cached_test")
        logger2 = get_logger(name="cached_test")
        # Should return same instance for same name
        assert logger1 is logger2


class TestLogExecution:
    """Test log_execution function."""

    def test_log_execution_basic(self):
        """Test basic execution log creation."""
        result = log_execution(
            script_name="test_script",
            status="Success",
            duration=10.5,
        )

        assert result["script"] == "test_script"
        assert result["status"] == "Success"
        assert result["duration_seconds"] == 10.5
        assert result["metrics"] == {}
        assert "timestamp" in result

    def test_log_execution_with_metrics(self):
        """Test execution log with metrics."""
        metrics = {
            "tracks_processed": 10,
            "tracks_failed": 2,
            "average_time": 5.2
        }

        result = log_execution(
            script_name="batch_processor",
            status="Partial",
            duration=52.0,
            metrics=metrics,
        )

        assert result["metrics"] == metrics
        assert result["status"] == "Partial"

    def test_log_execution_failed_status(self):
        """Test execution log with failed status."""
        result = log_execution(
            script_name="failed_script",
            status="Failed",
            duration=1.0,
        )

        assert result["status"] == "Failed"

    def test_log_execution_timestamp_format(self):
        """Test timestamp is ISO format."""
        result = log_execution(
            script_name="test",
            status="Success",
            duration=1.0,
        )

        # Should be ISO format timestamp
        timestamp = result["timestamp"]
        assert "T" in timestamp  # ISO format includes T between date and time
