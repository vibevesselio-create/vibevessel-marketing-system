"""Image matching and deduplication with cascade strategy.

Provides multi-tier matching aligned with music_workflow patterns:
1. Exact match (content hash)
2. Perceptual match (visual similarity)
3. Metadata fuzzy match (filename, dates, dimensions)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from image_workflow.deduplication.fingerprint import (
    FingerprintGenerator,
    ImageFingerprint,
)

logger = logging.getLogger(__name__)


class MatchStrategy(Enum):
    """Matching strategy for deduplication."""

    EXACT_ONLY = "exact_only"          # Only content hash match
    PERCEPTUAL = "perceptual"           # Include perceptual similarity
    FUZZY = "fuzzy"                     # Include metadata fuzzy matching
    CASCADE = "cascade"                 # All strategies in priority order


@dataclass
class MatchResult:
    """Result of a match comparison between two images."""

    # The fingerprints being compared
    source: ImageFingerprint
    candidate: ImageFingerprint

    # Match type and confidence
    is_match: bool
    match_type: Optional[str] = None  # "exact", "perceptual", "metadata"
    confidence: float = 0.0           # 0.0 to 1.0

    # Additional context
    hamming_distance: Optional[int] = None
    metadata_score: Optional[float] = None

    def __repr__(self) -> str:
        if self.is_match:
            return f"MatchResult(match={self.match_type}, confidence={self.confidence:.2f})"
        return "MatchResult(no_match)"


@dataclass
class DuplicateGroup:
    """Group of duplicate images."""

    # The canonical/master image
    canonical: ImageFingerprint

    # All duplicates including canonical
    members: List[ImageFingerprint] = field(default_factory=list)

    # Match results for each member
    match_results: List[MatchResult] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of images in this duplicate group."""
        return len(self.members)

    @property
    def uii(self) -> str:
        """Universal Image Identifier for this group."""
        return self.canonical.uii


