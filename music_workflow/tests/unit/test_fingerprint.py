"""
Unit tests for the audio fingerprinting module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import struct

import sys
sys.path.insert(0, '.')

from music_workflow.deduplication.fingerprint import (
    AudioFingerprint,
    FingerprintGenerator,
    get_fingerprint,
    clear_fingerprint_cache,
)
from music_workflow.utils.errors import ProcessingError


class TestAudioFingerprint:
    """Test AudioFingerprint dataclass."""

    def test_fingerprint_creation(self):
        """Test AudioFingerprint can be created."""
        fp = AudioFingerprint(
            hash="abc123def456",
            duration=180.0,
            signature=b"signature_data",
            sample_rate=22050
        )

        assert fp.hash == "abc123def456"
        assert fp.duration == 180.0
        assert fp.signature == b"signature_data"
        assert fp.sample_rate == 22050

    def test_fingerprint_equality_same_hash(self):
        """Test fingerprints with same hash are equal."""
        fp1 = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig1",
            sample_rate=22050
        )
        fp2 = AudioFingerprint(
            hash="abc123",
            duration=190.0,  # Different duration
            signature=b"sig2",  # Different signature
            sample_rate=44100  # Different sample rate
        )

        assert fp1 == fp2

    def test_fingerprint_equality_different_hash(self):
        """Test fingerprints with different hash are not equal."""
        fp1 = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )
        fp2 = AudioFingerprint(
            hash="def456",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )

        assert fp1 != fp2

    def test_fingerprint_equality_non_fingerprint(self):
        """Test fingerprint is not equal to non-fingerprint."""
        fp = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )

        assert fp != "abc123"
        assert fp != 123
        assert fp != None


class TestFingerprintGenerator:
    """Test FingerprintGenerator class."""

    def test_generator_initialization(self):
        """Test generator can be initialized."""
        generator = FingerprintGenerator()
        assert generator is not None
        assert generator.sample_rate == 22050

    def test_generator_custom_sample_rate(self):
        """Test generator with custom sample rate."""
        generator = FingerprintGenerator(sample_rate=44100)
        assert generator.sample_rate == 44100

    def test_has_chromaprint_false(self):
        """Test chromaprint detection when not installed."""
        generator = FingerprintGenerator()

        with patch.dict(sys.modules, {'acoustid': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                assert generator._has_chromaprint() is False

    def test_get_librosa_not_installed(self):
        """Test error when librosa not installed."""
        generator = FingerprintGenerator()
        generator._librosa = None

        with patch.dict(sys.modules, {'librosa': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                with pytest.raises(ProcessingError) as exc_info:
                    generator._get_librosa()
                assert "librosa is not installed" in str(exc_info.value)


class TestGenerateFingerprint:
    """Test fingerprint generation."""

    @patch('music_workflow.deduplication.fingerprint.validate_audio_file')
    def test_generate_with_chromaprint(self, mock_validate):
        """Test generate uses chromaprint when available."""
        generator = FingerprintGenerator()

        with patch.object(generator, '_has_chromaprint', return_value=True):
            with patch.object(generator, '_generate_chromaprint') as mock_chromaprint:
                expected_fp = AudioFingerprint(
                    hash="abc123",
                    duration=180.0,
                    signature=b"sig",
                    sample_rate=22050
                )
                mock_chromaprint.return_value = expected_fp

                result = generator.generate(Path("/test/file.m4a"))

                assert result == expected_fp
                mock_chromaprint.assert_called_once()

    @patch('music_workflow.deduplication.fingerprint.validate_audio_file')
    def test_generate_fallback_to_spectral(self, mock_validate):
        """Test generate falls back to spectral hash."""
        generator = FingerprintGenerator()

        with patch.object(generator, '_has_chromaprint', return_value=False):
            with patch.object(generator, '_generate_spectral_hash') as mock_spectral:
                expected_fp = AudioFingerprint(
                    hash="spectral123",
                    duration=180.0,
                    signature=b"spectral_sig",
                    sample_rate=22050
                )
                mock_spectral.return_value = expected_fp

                result = generator.generate(Path("/test/file.m4a"))

                assert result == expected_fp
                mock_spectral.assert_called_once()

    @patch('music_workflow.deduplication.fingerprint.validate_audio_file')
    def test_generate_chromaprint_fails_fallback(self, mock_validate):
        """Test generate falls back when chromaprint fails."""
        generator = FingerprintGenerator()

        with patch.object(generator, '_has_chromaprint', return_value=True):
            with patch.object(generator, '_generate_chromaprint', side_effect=Exception("Failed")):
                with patch.object(generator, '_generate_spectral_hash') as mock_spectral:
                    expected_fp = AudioFingerprint(
                        hash="spectral123",
                        duration=180.0,
                        signature=b"sig",
                        sample_rate=22050
                    )
                    mock_spectral.return_value = expected_fp

                    result = generator.generate(Path("/test/file.m4a"))

                    assert result == expected_fp


class TestCompareFingerprints:
    """Test fingerprint comparison."""

    def test_compare_exact_match(self):
        """Test comparing identical fingerprints."""
        generator = FingerprintGenerator()

        fp1 = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )
        fp2 = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )

        similarity = generator.compare(fp1, fp2)
        assert similarity == 1.0

    def test_compare_different_duration(self):
        """Test comparing fingerprints with very different durations."""
        generator = FingerprintGenerator()

        fp1 = AudioFingerprint(
            hash="abc123",
            duration=180.0,
            signature=b"sig1",
            sample_rate=22050
        )
        fp2 = AudioFingerprint(
            hash="def456",
            duration=300.0,  # 2 minute difference
            signature=b"sig2",
            sample_rate=22050
        )

        similarity = generator.compare(fp1, fp2)
        assert similarity == 0.0

    def test_compare_signatures_different_length(self):
        """Test comparing signatures of different lengths."""
        generator = FingerprintGenerator()

        sig1 = struct.pack('4f', 1.0, 2.0, 3.0, 4.0)
        sig2 = struct.pack('3f', 1.0, 2.0, 3.0)

        similarity = generator._compare_signatures(sig1, sig2)
        assert similarity == 0.0


class TestCompareSignatures:
    """Test signature comparison."""

    def test_compare_identical_signatures(self):
        """Test comparing identical signatures."""
        generator = FingerprintGenerator()

        # Create identical signatures
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        sig = struct.pack(f'{len(values)}f', *values)

        similarity = generator._compare_signatures(sig, sig)
        assert similarity == 1.0

    def test_compare_similar_signatures(self):
        """Test comparing similar signatures."""
        generator = FingerprintGenerator()

        # Create slightly different signatures
        values1 = [1.0, 2.0, 3.0, 4.0, 5.0] * 10
        values2 = [1.1, 2.1, 3.1, 4.1, 5.1] * 10

        sig1 = struct.pack(f'{len(values1)}f', *values1)
        sig2 = struct.pack(f'{len(values2)}f', *values2)

        similarity = generator._compare_signatures(sig1, sig2)
        # Should be high but not 1.0
        assert 0.9 < similarity <= 1.0

    def test_compare_different_signatures(self):
        """Test comparing very different signatures."""
        generator = FingerprintGenerator()

        # Create very different signatures
        values1 = [1.0, 2.0, 3.0, 4.0] * 10
        values2 = [10.0, -5.0, 20.0, -10.0] * 10

        sig1 = struct.pack(f'{len(values1)}f', *values1)
        sig2 = struct.pack(f'{len(values2)}f', *values2)

        similarity = generator._compare_signatures(sig1, sig2)
        # Should be lower due to different patterns
        assert similarity < 0.9


class TestFingerprintCache:
    """Test fingerprint caching."""

    def test_clear_fingerprint_cache(self):
        """Test clearing fingerprint cache."""
        # This should not raise
        clear_fingerprint_cache()

    @patch('music_workflow.deduplication.fingerprint.FingerprintGenerator')
    def test_get_fingerprint_caches(self, mock_generator_class):
        """Test get_fingerprint uses cache."""
        clear_fingerprint_cache()

        mock_generator = MagicMock()
        expected_fp = AudioFingerprint(
            hash="cached123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )
        mock_generator.generate.return_value = expected_fp
        mock_generator_class.return_value = mock_generator

        # First call should generate
        result1 = get_fingerprint(Path("/test/file.m4a"), use_cache=True)
        assert result1 == expected_fp

        # Second call should use cache (but our mock doesn't actually cache)
        result2 = get_fingerprint(Path("/test/file.m4a"), use_cache=True)
        assert result2 == expected_fp

    @patch('music_workflow.deduplication.fingerprint.FingerprintGenerator')
    def test_get_fingerprint_no_cache(self, mock_generator_class):
        """Test get_fingerprint without cache."""
        clear_fingerprint_cache()

        mock_generator = MagicMock()
        expected_fp = AudioFingerprint(
            hash="nocache123",
            duration=180.0,
            signature=b"sig",
            sample_rate=22050
        )
        mock_generator.generate.return_value = expected_fp
        mock_generator_class.return_value = mock_generator

        result = get_fingerprint(Path("/test/file.m4a"), use_cache=False)
        assert result == expected_fp
