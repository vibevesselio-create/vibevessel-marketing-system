"""
Metadata extraction from audio files.

This module provides functions for extracting metadata from audio files
using mutagen and other libraries.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List, Any

from music_workflow.utils.errors import ProcessingError
from music_workflow.config.settings import get_settings


@dataclass
class ExtractedMetadata:
    """Metadata extracted from an audio file."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    duration_seconds: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bitrate: int = 0
    codec: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    comment: Optional[str] = None
    isrc: Optional[str] = None
    lyrics: Optional[str] = None
    artwork_data: Optional[bytes] = None
    custom_tags: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_tags is None:
            self.custom_tags = {}


class MetadataExtractor:
    """Extracts metadata from audio files.

    Supports multiple formats via mutagen:
    - MP3 (ID3 tags)
    - M4A/AAC (MP4 atoms)
    - FLAC (Vorbis comments)
    - WAV (RIFF INFO)
    - AIFF (ID3 tags)
    - OGG (Vorbis comments)
    """

    SUPPORTED_FORMATS = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aiff", ".ogg", ".opus"}

    def __init__(self):
        self._settings = get_settings()
        self._mutagen = None

    def _get_mutagen(self):
        """Lazy load mutagen."""
        if self._mutagen is None:
            try:
                import mutagen
                self._mutagen = mutagen
            except ImportError:
                raise ProcessingError(
                    "mutagen library not installed",
                    operation="metadata_extraction",
                    details={"hint": "pip install mutagen"},
                )
        return self._mutagen

    def extract(self, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from an audio file.

        Args:
            file_path: Path to the audio file

        Returns:
            ExtractedMetadata object

        Raises:
            ProcessingError: If extraction fails
        """
        if not file_path.exists():
            raise ProcessingError(
                f"File not found: {file_path}",
                file_path=str(file_path),
                operation="metadata_extraction",
            )

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ProcessingError(
                f"Unsupported format: {suffix}",
                file_path=str(file_path),
                operation="metadata_extraction",
            )

        mutagen = self._get_mutagen()

        try:
            audio = mutagen.File(file_path, easy=False)
            if audio is None:
                raise ProcessingError(
                    "Could not read audio file",
                    file_path=str(file_path),
                    operation="metadata_extraction",
                )

            # Extract based on format
            if suffix == ".mp3":
                return self._extract_mp3(audio, file_path)
            elif suffix in {".m4a", ".aac"}:
                return self._extract_m4a(audio, file_path)
            elif suffix == ".flac":
                return self._extract_flac(audio, file_path)
            elif suffix == ".wav":
                return self._extract_wav(audio, file_path)
            elif suffix == ".aiff":
                return self._extract_aiff(audio, file_path)
            elif suffix in {".ogg", ".opus"}:
                return self._extract_ogg(audio, file_path)
            else:
                return self._extract_generic(audio, file_path)

        except ProcessingError:
            raise
        except Exception as e:
            raise ProcessingError(
                f"Metadata extraction failed: {e}",
                file_path=str(file_path),
                operation="metadata_extraction",
            )

    def _extract_mp3(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from MP3 (ID3 tags)."""
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3

        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate
            metadata.channels = audio.info.channels if hasattr(audio.info, "channels") else 2
            metadata.bitrate = audio.info.bitrate if hasattr(audio.info, "bitrate") else 0
            metadata.codec = "mp3"

        tags = audio.tags
        if tags:
            metadata.title = self._get_id3_text(tags, "TIT2")
            metadata.artist = self._get_id3_text(tags, "TPE1")
            metadata.album = self._get_id3_text(tags, "TALB")
            metadata.album_artist = self._get_id3_text(tags, "TPE2")
            metadata.genre = self._get_id3_text(tags, "TCON")
            metadata.comment = self._get_id3_text(tags, "COMM")
            metadata.isrc = self._get_id3_text(tags, "TSRC")

            # Track number
            track = self._get_id3_text(tags, "TRCK")
            if track:
                try:
                    metadata.track_number = int(track.split("/")[0])
                except (ValueError, IndexError):
                    pass

            # Year
            year = self._get_id3_text(tags, "TDRC") or self._get_id3_text(tags, "TYER")
            if year:
                try:
                    metadata.year = int(str(year)[:4])
                except (ValueError, IndexError):
                    pass

            # BPM
            bpm = self._get_id3_text(tags, "TBPM")
            if bpm:
                try:
                    metadata.bpm = float(bpm)
                except ValueError:
                    pass

            # Key
            metadata.key = self._get_id3_text(tags, "TKEY")

            # Artwork
            for tag in tags.values():
                if tag.FrameID == "APIC":
                    metadata.artwork_data = tag.data
                    break

        return metadata

    def _extract_m4a(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from M4A/AAC (MP4 atoms)."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate
            metadata.channels = audio.info.channels
            metadata.bitrate = audio.info.bitrate if hasattr(audio.info, "bitrate") else 0
            metadata.codec = audio.info.codec if hasattr(audio.info, "codec") else "aac"

        tags = audio.tags
        if tags:
            metadata.title = self._get_mp4_text(tags, "\xa9nam")
            metadata.artist = self._get_mp4_text(tags, "\xa9ART")
            metadata.album = self._get_mp4_text(tags, "\xa9alb")
            metadata.album_artist = self._get_mp4_text(tags, "aART")
            metadata.genre = self._get_mp4_text(tags, "\xa9gen")
            metadata.comment = self._get_mp4_text(tags, "\xa9cmt")

            # Track number
            track = tags.get("trkn")
            if track and len(track) > 0:
                metadata.track_number = track[0][0]

            # Disc number
            disc = tags.get("disk")
            if disc and len(disc) > 0:
                metadata.disc_number = disc[0][0]

            # Year
            year = self._get_mp4_text(tags, "\xa9day")
            if year:
                try:
                    metadata.year = int(str(year)[:4])
                except (ValueError, IndexError):
                    pass

            # BPM
            bpm = tags.get("tmpo")
            if bpm:
                try:
                    metadata.bpm = float(bpm[0])
                except (ValueError, IndexError):
                    pass

            # Artwork
            if "covr" in tags:
                covers = tags["covr"]
                if covers:
                    metadata.artwork_data = bytes(covers[0])

        return metadata

    def _extract_flac(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from FLAC (Vorbis comments)."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate
            metadata.channels = audio.info.channels
            metadata.bitrate = audio.info.bits_per_sample if hasattr(audio.info, "bits_per_sample") else 0
            metadata.codec = "flac"

        tags = audio.tags
        if tags:
            metadata.title = self._get_vorbis_text(tags, "TITLE")
            metadata.artist = self._get_vorbis_text(tags, "ARTIST")
            metadata.album = self._get_vorbis_text(tags, "ALBUM")
            metadata.album_artist = self._get_vorbis_text(tags, "ALBUMARTIST")
            metadata.genre = self._get_vorbis_text(tags, "GENRE")
            metadata.comment = self._get_vorbis_text(tags, "COMMENT")
            metadata.isrc = self._get_vorbis_text(tags, "ISRC")

            # Track number
            track = self._get_vorbis_text(tags, "TRACKNUMBER")
            if track:
                try:
                    metadata.track_number = int(track.split("/")[0])
                except (ValueError, IndexError):
                    pass

            # Year
            year = self._get_vorbis_text(tags, "DATE")
            if year:
                try:
                    metadata.year = int(str(year)[:4])
                except (ValueError, IndexError):
                    pass

            # BPM
            bpm = self._get_vorbis_text(tags, "BPM")
            if bpm:
                try:
                    metadata.bpm = float(bpm)
                except ValueError:
                    pass

            # Key
            metadata.key = self._get_vorbis_text(tags, "KEY")

        # FLAC pictures
        if hasattr(audio, "pictures") and audio.pictures:
            metadata.artwork_data = audio.pictures[0].data

        return metadata

    def _extract_wav(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from WAV (RIFF INFO or ID3)."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate
            metadata.channels = audio.info.channels
            metadata.bitrate = audio.info.bits_per_sample if hasattr(audio.info, "bits_per_sample") else 16
            metadata.codec = "wav"

        # WAV files may have ID3 tags
        tags = audio.tags
        if tags:
            if hasattr(tags, "get"):
                metadata.title = self._get_id3_text(tags, "TIT2")
                metadata.artist = self._get_id3_text(tags, "TPE1")
                metadata.album = self._get_id3_text(tags, "TALB")

        return metadata

    def _extract_aiff(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from AIFF (ID3 tags)."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate
            metadata.channels = audio.info.channels
            metadata.bitrate = audio.info.bits_per_sample if hasattr(audio.info, "bits_per_sample") else 16
            metadata.codec = "aiff"

        tags = audio.tags
        if tags:
            metadata.title = self._get_id3_text(tags, "TIT2")
            metadata.artist = self._get_id3_text(tags, "TPE1")
            metadata.album = self._get_id3_text(tags, "TALB")
            metadata.album_artist = self._get_id3_text(tags, "TPE2")
            metadata.genre = self._get_id3_text(tags, "TCON")

        return metadata

    def _extract_ogg(self, audio, file_path: Path) -> ExtractedMetadata:
        """Extract metadata from OGG/Opus (Vorbis comments)."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = audio.info.length
            metadata.sample_rate = audio.info.sample_rate if hasattr(audio.info, "sample_rate") else 0
            metadata.channels = audio.info.channels
            metadata.codec = "opus" if file_path.suffix.lower() == ".opus" else "vorbis"

        tags = audio.tags
        if tags:
            metadata.title = self._get_vorbis_text(tags, "TITLE")
            metadata.artist = self._get_vorbis_text(tags, "ARTIST")
            metadata.album = self._get_vorbis_text(tags, "ALBUM")
            metadata.album_artist = self._get_vorbis_text(tags, "ALBUMARTIST")
            metadata.genre = self._get_vorbis_text(tags, "GENRE")

        return metadata

    def _extract_generic(self, audio, file_path: Path) -> ExtractedMetadata:
        """Generic metadata extraction for unknown formats."""
        metadata = ExtractedMetadata()

        if hasattr(audio, "info"):
            metadata.duration_seconds = getattr(audio.info, "length", 0)
            metadata.sample_rate = getattr(audio.info, "sample_rate", 0)
            metadata.channels = getattr(audio.info, "channels", 0)

        return metadata

    def _get_id3_text(self, tags, key: str) -> Optional[str]:
        """Get text from ID3 tag."""
        if key in tags:
            tag = tags[key]
            if hasattr(tag, "text") and tag.text:
                return str(tag.text[0])
        return None

    def _get_mp4_text(self, tags, key: str) -> Optional[str]:
        """Get text from MP4 atom."""
        value = tags.get(key)
        if value:
            return str(value[0]) if isinstance(value, list) else str(value)
        return None

    def _get_vorbis_text(self, tags, key: str) -> Optional[str]:
        """Get text from Vorbis comment."""
        value = tags.get(key) or tags.get(key.upper()) or tags.get(key.lower())
        if value:
            return str(value[0]) if isinstance(value, list) else str(value)
        return None


# Singleton instance
_extractor: Optional[MetadataExtractor] = None


def get_metadata_extractor() -> MetadataExtractor:
    """Get the global metadata extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = MetadataExtractor()
    return _extractor


def extract_metadata(file_path: Path) -> ExtractedMetadata:
    """Convenience function to extract metadata from a file."""
    return get_metadata_extractor().extract(file_path)
