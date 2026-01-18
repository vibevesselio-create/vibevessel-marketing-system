"""
Notion database deduplication for music workflow.

This module provides deduplication checks against the Notion tracks database,
identifying duplicate tracks based on fingerprint, URL, Spotify ID, and metadata matching.

INTEGRATION POINTS:
- process_tracks_from_notion.py: Pre-processing duplicate check
- process_track_workflow.py: Single track duplicate check
- run_fingerprint_dedup_production.py: Eagle-first mode duplicate check

Version: 2026-01-17 - Added fingerprint-based dedup, page merge, and archive capabilities
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Union
import re
import logging

# Try to import from music_workflow, fall back to basic types
try:
    from music_workflow.core.models import TrackInfo, DeduplicationResult
    from music_workflow.utils.errors import DuplicateFoundError
    from music_workflow.utils.logging import MusicWorkflowLogger
    logger = MusicWorkflowLogger("notion-dedup")
except ImportError:
    # Fallback for standalone usage
    logger = logging.getLogger("notion-dedup")

    @dataclass
    class DeduplicationResult:
        """Fallback deduplication result."""
        is_duplicate: bool = False
        matching_track_id: Optional[str] = None
        matching_source: Optional[str] = None
        similarity_score: float = 0.0
        metadata_match: bool = False
        all_matches: List[Dict] = field(default_factory=list)

    class TrackInfo:
        """Fallback track info stub."""
        pass


@dataclass
class NotionMatch:
    """A potential match from Notion database."""
    page_id: str
    title: str
    artist: str
    similarity_score: float
    match_type: str  # fingerprint, exact, fuzzy_title, fuzzy_artist, url_match, spotify_id
    has_file_paths: bool = False
    has_fingerprints: bool = False
    is_downloaded: bool = False
    completeness_score: float = 0.0  # 0-1 score for how complete the page is


class NotionDeduplicator:
    """Deduplication checker for Notion database.

    Checks for duplicate tracks in the Notion tracks database
    using fingerprint, URL, Spotify ID, and metadata matching strategies.

    This class supports BOTH:
    - TrackInfo objects (from music_workflow.core.models)
    - Raw Notion page dictionaries (from API queries)
    """

    # Fingerprint property names for each format
    FINGERPRINT_PROPERTIES = {
        "aiff": "AIFF Fingerprint",
        "wav": "WAV Fingerprint",
        "m4a": "M4A Fingerprint",
    }

    # File path property names for each format
    FILE_PATH_PROPERTIES = {
        "aiff": "AIFF File Path",
        "wav": "WAV File Path",
        "m4a": "M4A File Path",
    }

    def __init__(
        self,
        notion_client=None,
        tracks_db_id: Optional[str] = None,
        similarity_threshold: float = 0.85,
    ):
        """Initialize the deduplicator.

        Args:
            notion_client: Notion API client instance
            tracks_db_id: ID of the tracks database
            similarity_threshold: Minimum similarity for fuzzy matches
        """
        self.notion_client = notion_client
        self.tracks_db_id = tracks_db_id
        self.similarity_threshold = similarity_threshold
        self._property_types_cache: Optional[Dict[str, str]] = None
        self._property_types_cache_initialized = False

    def check_duplicate(self, track: Union[TrackInfo, Dict[str, Any]], exclude_page_id: Optional[str] = None) -> DeduplicationResult:
        """Check if a track already exists in Notion.

        Args:
            track: Track to check (TrackInfo object or raw Notion page dict)
            exclude_page_id: Page ID to exclude from results (typically the current track's page)

        Returns:
            DeduplicationResult with match information
        """
        # #region agent log
        import json
        import time
        debug_log_path = "/Users/brianhellemn/Projects/github-production/.cursor/debug.log"
        try:
            with open(debug_log_path, 'a') as f:
                f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_check_dup_start", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:check_duplicate", "message": "Duplicate check started", "data": {"has_track": bool(track), "exclude_page_id": exclude_page_id[:8] if exclude_page_id else None}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
        except Exception:
            pass
        # #endregion agent log

        if not self.notion_client or not self.tracks_db_id:
            logger.warning("Notion client or database ID not configured")
            return DeduplicationResult(is_duplicate=False)

        # Extract track properties (handle both TrackInfo and raw dict)
        track_props = self._extract_track_properties(track)
        current_page_id = track_props.get("page_id")

        # If no exclude_page_id provided, use current track's page_id
        if exclude_page_id is None:
            exclude_page_id = current_page_id

        matches = []

        # Strategy 1: Check by fingerprint (MOST reliable - exact content match)
        fingerprints = track_props.get("fingerprints", {})
        for fmt, fp in fingerprints.items():
            if fp and fp not in ("FILE_MISSING", ""):
                fp_matches = self._check_by_fingerprint(fp, fmt, exclude_page_id)
                matches.extend(fp_matches)

        # Strategy 2: Check by URL (very reliable - exact source match)
        source_url = track_props.get("source_url")
        if source_url:
            url_matches = self._check_by_url(source_url, exclude_page_id)
            matches.extend(url_matches)

        soundcloud_url = track_props.get("soundcloud_url")
        if soundcloud_url:
            url_matches = self._check_by_url(soundcloud_url, exclude_page_id)
            matches.extend(url_matches)

        # Strategy 3: Check by Spotify ID (reliable - unique identifier)
        spotify_id = track_props.get("spotify_id")
        if spotify_id:
            spotify_matches = self._check_by_spotify_id(spotify_id, exclude_page_id)
            matches.extend(spotify_matches)

        # Strategy 4: Check by title and artist (fuzzy - metadata match)
        title = track_props.get("title")
        artist = track_props.get("artist")
        if title and artist:
            metadata_matches = self._check_by_metadata(title, artist, exclude_page_id)
            matches.extend(metadata_matches)

        # Deduplicate matches by page_id (same page may match multiple strategies)
        unique_matches = {}
        for match in matches:
            if match.page_id not in unique_matches:
                unique_matches[match.page_id] = match
            else:
                # Keep the match with higher score
                if match.similarity_score > unique_matches[match.page_id].similarity_score:
                    unique_matches[match.page_id] = match

        matches = list(unique_matches.values())

        # #region agent log
        try:
            with open(debug_log_path, 'a') as f:
                f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_check_dup_result", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:check_duplicate", "message": "Duplicate check completed", "data": {"matches_count": len(matches), "has_fingerprints": bool(fingerprints), "has_source_url": bool(source_url), "has_soundcloud_url": bool(soundcloud_url), "has_spotify_id": bool(spotify_id), "has_title_artist": bool(title and artist)}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
        except Exception:
            pass
        # #endregion agent log

        # Return best match
        if matches:
            best_match = max(matches, key=lambda m: m.similarity_score)

            if best_match.similarity_score >= self.similarity_threshold:
                logger.info(
                    f"🔍 NOTION DEDUP: Duplicate found for '{track_props.get('title', 'Unknown')}' "
                    f"→ matches '{best_match.title}' (page: {best_match.page_id[:8]}..., "
                    f"score: {best_match.similarity_score:.2f}, type: {best_match.match_type})"
                )
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_track_id=best_match.page_id,
                    matching_source="notion",
                    similarity_score=best_match.similarity_score,
                    metadata_match=best_match.match_type in ["exact", "fuzzy_title", "fuzzy_artist", "fingerprint"],
                    all_matches=[{
                        "page_id": m.page_id,
                        "title": m.title,
                        "artist": m.artist,
                        "score": m.similarity_score,
                        "match_type": m.match_type,
                        "completeness": m.completeness_score
                    } for m in matches]
                )

        logger.debug(f"🔍 NOTION DEDUP: No duplicates found for '{track_props.get('title', 'Unknown')}'")
        return DeduplicationResult(is_duplicate=False)

    def _extract_track_properties(self, track: Union[TrackInfo, Dict[str, Any]]) -> Dict[str, Any]:
        """Extract standardized properties from either TrackInfo or raw Notion dict."""
        if isinstance(track, dict):
            # Raw Notion page dictionary
            props = track.get("properties", {})
            page_id = track.get("id")

            # Extract fingerprints
            fingerprints = {}
            for fmt, prop_name in self.FINGERPRINT_PROPERTIES.items():
                fp_val = self._get_rich_text(props, prop_name)
                if fp_val:
                    fingerprints[fmt] = fp_val

            # Extract file paths
            file_paths = {}
            for fmt, prop_name in self.FILE_PATH_PROPERTIES.items():
                path_val = self._get_rich_text(props, prop_name) or self._get_url(props, prop_name)
                if path_val:
                    file_paths[fmt] = path_val

            return {
                "page_id": page_id,
                "title": self._get_title_from_props(props),
                "artist": self._get_rich_text(props, "Artist"),
                "source_url": self._get_url(props, "Source URL"),
                "soundcloud_url": self._get_url(props, "SoundCloud URL"),
                "spotify_id": self._get_rich_text(props, "Spotify ID"),
                "fingerprints": fingerprints,
                "file_paths": file_paths,
                "is_downloaded": self._get_checkbox(props, "DL"),
            }
        else:
            # TrackInfo object
            return {
                "page_id": getattr(track, "notion_page_id", None),
                "title": getattr(track, "title", None),
                "artist": getattr(track, "artist", None),
                "source_url": getattr(track, "source_url", None),
                "soundcloud_url": getattr(track, "soundcloud_url", None),
                "spotify_id": getattr(track, "spotify_id", None),
                "fingerprints": {"default": getattr(track, "fingerprint", None)} if hasattr(track, "fingerprint") else {},
                "file_paths": {},
                "is_downloaded": False,
            }

    def _check_by_fingerprint(self, fingerprint: str, format_type: str, exclude_page_id: Optional[str] = None) -> List[NotionMatch]:
        """Check for duplicates by fingerprint (MOST RELIABLE - exact content match)."""
        matches = []

        try:
            prop_name = self.FINGERPRINT_PROPERTIES.get(format_type, "AIFF Fingerprint")
            
            # Check if property exists before querying
            prop_types = self._get_property_types()
            if prop_name not in prop_types:
                logger.debug(f"Fingerprint property '{prop_name}' not found in database schema - skipping fingerprint check")
                return matches

            results = self.notion_client.databases.query(
                database_id=self.tracks_db_id,
                filter={
                    "property": prop_name,
                    "rich_text": {"equals": fingerprint},
                },
                page_size=10,
            )

            for page in results.get("results", []):
                page_id = page.get("id")
                if exclude_page_id and page_id == exclude_page_id:
                    continue

                props = page.get("properties", {})
                completeness = self._calculate_page_completeness(props)

                matches.append(NotionMatch(
                    page_id=page_id,
                    title=self._get_title_from_props(props),
                    artist=self._get_rich_text(props, "Artist"),
                    similarity_score=1.0,  # Fingerprint match = exact match
                    match_type="fingerprint",
                    has_file_paths=completeness.get("has_file_paths", False),
                    has_fingerprints=True,
                    is_downloaded=self._get_checkbox(props, "DL"),
                    completeness_score=completeness.get("score", 0.0),
                ))

            if matches:
                logger.info(f"🔍 NOTION DEDUP: Found {len(matches)} fingerprint match(es) for {format_type.upper()}")

        except Exception as e:
            logger.warning(f"Fingerprint check failed: {e}")

        return matches

    def _get_property_types(self) -> Dict[str, str]:
        """Get property types from database schema (cached)."""
        # #region agent log
        import json
        import time
        debug_log_path = "/Users/brianhellemn/Projects/github-production/.cursor/debug.log"
        cache_hit = self._property_types_cache_initialized and self._property_types_cache is not None
        try:
            with open(debug_log_path, 'a') as f:
                f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_prop_types", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_get_property_types", "message": "Property types lookup", "data": {"cache_hit": cache_hit, "cache_initialized": self._property_types_cache_initialized}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
        except Exception:
            pass
        # #endregion agent log

        if self._property_types_cache_initialized and self._property_types_cache is not None:
            return self._property_types_cache

        if not self.notion_client or not self.tracks_db_id:
            return {}

        try:
            db_meta = self.notion_client.databases.retrieve(database_id=self.tracks_db_id)
            props = db_meta.get("properties", {})
            self._property_types_cache = {name: info.get("type") for name, info in props.items()}
            self._property_types_cache_initialized = True

            # #region agent log
            try:
                url_props = [k for k, v in self._property_types_cache.items() if v == "url"]
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_prop_types_cached", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_get_property_types", "message": "Property types cached", "data": {"total_props": len(self._property_types_cache), "url_props": url_props, "has_source_url": "Source URL" in self._property_types_cache, "has_soundcloud_url": "SoundCloud URL" in self._property_types_cache, "has_youtube_url": "YouTube URL" in self._property_types_cache}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log

            return self._property_types_cache
        except Exception as e:
            # #region agent log
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_prop_types_error", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_get_property_types", "message": "Property types fetch error", "data": {"error": str(e)[:200]}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log
            logger.warning(f"Could not fetch property types: {e}")
            self._property_types_cache = {}
            self._property_types_cache_initialized = True
            return {}

    def _check_by_url(self, url: str, exclude_page_id: Optional[str] = None) -> List[NotionMatch]:
        """Check for duplicates by source URL."""
        matches = []

        try:
            # #region agent log
            import json
            import time
            debug_log_path = "/Users/brianhellemn/Projects/github-production/.cursor/debug.log"
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_url_check", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_check_by_url", "message": "URL check started", "data": {"has_url": bool(url), "url_length": len(url) if url else 0, "exclude_page_id": exclude_page_id[:8] if exclude_page_id else None}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log

            # Normalize URL for comparison
            normalized_url = self._normalize_url(url)

            # Get property types to check which URL properties exist
            prop_types = self._get_property_types()
            
            # Build filter conditions only for properties that exist
            url_filter_conditions = []
            url_properties = [
                ("Source URL", url),
                ("Source URL", normalized_url),
                ("SoundCloud URL", url),
                ("SoundCloud URL", normalized_url),
                ("YouTube URL", url),
            ]
            
            for prop_name, prop_url in url_properties:
                # Only add filter if property exists and is a URL type
                if prop_name in prop_types and prop_types[prop_name] == "url":
                    url_filter_conditions.append({
                        "property": prop_name,
                        "url": {"equals": prop_url}
                    })

            # #region agent log
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_url_filter", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_check_by_url", "message": "URL filter built", "data": {"filter_count": len(url_filter_conditions), "has_source_url": "Source URL" in prop_types, "has_soundcloud_url": "SoundCloud URL" in prop_types, "has_youtube_url": "YouTube URL" in prop_types}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log

            # If no URL properties exist, skip query
            if not url_filter_conditions:
                logger.debug("No URL properties found in database schema - skipping URL check")
                return matches

            # Query Notion for matching URLs
            results = self.notion_client.databases.query(
                database_id=self.tracks_db_id,
                filter={
                    "or": url_filter_conditions
                } if len(url_filter_conditions) > 1 else url_filter_conditions[0],
                page_size=10,
            )

            result_count = len(results.get("results", []))
            # #region agent log
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_url_results", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_check_by_url", "message": "URL query completed", "data": {"results_count": result_count, "filter_conditions": len(url_filter_conditions)}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log

            for page in results.get("results", []):
                page_id = page.get("id")
                if exclude_page_id and page_id == exclude_page_id:
                    continue

                props = page.get("properties", {})
                completeness = self._calculate_page_completeness(props)

                matches.append(NotionMatch(
                    page_id=page_id,
                    title=self._get_title_from_props(props),
                    artist=self._get_rich_text(props, "Artist"),
                    similarity_score=1.0,
                    match_type="url_match",
                    has_file_paths=completeness.get("has_file_paths", False),
                    has_fingerprints=completeness.get("has_fingerprints", False),
                    is_downloaded=self._get_checkbox(props, "DL"),
                    completeness_score=completeness.get("score", 0.0),
                ))

        except Exception as e:
            # #region agent log
            try:
                with open(debug_log_path, 'a') as f:
                    f.write(json.dumps({"id": f"log_{int(time.time() * 1000)}_url_error", "timestamp": int(time.time() * 1000), "location": "notion_dedup.py:_check_by_url", "message": "URL check error", "data": {"error": str(e)[:300], "error_type": type(e).__name__}, "sessionId": "production-test", "runId": "prod", "hypothesisId": "monitor"}) + "\n")
            except Exception:
                pass
            # #endregion agent log
            logger.warning(f"URL check failed: {e}")

        return matches

    def _check_by_spotify_id(self, spotify_id: str, exclude_page_id: Optional[str] = None) -> List[NotionMatch]:
        """Check for duplicates by Spotify ID."""
        matches = []

        try:
            # Check if property exists before querying
            prop_types = self._get_property_types()
            if "Spotify ID" not in prop_types:
                logger.debug("Spotify ID property not found in database schema - skipping Spotify ID check")
                return matches

            results = self.notion_client.databases.query(
                database_id=self.tracks_db_id,
                filter={
                    "property": "Spotify ID",
                    "rich_text": {"equals": spotify_id},
                },
                page_size=10,
            )

            for page in results.get("results", []):
                page_id = page.get("id")
                if exclude_page_id and page_id == exclude_page_id:
                    continue

                props = page.get("properties", {})
                completeness = self._calculate_page_completeness(props)

                matches.append(NotionMatch(
                    page_id=page_id,
                    title=self._get_title_from_props(props),
                    artist=self._get_rich_text(props, "Artist"),
                    similarity_score=1.0,
                    match_type="spotify_id",
                    has_file_paths=completeness.get("has_file_paths", False),
                    has_fingerprints=completeness.get("has_fingerprints", False),
                    is_downloaded=self._get_checkbox(props, "DL"),
                    completeness_score=completeness.get("score", 0.0),
                ))

        except Exception as e:
            logger.warning(f"Spotify ID check failed: {e}")

        return matches

    def _check_by_metadata(self, title: str, artist: str, exclude_page_id: Optional[str] = None) -> List[NotionMatch]:
        """Check for duplicates by title and artist fuzzy matching."""
        matches = []

        try:
            # Check if Title property exists before querying
            prop_types = self._get_property_types()
            if "Title" not in prop_types:
                logger.debug("Title property not found in database schema - skipping metadata check")
                return matches

            # Search by title
            results = self.notion_client.databases.query(
                database_id=self.tracks_db_id,
                filter={
                    "property": "Title",
                    "title": {"contains": self._normalize_title(title)[:50]},
                },
                page_size=20,
            )

            for page in results.get("results", []):
                page_id = page.get("id")
                if exclude_page_id and page_id == exclude_page_id:
                    continue

                props = page.get("properties", {})
                db_title = self._get_title_from_props(props)
                db_artist = self._get_rich_text(props, "Artist")

                # Calculate similarity
                title_sim = self._calculate_similarity(title, db_title)
                artist_sim = self._calculate_similarity(artist, db_artist)
                combined_score = (title_sim * 0.6) + (artist_sim * 0.4)

                if combined_score >= self.similarity_threshold:
                    match_type = "exact" if combined_score >= 0.95 else "fuzzy_title"
                    completeness = self._calculate_page_completeness(props)

                    matches.append(NotionMatch(
                        page_id=page_id,
                        title=db_title,
                        artist=db_artist,
                        similarity_score=combined_score,
                        match_type=match_type,
                        has_file_paths=completeness.get("has_file_paths", False),
                        has_fingerprints=completeness.get("has_fingerprints", False),
                        is_downloaded=self._get_checkbox(props, "DL"),
                        completeness_score=completeness.get("score", 0.0),
                    ))

        except Exception as e:
            logger.warning(f"Metadata check failed: {e}")

        return matches

    def _calculate_page_completeness(self, props: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate how complete a Notion page is (for selecting canonical page)."""
        score = 0.0
        has_file_paths = False
        has_fingerprints = False

        # Check file paths (weight: 0.3)
        for fmt, prop_name in self.FILE_PATH_PROPERTIES.items():
            path_val = self._get_rich_text(props, prop_name) or self._get_url(props, prop_name)
            if path_val and path_val not in ("FILE_MISSING", ""):
                has_file_paths = True
                score += 0.1

        # Check fingerprints (weight: 0.3)
        for fmt, prop_name in self.FINGERPRINT_PROPERTIES.items():
            fp_val = self._get_rich_text(props, prop_name)
            if fp_val and fp_val not in ("FILE_MISSING", ""):
                has_fingerprints = True
                score += 0.1

        # Check DL checkbox (weight: 0.2)
        if self._get_checkbox(props, "DL"):
            score += 0.2

        # Check for artist (weight: 0.1)
        if self._get_rich_text(props, "Artist"):
            score += 0.1

        # Check for Spotify ID (weight: 0.1)
        if self._get_rich_text(props, "Spotify ID"):
            score += 0.1

        return {
            "score": min(score, 1.0),
            "has_file_paths": has_file_paths,
            "has_fingerprints": has_fingerprints,
        }

    def _get_url(self, props: Dict[str, Any], prop_name: str) -> Optional[str]:
        """Extract URL from Notion properties."""
        prop = props.get(prop_name)
        if not prop:
            return None
        if prop.get("type") == "url":
            return prop.get("url")
        return None

    def _get_checkbox(self, props: Dict[str, Any], prop_name: str) -> bool:
        """Extract checkbox value from Notion properties."""
        prop = props.get(prop_name, {})
        if prop.get("type") == "checkbox":
            return prop.get("checkbox", False)
        return False

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for comparison."""
        url = url.lower().strip()
        # Remove tracking parameters
        url = re.sub(r'\?.*$', '', url)
        # Remove trailing slashes
        url = url.rstrip('/')
        return url

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        title = title.lower().strip()
        # Remove common suffixes like (Official Video), [Remix], etc.
        title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title)
        # Remove extra whitespace
        title = ' '.join(title.split())
        return title

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity between two strings using Levenshtein-like approach."""
        if not s1 or not s2:
            return 0.0

        s1 = self._normalize_title(s1)
        s2 = self._normalize_title(s2)

        if s1 == s2:
            return 1.0

        # Simple character-based similarity
        set1 = set(s1.lower())
        set2 = set(s2.lower())

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        if union == 0:
            return 0.0

        jaccard = intersection / union

        # Also check for substring match
        if s1 in s2 or s2 in s1:
            jaccard = max(jaccard, 0.8)

        return jaccard

    def _get_title_from_props(self, props: Dict[str, Any]) -> str:
        """Extract title from Notion properties."""
        title_prop = props.get("Title", {})
        title_items = title_prop.get("title", [])
        return "".join(t.get("plain_text", "") for t in title_items)

    def _get_rich_text(self, props: Dict[str, Any], prop_name: str) -> str:
        """Extract rich text from Notion properties."""
        prop = props.get(prop_name, {})
        items = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in items)


