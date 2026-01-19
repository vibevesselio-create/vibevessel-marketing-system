"""Data models for Apple Music library integration.

These dataclasses mirror the structure used in djay Pro and Rekordbox
integrations, enabling unified handling of DJ library data across platforms.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class AppleMusicTrack:
    """Track from Apple Music library.

    Attributes map to AppleScript properties available via the Music app.
    All writable properties can be updated via AppleScript.

    Attributes:
        persistent_id: Unique Apple Music ID (16-char hex string)
        database_id: Local database ID (integer)
        name: Track title
        artist: Artist name
        album: Album name
        album_artist: Album artist (may differ from track artist)
        composer: Composer name
        genre: Genre classification
        grouping: User-defined grouping
        comment: User comments (often used for source URLs)
        bpm: Beats per minute (writable)
        duration: Track duration in seconds
        location: POSIX file path to audio file
        kind: File type description (e.g., "AIFF audio file")
        bit_rate: Audio bitrate in kbps
        sample_rate: Sample rate in Hz
        size: File size in bytes
        date_added: When track was added to library
        date_modified: Last modification time
        played_count: Number of times played (writable)
        skipped_count: Number of times skipped
        rating: Rating 0-100 (Apple's scale, 20 = 1 star)
        track_number: Track number on album
        disc_number: Disc number
        year: Release year
        enabled: Whether track is enabled for playback
        compilation: Part of a compilation album
        favorited: User favorited
    """
    # Identifiers
    persistent_id: str
    database_id: int

    # Basic metadata
    name: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    composer: str = ""
    genre: str = ""
    grouping: str = ""
    comment: str = ""

    # Musical properties
    bpm: Optional[int] = None
    duration: float = 0.0  # seconds

    # File information
    location: Optional[str] = None  # POSIX file path
    kind: str = ""  # e.g., "AIFF audio file", "MPEG audio file"
    bit_rate: int = 0  # kbps
    sample_rate: int = 0  # Hz
    size: int = 0  # bytes

    # Timestamps
    date_added: Optional[datetime] = None
    date_modified: Optional[datetime] = None

    # Playback statistics
    played_count: int = 0
    skipped_count: int = 0
    rating: int = 0  # 0-100 (20 per star)

    # Track numbers
    track_number: int = 0
    track_count: int = 0
    disc_number: int = 0
    disc_count: int = 0
    year: int = 0

    # Flags
    enabled: bool = True
    compilation: bool = False
    favorited: bool = False
    disliked: bool = False

    # Cross-platform sync tracking
    notion_page_id: Optional[str] = None
    djay_pro_id: Optional[str] = None
    rekordbox_id: Optional[int] = None
    sync_status: str = "pending"  # pending, synced, conflict, error

    @property
    def rating_stars(self) -> int:
        """Convert Apple's 0-100 rating to 0-5 stars."""
        return self.rating // 20

    @rating_stars.setter
    def rating_stars(self, stars: int):
        """Set rating from 0-5 stars."""
        self.rating = min(100, max(0, stars * 20))

    @property
    def duration_formatted(self) -> str:
        """Get duration as MM:SS string."""
        minutes = int(self.duration // 60)
        seconds = int(self.duration % 60)
        return f"{minutes}:{seconds:02d}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "persistent_id": self.persistent_id,
            "database_id": self.database_id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "composer": self.composer,
            "genre": self.genre,
            "grouping": self.grouping,
            "comment": self.comment,
            "bpm": self.bpm,
            "duration": self.duration,
            "duration_formatted": self.duration_formatted,
            "location": self.location,
            "kind": self.kind,
            "bit_rate": self.bit_rate,
            "sample_rate": self.sample_rate,
            "size": self.size,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "date_modified": self.date_modified.isoformat() if self.date_modified else None,
            "played_count": self.played_count,
            "skipped_count": self.skipped_count,
            "rating": self.rating,
            "rating_stars": self.rating_stars,
            "track_number": self.track_number,
            "year": self.year,
            "favorited": self.favorited,
            "sync_status": self.sync_status,
        }

    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to flat dictionary for CSV export."""
        return {
            "persistent_id": self.persistent_id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "bpm": self.bpm or "",
            "duration": self.duration,
            "location": self.location or "",
            "bit_rate": self.bit_rate,
            "sample_rate": self.sample_rate,
            "played_count": self.played_count,
            "rating_stars": self.rating_stars,
            "year": self.year,
            "date_added": self.date_added.isoformat() if self.date_added else "",
        }


@dataclass
class AppleMusicPlaylist:
    """Playlist from Apple Music library.

    Apple Music supports both regular playlists and smart playlists
    (rule-based). Smart playlist rules cannot be read via AppleScript.

    Attributes:
        playlist_id: Persistent ID (hex string)
        name: Playlist name
        parent_id: Parent folder ID (for nested playlists)
        is_folder: Whether this is a folder containing playlists
        is_smart: Whether this is a smart (rule-based) playlist
        track_ids: List of track persistent IDs in this playlist
        description: Playlist description
        duration: Total duration in seconds
        track_count: Number of tracks
    """
    playlist_id: str
    name: str
    parent_id: Optional[str] = None
    is_folder: bool = False
    is_smart: bool = False
    track_ids: List[str] = field(default_factory=list)
    description: str = ""
    duration: float = 0.0
    track_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playlist_id": self.playlist_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "is_folder": self.is_folder,
            "is_smart": self.is_smart,
            "track_count": len(self.track_ids) if self.track_ids else self.track_count,
            "duration": self.duration,
        }


@dataclass
class AppleMusicLibrary:
    """Container for Apple Music library export.

    Holds all tracks and playlists from an Apple Music library,
    with convenience methods for lookups and statistics.

    Attributes:
        tracks: Dictionary mapping persistent_id to AppleMusicTrack
        playlists: List of all playlists
        total_tracks: Count of tracks
        tracks_with_bpm: Count of tracks with BPM data
        tracks_with_location: Count of tracks with valid file paths
        total_duration: Total library duration in seconds
    """
    tracks: Dict[str, AppleMusicTrack] = field(default_factory=dict)
    playlists: List[AppleMusicPlaylist] = field(default_factory=list)

    # Statistics
    total_tracks: int = 0
    tracks_with_bpm: int = 0
    tracks_with_location: int = 0
    total_duration: float = 0.0

    def track_by_id(self, persistent_id: str) -> Optional[AppleMusicTrack]:
        """Find track by persistent ID."""
        return self.tracks.get(persistent_id)

    def track_by_path(self, path: str) -> Optional[AppleMusicTrack]:
        """Find track by file path (case-insensitive)."""
        path_lower = path.lower()
        for track in self.tracks.values():
            if track.location and track.location.lower() == path_lower:
                return track
        return None

    def tracks_by_artist(self, artist: str) -> List[AppleMusicTrack]:
        """Find all tracks by artist (case-insensitive)."""
        artist_lower = artist.lower()
        return [
            t for t in self.tracks.values()
            if artist_lower in t.artist.lower()
        ]

    def tracks_by_genre(self, genre: str) -> List[AppleMusicTrack]:
        """Find all tracks by genre (case-insensitive)."""
        genre_lower = genre.lower()
        return [
            t for t in self.tracks.values()
            if t.genre and genre_lower in t.genre.lower()
        ]

    def tracks_in_bpm_range(
        self, min_bpm: int, max_bpm: int
    ) -> List[AppleMusicTrack]:
        """Find tracks within BPM range."""
        return [
            t for t in self.tracks.values()
            if t.bpm and min_bpm <= t.bpm <= max_bpm
        ]

    def playlist_by_name(self, name: str) -> Optional[AppleMusicPlaylist]:
        """Find playlist by name (case-insensitive)."""
        name_lower = name.lower()
        for playlist in self.playlists:
            if playlist.name.lower() == name_lower:
                return playlist
        return None

    def get_genres(self) -> List[str]:
        """Get list of unique genres."""
        genres = set()
        for track in self.tracks.values():
            if track.genre:
                genres.add(track.genre)
        return sorted(genres)

    def get_artists(self) -> List[str]:
        """Get list of unique artists."""
        artists = set()
        for track in self.tracks.values():
            if track.artist:
                artists.add(track.artist)
        return sorted(artists)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        genres = self.get_genres()
        artists = self.get_artists()

        return {
            "total_tracks": self.total_tracks,
            "tracks_with_bpm": self.tracks_with_bpm,
            "tracks_with_location": self.tracks_with_location,
            "total_playlists": len(self.playlists),
            "user_playlists": len([p for p in self.playlists if not p.is_folder]),
            "playlist_folders": len([p for p in self.playlists if p.is_folder]),
            "smart_playlists": len([p for p in self.playlists if p.is_smart]),
            "unique_genres": len(genres),
            "unique_artists": len(artists),
            "total_duration_hours": round(self.total_duration / 3600, 1),
            "bpm_coverage": (
                f"{100 * self.tracks_with_bpm / self.total_tracks:.1f}%"
                if self.total_tracks > 0 else "0%"
            ),
        }
