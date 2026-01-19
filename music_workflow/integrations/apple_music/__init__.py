"""Apple Music library integration module.

This module provides tools for reading and syncing Apple Music/iTunes
library data with Notion and other DJ software (djay Pro, Rekordbox).

Access Method: AppleScript via osascript subprocess calls
- No XML export dependency required
- Real-time library access
- Full read/write capability for most properties

Components:
    - models: Data classes for Apple Music tracks, playlists
    - applescript_executor: Execute AppleScript commands safely
    - library_reader: Read library data via AppleScript
    - matcher: Match Apple Music tracks to Notion database
    - sync: Sync Apple Music data with Notion and write back

Example usage:
    from apple_music import AppleMusicLibraryReader, AppleMusicTrack

    reader = AppleMusicLibraryReader()
    library = reader.export_library()

    for track in library.tracks.values():
        print(f"{track.name} - {track.artist} ({track.bpm} BPM)")
"""

from .models import (
    AppleMusicTrack,
    AppleMusicPlaylist,
    AppleMusicLibrary,
)
from .applescript_executor import AppleScriptExecutor, AppleScriptError
from .library_reader import AppleMusicLibraryReader
from .matcher import AppleMusicTrackMatcher, AppleMusicTrackMatch
from .id_sync import AppleMusicIdSync, SyncResult, SyncStats

__all__ = [
    # Models
    "AppleMusicTrack",
    "AppleMusicPlaylist",
    "AppleMusicLibrary",
    # Executor
    "AppleScriptExecutor",
    "AppleScriptError",
    # Reader
    "AppleMusicLibraryReader",
    # Matcher
    "AppleMusicTrackMatcher",
    "AppleMusicTrackMatch",
    # Sync
    "AppleMusicIdSync",
    "SyncResult",
    "SyncStats",
]

__version__ = "1.0.0"
