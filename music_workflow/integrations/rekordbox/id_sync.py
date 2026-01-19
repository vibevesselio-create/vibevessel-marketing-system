"""Sync Rekordbox track IDs and metadata to Notion.

This module syncs Rekordbox-specific data to Notion Music Tracks database,
enabling bidirectional library management.

Properties synced:
- Rekordbox ID (unique identifier)
- BPM/Tempo (from Rekordbox analysis)
- Key (musical key)
- Camelot (harmonic mixing notation)
- Play Count (Rekordbox)
- Rating

Example usage:
    from rekordbox.id_sync import RekordboxIdSync
    from rekordbox.db_reader import RekordboxDbReader
    from rekordbox.matcher import RekordboxTrackMatcher

    reader = RekordboxDbReader()
    library = reader.export_library()

    matcher = RekordboxTrackMatcher(notion, DB_ID)
    sync = RekordboxIdSync(notion, DB_ID)

    for track in library.tracks.values():
        match = matcher.match_track(track)
        if match.notion_page_id:
            sync.sync_track(track, match.notion_page_id)
"""

import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime

from .models import RekordboxTrack
from .matcher import RekordboxTrackMatch

logger = logging.getLogger("rekordbox.id_sync")


@dataclass
class SyncResult:
    """Result of syncing a single track.

    Attributes:
        track_id: Rekordbox track ID
        notion_page_id: Notion page ID
        action: What was done (created, updated, skipped, error)
        properties_updated: List of property names that were changed
        error_message: Error details if action is 'error'
    """
    track_id: int
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


