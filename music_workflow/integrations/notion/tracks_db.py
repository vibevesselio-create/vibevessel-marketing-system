"""
Tracks database operations for music workflow.

This module provides operations specific to the Tracks database in Notion,
including querying, creating, and updating track records.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from music_workflow.core.models import TrackInfo, TrackStatus
from music_workflow.integrations.notion.client import get_notion_client, NotionClient
from music_workflow.utils.errors import NotionIntegrationError
from music_workflow.config.settings import get_settings


@dataclass
class TrackQuery:
    """Query parameters for tracks database."""
    status: Optional[str] = None
    playlist: Optional[str] = None
    needs_processing: Optional[bool] = None
    has_audio_files: Optional[bool] = None
    limit: int = 100


class TracksDatabase:
    """Operations for the Tracks database in Notion.

    Provides methods to query, create, and update track records
    in the Notion Tracks database.
    """

    def __init__(self, database_id: Optional[str] = None, client: Optional[NotionClient] = None):
        """Initialize the tracks database handler.

        Args:
            database_id: Tracks database ID (uses settings if not provided)
            client: Notion client instance
        """
        settings = get_settings()
        self.database_id = database_id or settings.notion.tracks_db_id
        self._client = client

        if not self.database_id:
            raise NotionIntegrationError(
                "Tracks database ID not configured",
                details={"hint": "Set TRACKS_DB_ID environment variable"}
            )

    @property
    def client(self) -> NotionClient:
        """Get the Notion client."""
        if self._client is None:
            self._client = get_notion_client()
        return self._client

    def query_tracks(self, query: Optional[TrackQuery] = None) -> List[TrackInfo]:
        """Query tracks from the database.

        Args:
            query: Query parameters

        Returns:
            List of TrackInfo objects
        """
        query = query or TrackQuery()
        filter_conditions = []

        if query.status:
            filter_conditions.append({
                "property": "Status",
                "status": {"equals": query.status}
            })

        if query.playlist:
            filter_conditions.append({
                "property": "Playlist",
                "rich_text": {"contains": query.playlist}
            })

        if query.needs_processing is not None:
            filter_conditions.append({
                "property": "Needs Processing",
                "checkbox": {"equals": query.needs_processing}
            })

        filter_dict = None
        if len(filter_conditions) == 1:
            filter_dict = filter_conditions[0]
        elif len(filter_conditions) > 1:
            filter_dict = {"and": filter_conditions}

        results = self.client.query_database(
            self.database_id,
            filter=filter_dict,
            page_size=min(query.limit, 100)
        )

        return [self._page_to_track(page) for page in results]

    def get_track_by_id(self, page_id: str) -> Optional[TrackInfo]:
        """Get a track by its Notion page ID.

        Args:
            page_id: Notion page ID

        Returns:
            TrackInfo or None if not found
        """
        try:
            page = self.client.get_page(page_id)
            return self._page_to_track(page)
        except NotionIntegrationError:
            return None

    def update_track(self, track: TrackInfo) -> TrackInfo:
        """Update a track in the database.

        Args:
            track: TrackInfo with updated values

        Returns:
            Updated TrackInfo
        """
        if not track.notion_page_id:
            raise NotionIntegrationError(
                "Cannot update track without page ID",
                details={"track_id": track.id}
            )

        properties = self._track_to_properties(track)
        self.client.update_page(track.notion_page_id, properties)
        return track

    def create_track(self, track: TrackInfo) -> TrackInfo:
        """Create a new track in the database.

        Args:
            track: TrackInfo to create

        Returns:
            TrackInfo with Notion page ID
        """
        properties = self._track_to_properties(track)
        page = self.client.create_page(self.database_id, properties)
        track.notion_page_id = page["id"]
        return track

    def find_duplicates(self, track: TrackInfo) -> List[TrackInfo]:
        """Find potential duplicate tracks.

        Args:
            track: Track to check for duplicates

        Returns:
            List of potential duplicates
        """
        filter_conditions = []

        # Search by title
        if track.title:
            filter_conditions.append({
                "property": "Title",
                "title": {"contains": track.title}
            })

        # Search by Spotify ID if available
        if track.spotify_id:
            filter_conditions.append({
                "property": "Spotify ID",
                "rich_text": {"equals": track.spotify_id}
            })

        if not filter_conditions:
            return []

        filter_dict = {"or": filter_conditions} if len(filter_conditions) > 1 else filter_conditions[0]

        results = self.client.query_database(
            self.database_id,
            filter=filter_dict
        )

        return [self._page_to_track(page) for page in results]

    def _page_to_track(self, page: Dict) -> TrackInfo:
        """Convert a Notion page to TrackInfo."""
        props = page.get("properties", {})

        def get_title(prop_name: str) -> str:
            prop = props.get(prop_name, {})
            title = prop.get("title", [])
            if title and len(title) > 0:
                return title[0].get("text", {}).get("content", "")
            return ""

        def get_text(prop_name: str) -> str:
            prop = props.get(prop_name, {})
            text = prop.get("rich_text", [])
            if text and len(text) > 0:
                return text[0].get("text", {}).get("content", "")
            return ""

        def get_number(prop_name: str) -> Optional[float]:
            prop = props.get(prop_name, {})
            return prop.get("number")

        def get_status(prop_name: str) -> str:
            prop = props.get(prop_name, {})
            status = prop.get("status", {})
            return status.get("name", "")

        def get_checkbox(prop_name: str) -> bool:
            prop = props.get(prop_name, {})
            return prop.get("checkbox", False)

        def get_url(prop_name: str) -> Optional[str]:
            prop = props.get(prop_name, {})
            return prop.get("url")

        track = TrackInfo(
            id=page["id"],
            notion_page_id=page["id"],
            title=get_title("Name") or get_title("Title"),
            artist=get_text("Artist"),
            bpm=get_number("BPM"),
            key=get_text("Key"),
            duration=get_number("Duration"),
            spotify_id=get_text("Spotify ID"),
            soundcloud_url=get_url("SoundCloud URL"),
            source_url=get_url("URL") or get_url("Source URL"),
            playlist=get_text("Playlist"),
            processed=get_checkbox("Processed"),
        )

        # Map status
        status_str = get_status("Status")
        status_mapping = {
            "Ready": TrackStatus.PENDING,
            "Processing": TrackStatus.PROCESSING,
            "Complete": TrackStatus.COMPLETE,
            "Failed": TrackStatus.FAILED,
            "Duplicate": TrackStatus.DUPLICATE,
        }
        track.status = status_mapping.get(status_str, TrackStatus.PENDING)

        return track

    def _track_to_properties(self, track: TrackInfo) -> Dict:
        """Convert TrackInfo to Notion properties."""
        properties = {}

        # Title (Name property)
        if track.title:
            properties["Name"] = {
                "title": [{"text": {"content": track.title}}]
            }

        # Rich text properties
        if track.artist:
            properties["Artist"] = {
                "rich_text": [{"text": {"content": track.artist}}]
            }

        if track.key:
            properties["Key"] = {
                "rich_text": [{"text": {"content": track.key}}]
            }

        if track.spotify_id:
            properties["Spotify ID"] = {
                "rich_text": [{"text": {"content": track.spotify_id}}]
            }

        if track.playlist:
            properties["Playlist"] = {
                "rich_text": [{"text": {"content": track.playlist}}]
            }

        # Number properties
        if track.bpm is not None:
            properties["BPM"] = {"number": track.bpm}

        if track.duration is not None:
            properties["Duration"] = {"number": track.duration}

        # URL properties
        if track.source_url:
            properties["URL"] = {"url": track.source_url}

        if track.soundcloud_url:
            properties["SoundCloud URL"] = {"url": track.soundcloud_url}

        # Checkbox properties
        properties["Processed"] = {"checkbox": track.processed}

        # Status
        status_mapping = {
            TrackStatus.PENDING: "Ready",
            TrackStatus.DOWNLOADING: "Processing",
            TrackStatus.PROCESSING: "Processing",
            TrackStatus.COMPLETE: "Complete",
            TrackStatus.FAILED: "Failed",
            TrackStatus.DUPLICATE: "Duplicate",
        }
        status_name = status_mapping.get(track.status, "Ready")
        properties["Status"] = {"status": {"name": status_name}}

        return properties


# Convenience function
def get_tracks_database(database_id: Optional[str] = None) -> TracksDatabase:
    """Get a TracksDatabase instance."""
    return TracksDatabase(database_id=database_id)
