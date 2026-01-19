"""AppleScript execution wrapper for Apple Music automation.

This module provides a safe interface to execute AppleScript commands
for interacting with the Apple Music app (formerly iTunes).

All Music app operations go through this executor, which handles:
- Subprocess management
- Error handling and logging
- Timeout management
- Output parsing

Example usage:
    from applescript_executor import AppleScriptExecutor

    executor = AppleScriptExecutor()
    count = executor.get_track_count()
    print(f"Library has {count} tracks")
"""

import subprocess
import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger("apple_music.applescript")


class AppleScriptError(Exception):
    """Exception raised for AppleScript execution errors."""
    pass


class AppleScriptExecutor:
    """Execute AppleScript commands for Apple Music.

    This class provides methods to interact with the Music app via
    AppleScript, executed through the osascript command.

    Attributes:
        default_timeout: Default timeout for script execution (seconds)
    """

    def __init__(self, default_timeout: int = 60):
        """Initialize the executor.

        Args:
            default_timeout: Default timeout for script execution
        """
        self.default_timeout = default_timeout

    def run(self, script: str, timeout: Optional[int] = None) -> str:
        """Execute AppleScript and return result.

        Args:
            script: AppleScript code to execute
            timeout: Maximum execution time in seconds (uses default if None)

        Returns:
            Script output as string (stdout)

        Raises:
            AppleScriptError: If script execution fails
            TimeoutError: If script exceeds timeout
        """
        timeout = timeout or self.default_timeout

        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"AppleScript error: {error_msg}")
                raise AppleScriptError(f"AppleScript failed: {error_msg}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.error(f"AppleScript timed out after {timeout}s")
            raise TimeoutError(f"AppleScript timed out after {timeout}s")

    def run_jxa(self, script: str, timeout: Optional[int] = None) -> str:
        """Execute JavaScript for Automation (JXA) script.

        Args:
            script: JXA code to execute
            timeout: Maximum execution time in seconds

        Returns:
            Script output as string

        Raises:
            AppleScriptError: If script execution fails
        """
        timeout = timeout or self.default_timeout

        try:
            result = subprocess.run(
                ['osascript', '-l', 'JavaScript', '-e', script],
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"JXA error: {error_msg}")
                raise AppleScriptError(f"JXA failed: {error_msg}")

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"JXA timed out after {timeout}s")

    # =========================================================================
    # Library-level operations
    # =========================================================================

    def get_track_count(self) -> int:
        """Get total number of tracks in library.

        Returns:
            Number of tracks
        """
        result = self.run('tell application "Music" to count of tracks')
        return int(result)

    def get_playlist_count(self) -> int:
        """Get total number of playlists.

        Returns:
            Number of playlists
        """
        result = self.run('tell application "Music" to count of playlists')
        return int(result)

    def get_playlist_names(self) -> List[str]:
        """Get names of all playlists.

        Returns:
            List of playlist names
        """
        result = self.run('tell application "Music" to get name of every playlist')
        # Parse comma-separated list
        return [name.strip() for name in result.split(', ')]

    def is_music_running(self) -> bool:
        """Check if Music app is running.

        Returns:
            True if Music is running
        """
        script = '''
tell application "System Events"
    return (name of processes) contains "Music"
end tell
'''
        result = self.run(script)
        return result.lower() == "true"

    # =========================================================================
    # Track retrieval
    # =========================================================================

    def get_track_properties(self, index: int) -> Dict[str, Any]:
        """Get all properties of a track by index.

        Args:
            index: 1-based track index

        Returns:
            Dictionary of track properties
        """
        script = f'''
tell application "Music"
    set t to track {index}
    set trackProps to {{}}

    set end of trackProps to persistent ID of t
    set end of trackProps to database ID of t
    set end of trackProps to name of t
    set end of trackProps to artist of t
    set end of trackProps to album of t
    set end of trackProps to album artist of t
    set end of trackProps to composer of t
    set end of trackProps to genre of t
    set end of trackProps to grouping of t
    set end of trackProps to comment of t
    set end of trackProps to bpm of t
    set end of trackProps to duration of t
    set end of trackProps to bit rate of t
    set end of trackProps to sample rate of t
    set end of trackProps to size of t
    set end of trackProps to played count of t
    set end of trackProps to skipped count of t
    set end of trackProps to rating of t
    set end of trackProps to track number of t
    set end of trackProps to disc number of t
    set end of trackProps to year of t
    set end of trackProps to kind of t
    set end of trackProps to enabled of t
    set end of trackProps to compilation of t
    set end of trackProps to favorited of t

    try
        set end of trackProps to POSIX path of (location of t)
    on error
        set end of trackProps to ""
    end try

    try
        set end of trackProps to date added of t as string
    on error
        set end of trackProps to ""
    end try

    return trackProps
end tell
'''
        result = self.run(script, timeout=30)
        return self._parse_track_properties(result)

    def _parse_track_properties(self, raw: str) -> Dict[str, Any]:
        """Parse raw AppleScript track properties output.

        Args:
            raw: Raw comma-separated output from AppleScript

        Returns:
            Parsed dictionary of properties
        """
        # AppleScript returns comma-separated values
        # Need careful parsing due to commas in values
        parts = self._split_applescript_list(raw)

        if len(parts) < 25:
            logger.warning(f"Unexpected property count: {len(parts)}")
            return {}

        return {
            "persistent_id": parts[0],
            "database_id": self._safe_int(parts[1]),
            "name": parts[2],
            "artist": parts[3],
            "album": parts[4],
            "album_artist": parts[5],
            "composer": parts[6],
            "genre": parts[7],
            "grouping": parts[8],
            "comment": parts[9],
            "bpm": self._safe_int(parts[10]),
            "duration": self._safe_float(parts[11]),
            "bit_rate": self._safe_int(parts[12]),
            "sample_rate": self._safe_int(parts[13]),
            "size": self._safe_int(parts[14]),
            "played_count": self._safe_int(parts[15]),
            "skipped_count": self._safe_int(parts[16]),
            "rating": self._safe_int(parts[17]),
            "track_number": self._safe_int(parts[18]),
            "disc_number": self._safe_int(parts[19]),
            "year": self._safe_int(parts[20]),
            "kind": parts[21],
            "enabled": parts[22].lower() == "true",
            "compilation": parts[23].lower() == "true",
            "favorited": parts[24].lower() == "true",
            "location": parts[25] if len(parts) > 25 and parts[25] else None,
            "date_added": parts[26] if len(parts) > 26 else None,
        }

    def get_track_batch_jxa(self, start: int, count: int) -> List[Dict[str, Any]]:
        """Get a batch of tracks using JXA (more reliable for large batches).

        Args:
            start: Starting track index (0-based for JXA)
            count: Number of tracks to retrieve

        Returns:
            List of track dictionaries
        """
        script = f'''
const Music = Application('Music');
const tracks = Music.tracks();
const start = {start};
const count = Math.min({count}, tracks.length - start);
const result = [];

for (let i = start; i < start + count; i++) {{
    const t = tracks[i];
    let loc = null;
    try {{ loc = t.location().toString(); }} catch(e) {{}}

    result.push({{
        persistentId: t.persistentID(),
        databaseId: t.databaseID(),
        name: t.name(),
        artist: t.artist(),
        album: t.album(),
        albumArtist: t.albumArtist(),
        composer: t.composer(),
        genre: t.genre(),
        grouping: t.grouping(),
        comment: t.comment(),
        bpm: t.bpm(),
        duration: t.duration(),
        bitRate: t.bitRate(),
        sampleRate: t.sampleRate(),
        size: t.size(),
        playedCount: t.playedCount(),
        skippedCount: t.skippedCount(),
        rating: t.rating(),
        trackNumber: t.trackNumber(),
        discNumber: t.discNumber(),
        year: t.year(),
        kind: t.kind(),
        enabled: t.enabled(),
        compilation: t.compilation(),
        favorited: t.favorited(),
        location: loc
    }});
}}

JSON.stringify(result);
'''
        import json
        result = self.run_jxa(script, timeout=120)
        return json.loads(result)

    # =========================================================================
    # Track modification
    # =========================================================================

    def set_track_bpm(self, persistent_id: str, bpm: int) -> bool:
        """Set BPM for a track.

        Args:
            persistent_id: Track's persistent ID
            bpm: New BPM value (positive integer)

        Returns:
            True if successful
        """
        if bpm <= 0:
            logger.warning(f"Invalid BPM value: {bpm}")
            return False

        script = f'''
tell application "Music"
    set targetTrack to (first track whose persistent ID is "{persistent_id}")
    set bpm of targetTrack to {bpm}
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to set BPM: {e}")
            return False

    def set_track_rating(self, persistent_id: str, rating: int) -> bool:
        """Set rating for a track.

        Args:
            persistent_id: Track's persistent ID
            rating: Rating value (0-100, where 20=1 star)

        Returns:
            True if successful
        """
        rating = max(0, min(100, rating))

        script = f'''