def check_notion_duplicate(
    track: Union[TrackInfo, Dict[str, Any]],
    notion_client=None,
    tracks_db_id: Optional[str] = None,
    exclude_page_id: Optional[str] = None,
) -> DeduplicationResult:
    """Convenience function to check for Notion duplicates.

    Args:
        track: Track to check (TrackInfo object or raw Notion page dict)
        notion_client: Notion API client
        tracks_db_id: Tracks database ID
        exclude_page_id: Page ID to exclude from results (typically the current track)

    Returns:
        DeduplicationResult
    """
    deduplicator = NotionDeduplicator(
        notion_client=notion_client,
        tracks_db_id=tracks_db_id,
    )
    return deduplicator.check_duplicate(track, exclude_page_id=exclude_page_id)


def check_notion_duplicate_for_batch(
    tracks: List[Dict[str, Any]],
    notion_client=None,
    tracks_db_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Check a batch of tracks for duplicates in Notion.

    This function is optimized for batch processing and returns
    statistics about duplicates found in the batch.

    Args:
        tracks: List of Notion track page dictionaries
        notion_client: Notion API client
        tracks_db_id: Tracks database ID

    Returns:
        Dict with:
            - duplicates_found: List of track IDs that have duplicates
            - canonical_pages: Dict mapping track ID to canonical page ID
            - duplicate_groups: List of duplicate groups (list of page IDs)
            - stats: Statistics about the dedup check
    """
    deduplicator = NotionDeduplicator(
        notion_client=notion_client,
        tracks_db_id=tracks_db_id,
    )

    result = {
        "duplicates_found": [],
        "canonical_pages": {},
        "duplicate_groups": [],
        "stats": {
            "total_checked": 0,
            "duplicates_found": 0,
            "unique_tracks": 0,
            "by_match_type": {},
        }
    }

    # Track which pages we've already seen (for intra-batch dedup)
    seen_pages = set()
    duplicate_map = {}  # Maps fingerprint/URL/SpotifyID to list of page IDs

    for track in tracks:
        track_id = track.get("id")
        result["stats"]["total_checked"] += 1

        # Check for duplicate in Notion (excluding self)
        dedup_result = deduplicator.check_duplicate(track, exclude_page_id=track_id)

        if dedup_result.is_duplicate:
            result["duplicates_found"].append(track_id)
            result["stats"]["duplicates_found"] += 1

            # Track match type
            if hasattr(dedup_result, 'all_matches') and dedup_result.all_matches:
                match_type = dedup_result.all_matches[0].get("match_type", "unknown")
                result["stats"]["by_match_type"][match_type] = result["stats"]["by_match_type"].get(match_type, 0) + 1

            # Determine canonical page (highest completeness score)
            canonical_id = dedup_result.matching_track_id
            if hasattr(dedup_result, 'all_matches') and dedup_result.all_matches:
                # Sort by completeness score and pick best
                best_match = max(dedup_result.all_matches, key=lambda m: m.get("completeness", 0))
                canonical_id = best_match.get("page_id", dedup_result.matching_track_id)

            result["canonical_pages"][track_id] = canonical_id

            # Build duplicate groups
            group_key = canonical_id
            if group_key not in duplicate_map:
                duplicate_map[group_key] = [canonical_id]
            if track_id not in duplicate_map[group_key]:
                duplicate_map[group_key].append(track_id)
        else:
            result["stats"]["unique_tracks"] += 1

        seen_pages.add(track_id)

    # Convert duplicate_map to groups
    result["duplicate_groups"] = [
        group for group in duplicate_map.values() if len(group) > 1
    ]

    return result


# Logging helper for integration points
def log_notion_dedup_check(track_title: str, result: DeduplicationResult) -> None:
    """Log the result of a Notion dedup check for audit trail."""
    if result.is_duplicate:
        logger.info(
            f"🔍 NOTION DEDUP: '{track_title}' "
            f"→ DUPLICATE FOUND (page: {result.matching_track_id[:8]}..., "
            f"score: {result.similarity_score:.2f})"
        )
    else:
        logger.debug(f"🔍 NOTION DEDUP: '{track_title}' → No duplicates found")
