"""
Unit tests for the Downloader module.

Tests download functionality, URL validation, YouTube fallback,
and error handling.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from music_workflow.core.downloader import Downloader, DownloadOptions
from music_workflow.core.models import DownloadResult
from music_workflow.utils.errors import DownloadError, DRMProtectionError
from music_workflow.config.constants import Platform


class TestDownloadOptions:
    """Tests for DownloadOptions dataclass."""

    def test_default_options(self):
        """Test default option values."""
        opts = DownloadOptions(
            output_dir=Path("/tmp/test"),
            formats=["m4a"],
        )
        assert opts.audio_only is True
        assert opts.extract_metadata is True
        assert opts.max_retries == 3
        assert opts.timeout == 300
        assert opts.youtube_fallback is True

    def test_custom_options(self):
        """Test custom option values."""
        opts = DownloadOptions(
            output_dir=Path("/custom/dir"),
            formats=["wav", "aiff"],
            audio_only=False,
            max_retries=5,
            timeout=600,
            youtube_fallback=False,
        )
        assert opts.output_dir == Path("/custom/dir")
        assert opts.formats == ["wav", "aiff"]
        assert opts.max_retries == 5
        assert opts.timeout == 600
        assert opts.youtube_fallback is False


class TestDownloader:
    """Tests for Downloader class."""

    @pytest.fixture
    def downloader(self, tmp_path):
        """Create a downloader instance for testing."""
        opts = DownloadOptions(
            output_dir=tmp_path,
            formats=["m4a"],
        )
        return Downloader(options=opts)

    @pytest.fixture
    def downloader_no_youtube(self, tmp_path):
        """Create a downloader without YouTube fallback."""
        opts = DownloadOptions(
            output_dir=tmp_path,
            formats=["m4a"],
            youtube_fallback=False,
        )
        return Downloader(options=opts)

    def test_init_default_options(self):
        """Test initialization with default options."""
        dl = Downloader()
        assert dl.options is not None
        assert dl.options.output_dir == Path("/tmp/music_downloads")
        assert "m4a" in dl.options.formats

    def test_init_custom_options(self, tmp_path):
        """Test initialization with custom options."""
        opts = DownloadOptions(
            output_dir=tmp_path,
            formats=["wav"],
        )
        dl = Downloader(options=opts)
        assert dl.options.output_dir == tmp_path
        assert dl.options.formats == ["wav"]

    @patch("music_workflow.core.downloader.validate_url")
    def test_download_spotify_raises_drm_error_no_fallback(
        self, mock_validate, downloader_no_youtube
    ):
        """Test that Spotify URLs raise DRMProtectionError without fallback."""
        mock_validate.return_value = (True, Platform.SPOTIFY)

        with pytest.raises(DRMProtectionError) as exc_info:
            downloader_no_youtube.download("https://open.spotify.com/track/123")

        assert "DRM-protected" in str(exc_info.value)

    @patch("music_workflow.core.downloader.validate_url")
    @patch.object(Downloader, "_download_via_youtube_search")
    def test_download_spotify_with_youtube_fallback(
        self, mock_youtube_fallback, mock_validate, downloader
    ):
        """Test Spotify download triggers YouTube fallback."""
        mock_validate.return_value = (True, Platform.SPOTIFY)
        mock_youtube_fallback.return_value = DownloadResult(
            success=True,
            files=[Path("/tmp/test.m4a")],
            metadata={"title": "Test Track"},
        )

        result = downloader.download("https://open.spotify.com/track/123")

        mock_youtube_fallback.assert_called_once()
        assert result.success is True

    @patch("music_workflow.core.downloader.validate_url")
    def test_download_youtube_url(self, mock_validate, downloader, tmp_path):
        """Test download from YouTube URL."""
        mock_validate.return_value = (True, Platform.YOUTUBE)

        # Mock yt-dlp
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.return_value = {
            "title": "Test Track",
            "duration": 180,
            "webpage_url": "https://youtube.com/watch?v=test123",
        }

        # Create mock file
        test_file = tmp_path / "Test Track.m4a"
        test_file.touch()

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            result = downloader.download("https://youtube.com/watch?v=test123")

        assert result.success is True
        assert len(result.files) == 1

    @patch("music_workflow.core.downloader.validate_url")
    def test_download_soundcloud_url(self, mock_validate, downloader, tmp_path):
        """Test download from SoundCloud URL."""
        mock_validate.return_value = (True, Platform.SOUNDCLOUD)

        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.return_value = {
            "title": "SC Track",
            "duration": 240,
            "webpage_url": "https://soundcloud.com/artist/track",
        }

        test_file = tmp_path / "SC Track.m4a"
        test_file.touch()

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            result = downloader.download("https://soundcloud.com/artist/track")

        assert result.success is True

    def test_build_ydl_options(self, downloader, tmp_path):
        """Test yt-dlp options building."""
        opts = downloader._build_ydl_options(tmp_path, ["m4a"])

        assert opts["format"] == "bestaudio/best"
        assert opts["extractaudio"] is True
        assert opts["audioformat"] == "m4a"
        assert opts["noplaylist"] is True
        assert opts["retries"] == 3

    def test_process_download_result_success(self, downloader, tmp_path):
        """Test processing successful download result."""
        # Create test files
        (tmp_path / "Test.m4a").touch()

        info = {
            "title": "Test",
            "duration": 180,
            "webpage_url": "https://example.com/test",
        }

        result = downloader._process_download_result(info, tmp_path, ["m4a"])

        assert result.success is True
        assert len(result.files) == 1
        assert result.duration_seconds == 180

    def test_process_download_result_no_files(self, downloader, tmp_path):
        """Test processing result with no files."""
        info = {
            "title": "Missing",
            "duration": 180,
        }

        result = downloader._process_download_result(info, tmp_path, ["m4a"])

        assert result.success is False
        assert len(result.files) == 0

    def test_search_youtube(self, downloader):
        """Test YouTube search functionality."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.return_value = {
            "entries": [{"id": "abc123"}],
        }

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            result = downloader.search_youtube("Artist - Track")

        assert result == "https://www.youtube.com/watch?v=abc123"

    def test_search_youtube_no_results(self, downloader):
        """Test YouTube search with no results."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.return_value = {"entries": []}

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            result = downloader.search_youtube("NonexistentTrack12345")

        assert result is None

    def test_get_metadata(self, downloader):
        """Test metadata extraction."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.return_value = {
            "title": "Test Track",
            "artist": "Test Artist",
            "duration": 200,
        }

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            metadata = downloader.get_metadata("https://youtube.com/watch?v=test")

        assert metadata["title"] == "Test Track"
        assert metadata["duration"] == 200

    def test_get_metadata_error(self, downloader):
        """Test metadata extraction error handling."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.side_effect = Exception("Network error")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            with pytest.raises(DownloadError) as exc_info:
                downloader.get_metadata("https://example.com/invalid")

        assert "Failed to extract metadata" in str(exc_info.value)

    def test_yt_dlp_lazy_loading(self, downloader):
        """Test that yt-dlp is lazily loaded."""
        assert downloader._yt_dlp is None

        # Mock the import
        with patch.dict("sys.modules", {"yt_dlp": MagicMock()}):
            yt_dlp = downloader._get_yt_dlp()
            assert yt_dlp is not None

    def test_yt_dlp_import_error(self):
        """Test error when yt-dlp is not installed."""
        dl = Downloader()
        dl._yt_dlp = None

        with patch.dict("sys.modules", {"yt_dlp": None}):
            with patch("builtins.__import__", side_effect=ImportError("No yt_dlp")):
                with pytest.raises(DownloadError) as exc_info:
                    dl._get_yt_dlp()

        assert "yt-dlp is not installed" in str(exc_info.value)


class TestDownloadErrorHandling:
    """Tests for download error scenarios."""

    @pytest.fixture
    def downloader(self, tmp_path):
        """Create a downloader for error testing."""
        opts = DownloadOptions(
            output_dir=tmp_path,
            formats=["m4a"],
        )
        return Downloader(options=opts)

    @patch("music_workflow.core.downloader.validate_url")
    def test_drm_error_from_download(self, mock_validate, downloader):
        """Test DRM error detection during download."""
        mock_validate.return_value = (True, Platform.YOUTUBE)

        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.side_effect = Exception("DRM protected content")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            with pytest.raises(DRMProtectionError) as exc_info:
                downloader.download("https://youtube.com/watch?v=drm")

        assert "DRM-protected" in str(exc_info.value)

    @patch("music_workflow.core.downloader.validate_url")
    def test_generic_download_error(self, mock_validate, downloader):
        """Test generic download error handling."""
        mock_validate.return_value = (True, Platform.YOUTUBE)

        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = Mock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = Mock(return_value=False)
        mock_ydl_instance.extract_info.side_effect = Exception("Network timeout")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
            with pytest.raises(DownloadError) as exc_info:
                downloader.download("https://youtube.com/watch?v=test")

        assert "Download failed" in str(exc_info.value)
        assert "Network timeout" in str(exc_info.value)
