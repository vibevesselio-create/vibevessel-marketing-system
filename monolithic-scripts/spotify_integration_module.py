#!/usr/bin/env python3
"""
Spotify Integration Module for Production
========================================

Comprehensive Spotify API integration with Notion synchronization.
Combines the best elements from existing implementations.

Features:
- OAuth token management with automatic refresh
- Playlist and track fetching with pagination
- Notion database integration with dynamic schema
- Error handling and retry logic
- State management for incremental sync

Author: Cursor MM1 Agent • 2025-01-27
"""

import os
import sys
import json
import time
import logging
import requests
import base64
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Import unified logging
try:
    # Add project root to path for imports
    import sys
    from pathlib import Path
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    # Import from shared_core.logging (correct path)
    from shared_core.logging import get_unified_logger
    UNIFIED_LOGGING_AVAILABLE = True
except (ImportError, ModuleNotFoundError, TimeoutError) as e:
    UNIFIED_LOGGING_AVAILABLE = False
    print(f"[spotify_integration_module] Unified logging unavailable ({e}); using fallback.", file=sys.stderr)

# Load environment variables
load_dotenv()

# CSV Backup integration for rate limit fallback
try:
    from spotify_csv_backup import SpotifyCSVBackup
    CSV_BACKUP_AVAILABLE = True
except ImportError:
    CSV_BACKUP_AVAILABLE = False

# Singleton instance for CSV backup
_csv_backup_instance = None

def get_spotify_csv_backup() -> Optional['SpotifyCSVBackup']:
    """Get singleton instance of SpotifyCSVBackup."""
    global _csv_backup_instance
    if not CSV_BACKUP_AVAILABLE:
        return None
    if _csv_backup_instance is None:
        _csv_backup_instance = SpotifyCSVBackup()
        _csv_backup_instance.load_all()
    return _csv_backup_instance

# Initialize unified logger if available
if UNIFIED_LOGGING_AVAILABLE:
    logger = get_unified_logger(
        script_name="spotify-integration",
        env=os.getenv("ENV", "PROD"),
        enable_notion=True
    )
else:
    # Fallback to basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

