#!/usr/bin/env python3
"""
djay Pro Unified Library Export
═══════════════════════════════════════════════════════════════════════════════
Comprehensive export of djay Pro library data to CSV and Google Sheets.

Produces 5 output files:
1. djay_library_tracks.csv - Complete track catalog with source info
2. djay_library_streaming.csv - Streaming service details
3. djay_session_history.csv - DJ session records
4. djay_session_tracks.csv - Track play history
5. djay_playlists.csv - Playlist data

Also syncs to a Google Sheets workbook with all sheets plus a summary dashboard.

Version: 2026-01-16
"""

from __future__ import annotations

import os
import sys
import json
import csv
import sqlite3
import struct
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict

# Constants
# Note: CSV files are now "living documents" with consistent filenames (no timestamps)
# This allows them to be reused and managed over time
DEFAULT_DB_PATH = Path("/Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db")
DEFAULT_OUTPUT_DIR = Path.home() / "Projects/github-production/djay_pro_export"

# Key signature mappings
KEY_SIGNATURE_MAP = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E", 5: "F",
    6: "F#", 7: "G", 8: "G#", 9: "A", 10: "A#", 11: "B",
    12: "Cm", 13: "C#m", 14: "Dm", 15: "D#m", 16: "Em", 17: "Fm",
    18: "F#m", 19: "Gm", 20: "G#m", 21: "Am", 22: "A#m", 23: "Bm"
}

# Camelot wheel mappings
CAMELOT_MAP = {
    "C": "8B", "C#": "3B", "D": "10B", "D#": "5B", "E": "12B", "F": "7B",
    "F#": "2B", "G": "9B", "G#": "4B", "A": "11B", "A#": "6B", "B": "1B",
    "Cm": "5A", "C#m": "12A", "Dm": "7A", "D#m": "2A", "Em": "9A", "Fm": "4A",
    "F#m": "11A", "Gm": "6A", "G#m": "1A", "Am": "8A", "A#m": "3A", "Bm": "10A"
}

