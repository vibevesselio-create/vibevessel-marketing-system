"""Track matching for djay Pro exports against Notion Tracks."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, List

from music_workflow.integrations.djay_pro.models import DjayTrack, DjayStreamingTrack
from music_workflow.integrations.notion.tracks_db import TracksDatabase
from music_workflow.utils.errors import NotionIntegrationError


@dataclass
class DjayTrackMatch:
    """Represents a matched Notion track for a djay Pro item."""
    notion_page_id: str
    match_type: str
    similarity_score: float
    title: Optional[str] = None
    artist: Optional[str] = None


class DjayTrackMatcher:
    """Match djay Pro tracks to Notion Music Tracks."""

    def __init__(
        self,
        tracks_db: Optional[TracksDatabase] = None,
        similarity_threshold: float = 0.85,
    ) -> None:
        self.tracks_db = tracks_db or TracksDatabase()
        self.similarity_threshold = similarity_threshold

    def find_match(
        self,
        track: DjayTrack,
        streaming: Optional[DjayStreamingTrack] = None,
    ) -> Optional[DjayTrackMatch]:
        """Find the best Notion match for a djay Pro track."""
        if track.track_id:
            match = self._match_by_rich_text("djay Pro ID", track.track_id, "djay_id")
            if match:
                return match

        source_type = (track.source_type or "").lower()
        if source_type == "spotify" and track.source_id:
            match = self._match_by_rich_text("Spotify ID", track.source_id, "spotify_id")
            if match:
                return match

        if source_type == "soundcloud":
            if streaming and streaming.source_url:
                match = self._match_by_url("SoundCloud URL", streaming.source_url, "soundcloud_url")
                if match:
                    return match
            # Try matching by SoundCloud ID (number property) if available
            if track.source_id and track.source_id.isdigit():
                match = self._match_by_number("SoundCloud ID", int(track.source_id), "soundcloud_id")
                if match:
                    return match

        # Note: "Source ID" property doesn't exist in Tracks DB - removed lookups
        # Fallback: try matching by URL property if we have a source URL
        if streaming and streaming.source_url:
            match = self._match_by_url("URL", streaming.source_url, "source_url")
            if match:
                return match
            # Note: "Source URL" property doesn't exist - only "URL" exists

        return self._match_by_metadata(track)

    def _match_by_rich_text(self, prop: str, value: str, match_type: str) -> Optional[DjayTrackMatch]:
        filter_dict = {"property": prop, "rich_text": {"equals": value}}
        pages = self._query_pages(filter_dict)
        return self._first_match(pages, match_type, 1.0)

    def _match_by_url(self, prop: str, value: str, match_type: str) -> Optional[DjayTrackMatch]:
        filter_dict = {"property": prop, "url": {"equals": value}}
        pages = self._query_pages(filter_dict)
        return self._first_match(pages, match_type, 1.0)

    def _match_by_number(self, prop: str, value: int, match_type: str) -> Optional[DjayTrackMatch]:
        filter_dict = {"property": prop, "number": {"equals": value}}
        pages = self._query_pages(filter_dict)
        return self._first_match(pages, match_type, 1.0)

    def _match_by_metadata(self, track: DjayTrack) -> Optional[DjayTrackMatch]:
        if not track.title:
            return None

        pages = self._query_title_candidates(track.title)
        best_match = None
        best_score = 0.0

        for page in pages:
            candidate = self.tracks_db._page_to_track(page)
            score = self._metadata_similarity(
                track.title,
                track.artist,
                candidate.title,
                candidate.artist,
            )
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match and best_score >= self.similarity_threshold:
            return DjayTrackMatch(
                notion_page_id=best_match.notion_page_id or best_match.id,
                match_type="fuzzy",
                similarity_score=best_score,
                title=best_match.title,
                artist=best_match.artist,
            )

        return None

    def _query_title_candidates(self, title: str) -> List[dict]:
        title_value = title.strip()
        if len(title_value) > 50:
            title_value = title_value[:50]

        pages = []
        # Only query "Title" - "Name" property doesn't exist in the Tracks database
        filter_dict = {"property": "Title", "title": {"contains": title_value}}
        pages.extend(self._query_pages(filter_dict))
        return pages

    def _query_pages(self, filter_dict: dict) -> List[dict]:
        try:
            return self.tracks_db.client.query_database(
                self.tracks_db.database_id,
                filter=filter_dict,
                page_size=10,
            )
        except NotionIntegrationError:
            return []

    def _first_match(
        self,
        pages: List[dict],
        match_type: str,
        score: float,
    ) -> Optional[DjayTrackMatch]:
        if not pages:
            return None
        page = pages[0]
        candidate = self.tracks_db._page_to_track(page)
        return DjayTrackMatch(
            notion_page_id=candidate.notion_page_id or candidate.id,
            match_type=match_type,
            similarity_score=score,
            title=candidate.title,
            artist=candidate.artist,
        )

    def _metadata_similarity(
        self,
        title_a: str,
        artist_a: str,
        title_b: str,
        artist_b: str,
    ) -> float:
        title_score = self._string_similarity(title_a, title_b)
        if not artist_a or not artist_b:
            return title_score
        artist_score = self._string_similarity(artist_a, artist_b)
        return (title_score * 0.6) + (artist_score * 0.4)

    def _string_similarity(self, a: str, b: str) -> float:
        a_norm = self._normalize_text(a)
        b_norm = self._normalize_text(b)
        if not a_norm or not b_norm:
            return 0.0
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    def _normalize_text(self, value: str) -> str:
        return "".join(
            ch for ch in value.lower() if ch.isalnum() or ch.isspace()
        ).strip()
