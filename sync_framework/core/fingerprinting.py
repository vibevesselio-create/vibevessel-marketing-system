#!/usr/bin/env python3
"""
Generic Fingerprinting Engine
==============================

Provides fingerprint computation for all file types: audio, image, document, video, and generic files.
Supports hash-based change detection and perceptual hashing for media files.
"""

import hashlib
import json
import struct
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileFingerprint:
    """Representation of a file fingerprint."""
    hash: str  # Primary hash (SHA256)
    content_hash: str  # Content-based hash
    file_size: int
    file_path: str
    item_type: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FingerprintEngine:
    """Generic fingerprint computation engine for all file types."""
    
    def __init__(self):
        """Initialize the fingerprint engine."""
        self._cache: Dict[str, FileFingerprint] = {}
    
    def compute_fingerprint(
        self,
        file_path: Path,
        item_type: str,
        use_cache: bool = True
    ) -> FileFingerprint:
        """
        Compute fingerprint for a file based on item type.
        
        Args:
            file_path: Path to the file
            item_type: Type of item (determines fingerprinting strategy)
            use_cache: Whether to use cached fingerprints
            
        Returns:
            FileFingerprint object
        """
        cache_key = f"{item_type}:{file_path.absolute()}"
        
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        # Determine fingerprinting strategy based on item type
        item_type_lower = item_type.lower()
        
        if any(keyword in item_type_lower for keyword in ['audio', 'music', 'track', 'sound']):
            fingerprint = self._compute_audio_fingerprint(file_path, item_type)
        elif any(keyword in item_type_lower for keyword in ['image', 'photo', 'picture', 'png', 'jpeg', 'jpg']):
            fingerprint = self._compute_image_fingerprint(file_path, item_type)
        elif any(keyword in item_type_lower for keyword in ['video', 'movie', 'clip', 'mp4', 'mov']):
            fingerprint = self._compute_video_fingerprint(file_path, item_type)
        elif any(keyword in item_type_lower for keyword in ['document', 'doc', 'pdf', 'text']):
            fingerprint = self._compute_document_fingerprint(file_path, item_type)
        else:
            fingerprint = self._compute_generic_fingerprint(file_path, item_type)
        
        if use_cache:
            self._cache[cache_key] = fingerprint
        
        return fingerprint
    
    def compute_content_hash(self, content: bytes) -> str:
        """
        Compute content hash for change detection.
        
        Args:
            content: File content as bytes
            
        Returns:
            SHA256 hash string
        """
        return hashlib.sha256(content).hexdigest()
    
    def _compute_audio_fingerprint(
        self,
        file_path: Path,
        item_type: str
    ) -> FileFingerprint:
        """Compute fingerprint for audio files."""
        try:
            # Try chromaprint/acoustid first (best quality)
            try:
                import acoustid
                duration, fingerprint = acoustid.fingerprint_file(str(file_path))
                fp_hash = hashlib.sha256(fingerprint.encode()).hexdigest()
                
                metadata = {
                    "duration": duration,
                    "method": "chromaprint",
                    "signature": fingerprint
                }
            except ImportError:
                # Fallback to spectral hash
                fp_hash, metadata = self._compute_spectral_audio_hash(file_path)
        except Exception as e:
            logger.warning(f"Audio fingerprinting failed, using generic: {e}")
            fp_hash, metadata = self._compute_generic_fingerprint_internal(file_path)
        
        # Compute content hash
        content_hash = self._compute_file_content_hash(file_path)
        
        return FileFingerprint(
            hash=fp_hash,
            content_hash=content_hash,
            file_size=file_path.stat().st_size,
            file_path=str(file_path),
            item_type=item_type,
            metadata=metadata
        )
    
    def _compute_spectral_audio_hash(self, file_path: Path) -> Tuple[str, Dict[str, Any]]:
        """Compute spectral hash for audio (fallback method)."""
        try:
            import librosa
            import numpy as np
            
            y, sr = librosa.load(str(file_path), sr=22050, mono=True)
            duration = librosa.get_duration(y=y, sr=sr)
            
            # Compute mel spectrogram
            mel_spec = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
            log_mel = librosa.power_to_db(mel_spec, ref=np.max)
            
            # Create signature
            time_bins = 32
            bin_size = log_mel.shape[1] // time_bins
            signature = []
            
            for i in range(time_bins):
                start = i * bin_size
                end = start + bin_size
                if end <= log_mel.shape[1]:
                    bin_avg = np.mean(log_mel[:, start:end], axis=1)
                    signature.extend(bin_avg.tolist())
            
            signature_bytes = struct.pack(f'{len(signature)}f', *signature)
            fp_hash = hashlib.sha256(signature_bytes).hexdigest()
            
            return fp_hash, {
                "duration": duration,
                "method": "spectral",
                "sample_rate": sr
            }
        except ImportError:
            logger.warning("librosa not available, using generic hash")
            return self._compute_generic_fingerprint_internal(file_path)
    
    def _compute_image_fingerprint(
        self,
        file_path: Path,
        item_type: str
    ) -> FileFingerprint:
        """Compute fingerprint for image files using perceptual hashing."""
        try:
            from PIL import Image
            import imagehash
            
            with Image.open(file_path) as img:
                # Compute perceptual hash
                phash = imagehash.phash(img)
                ahash = imagehash.average_hash(img)
                
                # Combine hashes
                combined = f"{phash}{ahash}"
                fp_hash = hashlib.sha256(combined.encode()).hexdigest()
                
                metadata = {
                    "method": "perceptual_hash",
                    "phash": str(phash),
                    "ahash": str(ahash),
                    "size": img.size,
                    "format": img.format
                }
        except ImportError:
            logger.warning("PIL/imagehash not available, using generic hash")
            fp_hash, metadata = self._compute_generic_fingerprint_internal(file_path)
        except Exception as e:
            logger.warning(f"Image fingerprinting failed: {e}")
            fp_hash, metadata = self._compute_generic_fingerprint_internal(file_path)
        
        content_hash = self._compute_file_content_hash(file_path)
        
        return FileFingerprint(
            hash=fp_hash,
            content_hash=content_hash,
            file_size=file_path.stat().st_size,
            file_path=str(file_path),
            item_type=item_type,
            metadata=metadata
        )
    
    def _compute_video_fingerprint(
        self,
        file_path: Path,
        item_type: str
    ) -> FileFingerprint:
        """Compute fingerprint for video files."""
        # For now, use generic hash (can be enhanced with video-specific hashing)
        fp_hash, metadata = self._compute_generic_fingerprint_internal(file_path)
        content_hash = self._compute_file_content_hash(file_path)
        
        # Try to extract basic metadata
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info = json.loads(result.stdout)
                format_info = info.get("format", {})
                metadata.update({
                    "duration": format_info.get("duration"),
                    "size": format_info.get("size"),
                    "bit_rate": format_info.get("bit_rate")
                })
        except Exception:
            pass  # FFprobe not available or failed
        
        return FileFingerprint(
            hash=fp_hash,
            content_hash=content_hash,
            file_size=file_path.stat().st_size,
            file_path=str(file_path),
            item_type=item_type,
            metadata=metadata
        )
    
    def _compute_document_fingerprint(
        self,
        file_path: Path,
        item_type: str
    ) -> FileFingerprint:
        """Compute fingerprint for document files."""
        # Use content hash for documents (text-based)
        content_hash = self._compute_file_content_hash(file_path)
        
        # Also compute metadata hash
        stat = file_path.stat()
        metadata_str = json.dumps({
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "path": str(file_path)
        }, sort_keys=True)
        fp_hash = hashlib.sha256(metadata_str.encode()).hexdigest()
        
        return FileFingerprint(
            hash=fp_hash,
            content_hash=content_hash,
            file_size=stat.st_size,
            file_path=str(file_path),
            item_type=item_type,
            metadata={"method": "content_hash"}
        )
    
    def _compute_generic_fingerprint(
        self,
        file_path: Path,
        item_type: str
    ) -> FileFingerprint:
        """Compute generic fingerprint for unknown file types."""
        fp_hash, metadata = self._compute_generic_fingerprint_internal(file_path)
        content_hash = self._compute_file_content_hash(file_path)
        
        return FileFingerprint(
            hash=fp_hash,
            content_hash=content_hash,
            file_size=file_path.stat().st_size,
            file_path=str(file_path),
            item_type=item_type,
            metadata=metadata
        )
    
    def _compute_generic_fingerprint_internal(
        self,
        file_path: Path
    ) -> Tuple[str, Dict[str, Any]]:
        """Internal method to compute generic fingerprint."""
        stat = file_path.stat()
        metadata_str = json.dumps({
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "name": file_path.name
        }, sort_keys=True)
        fp_hash = hashlib.sha256(metadata_str.encode()).hexdigest()
        
        return fp_hash, {"method": "generic_metadata"}
    
    def _compute_file_content_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def compare_fingerprints(
        self,
        fp1: FileFingerprint,
        fp2: FileFingerprint
    ) -> float:
        """
        Compare two fingerprints and return similarity score.
        
        Args:
            fp1: First fingerprint
            fp2: Second fingerprint
            
        Returns:
            Similarity score from 0.0 (different) to 1.0 (identical)
        """
        # Exact hash match
        if fp1.hash == fp2.hash:
            return 1.0
        
        # Content hash match
        if fp1.content_hash == fp2.content_hash:
            return 1.0
        
        # For audio fingerprints, compare metadata
        if fp1.item_type.lower() in ['audio', 'music', 'track']:
            return self._compare_audio_fingerprints(fp1, fp2)
        
        # For image fingerprints, compare perceptual hashes
        if fp1.item_type.lower() in ['image', 'photo', 'picture']:
            return self._compare_image_fingerprints(fp1, fp2)
        
        # Default: no match
        return 0.0
    
    def _compare_audio_fingerprints(
        self,
        fp1: FileFingerprint,
        fp2: FileFingerprint
    ) -> float:
        """Compare audio fingerprints."""
        # If both have chromaprint signatures, compare them
        if (fp1.metadata.get("method") == "chromaprint" and
            fp2.metadata.get("method") == "chromaprint"):
            sig1 = fp1.metadata.get("signature", "")
            sig2 = fp2.metadata.get("signature", "")
            if sig1 == sig2:
                return 1.0
        
        # Compare duration
        dur1 = fp1.metadata.get("duration")
        dur2 = fp2.metadata.get("duration")
        if dur1 and dur2:
            duration_diff = abs(dur1 - dur2)
            if duration_diff < 0.5:
                return 0.9
            elif duration_diff < 2.0:
                return 0.7
        
        return 0.0
    
    def _compare_image_fingerprints(
        self,
        fp1: FileFingerprint,
        fp2: FileFingerprint
    ) -> float:
        """Compare image fingerprints using perceptual hash."""
        try:
            from PIL import Image
            import imagehash
            
            phash1_str = fp1.metadata.get("phash")
            phash2_str = fp2.metadata.get("phash")
            
            if phash1_str and phash2_str:
                phash1 = imagehash.hex_to_hash(phash1_str)
                phash2 = imagehash.hex_to_hash(phash2_str)
                hamming = phash1 - phash2
                # Convert hamming distance to similarity (0-1)
                # Max hamming distance for phash is 64
                similarity = 1.0 - (hamming / 64.0)
                return max(0.0, similarity)
        except Exception:
            pass
        
        return 0.0
    
    def clear_cache(self) -> None:
        """Clear the fingerprint cache."""
        self._cache.clear()


# Global instance
_global_engine: Optional[FingerprintEngine] = None


def get_fingerprint_engine() -> FingerprintEngine:
    """Get or create global FingerprintEngine instance."""
    global _global_engine
    if _global_engine is None:
        _global_engine = FingerprintEngine()
    return _global_engine
