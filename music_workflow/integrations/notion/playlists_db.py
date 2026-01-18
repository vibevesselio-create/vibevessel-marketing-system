"""
Notion Playlists database operations for music workflow.

This module provides CRUD operations for the Notion playlists database,
including playlist management, track associations, and sync operations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from music_workflow.core.models import TrackInfo
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("playlists-db")


@dataclass
class PlaylistInfo:
    """Represents a playlist with its metadata."""
    id: str
    notion_page_id: Optional[str] = None
    name: str = ""
    description: Optional[str] = None
    source_platform: Optional[str] = None  # spotify, soundcloud, local
    source_url: Optional[str] = None
    track_count: int = 0
    duration_seconds: Optional[float] = None
    tracks: List[str] = field(default_factory=list)  # List of track IDs
    tags: List[str] = field(default_factory=list)
    folder_path: Optional[str] = None
    last_synced: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PlaylistsDatabase:
    """Interface to the Notion playlists database.

    Provides operations for managing playlists and their track associations.
    """

    def __init__(
        self,
        notion_client,
        database_id: Optional[str] = None,
    ):
        """Initialize the playlists database interface.

        Args:
            notion_client: NotionClient instance
            database_id: ID of the playlists database
        """
        self.notion = notion_client
        self.database_id = database_id or self._get_database_id()

    def _get_database_id(self) -> str:
        """Get the playlists database ID from environment or config."""
        import os
        db_id = os.environ.get("PLAYLISTS_DB_ID", "")
        if not db_id:
            logger.warning("PLAYLISTS_DB_ID not set in environment")
        return db_id

    def get_playlist(self, page_id: str) -> Optional[PlaylistInfo]:
        """Get a playlist by its Notion page ID.

        Args:
            page_id: Notion page ID

        Returns:
            PlaylistInfo or None if not found
        """
        try:
            page = self.notion.client.pages.retrieve(page_id=page_id)
            return self._page_to_playlist(page)
        except Exception as e:
            logger.error(f"Failed to get playlist {page_id}: {e}")
            return None

    def get_playlist_by_name(self, name: str) -> Optional[PlaylistInfo]:
        """Get a playlist by its name.

        Args:
            name: Playlist name

        Returns:
            PlaylistInfo or None if not found
        """
        try:
            results = self.notion.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Name",
                    "title": {"equals": name},
                },
                page_size=1,
            )

            pages = results.get("results", [])
            if pages:
                return self._page_to_playlist(pages[0])
            return None

        except Exception as e:
            logger.error(f"Failed to get playlist by name '{name}': {e}")
            return None

    def get_all_playlists(self) -> List[PlaylistInfo]:
        """Get all playlists from the database.

        Returns:
            List of PlaylistInfo objects
        """
        playlists = []
        start_cursor = None

        try:
            while True:
                kwargs = {"database_id": self.database_id, "page_size": 100}
                if start_cursor:
                    kwargs["start_cursor"] = start_cursor

                results = self.notion.client.databases.query(**kwargs)

                for page in results.get("results", []):
                    playlist = self._page_to_playlist(page)
                    if playlist:
                        playlists.append(playlist)

                if results.get("has_more"):
                    start_cursor = results.get("next_cursor")
                else:
                    break

        except Exception as e:
            logger.error(f"Failed to get all playlists: {e}")

        return playlists

    def get_playlists_by_source(self, source_platform: str) -> List[PlaylistInfo]:
        """Get playlists from a specific source platform.

        Args:
            source_platform: Platform name (spotify, soundcloud, local)

        Returns:
            List of PlaylistInfo objects
        """
        try:
            results = self.notion.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Source",
                    "select": {"equals": source_platform},
                },
            )

            return [
                self._page_to_playlist(page)
                for page in results.get("results", [])
            ]

        except Exception as e:
            logger.error(f"Failed to get playlists by source '{source_platform}': {e}")
            return []

    def create_playlist(self, playlist: PlaylistInfo) -> Optional[str]:
        """Create a new playlist in the database.

        Args:
            playlist: PlaylistInfo with playlist data

        Returns:
            Created page ID or None on failure
        """
        try:
            properties = self._playlist_to_properties(playlist)

            page = self.notion.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
            )

            page_id = page.get("id")
            logger.info(f"Created playlist: {playlist.name} ({page_id})")
            return page_id

        except Exception as e:
            logger.error(f"Failed to create playlist '{playlist.name}': {e}")
            return None

    def update_playlist(self, playlist: PlaylistInfo) -> bool:
        """Update an existing playlist.

        Args:
            playlist: PlaylistInfo with updated data

        Returns:
            True on success, False on failure
        """
        if not playlist.notion_page_id:
            logger.error("Cannot update playlist without page ID")
            return False

        try:
            properties = self._playlist_to_properties(playlist)

            self.notion.client.pages.update(
                page_id=playlist.notion_page_id,
                properties=properties,
            )

            logger.info(f"Updated playlist: {playlist.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update playlist '{playlist.name}': {e}")
            return False

    def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_ids: List[str],
    ) -> bool:
        """Add tracks to a playlist's related tracks.

        Args:
            playlist_id: Playlist page ID
            track_ids: List of track page IDs to add

        Returns:
            True on success
        """
        try:
            # Get current relations
            playlist = self.get_playlist(playlist_id)
            if not playlist:
                return False

            current_tracks = set(playlist.tracks)
            new_tracks = current_tracks.union(set(track_ids))

            # Update the relation
            self.notion.client.pages.update(
                page_id=playlist_id,
                properties={
                    "Tracks": {
                        "relation": [{"id": tid} for tid in new_tracks]
                    }
                },
            )

            logger.info(f"Added {len(track_ids)} tracks to playlist {playlist.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add tracks to playlist: {e}")
            return False

    def remove_tracks_from_playlist(
        self,
        playlist_id: str,
        track_ids: List[str],
    ) -> bool:
        """Remove tracks from a playlist.

        Args:
            playlist_id: Playlist page ID
            track_ids: List of track page IDs to remove

        Returns:
            True on success
        """
        try:
            playlist = self.get_playlist(playlist_id)
            if not playlist:
                return False

            current_tracks = set(playlist.tracks)
            remaining_tracks = current_tracks.difference(set(track_ids))

            self.notion.client.pages.update(
                page_id=playlist_id,
                properties={
                    "Tracks": {
                        "relation": [{"id": tid} for tid in remaining_tracks]
                    }
                },
            )

            logger.info(f"Removed {len(track_ids)} tracks from playlist {playlist.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove tracks from playlist: {e}")
            return False

    def sync_playlist_from_source(
        self,
        playlist: PlaylistInfo,
        source_tracks: List[TrackInfo],
    ) -> Dict[str, Any]:
        """Sync a playlist with tracks from an external source.

        Args:
            playlist: Playlist to sync
            source_tracks: Tracks from the external source

        Returns:
            Sync results with counts
        """
        results = {
            "added": 0,
            "removed": 0,
            "unchanged": 0,
            "errors": [],
        }

        try:
            current_track_ids = set(playlist.tracks)
            source_track_ids = set()

            # Process source tracks
            for track in source_tracks:
                if track.notion_page_id:
                    source_track_ids.add(track.notion_page_id)

            # Determine changes
            to_add = source_track_ids - current_track_ids
            to_remove = current_track_ids - source_track_ids
            unchanged = current_track_ids & source_track_ids

            # Apply changes
            if to_add:
                if self.add_tracks_to_playlist(playlist.notion_page_id, list(to_add)):
                    results["added"] = len(to_add)
                else:
                    results["errors"].append("Failed to add new tracks")

            if to_remove:
                if self.remove_tracks_from_playlist(playlist.notion_page_id, list(to_remove)):
                    results["removed"] = len(to_remove)
                else:
                    results["errors"].append("Failed to remove old tracks")

            results["unchanged"] = len(unchanged)

            # Update sync timestamp
            playlist.last_synced = datetime.now()
            playlist.track_count = len(source_track_ids)
            self.update_playlist(playlist)

        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"Playlist sync failed: {e}")

        return results

    def _page_to_playlist(self, page: Dict[str, Any]) -> Optional[PlaylistInfo]:
        """Convert a Notion page to PlaylistInfo."""
        try:
            props = page.get("properties", {})

            # Extract name
            name_prop = props.get("Name", {})
            title_items = name_prop.get("title", [])
            name = "".join(t.get("plain_text", "") for t in title_items)

            # Extract other properties
            description = self._get_rich_text(props, "Description")
            source = props.get("Source", {}).get("select", {}).get("name")
            source_url = props.get("Source URL", {}).get("url")
            folder_path = self._get_rich_text(props, "Folder Path")

            # Extract track relations
            tracks_rel = props.get("Tracks", {}).get("relation", [])
            track_ids = [r.get("id") for r in tracks_rel if r.get("id")]

            # Extract tags
            tags_prop = props.get("Tags", {}).get("multi_select", [])
            tags = [t.get("name") for t in tags_prop if t.get("name")]

            return PlaylistInfo(
                id=page.get("id", ""),
                notion_page_id=page.get("id"),
                name=name,
                description=description,
                source_platform=source,
                source_url=source_url,
                track_count=len(track_ids),
                tracks=track_ids,
                tags=tags,
                folder_path=folder_path,
            )

        except Exception as e:
            logger.error(f"Failed to convert page to playlist: {e}")
            return None

    def _playlist_to_properties(self, playlist: PlaylistInfo) -> Dict[str, Any]:
        """Convert PlaylistInfo to Notion properties."""
        properties = {
            "Name": {"title": [{"text": {"content": playlist.name}}]},
        }

        if playlist.description:
            properties["Description"] = {
                "rich_text": [{"text": {"content": playlist.description}}]
            }

        if playlist.source_platform:
            properties["Source"] = {"select": {"name": playlist.source_platform}}

        if playlist.source_url:
            properties["Source URL"] = {"url": playlist.source_url}

        if playlist.folder_path:
            properties["Folder Path"] = {
                "rich_text": [{"text": {"content": playlist.folder_path}}]
            }

        if playlist.track_count:
            properties["Track Count"] = {"number": playlist.track_count}

        if playlist.tags:
            properties["Tags"] = {
                "multi_select": [{"name": tag} for tag in playlist.tags]
            }

        if playlist.tracks:
            properties["Tracks"] = {
                "relation": [{"id": tid} for tid in playlist.tracks]
            }

        if playlist.last_synced:
            properties["Last Synced"] = {
                "date": {"start": playlist.last_synced.isoformat()}
            }

        return properties

    def _get_rich_text(self, props: Dict[str, Any], prop_name: str) -> str:
        """Extract rich text from properties."""
        prop = props.get(prop_name, {})
        items = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in items)
