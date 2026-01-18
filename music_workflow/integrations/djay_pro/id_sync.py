"""Sync djay Pro IDs to Notion."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path

from music_workflow.integrations.djay_pro.export_loader import load_djay_export
from music_workflow.integrations.djay_pro.models import DjayExport
from music_workflow.integrations.djay_pro.matcher import DjayTrackMatcher
from music_workflow.integrations.notion.client import get_notion_client
from music_workflow.integrations.notion.tracks_db import TracksDatabase

logger = logging.getLogger(__name__)

@dataclass
class SyncStats:
    total_tracks: int = 0
    already_synced: int = 0
    newly_matched: int = 0
    updated: int = 0
    unmatched: int = 0
    errors: int = 0

class DjayProIdSync:
    def __init__(self, tracks_db=None, client=None, similarity_threshold=0.85, dry_run=False):
        self.tracks_db = tracks_db or TracksDatabase()
        self.client = client or get_notion_client()
        self.similarity_threshold = similarity_threshold
        self.dry_run = dry_run
        self._matcher = DjayTrackMatcher(tracks_db=self.tracks_db, similarity_threshold=similarity_threshold)

    def sync_from_export(self, export_dir: Path) -> SyncStats:
        export = load_djay_export(export_dir)
        return self.sync_tracks(export)

    def sync_tracks(self, export: DjayExport) -> SyncStats:
        stats = SyncStats(total_tracks=len(export.tracks))
        streaming_index = {st.track_id: st for st in export.streaming_tracks}
        for i, track in enumerate(export.tracks):
            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i + 1}/{stats.total_tracks}")
            try:
                result = self._sync_single_track(track, streaming_index.get(track.track_id))
                if result == "already_synced":
                    stats.already_synced += 1
                elif result == "matched_and_updated":
                    stats.newly_matched += 1
                    stats.updated += 1
                elif result == "unmatched":
                    stats.unmatched += 1
            except Exception as e:
                logger.error(f"Error: {e}")
                stats.errors += 1
        return stats

    def _sync_single_track(self, track, streaming=None) -> str:
        if not track.track_id:
            return "unmatched"
        if self._find_by_djay_id(track.track_id):
            return "already_synced"
        match = self._find_match_without_djay_id(track, streaming)
        if not match:
            return "unmatched"
        if not self.dry_run:
            self._update_djay_id(match.notion_page_id, track.track_id)
        return "matched_and_updated"

    def _find_by_djay_id(self, djay_id):
        try:
            pages = self.tracks_db.client.query_database(
                self.tracks_db.database_id,
                filter={"property": "djay Pro ID", "rich_text": {"equals": djay_id}},
                page_size=1)
            return pages[0] if pages else None
        except Exception:
            return None

    def _find_match_without_djay_id(self, track, streaming=None):
        source_type = (track.source_type or "").lower()
        if source_type == "spotify" and track.source_id:
            match = self._matcher._match_by_rich_text("Spotify ID", track.source_id, "spotify_id")
            if match:
                return match
        if source_type == "soundcloud" and streaming and getattr(streaming, "source_url", None):
            match = self._matcher._match_by_url("SoundCloud URL", streaming.source_url, "soundcloud_url")
            if match:
                return match
        # Note: "Source ID" property doesn't exist in Tracks DB - skip this lookup
        # Fallback to fuzzy metadata matching
        return self._matcher._match_by_metadata(track)

    def _update_djay_id(self, page_id, djay_id):
        self.client.update_page(page_id, {"djay Pro ID": {"rich_text": [{"text": {"content": djay_id}}]}})

def sync_djay_pro_ids(export_dir=None, dry_run=False, similarity_threshold=0.85):
    if export_dir is None:
        export_dir = Path("/Users/brianhellemn/Projects/github-production/djay_pro_export")
    return DjayProIdSync(dry_run=dry_run, similarity_threshold=similarity_threshold).sync_from_export(export_dir)
