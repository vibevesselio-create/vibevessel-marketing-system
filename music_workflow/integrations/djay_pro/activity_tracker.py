"""
DJ Activity Tracker for djay Pro ↔ Notion integration.

This module tracks play activity from djay Pro sessions and updates
Music Tracks with statistics:
- Play counts
- Session counts
- Co-occurrence data (tracks played together)
- Last played dates
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import Counter, defaultdict

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

TRACKS_DB_ID = os.environ.get("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")


@dataclass
class TrackActivity:
    """Activity statistics for a single track."""
    track_id: str  # djay Pro track ID
    notion_page_id: Optional[str] = None
    title: str = ""
    artist: str = ""

    # Play statistics
    total_plays: int = 0
    session_count: int = 0
    first_played: Optional[datetime] = None
    last_played: Optional[datetime] = None

    # Co-occurrence
    played_with: Counter = field(default_factory=Counter)

    # Sessions played in (for relation updates)
    session_ids: Set[str] = field(default_factory=set)


@dataclass
class ActivityUpdateResult:
    """Result of updating activity for a track."""
    track_id: str
    notion_page_id: Optional[str]
    updated: bool = False
    error: Optional[str] = None


@dataclass
class ActivitySyncStats:
    """Statistics for activity sync run."""
    tracks_processed: int = 0
    tracks_updated: int = 0
    tracks_skipped: int = 0
    tracks_failed: int = 0
    cooccurrence_relations_created: int = 0


class DJActivityTracker:
    """Track and sync DJ activity data from djay Pro to Notion."""

    def __init__(
        self,
        client: Optional[NotionClient] = None,
        tracks_db_id: Optional[str] = None,
        track_matcher: Optional[DjayTrackMatcher] = None,
        cooccurrence_threshold: int = 3,
    ) -> None:
        """Initialize the activity tracker.

        Args:
            client: Notion client instance
            tracks_db_id: Music Tracks database ID
            track_matcher: Track matcher for finding Notion tracks
            cooccurrence_threshold: Minimum co-play count to create relation
        """
        self.client = client or get_notion_client()
        self.tracks_db_id = tracks_db_id or TRACKS_DB_ID
        self.track_matcher = track_matcher or DjayTrackMatcher()
        self.cooccurrence_threshold = cooccurrence_threshold

    def calculate_activity(self, export: DjayExport) -> Dict[str, TrackActivity]:
        """Calculate activity statistics from djay Pro export.

        Args:
            export: DjayExport containing sessions and tracks

        Returns:
            Dict mapping track_id to TrackActivity
        """
        track_index = export.track_index()
        streaming_index = export.streaming_index()
        activity: Dict[str, TrackActivity] = {}

        # Group session tracks by session
        session_tracks_map: Dict[str, List[DjaySessionTrack]] = defaultdict(list)
        for st in export.session_tracks:
            if st.session_id:
                session_tracks_map[st.session_id].append(st)

        # Session start times for first/last played
        session_times: Dict[str, Optional[datetime]] = {}
        for session in export.sessions:
            session_time = None
            if session.start_time:
                try:
                    session_time = datetime.fromisoformat(
                        session.start_time.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            session_times[session.session_id] = session_time

        # Process each session's tracks
        for session_id, tracks in session_tracks_map.items():
            session_time = session_times.get(session_id)
            track_ids_in_session: Set[str] = set()

            # First pass: count plays and gather track IDs
            for st in tracks:
                if not st.track_id:
                    continue

                track_ids_in_session.add(st.track_id)

                # Initialize activity if needed
                if st.track_id not in activity:
                    djay_track = track_index.get(st.track_id)
                    activity[st.track_id] = TrackActivity(
                        track_id=st.track_id,
                        title=st.title or (djay_track.title if djay_track else ""),
                        artist=st.artist or (djay_track.artist if djay_track else ""),
                    )

                act = activity[st.track_id]
                act.total_plays += 1
                act.session_ids.add(session_id)

                # Update first/last played
                if session_time:
                    if act.first_played is None or session_time < act.first_played:
                        act.first_played = session_time
                    if act.last_played is None or session_time > act.last_played:
                        act.last_played = session_time

            # Second pass: calculate co-occurrence
            for st in tracks:
                if not st.track_id:
                    continue

                act = activity[st.track_id]

                # Same session co-occurrence
                for other_id in track_ids_in_session:
                    if other_id != st.track_id:
                        act.played_with[other_id] += 1

            # Third pass: adjacent track bonus
            sorted_tracks = sorted(tracks, key=lambda x: x.play_start or "")
            for i, st in enumerate(sorted_tracks):
                if not st.track_id:
                    continue

                act = activity[st.track_id]

                # Adjacent bonus (+2)
                if i > 0 and sorted_tracks[i - 1].track_id:
                    act.played_with[sorted_tracks[i - 1].track_id] += 2
                if i < len(sorted_tracks) - 1 and sorted_tracks[i + 1].track_id:
                    act.played_with[sorted_tracks[i + 1].track_id] += 2

        # Calculate session counts
        for act in activity.values():
            act.session_count = len(act.session_ids)

        logger.info(f"Calculated activity for {len(activity)} tracks")
        return activity

    def sync_activity_to_notion(
        self,
        activity: Dict[str, TrackActivity],
        export: DjayExport,
        update_cooccurrence: bool = True,
    ) -> Tuple[List[ActivityUpdateResult], ActivitySyncStats]:
        """Sync activity data to Notion Music Tracks.

        Args:
            activity: Activity data from calculate_activity()
            export: DjayExport for track matching
            update_cooccurrence: Whether to update "Played With" relations

        Returns:
            Tuple of (results list, stats)
        """
        results = []
        stats = ActivitySyncStats()

        track_index = export.track_index()
        streaming_index = export.streaming_index()

        # First pass: match tracks to Notion and update activity properties
        matched_activities: Dict[str, TrackActivity] = {}  # notion_page_id -> activity

        for track_id, act in activity.items():
            stats.tracks_processed += 1

            # Try to match to Notion
            djay_track = track_index.get(track_id)
            streaming_track = streaming_index.get(track_id)

            if djay_track:
                match = self.track_matcher.find_match(djay_track, streaming_track)
                if match:
                    act.notion_page_id = match.notion_page_id
                    matched_activities[match.notion_page_id] = act

            if not act.notion_page_id:
                stats.tracks_skipped += 1
                results.append(ActivityUpdateResult(
                    track_id=track_id,
                    notion_page_id=None,
                    updated=False,
                    error="No Notion match found",
                ))
                continue

            # Update track activity properties
            result = self._update_track_activity(act)
            results.append(result)

            if result.updated:
                stats.tracks_updated += 1
            elif result.error:
                stats.tracks_failed += 1

        # Second pass: update co-occurrence relations
        if update_cooccurrence:
            cooccurrence_count = self._update_cooccurrence_relations(
                matched_activities, activity
            )
            stats.cooccurrence_relations_created = cooccurrence_count

        return results, stats

    def _update_track_activity(self, act: TrackActivity) -> ActivityUpdateResult:
        """Update a single track's activity properties in Notion."""
        result = ActivityUpdateResult(
            track_id=act.track_id,
            notion_page_id=act.notion_page_id,
        )

        if not act.notion_page_id:
            result.error = "No Notion page ID"
            return result

        try:
            properties = {}

            # Play Count (DJ)
            properties["Play Count (DJ)"] = {"number": act.total_plays}

            # Session Count
            properties["Session Count"] = {"number": act.session_count}

            # Last Played (DJ)
            if act.last_played:
                properties["Last Played (DJ)"] = {
                    "date": {"start": act.last_played.isoformat()}
                }

            # First Played (DJ) - if property exists
            # if act.first_played:
            #     properties["First Played (DJ)"] = {
            #         "date": {"start": act.first_played.isoformat()}
            #     }

            self.client.update_page(act.notion_page_id, properties)
            result.updated = True

        except NotionIntegrationError as e:
            # Properties may not exist yet
            if "validation_error" in str(e).lower():
                logger.warning(
                    f"Activity properties may not exist for track {act.track_id}: {e}"
                )
                result.error = "Properties not configured"
            else:
                result.error = str(e)
                logger.error(f"Failed to update activity for {act.track_id}: {e}")

        return result

    def _update_cooccurrence_relations(
        self,
        matched_activities: Dict[str, TrackActivity],
        all_activity: Dict[str, TrackActivity],
    ) -> int:
        """Update "Played With" relations based on co-occurrence data.

        Returns:
            Number of relations created
        """
        relations_created = 0

        for notion_page_id, act in matched_activities.items():
            # Get top co-occurring tracks
            top_cooccurrences = [
                (other_id, count)
                for other_id, count in act.played_with.most_common(10)
                if count >= self.cooccurrence_threshold
            ]

            if not top_cooccurrences:
                continue

            # Resolve other track IDs to Notion page IDs
            related_page_ids = []
            for other_id, count in top_cooccurrences:
                other_act = all_activity.get(other_id)
                if other_act and other_act.notion_page_id:
                    related_page_ids.append(other_act.notion_page_id)

            if not related_page_ids:
                continue

            # Update "Played With" or "Goes With::" relation
            try:
                # Try "Played With" first, fall back to "Goes With::"
                for prop_name in ["Played With", "Goes With::"]:
                    try:
                        self.client.update_page(notion_page_id, {
                            prop_name: {
                                "relation": [{"id": pid} for pid in related_page_ids]
                            }
                        })
                        relations_created += len(related_page_ids)
                        break
                    except NotionIntegrationError:
                        continue
            except Exception as e:
                logger.warning(f"Could not update co-occurrence for {act.track_id}: {e}")

        return relations_created


def sync_djay_activity_to_notion(
    export_dir: str,
    update_cooccurrence: bool = True,
) -> ActivitySyncStats:
    """Convenience function to sync djay activity to Notion.

    Args:
        export_dir: Directory containing djay Pro export CSV files
        update_cooccurrence: Whether to update co-occurrence relations

    Returns:
        ActivitySyncStats
    """
    from pathlib import Path
    from music_workflow.integrations.djay_pro.export_loader import load_djay_export

    export = load_djay_export(Path(export_dir))
    tracker = DJActivityTracker()

    # Calculate activity
    activity = tracker.calculate_activity(export)

    # Sync to Notion
    results, stats = tracker.sync_activity_to_notion(
        activity, export, update_cooccurrence=update_cooccurrence
    )

    logger.info(
        f"Activity sync complete: "
        f"{stats.tracks_updated} updated, "
        f"{stats.tracks_skipped} skipped, "
        f"{stats.tracks_failed} failed, "
        f"{stats.cooccurrence_relations_created} co-occurrence relations"
    )

    return stats
