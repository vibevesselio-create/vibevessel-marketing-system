"""SoundCloud integration via yt-dlp.

This module provides SoundCloud integration for the music workflow system,
using yt-dlp for track extraction and downloading. Since SoundCloud does
not have a public API, this module relies on yt-dlp for all operations.

Usage:
    from music_workflow.integrations.soundcloud import (
        SoundCloudClient,
        SoundCloudTrack,
        SoundCloudPlaylist,
        get_soundcloud_client,
    )

    client = get_soundcloud_client()
    track = client.get_track("https://soundcloud.com/artist/track")
    files = client.download(track.url, formats=["m4a", "wav"])
"""

from music_workflow.integrations.soundcloud.client import (
    SoundCloudClient,
    SoundCloudTrack,
    SoundCloudPlaylist,
    SoundCloudIntegrationError,
    get_soundcloud_client,
)
from music_workflow.integrations.soundcloud.compat import (
    parse_soundcloud_url,
    extract_track_info_with_retry,
    download_track_to_wav,
    is_preview_track,
    is_geo_restricted,
)

__all__ = [
    "SoundCloudClient",
    "SoundCloudTrack",
    "SoundCloudPlaylist",
    "SoundCloudIntegrationError",
    "get_soundcloud_client",
    # Compatibility functions for migration
    "parse_soundcloud_url",
    "extract_track_info_with_retry",
    "download_track_to_wav",
    "is_preview_track",
    "is_geo_restricted",
]
