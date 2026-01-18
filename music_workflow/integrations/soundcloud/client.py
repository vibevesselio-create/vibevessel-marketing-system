"""
SoundCloud integration client for music workflow.

This module provides SoundCloud integration via yt-dlp for downloading
tracks and extracting metadata. SoundCloud does not have a public API,
so we rely on yt-dlp for data extraction.
"""

import os
import re
import subprocess
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from music_workflow.utils.errors import DownloadError, IntegrationError
from music_workflow.config.settings import get_settings


class SoundCloudIntegrationError(IntegrationError):
    """SoundCloud-specific integration error."""

    def __init__(self, message: str, url: Optional[str] = None, **kwargs):
        super().__init__(message, service="soundcloud", **kwargs)
        self.url = url


@dataclass
class SoundCloudTrack:
    """Represents a SoundCloud track with metadata."""
    id: str
    title: str
    artist: str
    url: str
    duration_seconds: int = 0
    genre: Optional[str] = None
    description: Optional[str] = None
    artwork_url: Optional[str] = None
    waveform_url: Optional[str] = None
    play_count: int = 0
    like_count: int = 0
    repost_count: int = 0
    comment_count: int = 0
    upload_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    bpm: Optional[float] = None


@dataclass
class SoundCloudPlaylist:
    """Represents a SoundCloud playlist."""
    id: str
    title: str
    url: str
    creator: Optional[str] = None
    description: Optional[str] = None
    track_count: int = 0
    artwork_url: Optional[str] = None
    tracks: List[SoundCloudTrack] = field(default_factory=list)


