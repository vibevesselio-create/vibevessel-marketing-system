"""
Spotify API client wrapper for music workflow.

This module provides a Spotify client wrapper specifically for music workflow
operations, including OAuth token management, track/playlist fetching, and
metadata enrichment.
"""

import os
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import requests

from music_workflow.utils.errors import SpotifyIntegrationError
from music_workflow.config.settings import get_settings


@dataclass
class SpotifyTrack:
    """Represents a Spotify track with metadata."""
    id: str
    name: str
    artists: List[str]
    album: Optional[str] = None
    album_art_url: Optional[str] = None
    duration_ms: int = 0
    popularity: int = 0
    isrc: Optional[str] = None
    preview_url: Optional[str] = None
    explicit: bool = False
    spotify_url: Optional[str] = None
    release_date: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[int] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None


@dataclass
class SpotifyPlaylist:
    """Represents a Spotify playlist."""
    id: str
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    public: bool = True
    collaborative: bool = False
    track_count: int = 0
    image_url: Optional[str] = None
    spotify_url: Optional[str] = None
    tracks: List[SpotifyTrack] = field(default_factory=list)


class SpotifyOAuthManager:
    """Manages Spotify OAuth tokens with automatic refresh."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
        self.access_token = access_token or os.getenv("SPOTIFY_ACCESS_TOKEN")
        self.refresh_token = refresh_token or os.getenv("SPOTIFY_REFRESH_TOKEN")
        self.token_expires_at: Optional[datetime] = self._parse_expiration(
            os.getenv("SPOTIFY_ACCESS_TOKEN_EXPIRES_AT")
        )

    def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary."""
        if isinstance(self.token_expires_at, (int, float)):
            self.token_expires_at = datetime.fromtimestamp(
                float(self.token_expires_at), tz=timezone.utc
            )

        if not self.access_token:
            if self.refresh_token:
                if not self._refresh_token():
                    return None
            else:
                return None

        # Check if token is expired (with 5-minute buffer)
        if self.token_expires_at and datetime.now(timezone.utc) >= self.token_expires_at:
            if not self._refresh_token():
                return None

        return self.access_token

    def _refresh_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self.refresh_token or not self.client_id or not self.client_secret:
            return False

        try:
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_b64 = base64.b64encode(auth_string.encode("ascii")).decode("ascii")
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            data = {"grant_type": "refresh_token", "refresh_token": self.refresh_token}

            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=30,
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data["refresh_token"]

                expires_in = int(token_data.get("expires_in", 3600))
                buffer_seconds = 300 if expires_in > 300 else 0
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=max(0, expires_in - buffer_seconds)
                )

                # Update environment variables
                os.environ["SPOTIFY_ACCESS_TOKEN"] = self.access_token
                os.environ["SPOTIFY_ACCESS_TOKEN_EXPIRES_AT"] = (
                    self.token_expires_at.isoformat()
                )
                return True

            return False
        except Exception:
            return False

    def _parse_expiration(self, value: Optional[str]) -> Optional[datetime]:
        """Parse expiration timestamp from string."""
        if not value:
            return None

        # Try parsing as float timestamp
        try:
            ts = float(value.strip())
            if ts > 1e12:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (TypeError, ValueError):
            pass

        # Try parsing as ISO format
        try:
            dt = datetime.fromisoformat(value.strip())
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        return None


