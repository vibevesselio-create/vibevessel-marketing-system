"""Unified three-library sync orchestrator.

This module provides a unified synchronization layer for managing music
libraries across Apple Music, Rekordbox, djay Pro, and Notion.

The orchestrator implements a hub-and-spoke model where Notion serves
as the central database, and each DJ library syncs bidirectionally.

Key Features:
- Cross-platform track matching (file path, title/artist, platform IDs)
- Conflict resolution with configurable authority rules
- Validation and consistency checking
- Batch sync operations with progress tracking

Architecture:
    Apple Music ←→ Notion (hub) ←→ Rekordbox
                       ↕
                   djay Pro

Example usage:
    from unified_sync import UnifiedLibrarySync

    sync = UnifiedLibrarySync(notion_client, MUSIC_TRACKS_DB_ID)
    report = sync.full_sync()

    print(f"Matched: {report.total_matched}")
    print(f"Conflicts: {len(report.conflicts)}")
"""

from .orchestrator import (
    UnifiedLibrarySync,
    SyncReport,
    TrackConflict,
    ConflictResolution,
)
from .cross_matcher import (
    CrossPlatformMatcher,
    UnifiedTrackMatch,
)
from .validators import (
    LibraryValidator,
    ValidationReport,
)

__all__ = [
    # Orchestrator
    "UnifiedLibrarySync",
    "SyncReport",
    "TrackConflict",
    "ConflictResolution",
    # Matcher
    "CrossPlatformMatcher",
    "UnifiedTrackMatch",
    # Validators
    "LibraryValidator",
    "ValidationReport",
]

__version__ = "1.0.0"
