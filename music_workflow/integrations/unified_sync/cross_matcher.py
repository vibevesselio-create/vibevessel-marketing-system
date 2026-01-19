"""Cross-platform track matching for unified library sync.

This module provides unified track matching across Apple Music, Rekordbox,
djay Pro, and Notion databases, creating a canonical view of each track
across all platforms.

Matching Strategy (in order of precedence):
1. Platform IDs (if previously synced)
2. File path (exact match)
3. Filename (exact match)
4. Title + Artist (fuzzy match)

Example usage:
    from unified_sync.cross_matcher import CrossPlatformMatcher

    matcher = CrossPlatformMatcher(notion_client, DB_ID)
    matcher.load_all_libraries()

    unified_tracks = matcher.build_unified_index()
    for track in unified_tracks:
        print(f"{track.canonical_title} - platforms: {track.platforms}")
"""

import logging
from typing import Optional, Dict, List, Set, Tuple, Any
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("unified_sync.cross_matcher")


@dataclass
class PlatformTrackRef:
    """Reference to a track in a specific platform.

    Attributes:
        platform: Platform name (apple_music, rekordbox, djay_pro, notion)
        platform_id: Platform-specific identifier
        title: Track title
        artist: Artist name
        album: Album name
        file_path: Local file path (if applicable)
        bpm: Beats per minute
        key: Musical key
        rating: Star rating (0-5)
        play_count: Number of plays
        raw_data: Full platform-specific data
    """
    platform: str
    platform_id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    file_path: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    rating: Optional[int] = None
    play_count: int = 0
    raw_data: Optional[Dict] = None


@dataclass
class UnifiedTrackMatch:
    """Unified view of a track across all platforms.

    Represents the canonical version of a track, with references
    to all platform-specific versions and conflict information.

    Attributes:
        match_id: Unique identifier for this unified match
        canonical_title: Authoritative title
        canonical_artist: Authoritative artist
        canonical_album: Authoritative album
        canonical_bpm: Authoritative BPM (from analysis)
        canonical_key: Authoritative musical key
        file_path: Common file path across platforms
        platforms: Set of platforms where this track exists
        platform_refs: Dictionary of platform references
        notion_page_id: Linked Notion page ID
        confidence_score: Match confidence (0.0 to 1.0)
        has_conflicts: Whether there are data conflicts
        conflicts: List of conflicting fields
    """
    match_id: str
    canonical_title: str = ""
    canonical_artist: str = ""
    canonical_album: str = ""
    canonical_bpm: Optional[float] = None
    canonical_key: Optional[str] = None
    file_path: Optional[str] = None
    platforms: Set[str] = field(default_factory=set)
    platform_refs: Dict[str, PlatformTrackRef] = field(default_factory=dict)
    notion_page_id: Optional[str] = None
    confidence_score: float = 0.0
    has_conflicts: bool = False
    conflicts: List[Dict] = field(default_factory=list)


