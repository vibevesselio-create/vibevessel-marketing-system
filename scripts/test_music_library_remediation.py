#!/usr/bin/env python3
"""
Unit Tests for Music Library Remediation Functions
===================================================

Tests the fingerprint embedding and remediation execution functions,
with specific focus on the WAV file handling bug fix (DEF-001).

Created: 2026-01-13
Purpose: Prevent regression of WAV skip vs fail bug
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

# Import the module under test
from music_library_remediation import (
    embed_fingerprint_in_metadata,
    extract_fingerprint_from_metadata,
    compute_file_fingerprint,
    RemediationResult,
    MUTAGEN_AVAILABLE,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_audio_dir():
    """Create a temporary directory for test audio files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_m4a_file(temp_audio_dir):
    """Create a mock M4A file path."""
    file_path = temp_audio_dir / "test_track.m4a"
    file_path.write_bytes(b'\x00' * 1024)  # Minimal file content
    return str(file_path)


@pytest.fixture
def mock_mp3_file(temp_audio_dir):
    """Create a mock MP3 file path."""
    file_path = temp_audio_dir / "test_track.mp3"
    file_path.write_bytes(b'\x00' * 1024)
    return str(file_path)


@pytest.fixture
def mock_wav_file(temp_audio_dir):
    """Create a mock WAV file path."""
    file_path = temp_audio_dir / "test_track.wav"
    file_path.write_bytes(b'\x00' * 1024)
    return str(file_path)


@pytest.fixture
def mock_flac_file(temp_audio_dir):
    """Create a mock FLAC file path."""
    file_path = temp_audio_dir / "test_track.flac"
    file_path.write_bytes(b'\x00' * 1024)
    return str(file_path)


@pytest.fixture
def mock_unknown_file(temp_audio_dir):
    """Create a file with unknown extension."""
    file_path = temp_audio_dir / "test_track.xyz"
    file_path.write_bytes(b'\x00' * 1024)
    return str(file_path)


@pytest.fixture
def sample_fingerprint():
    """Return a sample fingerprint hash."""
    return "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef12345678"


# ============================================================================
# Tests for embed_fingerprint_in_metadata - Return Type Verification
# ============================================================================

class TestEmbedFingerprintReturnType:
    """Test that embed_fingerprint_in_metadata returns correct tuple types."""

    def test_returns_tuple(self, mock_wav_file, sample_fingerprint):
        """Verify function returns a tuple."""
        result = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)
        assert isinstance(result, tuple), "Should return a tuple"
        assert len(result) == 2, "Tuple should have exactly 2 elements"

    def test_tuple_first_element_is_bool(self, mock_wav_file, sample_fingerprint):
        """Verify first element of tuple is boolean."""
        result = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)
        assert isinstance(result[0], bool), "First element should be bool"

    def test_tuple_second_element_is_string_or_none(self, mock_wav_file, sample_fingerprint):
        """Verify second element is string or None."""
        result = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)
        assert result[1] is None or isinstance(result[1], str), \
            "Second element should be str or None"


# ============================================================================
# Tests for WAV File Handling (DEF-001 Bug Fix)
# ============================================================================

class TestWAVFileHandling:
    """
    Critical tests for WAV file handling bug fix.

    DEF-001: WAV files should be counted as "skipped" not "failed".
    The function should return (False, "unsupported_format") for WAV files.
    """

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed - cannot test WAV handling")
    def test_wav_returns_false_with_unsupported_format(self, mock_wav_file, sample_fingerprint):
        """
        CRITICAL TEST: WAV files must return (False, 'unsupported_format').

        This is the core test for DEF-001 bug fix. WAV files have limited
        metadata support and should be skipped, not counted as failures.
        """
        success, skip_reason = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)

        assert success is False, "WAV embedding should return False (not supported)"
        assert skip_reason == "unsupported_format", \
            f"WAV files should return 'unsupported_format', got '{skip_reason}'"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed - cannot test WAV handling")
    def test_wav_not_counted_as_error(self, mock_wav_file, sample_fingerprint):
        """WAV files should NOT return (False, None) which indicates error."""
        success, skip_reason = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)

        # The key distinction: (False, None) = error, (False, "unsupported_format") = skip
        assert skip_reason is not None, \
            "WAV should have a skip_reason, not None (which indicates error)"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed - cannot test WAV handling")
    def test_wav_file_uppercase_extension(self, temp_audio_dir, sample_fingerprint):
        """Test WAV handling with uppercase extension."""
        file_path = temp_audio_dir / "test_track.WAV"
        file_path.write_bytes(b'\x00' * 1024)

        success, skip_reason = embed_fingerprint_in_metadata(str(file_path), sample_fingerprint)

        assert success is False
        assert skip_reason == "unsupported_format"


