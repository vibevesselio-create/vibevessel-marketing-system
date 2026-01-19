"""Rekordbox library integration module.

This module provides tools for reading, parsing, and syncing Rekordbox
DJ library data with Notion and other DJ software.

Requires pyrekordbox:
    pip install pyrekordbox[psutil]

Components:
    - models: Data classes for Rekordbox tracks, cues, playlists
    - db_reader: Read Rekordbox 6/7 encrypted database
    - matcher: Match Rekordbox tracks to Notion database
    - id_sync: Sync Rekordbox IDs to Notion properties
    - cue_parser: Parse .DAT/.EXT analysis files
"""

from .models import (
    RekordboxTrack,
    RekordboxCue,
    RekordboxBeatgrid,
    RekordboxPlaylist,
    RekordboxLibrary,
)

__all__ = [
    "RekordboxTrack",
    "RekordboxCue",
    "RekordboxBeatgrid",
    "RekordboxPlaylist",
    "RekordboxLibrary",
]

__version__ = "1.0.0"
