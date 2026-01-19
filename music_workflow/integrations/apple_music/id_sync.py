"""Sync Apple Music track IDs and metadata to Notion.

This module syncs Apple Music-specific data to Notion Music Tracks database,
enabling bidirectional library management and cross-platform validation.

Properties synced:
- Apple Music ID (persistent identifier)
- BPM (if available)
- Rating (star rating)
- Play Count (Apple Music)
- Date Added

Example usage:
    from apple_music.id_sync import AppleMusicIdSync
    from apple_music.library_reader import AppleMusicLibraryReader
    from apple_music.matcher import AppleMusicTrackMatcher

    reader = AppleMusicLibraryReader()
    library = reader.export_library()

    matcher = AppleMusicTrackMatcher(notion, DB_ID)
    sync = AppleMusicIdSync(notion, DB_ID)

    for track in library.tracks.values():
        match = matcher.match_track(track)
        if match.notion_page_id:
            sync.sync_track(track, match.notion_page_id)
"""

import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime

from .models import AppleMusicTrack
from .matcher import AppleMusicTrackMatch

logger = logging.getLogger("apple_music.id_sync")


@dataclass
class SyncResult:
    """Result of syncing a single track.

    Attributes:
        persistent_id: Apple Music persistent ID
        notion_page_id: Notion page ID
        action: What was done (created, updated, skipped, error)
        properties_updated: List of property names that were changed
        error_message: Error details if action is 'error'
    """
    persistent_id: str
    notion_page_id: Optional[str] = None
    action: str = "skipped"  # created, updated, skipped, error
    properties_updated: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class SyncStats:
    """Statistics for a sync operation.

    Attributes:
        total_tracks: Total tracks processed
        already_synced: Tracks already up-to-date
        newly_matched: New tracks matched to Notion
        updated: Tracks with updated properties
        created: New Notion pages created
        unmatched: Tracks without Notion match
        errors: Tracks that failed to sync
        start_time: When sync started
        end_time: When sync completed
    """
    total_tracks: int = 0
    already_synced: int = 0
    newly_matched: int = 0
    updated: int = 0
    created: int = 0
    unmatched: int = 0
    errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tracks": self.total_tracks,
            "already_synced": self.already_synced,
            "newly_matched": self.newly_matched,
            "updated": self.updated,
            "created": self.created,
            "unmatched": self.unmatched,
            "errors": self.errors,
            "duration_seconds": (
                (self.end_time - self.start_time).total_seconds()
                if self.start_time and self.end_time else None
            ),
        }


