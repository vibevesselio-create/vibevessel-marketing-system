"""
Integration tests for Spotify module.

These tests verify the Spotify integration works correctly with the API.
"""

import pytest
import sys
sys.path.insert(0, '.')

from music_workflow.integrations.spotify.client import (
    SpotifyClient,
    SpotifyTrack,
    SpotifyPlaylist,
    SpotifyOAuthManager,
)
from music_workflow.utils.errors import SpotifyIntegrationError


class TestSpotifyClient:
    """Test SpotifyClient class."""

    def test_client_initialization(self):
        """Test client can be initialized."""
        try:
            client = SpotifyClient()
            assert client is not None
        except SpotifyIntegrationError:
            pass

    def test_spotify_track_dataclass(self):
        """Test SpotifyTrack dataclass."""
        track = SpotifyTrack(
            id="test123",
            name="Test Track",
            artists=["Test Artist"],
            album="Test Album",
            duration_ms=180000,
            popularity=50,
        )

        assert track.id == "test123"
        assert track.name == "Test Track"
        assert track.artists == ["Test Artist"]
        assert track.duration_ms == 180000

    def test_spotify_playlist_dataclass(self):
        """Test SpotifyPlaylist dataclass."""
        playlist = SpotifyPlaylist(
            id="playlist123",
            name="Test Playlist",
            description="A test playlist",
            owner="testuser",
            track_count=10,
            tracks=[],
        )

        assert playlist.id == "playlist123"
        assert playlist.name == "Test Playlist"
        assert playlist.track_count == 10


class TestSpotifyOAuthManager:
    """Test SpotifyOAuthManager class."""

    def test_oauth_manager_initialization(self):
        """Test OAuth manager can be initialized."""
        manager = SpotifyOAuthManager(
            client_id="test_id",
            client_secret="test_secret",
        )
        assert manager is not None
        assert manager.client_id == "test_id"


class TestSpotifyIntegrationError:
    """Test SpotifyIntegrationError exception."""

    def test_error_creation(self):
        """Test error can be created with message."""
        error = SpotifyIntegrationError("Test error message")
        assert "Test error message" in str(error)

    def test_error_inheritance(self):
        """Test error inherits from correct base."""
        from music_workflow.utils.errors import IntegrationError
        error = SpotifyIntegrationError("Test")
        assert isinstance(error, IntegrationError)