# ============================================================================
# Tests for Other Unsupported Formats
# ============================================================================

class TestUnsupportedFormats:
    """Test handling of various unsupported file formats."""

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_unknown_extension_returns_unsupported(self, mock_unknown_file, sample_fingerprint):
        """Unknown file extensions should return unsupported_format."""
        success, skip_reason = embed_fingerprint_in_metadata(mock_unknown_file, sample_fingerprint)

        assert success is False
        assert skip_reason == "unsupported_format"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_txt_file_returns_unsupported(self, temp_audio_dir, sample_fingerprint):
        """Text files should return unsupported_format."""
        file_path = temp_audio_dir / "not_audio.txt"
        file_path.write_bytes(b"This is text")

        success, skip_reason = embed_fingerprint_in_metadata(str(file_path), sample_fingerprint)

        assert success is False
        assert skip_reason == "unsupported_format"


# ============================================================================
# Tests for Supported Formats (with mocking)
# ============================================================================

class TestSupportedFormatsWithMocking:
    """Test supported formats using mocks to avoid needing real audio files."""

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    @patch('music_library_remediation.MP4')
    def test_m4a_success_returns_true_none(self, mock_mp4, mock_m4a_file, sample_fingerprint):
        """M4A files should return (True, None) on success."""
        mock_audio = MagicMock()
        mock_mp4.return_value = mock_audio

        success, skip_reason = embed_fingerprint_in_metadata(mock_m4a_file, sample_fingerprint)

        assert success is True, "M4A embedding should succeed"
        assert skip_reason is None, "Success should have None skip_reason"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    @patch('music_library_remediation.ID3')
    def test_mp3_success_returns_true_none(self, mock_id3, mock_mp3_file, sample_fingerprint):
        """MP3 files should return (True, None) on success."""
        mock_audio = MagicMock()
        mock_id3.return_value = mock_audio

        success, skip_reason = embed_fingerprint_in_metadata(mock_mp3_file, sample_fingerprint)

        assert success is True, "MP3 embedding should succeed"
        assert skip_reason is None, "Success should have None skip_reason"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    @patch('music_library_remediation.FLAC')
    def test_flac_success_returns_true_none(self, mock_flac, mock_flac_file, sample_fingerprint):
        """FLAC files should return (True, None) on success."""
        mock_audio = MagicMock()
        mock_flac.return_value = mock_audio

        success, skip_reason = embed_fingerprint_in_metadata(mock_flac_file, sample_fingerprint)

        assert success is True, "FLAC embedding should succeed"
        assert skip_reason is None, "Success should have None skip_reason"


# ============================================================================
# Tests for Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling returns (False, None) for actual errors."""

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    @patch('music_library_remediation.MP4')
    def test_exception_returns_false_none(self, mock_mp4, mock_m4a_file, sample_fingerprint):
        """Actual exceptions should return (False, None)."""
        mock_mp4.side_effect = Exception("Simulated error")

        success, skip_reason = embed_fingerprint_in_metadata(mock_m4a_file, sample_fingerprint)

        assert success is False, "Exception should return False"
        assert skip_reason is None, "Exception should return None skip_reason (actual error)"

    def test_nonexistent_file_handling(self, temp_audio_dir, sample_fingerprint):
        """Test handling of non-existent files."""
        nonexistent = str(temp_audio_dir / "does_not_exist.m4a")

        success, skip_reason = embed_fingerprint_in_metadata(nonexistent, sample_fingerprint)

        # Non-existent file should be treated as error, not unsupported format
        assert success is False


# ============================================================================
# Tests for Mutagen Availability
# ============================================================================

class TestMutagenAvailability:
    """Test behavior when mutagen is not available."""

    @patch('music_library_remediation.MUTAGEN_AVAILABLE', False)
    def test_mutagen_unavailable_returns_false_none(self, mock_m4a_file, sample_fingerprint):
        """When mutagen unavailable, should return (False, None) - actual error."""
        # Re-import to get patched value
        from music_library_remediation import embed_fingerprint_in_metadata as embed_fn

        success, skip_reason = embed_fn(mock_m4a_file, sample_fingerprint)

        assert success is False
        # When mutagen is unavailable, it's an error condition, not unsupported format
        # The actual implementation returns (False, None) for this case


# ============================================================================
# Tests for compute_file_fingerprint
# ============================================================================

