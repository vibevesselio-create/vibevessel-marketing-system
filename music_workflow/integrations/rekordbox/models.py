"""Data models for Rekordbox library integration.

These dataclasses mirror the structure used in the djay Pro integration,
enabling unified handling of DJ library data across platforms.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class RekordboxCue:
    """Cue point from Rekordbox track analysis.

    Rekordbox stores cue points in .DAT/.EXT analysis files alongside
    the main database. Each track can have up to 10 memory cues and
    8 hot cues (A-H).

    Attributes:
        cue_id: Internal cue identifier
        cue_type: Type of cue - "cue", "loop", or "memory"
        hot_cue: Hot cue number (1-8) if assigned, None for memory cues
        time_ms: Position in track in milliseconds
        loop_time_ms: Loop end position for loop cues
        color_id: Rekordbox color code (0-16)
        color_rgb: RGB hex color (e.g., "#FF0000")
        name: User-assigned cue name
    """
    cue_id: int
    cue_type: str = "cue"  # cue, loop, memory
    hot_cue: Optional[int] = None
    time_ms: int = 0
    loop_time_ms: Optional[int] = None
    color_id: Optional[int] = None
    color_rgb: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "cue_type": self.cue_type,
            "hot_cue": self.hot_cue,
            "time_ms": self.time_ms,
            "loop_time_ms": self.loop_time_ms,
            "color_id": self.color_id,
            "color_rgb": self.color_rgb,
            "name": self.name,
        }


@dataclass
class RekordboxBeatgrid:
    """Beatgrid data from Rekordbox analysis.

    Rekordbox analyzes tracks to create beat grids that can be static
    (single BPM) or dynamic (tempo changes throughout track).

    Attributes:
        bpm: Primary BPM value
        offset_ms: Beat grid start offset in milliseconds
        tempo_changes: List of tempo change points for dynamic grids
        is_dynamic: Whether grid has tempo changes
    """
    bpm: float
    offset_ms: int = 0
    tempo_changes: List[Dict] = field(default_factory=list)
    is_dynamic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bpm": self.bpm,
            "offset_ms": self.offset_ms,
            "tempo_changes": self.tempo_changes,
            "is_dynamic": self.is_dynamic,
        }


@dataclass
class RekordboxTrack:
    """Track from Rekordbox library.

    Comprehensive track model that maps to Rekordbox's djmdContent table
    and associated analysis files. Includes both metadata from the database
    and performance data from .DAT/.EXT files.

    Attributes:
        track_id: Rekordbox internal content ID
        content_id: UUID string identifier
        title: Track title
        artist: Artist name
        album: Album name
        genre: Genre classification
        composer: Composer name
        remixer: Remixer name
        label: Record label
        comment: User comments
        file_path: Full path to audio file
        duration_sec: Track duration in seconds
        bitrate: Audio bitrate in kbps
        sample_rate: Sample rate in Hz
        file_size: File size in bytes
        file_type: File extension/type
        bpm: Beats per minute (may differ from analysis)
        key: Musical key (e.g., "Am", "C")
        key_camelot: Camelot notation (e.g., "8A", "8B")
        rating: Star rating (0-5)
        analysis_path: Path to .DAT/.EXT analysis file
        cues: List of cue points
        beatgrid: Beat grid data
        waveform_overview: Overview waveform data
        date_added: When track was added to library
        date_modified: Last modification time
        last_played: Last play timestamp
        play_count: Number of times played
        notion_page_id: Linked Notion page ID (for sync)
        djay_pro_id: Linked djay Pro titleID (for cross-platform sync)
        sync_status: Current sync state
    """
    # Identifiers
    track_id: int
    content_id: Optional[str] = None

    # Basic metadata
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    composer: str = ""
    remixer: str = ""
    label: str = ""
    comment: str = ""

    # File information
    file_path: str = ""
    duration_sec: float = 0.0
    bitrate: int = 0
    sample_rate: int = 0
    file_size: int = 0
    file_type: str = ""

    # Musical properties
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    rating: int = 0

    # Analysis data
    analysis_path: Optional[str] = None
    cues: List[RekordboxCue] = field(default_factory=list)
    beatgrid: Optional[RekordboxBeatgrid] = None
    waveform_overview: Optional[bytes] = None

    # Timestamps
    date_added: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    last_played: Optional[datetime] = None
    play_count: int = 0

    # Cross-platform sync tracking
    notion_page_id: Optional[str] = None
    djay_pro_id: Optional[str] = None
    sync_status: str = "pending"  # pending, synced, conflict, error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "track_id": self.track_id,
            "content_id": self.content_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "composer": self.composer,
            "remixer": self.remixer,
            "label": self.label,
            "comment": self.comment,
            "file_path": self.file_path,
            "duration_sec": self.duration_sec,
            "bitrate": self.bitrate,
            "sample_rate": self.sample_rate,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "bpm": self.bpm,
            "key": self.key,
            "key_camelot": self.key_camelot,
            "rating": self.rating,
            "play_count": self.play_count,
            "cue_count": len(self.cues),
            "has_beatgrid": self.beatgrid is not None,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "last_played": self.last_played.isoformat() if self.last_played else None,
            "sync_status": self.sync_status,
        }

    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to flat dictionary for CSV export."""
        return {
            "track_id": self.track_id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "genre": self.genre,
            "bpm": self.bpm,
            "key": self.key,
            "key_camelot": self.key_camelot,
            "rating": self.rating,
            "duration_sec": self.duration_sec,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "play_count": self.play_count,
            "cue_count": len(self.cues),
            "has_beatgrid": "yes" if self.beatgrid else "no",
            "date_added": self.date_added.isoformat() if self.date_added else "",
            "last_played": self.last_played.isoformat() if self.last_played else "",
        }


