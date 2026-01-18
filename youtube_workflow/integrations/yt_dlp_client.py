"""yt-dlp integration for YouTube search and download.

Provides a clean wrapper around yt-dlp with multi-strategy search
and configurable download options.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from youtube_workflow.core.models import (
    DownloadResult,
    SearchResult,
    SearchStrategy,
    VideoInfo,
    VideoStatus,
)
from youtube_workflow.utils.errors import DownloadError, SearchError, VideoUnavailableError

logger = logging.getLogger(__name__)


class YtDlpClient:
    """Client for YouTube operations using yt-dlp.

    Provides:
    - Multi-strategy search
    - Audio/video download with format selection
    - Metadata extraction
    - Duration-based matching
    """

    # Lazy-loaded yt-dlp module
    _yt_dlp = None

    def __init__(
        self,
        output_dir: Optional[Union[str, Path]] = None,
        audio_format: str = "wav",
        video_format: str = "mp4",
        quiet: bool = True,
    ):
        """Initialize the yt-dlp client.

        Args:
            output_dir: Directory for downloaded files
            audio_format: Target audio format (wav, mp3, m4a, etc.)
            video_format: Target video format (mp4, mkv, etc.)
            quiet: Suppress yt-dlp output
        """
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.audio_format = audio_format
        self.video_format = video_format
        self.quiet = quiet

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def yt_dlp(self):
        """Lazy-load yt-dlp module."""
        if self._yt_dlp is None:
            try:
                import yt_dlp
                self._yt_dlp = yt_dlp
            except ImportError:
                raise ImportError(
                    "yt-dlp is required for YouTube operations. "
                    "Install with: pip install yt-dlp"
                )
        return self._yt_dlp

    def search(
        self,
        query: str,
        max_results: int = 5,
        target_duration_seconds: Optional[int] = None,
    ) -> SearchResult:
        """Search YouTube for videos.

        Args:
            query: Search query string
            max_results: Maximum number of results
            target_duration_seconds: Target duration for matching

        Returns:
            SearchResult with matching videos
        """
        start_time = time.time()

        ydl_opts = {
            "quiet": self.quiet,
            "no_warnings": self.quiet,
            "extract_flat": True,
            "skip_download": True,
        }

        search_url = f"ytsearch{max_results}:{query}"

        try:
            with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=False)

            videos = []
            for entry in info.get("entries", []):
                if entry:
                    video = VideoInfo.from_yt_dlp(entry)
                    video.status = VideoStatus.FOUND
                    videos.append(video)

            search_time = int((time.time() - start_time) * 1000)

            result = SearchResult(
                query=query,
                strategy=SearchStrategy.EXACT,
                results=videos,
                target_duration_seconds=target_duration_seconds,
                search_time_ms=search_time,
                api_used="yt_dlp",
            )

            # Find best match if duration target provided
            if target_duration_seconds:
                result.find_best_match()

            logger.info(f"Search '{query}' found {len(videos)} results in {search_time}ms")
            return result

        except Exception as e:
            raise SearchError(f"Search failed: {e}", query=query)

    def search_multi_strategy(
        self,
        artist: str,
        title: str,
        target_duration_seconds: Optional[int] = None,
        max_results_per_strategy: int = 3,
    ) -> SearchResult:
        """Search using multiple strategies to find the best match.

        Strategies tried in order:
        1. Artist + Title + "official audio"
        2. Artist + Title (exact)
        3. Artist + Title + "audio"
        4. Title only
        5. Cleaned title (remove featuring, etc.)
        6. First artist only

        Args:
            artist: Artist name
            title: Track title
            target_duration_seconds: Target duration for matching
            max_results_per_strategy: Max results per search strategy

        Returns:
            SearchResult with best match from all strategies
        """
        strategies = [
            (SearchStrategy.OFFICIAL_AUDIO, f"{artist} {title} official audio"),
            (SearchStrategy.EXACT, f"{artist} {title}"),
            (SearchStrategy.AUDIO_ONLY, f"{artist} {title} audio"),
            (SearchStrategy.TITLE_ONLY, title),
        ]

        # Add cleaned title strategy
        cleaned_title = self._clean_title(title)
        if cleaned_title != title:
            strategies.append((SearchStrategy.CLEANED, f"{artist} {cleaned_title}"))

        # Add first artist strategy for multi-artist tracks
        first_artist = self._get_first_artist(artist)
        if first_artist != artist:
            strategies.append((SearchStrategy.FIRST_ARTIST, f"{first_artist} {title}"))

        all_results = []
        best_match = None
        best_strategy = None

        for strategy, query in strategies:
            try:
                result = self.search(
                    query=query,
                    max_results=max_results_per_strategy,
                    target_duration_seconds=target_duration_seconds,
                )

                for video in result.results:
                    video.match_strategy = strategy
                    all_results.append(video)

                # Check if we found a good match
                if result.best_match and target_duration_seconds:
                    if (best_match is None or
                        result.best_match.duration_diff_seconds < best_match.duration_diff_seconds):
                        best_match = result.best_match
                        best_strategy = strategy

                        # If perfect match (within 2 seconds), stop searching
                        if result.best_match.duration_diff_seconds <= 2:
                            break

            except SearchError as e:
                logger.warning(f"Strategy {strategy.value} failed: {e}")
                continue

        final_result = SearchResult(
            query=f"{artist} - {title}",
            strategy=best_strategy or SearchStrategy.EXACT,
            results=all_results,
            target_duration_seconds=target_duration_seconds,
            best_match=best_match,
            api_used="yt_dlp",
        )

        return final_result

    def get_video_info(self, url: str) -> VideoInfo:
        """Get detailed info for a specific video.

        Args:
            url: YouTube video URL

        Returns:
            VideoInfo with full metadata
        """
        ydl_opts = {
            "quiet": self.quiet,
            "no_warnings": self.quiet,
            "skip_download": True,
        }

        try:
            with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            video = VideoInfo.from_yt_dlp(info)
            video.status = VideoStatus.FOUND
            return video

        except self.yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Private video" in error_msg or "unavailable" in error_msg.lower():
                raise VideoUnavailableError(
                    f"Video unavailable: {error_msg}",
                    video_id=self._extract_video_id(url),
                    reason="unavailable"
                )
            raise DownloadError(f"Failed to get video info: {e}", url=url)

    def download_audio(
        self,
        url: str,
        output_template: Optional[str] = None,
    ) -> DownloadResult:
        """Download audio from a YouTube video.

        Args:
            url: YouTube video URL
            output_template: Custom output filename template

        Returns:
            DownloadResult with audio file path
        """
        video = self.get_video_info(url)
        video.status = VideoStatus.DOWNLOADING

        output_template = output_template or str(
            self.output_dir / "%(title)s.%(ext)s"
        )

        ydl_opts = {
            "quiet": self.quiet,
            "no_warnings": self.quiet,
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.audio_format,
                "preferredquality": "0",  # Best quality
            }],
        }

        start_time = time.time()

        try:
            with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            # Determine output file path
            base_path = Path(ydl.prepare_filename(info))
            audio_path = base_path.with_suffix(f".{self.audio_format}")

            video.status = VideoStatus.DOWNLOADED
            video.download_path = str(audio_path)

            return DownloadResult(
                video=video,
                success=True,
                audio_path=str(audio_path),
                audio_format=self.audio_format,
                file_size_bytes=audio_path.stat().st_size if audio_path.exists() else None,
                download_time_seconds=time.time() - start_time,
            )

        except Exception as e:
            video.status = VideoStatus.FAILED
            return DownloadResult(
                video=video,
                success=False,
                error_message=str(e),
                error_type=type(e).__name__,
                download_time_seconds=time.time() - start_time,
            )

    def download_video(
        self,
        url: str,
        output_template: Optional[str] = None,
        with_audio: bool = True,
    ) -> DownloadResult:
        """Download video (with optional audio) from YouTube.

        Args:
            url: YouTube video URL
            output_template: Custom output filename template
            with_audio: Include audio in video file

        Returns:
            DownloadResult with video file path
        """
        video = self.get_video_info(url)
        video.status = VideoStatus.DOWNLOADING

        output_template = output_template or str(
            self.output_dir / "%(title)s.%(ext)s"
        )

        format_str = "bestvideo+bestaudio/best" if with_audio else "bestvideo/best"

        ydl_opts = {
            "quiet": self.quiet,
            "no_warnings": self.quiet,
            "format": format_str,
            "outtmpl": output_template,
            "merge_output_format": self.video_format,
        }

        start_time = time.time()

        try:
            with self.yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            video_path = Path(ydl.prepare_filename(info))

            video.status = VideoStatus.DOWNLOADED
            video.download_path = str(video_path)

            return DownloadResult(
                video=video,
                success=True,
                video_path=str(video_path),
                video_format=self.video_format,
                file_size_bytes=video_path.stat().st_size if video_path.exists() else None,
                download_time_seconds=time.time() - start_time,
            )

        except Exception as e:
            video.status = VideoStatus.FAILED
            return DownloadResult(
                video=video,
                success=False,
                error_message=str(e),
                error_type=type(e).__name__,
                download_time_seconds=time.time() - start_time,
            )

    def _clean_title(self, title: str) -> str:
        """Clean track title for better search results."""
        import re

        # Remove featuring artists
        title = re.sub(r"\s*[\(\[](feat\.?|ft\.?|featuring)[^\)\]]*[\)\]]", "", title, flags=re.IGNORECASE)

        # Remove remix info
        title = re.sub(r"\s*[\(\[].*remix.*[\)\]]", "", title, flags=re.IGNORECASE)

        # Remove extra whitespace
        title = " ".join(title.split())

        return title.strip()

    def _get_first_artist(self, artist: str) -> str:
        """Get first artist from multi-artist string."""
        separators = [",", "&", " x ", " X ", " and ", " vs ", " vs. "]

        for sep in separators:
            if sep in artist:
                return artist.split(sep)[0].strip()

        return artist

    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from URL."""
        import re

        patterns = [
            r"(?:v=|/)([a-zA-Z0-9_-]{11})(?:[&?]|$)",
            r"youtu\.be/([a-zA-Z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return ""


# Convenience functions

def search_youtube(
    query: str,
    max_results: int = 5,
    target_duration_seconds: Optional[int] = None,
) -> SearchResult:
    """Search YouTube for videos.

    Convenience function using default client.
    """
    client = YtDlpClient()
    return client.search(query, max_results, target_duration_seconds)


def download_video(
    url: str,
    output_dir: Optional[str] = None,
    audio_only: bool = False,
) -> DownloadResult:
    """Download a YouTube video.

    Convenience function using default client.
    """
    client = YtDlpClient(output_dir=output_dir)

    if audio_only:
        return client.download_audio(url)
    return client.download_video(url)
