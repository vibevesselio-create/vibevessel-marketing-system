"""
Pytest configuration and fixtures for music workflow tests.

This module provides shared fixtures, mock data, and test configuration
for the music workflow test suite.
"""

import pytest
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock

# Import models when available
try:
    from music_workflow.core.models import TrackInfo, TrackStatus
except ImportError:
    TrackInfo = None
    TrackStatus = None


@pytest.fixture
def sample_track_data() -> Dict[str, Any]:
    """Provide sample track data for testing."""
    return {
        "id": "test-track-001",
        "title": "Test Track",
        "artist": "Test Artist",
        "album": "Test Album",
        "duration": 180.5,
        "bpm": 120.0,
        "key": "Cm",
        "source_url": "https://soundcloud.com/test/track",
        "source_platform": "soundcloud",
        "playlist": "Test Playlist",
        "tags": ["electronic", "test"],
    }


@pytest.fixture
def sample_track(sample_track_data) -> "TrackInfo":
    """Provide a sample TrackInfo instance for testing."""
    if TrackInfo is None:
        pytest.skip("TrackInfo not available")
    return TrackInfo.from_dict(sample_track_data)


@pytest.fixture
def temp_audio_dir(tmp_path) -> Path:
    """Provide a temporary directory for audio files."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    return audio_dir


@pytest.fixture
def mock_notion_client() -> MagicMock:
    """Provide a mock Notion client for testing."""
    mock = MagicMock()
    mock.query_database.return_value = []
    mock.update_page.return_value = {"id": "test-page-id"}
    mock.create_page.return_value = {"id": "new-page-id"}
    return mock


@pytest.fixture
def mock_eagle_client() -> MagicMock:
    """Provide a mock Eagle client for testing."""
    mock = MagicMock()
    mock.import_file.return_value = "eagle-item-id"
    mock.search.return_value = []
    return mock


@pytest.fixture
def mock_spotify_client() -> MagicMock:
    """Provide a mock Spotify client for testing."""
    mock = MagicMock()
    mock.track.return_value = {
        "id": "spotify-track-id",
        "name": "Test Track",
        "artists": [{"name": "Test Artist"}],
        "album": {"name": "Test Album"},
        "duration_ms": 180500,
    }
    mock.audio_features.return_value = {
        "tempo": 120.0,
        "key": 0,  # C
        "mode": 0,  # Minor
        "energy": 0.8,
        "danceability": 0.75,
    }
    return mock


@pytest.fixture
def sample_download_metadata() -> Dict[str, Any]:
    """Provide sample download metadata from yt-dlp."""
    return {
        "id": "abc123",
        "title": "Test Track - Test Artist",
        "uploader": "Test Artist",
        "duration": 180,
        "webpage_url": "https://soundcloud.com/test/track",
        "extractor": "soundcloud",
        "format": "mp4a-dash-3",
        "formats": [
            {"format_id": "mp4a-dash-3", "ext": "m4a"},
            {"format_id": "wav", "ext": "wav"},
        ],
    }


# Test markers
def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require external services"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that may require external services"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take a long time to run"
    )


# Skip slow tests by default
def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-slow", action="store_true", default=False, help="Run slow tests"
    )
    parser.addoption(
        "--run-integration", action="store_true", default=False,
        help="Run integration tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on markers."""
    if not config.getoption("--run-slow"):
        skip_slow = pytest.mark.skip(reason="Need --run-slow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    if not config.getoption("--run-integration"):
        skip_integration = pytest.mark.skip(
            reason="Need --run-integration option to run"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
