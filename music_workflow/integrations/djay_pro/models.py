"""Data models for djay Pro export files."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class DjayTrack:
    """Track row from djay_library_tracks CSV."""
    track_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    duration_sec: Optional[float] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    source_type: str = "local"
    source_id: Optional[str] = None
    file_path: Optional[str] = None
    added_date: Optional[str] = None
    last_played: Optional[str] = None
    play_count: Optional[int] = None


@dataclass
class DjayStreamingTrack:
    """Streaming row from djay_library_streaming CSV."""
    track_id: str
    source_type: str
    source_track_id: str
    source_url: Optional[str] = None
    artist: str = ""
    title: str = ""
    duration_sec: Optional[float] = None
    is_available: bool = True


@dataclass
class DjaySession:
    """Session row from djay_session_history CSV."""
    session_id: str
    device_name: str = ""
    device_type: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: Optional[float] = None
    track_count: Optional[int] = None


@dataclass
class DjaySessionTrack:
    """Session play row from djay_session_tracks CSV."""
    play_id: str
    session_id: str
    track_id: str
    deck_number: Optional[int] = None
    play_start: Optional[str] = None
    title: str = ""
    artist: str = ""
    bpm: Optional[float] = None


@dataclass
class DjayPlaylistEntry:
    """Playlist membership row from djay_playlists CSV."""
    playlist_id: str
    playlist_name: str
    track_id: str
    position: Optional[int] = None
    added_date: Optional[str] = None


@dataclass
class DjayExport:
    """Container for a complete djay Pro export."""
    tracks: List[DjayTrack] = field(default_factory=list)
    streaming_tracks: List[DjayStreamingTrack] = field(default_factory=list)
    sessions: List[DjaySession] = field(default_factory=list)
    session_tracks: List[DjaySessionTrack] = field(default_factory=list)
    playlists: List[DjayPlaylistEntry] = field(default_factory=list)

    def track_index(self) -> Dict[str, DjayTrack]:
        """Build a lookup of track_id -> DjayTrack."""
        return {track.track_id: track for track in self.tracks if track.track_id}

    def streaming_index(self) -> Dict[str, DjayStreamingTrack]:
        """Build a lookup of track_id -> DjayStreamingTrack."""
        return {
            track.track_id: track
            for track in self.streaming_tracks
            if track.track_id
        }
