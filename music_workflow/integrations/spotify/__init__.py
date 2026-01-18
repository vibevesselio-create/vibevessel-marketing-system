"""Spotify API integration for metadata enrichment.

This module provides Spotify API integration for the music workflow system,
including OAuth token management, track/playlist fetching, and audio feature
analysis.

Usage:
    from music_workflow.integrations.spotify import (
        SpotifyClient,
        SpotifyTrack,
        SpotifyPlaylist,
        get_spotify_client,
    )

    client = get_spotify_client()
    track = client.get_track("spotify_track_id")
    enriched = client.enrich_track(track)  # Adds audio features
"""

from music_workflow.integrations.spotify.client import (
    SpotifyClient,
    SpotifyTrack,
    SpotifyPlaylist,
    SpotifyOAuthManager,
    get_spotify_client,
)

__all__ = [
    "SpotifyClient",
    "SpotifyTrack",
    "SpotifyPlaylist",
    "SpotifyOAuthManager",
    "get_spotify_client",
]
