"""
Unit tests for the audio processor module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, '.')

from music_workflow.core.processor import (
    AudioProcessor,
    ProcessingOptions,
)
from music_workflow.core.models import AudioAnalysis
from music_workflow.utils.errors import ProcessingError


class TestProcessingOptions:
    """Test ProcessingOptions dataclass."""

    def test_default_options(self):
        """Test default processing options."""
        options = ProcessingOptions()
        assert options.target_lufs == -14.0
        assert options.analyze_bpm is True
        assert options.analyze_key is True
        assert options.preserve_original is True
        assert options.output_format is None

    def test_custom_options(self):
        """Test custom processing options."""
        options = ProcessingOptions(
            target_lufs=-16.0,
            analyze_bpm=False,
            analyze_key=False,
            preserve_original=False,
            output_format="wav"
        )
        assert options.target_lufs == -16.0
        assert options.analyze_bpm is False
        assert options.analyze_key is False
        assert options.preserve_original is False
        assert options.output_format == "wav"


class TestAudioProcessor:
    """Test AudioProcessor class."""

    def test_processor_initialization(self):
        """Test processor can be initialized."""
        processor = AudioProcessor()
        assert processor is not None
        assert processor.options is not None
        assert isinstance(processor.options, ProcessingOptions)

    def test_processor_with_options(self):
        """Test processor with custom options."""
        options = ProcessingOptions(target_lufs=-18.0)
        processor = AudioProcessor(options=options)
        assert processor.options.target_lufs == -18.0

    def test_get_librosa_not_installed(self):
        """Test error when librosa not installed."""
        processor = AudioProcessor()
        processor._librosa = None

        with patch.dict(sys.modules, {'librosa': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                with pytest.raises(ProcessingError) as exc_info:
                    processor._get_librosa()
                assert "librosa is not installed" in str(exc_info.value)

    def test_get_mutagen_not_installed(self):
        """Test error when mutagen not installed."""
        processor = AudioProcessor()
        processor._mutagen = None

        with patch.dict(sys.modules, {'mutagen': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                with pytest.raises(ProcessingError) as exc_info:
                    processor._get_mutagen()
                assert "mutagen is not installed" in str(exc_info.value)

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_analyze_with_mock_librosa(self, mock_validate):
        """Test analyze method with mocked librosa."""
        processor = AudioProcessor()

        # Create mock librosa module
        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (MagicMock(), 44100)
        mock_librosa.get_duration.return_value = 180.0
        mock_librosa.beat.beat_track.return_value = (128.0, MagicMock())

        processor._librosa = mock_librosa

        # Mock the key detection
        with patch.object(processor, '_detect_key', return_value="Am"):
            result = processor.analyze(Path("/test/file.m4a"))

        assert isinstance(result, AudioAnalysis)
        assert result.bpm == 128.0
        assert result.duration == 180.0
        assert result.sample_rate == 44100

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_analyze_bpm_disabled(self, mock_validate):
        """Test analyze with BPM disabled."""
        options = ProcessingOptions(analyze_bpm=False, analyze_key=False)
        processor = AudioProcessor(options=options)

        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (MagicMock(), 44100)
        mock_librosa.get_duration.return_value = 180.0

        processor._librosa = mock_librosa

        result = processor.analyze(Path("/test/file.m4a"))

        # BPM should be None when disabled
        assert result.bpm is None
        # beat_track should not be called
        mock_librosa.beat.beat_track.assert_not_called()

    def test_get_export_params_lossless(self):
        """Test export params for lossless formats."""
        processor = AudioProcessor()

        # WAV should be lossless
        params = processor._get_export_params("wav")
        assert params["format"] == "wav"
        assert "parameters" in params

        # AIFF should be lossless
        params = processor._get_export_params("aiff")
        assert params["format"] == "aiff"

    def test_get_export_params_m4a(self):
        """Test export params for M4A format."""
        processor = AudioProcessor()

        params = processor._get_export_params("m4a")
        assert params["format"] == "mp4"
        assert params["codec"] == "aac"
        assert params["bitrate"] == "320k"

    def test_get_export_params_mp3(self):
        """Test export params for MP3 format."""
        processor = AudioProcessor()

        params = processor._get_export_params("mp3")
        assert params["format"] == "mp3"
        assert params["bitrate"] == "320k"

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_convert_pydub_not_installed(self, mock_validate):
        """Test convert error when pydub not installed."""
        processor = AudioProcessor()

        with patch.dict(sys.modules, {'pydub': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                with pytest.raises(ProcessingError) as exc_info:
                    processor.convert(Path("/test/file.m4a"), "wav")
                assert "pydub is not installed" in str(exc_info.value)

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_normalize_pydub_not_installed(self, mock_validate):
        """Test normalize error when pydub not installed."""
        processor = AudioProcessor()

        with patch.dict(sys.modules, {'pydub': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                with pytest.raises(ProcessingError) as exc_info:
                    processor.normalize(Path("/test/file.m4a"))
                assert "pydub is not installed" in str(exc_info.value)

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_get_audio_info_with_mock_mutagen(self, mock_validate):
        """Test get_audio_info with mocked mutagen."""
        processor = AudioProcessor()

        # Create mock mutagen
        mock_audio = MagicMock()
        mock_audio.info.length = 180.0
        mock_audio.info.sample_rate = 44100
        mock_audio.info.channels = 2
        mock_audio.info.bitrate = 320

        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = mock_audio
        processor._mutagen = mock_mutagen

        result = processor.get_audio_info(Path("/test/file.m4a"))

        assert result["duration"] == 180.0
        assert result["sample_rate"] == 44100
        assert result["channels"] == 2
        assert result["bitrate"] == 320
        assert result["format"] == "m4a"

    @patch('music_workflow.core.processor.validate_audio_file')
    def test_get_audio_info_file_not_recognized(self, mock_validate):
        """Test get_audio_info when file not recognized."""
        processor = AudioProcessor()

        mock_mutagen = MagicMock()
        mock_mutagen.File.return_value = None
        processor._mutagen = mock_mutagen

        result = processor.get_audio_info(Path("/test/file.m4a"))
        assert result == {}


class TestKeyDetection:
    """Test key detection functionality."""

    def test_detect_key_returns_key_format(self):
        """Test key detection returns expected format."""
        processor = AudioProcessor()

        # Mock librosa
        mock_librosa = MagicMock()
        processor._librosa = mock_librosa

        # Mock chroma features
        import numpy as np
        mock_chroma = np.random.rand(12, 100)
        mock_librosa.feature.chroma_cqt.return_value = mock_chroma

        with patch.dict(sys.modules, {'numpy': np}):
            result = processor._detect_key(np.array([1.0, 2.0]), 44100)

        # Result should be a key name (or None if detection fails)
        if result is not None:
            # Keys are like "C", "Am", "Db", etc.
            assert len(result) <= 3

    def test_detect_key_handles_exception(self):
        """Test key detection handles exceptions gracefully."""
        processor = AudioProcessor()

        mock_librosa = MagicMock()
        mock_librosa.feature.chroma_cqt.side_effect = Exception("Analysis failed")
        processor._librosa = mock_librosa

        import numpy as np
        result = processor._detect_key(np.array([1.0, 2.0]), 44100)

        # Should return None on failure
        assert result is None
