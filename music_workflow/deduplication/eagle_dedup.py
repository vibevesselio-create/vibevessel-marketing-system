"""
Eagle library deduplication for music workflow.

This module provides deduplication checks against the Eagle library,
identifying duplicate tracks based on file and metadata matching.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import re

from music_workflow.core.models import TrackInfo, DeduplicationResult
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("eagle-dedup")


@dataclass
class EagleMatch:
    """A potential match from Eagle library."""
    item_id: str
    name: str
    tags: List[str]
    similarity_score: float
    match_type: str  # exact, filename, tag_match, fuzzy


class EagleDeduplicator:
    """Deduplication checker for Eagle library.

    Checks for duplicate tracks in the Eagle library
    using filename, tag, and metadata matching.
    """

    def __init__(
        self,
        eagle_client=None,
        similarity_threshold: float = 0.85,
    ):
        """Initialize the deduplicator.

        Args:
            eagle_client: Eagle API client instance
            similarity_threshold: Minimum similarity for fuzzy matches
        """
        self.eagle_client = eagle_client
        self.similarity_threshold = similarity_threshold

    def check_duplicate(self, track: TrackInfo) -> DeduplicationResult:
        """Check if a track already exists in Eagle library.

        Uses fingerprint matching as the primary strategy, falling back to
        filename and tag matching if no fingerprint is available.

        Args:
            track: Track to check

        Returns:
            DeduplicationResult with match information
        """
        if not self.eagle_client:
            logger.warning("Eagle client not configured")
            return DeduplicationResult(is_duplicate=False)

        # Strategy 1: Check by fingerprint (most reliable)
        if hasattr(track, 'fingerprint') and track.fingerprint:
            fingerprint_match = self._check_by_fingerprint(track.fingerprint)
            if fingerprint_match:
                logger.info(
                    f"Eagle duplicate found via fingerprint: '{track.title}' "
                    f"(fingerprint: {track.fingerprint[:16]}...)"
                )
                return fingerprint_match

        # Strategy 2: Check by existing Eagle ID
        if track.eagle_id:
            existing = self._check_by_eagle_id(track.eagle_id)
            if existing:
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_track_id=track.eagle_id,
                    matching_source="eagle",
                    similarity_score=1.0,
                )

        matches = []

        # Strategy 3: Check by filename
        if track.title and track.artist:
            filename_matches = self._check_by_filename(track.title, track.artist)
            matches.extend(filename_matches)

        # Strategy 4: Check by tags (artist tag)
        if track.artist:
            tag_matches = self._check_by_tags(track.artist, track.title)
            matches.extend(tag_matches)

        # Return best match
        if matches:
            best_match = max(matches, key=lambda m: m.similarity_score)

            if best_match.similarity_score >= self.similarity_threshold:
                logger.info(
                    f"Eagle duplicate found: '{track.title}' matches '{best_match.name}' "
                    f"(score: {best_match.similarity_score:.2f})"
                )
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_track_id=best_match.item_id,
                    matching_source="eagle",
                    similarity_score=best_match.similarity_score,
                    metadata_match=True,
                )

        return DeduplicationResult(is_duplicate=False)

    def _check_by_fingerprint(self, fingerprint: str) -> Optional[DeduplicationResult]:
        """Check for duplicates by fingerprint tag.

        Args:
            fingerprint: Fingerprint hash string

        Returns:
            DeduplicationResult if match found, None otherwise
        """
        try:
            # Search for items with matching fingerprint tag
            matching_items = self.eagle_client.search_by_fingerprint(fingerprint)

            if matching_items:
                # Return the first match (fingerprints are unique)
                best_match = matching_items[0]
                logger.debug(
                    f"Fingerprint match found: {best_match.name} "
                    f"(ID: {best_match.id})"
                )
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_track_id=best_match.id,
                    matching_source="eagle",
                    similarity_score=1.0,  # Fingerprint matches are exact
                    metadata_match=True,
                )

        except Exception as e:
            logger.warning(f"Fingerprint check failed: {e}")

        return None

    def _check_by_eagle_id(self, eagle_id: str) -> bool:
        """Check if an Eagle item exists by ID."""
        try:
            item = self.eagle_client.get_item(eagle_id)
            return item is not None
        except Exception as e:
            logger.warning(f"Eagle ID check failed: {e}")
            return False

    def _check_by_filename(self, title: str, artist: str) -> List[EagleMatch]:
        """Check for duplicates by filename pattern."""
        matches = []

        try:
            # Construct expected filename patterns
            patterns = [
                f"{title}",
                f"{artist} - {title}",
                f"{title} - {artist}",
            ]

            for pattern in patterns:
                normalized_pattern = self._normalize_filename(pattern)

                # Search Eagle library
                results = self.eagle_client.search(keyword=normalized_pattern[:30])

                for item in results:
                    # Handle both EagleItem objects and dicts
                    if hasattr(item, 'name'):
                        item_name = item.name
                        item_id = item.id
                        item_tags = item.tags
                    else:
                        item_name = item.get("name", "")
                        item_id = item.get("id", "")
                        item_tags = item.get("tags", [])

                    normalized_name = self._normalize_filename(item_name)

                    similarity = self._calculate_similarity(normalized_pattern, normalized_name)

                    if similarity >= 0.7:  # Lower threshold for initial matching
                        matches.append(EagleMatch(
                            item_id=item_id,
                            name=item_name,
                            tags=item_tags,
                            similarity_score=similarity,
                            match_type="filename" if similarity >= 0.9 else "fuzzy",
                        ))

        except Exception as e:
            logger.warning(f"Filename check failed: {e}")

        return matches

    def _check_by_tags(self, artist: str, title: Optional[str] = None) -> List[EagleMatch]:
        """Check for duplicates by artist tag."""
        matches = []

        try:
            # Normalize artist name for tag search
            artist_tag = self._normalize_for_tag(artist)

            # Search by artist tag - use search method with tags parameter
            results = self.eagle_client.search(tags=[artist_tag])

            for item in results:
                # Handle both EagleItem objects and dicts
                if hasattr(item, 'name'):
                    item_name = item.name
                    item_id = item.id
                    item_tags = item.tags
                else:
                    item_name = item.get("name", "")
                    item_id = item.get("id", "")
                    item_tags = item.get("tags", [])

                # Calculate relevance based on title match
                if title:
                    normalized_title = self._normalize_filename(title)
                    normalized_name = self._normalize_filename(item_name)
                    similarity = self._calculate_similarity(normalized_title, normalized_name)
                else:
                    similarity = 0.5  # Base score for artist match only

                matches.append(EagleMatch(
                    item_id=item_id,
                    name=item_name,
                    tags=item_tags,
                    similarity_score=min(similarity + 0.2, 1.0),  # Boost for tag match
                    match_type="tag_match",
                ))

        except Exception as e:
            logger.warning(f"Tag check failed: {e}")

        return matches

    def _normalize_filename(self, name: str) -> str:
        """Normalize filename for comparison."""
        name = name.lower().strip()
        # Remove file extension
        name = re.sub(r'\.\w+$', '', name)
        # Remove common suffixes
        name = re.sub(r'\s*[\(\[].*?[\)\]]', '', name)
        # Remove extra whitespace and punctuation
        name = re.sub(r'[^\w\s]', ' ', name)
        name = ' '.join(name.split())
        return name

    def _normalize_for_tag(self, text: str) -> str:
        """Normalize text for tag matching."""
        text = text.strip()
        # Eagle tags are typically CamelCase or with spaces
        # Try to match common formats
        return text

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings."""
        if not s1 or not s2:
            return 0.0

        s1 = s1.lower()
        s2 = s2.lower()

        if s1 == s2:
            return 1.0

        # Check for substring
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return shorter / longer

        # Character-based similarity
        set1 = set(s1)
        set2 = set(s2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        return intersection / union


def check_eagle_duplicate(
    track: TrackInfo,
    eagle_client=None,
) -> DeduplicationResult:
    """Convenience function to check for Eagle duplicates.

    Args:
        track: Track to check
        eagle_client: Eagle API client

    Returns:
        DeduplicationResult
    """
    deduplicator = EagleDeduplicator(eagle_client=eagle_client)
    return deduplicator.check_duplicate(track)
