"""
Audio processing logic for music workflow.

This module provides audio analysis (BPM, key detection), normalization,
and format conversion capabilities.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Any

from music_workflow.core.models import AudioAnalysis, TrackInfo
from music_workflow.utils.errors import ProcessingError
from music_workflow.utils.validators import validate_audio_file, validate_bpm
from music_workflow.config.constants import DEFAULT_TARGET_LUFS, LOSSLESS_FORMATS


@dataclass
class ProcessingOptions:
    """Options for audio processing operations."""
    target_lufs: float = DEFAULT_TARGET_LUFS
    analyze_bpm: bool = True
    analyze_key: bool = True
    preserve_original: bool = True
    output_format: Optional[str] = None


class AudioProcessor:
    """Audio processing operations.

    Provides BPM detection, key analysis, loudness normalization,
    and format conversion.
    """

    def __init__(self, options: Optional[ProcessingOptions] = None):
        """Initialize the processor.

        Args:
            options: Processing options
        """
        self.options = options or ProcessingOptions()
        self._librosa = None
        self._mutagen = None

    def _get_librosa(self):
        """Get librosa instance (lazy loading)."""
        if self._librosa is None:
            try:
                import librosa
                self._librosa = librosa
            except ImportError:
                raise ProcessingError(
                    "librosa is not installed",
                    details={"hint": "Install with: pip install librosa"},
                )
        return self._librosa

    def _get_mutagen(self):
        """Get mutagen instance (lazy loading)."""
        if self._mutagen is None:
            try:
                import mutagen
                self._mutagen = mutagen
            except ImportError:
                raise ProcessingError(
                    "mutagen is not installed",
                    details={"hint": "Install with: pip install mutagen"},
                )
        return self._mutagen

    def analyze(self, file_path: Path) -> AudioAnalysis:
        """Analyze audio file for BPM, key, duration.

        Args:
            file_path: Path to audio file

        Returns:
            AudioAnalysis with detected values

        Raises:
            ProcessingError: If analysis fails
        """
        validate_audio_file(file_path)
        librosa = self._get_librosa()

        try:
            # Load audio
            y, sr = librosa.load(str(file_path), sr=None)
            duration = librosa.get_duration(y=y, sr=sr)

            # Detect BPM
            bpm = None
            if self.options.analyze_bpm:
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm = float(tempo)

            # Detect key (simplified - use Essentia for better results)
            key = None
            if self.options.analyze_key:
                key = self._detect_key(y, sr)

            # Get audio properties
            channels = 1 if y.ndim == 1 else y.shape[0]

            return AudioAnalysis(
                bpm=bpm,
                key=key or "Unknown",
                duration=duration,
                sample_rate=sr,
                channels=channels,
            )

        except Exception as e:
            raise ProcessingError(
                f"Audio analysis failed: {e}",
                file_path=str(file_path),
                operation="analyze",
                details={"error": str(e)},
            )

    def _detect_key(self, y, sr) -> Optional[str]:
        """Detect musical key using chroma features.

        Args:
            y: Audio time series
            sr: Sample rate

        Returns:
            Detected key or None
        """
        librosa = self._get_librosa()

        try:
            # Compute chroma features
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)

            # Sum across time to get pitch class distribution
            chroma_sum = chroma.sum(axis=1)

            # Define key profiles (Krumhansl-Schmuckler)
            major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
            minor_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

            keys = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

            best_key = None
            best_corr = -1

            import numpy as np
            for i, key in enumerate(keys):
                # Rotate chroma to match key
                rotated = np.roll(chroma_sum, -i)

                # Correlate with major and minor profiles
                major_corr = np.corrcoef(rotated, major_profile)[0, 1]
                minor_corr = np.corrcoef(rotated, minor_profile)[0, 1]

                if major_corr > best_corr:
                    best_corr = major_corr
                    best_key = key
                if minor_corr > best_corr:
                    best_corr = minor_corr
                    best_key = f"{key}m"

            return best_key

        except Exception:
            return None

    def convert(
        self,
        source: Path,
        target_format: str,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """Convert audio file to target format.

        Args:
            source: Source file path
            target_format: Target format (e.g., "wav", "aiff", "m4a")
            output_dir: Output directory (defaults to source directory)

        Returns:
            Path to converted file

        Raises:
            ProcessingError: If conversion fails
        """
        validate_audio_file(source)

        output_dir = output_dir or source.parent
        output_path = output_dir / f"{source.stem}.{target_format}"

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(str(source))

            # Map format to export parameters
            export_params = self._get_export_params(target_format)
            audio.export(str(output_path), **export_params)

            if not output_path.exists():
                raise ProcessingError(
                    "Conversion failed - output file not created",
                    file_path=str(source),
                    operation="convert",
                )

            return output_path

        except ImportError:
            raise ProcessingError(
                "pydub is not installed",
                details={"hint": "Install with: pip install pydub"},
            )
        except Exception as e:
            raise ProcessingError(
                f"Format conversion failed: {e}",
                file_path=str(source),
                operation="convert",
                details={"target_format": target_format, "error": str(e)},
            )

    def _get_export_params(self, target_format: str) -> Dict[str, Any]:
        """Get export parameters for a format."""
        params = {"format": target_format}

        if target_format in LOSSLESS_FORMATS:
            params["parameters"] = ["-acodec", "pcm_s16le"]
        elif target_format == "m4a":
            params["format"] = "mp4"
            params["codec"] = "aac"
            params["bitrate"] = "320k"
        elif target_format == "mp3":
            params["bitrate"] = "320k"

        return params

    def normalize(
        self,
        file_path: Path,
        target_lufs: Optional[float] = None,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Normalize audio to target loudness.

        Args:
            file_path: Input file path
            target_lufs: Target loudness in LUFS
            output_path: Output path (defaults to overwrite)

        Returns:
            Path to normalized file

        Raises:
            ProcessingError: If normalization fails
        """
        validate_audio_file(file_path)
        target_lufs = target_lufs or self.options.target_lufs
        output_path = output_path or file_path

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(str(file_path))

            # Calculate current loudness and normalize
            # Note: This is simplified - full LUFS calculation requires pyloudnorm
            current_db = audio.dBFS
            target_db = target_lufs + 23  # Approximate conversion

            change_db = target_db - current_db
            normalized = audio.apply_gain(change_db)

            # Export
            normalized.export(str(output_path), format=file_path.suffix.lstrip("."))

            return output_path

        except ImportError:
            raise ProcessingError(
                "pydub is not installed",
                details={"hint": "Install with: pip install pydub"},
            )
        except Exception as e:
            raise ProcessingError(
                f"Normalization failed: {e}",
                file_path=str(file_path),
                operation="normalize",
                details={"target_lufs": target_lufs, "error": str(e)},
            )

    def get_audio_info(self, file_path: Path) -> Dict[str, Any]:
        """Get basic audio file information using mutagen.

        Args:
            file_path: Audio file path

        Returns:
            Dictionary with audio information
        """
        validate_audio_file(file_path)
        mutagen = self._get_mutagen()

        try:
            audio = mutagen.File(str(file_path))
            if audio is None:
                return {}

            return {
                "duration": audio.info.length if hasattr(audio.info, "length") else None,
                "sample_rate": audio.info.sample_rate if hasattr(audio.info, "sample_rate") else None,
                "channels": audio.info.channels if hasattr(audio.info, "channels") else None,
                "bitrate": audio.info.bitrate if hasattr(audio.info, "bitrate") else None,
                "format": file_path.suffix.lstrip("."),
            }

        except Exception as e:
            raise ProcessingError(
                f"Failed to read audio info: {e}",
                file_path=str(file_path),
                operation="info",
                details={"error": str(e)},
            )
