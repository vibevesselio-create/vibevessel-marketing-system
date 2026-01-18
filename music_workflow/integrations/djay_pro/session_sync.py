"""
DJ Session Sync Manager for djay Pro ↔ Notion Calendar integration.

This module syncs DJ sessions from djay Pro exports to Notion Calendar database,
creating 2-way relations with Music Tracks.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from music_workflow.integrations.djay_pro.models import (
    DjayExport,
    DjaySession,
    DjaySessionTrack,
    DjayTrack,
)
from music_workflow.integrations.djay_pro.matcher import DjayTrackMatcher, DjayTrackMatch
from music_workflow.integrations.notion.client import NotionClient, get_notion_client
from music_workflow.utils.errors import NotionIntegrationError

logger = logging.getLogger(__name__)

# Database IDs from environment
TRACKS_DB_ID = os.environ.get("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
CALENDAR_DB_ID = os.environ.get("CALENDAR_DB_ID", "ca78e700-de9b-4f25-9935-e3a91281e41a")
ITEM_TYPES_DB_ID = os.environ.get("ITEM_TYPES_DB_ID", "26ce7361-6c27-81bd-812c-dfa26dc9390a")
# DJ Session Item Type page ID (in Item-Types database)
DJ_SESSION_ITEM_TYPE_ID = os.environ.get("DJ_SESSION_ITEM_TYPE_ID", "2eae7361-6c27-81f6-8fea-e0b5199499c5")


@dataclass
class SessionSyncResult:
    """Result of syncing a DJ session to Notion."""
    session_id: str
    notion_page_id: Optional[str] = None
    tracks_matched: int = 0
    tracks_unmatched: int = 0
    created: bool = False
    updated: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.notion_page_id is not None


@dataclass
class SessionSyncStats:
    """Statistics for a sync run."""
    sessions_processed: int = 0
    sessions_created: int = 0
    sessions_updated: int = 0
    sessions_skipped: int = 0
    sessions_failed: int = 0
    total_tracks_matched: int = 0
    total_tracks_unmatched: int = 0
    unmatched_tracks: List[Dict[str, Any]] = field(default_factory=list)


class DJSessionSyncManager:
    """Sync DJ sessions from djay Pro exports to Notion Calendar."""

    def __init__(
        self,
        client: Optional[NotionClient] = None,
        tracks_db_id: Optional[str] = None,
        calendar_db_id: Optional[str] = None,
        track_matcher: Optional[DjayTrackMatcher] = None,
    ) -> None:
        """Initialize the session sync manager.

        Args:
            client: Notion client instance
            tracks_db_id: Music Tracks database ID
            calendar_db_id: Calendar database ID
            track_matcher: Track matcher for finding Notion tracks
        """
        self.client = client or get_notion_client()
        self.tracks_db_id = tracks_db_id or TRACKS_DB_ID
        self.calendar_db_id = calendar_db_id or CALENDAR_DB_ID
        self.track_matcher = track_matcher or DjayTrackMatcher()

        # Cache for existing sessions
        self._session_cache: Dict[str, str] = {}  # session_id -> notion_page_id

    def sync_sessions(
        self,
        export: DjayExport,
        skip_existing: bool = True,
    ) -> Tuple[List[SessionSyncResult], SessionSyncStats]:
        """Sync all sessions from a djay Pro export.

        Args:
            export: DjayExport containing sessions and tracks
            skip_existing: Skip sessions that already exist in Notion

        Returns:
            Tuple of (list of results, stats)
        """
        results = []
        stats = SessionSyncStats()

        # Build track index for matching
        track_index = export.track_index()
        streaming_index = export.streaming_index()

        # Group session tracks by session
        session_tracks_map: Dict[str, List[DjaySessionTrack]] = defaultdict(list)
        for st in export.session_tracks:
            if st.session_id:
                session_tracks_map[st.session_id].append(st)

        # Load existing sessions to cache
        if skip_existing:
            self._load_session_cache()

        for session in export.sessions:
            stats.sessions_processed += 1

            # Check if session already exists
            if skip_existing and session.session_id in self._session_cache:
                stats.sessions_skipped += 1
                results.append(SessionSyncResult(
                    session_id=session.session_id,
                    notion_page_id=self._session_cache[session.session_id],
                    created=False,
                    updated=False,
                ))
                continue

            # Get tracks for this session
            session_tracks = session_tracks_map.get(session.session_id, [])

            # Match tracks to Notion
            matched_tracks, unmatched_tracks = self._match_session_tracks(
                session_tracks, track_index, streaming_index
            )

            # Sync the session (pass track_index for end time calculation)
            result = self._sync_single_session(
                session, session_tracks, matched_tracks, unmatched_tracks, track_index
            )
            results.append(result)

            # Update stats
            if result.created:
                stats.sessions_created += 1
            elif result.updated:
                stats.sessions_updated += 1
            elif result.error:
                stats.sessions_failed += 1

            stats.total_tracks_matched += result.tracks_matched
            stats.total_tracks_unmatched += result.tracks_unmatched

            # Track unmatched for potential auto-processing
            for track_info in unmatched_tracks:
                stats.unmatched_tracks.append({
                    "session_id": session.session_id,
                    **track_info,
                })

        return results, stats

    def _load_session_cache(self) -> None:
        """Load existing DJ sessions from Notion Calendar into cache.

        Uses the Item-type relation property to filter for DJ Session entries.
        """
        try:
            # Query for entries with DJ Session Item-type relation
            filter_dict = {
                "property": "Item-type",
                "relation": {"contains": DJ_SESSION_ITEM_TYPE_ID}
            }
            pages = self.client.query_database(
                self.calendar_db_id,
                filter=filter_dict,
                page_size=100,
            )

            for page in pages:
                session_id = self._get_text_property(page, "Session ID")
                if session_id:
                    self._session_cache[session_id] = page["id"]

            logger.info(f"Loaded {len(self._session_cache)} existing DJ sessions")

        except NotionIntegrationError as e:
            logger.warning(f"Could not load session cache: {e}")

    def _match_session_tracks(
        self,
        session_tracks: List[DjaySessionTrack],
        track_index: Dict[str, DjayTrack],
        streaming_index: Dict[str, Any],
    ) -> Tuple[List[Tuple[DjaySessionTrack, DjayTrackMatch]], List[Dict]]:
        """Match session tracks to Notion.

        Returns:
            Tuple of (matched tracks with their matches, unmatched track info)
        """
        matched = []
        unmatched = []

        for st in session_tracks:
            # Get full track info
            djay_track = track_index.get(st.track_id)
            streaming_track = streaming_index.get(st.track_id)

            if djay_track:
                # Try to find Notion match
                match = self.track_matcher.find_match(djay_track, streaming_track)
                if match:
                    matched.append((st, match))
                else:
                    unmatched.append({
                        "track_id": st.track_id,
                        "title": st.title or (djay_track.title if djay_track else ""),
                        "artist": st.artist or (djay_track.artist if djay_track else ""),
                        "source_type": djay_track.source_type if djay_track else "unknown",
                        "source_id": djay_track.source_id if djay_track else None,
                    })
            else:
                # Track not in export, use session track metadata
                unmatched.append({
                    "track_id": st.track_id,
                    "title": st.title,
                    "artist": st.artist,
                    "source_type": "unknown",
                    "source_id": None,
                })

        return matched, unmatched

    def _sync_single_session(
        self,
        session: DjaySession,
        session_tracks: List[DjaySessionTrack],
        matched_tracks: List[Tuple[DjaySessionTrack, DjayTrackMatch]],
        unmatched_tracks: List[Dict],
        track_index: Optional[Dict[str, DjayTrack]] = None,
    ) -> SessionSyncResult:
        """Sync a single session to Notion.

        Returns:
            SessionSyncResult
        """
        result = SessionSyncResult(
            session_id=session.session_id,
            tracks_matched=len(matched_tracks),
            tracks_unmatched=len(unmatched_tracks),
        )

        try:
            # Build session properties
            properties = self._build_session_properties(
                session, session_tracks, matched_tracks, track_index
            )

            # Check if session exists
            existing_page_id = self._session_cache.get(session.session_id)

            if existing_page_id:
                # Update existing
                self.client.update_page(existing_page_id, properties)
                result.notion_page_id = existing_page_id
                result.updated = True
            else:
                # Create new
                page = self.client.create_page(self.calendar_db_id, properties)
                result.notion_page_id = page["id"]
                result.created = True
                self._session_cache[session.session_id] = page["id"]

            # Update track relations (DJ Sessions property on tracks)
            if result.notion_page_id:
                self._update_track_relations(result.notion_page_id, matched_tracks)

        except NotionIntegrationError as e:
            result.error = str(e)
            logger.error(f"Failed to sync session {session.session_id}: {e}")
        except Exception as e:
            result.error = str(e)
            logger.exception(f"Unexpected error syncing session {session.session_id}")

        return result

    def _build_session_properties(
        self,
        session: DjaySession,
        session_tracks: List[DjaySessionTrack],
        matched_tracks: List[Tuple[DjaySessionTrack, DjayTrackMatch]],
        track_index: Optional[Dict[str, DjayTrack]] = None,
    ) -> Dict[str, Any]:
        """Build Notion properties for a DJ session."""
        # Parse session time
        start_time = None
        if session.start_time:
            try:
                start_time = datetime.fromisoformat(session.start_time.replace("Z", "+00:00"))
            except ValueError:
                pass

        # ═══════════════════════════════════════════════════════════════
        # FIX (2026-01-18): Calculate approximate end time from last track
        # djay Pro doesn't expose session end times, so we estimate from
        # the last track's play_start + duration
        # ═══════════════════════════════════════════════════════════════
        end_time = None
        if session_tracks:
            # Sort by play_start to find the last track
            tracks_with_time = [
                st for st in session_tracks
                if st.play_start
            ]
            if tracks_with_time:
                try:
                    # Sort by play_start timestamp
                    tracks_with_time.sort(
                        key=lambda st: datetime.fromisoformat(st.play_start.replace("Z", "+00:00"))
                    )
                    last_track = tracks_with_time[-1]
                    last_play_start = datetime.fromisoformat(last_track.play_start.replace("Z", "+00:00"))

                    # Get track duration if available
                    track_duration_sec = 180  # Default: 3 minutes
                    if track_index and last_track.track_id in track_index:
                        djay_track = track_index[last_track.track_id]
                        if djay_track.duration_sec:
                            track_duration_sec = djay_track.duration_sec

                    end_time = last_play_start + timedelta(seconds=track_duration_sec)
                    logger.debug(f"Calculated end_time for session {session.session_id}: {end_time}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not calculate end_time: {e}")

        # Calculate BPM stats from matched tracks
        bpms = []
        for st, match in matched_tracks:
            if st.bpm:
                bpms.append(st.bpm)

        avg_bpm = sum(bpms) / len(bpms) if bpms else None
        bpm_range = f"{min(bpms):.0f}-{max(bpms):.0f}" if bpms else None

        # Format session name
        session_name = f"DJ Session"
        if start_time:
            session_name = f"DJ Session - {start_time.strftime('%Y-%m-%d %H:%M')}"

        properties = {
            "Name": {
                "title": [{"text": {"content": session_name}}]
            },
            # Use Item-type relation instead of Type-AI select
            "Item-type": {
                "relation": [{"id": DJ_SESSION_ITEM_TYPE_ID}]
            },
            "Session ID": {
                "rich_text": [{"text": {"content": session.session_id}}]
            },
        }

        # Add date if available
        if start_time:
            properties["Event-Time"] = {
                "date": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat() if end_time else None,
                }
            }

        # Add device info
        if session.device_name:
            properties["Objective"] = {
                "rich_text": [{"text": {"content": f"Device: {session.device_name}"}}]
            }

        # Add BPM info if available
        if bpm_range:
            # Use Property Mapping for BPM Range since dedicated property may not exist
            properties["Property Mapping"] = {
                "rich_text": [{"text": {"content": f"BPM Range: {bpm_range}, Avg: {avg_bpm:.1f}"}}]
            }

        # Add track relations if any matched
        if matched_tracks:
            track_page_ids = [match.notion_page_id for _, match in matched_tracks]
            # Note: Relation property name may need to be discovered/created
            # For now, we'll skip relation if property doesn't exist
            # properties["Tracks Played"] = {
            #     "relation": [{"id": pid} for pid in track_page_ids]
            # }

        return properties

    def _update_track_relations(
        self,
        session_page_id: str,
        matched_tracks: List[Tuple[DjaySessionTrack, DjayTrackMatch]],
    ) -> None:
        """Update DJ Sessions relation on matched tracks."""
        for _, match in matched_tracks:
            try:
                # Get current DJ Sessions relations
                page = self.client.get_page(match.notion_page_id)
                current_relations = self._get_relation_ids(page, "DJ Sessions")

                # Add this session if not already present
                if session_page_id not in current_relations:
                    current_relations.append(session_page_id)
                    self.client.update_page(match.notion_page_id, {
                        "DJ Sessions": {
                            "relation": [{"id": pid} for pid in current_relations]
                        }
                    })
            except NotionIntegrationError:
                # Property may not exist yet, skip silently
                pass

    def _get_text_property(self, page: Dict, prop_name: str) -> Optional[str]:
        """Get text property value from a page."""
        props = page.get("properties", {})
        prop = props.get(prop_name, {})
        text_list = prop.get("rich_text", [])
        if text_list:
            return text_list[0].get("text", {}).get("content", "")
        return None

    def _get_relation_ids(self, page: Dict, prop_name: str) -> List[str]:
        """Get relation IDs from a page property."""
        props = page.get("properties", {})
        prop = props.get(prop_name, {})
        relations = prop.get("relation", [])
        return [r["id"] for r in relations]


def sync_djay_sessions_to_notion(
    export_dir: str,
    skip_existing: bool = True,
) -> SessionSyncStats:
    """Convenience function to sync djay sessions to Notion.

    Args:
        export_dir: Directory containing djay Pro export CSV files
        skip_existing: Skip sessions that already exist

    Returns:
        SessionSyncStats
    """
    from pathlib import Path
    from music_workflow.integrations.djay_pro.export_loader import load_djay_export

    export = load_djay_export(Path(export_dir))
    manager = DJSessionSyncManager()
    results, stats = manager.sync_sessions(export, skip_existing=skip_existing)

    logger.info(
        f"Session sync complete: "
        f"{stats.sessions_created} created, "
        f"{stats.sessions_updated} updated, "
        f"{stats.sessions_skipped} skipped, "
        f"{stats.sessions_failed} failed"
    )

    return stats
