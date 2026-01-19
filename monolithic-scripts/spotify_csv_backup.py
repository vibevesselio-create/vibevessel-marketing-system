#!/usr/bin/env python3
"""
Spotify CSV Backup Reader Module
=================================

Reads and provides access to Spotify CSV backup files as a documented backup
data source for all Spotify API functions. Supports:
- Track lookup by ID, name, artist
- Playlist track retrieval
- Liked songs access
- Metadata caching for performance
- Fallback data source for API operations

Author: Cursor MM1 Agent • 2026-01-13
"""

import os
import csv
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from collections import defaultdict
from functools import lru_cache

# Import unified logging
try:
    from shared_core.logging import get_unified_logger
    UNIFIED_LOGGING_AVAILABLE = True
except (ImportError, ModuleNotFoundError, TimeoutError):
    UNIFIED_LOGGING_AVAILABLE = False
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if UNIFIED_LOGGING_AVAILABLE:
    logger = get_unified_logger(
        script_name="spotify-csv-backup",
        env=os.getenv("ENV", "PROD"),
        enable_notion=False
    )
else:
    logger = logging.getLogger(__name__)


class CSVTrackCache:
    """In-memory cache for CSV track data."""
    
    def __init__(self, ttl: int = 3600):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[str, float] = {}
        self.ttl = ttl
        self.index_by_id: Dict[str, Dict[str, Any]] = {}
        self.index_by_name_artist: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached track data."""
        if key not in self.cache:
            return None
        
        # Check TTL
        if time.time() - self.cache_timestamps[key] > self.ttl:
            del self.cache[key]
            del self.cache_timestamps[key]
            return None
        
        return self.cache[key]
    
    def set(self, key: str, value: Dict[str, Any]):
        """Cache track data."""
        self.cache[key] = value
        self.cache_timestamps[key] = time.time()
    
    def clear(self):
        """Clear all cached data."""
        self.cache.clear()
        self.cache_timestamps.clear()
        self.index_by_id.clear()
        self.index_by_name_artist.clear()
    
    def index_track(self, track: Dict[str, Any]):
        """Index track for fast lookup."""
        track_id = track.get("id")
        if track_id:
            self.index_by_id[track_id] = track
        
        # Index by name + artist
        name = track.get("name", "").lower()
        artist = track.get("artist", "").lower()
        if name and artist:
            key = f"{name}::{artist}"
            if track not in self.index_by_name_artist[key]:
                self.index_by_name_artist[key].append(track)


class SpotifyCSVBackup:
    """
    Reads and provides access to Spotify CSV backup files.
    
    Serves as documented backup data source for all Spotify API functions,
    alternative data source for compute-intensive operations, and secondary
    verification for metadata remediation.
    """
    
    def __init__(
        self,
        csv_base_path: Optional[str] = None,
        enable_cache: bool = True,
        cache_ttl: int = 3600
    ):
        """
        Initialize CSV backup reader.
        
        Args:
            csv_base_path: Base path to CSV files (defaults to env var or standard location)
            enable_cache: Enable in-memory caching
            cache_ttl: Cache TTL in seconds
        """
        self.csv_base_path = Path(
            csv_base_path or 
            os.getenv("SPOTIFY_CSV_BACKUP_PATH", "/Volumes/SYSTEM_SSD/Dropbox/Music/Spotify Library")
        )
        self.enable_cache = enable_cache
        self.cache = CSVTrackCache(ttl=cache_ttl) if enable_cache else None
        
        # File paths
        self.liked_songs_path = self.csv_base_path / "Liked_Songs.csv"
        self.playlists_dir = self.csv_base_path / "spotify_playlists"
        
        # Data storage
        self._tracks: List[Dict[str, Any]] = []
        self._playlist_index: Dict[str, str] = {}  # playlist_name -> csv_filename
        self._loaded = False
        
        logger.info(f"Spotify CSV Backup initialized: {self.csv_base_path}")
    
    def _normalize_track_id(self, track_uri: str) -> str:
        """Extract track ID from Spotify URI."""
        if not track_uri:
            return ""
        if track_uri.startswith("spotify:track:"):
            return track_uri.replace("spotify:track:", "")
        return track_uri
    
    def _parse_csv_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse CSV row into normalized track dictionary matching API response format.
        
        Converts CSV columns to API response structure for seamless integration.
        """
        track_uri = row.get("Track URI", "")
        track_id = self._normalize_track_id(track_uri)
        
        # Parse artist names (comma-separated)
        artist_names = row.get("Artist Name(s)", "")
        artists = [
            {"name": name.strip(), "id": "", "external_urls": {}}
            for name in artist_names.split(",") if name.strip()
        ] if artist_names else []
        
        # Parse genres (comma-separated)
        genres_str = row.get("Genres", "")
        genres = [g.strip() for g in genres_str.split(",") if g.strip()] if genres_str else []
        
        # Parse duration
        duration_ms = 0
        try:
            duration_ms = int(row.get("Duration (ms)", 0))
        except (ValueError, TypeError):
            pass
        
        # Parse popularity
        popularity = 0
        try:
            popularity = int(row.get("Popularity", 0))
        except (ValueError, TypeError):
            pass
        
        # Parse explicit flag
        explicit = row.get("Explicit", "").lower() in ("true", "1", "yes")
        
        # Parse audio features
        audio_features = {}
        try:
            audio_features = {
                "danceability": float(row.get("Danceability", 0)),
                "energy": float(row.get("Energy", 0)),
                "key": int(row.get("Key", 0)),
                "loudness": float(row.get("Loudness", 0)),
                "mode": int(row.get("Mode", 0)),
                "speechiness": float(row.get("Speechiness", 0)),
                "acousticness": float(row.get("Acousticness", 0)),
                "instrumentalness": float(row.get("Instrumentalness", 0)),
                "liveness": float(row.get("Liveness", 0)),
                "valence": float(row.get("Valence", 0)),
                "tempo": float(row.get("Tempo", 0)),
                "time_signature": int(row.get("Time Signature", 4)),
            }
        except (ValueError, TypeError):
            pass
        
        # Build track dictionary matching API response format
        track = {
            "id": track_id,
            "uri": track_uri,
            "name": row.get("Track Name", ""),
            "artists": artists,
            "album": {
                "id": "",
                "name": row.get("Album Name", ""),
                "release_date": row.get("Release Date", ""),
                "external_urls": {}
            },
            "duration_ms": duration_ms,
            "popularity": popularity,
            "explicit": explicit,
            "external_ids": {
                "isrc": ""
            },
            "external_urls": {
                "spotify": f"https://open.spotify.com/track/{track_id}" if track_id else ""
            },
            "preview_url": "",
            # CSV-specific metadata
            "_csv_metadata": {
                "added_by": row.get("Added By", ""),
                "added_at": row.get("Added At", ""),
                "genres": genres,
                "record_label": row.get("Record Label", ""),
            },
            # Audio features (embedded for convenience)
            "audio_features": audio_features,
        }
        
        return track
    
    def _load_csv_file(self, csv_path: Path) -> List[Dict[str, Any]]:
        """Load and parse a single CSV file."""
        if not csv_path.exists():
            logger.warning(f"CSV file not found: {csv_path}")
            return []
        
        tracks = []
        try:
            # Try UTF-8 first, fallback to UTF-8-BOM if needed
            encodings = ['utf-8-sig', 'utf-8', 'latin-1']
            csv_data = None
            
            for encoding in encodings:
                try:
                    with open(csv_path, 'r', encoding=encoding) as f:
                        csv_data = list(csv.DictReader(f))
                        break
                except UnicodeDecodeError:
                    continue
            
            if csv_data is None:
                logger.error(f"Failed to read CSV file (encoding issues): {csv_path}")
                return []

            if len(csv_data) == 0:
                logger.debug(f"CSV file is empty (headers only): {csv_path.name}")
                return []

            for row in csv_data:
                track = self._parse_csv_row(row)
                if track.get("id"):
                    tracks.append(track)
                    # Index track if caching enabled
                    if self.cache:
                        self.cache.index_track(track)

            logger.info(f"Loaded {len(tracks)} tracks from {csv_path.name}")
            
        except Exception as e:
            logger.error(f"Error loading CSV file {csv_path}: {e}")
            return []
        
        return tracks
    
    def load_all(self, force_reload: bool = False) -> int:
        """
        Load all CSV files into memory.
        
        Args:
            force_reload: Force reload even if already loaded
            
        Returns:
            Number of tracks loaded
        """
        if self._loaded and not force_reload:
            return len(self._tracks)
        
        logger.info("Loading all Spotify CSV backup files...")
        self._tracks = []
        self._playlist_index = {}
        
        # Clear cache if reloading
        if self.cache:
            self.cache.clear()
        
        # Load Liked Songs
        if self.liked_songs_path.exists():
            liked_tracks = self._load_csv_file(self.liked_songs_path)
            self._tracks.extend(liked_tracks)
            logger.info(f"Loaded {len(liked_tracks)} tracks from Liked_Songs.csv")
        
        # Load playlist CSVs
        if self.playlists_dir.exists():
            csv_files = list(self.playlists_dir.glob("*.csv"))
            logger.info(f"Found {len(csv_files)} playlist CSV files")
            
            for csv_file in csv_files:
                playlist_name = csv_file.stem  # Filename without extension
                playlist_tracks = self._load_csv_file(csv_file)
                self._tracks.extend(playlist_tracks)
                self._playlist_index[playlist_name] = str(csv_file)
        
        # Deduplicate tracks by ID (keep first occurrence)
        seen_ids: Set[str] = set()
        unique_tracks = []
        for track in self._tracks:
            track_id = track.get("id")
            if track_id and track_id not in seen_ids:
                seen_ids.add(track_id)
                unique_tracks.append(track)
        
        self._tracks = unique_tracks
        self._loaded = True
        
        logger.info(f"Loaded {len(self._tracks)} unique tracks from CSV backups")
        return len(self._tracks)
    
    def get_track_by_id(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        Get track by Spotify ID.
        
        Args:
            track_id: Spotify track ID (with or without 'spotify:track:' prefix)
            
        Returns:
            Track dictionary matching API response format, or None
        """
        # Normalize track ID
        track_id = self._normalize_track_id(track_id)
        if not track_id:
            return None
        
        # Check cache first
        if self.cache:
            cached = self.cache.index_by_id.get(track_id)
            if cached:
                return cached
        
        # Load if not already loaded
        if not self._loaded:
            self.load_all()
        
        # Search in loaded tracks
        for track in self._tracks:
            if track.get("id") == track_id:
                # Cache if enabled
                if self.cache:
                    self.cache.index_by_id[track_id] = track
                return track
        
        logger.debug(f"Track not found in CSV backup: {track_id}")
        return None
    
    def get_track_by_name_artist(
        self, 
        name: str, 
        artist: str, 
        fuzzy: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get tracks by name and artist.
        
        Args:
            name: Track name
            artist: Artist name
            fuzzy: Use fuzzy matching (partial match)
            
        Returns:
            List of matching tracks
        """
        if not name or not artist:
            return []
        
        name_lower = name.lower()
        artist_lower = artist.lower()
        
        # Load if not already loaded
        if not self._loaded:
            self.load_all()
        
        matches = []
        for track in self._tracks:
            track_name = track.get("name", "").lower()
            track_artists = [a.get("name", "").lower() for a in track.get("artists", [])]
            
            if fuzzy:
                # Fuzzy match: name contains search term and artist matches
                name_match = name_lower in track_name or track_name in name_lower
                artist_match = any(artist_lower in a or a in artist_lower for a in track_artists)
            else:
                # Exact match
                name_match = track_name == name_lower
                artist_match = artist_lower in track_artists
            
            if name_match and artist_match:
                matches.append(track)
        
        return matches
    
    def get_playlist_tracks(self, playlist_name: str) -> List[Dict[str, Any]]:
        """
        Get all tracks from a specific playlist CSV.
        
        Args:
            playlist_name: Playlist name (CSV filename without extension)
            
        Returns:
            List of tracks in the playlist
        """
        if not self.playlists_dir.exists():
            return []
        
        # Try exact filename match first
        csv_file = self.playlists_dir / f"{playlist_name}.csv"
        if csv_file.exists():
            return self._load_csv_file(csv_file)
        
        # Try case-insensitive match
        for csv_file in self.playlists_dir.glob("*.csv"):
            if csv_file.stem.lower() == playlist_name.lower():
                return self._load_csv_file(csv_file)
        
        logger.warning(f"Playlist CSV not found: {playlist_name}")
        return []
    
    def get_liked_songs(self) -> List[Dict[str, Any]]:
        """Get all tracks from Liked Songs CSV."""
        if not self.liked_songs_path.exists():
            logger.warning("Liked_Songs.csv not found")
            return []
        
        return self._load_csv_file(self.liked_songs_path)
    
    def get_all_tracks(self) -> List[Dict[str, Any]]:
        """
        Get all tracks from all CSV files (deduplicated).
        
        Returns:
            List of all unique tracks
        """
        if not self._loaded:
            self.load_all()
        
        return self._tracks.copy()
    
    def search_tracks(self, query: str) -> List[Dict[str, Any]]:
        """
        Search tracks by query string (searches name, artist, album).
        
        Args:
            query: Search query string
            
        Returns:
            List of matching tracks
        """
        if not query:
            return []
        
        query_lower = query.lower()
        
        # Load if not already loaded
        if not self._loaded:
            self.load_all()
        
        matches = []
        for track in self._tracks:
            # Search in name
            if query_lower in track.get("name", "").lower():
                matches.append(track)
                continue
            
            # Search in artist names
            for artist in track.get("artists", []):
                if query_lower in artist.get("name", "").lower():
                    matches.append(track)
                    break
            
            # Search in album name
            album_name = track.get("album", {}).get("name", "")
            if query_lower in album_name.lower():
                matches.append(track)
        
        return matches
    
    def get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        Get audio features for a track (from CSV).
        
        Args:
            track_id: Spotify track ID
            
        Returns:
            Audio features dictionary, or None
        """
        track = self.get_track_by_id(track_id)
        if track:
            return track.get("audio_features", {})
        return None
    
    def get_playlist_names(self) -> List[str]:
        """Get list of all playlist names (CSV filenames)."""
        if not self.playlists_dir.exists():
            return []
        
        return [f.stem for f in self.playlists_dir.glob("*.csv")]
    
    def refresh_cache(self):
        """Refresh the cache by reloading all CSV files."""
        logger.info("Refreshing CSV backup cache...")
        self.load_all(force_reload=True)


# Convenience function for easy import
def get_spotify_csv_backup() -> SpotifyCSVBackup:
    """Get a configured SpotifyCSVBackup instance."""
    return SpotifyCSVBackup(
        enable_cache=os.getenv("SPOTIFY_CSV_CACHE_ENABLED", "true").lower() == "true",
        cache_ttl=int(os.getenv("SPOTIFY_CSV_CACHE_TTL", "3600"))
    )


if __name__ == "__main__":
    # Test the CSV backup reader
    backup = SpotifyCSVBackup()
    
    print("Loading CSV backups...")
    track_count = backup.load_all()
    print(f"Loaded {track_count} tracks")
    
    print(f"\nFound {len(backup.get_playlist_names())} playlists")
    
    # Test track lookup
    if track_count > 0:
        first_track = backup.get_all_tracks()[0]
        track_id = first_track.get("id")
        print(f"\nTesting lookup for track ID: {track_id}")
        
        found_track = backup.get_track_by_id(track_id)
        if found_track:
            print(f"✅ Found: {found_track.get('name')} by {found_track.get('artists', [{}])[0].get('name', 'Unknown')}")
        else:
            print("❌ Track not found")