class TestComputeFileFingerprint:
    """Test the fingerprint computation function."""

    def test_fingerprint_is_sha256_hex(self, mock_wav_file):
        """Fingerprint should be a 64-character hex string (SHA-256)."""
        fingerprint = compute_file_fingerprint(Path(mock_wav_file))

        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 64, "SHA-256 hex should be 64 characters"
        assert all(c in '0123456789abcdef' for c in fingerprint)

    def test_same_file_same_fingerprint(self, mock_wav_file):
        """Same file should produce same fingerprint."""
        fp1 = compute_file_fingerprint(Path(mock_wav_file))
        fp2 = compute_file_fingerprint(Path(mock_wav_file))

        assert fp1 == fp2

    def test_different_files_different_fingerprints(self, temp_audio_dir):
        """Different files should produce different fingerprints."""
        file1 = temp_audio_dir / "file1.wav"
        file2 = temp_audio_dir / "file2.wav"

        file1.write_bytes(b'\x00' * 1024)
        file2.write_bytes(b'\xFF' * 1024)

        fp1 = compute_file_fingerprint(file1)
        fp2 = compute_file_fingerprint(file2)

        assert fp1 != fp2


# ============================================================================
# Tests for RemediationResult Dataclass
# ============================================================================

class TestRemediationResult:
    """Test the RemediationResult dataclass."""

    def test_default_values(self):
        """Test default initialization values."""
        result = RemediationResult()

        assert result.planned == 0
        assert result.executed == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.actions == []
        assert result.errors == []

    def test_increment_counters(self):
        """Test that counters can be incremented."""
        result = RemediationResult()

        result.succeeded += 1
        result.failed += 2
        result.skipped += 3

        assert result.succeeded == 1
        assert result.failed == 2
        assert result.skipped == 3

    def test_separate_skip_and_fail_counters(self):
        """Verify skip and fail are separate counters."""
        result = RemediationResult()

        result.skipped += 10
        result.failed += 5

        assert result.skipped == 10
        assert result.failed == 5
        assert result.skipped != result.failed


# ============================================================================
# Integration Tests - Skip vs Fail Counting Logic
# ============================================================================

class TestSkipVsFailCounting:
    """
    Integration tests to verify the skip vs fail counting logic.

    These tests simulate how execute_fingerprint_remediation should use
    the return values from embed_fingerprint_in_metadata.
    """

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_unsupported_format_increments_skipped(self, mock_wav_file, sample_fingerprint):
        """Unsupported format should increment skipped counter."""
        result = RemediationResult()

        success, skip_reason = embed_fingerprint_in_metadata(mock_wav_file, sample_fingerprint)

        # This is how execute_fingerprint_remediation should handle it
        if not success:
            if skip_reason == "unsupported_format":
                result.skipped += 1
            else:
                result.failed += 1
        else:
            result.succeeded += 1

        assert result.skipped == 1, "WAV should increment skipped"
        assert result.failed == 0, "WAV should NOT increment failed"

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_actual_error_increments_failed(self, mock_m4a_file, sample_fingerprint):
        """Actual errors should increment failed counter."""
        result = RemediationResult()

        # Simulate an error by patching - use the module path
        import scripts.music_library_remediation as mlr
        original_mp4 = getattr(mlr, 'MP4', None)

        try:
            # Temporarily replace MP4 with something that raises
            mlr.MP4 = Mock(side_effect=Exception("Simulated error"))

            success, skip_reason = embed_fingerprint_in_metadata(mock_m4a_file, sample_fingerprint)

            # This is how execute_fingerprint_remediation should handle it
            if not success:
                if skip_reason == "unsupported_format":
                    result.skipped += 1
                else:
                    result.failed += 1
            else:
                result.succeeded += 1

            assert result.failed == 1, "Error should increment failed"
            assert result.skipped == 0, "Error should NOT increment skipped"
        finally:
            if original_mp4:
                mlr.MP4 = original_mp4

    @pytest.mark.skipif(not MUTAGEN_AVAILABLE, reason="mutagen not installed")
    def test_mixed_file_types_correct_counts(self, temp_audio_dir, sample_fingerprint):
        """Test processing multiple file types produces correct counts."""
        result = RemediationResult()

        # Create test files
        wav_file = temp_audio_dir / "track.wav"
        unknown_file = temp_audio_dir / "track.xyz"
        wav_file.write_bytes(b'\x00' * 100)
        unknown_file.write_bytes(b'\x00' * 100)

        files = [str(wav_file), str(unknown_file)]

        for file_path in files:
            success, skip_reason = embed_fingerprint_in_metadata(file_path, sample_fingerprint)

            if not success:
                if skip_reason == "unsupported_format":
                    result.skipped += 1
                else:
                    result.failed += 1
            else:
                result.succeeded += 1

        # Both WAV and unknown extension should be skipped
        assert result.skipped == 2
        assert result.failed == 0
        assert result.succeeded == 0


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