class SoundCloudClient:
    """SoundCloud client using yt-dlp for track extraction.

    This client provides methods for:
    - Extracting track metadata
    - Downloading audio files
    - Extracting playlist information
    """

    SOUNDCLOUD_URL_PATTERN = re.compile(
        r"https?://(?:www\.|m\.)?soundcloud\.com/[\w-]+/[\w-]+"
    )
    SOUNDCLOUD_PLAYLIST_PATTERN = re.compile(
        r"https?://(?:www\.|m\.)?soundcloud\.com/[\w-]+/sets/[\w-]+"
    )

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        default_format: str = "m4a",
        ytdlp_path: Optional[str] = None,
    ):
        """Initialize the SoundCloud client.

        Args:
            output_dir: Default output directory for downloads
            default_format: Default audio format (m4a, mp3, wav, etc.)
            ytdlp_path: Path to yt-dlp executable
        """
        self._settings = get_settings()
        self._output_dir = output_dir or Path(os.getenv("DOWNLOAD_DIR", "/tmp"))
        self._default_format = default_format
        self._ytdlp_path = ytdlp_path or "yt-dlp"

    def is_soundcloud_url(self, url: str) -> bool:
        """Check if URL is a valid SoundCloud track URL."""
        return bool(self.SOUNDCLOUD_URL_PATTERN.match(url))

    def is_playlist_url(self, url: str) -> bool:
        """Check if URL is a SoundCloud playlist/set URL."""
        return bool(self.SOUNDCLOUD_PLAYLIST_PATTERN.match(url))

    def extract_info(self, url: str) -> Optional[Dict]:
        """Extract metadata from a SoundCloud URL without downloading.

        Args:
            url: SoundCloud track or playlist URL

        Returns:
            Metadata dictionary or None if extraction fails
        """
        try:
            cmd = [
                self._ytdlp_path,
                "--dump-json",
                "--no-download",
                "--no-warnings",
                url,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return None

            return json.loads(result.stdout)

        except subprocess.TimeoutExpired:
            raise SoundCloudIntegrationError(
                "Metadata extraction timed out",
                url=url,
                details={"timeout": 60},
            )
        except json.JSONDecodeError:
            return None
        except Exception as e:
            raise SoundCloudIntegrationError(
                f"Failed to extract metadata: {e}",
                url=url,
            )

    def get_track(self, url: str) -> Optional[SoundCloudTrack]:
        """Get track metadata from URL.

        Args:
            url: SoundCloud track URL

        Returns:
            SoundCloudTrack object or None
        """
        if not self.is_soundcloud_url(url):
            return None

        info = self.extract_info(url)
        if not info:
            return None

        return self._parse_track(info)

    def get_playlist(self, url: str, include_tracks: bool = True) -> Optional[SoundCloudPlaylist]:
        """Get playlist metadata and optionally all tracks.

        Args:
            url: SoundCloud playlist/set URL
            include_tracks: Whether to fetch all track metadata

        Returns:
            SoundCloudPlaylist object or None
        """
        if not self.is_playlist_url(url):
            return None

        try:
            if include_tracks:
                cmd = [
                    self._ytdlp_path,
                    "--dump-json",
                    "--flat-playlist",
                    "--no-download",
                    "--no-warnings",
                    url,
                ]
            else:
                cmd = [
                    self._ytdlp_path,
                    "--dump-single-json",
                    "--flat-playlist",
                    "--no-download",
                    "--no-warnings",
                    url,
                ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                return None

            # For flat playlist, each line is a JSON object
            if include_tracks:
                entries = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

                if not entries:
                    return None

                playlist = SoundCloudPlaylist(
                    id=entries[0].get("playlist_id", ""),
                    title=entries[0].get("playlist_title", "Unknown Playlist"),
                    url=url,
                    creator=entries[0].get("playlist_uploader"),
                    track_count=len(entries),
                )

                for entry in entries:
                    if entry.get("url"):
                        track_info = self.extract_info(entry["url"])
                        if track_info:
                            playlist.tracks.append(self._parse_track(track_info))

                return playlist
            else:
                data = json.loads(result.stdout)
                return SoundCloudPlaylist(
                    id=data.get("id", ""),
                    title=data.get("title", "Unknown Playlist"),
                    url=url,
                    creator=data.get("uploader"),
                    description=data.get("description"),
                    track_count=len(data.get("entries", [])),
                )

        except subprocess.TimeoutExpired:
            raise SoundCloudIntegrationError(
                "Playlist extraction timed out",
                url=url,
            )
        except Exception as e:
            raise SoundCloudIntegrationError(
                f"Failed to get playlist: {e}",
                url=url,
            )

    def download(
        self,
        url: str,
        output_dir: Optional[Path] = None,
        formats: Optional[List[str]] = None,
        template: str = "%(title)s - %(uploader)s.%(ext)s",
    ) -> Dict[str, Path]:
        """Download track from SoundCloud.

        Args:
            url: SoundCloud track URL
            output_dir: Output directory (uses default if not specified)
            formats: List of formats to download (default: [m4a])
            template: Output filename template

        Returns:
            Dictionary mapping format to file path

        Raises:
            DownloadError: If download fails
        """
        output_dir = output_dir or self._output_dir
        formats = formats or [self._default_format]
        output_dir.mkdir(parents=True, exist_ok=True)

        downloaded_files: Dict[str, Path] = {}

        for audio_format in formats:
            output_template = str(output_dir / template)

            cmd = [
                self._ytdlp_path,
                "-x",  # Extract audio
                "--audio-format", audio_format,
                "--audio-quality", "0",  # Best quality
                "-o", output_template,
                "--no-playlist",  # Single track only
                "--embed-metadata",
                "--embed-thumbnail",
                url,
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                if result.returncode != 0:
                    raise DownloadError(
                        f"Download failed: {result.stderr[:500]}",
                        url=url,
                        source="soundcloud",
                    )

                # Find the downloaded file
                for f in output_dir.iterdir():
                    if f.suffix.lower() == f".{audio_format}":
                        downloaded_files[audio_format] = f
                        break

            except subprocess.TimeoutExpired:
                raise DownloadError(
                    "Download timed out",
                    url=url,
                    source="soundcloud",
                    details={"timeout": 300},
                )
            except DownloadError:
                raise
            except Exception as e:
                raise DownloadError(
                    f"Download failed: {e}",
                    url=url,
                    source="soundcloud",
                )

        return downloaded_files

    def search(self, query: str, limit: int = 10) -> List[str]:
        """Search SoundCloud for tracks.

        Note: yt-dlp supports SoundCloud search via "scsearch:" prefix.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of track URLs
        """
        try:
            cmd = [
                self._ytdlp_path,
                "--dump-json",
                "--flat-playlist",
                "--no-download",
                "--no-warnings",
                f"scsearch{limit}:{query}",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return []

            urls = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("url"):
                            urls.append(data["url"])
                    except json.JSONDecodeError:
                        continue

            return urls[:limit]

        except Exception:
            return []

    def _parse_track(self, info: Dict) -> SoundCloudTrack:
        """Parse yt-dlp info dict into SoundCloudTrack."""
        return SoundCloudTrack(
            id=str(info.get("id", "")),
            title=info.get("title", "Unknown"),
            artist=info.get("uploader", "Unknown"),
            url=info.get("webpage_url", info.get("url", "")),
            duration_seconds=int(info.get("duration", 0)),
            genre=info.get("genre"),
            description=info.get("description"),
            artwork_url=info.get("thumbnail"),
            play_count=int(info.get("view_count", 0)),
            like_count=int(info.get("like_count", 0)),
            repost_count=int(info.get("repost_count", 0)),
            comment_count=int(info.get("comment_count", 0)),
            upload_date=info.get("upload_date"),
            tags=info.get("tags", []) or [],
        )

    def is_available(self) -> bool:
        """Check if yt-dlp is available for SoundCloud."""
        try:
            result = subprocess.run(
                [self._ytdlp_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False


# Singleton instance
_soundcloud_client: Optional[SoundCloudClient] = None


def get_soundcloud_client() -> SoundCloudClient:
    """Get the global SoundCloud client instance."""
    global _soundcloud_client
    if _soundcloud_client is None:
        _soundcloud_client = SoundCloudClient()
    return _soundcloud_client
