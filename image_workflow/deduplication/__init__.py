"""Image deduplication and matching modules.

Provides fingerprinting and matching capabilities for image deduplication:
- Content hashing (SHA256) for exact duplicate detection
- Perceptual hashing (pHash) for visual similarity matching
- Cascade matching strategy aligned with music_workflow patterns
"""

from image_workflow.deduplication.fingerprint import (
    FingerprintGenerator,
    ImageFingerprint,
    compute_file_hash,
    compute_perceptual_hash,
)
from image_workflow.deduplication.matcher import (
    DuplicateGroup,
    ImageMatcher,
    MatchResult,
    MatchStrategy,
)

__all__ = [
    # Fingerprinting
    "FingerprintGenerator",
    "ImageFingerprint",
    "compute_file_hash",
    "compute_perceptual_hash",
    # Matching
    "DuplicateGroup",
    "ImageMatcher",
    "MatchResult",
    "MatchStrategy",
]
