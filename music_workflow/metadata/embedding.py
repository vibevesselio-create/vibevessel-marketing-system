"""
Metadata embedding into audio files.

This module provides functions for writing/embedding metadata into
audio files using mutagen.
"""

import os
from pathlib import Path
from typing import Dict, Optional, Any, Union
from dataclasses import dataclass

from music_workflow.utils.errors import ProcessingError
from music_workflow.config.settings import get_settings
from music_workflow.metadata.extraction import ExtractedMetadata


@dataclass
class EmbedResult:
    """Result of metadata embedding operation."""
    success: bool = False
    file_path: Optional[Path] = None
    fields_updated: int = 0
    error: Optional[str] = None


class MetadataEmbedder:
    """Embeds metadata into audio files.

    Supports multiple formats via mutagen:
    - MP3 (ID3v2.4 tags)
    - M4A/AAC (MP4 atoms)
    - FLAC (Vorbis comments)
    - AIFF (ID3 tags)
    - OGG/Opus (Vorbis comments)
    """

    SUPPORTED_FORMATS = {".mp3", ".m4a", ".aac", ".flac", ".aiff", ".ogg", ".opus"}

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
                    operation="metadata_embedding",
                    details={"hint": "pip install mutagen"},
                )
        return self._mutagen

    def embed(
        self,
        file_path: Path,
        metadata: Union[ExtractedMetadata, Dict[str, Any]],
        preserve_existing: bool = True,
    ) -> EmbedResult:
        """Embed metadata into an audio file.

        Args:
            file_path: Path to the audio file
            metadata: Metadata to embed (ExtractedMetadata or dict)
            preserve_existing: Whether to preserve existing tags

        Returns:
            EmbedResult with operation status

        Raises:
            ProcessingError: If embedding fails
        """
        if not file_path.exists():
            raise ProcessingError(
                f"File not found: {file_path}",
                file_path=str(file_path),
                operation="metadata_embedding",
            )

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ProcessingError(
                f"Unsupported format: {suffix}",
                file_path=str(file_path),
                operation="metadata_embedding",
            )

        # Convert dict to metadata object if needed
        if isinstance(metadata, dict):
            metadata = self._dict_to_metadata(metadata)

        mutagen = self._get_mutagen()

        try:
            audio = mutagen.File(file_path, easy=False)
            if audio is None:
                raise ProcessingError(
                    "Could not open audio file",
                    file_path=str(file_path),
                    operation="metadata_embedding",
                )

            # Embed based on format
            if suffix == ".mp3":
                fields = self._embed_mp3(audio, metadata, preserve_existing)
            elif suffix in {".m4a", ".aac"}:
                fields = self._embed_m4a(audio, metadata, preserve_existing)
            elif suffix == ".flac":
                fields = self._embed_flac(audio, metadata, preserve_existing)
            elif suffix == ".aiff":
                fields = self._embed_aiff(audio, metadata, preserve_existing)
            elif suffix in {".ogg", ".opus"}:
                fields = self._embed_ogg(audio, metadata, preserve_existing)
            else:
                return EmbedResult(
                    success=False,
                    file_path=file_path,
                    error=f"No embedder for format: {suffix}",
                )

            audio.save()

            return EmbedResult(
                success=True,
                file_path=file_path,
                fields_updated=fields,
            )

        except ProcessingError:
            raise
        except Exception as e:
            return EmbedResult(
                success=False,
                file_path=file_path,
                error=str(e),
            )

    def _embed_mp3(
        self,
        audio,
        metadata: ExtractedMetadata,
        preserve_existing: bool,
    ) -> int:
        """Embed metadata into MP3 (ID3v2.4 tags)."""
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TCON, TBPM, TKEY, TRCK, TDRC, COMM

        # Ensure ID3 tags exist
        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        fields = 0

        def set_tag(frame_class, value):
            nonlocal fields
            if value is not None:
                key = frame_class.__name__[:4]
                if not preserve_existing or key not in tags:
                    tags.add(frame_class(encoding=3, text=str(value)))
                    fields += 1

        set_tag(TIT2, metadata.title)
        set_tag(TPE1, metadata.artist)
        set_tag(TALB, metadata.album)
        set_tag(TPE2, metadata.album_artist)
        set_tag(TCON, metadata.genre)

        if metadata.bpm is not None:
            set_tag(TBPM, str(int(metadata.bpm)))
        if metadata.key is not None:
            set_tag(TKEY, metadata.key)
        if metadata.track_number is not None:
            set_tag(TRCK, str(metadata.track_number))
        if metadata.year is not None:
            set_tag(TDRC, str(metadata.year))
        if metadata.comment is not None:
            if not preserve_existing or "COMM" not in tags:
                tags.add(COMM(encoding=3, lang="eng", desc="", text=metadata.comment))
                fields += 1

        # Artwork
        if metadata.artwork_data and (not preserve_existing or "APIC" not in tags):
            from mutagen.id3 import APIC
            tags.add(APIC(
                encoding=3,
                mime="image/jpeg",
                type=3,  # Cover (front)
                desc="Cover",
                data=metadata.artwork_data,
            ))
            fields += 1

        return fields

    def _embed_m4a(
        self,
        audio,
        metadata: ExtractedMetadata,
        preserve_existing: bool,
    ) -> int:
        """Embed metadata into M4A/AAC (MP4 atoms)."""
        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        fields = 0

        def set_tag(key, value):
            nonlocal fields
            if value is not None:
                if not preserve_existing or key not in tags:
                    tags[key] = [value] if not isinstance(value, list) else value
                    fields += 1

        set_tag("\xa9nam", metadata.title)
        set_tag("\xa9ART", metadata.artist)
        set_tag("\xa9alb", metadata.album)
        set_tag("aART", metadata.album_artist)
        set_tag("\xa9gen", metadata.genre)
        set_tag("\xa9cmt", metadata.comment)

        if metadata.bpm is not None:
            set_tag("tmpo", [int(metadata.bpm)])

        if metadata.track_number is not None:
            set_tag("trkn", [(metadata.track_number, 0)])

        if metadata.disc_number is not None:
            set_tag("disk", [(metadata.disc_number, 0)])

        if metadata.year is not None:
            set_tag("\xa9day", str(metadata.year))

        # Artwork
        if metadata.artwork_data and (not preserve_existing or "covr" not in tags):
            from mutagen.mp4 import MP4Cover
            tags["covr"] = [MP4Cover(metadata.artwork_data, imageformat=MP4Cover.FORMAT_JPEG)]
            fields += 1

        return fields

    def _embed_flac(
        self,
        audio,
        metadata: ExtractedMetadata,
        preserve_existing: bool,
    ) -> int:
        """Embed metadata into FLAC (Vorbis comments)."""
        fields = 0

        def set_tag(key, value):
            nonlocal fields
            if value is not None:
                if not preserve_existing or key not in audio:
                    audio[key] = str(value)
                    fields += 1

        set_tag("TITLE", metadata.title)
        set_tag("ARTIST", metadata.artist)
        set_tag("ALBUM", metadata.album)
        set_tag("ALBUMARTIST", metadata.album_artist)
        set_tag("GENRE", metadata.genre)
        set_tag("COMMENT", metadata.comment)

        if metadata.bpm is not None:
            set_tag("BPM", str(int(metadata.bpm)))
        if metadata.key is not None:
            set_tag("KEY", metadata.key)
        if metadata.track_number is not None:
            set_tag("TRACKNUMBER", str(metadata.track_number))
        if metadata.year is not None:
            set_tag("DATE", str(metadata.year))
        if metadata.isrc is not None:
            set_tag("ISRC", metadata.isrc)

        # Artwork
        if metadata.artwork_data and (not preserve_existing or not audio.pictures):
            from mutagen.flac import Picture
            picture = Picture()
            picture.type = 3  # Cover (front)
            picture.mime = "image/jpeg"
            picture.data = metadata.artwork_data
            audio.add_picture(picture)
            fields += 1

        return fields

    def _embed_aiff(
        self,
        audio,
        metadata: ExtractedMetadata,
        preserve_existing: bool,
    ) -> int:
        """Embed metadata into AIFF (ID3 tags)."""
        # AIFF uses ID3 tags similar to MP3
        return self._embed_mp3(audio, metadata, preserve_existing)

    def _embed_ogg(
        self,
        audio,
        metadata: ExtractedMetadata,
        preserve_existing: bool,
    ) -> int:
        """Embed metadata into OGG/Opus (Vorbis comments)."""
        fields = 0

        def set_tag(key, value):
            nonlocal fields
            if value is not None:
                if not preserve_existing or key not in audio:
                    audio[key] = str(value)
                    fields += 1

        set_tag("TITLE", metadata.title)
        set_tag("ARTIST", metadata.artist)
        set_tag("ALBUM", metadata.album)
        set_tag("ALBUMARTIST", metadata.album_artist)
        set_tag("GENRE", metadata.genre)

        if metadata.bpm is not None:
            set_tag("BPM", str(int(metadata.bpm)))
        if metadata.key is not None:
            set_tag("KEY", metadata.key)
        if metadata.track_number is not None:
            set_tag("TRACKNUMBER", str(metadata.track_number))
        if metadata.year is not None:
            set_tag("DATE", str(metadata.year))

        return fields

    def _dict_to_metadata(self, d: Dict[str, Any]) -> ExtractedMetadata:
        """Convert dictionary to ExtractedMetadata."""
        return ExtractedMetadata(
            title=d.get("title"),
            artist=d.get("artist"),
            album=d.get("album"),
            album_artist=d.get("album_artist"),
            track_number=d.get("track_number"),
            disc_number=d.get("disc_number"),
            year=d.get("year"),
            genre=d.get("genre"),
            bpm=d.get("bpm"),
            key=d.get("key"),
            comment=d.get("comment"),
            isrc=d.get("isrc"),
            artwork_data=d.get("artwork_data"),
        )


# Singleton instance
_embedder: Optional[MetadataEmbedder] = None


def get_metadata_embedder() -> MetadataEmbedder:
    """Get the global metadata embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = MetadataEmbedder()
    return _embedder


def embed_metadata(
    file_path: Path,
    metadata: Union[ExtractedMetadata, Dict[str, Any]],
    preserve_existing: bool = True,
) -> EmbedResult:
    """Convenience function to embed metadata into a file."""
    return get_metadata_embedder().embed(file_path, metadata, preserve_existing)