# Streaming source patterns
STREAMING_SOURCES = {
    "beatport": "beatport:",
    "soundcloud": "soundcloud:",
    "spotify": "spotify:",
    "apple": "apple:",
    "tidal": "tidal:",
    "deezer": "deezer:",
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("djay-unified-export")


@dataclass
class Track:
    """Unified track data structure."""
    track_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    duration_sec: float = 0.0
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    source_type: str = "local"  # local, beatport, soundcloud, spotify, apple, tidal
    source_id: Optional[str] = None
    file_path: Optional[str] = None
    added_date: Optional[str] = None
    last_played: Optional[str] = None
    play_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StreamingTrack:
    """Streaming service track details."""
    track_id: str
    source_type: str
    source_track_id: str
    source_url: Optional[str] = None
    artist: str = ""
    title: str = ""
    duration_sec: float = 0.0
    is_available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    """DJ session record."""
    session_id: str
    device_name: str = ""
    device_type: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: float = 0.0
    track_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionTrack:
    """Track played in a session."""
    play_id: str
    session_id: str
    track_id: str
    deck_number: int = 0
    play_start: Optional[str] = None
    title: str = ""
    artist: str = ""
    bpm: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlaylistEntry:
    """Playlist and track membership."""
    playlist_id: str
    playlist_name: str
    track_id: str
    position: int = 0
    added_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class YapDatabaseDecoder:
    """Decoder for YapDatabase binary format used by djay Pro."""

    @staticmethod
    def decode_string(data: bytes, offset: int) -> Tuple[str, int]:
        """Decode a string from YapDatabase binary format."""
        if offset >= len(data):
            return "", offset

        # Check for string marker (0x08)
        if data[offset] == 0x08:
            offset += 1
            # Read until null terminator
            end = data.find(b'\x00', offset)
            if end == -1:
                end = len(data)
            try:
                value = data[offset:end].decode('utf-8', errors='replace')
            except:
                value = ""
            return value, end + 1
        return "", offset

    @staticmethod
    def decode_float(data: bytes, offset: int) -> Tuple[Optional[float], int]:
        """Decode a float from binary data."""
        try:
            if offset + 4 <= len(data):
                value = struct.unpack('<f', data[offset:offset+4])[0]
                return value, offset + 4
        except:
            pass
        return None, offset

    @staticmethod
    def extract_strings(data: bytes) -> List[str]:
        """Extract all readable strings from binary data."""
        strings = []
        current = []
        for byte in data:
            if 32 <= byte < 127:  # Printable ASCII
                current.append(chr(byte))
            else:
                if len(current) >= 3:  # Minimum string length
                    strings.append(''.join(current))
                current = []
        if len(current) >= 3:
            strings.append(''.join(current))
        return strings

    @staticmethod
    def find_source_uri(data: bytes) -> Optional[str]:
        """Find streaming source URI in binary data."""
        try:
            decoded = data.decode('utf-8', errors='ignore')
            for source_name, prefix in STREAMING_SOURCES.items():
                idx = decoded.find(prefix)
                if idx != -1:
                    # Extract the full URI
                    end = idx
                    while end < len(decoded) and decoded[end] not in '\x00\x08\x00':
                        end += 1
                    uri = decoded[idx:end].strip('\x00\x08')
                    return uri
        except:
            pass

        # Try binary search
        for source_name, prefix in STREAMING_SOURCES.items():
            prefix_bytes = prefix.encode('utf-8')
            idx = data.find(prefix_bytes)
            if idx != -1:
                end = idx
                while end < len(data) and data[end] != 0:
                    end += 1
                try:
                    return data[idx:end].decode('utf-8', errors='replace')
                except:
                    pass
        return None

    @staticmethod
    def find_file_uri(data: bytes) -> Optional[str]:
        """Find file:// URI in binary data."""
        try:
            decoded = data.decode('utf-8', errors='ignore')
            idx = decoded.find('file://')
            if idx != -1:
                end = idx + 7
                while end < len(decoded) and decoded[end] not in '\x00\x08':
                    end += 1
                return decoded[idx:end].strip('\x00')
        except:
            pass
        return None

    @staticmethod
    def extract_coredata_timestamp(data: bytes, marker: bytes) -> Optional[datetime]:
        """Extract CoreData timestamp after a marker string.

        CoreData timestamps are seconds since 2001-01-01 stored as little-endian doubles.
        The marker is followed by: 0x00 0x30 then 8 bytes of padding, then 8 bytes of timestamp.
        Type 0x30 indicates a number type; other types (0x0c = array) don't contain direct timestamps.
        """
        import struct
        from datetime import datetime, timedelta

        idx = data.find(marker)
        if idx == -1:
            return None

        # Pattern: marker + null + type_marker + data
        start = idx + len(marker) + 1  # Skip marker and null

        if start >= len(data):
            return None

        # Check for 0x30 type marker (number type)
        # If we see 0x0c or other types, this isn't a direct timestamp
        if data[start:start+1] != b'\x30':
            return None  # Not a number type, no direct timestamp here

        start += 1  # Skip type marker

        # Skip padding zeros
        while start < len(data) and data[start] == 0:
            start += 1
            if start - idx > 20:  # Safety limit
                break

        # Need 8 bytes for double
        if start + 8 > len(data):
            return None

        try:
            timestamp = struct.unpack('<d', data[start:start+8])[0]
            if timestamp > 0 and timestamp < 2000000000:  # Sanity check
                reference = datetime(2001, 1, 1)
                return reference + timedelta(seconds=timestamp)
        except:
            pass
        return None

    @staticmethod
    def extract_title_id(data: bytes) -> Optional[str]:
        """Extract 32-character titleID hash from binary data.

        Looks for 'ADCMediaItemTitleID' marker followed by the hash.
        """
        marker = b'ADCMediaItemTitleID'
        idx = data.find(marker)
        if idx == -1:
            return None

        # After marker, skip some bytes and look for 32-char hex hash
        # Pattern: marker + \x00\x08 + 32-char hash
        search_start = idx + len(marker)
        search_end = min(search_start + 50, len(data))  # Look within 50 bytes

        for i in range(search_start, search_end - 32):
            chunk = data[i:i+32]
            try:
                hex_str = chunk.decode('ascii')
                if all(c in '0123456789abcdef' for c in hex_str):
                    return hex_str
            except:
                continue
        return None

    @staticmethod
    def extract_session_uuid(data: bytes) -> Optional[str]:
        """Extract session UUID from historySessionItem data.

        The session UUID is stored after the 'uuid\\x00\\x08' marker.
        This is NOT the same as the play_id (which appears first after ADCHistorySessionItem).

        Binary structure:
        - ADCHistorySessionItem\\x00\\x08 + play_id (36 chars)
        - uuid\\x00\\x08 + session_id (36 chars)  <-- This is what we want
        """
        # Look for 'uuid\x00\x08' marker which precedes the session UUID
        marker = b'uuid\x00\x08'
        idx = data.find(marker)
        if idx == -1:
            return None

        # Session UUID starts immediately after the marker
        start = idx + len(marker)
        if start + 36 > len(data):
            return None

        try:
            uuid_str = data[start:start+36].decode('ascii')
            # Validate UUID format: 8-4-4-4-12 with hyphens
            if (len(uuid_str) == 36 and
                uuid_str[8] == '-' and uuid_str[13] == '-' and
                uuid_str[18] == '-' and uuid_str[23] == '-' and
                all(c in '0123456789abcdefABCDEF-' for c in uuid_str)):
                return uuid_str
        except:
            pass

        return None

    @staticmethod
    def extract_track_metadata(data: bytes) -> Tuple[str, str]:
        """Extract title and artist from historySessionItem data.

        The title and artist are stored as length-prefixed strings after the titleID.
        Format: ... titleID (32 hex chars) \x00\x05\x02\x08 <title> \x00\x08title\x00\x08 <artist> \x00\x08artist ...
        """
        # Find the titleID first as our anchor point
        marker = b'ADCMediaItemTitleID'
        idx = data.find(marker)
        if idx == -1:
            return "", ""

        # Search for title/artist after the titleID
        # Pattern: after titleID hash (32 chars), look for \x00\x05\x02\x08 then title
        search_start = idx + len(marker) + 35  # Skip marker + some padding + 32-char hash
        search_end = len(data)

        title = ""
        artist = ""

        # Look for \x00\x05\x02\x08 pattern which precedes title (after titleID ends with 0x30)
        # The titleID ends with hex char (0-9a-f) then \x00\x05\x02\x08
        pattern = b'\x00\x05\x02\x08'
        pattern_idx = data.find(pattern, idx)  # Search from after ADCMediaItemTitleID marker

        if pattern_idx != -1 and pattern_idx < search_end - 10:
            # Title is a null-terminated string after the pattern
            title_start = pattern_idx + len(pattern)

            # Find the end of title - look for \x00\x08title marker
            title_end_marker = b'\x00\x08title'
            title_end_idx = data.find(title_end_marker, title_start)

            if title_end_idx != -1 and title_end_idx > title_start:
                try:
                    title = data[title_start:title_end_idx].decode('utf-8', errors='ignore')
                except:
                    pass

                # Artist is after \x00\x08title\x00\x08, ending at \x00\x08artist
                artist_marker = b'\x00\x08title\x00\x08'
                artist_start_idx = data.find(artist_marker, title_end_idx)

                if artist_start_idx != -1:
                    artist_start = artist_start_idx + len(artist_marker)
                    artist_end_marker = b'\x00\x08artist'
                    artist_end_idx = data.find(artist_end_marker, artist_start)

                    if artist_end_idx != -1 and artist_end_idx > artist_start:
                        try:
                            artist = data[artist_start:artist_end_idx].decode('utf-8', errors='ignore')
                        except:
                            pass

        return title, artist

    @staticmethod
    def extract_metadata(data: bytes) -> Dict[str, Any]:
        """Extract metadata fields from binary blob."""
        result = {
            "title": None,
            "artist": None,
            "duration": None,
            "source_uri": None,
            "file_uri": None,
        }

        strings = YapDatabaseDecoder.extract_strings(data)

        # Look for common patterns
        for i, s in enumerate(strings):
            if s.startswith('title') and i + 1 < len(strings):
                result["title"] = strings[i + 1] if strings[i + 1] != 'artist' else None
            elif s.startswith('artist') and i + 1 < len(strings):
                result["artist"] = strings[i + 1] if strings[i + 1] != 'duration' else None

        # Find URIs
        result["source_uri"] = YapDatabaseDecoder.find_source_uri(data)
        result["file_uri"] = YapDatabaseDecoder.find_file_uri(data)

        return result


class DjayProUnifiedExporter:
    """Unified exporter for djay Pro library data."""

    def __init__(self, db_path: Path, output_dir: Path):
        self.db_path = db_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Data storage
        self.tracks: Dict[str, Track] = {}
        self.streaming_tracks: List[StreamingTrack] = []
        self.sessions: List[Session] = []
        self.session_tracks: List[SessionTrack] = []
        self.playlists: List[PlaylistEntry] = []

        # Statistics
        self.stats = {
            "total_tracks": 0,
            "local_tracks": 0,
            "streaming_tracks": 0,
            "beatport_tracks": 0,
            "soundcloud_tracks": 0,
            "spotify_tracks": 0,
            "apple_tracks": 0,
            "tidal_tracks": 0,
            "tracks_with_bpm": 0,
            "tracks_with_key": 0,
            "total_sessions": 0,
            "total_plays": 0,
            "total_playlists": 0,
        }

    def connect(self) -> sqlite3.Connection:
        """Open read-only connection to database."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def extract_local_tracks(self):
        """Extract local file tracks from the database."""
        logger.info("Extracting local tracks...")

        conn = self.connect()

        # Query for local tracks with metadata
        query = """
            SELECT
                m.rowid,
                m.titleID,
                m.bpm,
                m.musicalKeySignatureIndex,
                l.fileName,
                a.bpm as analyzed_bpm,
                a.keySignatureIndex as analyzed_key,
                a.manualBPM
            FROM secondaryIndex_mediaItemIndex m
            LEFT JOIN database2 d ON m.titleID = d.key AND d.collection = 'localMediaItemLocations'
            LEFT JOIN secondaryIndex_mediaItemLocationIndex l ON d.rowid = l.rowid
            LEFT JOIN secondaryIndex_mediaItemAnalyzedDataIndex a ON m.rowid = a.rowid
        """

        cursor = conn.execute(query)

        for row in cursor.fetchall():
            title_id = row["titleID"]
            if not title_id:
                continue

            # Get BPM - prefer manual, then analyzed, then index
            bpm = row["manualBPM"] or row["analyzed_bpm"] or row["bpm"]

            # Get key
            key_index = row["analyzed_key"] if row["analyzed_key"] is not None else row["musicalKeySignatureIndex"]
            key = KEY_SIGNATURE_MAP.get(int(key_index), None) if key_index is not None else None
            key_camelot = CAMELOT_MAP.get(key) if key else None

            # Get file info
            file_name = row["fileName"]
            title = Path(file_name).stem if file_name else f"[{title_id[:8]}]"

            # Clean title
            for suffix in ["_test_processed", " (1)", " (2)", " (3)"]:
                title = title.replace(suffix, "")

            track = Track(
                track_id=title_id,
                title=title.strip(),
                bpm=float(bpm) if bpm else None,
                key=key,
                key_camelot=key_camelot,
                source_type="local",
                file_path=file_name,
            )

            self.tracks[title_id] = track
            self.stats["local_tracks"] += 1

            if bpm:
                self.stats["tracks_with_bpm"] += 1
            if key:
                self.stats["tracks_with_key"] += 1

        conn.close()
        logger.info(f"  Extracted {self.stats['local_tracks']} local tracks")

    def extract_streaming_tracks(self):
        """Extract streaming service tracks from globalMediaItemLocations."""
        logger.info("Extracting streaming tracks...")

        conn = self.connect()

        # Query for global (streaming) media locations
        query = """
            SELECT key, data FROM database2
            WHERE collection = 'globalMediaItemLocations'
        """

        cursor = conn.execute(query)
        decoder = YapDatabaseDecoder()

        for row in cursor.fetchall():
            title_id = row["key"]
            data = row["data"]

            if not data:
                continue

            # Extract metadata from binary blob
            metadata = decoder.extract_metadata(data)
            source_uri = metadata.get("source_uri")

            if not source_uri:
                continue

            # Determine source type
            source_type = "unknown"
            source_track_id = source_uri

            for stype, prefix in STREAMING_SOURCES.items():
                if source_uri.startswith(prefix):
                    source_type = stype
                    source_track_id = source_uri.replace(prefix, "")
                    break

            # Build source URL
            source_url = None
            if source_type == "beatport":
                track_num = source_track_id.replace("track:", "")
                source_url = f"https://www.beatport.com/track/-/{track_num}"
            elif source_type == "soundcloud":
                track_num = source_track_id.replace("tracks:", "")
                source_url = f"https://soundcloud.com/tracks/{track_num}"
            elif source_type == "spotify":
                track_num = source_track_id.replace("track:", "")
                source_url = f"https://open.spotify.com/track/{track_num}"

            # Create or update track
            strings = decoder.extract_strings(data)
            title = metadata.get("title") or (strings[0] if strings else title_id[:8])
            artist = metadata.get("artist") or (strings[1] if len(strings) > 1 else "")

            if title_id not in self.tracks:
                track = Track(
                    track_id=title_id,
                    title=title,
                    artist=artist,
                    source_type=source_type,
                    source_id=source_uri,
                )
                self.tracks[title_id] = track
            else:
                # Update existing track with source info
                self.tracks[title_id].source_type = source_type
                self.tracks[title_id].source_id = source_uri

            # Create streaming track detail
            streaming_track = StreamingTrack(
                track_id=title_id,
                source_type=source_type,
                source_track_id=source_track_id,
                source_url=source_url,
                title=title,
                artist=artist,
            )
            self.streaming_tracks.append(streaming_track)

            # Update stats
            self.stats["streaming_tracks"] += 1
            if source_type == "beatport":
                self.stats["beatport_tracks"] += 1
            elif source_type == "soundcloud":
                self.stats["soundcloud_tracks"] += 1
            elif source_type == "spotify":
                self.stats["spotify_tracks"] += 1
            elif source_type == "apple":
                self.stats["apple_tracks"] += 1
            elif source_type == "tidal":
                self.stats["tidal_tracks"] += 1

        conn.close()
        logger.info(f"  Extracted {self.stats['streaming_tracks']} streaming tracks")
        logger.info(f"    Beatport: {self.stats['beatport_tracks']}")
        logger.info(f"    SoundCloud: {self.stats['soundcloud_tracks']}")
        logger.info(f"    Spotify: {self.stats['spotify_tracks']}")
        logger.info(f"    Apple: {self.stats['apple_tracks']}")

    def extract_sessions(self):
        """Extract DJ session history."""
        logger.info("Extracting session history...")

        conn = self.connect()
        decoder = YapDatabaseDecoder()

        # Extract sessions
        query = "SELECT key, data FROM database2 WHERE collection = 'historySessions'"
        cursor = conn.execute(query)

        session_track_counts = defaultdict(int)

        for row in cursor.fetchall():
            session_id = row["key"]
            data = row["data"]

            if not data:
                continue

            strings = decoder.extract_strings(data)

            # Parse session data
            device_name = ""
            for s in strings:
                if "MacBook" in s or "Mac" in s or "iPad" in s or "iPhone" in s:
                    device_name = s
                    break

            # Extract timestamps using new methods
            start_time = decoder.extract_coredata_timestamp(data, b'startDate')
            end_time = decoder.extract_coredata_timestamp(data, b'endDate')

            # Calculate duration if we have both timestamps
            duration_min = 0.0
            if start_time and end_time:
                duration_min = (end_time - start_time).total_seconds() / 60.0

            session = Session(
                session_id=session_id,
                device_name=device_name,
                start_time=start_time.isoformat() if start_time else None,
                end_time=end_time.isoformat() if end_time else None,
                duration_min=duration_min,
            )
            self.sessions.append(session)
            self.stats["total_sessions"] += 1

        # Extract session items (tracks played)
        query = "SELECT key, data FROM database2 WHERE collection = 'historySessionItems'"
        cursor = conn.execute(query)

        for row in cursor.fetchall():
            play_id = row["key"]
            data = row["data"]

            if not data:
                continue

            strings = decoder.extract_strings(data)

            # Extract session UUID using new method
            session_id = decoder.extract_session_uuid(data)

            # Fallback to string parsing if new method fails
            if not session_id:
                for s in strings:
                    if len(s) == 36 and s.count('-') == 4:
                        session_id = s
                        break

            # Extract titleID using new method
            track_id = decoder.extract_title_id(data)

            # Extract title and artist using new structured method
            title, artist = decoder.extract_track_metadata(data)

            # Fallback to string parsing if structured method fails
            if not title:
                for s in strings:
                    if len(s) > 3 and not s.startswith(('ADC', 'uuid', 'title', 'artist', 'deck', 'session', 'duration', 'startTim', 'deckNumb', 'QMFMF', 'TSAF')):
                        # Skip UUIDs and hashes
                        if len(s) == 36 and s.count('-') == 4:
                            continue
                        if len(s) == 32 and all(c in '0123456789abcdef' for c in s):
                            continue
                        if not title:
                            title = s
                        elif not artist:
                            artist = s

            if session_id:
                session_track_counts[session_id] += 1

            session_track = SessionTrack(
                play_id=play_id,
                session_id=session_id or "",
                track_id=track_id or "",  # Now properly extracted from ADCMediaItemTitleID
                title=title,
                artist=artist,
            )
            self.session_tracks.append(session_track)
            self.stats["total_plays"] += 1

        # Update session track counts
        for session in self.sessions:
            session.track_count = session_track_counts.get(session.session_id, 0)

        conn.close()
        logger.info(f"  Extracted {self.stats['total_sessions']} sessions")
        logger.info(f"  Extracted {self.stats['total_plays']} track plays")

        # Log stats on track linking
        linked_tracks = sum(1 for st in self.session_tracks if st.track_id)
        logger.info(f"  Linked {linked_tracks}/{len(self.session_tracks)} session tracks to titleIDs")

    def extract_playlists(self):
        """Extract playlist data."""
        logger.info("Extracting playlists...")

        conn = self.connect()
        decoder = YapDatabaseDecoder()

        # Extract playlists
        query = "SELECT key, data FROM database2 WHERE collection = 'mediaItemPlaylists'"
        cursor = conn.execute(query)

        playlist_names = {}

        for row in cursor.fetchall():
            playlist_id = row["key"]
            data = row["data"]

            if not data:
                continue

            strings = decoder.extract_strings(data)
            playlist_name = strings[0] if strings else playlist_id[:8]
            playlist_names[playlist_id] = playlist_name

        # Extract playlist items
        query = "SELECT key, data FROM database2 WHERE collection = 'mediaItemPlaylistItems'"
        cursor = conn.execute(query)

        for row in cursor.fetchall():
            item_key = row["key"]
            data = row["data"]

            if not data:
                continue

            strings = decoder.extract_strings(data)

            # Try to find playlist ID and track ID
            playlist_id = None
            track_id = None

            for s in strings:
                if s in playlist_names:
                    playlist_id = s
                elif len(s) == 32:  # Potential track ID (hash)
                    track_id = s

            if playlist_id and track_id:
                entry = PlaylistEntry(
                    playlist_id=playlist_id,
                    playlist_name=playlist_names.get(playlist_id, "Unknown"),
                    track_id=track_id,
                )
                self.playlists.append(entry)

        self.stats["total_playlists"] = len(playlist_names)

        conn.close()
        logger.info(f"  Extracted {self.stats['total_playlists']} playlists")
        logger.info(f"  Extracted {len(self.playlists)} playlist entries")

    def export_to_csv(self) -> Dict[str, Path]:
        """Export all data to CSV files."""
        logger.info("Exporting to CSV files...")

        output_files = {}

        # 1. Tracks CSV (living document - no timestamp)
        tracks_path = self.output_dir / "djay_library_tracks.csv"
        with open(tracks_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'track_id', 'title', 'artist', 'album', 'genre', 'duration_sec',
                'bpm', 'key', 'key_camelot', 'source_type', 'source_id', 'file_path',
                'added_date', 'last_played', 'play_count'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for track in self.tracks.values():
                writer.writerow(track.to_dict())
        output_files['tracks'] = tracks_path
        logger.info(f"  ✓ {tracks_path.name}: {len(self.tracks)} tracks")

        # 2. Streaming tracks CSV (living document - no timestamp)
        streaming_path = self.output_dir / "djay_library_streaming.csv"
        with open(streaming_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'track_id', 'source_type', 'source_track_id', 'source_url',
                'artist', 'title', 'duration_sec', 'is_available'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for st in self.streaming_tracks:
                writer.writerow(st.to_dict())
        output_files['streaming'] = streaming_path
        logger.info(f"  ✓ {streaming_path.name}: {len(self.streaming_tracks)} streaming tracks")

        # 3. Sessions CSV (living document - no timestamp)
        sessions_path = self.output_dir / "djay_session_history.csv"
        with open(sessions_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'session_id', 'device_name', 'device_type', 'start_time',
                'end_time', 'duration_min', 'track_count'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for session in self.sessions:
                writer.writerow(session.to_dict())
        output_files['sessions'] = sessions_path
        logger.info(f"  ✓ {sessions_path.name}: {len(self.sessions)} sessions")

        # 4. Session tracks CSV (living document - no timestamp)
        session_tracks_path = self.output_dir / "djay_session_tracks.csv"
        with open(session_tracks_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'play_id', 'session_id', 'track_id', 'deck_number',
                'play_start', 'title', 'artist', 'bpm'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for st in self.session_tracks:
                writer.writerow(st.to_dict())
        output_files['session_tracks'] = session_tracks_path
        logger.info(f"  ✓ {session_tracks_path.name}: {len(self.session_tracks)} plays")

        # 5. Playlists CSV (living document - no timestamp)
        playlists_path = self.output_dir / "djay_playlists.csv"
        with open(playlists_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'playlist_id', 'playlist_name', 'track_id', 'position', 'added_date'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self.playlists:
                writer.writerow(entry.to_dict())
        output_files['playlists'] = playlists_path
        logger.info(f"  ✓ {playlists_path.name}: {len(self.playlists)} entries")

        # Also create legacy format for backwards compatibility (living document - no timestamp)
        legacy_path = self.output_dir / "djay_pro_media_items.csv"
        with open(legacy_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = [
                'analyzed_bpm', 'bpm', 'fileName', 'file_path', 'key',
                'key_index', 'manual_bpm', 'title', 'titleID'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for track in self.tracks.values():
                row = {
                    'analyzed_bpm': '',
                    'bpm': track.bpm or '',
                    'fileName': track.file_path or '',
                    'file_path': track.file_path or '',
                    'key': track.key or '',
                    'key_index': '',
                    'manual_bpm': '',
                    'title': track.title,
                    'titleID': track.track_id,
                }
                writer.writerow(row)
        output_files['legacy'] = legacy_path
        logger.info(f"  ✓ {legacy_path.name}: {len(self.tracks)} tracks (legacy format)")

        return output_files

    def sync_to_google_sheets(self, spreadsheet_name: Optional[str] = None) -> Optional[str]:
        """Sync data to Google Sheets workbook."""
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError:
            logger.warning("gspread not installed - skipping Google Sheets sync")
            logger.warning("Install with: pip install gspread google-auth")
            return None

        logger.info("Syncing to Google Sheets...")

        # Find credentials
        creds_paths = [
            Path.home() / ".credentials" / "google-sheets-service-account.json",
            Path.home() / ".config" / "gspread" / "service_account.json",
            Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")),
        ]

        creds_path = None
        for p in creds_paths:
            if p.exists():
                creds_path = p
                break

        if not creds_path:
            logger.warning("No Google Sheets credentials found")
            return None

        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
            client = gspread.authorize(creds)

            # Create or open spreadsheet
            sheet_name = spreadsheet_name or f"djay Pro Library - {datetime.now().strftime('%Y-%m-%d')}"

            try:
                spreadsheet = client.open(sheet_name)
                logger.info(f"  Opened existing spreadsheet: {sheet_name}")
            except gspread.SpreadsheetNotFound:
                spreadsheet = client.create(sheet_name)
                logger.info(f"  Created new spreadsheet: {sheet_name}")

            # Update Tracks sheet
            self._update_sheet(spreadsheet, "Tracks",
                              ['track_id', 'title', 'artist', 'bpm', 'key', 'key_camelot',
                               'source_type', 'source_id', 'file_path'],
                              [t.to_dict() for t in self.tracks.values()])

            # Update Streaming sheet
            self._update_sheet(spreadsheet, "Streaming",
                              ['track_id', 'source_type', 'source_track_id', 'source_url', 'title', 'artist'],
                              [st.to_dict() for st in self.streaming_tracks])

            # Update Sessions sheet
            self._update_sheet(spreadsheet, "Sessions",
                              ['session_id', 'device_name', 'start_time', 'end_time', 'track_count'],
                              [s.to_dict() for s in self.sessions])

            # Update Play History sheet
            self._update_sheet(spreadsheet, "Play History",
                              ['play_id', 'session_id', 'title', 'artist'],
                              [st.to_dict() for st in self.session_tracks[:1000]])  # Limit for performance

            # Update Summary sheet
            summary_data = [
                ['Metric', 'Value'],
                ['Total Tracks', len(self.tracks)],
                ['Local Tracks', self.stats['local_tracks']],
                ['Streaming Tracks', self.stats['streaming_tracks']],
                ['Beatport', self.stats['beatport_tracks']],
                ['SoundCloud', self.stats['soundcloud_tracks']],
                ['Spotify', self.stats['spotify_tracks']],
                ['Apple Music', self.stats['apple_tracks']],
                ['Tracks with BPM', self.stats['tracks_with_bpm']],
                ['Tracks with Key', self.stats['tracks_with_key']],
                ['Total Sessions', self.stats['total_sessions']],
                ['Total Plays', self.stats['total_plays']],
                ['Last Updated', datetime.now().isoformat()],
            ]

            try:
                summary_sheet = spreadsheet.worksheet("Summary")
            except gspread.WorksheetNotFound:
                summary_sheet = spreadsheet.add_worksheet("Summary", rows=20, cols=5)

            summary_sheet.clear()
            summary_sheet.update('A1', summary_data)

            logger.info(f"  ✓ Synced to Google Sheets: {spreadsheet.url}")
            return spreadsheet.url

        except Exception as e:
            logger.error(f"  ✗ Google Sheets sync failed: {e}")
            return None

    def _update_sheet(self, spreadsheet, sheet_name: str, headers: List[str], data: List[Dict]):
        """Update or create a worksheet with data."""
        import gspread

        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(sheet_name, rows=max(len(data) + 1, 100), cols=len(headers))

        # Clear and update
        worksheet.clear()

        if not data:
            worksheet.update('A1', [headers])
            return

        # Prepare rows
        rows = [headers]
        for item in data:
            row = [str(item.get(h, '')) for h in headers]
            rows.append(row)

        # Batch update for performance
        worksheet.update('A1', rows)
        logger.info(f"    Updated {sheet_name}: {len(data)} rows")

    def run(self, sync_sheets: bool = False, sheet_name: Optional[str] = None) -> Dict[str, Any]:
        """Run the full export process."""
        logger.info("=" * 70)
        logger.info("DJAY PRO UNIFIED LIBRARY EXPORT")
        logger.info("=" * 70)
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Output: {self.output_dir}")
        logger.info("=" * 70)

        # Extract all data
        self.extract_local_tracks()
        self.extract_streaming_tracks()
        self.extract_sessions()
        self.extract_playlists()

        # Update total tracks
        self.stats["total_tracks"] = len(self.tracks)

        # Export to CSV
        csv_files = self.export_to_csv()

        # Sync to Google Sheets if requested
        sheets_url = None
        if sync_sheets:
            sheets_url = self.sync_to_google_sheets(sheet_name)

        # Summary
        logger.info("=" * 70)
        logger.info("EXPORT COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total tracks: {self.stats['total_tracks']}")
        logger.info(f"  Local: {self.stats['local_tracks']}")
        logger.info(f"  Streaming: {self.stats['streaming_tracks']}")
        logger.info(f"Sessions: {self.stats['total_sessions']}")
        logger.info(f"Track plays: {self.stats['total_plays']}")
        logger.info(f"Playlists: {self.stats['total_playlists']}")
        logger.info("=" * 70)

        return {
            "success": True,
            "stats": self.stats,
            "csv_files": {k: str(v) for k, v in csv_files.items()},
            "sheets_url": sheets_url,
            "export_time": datetime.now().isoformat(),
        }


def main():
    parser = argparse.ArgumentParser(
        description="djay Pro Unified Library Export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Output Files:
  djay_library_tracks.csv      - Complete track catalog
  djay_library_streaming.csv   - Streaming service details
  djay_session_history.csv     - DJ session records
  djay_session_tracks.csv      - Track play history
  djay_playlists.csv           - Playlist data
  djay_pro_media_items.csv     - Legacy format (backwards compatible)

Examples:
  %(prog)s                          # Export to CSV only
  %(prog)s --sync-sheets            # Export and sync to Google Sheets
  %(prog)s --sheet-name "My Library" # Use specific sheet name
        """
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to MediaLibrary.db (default: {DEFAULT_DB_PATH})"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})"
    )

    parser.add_argument(
        "--sync-sheets",
        action="store_true",
        help="Sync to Google Sheets"
    )

    parser.add_argument(
        "--sheet-name",
        type=str,
        help="Google Sheets workbook name"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        logger.error(f"Database not found: {args.db_path}")
        return 1

    exporter = DjayProUnifiedExporter(args.db_path, args.output_dir)
    result = exporter.run(sync_sheets=args.sync_sheets, sheet_name=args.sheet_name)

    if args.json:
        print(json.dumps(result, indent=2))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
