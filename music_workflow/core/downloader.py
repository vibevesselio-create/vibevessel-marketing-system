"""
Download logic for music workflow.

This module provides multi-source audio download capabilities using yt-dlp
as the download engine.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from music_workflow.core.models import DownloadResult, TrackInfo
from music_workflow.utils.errors import DownloadError, DRMProtectionError
from music_workflow.utils.validators import validate_url
from music_workflow.config.constants import Platform


@dataclass
class DownloadOptions:
    """Options for download operations."""
    output_dir: Path
    formats: List[str]
    audio_only: bool = True
    extract_metadata: bool = True
    max_retries: int = 3
    timeout: int = 300
    youtube_fallback: bool = True
    output_template: str = "%(title)s.%(ext)s"


class Downloader:
    """Multi-source audio downloader.

    Supports downloading from YouTube, SoundCloud, Bandcamp, and other
    sources supported by yt-dlp. Includes YouTube search fallback for
    DRM-protected Spotify content.
    """

    def __init__(self, options: Optional[DownloadOptions] = None):
        """Initialize the downloader.

        Args:
            options: Download options
        """
        # 2026-01-16: Updated default formats for new 3-file output structure
        # WAV and AIFF go to Eagle Library, WAV copy to playlist-tracks
        self.options = options or DownloadOptions(
            output_dir=Path("/tmp/music_downloads"),
            formats=["wav", "aiff"],  # M4A removed from default chain
        )
        self._yt_dlp = None

    def _get_yt_dlp(self):
        """Get or create yt-dlp instance (lazy loading)."""
        if self._yt_dlp is None:
            try:
                import yt_dlp
                self._yt_dlp = yt_dlp
            except ImportError:
                raise DownloadError(
                    "yt-dlp is not installed",
                    details={"hint": "Install with: pip install yt-dlp"},
                )
        return self._yt_dlp

    def download(
        self,
        url: str,
        output_dir: Optional[Path] = None,
        formats: Optional[List[str]] = None,
    ) -> DownloadResult:
        """Download audio from URL.

        Args:
            url: Source URL
            output_dir: Output directory (overrides default)
            formats: Output formats (overrides default)

        Returns:
            DownloadResult with file paths and metadata

        Raises:
            DownloadError: If download fails
            DRMProtectionError: If content is DRM-protected
        """
        # Validate URL
        is_valid, platform = validate_url(url)

        # Check for Spotify (DRM protected)
        if platform == Platform.SPOTIFY:
            if self.options.youtube_fallback:
                return self._download_via_youtube_search(url)
            raise DRMProtectionError(
                "Spotify content is DRM-protected",
                url=url,
                platform="spotify",
            )

        # Set up yt-dlp options
        output_dir = output_dir or self.options.output_dir
        formats = formats or self.options.formats

        yt_dlp = self._get_yt_dlp()
        ydl_opts = self._build_ydl_options(output_dir, formats)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return self._process_download_result(info, output_dir, formats)
        except Exception as e:
            error_msg = str(e)
            if "DRM" in error_msg or "protected" in error_msg.lower():
                raise DRMProtectionError(
                    f"Content is DRM-protected: {error_msg}",
                    url=url,
                    platform=platform,
                )
            raise DownloadError(
                f"Download failed: {error_msg}",
                url=url,
                source=platform,
                details={"error": error_msg},
            )

    def _build_ydl_options(
        self, output_dir: Path, formats: List[str]
    ) -> Dict[str, Any]:
        """Build yt-dlp options dictionary."""
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / self.options.output_template),
            "extractaudio": True,
            "audioformat": formats[0] if formats else "m4a",
            "audioquality": 0,  # Best quality
            "noplaylist": True,
            "ignoreerrors": False,
            "retries": self.options.max_retries,
            "socket_timeout": self.options.timeout,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": formats[0] if formats else "m4a",
                    "preferredquality": "0",
                }
            ],
        }

    def _process_download_result(
        self, info: Dict, output_dir: Path, formats: List[str]
    ) -> DownloadResult:
        """Process yt-dlp result into DownloadResult."""
        files = []

        # Find downloaded files
        if info:
            title = info.get("title", "unknown")
            for fmt in formats:
                potential_path = output_dir / f"{title}.{fmt}"
                if potential_path.exists():
                    files.append(potential_path)

        return DownloadResult(
            success=len(files) > 0,
            files=files,
            metadata=info or {},
            source_url=info.get("webpage_url") if info else None,
            duration_seconds=info.get("duration") if info else None,
        )

    def _download_via_youtube_search(self, spotify_url: str) -> DownloadResult:
        """Download Spotify track via YouTube search fallback.

        Args:
            spotify_url: Spotify track URL

        Returns:
            DownloadResult from YouTube search

        Raises:
            DRMProtectionError: If YouTube search fails
        """
        try:
            # Try to get track info from Spotify
            from music_workflow.integrations.spotify import SpotifyClient

            client = SpotifyClient()

            # Extract track ID from URL
            track_id = None
            if "/track/" in spotify_url:
                track_id = spotify_url.split("/track/")[1].split("?")[0]

            if track_id:
                track = client.get_track(track_id)
                if track:
                    # Build search query
                    artists = ", ".join(track.artists) if track.artists else "Unknown"
                    query = f"{track.name} {artists}"

                    # Search YouTube
                    youtube_url = self.search_youtube(query)
                    if youtube_url:
                        # Download from YouTube
                        return self.download(youtube_url)

            # Fallback: try generic search
            raise DRMProtectionError(
                "Could not find track on YouTube",
                url=spotify_url,
                platform="spotify",
            )

        except ImportError:
            raise DRMProtectionError(
                "Spotify integration not available for YouTube fallback",
                url=spotify_url,
                platform="spotify",
            )
        except Exception as e:
            raise DRMProtectionError(
                f"YouTube search fallback failed: {e}",
                url=spotify_url,
                platform="spotify",
            )

    def search_youtube(self, query: str, max_results: int = 1) -> Optional[str]:
        """Search YouTube for a track.

        Args:
            query: Search query (e.g., "Artist - Track Title")
            max_results: Maximum results to return

        Returns:
            YouTube URL if found, None otherwise
        """
        yt_dlp = self._get_yt_dlp()

        search_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
        }

        try:
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                result = ydl.extract_info(
                    f"ytsearch{max_results}:{query}",
                    download=False,
                )
                if result and result.get("entries"):
                    entry = result["entries"][0]
                    return f"https://www.youtube.com/watch?v={entry['id']}"
        except Exception:
            pass

        return None

    def get_metadata(self, url: str) -> Dict[str, Any]:
        """Get metadata for a URL without downloading.

        Args:
            url: Source URL

        Returns:
            Metadata dictionary
        """
        yt_dlp = self._get_yt_dlp()

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False) or {}
        except Exception as e:
            raise DownloadError(
                f"Failed to extract metadata: {e}",
                url=url,
                details={"error": str(e)},
            )