class RekordboxIdSync:
    """Sync Rekordbox track data to Notion Music Tracks database.

    This class handles updating Notion pages with Rekordbox-specific
    metadata, including BPM, Key, and play counts.

    Attributes:
        notion: Notion API client
        db_id: Music Tracks database ID
        overwrite_existing: Whether to overwrite existing values
    """

    # Notion property names (adjust to match your database schema)
    PROP_REKORDBOX_ID = "Rekordbox ID"
    PROP_TEMPO = "Tempo"
    PROP_KEY = "Key"
    PROP_CAMELOT = "Camelot"
    PROP_PLAY_COUNT_RB = "Play Count (Rekordbox)"
    PROP_RATING = "Rating"
    PROP_FILE_PATH = "File Path"
    PROP_LAST_SYNCED = "Last Synced (Rekordbox)"

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
        track: RekordboxTrack,
        notion_page_id: str,
        existing_props: Optional[Dict] = None
    ) -> SyncResult:
        """Sync a single Rekordbox track to its Notion page.

        Args:
            track: Rekordbox track to sync
            notion_page_id: Notion page to update
            existing_props: Optional cached Notion properties

        Returns:
            SyncResult with details of what was done
        """
        result = SyncResult(
            track_id=track.track_id,
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

            # Rekordbox ID (always sync if not set)
            current_rb_id = self._get_number(existing_props, self.PROP_REKORDBOX_ID)
            if current_rb_id is None or (self.overwrite_existing and current_rb_id != track.track_id):
                updates[self.PROP_REKORDBOX_ID] = {"number": track.track_id}
                updated_props.append(self.PROP_REKORDBOX_ID)

            # BPM/Tempo
            if track.bpm:
                current_bpm = self._get_number(existing_props, self.PROP_TEMPO)
                if current_bpm is None or self.overwrite_existing:
                    # Round to 1 decimal place
                    updates[self.PROP_TEMPO] = {"number": round(track.bpm, 1)}
                    updated_props.append(self.PROP_TEMPO)

            # Key
            if track.key:
                current_key = self._get_rich_text(existing_props, self.PROP_KEY)
                if current_key is None or self.overwrite_existing:
                    updates[self.PROP_KEY] = {
                        "rich_text": [{"text": {"content": track.key}}]
                    }
                    updated_props.append(self.PROP_KEY)

            # Camelot notation
            if track.key_camelot:
                # Check if Camelot is a select or rich_text property
                current_camelot = (
                    self._get_select(existing_props, self.PROP_CAMELOT) or
                    self._get_rich_text(existing_props, self.PROP_CAMELOT)
                )
                if current_camelot is None or self.overwrite_existing:
                    # Try select first, fall back to rich_text
                    if self._is_select_property(existing_props, self.PROP_CAMELOT):
                        updates[self.PROP_CAMELOT] = {
                            "select": {"name": track.key_camelot}
                        }
                    else:
                        updates[self.PROP_CAMELOT] = {
                            "rich_text": [{"text": {"content": track.key_camelot}}]
                        }
                    updated_props.append(self.PROP_CAMELOT)

            # Play count
            if track.play_count > 0:
                current_plays = self._get_number(existing_props, self.PROP_PLAY_COUNT_RB)
                if current_plays is None or self.overwrite_existing:
                    updates[self.PROP_PLAY_COUNT_RB] = {"number": track.play_count}
                    updated_props.append(self.PROP_PLAY_COUNT_RB)

            # Rating (if > 0)
            if track.rating > 0:
                current_rating = self._get_number(existing_props, self.PROP_RATING)
                if current_rating is None or self.overwrite_existing:
                    updates[self.PROP_RATING] = {"number": track.rating}
                    updated_props.append(self.PROP_RATING)

            # File path (only if not set)
            if track.file_path:
                current_path = self._get_rich_text(existing_props, self.PROP_FILE_PATH)
                if not current_path:
                    updates[self.PROP_FILE_PATH] = {
                        "rich_text": [{"text": {"content": track.file_path}}]
                    }
                    updated_props.append(self.PROP_FILE_PATH)

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
                    f"Updated track {track.track_id} '{track.title}': "
                    f"{', '.join(updated_props)}"
                )
            else:
                result.action = "skipped"
                logger.debug(f"Skipped track {track.track_id} '{track.title}' (no changes)")

        except Exception as e:
            result.action = "error"
            result.error_message = str(e)
            logger.error(f"Error syncing track {track.track_id}: {e}")

        return result

    def sync_matched_tracks(
        self,
        matches: List[RekordboxTrackMatch],
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
                track=match.rekordbox_track,
                notion_page_id=match.notion_page_id,
                existing_props=match.notion_properties
            )

            if result.action == "updated":
                if self.PROP_REKORDBOX_ID in result.properties_updated:
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
            f"Sync complete: {stats.updated} updated, "
            f"{stats.newly_matched} newly matched, "
            f"{stats.already_synced} unchanged, "
            f"{stats.unmatched} unmatched, "
            f"{stats.errors} errors"
        )

        return stats

    def create_notion_page(
        self,
        track: RekordboxTrack,
        parent_db_id: Optional[str] = None
    ) -> SyncResult:
        """Create a new Notion page for an unmatched track.

        Args:
            track: Rekordbox track to create page for
            parent_db_id: Database ID (uses self.db_id if not provided)

        Returns:
            SyncResult with new page ID
        """
        result = SyncResult(track_id=track.track_id)

        try:
            db_id = parent_db_id or self.db_id

            properties = {
                "Title": {
                    "title": [{"text": {"content": track.title or "Untitled"}}]
                },
                self.PROP_REKORDBOX_ID: {"number": track.track_id},
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

            if track.bpm:
                properties[self.PROP_TEMPO] = {"number": round(track.bpm, 1)}

            if track.key:
                properties[self.PROP_KEY] = {
                    "rich_text": [{"text": {"content": track.key}}]
                }

            if track.key_camelot:
                properties[self.PROP_CAMELOT] = {
                    "select": {"name": track.key_camelot}
                }

            if track.genre:
                properties["Genre"] = {
                    "rich_text": [{"text": {"content": track.genre}}]
                }

            if track.file_path:
                properties[self.PROP_FILE_PATH] = {
                    "rich_text": [{"text": {"content": track.file_path}}]
                }

            if not self.dry_run:
                page = self.notion.pages.create(
                    parent={"database_id": db_id},
                    properties=properties
                )
                result.notion_page_id = page["id"]

            result.action = "created"
            result.properties_updated = list(properties.keys())

            logger.info(f"Created Notion page for track '{track.title}'")

        except Exception as e:
            result.action = "error"
            result.error_message = str(e)
            logger.error(f"Error creating page for track {track.track_id}: {e}")

        return result

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

    def _is_select_property(self, props: Dict, name: str) -> bool:
        """Check if a property is a select type."""
        prop = props.get(name)
        if prop:
            return prop.get("type") == "select"
        return False