class SpotifyOAuthManager:
    """Manages Spotify OAuth tokens with automatic refresh."""
    
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.access_token = os.getenv("SPOTIFY_ACCESS_TOKEN")
        self.refresh_token = os.getenv("SPOTIFY_REFRESH_TOKEN")
        self.token_expires_at: Optional[datetime] = self._parse_expiration(
            os.getenv("SPOTIFY_ACCESS_TOKEN_EXPIRES_AT")
        )
        
    def get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary."""
        if isinstance(self.token_expires_at, (int, float)):
            self.token_expires_at = datetime.fromtimestamp(
                float(self.token_expires_at), tz=timezone.utc
            )
        elif isinstance(self.token_expires_at, str):
            self.token_expires_at = self._parse_expiration(self.token_expires_at)

        if not self.access_token:
            if self.refresh_token:
                logger.info("No Spotify access token found, attempting refresh...")
                if not self._refresh_token():
                    return None
            else:
                logger.error("No Spotify access token available")
                return None
            
        # Check if token is expired (with ~1-minute buffer)
        if self.token_expires_at and datetime.now(timezone.utc) >= self.token_expires_at:
            logger.info("Spotify token expired, refreshing...")
            if not self._refresh_token():
                return None
                
        return self.access_token
    
    def _refresh_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            logger.error("No refresh token available")
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
                # Spotify may not return a new refresh token; keep the existing one if missing.
                if token_data.get("refresh_token"):
                    self.refresh_token = token_data["refresh_token"]
                expires_in = int(token_data.get("expires_in", 3600))
                buffer_seconds = 300 if expires_in > 300 else 0
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=max(0, expires_in - buffer_seconds)
                )
                os.environ["SPOTIFY_ACCESS_TOKEN"] = self.access_token
                os.environ["SPOTIFY_ACCESS_TOKEN_EXPIRES_AT"] = self.token_expires_at.isoformat()
                os.environ["SPOTIFY_REFRESH_TOKEN"] = self.refresh_token or ""
                logger.info("Spotify token refreshed successfully")
                return True
            logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
            return False
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False

    def _parse_expiration(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        value = value.strip()
        parsed = self._parse_as_float_ts(value)
        if parsed:
            return parsed
        parsed = self._parse_iso(value)
        return parsed

    @staticmethod
    def _parse_as_float_ts(value: str) -> Optional[datetime]:
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return None
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, ValueError):
            return None

    @staticmethod
    def _parse_iso(value: str) -> Optional[datetime]:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

class SpotifyAPI:
    """Comprehensive Spotify API client with CSV backup fallback."""

    def __init__(self, oauth_manager: Optional[SpotifyOAuthManager] = None, market: Optional[str] = None):
        self.oauth_manager = oauth_manager or SpotifyOAuthManager()
        self.base_url = "https://api.spotify.com/v1"
        self.market = market or os.getenv("SPOTIFY_MARKET", "US")

        # CSV backup integration for rate limit fallback
        self.use_csv_fallback = os.getenv("SPOTIFY_CSV_BACKUP_ENABLED", "true").lower() == "true"
        self.csv_fallback_on_rate_limit = os.getenv("SPOTIFY_CSV_FALLBACK_ON_RATE_LIMIT", "true").lower() == "true"
        self.csv_fallback_on_error = os.getenv("SPOTIFY_CSV_FALLBACK_ON_ERROR", "true").lower() == "true"

        if CSV_BACKUP_AVAILABLE and self.use_csv_fallback:
            try:
                self.csv_backup = get_spotify_csv_backup()
                if self.csv_backup:
                    logger.info("CSV backup enabled for Spotify API fallback")
            except Exception as e:
                logger.warning(f"Failed to initialize CSV backup: {e}")
                self.csv_backup = None
        else:
            self.csv_backup = None
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        token = self.oauth_manager.get_valid_token()
        if not token:
            raise Exception("No valid Spotify token available")
            
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None,
                      use_csv_fallback: bool = True) -> Optional[Dict]:
        """Make API request with error handling, retry logic, and CSV fallback."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        for attempt in range(3):
            try:
                response = requests.request(
                    method, url, headers=headers, params=params, json=data, timeout=30
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - try CSV fallback if enabled
                    if self.csv_fallback_on_rate_limit and self.csv_backup and use_csv_fallback:
                        logger.info(f"Rate limited on {endpoint}, attempting CSV fallback")
                        csv_result = self._try_csv_fallback(endpoint, params)
                        if csv_result:
                            logger.info("CSV fallback successful")
                            return csv_result

                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited, waiting {retry_after} seconds")
                    time.sleep(retry_after)
                    continue
                elif response.status_code == 401:
                    # Token expired, try to refresh
                    logger.warning("Token expired, attempting refresh")
                    if self.oauth_manager._refresh_token():
                        headers = self._get_headers()
                        continue
                    else:
                        logger.error("Failed to refresh token")
                        # Try CSV fallback if enabled
                        if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                            logger.info(f"Token refresh failed, attempting CSV fallback for {endpoint}")
                            return self._try_csv_fallback(endpoint, params)
                        return None
                else:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    # Try CSV fallback on error if enabled
                    if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                        logger.info(f"API error, attempting CSV fallback for {endpoint}")
                        return self._try_csv_fallback(endpoint, params)
                    return None

            except Exception as e:
                logger.error(f"Request error (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                # Try CSV fallback on exception if enabled
                if self.csv_fallback_on_error and self.csv_backup and use_csv_fallback:
                    logger.info(f"Request exception, attempting CSV fallback for {endpoint}")
                    return self._try_csv_fallback(endpoint, params)
                return None

        return None

    def _try_csv_fallback(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Attempt to get data from CSV backup based on endpoint."""
        if not self.csv_backup:
            return None

        try:
            # Parse endpoint to determine what to fetch
            if endpoint.startswith("/tracks/"):
                # Extract track ID from endpoint
                track_id = endpoint.replace("/tracks/", "").split("?")[0]
                track = self.csv_backup.get_track_by_id(track_id)
                if track:
                    return self._csv_track_to_api_format(track)

            elif endpoint.startswith("/audio-features/"):
                # Extract track ID
                track_id = endpoint.replace("/audio-features/", "").split("?")[0]
                audio_features = self.csv_backup.get_audio_features(track_id)
                if audio_features:
                    return audio_features

            elif endpoint.startswith("/playlists/") and "/tracks" in endpoint:
                # Playlist tracks - limited support
                logger.debug("CSV fallback for playlist tracks has limited support")
                return None

            elif endpoint == "/me/playlists":
                # User playlists - return playlist names from CSV files
                playlist_names = self.csv_backup.get_playlist_names()
                playlists = []
                for name in playlist_names:
                    playlists.append({
                        "id": "",  # CSV doesn't have playlist IDs
                        "name": name,
                        "external_urls": {},
                        "tracks": {"total": 0}
                    })
                return {"items": playlists}

            elif endpoint == "/search":
                # Search - use CSV search
                query = params.get("q", "") if params else ""
                if query:
                    csv_tracks = self.csv_backup.search_tracks(query)
                    if csv_tracks:
                        limit = params.get("limit", 20) if params else 20
                        return {
                            "tracks": {
                                "items": [self._csv_track_to_api_format(t) for t in csv_tracks[:limit]]
                            }
                        }

        except Exception as e:
            logger.error(f"CSV fallback error: {e}")
            return None

        return None

    def _csv_track_to_api_format(self, csv_track: Dict[str, Any]) -> Dict[str, Any]:
        """Convert CSV track format to Spotify API response format."""
        # CSV track already matches API format (from spotify_csv_backup.py)
        # Just return as-is, but remove CSV-specific metadata
        api_track = csv_track.copy()
        api_track.pop("_csv_metadata", None)
        api_track.pop("audio_features", None)  # Audio features are separate endpoint
        return api_track
    
    def get_user_playlists(self, limit: int = 50, offset: int = 0,
                          use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
        """Get user's playlists with CSV fallback support."""
        params = {"limit": limit, "offset": offset, "market": self.market}
        data = self._make_request("GET", "/me/playlists", params=params,
                                  use_csv_fallback=use_csv_fallback)
        if data:
            return data.get("items", [])

        # Try CSV fallback if API failed
        if use_csv_fallback and self.csv_backup:
            logger.info("API failed for user playlists, trying CSV backup")
            playlist_names = self.csv_backup.get_playlist_names()
            playlists = []
            for name in playlist_names[offset:offset + limit]:
                playlists.append({
                    "id": "",  # CSV doesn't have playlist IDs
                    "name": name,
                    "external_urls": {},
                    "tracks": {"total": 0}
                })
            return playlists

        return []

    def get_playlist_tracks(self, playlist_id: str, limit: int = 100,
                           playlist_name: Optional[str] = None,
                           use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
        """Get tracks from a playlist with CSV fallback support.

        Args:
            playlist_id: Spotify playlist ID
            limit: Maximum number of tracks to return
            playlist_name: Optional playlist name for CSV fallback
            use_csv_fallback: Enable CSV fallback
        """
        tracks = []
        offset = 0

        while True:
            params = {
                "limit": min(limit, 100),
                "offset": offset,
                "market": self.market
            }

            data = self._make_request("GET", f"/playlists/{playlist_id}/tracks",
                                      params=params, use_csv_fallback=use_csv_fallback)
            if not data:
                # Try CSV fallback if API failed
                if use_csv_fallback and self.csv_backup and playlist_name:
                    logger.info(f"API failed for playlist {playlist_name}, trying CSV backup")
                    csv_tracks = self.csv_backup.get_playlist_tracks(playlist_name)
                    if csv_tracks:
                        return [{"track": self._csv_track_to_api_format(t)} for t in csv_tracks[:limit]]
                break

            items = data.get("items", [])
            if not items:
                break

            tracks.extend(items)
            offset += len(items)

            if len(items) < params["limit"]:
                break

        return tracks

    def get_playlist_info(self, playlist_id: str, use_csv_fallback: bool = True) -> Optional[Dict[str, Any]]:
        """Get playlist information."""
        return self._make_request("GET", f"/playlists/{playlist_id}",
                                  use_csv_fallback=use_csv_fallback)

    def get_track_info(self, track_id: str, use_csv_fallback: bool = True) -> Optional[Dict[str, Any]]:
        """Get detailed track information with CSV fallback support."""
        result = self._make_request("GET", f"/tracks/{track_id}",
                                    use_csv_fallback=use_csv_fallback)
        if result:
            return result

        # If API failed and CSV fallback wasn't already tried, try it now
        if use_csv_fallback and self.csv_backup:
            logger.info(f"API failed for track {track_id}, trying CSV backup")
            track = self.csv_backup.get_track_by_id(track_id)
            if track:
                return self._csv_track_to_api_format(track)

        return None

    def get_audio_features(self, track_id: str, use_csv_fallback: bool = True) -> Optional[Dict[str, Any]]:
        """Get audio features for a track with CSV fallback support."""
        result = self._make_request("GET", f"/audio-features/{track_id}",
                                    use_csv_fallback=use_csv_fallback)
        if result:
            return result

        # If API failed and CSV fallback wasn't already tried, try it now
        if use_csv_fallback and self.csv_backup:
            logger.info(f"API failed for audio features {track_id}, trying CSV backup")
            return self.csv_backup.get_audio_features(track_id)

        return None

    def search_tracks(self, query: str, limit: int = 20,
                     use_csv_fallback: bool = True) -> List[Dict[str, Any]]:
        """Search for tracks with CSV fallback support."""
        params = {
            "q": query,
            "type": "track",
            "limit": limit,
            "market": self.market
        }
        data = self._make_request("GET", "/search", params=params,
                                  use_csv_fallback=use_csv_fallback)
        if data:
            return data.get("tracks", {}).get("items", [])

        # Try CSV fallback if API failed
        if use_csv_fallback and self.csv_backup:
            logger.info(f"API failed for search '{query}', trying CSV backup")
            csv_tracks = self.csv_backup.search_tracks(query)
            if csv_tracks:
                return [self._csv_track_to_api_format(t) for t in csv_tracks[:limit]]

        return []

    def get_liked_songs_from_csv(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get liked songs directly from CSV backup (no API call).

        This is a CSV-first method for batch operations that need
        Liked Songs data without making API calls.
        """
        if not self.csv_backup:
            logger.warning("CSV backup not available for get_liked_songs_from_csv")
            return []

        tracks = self.csv_backup.get_liked_songs()
        if limit:
            tracks = tracks[:limit]

        # Convert to API format
        return [{"track": self._csv_track_to_api_format(t)} for t in tracks]

    def batch_get_track_metadata(self, track_ids: List[str],
                                 use_csv_first: bool = True) -> Dict[str, Dict[str, Any]]:
        """Batch get track metadata, using CSV first for performance.

        Args:
            track_ids: List of Spotify track IDs
            use_csv_first: If True, try CSV first before API

        Returns:
            Dict mapping track_id -> track metadata
        """
        results = {}
        api_needed = []

        if use_csv_first and self.csv_backup:
            # Try CSV first for all tracks
            for track_id in track_ids:
                track = self.csv_backup.get_track_by_id(track_id)
                if track:
                    results[track_id] = self._csv_track_to_api_format(track)
                else:
                    api_needed.append(track_id)
            logger.info(f"CSV provided {len(results)}/{len(track_ids)} tracks, {len(api_needed)} need API")
        else:
            api_needed = track_ids

        # Fetch remaining from API
        for track_id in api_needed:
            track = self.get_track_info(track_id, use_csv_fallback=False)
            if track:
                results[track_id] = track
            time.sleep(0.1)  # Rate limit protection

        return results

class NotionSpotifyIntegration:
    """Notion integration for Spotify data."""

    def __init__(self):
        # Use centralized token manager (MANDATORY per CLAUDE.md)
        try:
            from shared_core.notion.token_manager import get_notion_token
            self.notion_token = get_notion_token()
        except ImportError:
            # Fallback for backwards compatibility
            self.notion_token = os.getenv("NOTION_TOKEN")
        # Keep database IDs in their original format with hyphens
        self.tracks_db_id = os.getenv("TRACKS_DB_ID", "")
        self.playlists_db_id = os.getenv("PLAYLISTS_DB_ID", "")
        self.base_url = "https://api.notion.com/v1"
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Notion API requests."""
        return {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    
    def _make_notion_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make Notion API request with retry handling for rate limits and server errors."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        # Debug logging to understand the URL construction
        logger.info(f"Making Notion API request: {method} {url}")
        if data:
            logger.info(f"Request data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        for attempt in range(3):
            try:
                response = requests.request(method, url, headers=headers, json=data, timeout=30)
                if response.status_code in (200, 201):
                    return response.json()
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    logger.warning(
                        f"Notion rate limited request to {endpoint}; retrying in {retry_after}s (attempt {attempt + 1}/3)"
                    )
                    time.sleep(retry_after)
                    continue
                if response.status_code in (500, 502, 503, 504):
                    sleep_for = 2 ** attempt
                    logger.warning(
                        f"Notion transient error {response.status_code} on {endpoint}; retrying in {sleep_for}s"
                    )
                    time.sleep(sleep_for)
                    continue
                logger.error(f"Notion API error: {response.status_code} - {response.text}")
                return None
            except Exception as e:
                logger.error(f"Notion request error (attempt {attempt + 1}/3): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return None
        return None
    
    def create_track_page(self, track_data: Dict[str, Any], audio_features: Dict[str, Any] = None) -> Optional[str]:
        """Create a track page in Notion from a Spotify track object with comprehensive metadata."""
        artist_names = ", ".join([artist.get("name", "") for artist in track_data.get("artists", [])]) or "Unknown Artist"
        album_name = track_data.get("album", {}).get("name", "")
        album_id = track_data.get("album", {}).get("id", "")
        release_date = track_data.get("album", {}).get("release_date", "")
        isrc = track_data.get("external_ids", {}).get("isrc", "")
        preview_url = track_data.get("preview_url", "")
        
        # Build comprehensive properties
        properties = {
            "Title": {"title": [{"text": {"content": track_data.get("name", "Unknown Track")}}]},
            "Artist Name": {"rich_text": [{"text": {"content": artist_names}}]},
            "Spotify ID": {"rich_text": [{"text": {"content": track_data.get("id", "")}}]},
            "Spotify URL": {"url": track_data.get("external_urls", {}).get("spotify", "")},
            "Duration (ms)": {"number": track_data.get("duration_ms", 0)},
            "Popularity": {"number": track_data.get("popularity", 0)},
            "Explicit": {"checkbox": track_data.get("explicit", False)},
        }
        
        # Set DL=False for Spotify tracks so they can be processed for YouTube download
        # CRITICAL FIX: Always set DL=False for new Spotify tracks, even if property check fails
        # This ensures Spotify tracks are eligible for download processing
        # Try both property names (DL and Downloaded) - set both if both exist
        db_info = self._make_notion_request("GET", f"/databases/{self.tracks_db_id}")
        if db_info:
            db_props = db_info.get("properties", {})
            # Try "DL" property first
            if "DL" in db_props and db_props["DL"].get("type") == "checkbox":
                properties["DL"] = {"checkbox": False}
            # Also try "Downloaded" property (some databases use different name)
            if "Downloaded" in db_props and db_props["Downloaded"].get("type") == "checkbox":
                properties["Downloaded"] = {"checkbox": False}
        else:
            # Fallback: If database info retrieval fails, try setting both properties
            # Notion API will ignore properties that don't exist, so this is safe
            properties["DL"] = {"checkbox": False}
            properties["Downloaded"] = {"checkbox": False}
        
        # Add optional fields if they exist
        if album_name:
            properties["Album"] = {"rich_text": [{"text": {"content": album_name}}]}
        if release_date:
            try:
                # Parse release date and format for Notion
                from datetime import datetime
                if len(release_date) == 4:  # Year only
                    date_obj = datetime.strptime(release_date, "%Y")
                elif len(release_date) == 7:  # Year-Month
                    date_obj = datetime.strptime(release_date, "%Y-%m")
                else:  # Full date
                    date_obj = datetime.strptime(release_date, "%Y-%m-%d")
                properties["Release Date"] = {"date": {"start": date_obj.strftime("%Y-%m-%d")}}
            except:
                pass  # Skip if date parsing fails
        if isrc:
            properties["ISRC"] = {"rich_text": [{"text": {"content": isrc}}]}
        if preview_url:
            properties["Preview URL"] = {"url": preview_url}
            
        # Add audio features if available
        if audio_features:
            properties.update({
                "Danceability": {"number": audio_features.get("danceability", 0)},
                "Energy": {"number": audio_features.get("energy", 0)},
                "Key": {"select": {"name": str(audio_features.get("key", 0))}},
                "Loudness": {"number": audio_features.get("loudness", 0)},
                "Mode": {"select": {"name": "Major" if audio_features.get("mode", 0) == 1 else "Minor"}},
                "Speechiness": {"number": audio_features.get("speechiness", 0)},
                "Acousticness": {"number": audio_features.get("acousticness", 0)},
                "Instrumentalness": {"number": audio_features.get("instrumentalness", 0)},
                "Liveness": {"number": audio_features.get("liveness", 0)},
                "Valence": {"number": audio_features.get("valence", 0)},
                "Tempo": {"number": audio_features.get("tempo", 0)},
                "Time Signature": {"number": audio_features.get("time_signature", 0)},
            })
            
        payload = {"parent": {"database_id": self.tracks_db_id}, "properties": properties}
        result = self._make_notion_request("POST", "/pages", payload)
        return result.get("id") if result else None
    
    def create_playlist_page(self, playlist_data: Dict[str, Any]) -> Optional[str]:
        """Create a playlist page in Notion."""
        properties = {
            "Title": {
                "title": [{"text": {"content": playlist_data.get("name", "Unknown Playlist")}}]
            },
               "Spotify ID": {
                   "rich_text": [{"text": {"content": playlist_data.get("id", "")}}]
               },
            "Spotify URL": {
                "url": playlist_data.get("external_urls", {}).get("spotify", "")
            },
            "Track Count": {
                "number": playlist_data.get("tracks", {}).get("total", 0)
            },
            "Public": {
                "checkbox": playlist_data.get("public", False)
            },
            "Description": {
                "rich_text": [{"text": {"content": playlist_data.get("description", "")}}]
            }
        }
        
        payload = {
            "parent": {"database_id": self.playlists_db_id},
            "properties": properties
        }
        
        result = self._make_notion_request("POST", "/pages", payload)
        return result.get("id") if result else None
    
    def find_track_by_spotify_id(self, spotify_id: str) -> Optional[str]:
        """Find existing track by Spotify ID."""
        query = {
            "filter": {
                "property": "Spotify ID",
                "rich_text": {"equals": spotify_id}
            },
            "page_size": 1
        }
        
        result = self._make_notion_request("POST", f"/databases/{self.tracks_db_id}/query", query)
        if result and result.get("results"):
            return result["results"][0]["id"]
        return None

    def find_playlist_by_spotify_id(self, spotify_id: str) -> Optional[str]:
        """Find existing playlist by Spotify playlist ID."""
        if not spotify_id:
            return None
        query = {
            "filter": {
                "property": "Spotify ID",
                "rich_text": {"equals": spotify_id},
            },
            "page_size": 1,
        }
        result = self._make_notion_request("POST", f"/databases/{self.playlists_db_id}/query", query)
        if result and result.get("results"):
            return result["results"][0]["id"]
        return None

    def get_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a Notion page."""
        if not page_id:
            return None
        return self._make_notion_request("GET", f"/pages/{page_id}")

    def update_track_spotify_fields(self, page_id: str, track_data: Dict[str, Any], audio_features: Dict[str, Any] = None) -> bool:
        """Upsert Spotify-specific fields on an existing track page with comprehensive metadata.

        NOTE: djay Pro is the source of truth for Tempo and Key. Spotify values are only
        used as fallback when djay Pro data doesn't exist.
        """
        if not page_id:
            return False

        # Check if djay Pro data exists (source of truth for Tempo/Key)
        existing_page = self.get_page(page_id)
        existing_props = existing_page.get("properties", {}) if existing_page else {}
        has_djay_tempo = existing_props.get("Tempo", {}).get("number") is not None and existing_props.get("Tempo", {}).get("number", 0) > 0
        has_djay_key = bool(existing_props.get("Key ", {}).get("rich_text", []))
        has_djay_id = bool(existing_props.get("djay Pro ID", {}).get("rich_text", []))

        artist_names = ", ".join([artist.get("name", "") for artist in track_data.get("artists", [])]) or "Unknown Artist"
        album_name = track_data.get("album", {}).get("name", "")
        release_date = track_data.get("album", {}).get("release_date", "")
        isrc = track_data.get("external_ids", {}).get("isrc", "")
        preview_url = track_data.get("preview_url", "")

        properties: Dict[str, Any] = {
            "Artist Name": {"rich_text": [{"text": {"content": artist_names}}]},
            "Spotify ID": {"rich_text": [{"text": {"content": track_data.get("id", "")}}]},
            "Spotify URL": {"url": track_data.get("external_urls", {}).get("spotify", "")},
            "Duration (ms)": {"number": track_data.get("duration_ms", 0)},
            "Popularity": {"number": track_data.get("popularity", 0)},
            "Explicit": {"checkbox": track_data.get("explicit", False)},
        }

        # Add optional fields if they exist
        if album_name:
            properties["Album"] = {"rich_text": [{"text": {"content": album_name}}]}
        if release_date:
            try:
                # Parse release date and format for Notion
                from datetime import datetime
                if len(release_date) == 4:  # Year only
                    date_obj = datetime.strptime(release_date, "%Y")
                elif len(release_date) == 7:  # Year-Month
                    date_obj = datetime.strptime(release_date, "%Y-%m")
                else:  # Full date
                    date_obj = datetime.strptime(release_date, "%Y-%m-%d")
                properties["Release Date"] = {"date": {"start": date_obj.strftime("%Y-%m-%d")}}
            except:
                pass  # Skip if date parsing fails
        if isrc:
            properties["ISRC"] = {"rich_text": [{"text": {"content": isrc}}]}
        if preview_url:
            properties["Preview URL"] = {"url": preview_url}

        # Add audio features if available
        # NOTE: Skip Tempo/Key if djay Pro data exists (djay Pro is source of truth)
        if audio_features:
            audio_props = {
                "Danceability": {"number": audio_features.get("danceability", 0)},
                "Energy": {"number": audio_features.get("energy", 0)},
                "Loudness": {"number": audio_features.get("loudness", 0)},
                "Mode": {"select": {"name": "Major" if audio_features.get("mode", 0) == 1 else "Minor"}},
                "Speechiness": {"number": audio_features.get("speechiness", 0)},
                "Acousticness": {"number": audio_features.get("acousticness", 0)},
                "Instrumentalness": {"number": audio_features.get("instrumentalness", 0)},
                "Liveness": {"number": audio_features.get("liveness", 0)},
                "Valence": {"number": audio_features.get("valence", 0)},
                "Time Signature": {"number": audio_features.get("time_signature", 0)},
            }
            # Only add Tempo if no djay Pro tempo exists (djay Pro is source of truth)
            if not has_djay_tempo and not has_djay_id:
                audio_props["Tempo"] = {"number": audio_features.get("tempo", 0)}
            # Only add Key if no djay Pro key exists (djay Pro is source of truth)
            if not has_djay_key and not has_djay_id:
                audio_props["Key"] = {"select": {"name": str(audio_features.get("key", 0))}}
            properties.update(audio_props)
            
        result = self._make_notion_request("PATCH", f"/pages/{page_id}", {"properties": properties})
        return bool(result)

    def find_track_by_name_and_duration(self, name: str, duration_ms: int, window_ms: int = 2000) -> Optional[str]:
        """Search for a track by exact name and approximate duration."""
        if not name:
            return None
        query = {
            "filter": {
                "and": [
                    {"property": "Title", "rich_text": {"equals": name}},
                ]
            },
            "page_size": 10,
        }
        result = self._make_notion_request("POST", f"/databases/{self.tracks_db_id}/query", query)
        if not result:
            return None
        lower_bound = max(0, duration_ms - window_ms)
        upper_bound = duration_ms + window_ms
        for page in result.get("results", []):
            duration_value = (
                page.get("properties", {})
                .get("Duration (ms)", {})
                .get("number")
            )
            if isinstance(duration_value, (int, float)):
                duration_int = int(duration_value)
                if lower_bound <= duration_int <= upper_bound:
                    return page.get("id")
        return None

    def link_track_to_playlist(
        self,
        track_page_id: str,
        playlist_page_id: str,
        relation_prop: str = "Playlists",
    ) -> bool:
        """Link a track to a playlist using the configured relation property."""
        if not track_page_id or not playlist_page_id:
            return False
        page = self.get_page(track_page_id)
        if not page:
            return False
        relation_prop_data = page.get("properties", {}).get(relation_prop, {}) or {}
        existing_relations = relation_prop_data.get("relation", []) or []
        existing_ids: List[str] = []
        for rel in existing_relations:
            rel_id = rel.get("id")
            if rel_id and rel_id not in existing_ids:
                existing_ids.append(rel_id)
        if playlist_page_id in existing_ids:
            return True
        updated_relations = [{"id": rel_id} for rel_id in existing_ids]
        updated_relations.append({"id": playlist_page_id})
        payload = {
            "properties": {
                relation_prop: {
                    "relation": updated_relations
                }
            }
        }
        result = self._make_notion_request("PATCH", f"/pages/{track_page_id}", payload)
        return bool(result)

    def find_or_create_artist_page(self, artist_data: Dict[str, Any]) -> Optional[str]:
        """Find or create an artist page and return its ID."""
        if not artist_data or not artist_data.get("id"):
            return None
            
        # Get the Artists database ID from environment
        artists_db_id = os.getenv("ARTISTS_DB_ID", "")
        if not artists_db_id:
            logger.debug("ARTISTS_DB_ID not configured - skipping artist relation")
            return None
            
        # First, try to find existing artist by Spotify ID
        query = {
            "filter": {
                "property": "Spotify ID",
                "rich_text": {"equals": artist_data["id"]}
            },
            "page_size": 1
        }
        
        result = self._make_notion_request("POST", f"/databases/{artists_db_id}/query", query)
        if result and result.get("results"):
            return result["results"][0]["id"]
            
        # Create new artist page if not found
        artist_properties = {
            "Name": {"title": [{"text": {"content": artist_data.get("name", "Unknown Artist")}}]},
            "Spotify ID": {"rich_text": [{"text": {"content": artist_data.get("id", "")}}]},
            "Spotify URL": {"url": artist_data.get("external_urls", {}).get("spotify", "")},
            "Popularity": {"number": artist_data.get("popularity", 0)},
            "Genres": {"multi_select": [{"name": genre} for genre in artist_data.get("genres", [])]},
        }
        
        payload = {"parent": {"database_id": artists_db_id}, "properties": artist_properties}
        result = self._make_notion_request("POST", "/pages", payload)
        return result.get("id") if result else None

    def find_or_create_album_page(self, album_data: Dict[str, Any]) -> Optional[str]:
        """Find or create an album page and return its ID."""
        # For now, album information is stored directly in track records
        # No separate album database is configured
        logger.debug("Album information stored in track records - no separate database needed")
        return None

    def link_track_to_artist(self, track_page_id: str, artist_page_id: str) -> bool:
        """Link a track to an artist using the Artist relation property."""
        if not track_page_id or not artist_page_id:
            return False
        page = self.get_page(track_page_id)
        if not page:
            return False
        relation_prop_data = page.get("properties", {}).get("Artist", {}) or {}
        existing_relations = relation_prop_data.get("relation", []) or []
        existing_ids: List[str] = []
        for rel in existing_relations:
            rel_id = rel.get("id")
            if rel_id and rel_id not in existing_ids:
                existing_ids.append(rel_id)
        if artist_page_id in existing_ids:
            return True
        updated_relations = [{"id": rel_id} for rel_id in existing_ids]
        updated_relations.append({"id": artist_page_id})
        payload = {
            "properties": {
                "Artist": {
                    "relation": updated_relations
                }
            }
        }
        result = self._make_notion_request("PATCH", f"/pages/{track_page_id}", payload)
        return bool(result)

    def link_track_to_album(self, track_page_id: str, album_page_id: str) -> bool:
        """Link a track to an album using the Album relation property."""
        if not track_page_id or not album_page_id:
            return False
        page = self.get_page(track_page_id)
        if not page:
            return False
        relation_prop_data = page.get("properties", {}).get("Album", {}) or {}
        existing_relations = relation_prop_data.get("relation", []) or []
        existing_ids: List[str] = []
        for rel in existing_relations:
            rel_id = rel.get("id")
            if rel_id and rel_id not in existing_ids:
                existing_ids.append(rel_id)
        if album_page_id in existing_ids:
            return True
        updated_relations = [{"id": rel_id} for rel_id in existing_ids]
        updated_relations.append({"id": album_page_id})
        payload = {
            "properties": {
                "Album": {
                    "relation": updated_relations
                }
            }
        }
        result = self._make_notion_request("PATCH", f"/pages/{track_page_id}", payload)
        return bool(result)

class SpotifyNotionSync:
    """Main synchronization class."""
    
    def __init__(self):
        self.spotify = SpotifyAPI()
        self.notion = NotionSpotifyIntegration()
        
    def sync_playlist(self, playlist_id: str) -> Dict[str, Any]:
        """Sync a single playlist to Notion with idempotent playlist creation and track linking."""
        logger.info(f"Syncing playlist: {playlist_id}")

        playlist_info = self.spotify.get_playlist_info(playlist_id)
        if not playlist_info:
            logger.error(f"Failed to get playlist info for {playlist_id}")
            return {"success": False, "error": "Failed to get playlist info"}

        playlist_page_id = self.notion.find_playlist_by_spotify_id(playlist_info.get("id", ""))
        if not playlist_page_id:
            playlist_page_id = self.notion.create_playlist_page(playlist_info)
            if not playlist_page_id:
                logger.error(f"Failed to create playlist page for {playlist_id}")
                return {"success": False, "error": "Failed to create playlist page"}

        tracks = self.spotify.get_playlist_tracks(playlist_id)
        logger.info(f"Found {len(tracks)} tracks in playlist")

        processed = 0
        failures = 0
        for track_item in tracks:
            track = track_item.get("track") or {}
            if not track or not track.get("id"):
                continue
            try:
                # Get audio features for comprehensive metadata
                audio_features = self.spotify.get_audio_features(track["id"])
                
                track_page_id = self.notion.find_track_by_spotify_id(track["id"])
                if not track_page_id:
                    duration_ms = int(track.get("duration_ms") or 0)
                    track_page_id = self.notion.find_track_by_name_and_duration(
                        track.get("name", ""), duration_ms
                    )
                if not track_page_id:
                    track_page_id = self.notion.create_track_page(track, audio_features)

                if track_page_id:
                    self.notion.update_track_spotify_fields(track_page_id, track, audio_features)
                    self.notion.link_track_to_playlist(track_page_id, playlist_page_id)
                    
                    # Link to artist and album if available (only if databases are configured)
                    try:
                        artists = track.get("artists", [])
                        if artists:
                            for artist in artists:
                                artist_page_id = self.notion.find_or_create_artist_page(artist)
                                if artist_page_id:
                                    self.notion.link_track_to_artist(track_page_id, artist_page_id)
                    except Exception as e:
                        logger.debug(f"Artist relation failed (database not configured): {e}")
                    
                    try:
                        album_data = track.get("album", {})
                        if album_data:
                            album_page_id = self.notion.find_or_create_album_page(album_data)
                            if album_page_id:
                                self.notion.link_track_to_album(track_page_id, album_page_id)
                    except Exception as e:
                        logger.debug(f"Album relation failed (database not configured): {e}")
                    
                    processed += 1
                else:
                    failures += 1
                    logger.warning(f"Unable to create or locate Notion page for track {track.get('name')}")
            except Exception as exc:
                failures += 1
                logger.error(f"Failed to process track {track.get('name')}: {exc}")
                if failures >= 10:
                    logger.error("Stopping playlist sync after 10 failures to prevent cascading errors.")
                    break
            time.sleep(0.2)

        return {
            "success": failures == 0,
            "playlist_id": playlist_id,
            "playlist_name": playlist_info.get("name"),
            "total_tracks": len(tracks),
            "processed_tracks": processed,
            "failures": failures,
        }
    
    def sync_user_playlists(self, limit: int = 50) -> Dict[str, Any]:
        """Sync all user playlists."""
        logger.info("Starting user playlist sync")
        
        playlists = self.spotify.get_user_playlists(limit=limit)
        logger.info(f"Found {len(playlists)} playlists")
        
        results = []
        for playlist in playlists:
            playlist_id = playlist.get("id")
            if not playlist_id:
                continue
                
            result = self.sync_playlist(playlist_id)
            results.append(result)
            
            # Rate limiting
            time.sleep(1)
        
        successful = sum(1 for r in results if r.get("success"))
        total_failures = sum(r.get("failures", 0) for r in results)
        return {
            "success": total_failures == 0,
            "total_playlists": len(playlists),
            "successful_syncs": successful,
            "failures": total_failures,
            "results": results
        }

def main():
    """Main function for testing the integration."""
    logger.info("Starting Spotify-Notion integration test")
    
    try:
        # Initialize sync
        sync = SpotifyNotionSync()
        
        # Test with a single playlist (you can change this to a specific playlist ID)
        # For now, we'll sync all user playlists with a limit
        result = sync.sync_user_playlists(limit=5)  # Limit to 5 playlists for testing
        
        if result["success"]:
            logger.info(f"✅ Sync completed successfully!")
            logger.info(f"   Total playlists: {result['total_playlists']}")
            logger.info(f"   Successful syncs: {result['successful_syncs']}")
        else:
            logger.error("❌ Sync failed")
            
        return result
        
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    result = main()
    print(f"\n🎵 Spotify Integration Test Results:")
    print(f"   Success: {result.get('success', False)}")
    if result.get('error'):
        print(f"   Error: {result['error']}")
    if result.get('total_playlists') is not None:
        print(f"   Playlists processed: {result.get('total_playlists')}")
    if result.get('successful_syncs') is not None:
        print(f"   Successful syncs: {result.get('successful_syncs')}")
    if result.get('failures') is not None:
        print(f"   Failures: {result.get('failures')}")
