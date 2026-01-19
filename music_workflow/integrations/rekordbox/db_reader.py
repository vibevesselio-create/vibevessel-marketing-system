"""Reader for Rekordbox 6/7 encrypted database using pyrekordbox.

This module provides a clean interface to read Rekordbox library data,
handling database encryption and analysis file parsing automatically.

Requires pyrekordbox:
    pip install pyrekordbox[psutil]

Example usage:
    from rekordbox.db_reader import RekordboxDbReader

    reader = RekordboxDbReader()
    library = reader.export_library(include_analysis=True)

    for track in library.tracks.values():
        print(f"{track.title} - {track.artist} ({track.bpm} BPM)")
"""

import logging
from pathlib import Path
from typing import Optional, List, Iterator, Dict, Any
from datetime import datetime

# Try to import pyrekordbox
try:
    from pyrekordbox import Rekordbox6Database
    from pyrekordbox.anlz import AnlzFile
    PYREKORDBOX_AVAILABLE = True
except ImportError:
    PYREKORDBOX_AVAILABLE = False
    Rekordbox6Database = None
    AnlzFile = None

from .models import (
    RekordboxTrack,
    RekordboxCue,
    RekordboxBeatgrid,
    RekordboxPlaylist,
    RekordboxLibrary,
)

logger = logging.getLogger("rekordbox.db_reader")

# Rekordbox key signature mapping
# Rekordbox uses 1-24 internally, mapping to Camelot notation
REKORDBOX_KEY_MAP = {
    # Minor keys (A side of Camelot wheel)
    1: ("Abm", "1A"), 2: ("Ebm", "2A"), 3: ("Bbm", "3A"), 4: ("Fm", "4A"),
    5: ("Cm", "5A"), 6: ("Gm", "6A"), 7: ("Dm", "7A"), 8: ("Am", "8A"),
    9: ("Em", "9A"), 10: ("Bm", "10A"), 11: ("F#m", "11A"), 12: ("Dbm", "12A"),
    # Major keys (B side of Camelot wheel)
    13: ("B", "1B"), 14: ("F#", "2B"), 15: ("Db", "3B"), 16: ("Ab", "4B"),
    17: ("Eb", "5B"), 18: ("Bb", "6B"), 19: ("F", "7B"), 20: ("C", "8B"),
    21: ("G", "9B"), 22: ("D", "10B"), 23: ("A", "11B"), 24: ("E", "12B"),
}

# Alternative key mapping for string-based keys from Rekordbox
KEY_STRING_TO_CAMELOT = {
    "Am": "8A", "Em": "9A", "Bm": "10A", "F#m": "11A",
    "C#m": "12A", "Dbm": "12A", "G#m": "1A", "Abm": "1A",
    "D#m": "2A", "Ebm": "2A", "A#m": "3A", "Bbm": "3A",
    "Fm": "4A", "Cm": "5A", "Gm": "6A", "Dm": "7A",
    "C": "8B", "G": "9B", "D": "10B", "A": "11B",
    "E": "12B", "B": "1B", "F#": "2B", "Gb": "2B",
    "C#": "3B", "Db": "3B", "G#": "4B", "Ab": "4B",
    "D#": "5B", "Eb": "5B", "A#": "6B", "Bb": "6B",
    "F": "7B",
}

# Rekordbox cue colors (color ID to RGB)
REKORDBOX_CUE_COLORS = {
    0: "#FFFFFF",  # No color / default
    1: "#FF0000",  # Red
    2: "#FF8000",  # Orange
    3: "#FFFF00",  # Yellow
    4: "#00FF00",  # Green
    5: "#00FFFF",  # Cyan
    6: "#0000FF",  # Blue
    7: "#FF00FF",  # Magenta
    8: "#FF80FF",  # Pink
}


