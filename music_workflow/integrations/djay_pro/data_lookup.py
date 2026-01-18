"""Fast lookup service for djay Pro analysis data.

Provides in-memory indexes for quick lookups by various identifiers:
- Spotify ID
- SoundCloud URL
- Title + Artist (fuzzy)
- titleID hash

Used by processor and deduplication modules to:
- Skip audio analysis for pre-analyzed tracks
- Add titleID to deduplication cascade
- Cross-reference streaming sources
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from music_workflow.integrations.djay_pro.models import DjayTrack, DjayStreamingTrack
from music_workflow.integrations.djay_pro.export_loader import load_djay_export


# Camelot notation mapping for key normalization
KEY_TO_CAMELOT = {
    "C": "8B", "Cm": "5A", "C#": "3B", "C#m": "12A", "Db": "3B", "Dbm": "12A",
    "D": "10B", "Dm": "7A", "D#": "5B", "D#m": "2A", "Eb": "5B", "Ebm": "2A",
    "E": "12B", "Em": "9A",
    "F": "7B", "Fm": "4A", "F#": "2B", "F#m": "11A", "Gb": "2B", "Gbm": "11A",
    "G": "9B", "Gm": "6A", "G#": "4B", "G#m": "1A", "Ab": "4B", "Abm": "1A",
    "A": "11B", "Am": "8A", "A#": "6B", "A#m": "3A", "Bb": "6B", "Bbm": "3A",
    "B": "1B", "Bm": "10A",
}


@dataclass
class DjayLookupResult:
    """Result from djay Pro data lookup."""
    track_id: str
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    match_type: str = "unknown"
    match_confidence: float = 0.0


class DjayProDataLookup:
    """Fast lookup service for djay Pro library data.

    Maintains in-memory indexes for quick lookups:
    - spotify_index: Spotify ID -> DjayTrack
    - soundcloud_index: SoundCloud URL -> DjayStreamingTrack
    - title_artist_index: normalized(title+artist) -> List[DjayTrack]
    - titleid_index: titleID hash -> DjayTrack
    """

    def __init__(self, export_dir: Optional[Path] = None):
        """Initialize the lookup service.

        Args:
            export_dir: Path to djay Pro export directory. If None,
                        uses default location.
        """
        self._export_dir = export_dir
        self._tracks: List[DjayTrack] = []
        self._streaming: List[DjayStreamingTrack] = []

        # Indexes built on first use
        self._spotify_index: Optional[Dict[str, DjayTrack]] = None
        self._soundcloud_index: Optional[Dict[str, DjayStreamingTrack]] = None
        self._title_artist_index: Optional[Dict[str, List[DjayTrack]]] = None
        self._titleid_index: Optional[Dict[str, DjayTrack]] = None
        self._source_id_index: Optional[Dict[str, DjayTrack]] = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load export data if not already loaded."""
        if self._loaded:
            return

        if self._export_dir is None:
            # Try default locations
            candidates = [
                Path("djay_pro_export"),
                Path.home() / "djay_pro_export",
                Path("/Users/brianhellemn/Projects/github-production/djay_pro_export"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    self._export_dir = candidate
                    break

        if self._export_dir and self._export_dir.exists():
            try:
                export = load_djay_export(self._export_dir, require_tracks=False)
                self._tracks = export.tracks
                self._streaming = export.streaming_tracks
            except FileNotFoundError:
                pass

        self._loaded = True

    def _build_spotify_index(self) -> Dict[str, DjayTrack]:
        """Build index of Spotify ID -> DjayTrack."""
        self._ensure_loaded()
        if self._spotify_index is None:
            self._spotify_index = {}
            for track in self._tracks:
                if track.source_type and track.source_type.lower() == "spotify" and track.source_id:
                    self._spotify_index[track.source_id] = track
        return self._spotify_index

    def _build_soundcloud_index(self) -> Dict[str, DjayStreamingTrack]:
        """Build index of SoundCloud URL -> DjayStreamingTrack."""
        self._ensure_loaded()
        if self._soundcloud_index is None:
            self._soundcloud_index = {}
            for stream in self._streaming:
                if stream.source_type and stream.source_type.lower() == "soundcloud" and stream.source_url:
                    # Normalize URL (remove trailing slashes, etc)
                    url = stream.source_url.rstrip("/").lower()
                    self._soundcloud_index[url] = stream
        return self._soundcloud_index

    def _build_title_artist_index(self) -> Dict[str, List[DjayTrack]]:
        """Build index of normalized title+artist -> List[DjayTrack]."""
        self._ensure_loaded()
        if self._title_artist_index is None:
            self._title_artist_index = {}
            for track in self._tracks:
                key = self._normalize_title_artist(track.title, track.artist)
                if key:
                    if key not in self._title_artist_index:
                        self._title_artist_index[key] = []
                    self._title_artist_index[key].append(track)
        return self._title_artist_index

    def _build_titleid_index(self) -> Dict[str, DjayTrack]:
        """Build index of titleID hash -> DjayTrack."""
        self._ensure_loaded()
        if self._titleid_index is None:
            self._titleid_index = {}
            for track in self._tracks:
                # Calculate titleID from title + artist
                titleid = self._calculate_titleid(track.title, track.artist)
                if titleid:
                    self._titleid_index[titleid] = track
        return self._titleid_index

    def _build_source_id_index(self) -> Dict[str, DjayTrack]:
        """Build index of source_id -> DjayTrack."""
        self._ensure_loaded()
        if self._source_id_index is None:
            self._source_id_index = {}
            for track in self._tracks:
                if track.source_id:
                    self._source_id_index[track.source_id] = track
        return self._source_id_index

    @staticmethod
    def _normalize_title_artist(title: str, artist: str) -> str:
        """Normalize title + artist for fuzzy matching."""
        combined = f"{title or ''} {artist or ''}".lower()
        # Keep only alphanumeric and spaces
        return "".join(ch for ch in combined if ch.isalnum() or ch.isspace()).strip()

    @staticmethod
    def _calculate_titleid(title: str, artist: str) -> Optional[str]:
        """Calculate titleID hash matching djay Pro's algorithm.

        djay Pro uses a 32-character hash based on title + artist.
        """
        if not title:
            return None

        # Normalize: lowercase, remove non-alphanumeric
        normalized = f"{title or ''}{artist or ''}".lower()
        normalized = "".join(ch for ch in normalized if ch.isalnum())

        if not normalized:
            return None

        # djay Pro uses MD5 for titleID
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def lookup_by_spotify_id(self, spotify_id: str) -> Optional[DjayLookupResult]:
        """Look up a track by Spotify ID."""
        index = self._build_spotify_index()
        track = index.get(spotify_id)
        if track:
            return DjayLookupResult(
                track_id=track.track_id,
                bpm=track.bpm,
                key=track.key,
                key_camelot=track.key_camelot,
                title=track.title,
                artist=track.artist,
                source_type="spotify",
                source_id=spotify_id,
                match_type="spotify_id",
                match_confidence=1.0,
            )
        return None

    def lookup_by_soundcloud_url(self, url: str) -> Optional[DjayLookupResult]:
        """Look up a track by SoundCloud URL."""
        index = self._build_soundcloud_index()
        normalized_url = url.rstrip("/").lower()
        stream = index.get(normalized_url)
        if stream:
            # Try to get analysis data from main tracks
            source_index = self._build_source_id_index()
            track = source_index.get(stream.source_track_id)

            return DjayLookupResult(
                track_id=stream.track_id,
                bpm=track.bpm if track else None,
                key=track.key if track else None,
                key_camelot=track.key_camelot if track else None,
                title=stream.title or (track.title if track else None),
                artist=stream.artist or (track.artist if track else None),
                source_type="soundcloud",
                source_url=url,
                match_type="soundcloud_url",
                match_confidence=1.0,
            )
        return None

    def lookup_by_titleid(self, titleid: str) -> Optional[DjayLookupResult]:
        """Look up a track by titleID hash."""
        index = self._build_titleid_index()
        track = index.get(titleid)
        if track:
            return DjayLookupResult(
                track_id=track.track_id,
                bpm=track.bpm,
                key=track.key,
                key_camelot=track.key_camelot,
                title=track.title,
                artist=track.artist,
                source_type=track.source_type,
                source_id=track.source_id,
                match_type="titleid",
                match_confidence=1.0,
            )
        return None

    def lookup_by_title_artist(
        self,
        title: str,
        artist: str,
        threshold: float = 0.85,
    ) -> Optional[DjayLookupResult]:
        """Look up a track by title + artist with fuzzy matching.

        Args:
            title: Track title
            artist: Artist name
            threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            Best matching result or None if no match above threshold
        """
        # First try exact titleID match
        titleid = self._calculate_titleid(title, artist)
        if titleid:
            result = self.lookup_by_titleid(titleid)
            if result:
                return result

        # Fall back to fuzzy matching
        index = self._build_title_artist_index()
        query_key = self._normalize_title_artist(title, artist)

        if not query_key:
            return None

        best_match: Optional[DjayTrack] = None
        best_score = 0.0

        for key, tracks in index.items():
            # Calculate similarity
            score = SequenceMatcher(None, query_key, key).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = tracks[0]  # Take first if multiple

        if best_match:
            return DjayLookupResult(
                track_id=best_match.track_id,
                bpm=best_match.bpm,
                key=best_match.key,
                key_camelot=best_match.key_camelot,
                title=best_match.title,
                artist=best_match.artist,
                source_type=best_match.source_type,
                source_id=best_match.source_id,
                match_type="fuzzy",
                match_confidence=best_score,
            )

        return None

    def lookup(
        self,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        spotify_id: Optional[str] = None,
        soundcloud_url: Optional[str] = None,
        titleid: Optional[str] = None,
        fuzzy_threshold: float = 0.85,
    ) -> Optional[DjayLookupResult]:
        """Look up a track using multiple identifiers.

        Tries identifiers in order of specificity:
        1. Spotify ID (exact)
        2. SoundCloud URL (exact)
        3. titleID hash (exact)
        4. Title + Artist (fuzzy)

        Returns the first match found.
        """
        # Try exact matches first
        if spotify_id:
            result = self.lookup_by_spotify_id(spotify_id)
            if result:
                return result

        if soundcloud_url:
            result = self.lookup_by_soundcloud_url(soundcloud_url)
            if result:
                return result

        if titleid:
            result = self.lookup_by_titleid(titleid)
            if result:
                return result

        # Fall back to fuzzy title+artist
        if title:
            result = self.lookup_by_title_artist(title, artist or "", fuzzy_threshold)
            if result:
                return result

        return None

    def has_analysis_data(
        self,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        spotify_id: Optional[str] = None,
        soundcloud_url: Optional[str] = None,
    ) -> Tuple[bool, Optional[DjayLookupResult]]:
        """Check if djay Pro has BPM/key analysis for a track.

        Returns:
            Tuple of (has_data, lookup_result)
        """
        result = self.lookup(
            title=title,
            artist=artist,
            spotify_id=spotify_id,
            soundcloud_url=soundcloud_url,
        )

        if result and (result.bpm or result.key):
            return True, result

        return False, None

    def get_analysis_stats(self) -> Dict[str, int]:
        """Get statistics about available analysis data."""
        self._ensure_loaded()

        return {
            "total_tracks": len(self._tracks),
            "with_bpm": sum(1 for t in self._tracks if t.bpm),
            "with_key": sum(1 for t in self._tracks if t.key),
            "with_both": sum(1 for t in self._tracks if t.bpm and t.key),
            "spotify_tracks": sum(1 for t in self._tracks if t.source_type and t.source_type.lower() == "spotify"),
            "streaming_tracks": len(self._streaming),
        }


# Module-level singleton for efficiency
_lookup_instance: Optional[DjayProDataLookup] = None


def get_djay_lookup(export_dir: Optional[Path] = None) -> DjayProDataLookup:
    """Get or create the djay Pro data lookup singleton."""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = DjayProDataLookup(export_dir)
    return _lookup_instance