class SpotifyClient:
    """Wrapper around Spotify API for music workflow operations.

    Provides high-level methods for:
    - Fetching track metadata
    - Fetching playlist tracks
    - Audio feature analysis
    - Search functionality
    """

    BASE_URL = "https://api.spotify.com/v1"

    def __init__(
        self,
        oauth_manager: Optional[SpotifyOAuthManager] = None,
        market: Optional[str] = None,
    ):
        """Initialize the Spotify client.

        Args:
            oauth_manager: OAuth manager for token handling
            market: Market code for region-specific content (default: US)
        """
        self._oauth_manager = oauth_manager or SpotifyOAuthManager()
        self._market = market or os.getenv("SPOTIFY_MARKET", "US")
        self._settings = get_settings()

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        token = self._oauth_manager.get_valid_token()
        if not token:
            raise SpotifyIntegrationError(
                "No valid Spotify token available",
                details={"hint": "Check SPOTIFY_ACCESS_TOKEN or SPOTIFY_REFRESH_TOKEN"},
            )

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        max_retries: int = 3,
    ) -> Optional[Dict]:
        """Make API request with error handling and retry logic."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    timeout=30,
                )

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(response.headers.get("Retry-After", 5))
                    import time
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    # Server error - retry
                    import time
                    time.sleep(2 ** attempt)
                    continue

                raise SpotifyIntegrationError(
                    f"Spotify API error: {response.status_code}",
                    status_code=response.status_code,
                    details={"response": response.text[:500]},
                )

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise SpotifyIntegrationError(
                    f"Request failed: {e}",
                    details={"endpoint": endpoint},
                )

        return None

    def get_track(self, track_id: str) -> Optional[SpotifyTrack]:
        """Get track by ID.

        Args:
            track_id: Spotify track ID

        Returns:
            SpotifyTrack object or None if not found
        """
        data = self._make_request("GET", f"/tracks/{track_id}", {"market": self._market})
        if not data:
            return None

        return self._parse_track(data)

    def get_tracks(self, track_ids: List[str]) -> List[SpotifyTrack]:
        """Get multiple tracks by ID (batch).

        Args:
            track_ids: List of Spotify track IDs (max 50)

        Returns:
            List of SpotifyTrack objects
        """
        if not track_ids:
            return []

        # Spotify API limit is 50 tracks per request
        tracks = []
        for i in range(0, len(track_ids), 50):
            batch = track_ids[i : i + 50]
            data = self._make_request(
                "GET",
                "/tracks",
                {"ids": ",".join(batch), "market": self._market},
            )
            if data and "tracks" in data:
                for item in data["tracks"]:
                    if item:
                        tracks.append(self._parse_track(item))

        return tracks

    def get_audio_features(self, track_id: str) -> Optional[Dict]:
        """Get audio features for a track.

        Args:
            track_id: Spotify track ID

        Returns:
            Audio features dictionary or None
        """
        return self._make_request("GET", f"/audio-features/{track_id}")

    def get_audio_features_batch(self, track_ids: List[str]) -> Dict[str, Dict]:
        """Get audio features for multiple tracks.

        Args:
            track_ids: List of Spotify track IDs (max 100)

        Returns:
            Dictionary mapping track_id to audio features
        """
        if not track_ids:
            return {}

        features = {}
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i : i + 100]
            data = self._make_request(
                "GET",
                "/audio-features",
                {"ids": ",".join(batch)},
            )
            if data and "audio_features" in data:
                for item in data["audio_features"]:
                    if item:
                        features[item["id"]] = item

        return features

    def get_playlist(
        self,
        playlist_id: str,
        include_tracks: bool = True,
    ) -> Optional[SpotifyPlaylist]:
        """Get playlist with optional tracks.

        Args:
            playlist_id: Spotify playlist ID
            include_tracks: Whether to fetch all tracks

        Returns:
            SpotifyPlaylist object or None
        """
        fields = "id,name,description,owner.display_name,public,collaborative,images,external_urls,tracks.total"
        data = self._make_request(
            "GET",
            f"/playlists/{playlist_id}",
            {"fields": fields, "market": self._market},
        )

        if not data:
            return None

        playlist = SpotifyPlaylist(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            owner=data.get("owner", {}).get("display_name"),
            public=data.get("public", True),
            collaborative=data.get("collaborative", False),
            track_count=data.get("tracks", {}).get("total", 0),
            image_url=(data.get("images") or [{}])[0].get("url"),
            spotify_url=data.get("external_urls", {}).get("spotify"),
        )

        if include_tracks:
            playlist.tracks = self.get_playlist_tracks(playlist_id)

        return playlist

    def get_playlist_tracks(self, playlist_id: str) -> List[SpotifyTrack]:
        """Get all tracks from a playlist.

        Args:
            playlist_id: Spotify playlist ID

        Returns:
            List of SpotifyTrack objects
        """
        tracks = []
        offset = 0
        limit = 100

        while True:
            data = self._make_request(
                "GET",
                f"/playlists/{playlist_id}/tracks",
                {
                    "offset": offset,
                    "limit": limit,
                    "market": self._market,
                    "fields": "items(track(id,name,artists,album,duration_ms,popularity,explicit,external_ids,external_urls,preview_url)),next",
                },
            )

            if not data:
                break

            for item in data.get("items", []):
                track = item.get("track")
                if track:
                    tracks.append(self._parse_track(track))

            if not data.get("next"):
                break

            offset += limit

        return tracks

    def search(
        self,
        query: str,
        types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict[str, List]:
        """Search Spotify.

        Args:
            query: Search query
            types: List of types to search (track, album, artist, playlist)
            limit: Maximum results per type (max 50)

        Returns:
            Dictionary with results by type
        """
        types = types or ["track"]
        type_str = ",".join(types)

        data = self._make_request(
            "GET",
            "/search",
            {
                "q": query,
                "type": type_str,
                "limit": min(limit, 50),
                "market": self._market,
            },
        )

        if not data:
            return {t: [] for t in types}

        results: Dict[str, List] = {}
        if "tracks" in data:
            results["tracks"] = [
                self._parse_track(t) for t in data["tracks"].get("items", [])
            ]
        if "albums" in data:
            results["albums"] = data["albums"].get("items", [])
        if "artists" in data:
            results["artists"] = data["artists"].get("items", [])
        if "playlists" in data:
            results["playlists"] = data["playlists"].get("items", [])

        return results

    def search_track(
        self,
        title: str,
        artist: Optional[str] = None,
        limit: int = 5,
    ) -> List[SpotifyTrack]:
        """Search for a specific track.

        Args:
            title: Track title
            artist: Optional artist name
            limit: Maximum results

        Returns:
            List of matching SpotifyTrack objects
        """
        query = title
        if artist:
            query = f"track:{title} artist:{artist}"

        results = self.search(query, types=["track"], limit=limit)
        return results.get("tracks", [])

    def enrich_track(self, track: SpotifyTrack) -> SpotifyTrack:
        """Enrich track with audio features.

        Args:
            track: SpotifyTrack to enrich

        Returns:
            Enriched SpotifyTrack with audio features
        """
        features = self.get_audio_features(track.id)
        if features:
            track.bpm = features.get("tempo")
            track.key = features.get("key")
            track.energy = features.get("energy")
            track.danceability = features.get("danceability")
            track.valence = features.get("valence")
            track.acousticness = features.get("acousticness")
            track.instrumentalness = features.get("instrumentalness")

        return track

    def _parse_track(self, data: Dict) -> SpotifyTrack:
        """Parse Spotify API track response into SpotifyTrack."""
        artists = [a.get("name", "Unknown") for a in data.get("artists", [])]
        album_data = data.get("album", {})
        images = album_data.get("images", [])

        return SpotifyTrack(
            id=data["id"],
            name=data["name"],
            artists=artists,
            album=album_data.get("name"),
            album_art_url=images[0].get("url") if images else None,
            duration_ms=data.get("duration_ms", 0),
            popularity=data.get("popularity", 0),
            isrc=data.get("external_ids", {}).get("isrc"),
            preview_url=data.get("preview_url"),
            explicit=data.get("explicit", False),
            spotify_url=data.get("external_urls", {}).get("spotify"),
            release_date=album_data.get("release_date"),
        )

    def is_available(self) -> bool:
        """Check if Spotify API is available."""
        try:
            token = self._oauth_manager.get_valid_token()
            return token is not None
        except Exception:
            return False


# Singleton instance
_spotify_client: Optional[SpotifyClient] = None


def get_spotify_client() -> SpotifyClient:
    """Get the global Spotify client instance."""
    global _spotify_client
    if _spotify_client is None:
        _spotify_client = SpotifyClient()
    return _spotify_client
