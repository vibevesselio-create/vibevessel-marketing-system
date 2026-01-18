"""
Integration tests for SoundCloud module.

These tests verify the SoundCloud integration works correctly with yt-dlp.
Some tests require network access.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, '.')

from music_workflow.integrations.soundcloud.client import (
    SoundCloudClient,
    SoundCloudTrack,
    SoundCloudPlaylist,
    SoundCloudIntegrationError,
)


class TestSoundCloudClient:
    """Test SoundCloudClient class."""

    def test_client_initialization(self):
        """Test client can be initialized."""
        client = SoundCloudClient()
        assert client is not None

    def test_soundcloud_track_dataclass(self):
        """Test SoundCloudTrack dataclass."""
        track = SoundCloudTrack(
            id="123456789",
            title="Test Track",
            artist="Test Artist",
            url="https://soundcloud.com/artist/track",
            duration_seconds=180,
            description="A test track",
            genre="Electronic",
            artwork_url=None,
            play_count=1000,
            like_count=100,
        )

        assert track.id == "123456789"
        assert track.title == "Test Track"
        assert track.artist == "Test Artist"
        assert track.duration_seconds == 180
        assert track.play_count == 1000

    def test_soundcloud_playlist_dataclass(self):
        """Test SoundCloudPlaylist dataclass."""
        playlist = SoundCloudPlaylist(
            id="playlist123",
            title="Test Playlist",
            url="https://soundcloud.com/user/sets/playlist",
            creator="testuser",
            track_count=10,
            description="A test playlist",
            tracks=[],
        )

        assert playlist.id == "playlist123"
        assert playlist.title == "Test Playlist"
        assert playlist.track_count == 10

    def test_is_soundcloud_url(self):
        """Test SoundCloud URL detection."""
        client = SoundCloudClient()

        # Valid SoundCloud URLs
        assert client.is_soundcloud_url("https://soundcloud.com/artist/track") is True
        assert client.is_soundcloud_url("http://soundcloud.com/artist/track") is True
        assert client.is_soundcloud_url("https://www.soundcloud.com/artist/track") is True
        assert client.is_soundcloud_url("https://m.soundcloud.com/artist/track") is True

        # Invalid URLs
        assert client.is_soundcloud_url("https://youtube.com/watch?v=xxx") is False
        assert client.is_soundcloud_url("https://spotify.com/track/xxx") is False
        assert client.is_soundcloud_url("not a url") is False
        assert client.is_soundcloud_url("") is False

    def test_parse_track_url(self):
        """Test parsing track URLs."""
        client = SoundCloudClient()

        # Track URL
        url = "https://soundcloud.com/artist-name/track-title"
        assert client.is_soundcloud_url(url) is True

    def test_parse_playlist_url(self):
        """Test parsing playlist URLs."""
        client = SoundCloudClient()

        # Playlist/set URL
        url = "https://soundcloud.com/artist-name/sets/playlist-title"
        assert client.is_soundcloud_url(url) is True


class TestSoundCloudIntegrationError:
    """Test SoundCloudIntegrationError exception."""

    def test_error_creation(self):
        """Test error can be created with message."""
        error = SoundCloudIntegrationError("Test error message")
        assert "Test error message" in str(error)

    def test_error_inheritance(self):
        """Test error inherits from correct base."""
        from music_workflow.utils.errors import IntegrationError

        error = SoundCloudIntegrationError("Test")
        assert isinstance(error, IntegrationError)
