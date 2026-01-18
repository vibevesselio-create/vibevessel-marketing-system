"""
Audio fingerprinting for deduplication.

This module provides audio fingerprinting capabilities for detecting
duplicate tracks across the music library.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import struct

from music_workflow.utils.errors import ProcessingError
from music_workflow.utils.validators import validate_audio_file


@dataclass
class AudioFingerprint:
    """Representation of an audio fingerprint."""
    hash: str  # SHA256 hash of fingerprint data
    duration: float  # Audio duration in seconds
    signature: bytes  # Raw fingerprint signature
    sample_rate: int  # Sample rate used for analysis

    def __eq__(self, other: "AudioFingerprint") -> bool:
        """Check equality by hash."""
        if not isinstance(other, AudioFingerprint):
            return False
        return self.hash == other.hash


class FingerprintGenerator:
    """Generate and compare audio fingerprints.

    Uses chromaprint/acoustid for audio fingerprinting when available,
    with a fallback to spectral hash for basic detection.
    """

    def __init__(self, sample_rate: int = 22050):
        """Initialize the fingerprint generator.

        Args:
            sample_rate: Sample rate for analysis (default 22050)
        """
        self.sample_rate = sample_rate
        self._chromaprint = None
        self._librosa = None

    def _get_librosa(self):
        """Get librosa for audio loading."""
        if self._librosa is None:
            try:
                import librosa
                self._librosa = librosa
            except ImportError:
                raise ProcessingError(
                    "librosa is not installed",
                    details={"hint": "Install with: pip install librosa"}
                )
        return self._librosa

    def _has_chromaprint(self) -> bool:
        """Check if chromaprint/acoustid is available."""
        try:
            import acoustid
            return True
        except ImportError:
            return False

    def generate(self, file_path: Path) -> AudioFingerprint:
        """Generate fingerprint for audio file.

        Args:
            file_path: Path to audio file

        Returns:
            AudioFingerprint for the file

        Raises:
            ProcessingError: If fingerprinting fails
        """
        validate_audio_file(file_path)

        # Try chromaprint first (best quality)
        if self._has_chromaprint():
            try:
                return self._generate_chromaprint(file_path)
            except Exception:
                pass  # Fall back to spectral hash

        # Fall back to spectral hash
        return self._generate_spectral_hash(file_path)

    def _generate_chromaprint(self, file_path: Path) -> AudioFingerprint:
        """Generate fingerprint using chromaprint/acoustid.

        Args:
            file_path: Path to audio file

        Returns:
            AudioFingerprint
        """
        import acoustid

        try:
            duration, fingerprint = acoustid.fingerprint_file(str(file_path))

            # Create hash from fingerprint
            fp_hash = hashlib.sha256(fingerprint.encode()).hexdigest()

            return AudioFingerprint(
                hash=fp_hash,
                duration=duration,
                signature=fingerprint.encode(),
                sample_rate=self.sample_rate,
            )

        except Exception as e:
            raise ProcessingError(
                f"Chromaprint fingerprinting failed: {e}",
                file_path=str(file_path),
                operation="fingerprint",
                details={"error": str(e)}
            )

    def _generate_spectral_hash(self, file_path: Path) -> AudioFingerprint:
        """Generate fingerprint using spectral features.

        This is a fallback when chromaprint is not available.

        Args:
            file_path: Path to audio file

        Returns:
            AudioFingerprint
        """
        librosa = self._get_librosa()

        try:
            # Load audio
            y, sr = librosa.load(str(file_path), sr=self.sample_rate, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)

            # Compute mel spectrogram
            import numpy as np
            mel_spec = librosa.feature.melspectrogram(
                y=y, sr=sr, n_mels=128, fmax=8000
            )

            # Convert to log scale
            log_mel = librosa.power_to_db(mel_spec, ref=np.max)

            # Create signature by averaging across time bins
            # This creates a compact representation
            time_bins = 32
            bin_size = log_mel.shape[1] // time_bins
            signature = []

            for i in range(time_bins):
                start = i * bin_size
                end = start + bin_size
                if end <= log_mel.shape[1]:
                    bin_avg = np.mean(log_mel[:, start:end], axis=1)
                    signature.extend(bin_avg.tolist())

            # Convert to bytes
            signature_bytes = struct.pack(f'{len(signature)}f', *signature)

            # Create hash
            fp_hash = hashlib.sha256(signature_bytes).hexdigest()

            return AudioFingerprint(
                hash=fp_hash,
                duration=duration,
                signature=signature_bytes,
                sample_rate=sr,
            )

        except Exception as e:
            raise ProcessingError(
                f"Spectral fingerprinting failed: {e}",
                file_path=str(file_path),
                operation="fingerprint",
                details={"error": str(e)}
            )

    def compare(
        self,
        fp1: AudioFingerprint,
        fp2: AudioFingerprint,
    ) -> float:
        """Compare two fingerprints and return similarity score.

        Args:
            fp1: First fingerprint
            fp2: Second fingerprint

        Returns:
            Similarity score from 0.0 (different) to 1.0 (identical)
        """
        # Quick check: exact hash match
        if fp1.hash == fp2.hash:
            return 1.0

        # Check duration difference (quick filter)
        duration_diff = abs(fp1.duration - fp2.duration)
        if duration_diff > 5.0:  # More than 5 seconds difference
            return 0.0

        # Compare signatures
        try:
            return self._compare_signatures(fp1.signature, fp2.signature)
        except Exception:
            return 0.0

    def _compare_signatures(
        self,
        sig1: bytes,
        sig2: bytes,
    ) -> float:
        """Compare two signature byte arrays.

        Args:
            sig1: First signature
            sig2: Second signature

        Returns:
            Similarity score 0.0 to 1.0
        """
        if len(sig1) != len(sig2):
            # Different lengths - can't compare directly
            return 0.0

        import numpy as np

        # Unpack floats
        n_floats = len(sig1) // 4
        arr1 = np.array(struct.unpack(f'{n_floats}f', sig1))
        arr2 = np.array(struct.unpack(f'{n_floats}f', sig2))

        # Normalize
        arr1 = (arr1 - np.mean(arr1)) / (np.std(arr1) + 1e-8)
        arr2 = (arr2 - np.mean(arr2)) / (np.std(arr2) + 1e-8)

        # Compute correlation
        correlation = np.corrcoef(arr1, arr2)[0, 1]

        # Convert to 0-1 range (correlation is -1 to 1)
        similarity = (correlation + 1) / 2

        return max(0.0, min(1.0, similarity))


# Fingerprint cache
_fingerprint_cache: dict = {}


def get_fingerprint(
    file_path: Path,
    use_cache: bool = True,
) -> AudioFingerprint:
    """Get fingerprint for a file, using cache if available.

    Args:
        file_path: Path to audio file
        use_cache: Whether to use cached fingerprints

    Returns:
        AudioFingerprint
    """
    cache_key = str(file_path.absolute())

    if use_cache and cache_key in _fingerprint_cache:
        return _fingerprint_cache[cache_key]

    generator = FingerprintGenerator()
    fingerprint = generator.generate(file_path)

    if use_cache:
        _fingerprint_cache[cache_key] = fingerprint

    return fingerprint


def clear_fingerprint_cache() -> None:
    """Clear the fingerprint cache."""
    global _fingerprint_cache
    _fingerprint_cache = {}
