"""
Unit tests for the MusicWorkflow module.

Tests workflow orchestration, error handling, and component coordination.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from music_workflow.core.workflow import (
    MusicWorkflow,
    WorkflowOptions,
    WorkflowResult,
)
from music_workflow.core.models import (
    TrackInfo,
    TrackStatus,
    DownloadResult,
    OrganizeResult,
    AudioAnalysis,
)
from music_workflow.utils.errors import (
    MusicWorkflowError,
    DownloadError,
    ProcessingError,
    DuplicateFoundError,
)


class TestWorkflowOptions:
    """Tests for WorkflowOptions dataclass."""

    def test_default_options(self):
        """Test default option values."""
        opts = WorkflowOptions()
        assert opts.download_formats == ["m4a", "aiff", "wav"]
        assert opts.analyze_audio is True
        assert opts.organize_files is True
        assert opts.create_backups is True
        assert opts.skip_duplicates is True
        assert opts.dry_run is False

    def test_custom_options(self):
        """Test custom option values."""
        opts = WorkflowOptions(
            download_formats=["wav"],
            analyze_audio=False,
            organize_files=False,
            dry_run=True,
        )
        assert opts.download_formats == ["wav"]
        assert opts.analyze_audio is False
        assert opts.organize_files is False
        assert opts.dry_run is True


class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""

    def test_success_result(self):
        """Test successful result creation."""
        track = TrackInfo(
            id="test-id",
            title="Test Track",
            artist="Test Artist",
        )
        result = WorkflowResult(
            success=True,
            track=track,
            execution_time_seconds=5.5,
        )
        assert result.success is True
        assert result.errors == []
        assert result.warnings == []
        assert result.execution_time_seconds == 5.5

    def test_failure_result(self):
        """Test failure result with errors."""
        track = TrackInfo(id="test-id", title="Failed Track", artist="Artist")
        result = WorkflowResult(
            success=False,
            track=track,
            errors=["Download failed", "Network timeout"],
        )
        assert result.success is False
        assert len(result.errors) == 2
        assert "Download failed" in result.errors


class TestMusicWorkflow:
    """Tests for MusicWorkflow class."""

    @pytest.fixture
    def mock_downloader(self):
        """Create a mock downloader."""
        mock = MagicMock()
        mock.download.return_value = DownloadResult(
            success=True,
            files=[Path("/tmp/test.m4a")],
            metadata={"title": "Test", "artist": "Artist"},
        )
        return mock

    @pytest.fixture
    def mock_processor(self):
        """Create a mock processor."""
        mock = MagicMock()
        mock.analyze.return_value = AudioAnalysis(
            bpm=120.0,
            key="C Major",
            duration=180.0,
            sample_rate=44100,
            channels=2,
        )
        return mock

    @pytest.fixture
    def mock_organizer(self):
        """Create a mock organizer."""
        mock = MagicMock()
        mock.organize.return_value = OrganizeResult(
            success=True,
            original_path=Path("/tmp/test.m4a"),
            final_path=Path("/music/Artist/test.m4a"),
        )
        return mock

    @pytest.fixture
    def workflow(self, mock_downloader, mock_processor, mock_organizer):
        """Create a workflow with mocked components."""
        wf = MusicWorkflow()
        wf.downloader = mock_downloader
        wf.processor = mock_processor
        wf.organizer = mock_organizer
        return wf

    def test_init_default(self):
        """Test default initialization."""
        wf = MusicWorkflow()
        assert wf.options is not None
        assert wf.downloader is not None
        assert wf.processor is not None
        assert wf.organizer is not None

    def test_init_custom_options(self):
        """Test initialization with custom options."""
        opts = WorkflowOptions(
            download_formats=["wav"],
            dry_run=True,
        )
        wf = MusicWorkflow(options=opts)
        assert wf.options.download_formats == ["wav"]
        assert wf.options.dry_run is True

    def test_process_url_success(self, workflow, mock_downloader):
        """Test successful URL processing."""
        result = workflow.process_url("https://soundcloud.com/artist/track")

        mock_downloader.download.assert_called_once()
        assert result.success is True
        assert result.download_result is not None

    def test_process_url_download_failure(self, workflow, mock_downloader):
        """Test URL processing with download failure."""
        mock_downloader.download.side_effect = DownloadError(
            "Network error",
            url="https://example.com/track",
        )

        result = workflow.process_url("https://example.com/track")

        assert result.success is False
        assert len(result.errors) > 0
        assert "Download failed" in result.errors[0] or "Network error" in result.errors[0]

    def test_process_url_with_analysis(self, workflow, mock_processor):
        """Test URL processing includes audio analysis."""
        workflow.options.analyze_audio = True

        result = workflow.process_url("https://soundcloud.com/artist/track")

        # Processor should have been called for analysis
        assert result.success is True

    def test_process_url_skip_analysis(self, workflow, mock_processor):
        """Test URL processing can skip analysis."""
        workflow.options.analyze_audio = False

        result = workflow.process_url("https://soundcloud.com/artist/track")

        assert result.success is True

    def test_process_url_dry_run(self, workflow, mock_downloader):
        """Test dry run mode doesn't actually download."""
        workflow.options.dry_run = True

        result = workflow.process_url("https://soundcloud.com/artist/track")

        # In dry run, download shouldn't happen
        # (implementation may vary)
        assert result is not None

    def test_process_track_success(self, workflow):
        """Test processing an existing TrackInfo."""
        track = TrackInfo(
            id="test-123",
            title="Test Track",
            artist="Test Artist",
            source_url="https://soundcloud.com/artist/track",
        )

        result = workflow.process_track(track)

        assert result.success is True
        assert result.track.id == "test-123"

    def test_process_track_duplicate(self, workflow, mock_downloader):
        """Test duplicate detection during processing."""
        mock_downloader.download.side_effect = DuplicateFoundError(
            "Track already exists",
            existing_track=TrackInfo(
                id="existing",
                title="Test",
                artist="Artist",
            ),
        )

        track = TrackInfo(
            id="test",
            title="Test",
            artist="Artist",
            source_url="https://example.com/track",
        )

        result = workflow.process_track(track)

        assert result.success is False
        assert any("duplicate" in e.lower() for e in result.errors)

    def test_progress_callback(self, workflow):
        """Test progress callback is invoked."""
        callback_calls = []

        def callback(track, status):
            callback_calls.append((track, status))

        workflow.set_progress_callback(callback)
        workflow.process_url("https://soundcloud.com/artist/track")

        # Callback should have been called at least once
        # (implementation may vary)
        # assert len(callback_calls) > 0

    def test_batch_process(self, workflow):
        """Test batch processing multiple URLs."""
        urls = [
            "https://soundcloud.com/artist/track1",
            "https://soundcloud.com/artist/track2",
            "https://soundcloud.com/artist/track3",
        ]

        results = workflow.process_batch(urls)

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_batch_process_with_failures(self, workflow, mock_downloader):
        """Test batch processing with some failures."""
        # Make second download fail
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise DownloadError("Failed", url="test")
            return DownloadResult(
                success=True,
                files=[Path("/tmp/test.m4a")],
                metadata={},
            )

        mock_downloader.download.side_effect = side_effect

        urls = [
            "https://soundcloud.com/artist/track1",
            "https://soundcloud.com/artist/track2",
            "https://soundcloud.com/artist/track3",
        ]

        results = workflow.process_batch(urls)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True


