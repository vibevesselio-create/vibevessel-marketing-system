"""Read Apple Music library via AppleScript/JXA.

This module provides a high-level interface to read the complete
Apple Music library, including tracks and playlists.

Uses JXA (JavaScript for Automation) for batch operations due to
better performance with large datasets and native JSON support.

Example usage:
    from apple_music.library_reader import AppleMusicLibraryReader

    reader = AppleMusicLibraryReader()
    library = reader.export_library()

    print(f"Total tracks: {library.total_tracks}")
    for track in library.tracks.values():
        print(f"  {track.name} - {track.artist}")
"""

import logging
from typing import Optional, List, Iterator, Callable
from datetime import datetime

from .models import AppleMusicTrack, AppleMusicPlaylist, AppleMusicLibrary
from .applescript_executor import AppleScriptExecutor, AppleScriptError

logger = logging.getLogger("apple_music.library_reader")


class AppleMusicLibraryReader:
    """Read Apple Music library using AppleScript/JXA.

    This class provides methods to read tracks and playlists from
    the Apple Music application. It uses JXA for batch operations
    and AppleScript for individual track operations.

    Attributes:
        executor: AppleScriptExecutor instance
        batch_size: Number of tracks to fetch per JXA call
    """

    BATCH_SIZE = 500  # Tracks per JXA call (balance between speed and memory)
    SYSTEM_PLAYLISTS = {
        'Library', 'Music', 'Music Videos', 'Favorite Songs',
        'Downloaded', 'Recently Added', 'Recently Played'
    }

    def __init__(self, batch_size: Optional[int] = None):
        """Initialize the library reader.

        Args:
            batch_size: Number of tracks per batch (default 500)
        """
        self.executor = AppleScriptExecutor()
        self.batch_size = batch_size or self.BATCH_SIZE

    def get_track_count(self) -> int:
        """Get total number of tracks in library.

        Returns:
            Number of tracks
        """
        return self.executor.get_track_count()

    def get_playlist_count(self) -> int:
        """Get total number of playlists.

        Returns:
            Number of playlists
        """
        return self.executor.get_playlist_count()

    def get_tracks(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Iterator[AppleMusicTrack]:
        """Iterate over all tracks in library.

        Uses JXA batch fetching for performance. Large libraries
        (10,000+ tracks) may take 30-60 seconds.

        Args:
            progress_callback: Optional callback(current, total) for progress

        Yields:
            AppleMusicTrack for each track in library
        """
        total = self.get_track_count()
        logger.info(f"Reading {total} tracks from Apple Music...")

        for start in range(0, total, self.batch_size):
            try:
                # Fetch batch using JXA
                batch = self.executor.get_track_batch_jxa(start, self.batch_size)

                for track_data in batch:
                    track = self._jxa_to_track(track_data)
                    yield track

                current = min(start + self.batch_size, total)
                if progress_callback:
                    progress_callback(current, total)

                logger.debug(f"Processed {current}/{total} tracks")

            except Exception as e:
                logger.error(f"Error reading batch starting at {start}: {e}")
                # Try to continue with next batch
                continue

    def _jxa_to_track(self, data: dict) -> AppleMusicTrack:
        """Convert JXA track dictionary to AppleMusicTrack.

        Args:
            data: Dictionary from JXA JSON output

        Returns:
            AppleMusicTrack instance
        """
        # Parse date added if present
        date_added = None
        if data.get('dateAdded'):
            try:
                date_added = datetime.fromisoformat(data['dateAdded'])
            except (ValueError, TypeError):
                pass

        return AppleMusicTrack(
            persistent_id=data.get('persistentId', ''),
            database_id=data.get('databaseId', 0),
            name=data.get('name', ''),
            artist=data.get('artist', ''),
            album=data.get('album', ''),
            album_artist=data.get('albumArtist', ''),
            composer=data.get('composer', ''),
            genre=data.get('genre', ''),
            grouping=data.get('grouping', ''),
            comment=data.get('comment', ''),
            bpm=data.get('bpm') if data.get('bpm', 0) > 0 else None,
            duration=data.get('duration', 0.0),
            location=data.get('location'),
            kind=data.get('kind', ''),
            bit_rate=data.get('bitRate', 0),
            sample_rate=data.get('sampleRate', 0),
            size=data.get('size', 0),
            played_count=data.get('playedCount', 0),
            skipped_count=data.get('skippedCount', 0),
            rating=data.get('rating', 0),
            track_number=data.get('trackNumber', 0),
            disc_number=data.get('discNumber', 0),
            year=data.get('year', 0),
            enabled=data.get('enabled', True),
            compilation=data.get('compilation', False),
            favorited=data.get('favorited', False),
            date_added=date_added,
        )

    def get_playlists(
        self,
        include_system: bool = False,
        include_tracks: bool = True
    ) -> List[AppleMusicPlaylist]:
        """Get all playlists from library.

        Args:
            include_system: Include system playlists (Library, Music, etc.)
            include_tracks: Fetch track IDs for each playlist (slower)

        Returns:
            List of AppleMusicPlaylist objects
        """
        logger.info("Reading playlists from Apple Music...")

        names = self.executor.get_playlist_names()
        playlists = []

        for name in names:
            # Skip system playlists unless requested
            if not include_system and name in self.SYSTEM_PLAYLISTS:
                continue

            try:
                playlist = AppleMusicPlaylist(
                    playlist_id=name,  # Use name as ID (persistent ID requires more work)
                    name=name,
                )

                # Fetch track IDs if requested
                if include_tracks:
                    try:
                        track_ids = self.executor.get_playlist_tracks(name)
                        playlist.track_ids = track_ids
                        playlist.track_count = len(track_ids)
                    except AppleScriptError:
                        logger.warning(f"Could not get tracks for playlist: {name}")

                playlists.append(playlist)

            except Exception as e:
                logger.warning(f"Error reading playlist '{name}': {e}")
                continue

        logger.info(f"Read {len(playlists)} playlists")
        return playlists

    def export_library(
        self,
        include_playlists: bool = True,
        playlist_tracks: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> AppleMusicLibrary:
        """Export complete library to AppleMusicLibrary container.

        Args:
            include_playlists: Include playlist data
            playlist_tracks: Include track IDs for each playlist (slower)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            AppleMusicLibrary with all tracks and playlists
        """
        library = AppleMusicLibrary()

        logger.info("=" * 60)
        logger.info("APPLE MUSIC LIBRARY EXPORT")
        logger.info("=" * 60)

        # Export tracks
        for track in self.get_tracks(progress_callback):
            library.tracks[track.persistent_id] = track
            library.total_tracks += 1
            library.total_duration += track.duration

            if track.bpm:
                library.tracks_with_bpm += 1
            if track.location:
                library.tracks_with_location += 1

        logger.info(f"Exported {library.total_tracks} tracks")
        logger.info(f"  With BPM: {library.tracks_with_bpm}")
        logger.info(f"  With location: {library.tracks_with_location}")

        # Export playlists
        if include_playlists:
            library.playlists = self.get_playlists(
                include_system=False,
                include_tracks=playlist_tracks
            )
            logger.info(f"Exported {len(library.playlists)} playlists")

        logger.info("=" * 60)
        logger.info("EXPORT COMPLETE")
        logger.info("=" * 60)

        return library

    def get_track_by_id(self, persistent_id: str) -> Optional[AppleMusicTrack]:
        """Get a specific track by its persistent ID.

        This uses AppleScript (not JXA) to fetch a single track,
        which is more reliable for individual lookups.

        Args:
            persistent_id: Apple Music persistent ID

        Returns:
            AppleMusicTrack or None if not found
        """
        script = f'''
tell application "Music"
    try
        set t to (first track whose persistent ID is "{persistent_id}")
        return {{persistent ID of t, database ID of t, name of t, artist of t, ¬
            album of t, genre of t, bpm of t, duration of t}}
    on error
        return ""
    end try
end tell
'''
        try:
            result = self.executor.run(script)
            if not result:
                return None

            parts = [p.strip() for p in result.split(', ')]
            if len(parts) < 8:
                return None

            return AppleMusicTrack(
                persistent_id=parts[0],
                database_id=int(parts[1]) if parts[1].isdigit() else 0,
                name=parts[2],
                artist=parts[3],
                album=parts[4],
                genre=parts[5],
                bpm=int(parts[6]) if parts[6].isdigit() and int(parts[6]) > 0 else None,
                duration=float(parts[7]) if parts[7] else 0.0,
            )

        except Exception as e:
            logger.error(f"Error fetching track {persistent_id}: {e}")
            return None

    def find_tracks_by_path(self, paths: List[str]) -> List[AppleMusicTrack]:
        """Find tracks matching given file paths.

        Useful for cross-referencing with djay Pro or Rekordbox libraries.

        Args:
            paths: List of file paths to search for

        Returns:
            List of matching AppleMusicTrack objects
        """
        # Build path lookup set (normalized)
        path_set = {p.lower() for p in paths}
        matches = []

        for track in self.get_tracks():
            if track.location and track.location.lower() in path_set:
                matches.append(track)

        logger.info(f"Found {len(matches)} tracks matching {len(paths)} paths")
        return matches
