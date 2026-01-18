"""Image fingerprinting for deduplication and identity resolution.

Provides SHA256 content hashing and perceptual hashing for image similarity matching.
Aligned with music_workflow patterns for consistent architecture.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Optional imports for perceptual hashing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not available - perceptual hashing disabled")

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    logger.warning("imagehash not available - perceptual hashing disabled")


@dataclass
class ImageFingerprint:
    """Complete fingerprint data for an image."""

    # Content-based hash (SHA256 of file bytes)
    content_hash: str

    # Perceptual hash (robust to minor edits)
    perceptual_hash: Optional[str] = None

    # Average hash (fast comparison)
    average_hash: Optional[str] = None

    # Difference hash (edge-based)
    difference_hash: Optional[str] = None

    # File metadata
    file_size: Optional[int] = None
    file_path: Optional[str] = None

    def __post_init__(self):
        """Validate fingerprint data."""
        if not self.content_hash:
            raise ValueError("content_hash is required")

    @property
    def uii(self) -> str:
        """Universal Image Identifier - the content hash."""
        return self.content_hash

    def matches_exact(self, other: 'ImageFingerprint') -> bool:
        """Check for exact match (identical files)."""
        return self.content_hash == other.content_hash

    def matches_perceptual(
        self,
        other: 'ImageFingerprint',
        threshold: int = 8
    ) -> bool:
        """Check for perceptual match (visually similar).

        Args:
            other: Another fingerprint to compare
            threshold: Maximum hamming distance for match (0-64, lower = stricter)

        Returns:
            True if images are perceptually similar
        """
        if not self.perceptual_hash or not other.perceptual_hash:
            return False

        try:
            distance = _hamming_distance(self.perceptual_hash, other.perceptual_hash)
            return distance <= threshold
        except Exception as e:
            logger.warning(f"Perceptual comparison failed: {e}")
            return False

    def similarity_score(self, other: 'ImageFingerprint') -> float:
        """Calculate similarity score between 0.0 and 1.0.

        Returns:
            1.0 for identical, 0.0 for completely different
        """
        if self.matches_exact(other):
            return 1.0

        if not self.perceptual_hash or not other.perceptual_hash:
            return 0.0

        try:
            distance = _hamming_distance(self.perceptual_hash, other.perceptual_hash)
            # Max distance is 64 for 64-bit hash
            return max(0.0, 1.0 - (distance / 64.0))
        except Exception:
            return 0.0


class FingerprintGenerator:
    """Generates fingerprints for images.

    Supports both content hashing (SHA256) and perceptual hashing
    for robust deduplication across different environments.
    """

    def __init__(
        self,
        enable_perceptual: bool = True,
        hash_size: int = 8,
        buffer_size: int = 65536
    ):
        """Initialize the fingerprint generator.

        Args:
            enable_perceptual: Whether to compute perceptual hashes
            hash_size: Size for perceptual hash (8 = 64-bit hash)
            buffer_size: Buffer size for file reading
        """
        self.enable_perceptual = enable_perceptual and PIL_AVAILABLE and IMAGEHASH_AVAILABLE
        self.hash_size = hash_size
        self.buffer_size = buffer_size

        if enable_perceptual and not self.enable_perceptual:
            logger.warning(
                "Perceptual hashing requested but dependencies not available. "
                "Install with: pip install Pillow imagehash"
            )

    def generate(
        self,
        source: Union[str, Path, bytes],
        include_perceptual: bool = True
    ) -> ImageFingerprint:
        """Generate fingerprint for an image.

        Args:
            source: File path or raw bytes
            include_perceptual: Whether to include perceptual hashes

        Returns:
            ImageFingerprint with computed hashes
        """
        if isinstance(source, bytes):
            return self._from_bytes(source, include_perceptual)
        else:
            return self._from_file(Path(source), include_perceptual)

    def _from_file(
        self,
        path: Path,
        include_perceptual: bool
    ) -> ImageFingerprint:
        """Generate fingerprint from file path."""
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        # Compute content hash
        content_hash = compute_file_hash(path, buffer_size=self.buffer_size)
        file_size = path.stat().st_size

        # Compute perceptual hashes if enabled
        perceptual_hash = None
        average_hash = None
        difference_hash = None

        if include_perceptual and self.enable_perceptual:
            try:
                perceptual_hash = compute_perceptual_hash(path, self.hash_size)
                average_hash = _compute_average_hash(path, self.hash_size)
                difference_hash = _compute_difference_hash(path, self.hash_size)
            except Exception as e:
                logger.warning(f"Failed to compute perceptual hash for {path}: {e}")

        return ImageFingerprint(
            content_hash=content_hash,
            perceptual_hash=perceptual_hash,
            average_hash=average_hash,
            difference_hash=difference_hash,
            file_size=file_size,
            file_path=str(path)
        )

    def _from_bytes(
        self,
        data: bytes,
        include_perceptual: bool
    ) -> ImageFingerprint:
        """Generate fingerprint from raw bytes."""
        # Compute content hash
        content_hash = hashlib.sha256(data).hexdigest()

        # Compute perceptual hashes if enabled
        perceptual_hash = None
        average_hash = None
        difference_hash = None

        if include_perceptual and self.enable_perceptual:
            try:
                import io
                img = Image.open(io.BytesIO(data))
                perceptual_hash = str(imagehash.phash(img, hash_size=self.hash_size))
                average_hash = str(imagehash.average_hash(img, hash_size=self.hash_size))
                difference_hash = str(imagehash.dhash(img, hash_size=self.hash_size))
            except Exception as e:
                logger.warning(f"Failed to compute perceptual hash from bytes: {e}")

        return ImageFingerprint(
            content_hash=content_hash,
            perceptual_hash=perceptual_hash,
            average_hash=average_hash,
            difference_hash=difference_hash,
            file_size=len(data)
        )


def compute_file_hash(
    path: Union[str, Path],
    algorithm: str = 'sha256',
    buffer_size: int = 65536
) -> str:
    """Compute hash of file contents.

    Args:
        path: Path to the file
        algorithm: Hash algorithm (sha256, md5, etc.)
        buffer_size: Read buffer size

    Returns:
        Hex digest of file hash
    """
    path = Path(path)
    hasher = hashlib.new(algorithm)

    with open(path, 'rb') as f:
        while chunk := f.read(buffer_size):
            hasher.update(chunk)

    return hasher.hexdigest()


def compute_perceptual_hash(
    path: Union[str, Path],
    hash_size: int = 8
) -> Optional[str]:
    """Compute perceptual hash of an image.

    Uses pHash algorithm which is robust to:
    - Scaling
    - Minor color adjustments
    - Small crops
    - Compression artifacts

    Args:
        path: Path to image file
        hash_size: Hash size (8 = 64-bit hash)

    Returns:
        Hex string of perceptual hash, or None if failed
    """
    if not PIL_AVAILABLE or not IMAGEHASH_AVAILABLE:
        return None

    try:
        img = Image.open(path)
        phash = imagehash.phash(img, hash_size=hash_size)
        return str(phash)
    except Exception as e:
        logger.warning(f"Failed to compute perceptual hash: {e}")
        return None


def _compute_average_hash(
    path: Union[str, Path],
    hash_size: int = 8
) -> Optional[str]:
    """Compute average hash (aHash) of an image."""
    if not PIL_AVAILABLE or not IMAGEHASH_AVAILABLE:
        return None

    try:
        img = Image.open(path)
        ahash = imagehash.average_hash(img, hash_size=hash_size)
        return str(ahash)
    except Exception:
        return None


def _compute_difference_hash(
    path: Union[str, Path],
    hash_size: int = 8
) -> Optional[str]:
    """Compute difference hash (dHash) of an image."""
    if not PIL_AVAILABLE or not IMAGEHASH_AVAILABLE:
        return None

    try:
        img = Image.open(path)
        dhash = imagehash.dhash(img, hash_size=hash_size)
        return str(dhash)
    except Exception:
        return None


def _hamming_distance(hash1: str, hash2: str) -> int:
    """Calculate Hamming distance between two hex hash strings.

    Args:
        hash1: First hash as hex string
        hash2: Second hash as hex string

    Returns:
        Number of differing bits
    """
    if len(hash1) != len(hash2):
        raise ValueError(f"Hash length mismatch: {len(hash1)} vs {len(hash2)}")

    # Convert hex to integers and XOR
    int1 = int(hash1, 16)
    int2 = int(hash2, 16)
    xor_result = int1 ^ int2

    # Count set bits (differing positions)
    return bin(xor_result).count('1')