class AppleMusicIdSync:
    """Sync Apple Music track data to Notion Music Tracks database.

    This class handles updating Notion pages with Apple Music-specific
    metadata, including persistent ID and play counts.

    Attributes:
        notion: Notion API client
        db_id: Music Tracks database ID
        overwrite_existing: Whether to overwrite existing values
    """

    # Notion property names (adjust to match your database schema)
    PROP_APPLE_MUSIC_ID = "Apple Music ID"
    PROP_TEMPO = "Tempo"
    PROP_RATING = "Rating"
    PROP_PLAY_COUNT_AM = "Play Count (Apple Music)"
    PROP_FILE_PATH = "File Path"
    PROP_DATE_ADDED = "Date Added"
    PROP_LAST_SYNCED = "Last Synced (Apple Music)"

    def __init__(
        self,
        notion_client,
        music_tracks_db_id: str,
        overwrite_existing: bool = False,
        dry_run: bool = False
    ):
        """Initialize the sync service.

        Args:
            notion_client: Configured Notion API client
            music_tracks_db_id: Notion database ID for Music Tracks
            overwrite_existing: If True, overwrite non-empty values
            dry_run: If True, don't actually update Notion
        """
        self.notion = notion_client
        self.db_id = music_tracks_db_id
        self.overwrite_existing = overwrite_existing
        self.dry_run = dry_run

    def sync_track(
        self,
        track: AppleMusicTrack,
        notion_page_id: str,
        existing_props: Optional[Dict] = None
    ) -> SyncResult:
        """Sync a single Apple Music track to its Notion page.

        Args:
            track: Apple Music track to sync
            notion_page_id: Notion page to update
            existing_props: Optional cached Notion properties

        Returns:
            SyncResult with details of what was done
        """
        result = SyncResult(
            persistent_id=track.persistent_id,
            notion_page_id=notion_page_id
        )

        try:
            # Get existing properties if not provided
            if existing_props is None:
                page = self.notion.pages.retrieve(page_id=notion_page_id)
                existing_props = page.get("properties", {})

            # Build update payload
            updates = {}
            updated_props = []

            # Apple Music ID (always sync if not set)
            current_am_id = self._get_rich_text(existing_props, self.PROP_APPLE_MUSIC_ID)
            if not current_am_id or (self.overwrite_existing and current_am_id != track.persistent_id):
                updates[self.PROP_APPLE_MUSIC_ID] = {
                    "rich_text": [{"text": {"content": track.persistent_id}}]
                }
                updated_props.append(self.PROP_APPLE_MUSIC_ID)

            # BPM/Tempo (Apple Music stores as integer)
            if track.bpm and track.bpm > 0:
                current_bpm = self._get_number(existing_props, self.PROP_TEMPO)
                if current_bpm is None or self.overwrite_existing:
                    updates[self.PROP_TEMPO] = {"number": float(track.bpm)}
                    updated_props.append(self.PROP_TEMPO)

            # Rating (0-100 scale, convert to 0-5 stars)
            if track.rating > 0:
                # Apple Music uses 0-100, convert to 0-5 star rating
                star_rating = round(track.rating / 20)
                current_rating = self._get_number(existing_props, self.PROP_RATING)
                if current_rating is None or self.overwrite_existing:
                    updates[self.PROP_RATING] = {"number": star_rating}
                    updated_props.append(self.PROP_RATING)

            # Play count
            if track.played_count > 0:
                current_plays = self._get_number(existing_props, self.PROP_PLAY_COUNT_AM)
                if current_plays is None or self.overwrite_existing:
                    updates[self.PROP_PLAY_COUNT_AM] = {"number": track.played_count}
                    updated_props.append(self.PROP_PLAY_COUNT_AM)

            # File path (only if not set and we have location)
            if track.location:
                current_path = self._get_rich_text(existing_props, self.PROP_FILE_PATH)
                if not current_path:
                    updates[self.PROP_FILE_PATH] = {
                        "rich_text": [{"text": {"content": track.location}}]
                    }
                    updated_props.append(self.PROP_FILE_PATH)

            # Date added
            if track.date_added:
                current_date = self._get_date(existing_props, self.PROP_DATE_ADDED)
                if not current_date or self.overwrite_existing:
                    updates[self.PROP_DATE_ADDED] = {
                        "date": {"start": track.date_added.isoformat()}
                    }
                    updated_props.append(self.PROP_DATE_ADDED)

            # Perform update if we have changes
            if updates:
                if not self.dry_run:
                    self.notion.pages.update(
                        page_id=notion_page_id,
                        properties=updates
                    )

                result.action = "updated"
                result.properties_updated = updated_props
                logger.debug(
                    f"Updated track '{track.name}': "
                    f"{', '.join(updated_props)}"
                )
            else:
                result.action = "skipped"
                logger.debug(f"Skipped track '{track.name}' (no changes)")

        except Exception as e:
            result.action = "error"
            result.error_message = str(e)
            logger.error(f"Error syncing track {track.persistent_id}: {e}")

        return result

    def sync_matched_tracks(
        self,
        matches: List[AppleMusicTrackMatch],
        progress_callback: Optional[callable] = None
    ) -> SyncStats:
        """Sync all matched tracks to Notion.

        Args:
            matches: List of track matches from matcher
            progress_callback: Optional callback(current, total)

        Returns:
            SyncStats with operation summary
        """
        stats = SyncStats(start_time=datetime.now())

        total = len(matches)
        for idx, match in enumerate(matches):
            stats.total_tracks += 1

            if match.is_new:
                stats.unmatched += 1
                continue

            result = self.sync_track(
                track=match.apple_music_track,
                notion_page_id=match.notion_page_id,
                existing_props=match.notion_properties
            )

            if result.action == "updated":
                if self.PROP_APPLE_MUSIC_ID in result.properties_updated:
                    stats.newly_matched += 1
                else:
                    stats.updated += 1
            elif result.action == "skipped":
                stats.already_synced += 1
            elif result.action == "error":
                stats.errors += 1

            if progress_callback and idx % 50 == 0:
                progress_callback(idx, total)

        stats.end_time = datetime.now()

        logger.info(
            f"Apple Music sync complete: {stats.updated} updated, "
            f"{stats.newly_matched} newly matched, "
            f"{stats.already_synced} unchanged, "
            f"{stats.unmatched} unmatched, "
            f"{stats.errors} errors"
        )

        return stats

    def create_notion_page(
        self,
        track: AppleMusicTrack,
        parent_db_id: Optional[str] = None
    ) -> SyncResult:
        """Create a new Notion page for an unmatched track.

        Args:
            track: Apple Music track to create page for
            parent_db_id: Database ID (uses self.db_id if not provided)

        Returns:
            SyncResult with new page ID
        """
        result = SyncResult(persistent_id=track.persistent_id)

        try:
            db_id = parent_db_id or self.db_id

            properties = {
                "Title": {
                    "title": [{"text": {"content": track.name or "Untitled"}}]
                },
                self.PROP_APPLE_MUSIC_ID: {
                    "rich_text": [{"text": {"content": track.persistent_id}}]
                },
            }

            # Add optional properties
            if track.artist:
                properties["Artist"] = {
                    "rich_text": [{"text": {"content": track.artist}}]
                }

            if track.album:
                properties["Album"] = {
                    "rich_text": [{"text": {"content": track.album}}]
                }

            if track.bpm and track.bpm > 0:
                properties[self.PROP_TEMPO] = {"number": float(track.bpm)}

            if track.genre:
                properties["Genre"] = {
                    "rich_text": [{"text": {"content": track.genre}}]
                }

            if track.location:
                properties[self.PROP_FILE_PATH] = {
                    "rich_text": [{"text": {"content": track.location}}]
                }

            if track.date_added:
                properties[self.PROP_DATE_ADDED] = {
                    "date": {"start": track.date_added.isoformat()}
                }

            if not self.dry_run:
                page = self.notion.pages.create(
                    parent={"database_id": db_id},
                    properties=properties
                )
                result.notion_page_id = page["id"]

            result.action = "created"
            result.properties_updated = list(properties.keys())

            logger.info(f"Created Notion page for track '{track.name}'")

        except Exception as e:
            result.action = "error"
            result.error_message = str(e)
            logger.error(f"Error creating page for track {track.persistent_id}: {e}")

        return result

    def validate_against_notion(
        self,
        matches: List[AppleMusicTrackMatch]
    ) -> Dict[str, Any]:
        """Validate Apple Music library against Notion database.

        Compares track counts, identifies discrepancies, and generates
        a validation report for library consistency checking.

        Args:
            matches: List of matched tracks

        Returns:
            Validation report dictionary
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_apple_music_tracks": len(matches),
            "matched_to_notion": 0,
            "unmatched": 0,
            "discrepancies": [],
            "missing_in_apple_music": [],
            "match_methods": {},
        }

        for match in matches:
            if match.is_new:
                report["unmatched"] += 1
            else:
                report["matched_to_notion"] += 1

                # Track match methods
                method = match.match_method
                report["match_methods"][method] = report["match_methods"].get(method, 0) + 1

                # Check for discrepancies
                if match.notion_properties:
                    props = match.notion_properties
                    track = match.apple_music_track

                    # Check BPM discrepancy
                    notion_bpm = props.get("bpm")
                    if track.bpm and notion_bpm:
                        bpm_diff = abs(track.bpm - notion_bpm)
                        if bpm_diff > 1.0:  # More than 1 BPM difference
                            report["discrepancies"].append({
                                "type": "bpm_mismatch",
                                "track": track.name,
                                "artist": track.artist,
                                "apple_music_value": track.bpm,
                                "notion_value": notion_bpm,
                                "difference": bpm_diff,
                            })

        report["match_rate"] = (
            f"{100 * report['matched_to_notion'] / len(matches):.1f}%"
            if matches else "0%"
        )

        return report

    # Property extraction helpers

    def _get_number(self, props: Dict, name: str) -> Optional[float]:
        """Extract number property value."""
        prop = props.get(name)
        if prop and prop.get("number") is not None:
            return prop["number"]
        return None

    def _get_rich_text(self, props: Dict, name: str) -> Optional[str]:
        """Extract rich text property value."""
        prop = props.get(name)
        if prop and prop.get("rich_text"):
            texts = prop["rich_text"]
            if texts:
                return texts[0].get("plain_text", "")
        return None

    def _get_select(self, props: Dict, name: str) -> Optional[str]:
        """Extract select property value."""
        prop = props.get(name)
        if prop and prop.get("select"):
            return prop["select"].get("name")
        return None

    def _get_date(self, props: Dict, name: str) -> Optional[str]:
        """Extract date property value."""
        prop = props.get(name)
        if prop and prop.get("date"):
            return prop["date"].get("start")
        return None

    def _is_select_property(self, props: Dict, name: str) -> bool:
        """Check if a property is a select type."""
        prop = props.get(name)
        if prop:
            return prop.get("type") == "select"
        return False