class RekordboxDbReader:
    """Read Rekordbox 6/7 library database.

    This class provides methods to read tracks, playlists, and analysis
    data from a Rekordbox database. It handles the SQLCipher encryption
    automatically using pyrekordbox.

    Attributes:
        db_path: Optional explicit path to master.db
        _db: Internal pyrekordbox database connection
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the database reader.

        Args:
            db_path: Path to Rekordbox master.db. If None, pyrekordbox
                    will auto-discover from default location.

        Raises:
            ImportError: If pyrekordbox is not installed
        """
        if not PYREKORDBOX_AVAILABLE:
            raise ImportError(
                "pyrekordbox is not installed. Install with:\n"
                "  pip install pyrekordbox[psutil]\n"
                "Note: SQLCipher support requires the psutil extra."
            )

        self.db_path = db_path
        self._db: Optional[Rekordbox6Database] = None

    def connect(self) -> Rekordbox6Database:
        """Open connection to Rekordbox database.

        The connection is cached for reuse. pyrekordbox handles
        finding the encryption key automatically.

        Returns:
            Connected Rekordbox6Database instance

        Raises:
            FileNotFoundError: If database cannot be found
            RuntimeError: If decryption fails
        """
        if self._db is None:
            try:
                if self.db_path:
                    self._db = Rekordbox6Database(path=str(self.db_path))
                else:
                    self._db = Rekordbox6Database()
                logger.info(f"Connected to Rekordbox database: {self._db.path}")
            except Exception as e:
                logger.error(f"Failed to connect to Rekordbox database: {e}")
                raise

        return self._db

    def close(self):
        """Close database connection."""
        if self._db is not None:
            self._db = None
            logger.debug("Closed Rekordbox database connection")

    def get_database_info(self) -> Dict[str, Any]:
        """Get information about the connected database.

        Returns:
            Dictionary with database path, version, and basic stats
        """
        db = self.connect()
        content_count = len(list(db.get_content()))
        playlist_count = len(list(db.get_playlist()))

        return {
            "path": str(db.path),
            "track_count": content_count,
            "playlist_count": playlist_count,
        }

    def get_tracks(self, include_analysis: bool = False) -> Iterator[RekordboxTrack]:
        """Iterate over all tracks in the library.

        Args:
            include_analysis: If True, load cue points and beatgrid
                            from analysis files (slower)

        Yields:
            RekordboxTrack objects for each track in library
        """
        db = self.connect()

        for content in db.get_content():
            try:
                track = self._content_to_track(content)

                if include_analysis and track.analysis_path:
                    track = self._load_analysis(track)

                yield track

            except Exception as e:
                logger.warning(
                    f"Error parsing track ID {content.ID} "
                    f"'{getattr(content, 'Title', 'Unknown')}': {e}"
                )
                continue

    def get_track_by_id(self, track_id: int) -> Optional[RekordboxTrack]:
        """Get a specific track by its Rekordbox ID.

        Args:
            track_id: Rekordbox content ID

        Returns:
            RekordboxTrack or None if not found
        """
        db = self.connect()

        for content in db.get_content():
            if content.ID == track_id:
                return self._content_to_track(content)

        return None

    def _content_to_track(self, content) -> RekordboxTrack:
        """Convert pyrekordbox content object to RekordboxTrack.

        Args:
            content: pyrekordbox content row object

        Returns:
            Populated RekordboxTrack dataclass
        """
        # Parse key and Camelot notation
        key = None
        key_camelot = None

        if hasattr(content, 'Tonality') and content.Tonality:
            key = content.Tonality
            key_camelot = KEY_STRING_TO_CAMELOT.get(key)

        # Build file path
        file_path = ""
        if hasattr(content, 'FolderPath') and content.FolderPath:
            file_path = content.FolderPath
        elif hasattr(content, 'OrgFolderPath') and content.OrgFolderPath:
            file_path = content.OrgFolderPath

        # Parse BPM (stored as int * 100 in some versions)
        bpm = None
        if hasattr(content, 'BPM') and content.BPM:
            bpm_val = content.BPM
            # If BPM is stored as integer * 100
            if bpm_val > 1000:
                bpm = bpm_val / 100.0
            else:
                bpm = float(bpm_val)

        # Parse duration (stored as milliseconds)
        duration_sec = 0.0
        if hasattr(content, 'Length') and content.Length:
            duration_sec = content.Length / 1000.0

        # Build track object
        track = RekordboxTrack(
            track_id=content.ID,
            title=getattr(content, 'Title', '') or '',
            artist=self._get_related_name(content, 'Artist'),
            album=self._get_related_name(content, 'Album'),
            genre=self._get_related_name(content, 'Genre'),
            composer=getattr(content, 'Composer', '') or '',
            remixer=getattr(content, 'Remixer', '') or '',
            label=self._get_related_name(content, 'Label'),
            comment=getattr(content, 'Commnt', '') or '',
            file_path=file_path,
            duration_sec=duration_sec,
            bitrate=getattr(content, 'BitRate', 0) or 0,
            sample_rate=getattr(content, 'SampleRate', 0) or 0,
            file_size=getattr(content, 'FileSize', 0) or 0,
            bpm=bpm,
            key=key,
            key_camelot=key_camelot,
            rating=getattr(content, 'Rating', 0) or 0,
            play_count=getattr(content, 'DJPlayCount', 0) or 0,
            analysis_path=getattr(content, 'AnalysisDataPath', None),
        )

        # Parse timestamps
        if hasattr(content, 'created_at') and content.created_at:
            track.date_added = content.created_at
        if hasattr(content, 'updated_at') and content.updated_at:
            track.date_modified = content.updated_at

        return track

    def _get_related_name(self, content, relation: str) -> str:
        """Safely get name from a related object.

        Args:
            content: pyrekordbox content object
            relation: Name of the relation (e.g., 'Artist', 'Album')

        Returns:
            Name string or empty string
        """
        try:
            related = getattr(content, relation, None)
            if related and hasattr(related, 'Name'):
                return related.Name or ''
        except Exception:
            pass
        return ''

    def _load_analysis(self, track: RekordboxTrack) -> RekordboxTrack:
        """Load analysis data (cues, beatgrid) for a track.

        Args:
            track: Track to load analysis for

        Returns:
            Track with cues and beatgrid populated
        """
        if not track.analysis_path:
            return track

        anlz_path = Path(track.analysis_path)

        # Try .DAT file first, then .EXT
        dat_path = anlz_path.with_suffix('.DAT')
        ext_path = anlz_path.with_suffix('.EXT')

        paths_to_try = [dat_path, ext_path, anlz_path]

        for path in paths_to_try:
            if path.exists():
                try:
                    anlz = AnlzFile.parse_file(path)
                    track = self._parse_analysis(track, anlz)
                    break
                except Exception as e:
                    logger.debug(f"Could not parse {path}: {e}")
                    continue

        return track

    def _parse_analysis(self, track: RekordboxTrack, anlz) -> RekordboxTrack:
        """Parse analysis file data into track object.

        Args:
            track: Track to update
            anlz: Parsed AnlzFile object

        Returns:
            Updated track with cues and beatgrid
        """
        # Parse cue points
        if hasattr(anlz, 'cue_list_tags') or hasattr(anlz, 'cue_extended_tags'):
            cue_data = getattr(anlz, 'cue_list_tags', None) or []
            if not cue_data:
                cue_data = getattr(anlz, 'cue_extended_tags', None) or []

            for idx, cue in enumerate(cue_data):
                try:
                    rb_cue = RekordboxCue(
                        cue_id=idx,
                        cue_type="loop" if getattr(cue, 'loop', False) else "cue",
                        hot_cue=getattr(cue, 'hot_cue', None),
                        time_ms=getattr(cue, 'time', 0) or 0,
                        loop_time_ms=getattr(cue, 'loop_time', None),
                        color_id=getattr(cue, 'color_id', None),
                        color_rgb=REKORDBOX_CUE_COLORS.get(
                            getattr(cue, 'color_id', 0), "#FFFFFF"
                        ),
                        name=getattr(cue, 'name', None),
                    )
                    track.cues.append(rb_cue)
                except Exception as e:
                    logger.debug(f"Error parsing cue {idx}: {e}")

        # Parse beat grid
        if hasattr(anlz, 'beat_grid_tags'):
            beat_data = getattr(anlz, 'beat_grid_tags', None)
            if beat_data:
                try:
                    bpm = getattr(beat_data, 'bpm', None) or track.bpm
                    beat_times = getattr(beat_data, 'beat_times', []) or []

                    track.beatgrid = RekordboxBeatgrid(
                        bpm=bpm or 0.0,
                        offset_ms=beat_times[0] if beat_times else 0,
                        is_dynamic=len(beat_times) > 1,
                    )
                except Exception as e:
                    logger.debug(f"Error parsing beatgrid: {e}")

        return track

    def get_playlists(self) -> List[RekordboxPlaylist]:
        """Get all playlists from the library.

        Returns:
            List of RekordboxPlaylist objects
        """
        db = self.connect()
        playlists = []

        for playlist in db.get_playlist():
            try:
                # Determine if folder or playlist
                is_folder = (
                    getattr(playlist, 'Attribute', 1) == 0 or
                    hasattr(playlist, 'is_folder') and playlist.is_folder
                )

                rb_playlist = RekordboxPlaylist(
                    playlist_id=playlist.ID,
                    name=getattr(playlist, 'Name', '') or f'Playlist {playlist.ID}',
                    parent_id=(
                        playlist.ParentID
                        if hasattr(playlist, 'ParentID') and playlist.ParentID != 0
                        else None
                    ),
                    is_folder=is_folder,
                    position=getattr(playlist, 'Seq', 0) or 0,
                )

                # Get track IDs if it's a playlist (not folder)
                if not is_folder:
                    songs = getattr(playlist, 'Songs', None) or []
                    for song in songs:
                        content_id = getattr(song, 'ContentID', None)
                        if content_id:
                            rb_playlist.track_ids.append(content_id)

                playlists.append(rb_playlist)

            except Exception as e:
                logger.warning(f"Error parsing playlist {playlist.ID}: {e}")
                continue

        return playlists

    def export_library(
        self,
        include_analysis: bool = False,
        progress_callback: Optional[callable] = None
    ) -> RekordboxLibrary:
        """Export complete library to RekordboxLibrary container.

        Args:
            include_analysis: Load cue points and beatgrids (slower)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            RekordboxLibrary with all tracks and playlists
        """
        library = RekordboxLibrary()

        logger.info("Exporting Rekordbox library...")

        # Get track count for progress
        db = self.connect()
        track_list = list(db.get_content())
        total = len(track_list)

        # Export tracks
        for idx, content in enumerate(track_list):
            try:
                track = self._content_to_track(content)

                if include_analysis:
                    track = self._load_analysis(track)

                library.tracks[track.track_id] = track
                library.total_tracks += 1

                if track.cues:
                    library.tracks_with_cues += 1
                if track.beatgrid:
                    library.tracks_with_beatgrid += 1
                if track.key:
                    library.tracks_with_key += 1

                if progress_callback and idx % 100 == 0:
                    progress_callback(idx, total)

            except Exception as e:
                logger.warning(f"Error exporting track: {e}")
                continue

        # Export playlists
        library.playlists = self.get_playlists()

        logger.info(
            f"Exported {library.total_tracks} tracks, "
            f"{len(library.playlists)} playlists"
        )
        logger.info(
            f"  With cues: {library.tracks_with_cues}, "
            f"With key: {library.tracks_with_key}"
        )

        return library

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