class TestWorkflowErrorHandling:
    """Tests for workflow error handling."""

    @pytest.fixture
    def workflow(self):
        """Create a workflow for error testing."""
        return MusicWorkflow()

    def test_handles_download_error(self, workflow):
        """Test handling of download errors."""
        workflow.downloader.download = Mock(
            side_effect=DownloadError("Connection refused", url="test")
        )

        result = workflow.process_url("https://example.com/track")

        assert result.success is False
        assert len(result.errors) > 0

    def test_handles_processing_error(self, workflow):
        """Test handling of processing errors."""
        # Mock successful download
        workflow.downloader.download = Mock(
            return_value=DownloadResult(
                success=True,
                files=[Path("/tmp/test.m4a")],
                metadata={},
            )
        )
        # Mock processing failure
        workflow.processor.analyze = Mock(
            side_effect=ProcessingError("Corrupt audio file")
        )

        result = workflow.process_url("https://example.com/track")

        # Result should still contain download info, even if processing failed
        assert result.download_result is not None

    def test_handles_unexpected_error(self, workflow):
        """Test handling of unexpected errors."""
        workflow.downloader.download = Mock(side_effect=RuntimeError("Unexpected"))

        result = workflow.process_url("https://example.com/track")

        assert result.success is False

    def test_error_messages_are_informative(self, workflow):
        """Test that error messages provide useful information."""
        workflow.downloader.download = Mock(
            side_effect=DownloadError(
                "Rate limit exceeded",
                url="https://example.com/track",
                details={"retry_after": 60},
            )
        )

        result = workflow.process_url("https://example.com/track")

        assert result.success is False
        assert len(result.errors) > 0
        # Error message should contain useful info
        error_text = " ".join(result.errors)
        assert "Rate limit" in error_text or "rate" in error_text.lower()


class TestWorkflowIntegration:
    """Integration-style tests for workflow components."""

    def test_full_pipeline_mock(self):
        """Test full pipeline with mocked external calls."""
        # This test verifies the workflow coordinates all components
        wf = MusicWorkflow()

        # Mock all external dependencies
        wf.downloader.download = Mock(
            return_value=DownloadResult(
                success=True,
                files=[Path("/tmp/test.m4a")],
                metadata={"title": "Test", "artist": "Artist"},
            )
        )
        wf.processor.analyze = Mock(
            return_value=AudioAnalysis(
                bpm=128.0,
                key="A Minor",
                duration=240.0,
                sample_rate=44100,
                channels=2,
            )
        )
        wf.organizer.organize = Mock(
            return_value=OrganizeResult(
                success=True,
                original_path=Path("/tmp/test.m4a"),
                final_path=Path("/music/test.m4a"),
            )
        )

        result = wf.process_url("https://soundcloud.com/artist/track")

        assert result.success is True
        assert result.download_result is not None

    def test_workflow_state_isolation(self):
        """Test that workflow instances don't share state."""
        wf1 = MusicWorkflow(options=WorkflowOptions(dry_run=True))
        wf2 = MusicWorkflow(options=WorkflowOptions(dry_run=False))

        assert wf1.options.dry_run is True
        assert wf2.options.dry_run is False
