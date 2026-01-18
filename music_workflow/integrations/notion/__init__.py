"""Notion API integration for tracks and playlists databases.

This module provides Notion integration for the music workflow system,
including client wrapper and database-specific operations.
"""

from music_workflow.integrations.notion.client import (
    NotionClient,
    get_notion_client,
)
from music_workflow.integrations.notion.tracks_db import (
    TracksDatabase,
    TrackQuery,
    get_tracks_database,
)
from music_workflow.integrations.notion.playlists_db import (
    PlaylistInfo,
    PlaylistsDatabase,
)

__all__ = [
    # Client
    "NotionClient",
    "get_notion_client",
    # Tracks database
    "TracksDatabase",
    "TrackQuery",
    "get_tracks_database",
    # Playlists database
    "PlaylistInfo",
    "PlaylistsDatabase",
]
