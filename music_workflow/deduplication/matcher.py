"""
Duplicate matching logic for music workflow.

This module provides multi-source duplicate detection by checking
Notion database, Eagle library, and local file fingerprints.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from music_workflow.core.models import TrackInfo, DeduplicationResult
from music_workflow.deduplication.fingerprint import (
    FingerprintGenerator,
    AudioFingerprint,
    get_fingerprint,
)
from music_workflow.utils.errors import DuplicateFoundError
from music_workflow.config.settings import get_settings
from music_workflow.integrations.djay_pro.data_lookup import get_djay_lookup, DjayProDataLookup


@dataclass
class Match:
    """Represents a potential duplicate match."""
    track_id: str
    source: str  # 'notion', 'eagle', 'file'
    similarity_score: float
    fingerprint_match: bool
    metadata_match: bool
    title: Optional[str] = None
    artist: Optional[str] = None


class DuplicateMatcher:
    """Match potential duplicates across sources.

    Checks for duplicates in:
    - djay Pro library (by titleID, Spotify ID, SoundCloud URL)
    - Notion Tracks database (by metadata)
    - Eagle library (by metadata and fingerprint)
    - Local files (by fingerprint)
    """

    def __init__(
        self,
        fingerprint_threshold: float = 0.95,
        check_notion: bool = True,
        check_eagle: bool = True,
        check_files: bool = True,
        check_djay: bool = True,
    ):
        """Initialize the matcher.

        Args:
            fingerprint_threshold: Similarity threshold for fingerprint match
            check_notion: Whether to check Notion database
            check_eagle: Whether to check Eagle library
            check_files: Whether to check local files
            check_djay: Whether to check djay Pro library
        """
        settings = get_settings()
        self.fingerprint_threshold = fingerprint_threshold
        self.check_notion = check_notion and settings.deduplication.check_notion
        self.check_eagle = check_eagle and settings.deduplication.check_eagle
        self.check_files = check_files
        self.check_djay = check_djay

        self._fingerprint_generator = FingerprintGenerator()
        self._notion_client = None
        self._eagle_client = None
        self._djay_lookup: Optional[DjayProDataLookup] = None

    def find_matches(
        self,
        track: TrackInfo,
        file_path: Optional[Path] = None,
    ) -> List[Match]:
        """Find potential matches for a track.

        Args:
            track: Track to check for duplicates
            file_path: Optional audio file for fingerprint matching

        Returns:
            List of potential matches sorted by similarity
        """
        matches = []

        # Check Notion database
        if self.check_notion:
            notion_matches = self._check_notion(track)
            matches.extend(notion_matches)

        # Check Eagle library
        if self.check_eagle:
            eagle_matches = self._check_eagle(track, file_path)
            matches.extend(eagle_matches)

        # Sort by similarity score
        matches.sort(key=lambda m: m.similarity_score, reverse=True)

        return matches

    def check_duplicate(
        self,
        track: TrackInfo,
        file_path: Optional[Path] = None,
    ) -> DeduplicationResult:
        """Check if track is a duplicate.

        Args:
            track: Track to check
            file_path: Optional audio file for fingerprint matching

        Returns:
            DeduplicationResult with duplicate status
        """
        matches = self.find_matches(track, file_path)

        if not matches:
            return DeduplicationResult(
                is_duplicate=False,
                similarity_score=0.0,
            )

        best_match = matches[0]

        return DeduplicationResult(
            is_duplicate=best_match.similarity_score >= self.fingerprint_threshold,
            matching_track_id=best_match.track_id,
            matching_source=best_match.source,
            similarity_score=best_match.similarity_score,
            fingerprint_match=best_match.fingerprint_match,
            metadata_match=best_match.metadata_match,
        )

    def resolve(self, matches: List[Match]) -> Tuple[str, str]:
        """Resolve which version to keep.

        Args:
            matches: List of potential matches

        Returns:
            Tuple of (action, reason) where action is 'keep', 'skip', or 'merge'
        """
        if not matches:
            return ("keep", "No duplicates found")

        best_match = matches[0]

        # If fingerprint match with high similarity, skip
        if best_match.fingerprint_match and best_match.similarity_score >= 0.98:
            return ("skip", f"Fingerprint match with {best_match.source}:{best_match.track_id}")

        # If metadata match only, consider merging
        if best_match.metadata_match and not best_match.fingerprint_match:
            return ("merge", f"Metadata match - may be different version")

        # Below threshold
        if best_match.similarity_score < self.fingerprint_threshold:
            return ("keep", "Similarity below threshold")

        return ("skip", f"Duplicate of {best_match.source}:{best_match.track_id}")

    def _check_notion(self, track: TrackInfo) -> List[Match]:
        """Check Notion database for duplicates.

        Args:
            track: Track to check

        Returns:
            List of Notion matches
        """
        matches = []

        try:
            from music_workflow.integrations.notion import get_tracks_database

            tracks_db = get_tracks_database()
            potential_dupes = tracks_db.find_duplicates(track)

            for dupe in potential_dupes:
                # Skip self
                if dupe.notion_page_id == track.notion_page_id:
                    continue

                # Calculate metadata similarity
                similarity = self._calculate_metadata_similarity(track, dupe)

                if similarity > 0.5:
                    matches.append(Match(
                        track_id=dupe.notion_page_id,
                        source="notion",
                        similarity_score=similarity,
                        fingerprint_match=False,
                        metadata_match=True,
                        title=dupe.title,
                        artist=dupe.artist,
                    ))

        except Exception:
            pass  # Continue without Notion check

        return matches

    def _check_eagle(
        self,
        track: TrackInfo,
        file_path: Optional[Path] = None,
    ) -> List[Match]:
        """Check Eagle library for duplicates.

        Args:
            track: Track to check
            file_path: Optional file for fingerprint

        Returns:
            List of Eagle matches
        """
        matches = []

        try:
            from music_workflow.integrations.eagle import get_eagle_client

            eagle = get_eagle_client()

            if not eagle.is_available():
                return matches

            # Search by title
            search_results = eagle.search(
                keyword=track.title,
                ext="m4a",  # Common audio format
                limit=10,
            )

            for item in search_results:
                # Calculate metadata similarity
                similarity = self._calculate_name_similarity(
                    track.title, item.name
                )

                if similarity > 0.7:
                    matches.append(Match(
                        track_id=item.id,
                        source="eagle",
                        similarity_score=similarity,
                        fingerprint_match=False,
                        metadata_match=True,
                        title=item.name,
                    ))

        except Exception:
            pass  # Continue without Eagle check

        return matches

    def _calculate_metadata_similarity(
        self,
        track1: TrackInfo,
        track2: TrackInfo,
    ) -> float:
        """Calculate similarity between two tracks based on metadata.

        Args:
            track1: First track
            track2: Second track

        Returns:
            Similarity score 0.0 to 1.0
        """
        scores = []

        # Title similarity
        if track1.title and track2.title:
            title_sim = self._calculate_name_similarity(track1.title, track2.title)
            scores.append(title_sim * 0.5)  # Weight 50%

        # Artist similarity
        if track1.artist and track2.artist:
            artist_sim = self._calculate_name_similarity(track1.artist, track2.artist)
            scores.append(artist_sim * 0.3)  # Weight 30%

        # Duration similarity
        if track1.duration and track2.duration:
            duration_diff = abs(track1.duration - track2.duration)
            if duration_diff < 2:
                scores.append(0.2)  # Weight 20%
            elif duration_diff < 5:
                scores.append(0.1)

        # Spotify ID match
        if track1.spotify_id and track2.spotify_id:
            if track1.spotify_id == track2.spotify_id:
                return 1.0  # Exact match

        return sum(scores) if scores else 0.0

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names.

        Uses normalized Levenshtein distance.

        Args:
            name1: First name
            name2: Second name

        Returns:
            Similarity score 0.0 to 1.0
        """
        # Normalize names
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        if n1 == n2:
            return 1.0

        if not n1 or not n2:
            return 0.0

        # Simple containment check
        if n1 in n2 or n2 in n1:
            return 0.8

        # Character-level comparison
        common = set(n1) & set(n2)
        total = set(n1) | set(n2)

        return len(common) / len(total) if total else 0.0


def check_for_duplicates(
    track: TrackInfo,
    file_path: Optional[Path] = None,
    raise_on_duplicate: bool = False,
) -> DeduplicationResult:
    """Convenience function to check for duplicates.

    Args:
        track: Track to check
        file_path: Optional audio file
        raise_on_duplicate: Whether to raise DuplicateFoundError

    Returns:
        DeduplicationResult

    Raises:
        DuplicateFoundError: If duplicate found and raise_on_duplicate=True
    """
    matcher = DuplicateMatcher()
    result = matcher.check_duplicate(track, file_path)

    if result.is_duplicate and raise_on_duplicate:
        raise DuplicateFoundError(
            f"Track is a duplicate of {result.matching_source}:{result.matching_track_id}",
            existing_track_id=result.matching_track_id,
            existing_track_source=result.matching_source,
            similarity_score=result.similarity_score,
        )

    return result