tell application "Music"
    set targetTrack to (first track whose persistent ID is "{persistent_id}")
    set rating of targetTrack to {rating}
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to set rating: {e}")
            return False

    def set_track_comment(self, persistent_id: str, comment: str) -> bool:
        """Set comment for a track.

        Args:
            persistent_id: Track's persistent ID
            comment: New comment text

        Returns:
            True if successful
        """
        # Escape quotes in comment
        comment_escaped = comment.replace('"', '\\"')

        script = f'''
tell application "Music"
    set targetTrack to (first track whose persistent ID is "{persistent_id}")
    set comment of targetTrack to "{comment_escaped}"
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to set comment: {e}")
            return False

    def set_track_grouping(self, persistent_id: str, grouping: str) -> bool:
        """Set grouping for a track.

        Args:
            persistent_id: Track's persistent ID
            grouping: New grouping text

        Returns:
            True if successful
        """
        grouping_escaped = grouping.replace('"', '\\"')

        script = f'''
tell application "Music"
    set targetTrack to (first track whose persistent ID is "{persistent_id}")
    set grouping of targetTrack to "{grouping_escaped}"
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to set grouping: {e}")
            return False

    # =========================================================================
    # Playlist operations
    # =========================================================================

    def get_playlist_tracks(self, playlist_name: str) -> List[str]:
        """Get persistent IDs of all tracks in a playlist.

        Args:
            playlist_name: Name of the playlist

        Returns:
            List of track persistent IDs
        """
        # Escape playlist name
        name_escaped = playlist_name.replace('"', '\\"')

        script = f'''
tell application "Music"
    set pl to playlist "{name_escaped}"
    set trackIDs to {{}}
    repeat with t in tracks of pl
        set end of trackIDs to persistent ID of t
    end repeat
    return trackIDs
end tell
'''
        try:
            result = self.run(script, timeout=120)
            return self._split_applescript_list(result)
        except AppleScriptError as e:
            logger.error(f"Failed to get playlist tracks: {e}")
            return []

    def create_playlist(self, name: str) -> bool:
        """Create a new empty playlist.

        Args:
            name: Name for the new playlist

        Returns:
            True if successful
        """
        name_escaped = name.replace('"', '\\"')

        script = f'''
tell application "Music"
    make new playlist with properties {{name:"{name_escaped}"}}
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to create playlist: {e}")
            return False

    def add_track_to_playlist(
        self, track_persistent_id: str, playlist_name: str
    ) -> bool:
        """Add a track to a playlist.

        Args:
            track_persistent_id: Track's persistent ID
            playlist_name: Name of target playlist

        Returns:
            True if successful
        """
        name_escaped = playlist_name.replace('"', '\\"')

        script = f'''
tell application "Music"
    set targetTrack to (first track whose persistent ID is "{track_persistent_id}")
    set targetPlaylist to playlist "{name_escaped}"
    duplicate targetTrack to targetPlaylist
    return "OK"
end tell
'''
        try:
            result = self.run(script)
            return result == "OK"
        except AppleScriptError as e:
            logger.error(f"Failed to add track to playlist: {e}")
            return False

    # =========================================================================
    # Helper methods
    # =========================================================================

    def _split_applescript_list(self, raw: str) -> List[str]:
        """Split AppleScript comma-separated list, handling nested values.

        Args:
            raw: Raw AppleScript output

        Returns:
            List of string values
        """
        # Simple split for now - may need more sophisticated parsing
        # for values containing commas
        return [item.strip() for item in raw.split(', ')]

    def _safe_int(self, value: str) -> int:
        """Safely convert string to int.

        Args:
            value: String to convert

        Returns:
            Integer value or 0 if conversion fails
        """
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def _safe_float(self, value: str) -> float:
        """Safely convert string to float.

        Args:
            value: String to convert

        Returns:
            Float value or 0.0 if conversion fails
        """
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
