"""Match Rekordbox tracks to Notion Music Tracks database.

This module provides track matching capabilities similar to the djay Pro
integration, enabling unified cross-platform library management.

The matcher supports multiple matching strategies:
1. Exact match by Rekordbox ID (if previously synced)
2. Exact match by file path
3. Fuzzy match by title + artist combination

Example usage:
    from rekordbox.matcher import RekordboxTrackMatcher

    matcher = RekordboxTrackMatcher(notion_client, MUSIC_TRACKS_DB_ID)
    match = matcher.match_track(rekordbox_track)

    if match.notion_page_id:
        print(f"Matched: {match.match_method} ({match.similarity_score:.0%})")
"""

import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .models import RekordboxTrack

logger = logging.getLogger("rekordbox.matcher")


@dataclass
class RekordboxTrackMatch:
    """Result of matching a Rekordbox track to Notion.

    Attributes:
        rekordbox_track: The source Rekordbox track
        notion_page_id: Matched Notion page ID (None if not matched)
        match_method: How the match was found (exact_id, path, fuzzy_title)
        similarity_score: Confidence score (0.0 to 1.0)
        is_new: Whether this is a new track not in Notion
        notion_properties: Cached Notion properties for the matched page
    """
    rekordbox_track: RekordboxTrack
    notion_page_id: Optional[str] = None
    match_method: str = "none"
    similarity_score: float = 0.0
    is_new: bool = True
    notion_properties: Optional[Dict] = None