@dataclass
class RekordboxPlaylist:
    """Playlist from Rekordbox library.

    Rekordbox uses a hierarchical playlist structure where playlists
    can be nested in folders.

    Attributes:
        playlist_id: Internal playlist ID
        name: Playlist name
        parent_id: Parent folder ID (None for root level)
        is_folder: Whether this is a folder (contains playlists) vs playlist
        track_ids: List of content IDs in this playlist
        position: Sort position within parent
    """
    playlist_id: int
    name: str
    parent_id: Optional[int] = None
    is_folder: bool = False
    track_ids: List[int] = field(default_factory=list)
    position: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playlist_id": self.playlist_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "is_folder": self.is_folder,
            "track_count": len(self.track_ids),
            "position": self.position,
        }


@dataclass
class RekordboxLibrary:
    """Container for complete Rekordbox library export.

    Holds all tracks and playlists from a Rekordbox library,
    with convenience methods for lookups and statistics.

    Attributes:
        tracks: Dictionary mapping track_id to RekordboxTrack
        playlists: List of all playlists
        total_tracks: Count of tracks
        tracks_with_cues: Count of tracks with cue points
        tracks_with_beatgrid: Count of analyzed tracks
        tracks_with_key: Count of tracks with key detection
    """
    tracks: Dict[int, RekordboxTrack] = field(default_factory=dict)
    playlists: List[RekordboxPlaylist] = field(default_factory=list)

    # Statistics
    total_tracks: int = 0
    tracks_with_cues: int = 0
    tracks_with_beatgrid: int = 0
    tracks_with_key: int = 0

    def track_by_id(self, track_id: int) -> Optional[RekordboxTrack]:
        """Find track by ID."""
        return self.tracks.get(track_id)

    def track_by_path(self, path: str) -> Optional[RekordboxTrack]:
        """Find track by file path."""
        for track in self.tracks.values():
            if track.file_path == path:
                return track
        return None

    def tracks_by_artist(self, artist: str) -> List[RekordboxTrack]:
        """Find all tracks by artist (case-insensitive)."""
        artist_lower = artist.lower()
        return [
            t for t in self.tracks.values()
            if artist_lower in t.artist.lower()
        ]

    def tracks_in_bpm_range(
        self, min_bpm: float, max_bpm: float
    ) -> List[RekordboxTrack]:
        """Find tracks within BPM range."""
        return [
            t for t in self.tracks.values()
            if t.bpm and min_bpm <= t.bpm <= max_bpm
        ]

    def tracks_by_key(self, key: str) -> List[RekordboxTrack]:
        """Find tracks by musical key."""
        key_lower = key.lower()
        return [
            t for t in self.tracks.values()
            if t.key and t.key.lower() == key_lower
        ]

    def playlist_tree(self) -> Dict[int, List[RekordboxPlaylist]]:
        """Build hierarchical playlist tree."""
        tree: Dict[int, List[RekordboxPlaylist]] = {None: []}
        for playlist in self.playlists:
            parent = playlist.parent_id
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(playlist)
        return tree

    def to_summary_dict(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        return {
            "total_tracks": self.total_tracks,
            "tracks_with_cues": self.tracks_with_cues,
            "tracks_with_beatgrid": self.tracks_with_beatgrid,
            "tracks_with_key": self.tracks_with_key,
            "total_playlists": len([p for p in self.playlists if not p.is_folder]),
            "total_folders": len([p for p in self.playlists if p.is_folder]),
            "cue_percentage": (
                f"{100 * self.tracks_with_cues / self.total_tracks:.1f}%"
                if self.total_tracks > 0 else "0%"
            ),
            "key_percentage": (
                f"{100 * self.tracks_with_key / self.total_tracks:.1f}%"
                if self.total_tracks > 0 else "0%"
            ),
        }
