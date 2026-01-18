"""External service integrations for music workflow.

This module provides integrations with external services:
- Notion: Database operations for tracks and playlists
- Spotify: Track metadata enrichment and playlist sync
- Eagle: Library asset management and import
- SoundCloud: Track downloading and metadata extraction

Usage:
    from music_workflow.integrations import (
        NotionClient,
        SpotifyClient,
        EagleClient,
        SoundCloudClient,
    )
    
    # Or import from submodules:
    from music_workflow.integrations.notion import NotionClient, TracksDatabase
    from music_workflow.integrations.spotify import SpotifyClient, SpotifyTrack
    from music_workflow.integrations.eagle import EagleClient, EagleItem
    from music_workflow.integrations.soundcloud import SoundCloudClient, SoundCloudTrack
"""

# Import main clients from submodules for convenience
from music_workflow.integrations.notion import (
    NotionClient,
    get_notion_client,
    TracksDatabase,
    PlaylistsDatabase,
)
from music_workflow.integrations.spotify import (
    SpotifyClient,
    SpotifyTrack,
    SpotifyPlaylist,
    get_spotify_client,
)
from music_workflow.integrations.eagle import (
    EagleClient,
    EagleItem,
    get_eagle_client,
)
from music_workflow.integrations.soundcloud import (
    SoundCloudClient,
    SoundCloudTrack,
    SoundCloudPlaylist,
    get_soundcloud_client,
)

__all__ = [
    # Notion
    "NotionClient",
    "get_notion_client",
    "TracksDatabase",
    "PlaylistsDatabase",
    # Spotify
    "SpotifyClient",
    "SpotifyTrack",
    "SpotifyPlaylist",
    "get_spotify_client",
    # Eagle
    "EagleClient",
    "EagleItem",
    "get_eagle_client",
    # SoundCloud
    "SoundCloudClient",
    "SoundCloudTrack",
    "SoundCloudPlaylist",
    "get_soundcloud_client",
]
