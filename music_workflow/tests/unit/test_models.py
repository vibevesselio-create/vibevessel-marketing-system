"""Unit tests for core models module."""

import pytest
from pathlib import Path
from music_workflow.core.models import (
    TrackInfo,
    TrackStatus,
    AudioFormat,
    AudioAnalysis,
    DownloadResult,
    OrganizeResult,
    DeduplicationResult,
)


class TestTrackInfo:
    """Tests for TrackInfo dataclass."""

    def test_create_basic_track(self):
        """Test creating a basic track."""
        track = TrackInfo(id="track1", title="Test Track", artist="Test Artist")
        assert track.id == "track1"
        assert track.title == "Test Track"
        assert track.artist == "Test Artist"
        assert track.status == TrackStatus.PENDING

    def test_add_file(self):
        """Test adding a file path."""
        track = TrackInfo(id="track1")
        track.add_file("m4a", Path("/path/to/file.m4a"))

        assert "m4a" in track.file_paths
        assert track.file_paths["m4a"] == Path("/path/to/file.m4a")

    def test_get_file(self):
        """Test getting a file path."""
        track = TrackInfo(id="track1")
        track.add_file("wav", Path("/path/to/file.wav"))

        assert track.get_file("wav") == Path("/path/to/file.wav")
        assert track.get_file("mp3") is None

    def test_add_error(self):
        """Test adding an error."""
        track = TrackInfo(id="track1")
        track.add_error("Download failed")

        assert len(track.errors) == 1
        assert track.errors[0] == "Download failed"
        assert track.status == TrackStatus.FAILED

    def test_add_warning(self):
        """Test adding a warning."""
        track = TrackInfo(id="track1")
        track.add_warning("Low quality source")

        assert len(track.warnings) == 1
        assert track.warnings[0] == "Low quality source"
        assert track.status == TrackStatus.PENDING  # Status unchanged

    def test_has_audio_analysis(self):
        """Test has_audio_analysis check."""
        track = TrackInfo(id="track1")
        assert track.has_audio_analysis() is False

        track.bpm = 120.0
        assert track.has_audio_analysis() is True

    def test_has_files(self):
        """Test has_files check."""
        track = TrackInfo(id="track1")
        assert track.has_files() is False

        track.add_file("m4a", Path("/path/to/file.m4a"))
        assert track.has_files() is True

    def test_to_dict(self):
        """Test serialization to dictionary."""
        track = TrackInfo(
            id="track1",
            title="Test Track",
            artist="Test Artist",
            bpm=120.0,
            key="Am",
        )
        track.add_file("m4a", Path("/path/to/file.m4a"))

        data = track.to_dict()
        assert data["id"] == "track1"
        assert data["title"] == "Test Track"
        assert data["artist"] == "Test Artist"
        assert data["bpm"] == 120.0
        assert data["key"] == "Am"
        assert "m4a" in data["file_paths"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "track1",
            "title": "Test Track",
            "artist": "Test Artist",
            "bpm": 120.0,
            "key": "Am",
            "status": "pending",
            "file_paths": {"m4a": "/path/to/file.m4a"},
        }

        track = TrackInfo.from_dict(data)
        assert track.id == "track1"
        assert track.title == "Test Track"
        assert track.bpm == 120.0
        assert track.status == TrackStatus.PENDING
        assert "m4a" in track.file_paths


class TestTrackStatus:
    """Tests for TrackStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert TrackStatus.PENDING.value == "pending"
        assert TrackStatus.DOWNLOADING.value == "downloading"
        assert TrackStatus.COMPLETE.value == "complete"
        assert TrackStatus.FAILED.value == "failed"


class TestAudioFormat:
    """Tests for AudioFormat enum."""

    def test_format_values(self):
        """Test format enum values."""
        assert AudioFormat.M4A.value == "m4a"
        assert AudioFormat.WAV.value == "wav"
        assert AudioFormat.AIFF.value == "aiff"
        assert AudioFormat.MP3.value == "mp3"


class TestAudioAnalysis:
    """Tests for AudioAnalysis dataclass."""

    def test_create_analysis(self):
        """Test creating audio analysis."""
        analysis = AudioAnalysis(
            bpm=120.0,
            key="Am",
            duration=180.0,
            sample_rate=44100,
            channels=2,
        )
        assert analysis.bpm == 120.0
        assert analysis.key == "Am"
        assert analysis.duration == 180.0
        assert analysis.sample_rate == 44100
        assert analysis.channels == 2


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_successful_download(self):
        """Test successful download result."""
        result = DownloadResult(
            success=True,
            files=[Path("/path/to/file.m4a")],
            source_url="https://example.com/track",
        )
        assert result.success is True
        assert len(result.files) == 1
        assert result.errors == []

    def test_failed_download(self):
        """Test failed download result."""
        result = DownloadResult(
            success=False,
            errors=["Connection timeout"],
        )
        assert result.success is False
        assert len(result.errors) == 1


class TestOrganizeResult:
    """Tests for OrganizeResult dataclass."""

    def test_successful_organize(self):
        """Test successful organize result."""
        result = OrganizeResult(
            success=True,
            source_path=Path("/source/file.m4a"),
            destination_path=Path("/dest/file.m4a"),
        )
        assert result.success is True
        assert result.errors == []


class TestDeduplicationResult:
    """Tests for DeduplicationResult dataclass."""

    def test_not_duplicate(self):
        """Test non-duplicate result."""
        result = DeduplicationResult(is_duplicate=False)
        assert result.is_duplicate is False
        assert result.matching_track_id is None

    def test_is_duplicate(self):
        """Test duplicate result."""
        result = DeduplicationResult(
            is_duplicate=True,
            matching_track_id="existing_track_1",
            similarity_score=0.95,
            fingerprint_match=True,
        )
        assert result.is_duplicate is True
        assert result.matching_track_id == "existing_track_1"
        assert result.similarity_score == 0.95