class ImageMatcher:
    """Matches images using cascade identity resolution.

    Implements the same cascade pattern as music_workflow:
    1. Exact match (content hash) - 100% confidence
    2. Perceptual match (visual similarity) - configurable threshold
    3. Metadata fuzzy match - filename, dates, dimensions
    """

    def __init__(
        self,
        strategy: MatchStrategy = MatchStrategy.CASCADE,
        perceptual_threshold: int = 8,
        metadata_threshold: float = 0.85,
        fingerprint_generator: Optional[FingerprintGenerator] = None
    ):
        """Initialize the matcher.

        Args:
            strategy: Matching strategy to use
            perceptual_threshold: Max hamming distance for perceptual match (0-64)
            metadata_threshold: Min score for metadata fuzzy match (0.0-1.0)
            fingerprint_generator: Optional shared fingerprint generator
        """
        self.strategy = strategy
        self.perceptual_threshold = perceptual_threshold
        self.metadata_threshold = metadata_threshold
        self.fingerprint_generator = fingerprint_generator or FingerprintGenerator()

        # Cache of fingerprints by content hash
        self._fingerprint_cache: Dict[str, ImageFingerprint] = {}

    def compare(
        self,
        source: ImageFingerprint,
        candidate: ImageFingerprint,
        metadata_source: Optional[Dict] = None,
        metadata_candidate: Optional[Dict] = None
    ) -> MatchResult:
        """Compare two images for similarity.

        Args:
            source: Source image fingerprint
            candidate: Candidate image fingerprint
            metadata_source: Optional metadata for source image
            metadata_candidate: Optional metadata for candidate image

        Returns:
            MatchResult with match details
        """
        # 1. Exact match (always checked first)
        if source.matches_exact(candidate):
            return MatchResult(
                source=source,
                candidate=candidate,
                is_match=True,
                match_type="exact",
                confidence=1.0
            )

        # If exact-only strategy, stop here
        if self.strategy == MatchStrategy.EXACT_ONLY:
            return MatchResult(
                source=source,
                candidate=candidate,
                is_match=False
            )

        # 2. Perceptual match
        if self.strategy in (MatchStrategy.PERCEPTUAL, MatchStrategy.CASCADE):
            if source.perceptual_hash and candidate.perceptual_hash:
                is_perceptual_match = source.matches_perceptual(
                    candidate,
                    threshold=self.perceptual_threshold
                )

                if is_perceptual_match:
                    similarity = source.similarity_score(candidate)
                    hamming = _calculate_hamming(
                        source.perceptual_hash,
                        candidate.perceptual_hash
                    )

                    return MatchResult(
                        source=source,
                        candidate=candidate,
                        is_match=True,
                        match_type="perceptual",
                        confidence=similarity,
                        hamming_distance=hamming
                    )

        # 3. Metadata fuzzy match
        if self.strategy in (MatchStrategy.FUZZY, MatchStrategy.CASCADE):
            if metadata_source and metadata_candidate:
                metadata_score = self._compute_metadata_score(
                    metadata_source,
                    metadata_candidate
                )

                if metadata_score >= self.metadata_threshold:
                    return MatchResult(
                        source=source,
                        candidate=candidate,
                        is_match=True,
                        match_type="metadata",
                        confidence=metadata_score,
                        metadata_score=metadata_score
                    )

        # No match found
        return MatchResult(
            source=source,
            candidate=candidate,
            is_match=False
        )

    def find_duplicates(
        self,
        fingerprints: List[ImageFingerprint],
        metadata: Optional[Dict[str, Dict]] = None
    ) -> List[DuplicateGroup]:
        """Find duplicate groups in a collection of fingerprints.

        Args:
            fingerprints: List of image fingerprints to check
            metadata: Optional dict mapping content_hash to metadata

        Returns:
            List of DuplicateGroup objects
        """
        if not fingerprints:
            return []

        metadata = metadata or {}
        groups: List[DuplicateGroup] = []
        processed: set = set()

        for i, source in enumerate(fingerprints):
            if source.content_hash in processed:
                continue

            # Start a new group with this image as canonical
            group = DuplicateGroup(
                canonical=source,
                members=[source]
            )
            processed.add(source.content_hash)

            # Find all duplicates
            for j, candidate in enumerate(fingerprints):
                if i == j or candidate.content_hash in processed:
                    continue

                result = self.compare(
                    source,
                    candidate,
                    metadata.get(source.content_hash),
                    metadata.get(candidate.content_hash)
                )

                if result.is_match:
                    group.members.append(candidate)
                    group.match_results.append(result)
                    processed.add(candidate.content_hash)

            # Only add groups with actual duplicates
            if group.count > 1:
                groups.append(group)
                logger.debug(
                    f"Found duplicate group: {group.count} images, "
                    f"UII={group.uii[:16]}..."
                )

        logger.info(f"Found {len(groups)} duplicate groups")
        return groups

    def find_matches(
        self,
        source: ImageFingerprint,
        candidates: List[ImageFingerprint],
        metadata: Optional[Dict[str, Dict]] = None,
        limit: Optional[int] = None
    ) -> List[MatchResult]:
        """Find all matches for a source image.

        Args:
            source: Source image to match
            candidates: List of candidate images
            metadata: Optional metadata dict
            limit: Maximum number of matches to return

        Returns:
            List of MatchResult objects, sorted by confidence
        """
        metadata = metadata or {}
        matches = []

        for candidate in candidates:
            if source.content_hash == candidate.content_hash:
                continue

            result = self.compare(
                source,
                candidate,
                metadata.get(source.content_hash),
                metadata.get(candidate.content_hash)
            )

            if result.is_match:
                matches.append(result)

        # Sort by confidence descending
        matches.sort(key=lambda r: r.confidence, reverse=True)

        if limit:
            matches = matches[:limit]

        return matches

    def _compute_metadata_score(
        self,
        meta1: Dict,
        meta2: Dict
    ) -> float:
        """Compute similarity score based on metadata.

        Checks:
        - Filename similarity
        - Capture date match
        - Dimensions match
        - Camera/device match

        Returns:
            Score between 0.0 and 1.0
        """
        scores = []
        weights = []

        # Filename similarity (weight: 0.3)
        if 'filename' in meta1 and 'filename' in meta2:
            filename_sim = _string_similarity(
                meta1['filename'],
                meta2['filename']
            )
            scores.append(filename_sim)
            weights.append(0.3)

        # Capture date match (weight: 0.25)
        if 'capture_time' in meta1 and 'capture_time' in meta2:
            if meta1['capture_time'] == meta2['capture_time']:
                scores.append(1.0)
            else:
                scores.append(0.0)
            weights.append(0.25)

        # Dimensions match (weight: 0.25)
        if all(k in meta1 and k in meta2 for k in ['width', 'height']):
            if (meta1['width'] == meta2['width'] and
                meta1['height'] == meta2['height']):
                scores.append(1.0)
            else:
                # Check for common aspect ratio
                ratio1 = meta1['width'] / max(meta1['height'], 1)
                ratio2 = meta2['width'] / max(meta2['height'], 1)
                if abs(ratio1 - ratio2) < 0.01:
                    scores.append(0.7)  # Same aspect ratio
                else:
                    scores.append(0.0)
            weights.append(0.25)

        # Camera match (weight: 0.2)
        if 'camera' in meta1 and 'camera' in meta2:
            if meta1['camera'] == meta2['camera']:
                scores.append(1.0)
            else:
                scores.append(0.0)
            weights.append(0.2)

        if not scores:
            return 0.0

        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def add_to_cache(self, fingerprint: ImageFingerprint) -> None:
        """Add a fingerprint to the cache."""
        self._fingerprint_cache[fingerprint.content_hash] = fingerprint

    def get_from_cache(self, content_hash: str) -> Optional[ImageFingerprint]:
        """Get a fingerprint from cache by content hash."""
        return self._fingerprint_cache.get(content_hash)

    def clear_cache(self) -> None:
        """Clear the fingerprint cache."""
        self._fingerprint_cache.clear()


def _calculate_hamming(hash1: str, hash2: str) -> int:
    """Calculate Hamming distance between two hex hash strings."""
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)
        return bin(int1 ^ int2).count('1')
    except (ValueError, TypeError):
        return 64  # Max distance


def _string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity using simple ratio.

    Returns value between 0.0 and 1.0.
    """
    if not s1 or not s2:
        return 0.0

    s1 = s1.lower()
    s2 = s2.lower()

    if s1 == s2:
        return 1.0

    # Simple Jaccard similarity on character sets
    set1 = set(s1)
    set2 = set(s2)
    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0