class CrossPlatformMatcher:
    """Match tracks across Apple Music, Rekordbox, djay Pro, and Notion.

    This class builds unified track indexes from multiple platforms,
    enabling cross-platform operations and conflict detection.

    Attributes:
        notion: Notion API client
        db_id: Music Tracks database ID
        fuzzy_threshold: Minimum similarity for fuzzy matches
    """

    # Platform authority rankings (higher = more authoritative)
    # djay Pro wins for performance data (BPM/Key), Notion wins for metadata
    AUTHORITY_RANKING = {
        "bpm": ["djay_pro", "rekordbox", "apple_music", "notion"],
        "key": ["djay_pro", "rekordbox", "apple_music", "notion"],
        "title": ["notion", "apple_music", "rekordbox", "djay_pro"],
        "artist": ["notion", "apple_music", "rekordbox", "djay_pro"],
        "album": ["notion", "apple_music", "rekordbox", "djay_pro"],
        "rating": ["notion", "apple_music", "rekordbox", "djay_pro"],
    }

    def __init__(
        self,
        notion_client,
        music_tracks_db_id: str,
        fuzzy_threshold: float = 0.85
    ):
        """Initialize the cross-platform matcher.

        Args:
            notion_client: Configured Notion API client
            music_tracks_db_id: Notion database ID for Music Tracks
            fuzzy_threshold: Minimum similarity for fuzzy matches
        """
        self.notion = notion_client
        self.db_id = music_tracks_db_id
        self.fuzzy_threshold = fuzzy_threshold

        # Platform-specific track caches
        self._notion_tracks: Dict[str, PlatformTrackRef] = {}
        self._apple_music_tracks: Dict[str, PlatformTrackRef] = {}
        self._rekordbox_tracks: Dict[str, PlatformTrackRef] = {}
        self._djay_pro_tracks: Dict[str, PlatformTrackRef] = {}

        # Unified index
        self._unified_tracks: Dict[str, UnifiedTrackMatch] = {}

        # Lookup indexes
        self._path_index: Dict[str, Set[Tuple[str, str]]] = {}  # path -> set of (platform, id)
        self._filename_index: Dict[str, Set[Tuple[str, str]]] = {}
        self._title_artist_index: Dict[str, Set[Tuple[str, str]]] = {}

        self._caches_loaded = False

    def load_notion_tracks(self, force_reload: bool = False):
        """Load all Notion tracks into cache.

        Args:
            force_reload: Force reload even if cached
        """
        if self._notion_tracks and not force_reload:
            return

        logger.info("Loading Notion Music Tracks...")
        self._notion_tracks.clear()

        has_more = True
        start_cursor = None

        while has_more:
            response = self.notion.databases.query(
                database_id=self.db_id,
                start_cursor=start_cursor,
                page_size=100,
            )

            for page in response.get("results", []):
                page_id = page["id"]
                props = page.get("properties", {})

                ref = PlatformTrackRef(
                    platform="notion",
                    platform_id=page_id,
                    title=self._get_title(props) or "",
                    artist=self._get_rich_text(props, "Artist") or "",
                    album=self._get_rich_text(props, "Album") or "",
                    file_path=self._get_rich_text(props, "File Path"),
                    bpm=self._get_number(props, "Tempo"),
                    key=self._get_rich_text(props, "Key"),
                    rating=int(self._get_number(props, "Rating") or 0),
                    raw_data={
                        "apple_music_id": self._get_rich_text(props, "Apple Music ID"),
                        "rekordbox_id": self._get_number(props, "Rekordbox ID"),
                        "djay_pro_id": self._get_rich_text(props, "djay Pro ID"),
                    }
                )

                self._notion_tracks[page_id] = ref
                self._index_track("notion", page_id, ref)

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        logger.info(f"Loaded {len(self._notion_tracks)} Notion tracks")

    def load_apple_music_tracks(
        self,
        tracks: List[Any],
        force_reload: bool = False
    ):
        """Load Apple Music tracks into cache.

        Args:
            tracks: List of AppleMusicTrack objects
            force_reload: Force reload even if cached
        """
        if self._apple_music_tracks and not force_reload:
            return

        logger.info("Loading Apple Music tracks...")
        self._apple_music_tracks.clear()

        for track in tracks:
            ref = PlatformTrackRef(
                platform="apple_music",
                platform_id=track.persistent_id,
                title=track.name or "",
                artist=track.artist or "",
                album=track.album or "",
                file_path=track.location,
                bpm=float(track.bpm) if track.bpm else None,
                rating=track.rating // 20 if track.rating else None,  # Convert 0-100 to 0-5
                play_count=track.played_count,
                raw_data=track.__dict__,
            )

            self._apple_music_tracks[track.persistent_id] = ref
            self._index_track("apple_music", track.persistent_id, ref)

        logger.info(f"Loaded {len(self._apple_music_tracks)} Apple Music tracks")

    def load_rekordbox_tracks(
        self,
        tracks: List[Any],
        force_reload: bool = False
    ):
        """Load Rekordbox tracks into cache.

        Args:
            tracks: List of RekordboxTrack objects
            force_reload: Force reload even if cached
        """
        if self._rekordbox_tracks and not force_reload:
            return

        logger.info("Loading Rekordbox tracks...")
        self._rekordbox_tracks.clear()

        for track in tracks:
            ref = PlatformTrackRef(
                platform="rekordbox",
                platform_id=str(track.track_id),
                title=track.title or "",
                artist=track.artist or "",
                album=track.album or "",
                file_path=track.file_path,
                bpm=track.bpm,
                key=track.key,
                rating=track.rating,
                play_count=track.play_count,
                raw_data=track.__dict__ if hasattr(track, '__dict__') else None,
            )

            self._rekordbox_tracks[str(track.track_id)] = ref
            self._index_track("rekordbox", str(track.track_id), ref)

        logger.info(f"Loaded {len(self._rekordbox_tracks)} Rekordbox tracks")

    def load_djay_pro_tracks(
        self,
        tracks: List[Any],
        force_reload: bool = False
    ):
        """Load djay Pro tracks into cache.

        Args:
            tracks: List of DjayProTrack objects
            force_reload: Force reload even if cached
        """
        if self._djay_pro_tracks and not force_reload:
            return

        logger.info("Loading djay Pro tracks...")
        self._djay_pro_tracks.clear()

        for track in tracks:
            title_id = getattr(track, 'title_id', None) or getattr(track, 'titleID', '')
            ref = PlatformTrackRef(
                platform="djay_pro",
                platform_id=title_id,
                title=getattr(track, 'title', '') or "",
                artist=getattr(track, 'artist', '') or "",
                album=getattr(track, 'album', '') or "",
                file_path=getattr(track, 'file_path', None) or getattr(track, 'filePath', None),
                bpm=getattr(track, 'bpm', None),
                key=getattr(track, 'key', None),
                raw_data=track.__dict__ if hasattr(track, '__dict__') else None,
            )

            self._djay_pro_tracks[title_id] = ref
            self._index_track("djay_pro", title_id, ref)

        logger.info(f"Loaded {len(self._djay_pro_tracks)} djay Pro tracks")

    def _index_track(self, platform: str, platform_id: str, ref: PlatformTrackRef):
        """Add track to lookup indexes.

        Args:
            platform: Platform name
            platform_id: Platform-specific ID
            ref: Track reference
        """
        key = (platform, platform_id)

        # Path index
        if ref.file_path:
            path_key = ref.file_path.lower()
            if path_key not in self._path_index:
                self._path_index[path_key] = set()
            self._path_index[path_key].add(key)

            # Filename index
            filename = Path(ref.file_path).name.lower()
            if filename:
                if filename not in self._filename_index:
                    self._filename_index[filename] = set()
                self._filename_index[filename].add(key)

        # Title + Artist index
        if ref.title:
            ta_key = self._make_title_artist_key(ref.title, ref.artist)
            if ta_key not in self._title_artist_index:
                self._title_artist_index[ta_key] = set()
            self._title_artist_index[ta_key].add(key)

    def _make_title_artist_key(self, title: str, artist: str) -> str:
        """Create normalized key for title/artist matching."""
        title_norm = (title or "").lower().strip()
        artist_norm = (artist or "").lower().strip()
        return f"{title_norm}|{artist_norm}"

    def build_unified_index(self) -> List[UnifiedTrackMatch]:
        """Build unified track index from all loaded platforms.

        Creates unified track records by matching across platforms
        and resolving conflicts according to authority rules.

        Returns:
            List of UnifiedTrackMatch objects
        """
        logger.info("Building unified track index...")
        self._unified_tracks.clear()

        processed_refs: Set[Tuple[str, str]] = set()
        match_id = 0

        # Start with Notion as the authoritative source
        for notion_id, notion_ref in self._notion_tracks.items():
            if ("notion", notion_id) in processed_refs:
                continue

            # Find all matching tracks across platforms
            matches = self._find_all_matches(notion_ref)
            matches.add(("notion", notion_id))

            # Create unified record
            unified = self._create_unified_match(f"unified_{match_id}", matches)
            self._unified_tracks[unified.match_id] = unified

            # Mark all as processed
            processed_refs.update(matches)
            match_id += 1

        # Process remaining unmatched tracks from other platforms
        for platform, cache in [
            ("apple_music", self._apple_music_tracks),
            ("rekordbox", self._rekordbox_tracks),
            ("djay_pro", self._djay_pro_tracks),
        ]:
            for platform_id, ref in cache.items():
                if (platform, platform_id) in processed_refs:
                    continue

                matches = self._find_all_matches(ref)
                matches.add((platform, platform_id))

                unified = self._create_unified_match(f"unified_{match_id}", matches)
                self._unified_tracks[unified.match_id] = unified

                processed_refs.update(matches)
                match_id += 1

        logger.info(f"Built {len(self._unified_tracks)} unified track records")
        return list(self._unified_tracks.values())

    def _find_all_matches(self, ref: PlatformTrackRef) -> Set[Tuple[str, str]]:
        """Find all platform matches for a track reference.

        Args:
            ref: Source track reference

        Returns:
            Set of (platform, platform_id) tuples
        """
        matches: Set[Tuple[str, str]] = set()

        # Match by file path
        if ref.file_path:
            path_key = ref.file_path.lower()
            if path_key in self._path_index:
                matches.update(self._path_index[path_key])

            # Also try filename only
            filename = Path(ref.file_path).name.lower()
            if filename in self._filename_index:
                matches.update(self._filename_index[filename])

        # Match by title + artist (fuzzy)
        if ref.title:
            ta_key = self._make_title_artist_key(ref.title, ref.artist)

            # Exact match first
            if ta_key in self._title_artist_index:
                matches.update(self._title_artist_index[ta_key])

            # Fuzzy match
            for key, refs in self._title_artist_index.items():
                if abs(len(ta_key) - len(key)) > max(len(ta_key), len(key)) * 0.5:
                    continue
                score = SequenceMatcher(None, ta_key, key).ratio()
                if score >= self.fuzzy_threshold:
                    matches.update(refs)

        # Match by platform-specific IDs (from Notion cross-references)
        if ref.platform == "notion" and ref.raw_data:
            am_id = ref.raw_data.get("apple_music_id")
            if am_id and am_id in self._apple_music_tracks:
                matches.add(("apple_music", am_id))

            rb_id = ref.raw_data.get("rekordbox_id")
            if rb_id and str(int(rb_id)) in self._rekordbox_tracks:
                matches.add(("rekordbox", str(int(rb_id))))

            djay_id = ref.raw_data.get("djay_pro_id")
            if djay_id and djay_id in self._djay_pro_tracks:
                matches.add(("djay_pro", djay_id))

        return matches

    def _create_unified_match(
        self,
        match_id: str,
        refs: Set[Tuple[str, str]]
    ) -> UnifiedTrackMatch:
        """Create unified match from platform references.

        Args:
            match_id: Unique match identifier
            refs: Set of (platform, platform_id) tuples

        Returns:
            UnifiedTrackMatch with resolved values
        """
        unified = UnifiedTrackMatch(match_id=match_id)

        # Collect all platform references
        for platform, platform_id in refs:
            cache = self._get_platform_cache(platform)
            if cache and platform_id in cache:
                ref = cache[platform_id]
                unified.platforms.add(platform)
                unified.platform_refs[platform] = ref

                if platform == "notion":
                    unified.notion_page_id = platform_id

        # Resolve canonical values using authority ranking
        unified.canonical_title = self._resolve_field("title", unified.platform_refs)
        unified.canonical_artist = self._resolve_field("artist", unified.platform_refs)
        unified.canonical_album = self._resolve_field("album", unified.platform_refs)
        unified.canonical_bpm = self._resolve_field("bpm", unified.platform_refs)
        unified.canonical_key = self._resolve_field("key", unified.platform_refs)

        # Use any available file path
        for ref in unified.platform_refs.values():
            if ref.file_path:
                unified.file_path = ref.file_path
                break

        # Detect conflicts
        unified.conflicts = self._detect_conflicts(unified.platform_refs)
        unified.has_conflicts = len(unified.conflicts) > 0

        # Calculate confidence score
        unified.confidence_score = self._calculate_confidence(unified)

        return unified

    def _get_platform_cache(self, platform: str) -> Optional[Dict]:
        """Get cache for a specific platform."""
        return {
            "notion": self._notion_tracks,
            "apple_music": self._apple_music_tracks,
            "rekordbox": self._rekordbox_tracks,
            "djay_pro": self._djay_pro_tracks,
        }.get(platform)

    def _resolve_field(
        self,
        field_name: str,
        refs: Dict[str, PlatformTrackRef]
    ) -> Optional[Any]:
        """Resolve canonical value for a field using authority ranking.

        Args:
            field_name: Field to resolve
            refs: Platform references

        Returns:
            Canonical value from highest-authority source
        """
        authority_order = self.AUTHORITY_RANKING.get(field_name, [])

        for platform in authority_order:
            if platform in refs:
                ref = refs[platform]
                value = getattr(ref, field_name, None)
                if value is not None and value != "" and value != 0:
                    return value

        # Fallback: return any non-empty value
        for ref in refs.values():
            value = getattr(ref, field_name, None)
            if value is not None and value != "" and value != 0:
                return value

        return None

    def _detect_conflicts(
        self,
        refs: Dict[str, PlatformTrackRef]
    ) -> List[Dict]:
        """Detect conflicting values across platforms.

        Args:
            refs: Platform references

        Returns:
            List of conflict dictionaries
        """
        conflicts = []

        # Check BPM conflicts (significant difference)
        bpm_values = {}
        for platform, ref in refs.items():
            if ref.bpm and ref.bpm > 0:
                bpm_values[platform] = ref.bpm

        if len(bpm_values) > 1:
            bpm_list = list(bpm_values.values())
            max_diff = max(bpm_list) - min(bpm_list)
            if max_diff > 1.0:  # More than 1 BPM difference
                conflicts.append({
                    "field": "bpm",
                    "values": bpm_values,
                    "max_difference": max_diff,
                })

        # Check key conflicts
        key_values = {}
        for platform, ref in refs.items():
            if ref.key:
                key_values[platform] = ref.key

        if len(set(key_values.values())) > 1:
            conflicts.append({
                "field": "key",
                "values": key_values,
            })

        return conflicts

    def _calculate_confidence(self, unified: UnifiedTrackMatch) -> float:
        """Calculate match confidence score.

        Args:
            unified: Unified track match

        Returns:
            Confidence score (0.0 to 1.0)
        """
        score = 0.0

        # More platforms = higher confidence
        platform_count = len(unified.platforms)
        score += min(platform_count * 0.2, 0.6)

        # File path match = high confidence
        if unified.file_path:
            path_matches = sum(
                1 for ref in unified.platform_refs.values()
                if ref.file_path and ref.file_path.lower() == unified.file_path.lower()
            )
            if path_matches > 1:
                score += 0.3

        # No conflicts = higher confidence
        if not unified.has_conflicts:
            score += 0.1

        return min(score, 1.0)

    def get_statistics(self) -> Dict[str, Any]:
        """Get cross-platform matching statistics.

        Returns:
            Dictionary with statistics
        """
        all_platforms = 0
        multi_platform = 0
        single_platform = 0
        with_conflicts = 0

        platform_coverage = {
            "notion": 0,
            "apple_music": 0,
            "rekordbox": 0,
            "djay_pro": 0,
        }

        for unified in self._unified_tracks.values():
            platform_count = len(unified.platforms)

            if platform_count == 4:
                all_platforms += 1
            elif platform_count > 1:
                multi_platform += 1
            else:
                single_platform += 1

            if unified.has_conflicts:
                with_conflicts += 1

            for platform in unified.platforms:
                platform_coverage[platform] += 1

        return {
            "total_unified_tracks": len(self._unified_tracks),
            "all_platforms": all_platforms,
            "multi_platform": multi_platform,
            "single_platform": single_platform,
            "with_conflicts": with_conflicts,
            "platform_coverage": platform_coverage,
            "indexes": {
                "path_index": len(self._path_index),
                "filename_index": len(self._filename_index),
                "title_artist_index": len(self._title_artist_index),
            }
        }

    # Property extraction helpers

    def _get_title(self, props: Dict) -> Optional[str]:
        """Extract title from Notion properties."""
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