class RekordboxTrackMatcher:
    """Match Rekordbox tracks to Notion Music Tracks database.

    This class builds in-memory indexes of Notion tracks for fast
    matching, then provides methods to find matches for Rekordbox tracks.

    Attributes:
        notion: Notion API client
        db_id: Music Tracks database ID
        fuzzy_threshold: Minimum similarity for fuzzy matches (default 0.85)
    """

    def __init__(
        self,
        notion_client,
        music_tracks_db_id: str,
        fuzzy_threshold: float = 0.85
    ):
        """Initialize the matcher.

        Args:
            notion_client: Configured Notion API client
            music_tracks_db_id: Notion database ID for Music Tracks
            fuzzy_threshold: Minimum similarity score for fuzzy matches
        """
        self.notion = notion_client
        self.db_id = music_tracks_db_id
        self.fuzzy_threshold = fuzzy_threshold

        # Cache for Notion tracks
        self._notion_tracks: Dict[str, Dict] = {}

        # Lookup indexes
        self._rekordbox_id_index: Dict[int, str] = {}
        self._path_index: Dict[str, str] = {}
        self._filename_index: Dict[str, str] = {}
        self._title_artist_index: Dict[str, str] = {}

        self._cache_loaded = False

    def load_notion_cache(self, force_reload: bool = False):
        """Load all Notion tracks into memory for fast matching.

        Args:
            force_reload: Reload cache even if already loaded
        """
        if self._cache_loaded and not force_reload:
            return

        logger.info("Loading Notion Music Tracks cache...")

        # Clear existing cache
        self._notion_tracks.clear()
        self._rekordbox_id_index.clear()
        self._path_index.clear()
        self._filename_index.clear()
        self._title_artist_index.clear()

        # Query all tracks with relevant properties
        has_more = True
        start_cursor = None
        page_count = 0

        while has_more:
            response = self.notion.databases.query(
                database_id=self.db_id,
                start_cursor=start_cursor,
                page_size=100,
            )

            for page in response.get("results", []):
                page_id = page["id"]
                props = page.get("properties", {})

                # Extract properties
                track_info = {
                    "title": self._get_title(props),
                    "artist": self._get_rich_text(props, "Artist"),
                    "album": self._get_rich_text(props, "Album"),
                    "file_path": self._get_rich_text(props, "File Path"),
                    "rekordbox_id": self._get_number(props, "Rekordbox ID"),
                    "djay_pro_id": self._get_rich_text(props, "djay Pro ID"),
                    "bpm": self._get_number(props, "Tempo"),
                    "key": self._get_rich_text(props, "Key"),
                }

                self._notion_tracks[page_id] = track_info
                self._build_indexes(page_id, track_info)
                page_count += 1

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        self._cache_loaded = True
        logger.info(f"Loaded {page_count} tracks into cache")
        logger.info(f"  Rekordbox ID index: {len(self._rekordbox_id_index)} entries")
        logger.info(f"  Path index: {len(self._path_index)} entries")
        logger.info(f"  Title/Artist index: {len(self._title_artist_index)} entries")

    def _build_indexes(self, page_id: str, track_info: Dict):
        """Build lookup indexes for a track.

        Args:
            page_id: Notion page ID
            track_info: Track property dictionary
        """
        # Rekordbox ID index (exact)
        rb_id = track_info.get("rekordbox_id")
        if rb_id is not None:
            self._rekordbox_id_index[int(rb_id)] = page_id

        # File path index (case-insensitive)
        file_path = track_info.get("file_path")
        if file_path:
            self._path_index[file_path.lower()] = page_id

            # Also index by filename only
            filename = Path(file_path).name.lower()
            if filename:
                self._filename_index[filename] = page_id

        # Title + Artist index (for fuzzy matching)
        title = track_info.get("title")
        if title:
            artist = track_info.get("artist") or ""
            key = self._make_title_artist_key(title, artist)
            self._title_artist_index[key] = page_id

    def _make_title_artist_key(self, title: str, artist: str) -> str:
        """Create normalized key for title/artist matching.

        Args:
            title: Track title
            artist: Artist name

        Returns:
            Normalized lowercase key
        """
        # Normalize: lowercase, strip, combine
        title_norm = (title or "").lower().strip()
        artist_norm = (artist or "").lower().strip()
        return f"{title_norm}|{artist_norm}"

    def match_track(self, track: RekordboxTrack) -> RekordboxTrackMatch:
        """Match a single Rekordbox track to Notion.

        Tries matching in order of reliability:
        1. Rekordbox ID (exact)
        2. File path (exact)
        3. Filename only (exact)
        4. Title + Artist (fuzzy)

        Args:
            track: Rekordbox track to match

        Returns:
            RekordboxTrackMatch with results
        """
        self.load_notion_cache()

        result = RekordboxTrackMatch(rekordbox_track=track)

        # 1. Match by Rekordbox ID (exact)
        if track.track_id in self._rekordbox_id_index:
            page_id = self._rekordbox_id_index[track.track_id]
            result.notion_page_id = page_id
            result.match_method = "exact_rekordbox_id"
            result.similarity_score = 1.0
            result.is_new = False
            result.notion_properties = self._notion_tracks.get(page_id)
            return result

        # 2. Match by file path (exact)
        if track.file_path:
            path_key = track.file_path.lower()
            if path_key in self._path_index:
                page_id = self._path_index[path_key]
                result.notion_page_id = page_id
                result.match_method = "exact_path"
                result.similarity_score = 1.0
                result.is_new = False
                result.notion_properties = self._notion_tracks.get(page_id)
                return result

        # 3. Match by filename only (exact)
        if track.file_path:
            filename = Path(track.file_path).name.lower()
            if filename in self._filename_index:
                page_id = self._filename_index[filename]
                result.notion_page_id = page_id
                result.match_method = "exact_filename"
                result.similarity_score = 0.95  # Slightly lower confidence
                result.is_new = False
                result.notion_properties = self._notion_tracks.get(page_id)
                return result

        # 4. Match by title + artist (fuzzy)
        if track.title:
            best_match = self._fuzzy_match_title_artist(track.title, track.artist)
            if best_match:
                page_id, score = best_match
                if score >= self.fuzzy_threshold:
                    result.notion_page_id = page_id
                    result.match_method = "fuzzy_title_artist"
                    result.similarity_score = score
                    result.is_new = False
                    result.notion_properties = self._notion_tracks.get(page_id)
                    return result

        # No match found
        return result

    def match_tracks(
        self,
        tracks: List[RekordboxTrack],
        progress_callback: Optional[callable] = None
    ) -> List[RekordboxTrackMatch]:
        """Match multiple tracks.

        Args:
            tracks: List of Rekordbox tracks to match
            progress_callback: Optional callback(current, total)

        Returns:
            List of match results
        """
        self.load_notion_cache()
        results = []

        total = len(tracks)
        for idx, track in enumerate(tracks):
            result = self.match_track(track)
            results.append(result)

            if progress_callback and idx % 100 == 0:
                progress_callback(idx, total)

        return results

    def _fuzzy_match_title_artist(
        self,
        title: str,
        artist: str
    ) -> Optional[Tuple[str, float]]:
        """Find best fuzzy match for title/artist combination.

        Uses SequenceMatcher for similarity scoring, which handles
        common variations like different punctuation or spacing.

        Args:
            title: Track title to match
            artist: Artist name to match

        Returns:
            Tuple of (page_id, score) or None if no good match
        """
        query = self._make_title_artist_key(title, artist)

        best_match = None
        best_score = 0.0

        for key, page_id in self._title_artist_index.items():
            # Quick rejection: if lengths differ by more than 50%, skip
            if abs(len(query) - len(key)) > max(len(query), len(key)) * 0.5:
                continue

            score = SequenceMatcher(None, query, key).ratio()
            if score > best_score:
                best_score = score
                best_match = (page_id, score)

        return best_match if best_score >= self.fuzzy_threshold else None

    def get_match_statistics(
        self,
        matches: List[RekordboxTrackMatch]
    ) -> Dict[str, any]:
        """Calculate statistics for a set of match results.

        Args:
            matches: List of match results

        Returns:
            Dictionary with match statistics
        """
        total = len(matches)
        matched = sum(1 for m in matches if not m.is_new)
        unmatched = total - matched

        by_method = {}
        for m in matches:
            method = m.match_method
            by_method[method] = by_method.get(method, 0) + 1

        avg_score = (
            sum(m.similarity_score for m in matches if not m.is_new) / matched
            if matched > 0 else 0.0
        )

        return {
            "total": total,
            "matched": matched,
            "unmatched": unmatched,
            "match_rate": f"{100 * matched / total:.1f}%" if total > 0 else "0%",
            "by_method": by_method,
            "average_similarity": f"{avg_score:.2f}",
        }

    # Property extraction helpers

    def _get_title(self, props: Dict) -> Optional[str]:
        """Extract title from Notion properties."""
        # Try 'Title' first, then 'Name'
        for prop_name in ["Title", "Name"]:
            prop = props.get(prop_name)
            if prop and prop.get("title"):
                texts = prop["title"]
                if texts:
                    return texts[0].get("plain_text", "")
        return None

    def _get_rich_text(self, props: Dict, name: str) -> Optional[str]:
        """Extract rich text property value."""
        prop = props.get(name)
        if prop and prop.get("rich_text"):
            texts = prop["rich_text"]
            if texts:
                return texts[0].get("plain_text", "")
        return None

    def _get_number(self, props: Dict, name: str) -> Optional[float]:
        """Extract number property value."""
        prop = props.get(name)
        if prop and prop.get("number") is not None:
            return prop["number"]
        return None

    def _get_select(self, props: Dict, name: str) -> Optional[str]:
        """Extract select property value."""
        prop = props.get(name)
        if prop and prop.get("select"):
            return prop["select"].get("name")
        return None
