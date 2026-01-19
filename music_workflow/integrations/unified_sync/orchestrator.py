"""Unified library sync orchestrator.

This module provides the main orchestration layer for synchronizing
music libraries across Apple Music, Rekordbox, djay Pro, and Notion.

The orchestrator coordinates:
- Library loading from all platforms
- Cross-platform matching
- Conflict detection and resolution
- Bidirectional sync operations
- Validation and reporting

Architecture:
    Apple Music ←→ Notion (hub) ←→ Rekordbox
                       ↕
                   djay Pro

Conflict Resolution Rules:
- BPM/Key: djay Pro wins (best analysis engine)
- Title/Artist/Album: Notion wins (curated metadata)
- Rating: Notion wins (user preference)
- Play counts: Sum from all platforms

Example usage:
    from unified_sync import UnifiedLibrarySync

    sync = UnifiedLibrarySync(
        notion_client=notion,
        music_tracks_db_id=DB_ID,
        apple_music_reader=am_reader,
        rekordbox_reader=rb_reader,
        djay_pro_reader=djay_reader,
    )

    report = sync.full_sync(dry_run=True)
    print(report.summary())
"""

import logging
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .cross_matcher import CrossPlatformMatcher, UnifiedTrackMatch

logger = logging.getLogger("unified_sync.orchestrator")


class ConflictResolution(Enum):
    """How conflicts should be resolved."""
    AUTHORITY = "authority"  # Use authority ranking
    DJAY_WINS = "djay_wins"  # djay Pro always wins
    NOTION_WINS = "notion_wins"  # Notion always wins
    MANUAL = "manual"  # Flag for manual review
    SKIP = "skip"  # Skip conflicting tracks


@dataclass
class TrackConflict:
    """Details of a sync conflict.

    Attributes:
        unified_match_id: ID of the unified track
        field: Conflicting field name
        values: Dictionary of platform values
        resolved_value: Value after resolution
        resolution_method: How it was resolved
        needs_review: Whether manual review is needed
    """
    unified_match_id: str
    field: str
    values: Dict[str, Any]
    resolved_value: Optional[Any] = None
    resolution_method: str = "authority"
    needs_review: bool = False


@dataclass
class SyncReport:
    """Complete report of a sync operation.

    Attributes:
        timestamp: When sync was performed
        total_tracks: Total tracks processed
        total_matched: Tracks matched across platforms
        synced_to_notion: Updates pushed to Notion
        synced_to_rekordbox: Updates pushed to Rekordbox
        synced_to_djay: Updates pushed to djay Pro
        synced_to_apple_music: Updates pushed to Apple Music
        conflicts: List of detected conflicts
        errors: List of error messages
        dry_run: Whether this was a dry run
        duration_seconds: Time taken
    """
    timestamp: datetime = field(default_factory=datetime.now)
    total_tracks: int = 0
    total_matched: int = 0
    synced_to_notion: int = 0
    synced_to_rekordbox: int = 0
    synced_to_djay: int = 0
    synced_to_apple_music: int = 0
    conflicts: List[TrackConflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    dry_run: bool = False
    duration_seconds: float = 0.0

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            "UNIFIED LIBRARY SYNC REPORT",
            "=" * 60,
            f"Timestamp: {self.timestamp.isoformat()}",
            f"Duration: {self.duration_seconds:.1f}s",
            f"Dry Run: {self.dry_run}",
            "",
            f"Total Tracks: {self.total_tracks}",
            f"Matched Across Platforms: {self.total_matched}",
            "",
            "Updates Applied:",
            f"  → Notion: {self.synced_to_notion}",
            f"  → Rekordbox: {self.synced_to_rekordbox}",
            f"  → djay Pro: {self.synced_to_djay}",
            f"  → Apple Music: {self.synced_to_apple_music}",
            "",
            f"Conflicts Detected: {len(self.conflicts)}",
            f"Errors: {len(self.errors)}",
            "=" * 60,
        ]

        if self.conflicts:
            lines.append("\nCONFLICT DETAILS:")
            for conflict in self.conflicts[:10]:  # Show first 10
                lines.append(f"  - {conflict.field}: {conflict.values}")
            if len(self.conflicts) > 10:
                lines.append(f"  ... and {len(self.conflicts) - 10} more")

        if self.errors:
            lines.append("\nERRORS:")
            for error in self.errors[:5]:
                lines.append(f"  - {error}")
            if len(self.errors) > 5:
                lines.append(f"  ... and {len(self.errors) - 5} more")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_tracks": self.total_tracks,
            "total_matched": self.total_matched,
            "synced_to_notion": self.synced_to_notion,
            "synced_to_rekordbox": self.synced_to_rekordbox,
            "synced_to_djay": self.synced_to_djay,
            "synced_to_apple_music": self.synced_to_apple_music,
            "conflicts_count": len(self.conflicts),
            "errors_count": len(self.errors),
            "dry_run": self.dry_run,
            "duration_seconds": self.duration_seconds,
        }


class UnifiedLibrarySync:
    """Orchestrate sync across all music library platforms.

    This class coordinates loading, matching, and syncing music
    libraries across Apple Music, Rekordbox, djay Pro, and Notion.

    Attributes:
        notion: Notion API client
        db_id: Music Tracks database ID
        apple_music_reader: Apple Music library reader (optional)
        rekordbox_reader: Rekordbox database reader (optional)
        djay_pro_reader: djay Pro database reader (optional)
        conflict_resolution: How to resolve conflicts
    """

    def __init__(
        self,
        notion_client,
        music_tracks_db_id: str,
        apple_music_reader=None,
        rekordbox_reader=None,
        djay_pro_reader=None,
        conflict_resolution: ConflictResolution = ConflictResolution.AUTHORITY
    ):
        """Initialize the sync orchestrator.

        Args:
            notion_client: Configured Notion API client
            music_tracks_db_id: Notion database ID for Music Tracks
            apple_music_reader: AppleMusicLibraryReader instance
            rekordbox_reader: RekordboxDbReader instance
            djay_pro_reader: DjayProDbReader instance
            conflict_resolution: How to handle conflicts
        """
        self.notion = notion_client
        self.db_id = music_tracks_db_id
        self.apple_music_reader = apple_music_reader
        self.rekordbox_reader = rekordbox_reader
        self.djay_pro_reader = djay_pro_reader
        self.conflict_resolution = conflict_resolution

        # Cross-platform matcher
        self.matcher = CrossPlatformMatcher(notion_client, music_tracks_db_id)

        # Cached libraries
        self._apple_music_library = None
        self._rekordbox_library = None
        self._djay_pro_library = None

    def load_all_libraries(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ):
        """Load all available libraries into memory.

        Args:
            progress_callback: Optional callback(platform, current, total)
        """
        logger.info("=" * 60)
        logger.info("LOADING ALL LIBRARIES")
        logger.info("=" * 60)

        # Load Notion (always required)
        logger.info("Loading Notion Music Tracks...")
        self.matcher.load_notion_tracks(force_reload=True)

        # Load Apple Music
        if self.apple_music_reader:
            logger.info("Loading Apple Music library...")
            try:
                self._apple_music_library = self.apple_music_reader.export_library(
                    include_playlists=False
                )
                self.matcher.load_apple_music_tracks(
                    list(self._apple_music_library.tracks.values()),
                    force_reload=True
                )
            except Exception as e:
                logger.error(f"Failed to load Apple Music: {e}")

        # Load Rekordbox
        if self.rekordbox_reader:
            logger.info("Loading Rekordbox library...")
            try:
                self._rekordbox_library = self.rekordbox_reader.export_library(
                    include_playlists=False
                )
                self.matcher.load_rekordbox_tracks(
                    list(self._rekordbox_library.tracks.values()),
                    force_reload=True
                )
            except Exception as e:
                logger.error(f"Failed to load Rekordbox: {e}")

        # Load djay Pro
        if self.djay_pro_reader:
            logger.info("Loading djay Pro library...")
            try:
                self._djay_pro_library = self.djay_pro_reader.export_library(
                    include_playlists=False
                )
                self.matcher.load_djay_pro_tracks(
                    list(self._djay_pro_library.tracks.values()),
                    force_reload=True
                )
            except Exception as e:
                logger.error(f"Failed to load djay Pro: {e}")

        logger.info("All libraries loaded")

    def full_sync(
        self,
        dry_run: bool = False,
        sync_to_notion: bool = True,
        sync_to_rekordbox: bool = False,
        sync_to_djay: bool = False,
        sync_to_apple_music: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> SyncReport:
        """Perform full sync across all platforms.

        Args:
            dry_run: If True, don't actually update anything
            sync_to_notion: Push updates to Notion
            sync_to_rekordbox: Push updates to Rekordbox
            sync_to_djay: Push updates to djay Pro
            sync_to_apple_music: Push updates to Apple Music
            progress_callback: Optional callback(current, total)

        Returns:
            SyncReport with operation details
        """
        start_time = datetime.now()
        report = SyncReport(dry_run=dry_run)

        logger.info("=" * 60)
        logger.info("UNIFIED LIBRARY SYNC")
        logger.info(f"Dry Run: {dry_run}")
        logger.info("=" * 60)

        try:
            # Load all libraries
            self.load_all_libraries()

            # Build unified index
            unified_tracks = self.matcher.build_unified_index()
            report.total_tracks = len(unified_tracks)

            # Count matches
            report.total_matched = sum(
                1 for t in unified_tracks if len(t.platforms) > 1
            )

            # Detect and collect conflicts
            for track in unified_tracks:
                if track.has_conflicts:
                    for conflict_data in track.conflicts:
                        conflict = TrackConflict(
                            unified_match_id=track.match_id,
                            field=conflict_data["field"],
                            values=conflict_data["values"],
                        )
                        report.conflicts.append(conflict)

            # Sync to Notion
            if sync_to_notion:
                report.synced_to_notion = self._sync_to_notion(
                    unified_tracks, dry_run, progress_callback
                )

            # Sync to Rekordbox (write-back)
            if sync_to_rekordbox:
                report.synced_to_rekordbox = self._sync_to_rekordbox(
                    unified_tracks, dry_run
                )

            # Sync to djay Pro (write-back)
            if sync_to_djay:
                report.synced_to_djay = self._sync_to_djay(
                    unified_tracks, dry_run
                )

            # Sync to Apple Music (write-back)
            if sync_to_apple_music:
                report.synced_to_apple_music = self._sync_to_apple_music(
                    unified_tracks, dry_run
                )

        except Exception as e:
            report.errors.append(f"Sync failed: {str(e)}")
            logger.error(f"Full sync failed: {e}")

        end_time = datetime.now()
        report.duration_seconds = (end_time - start_time).total_seconds()

        logger.info(report.summary())
        return report

    def _sync_to_notion(
        self,
        unified_tracks: List[UnifiedTrackMatch],
        dry_run: bool,
        progress_callback: Optional[Callable] = None
    ) -> int:
        """Sync unified tracks to Notion.

        Args:
            unified_tracks: List of unified track matches
            dry_run: Don't actually update
            progress_callback: Progress callback

        Returns:
            Number of tracks updated
        """
        logger.info("Syncing to Notion...")
        updated = 0
        total = len(unified_tracks)

        for idx, track in enumerate(unified_tracks):
            if progress_callback and idx % 50 == 0:
                progress_callback(idx, total)

            # Skip if no Notion page exists
            if not track.notion_page_id:
                continue

            # Build update payload
            updates = {}

            # Add platform IDs if not already set
            notion_ref = track.platform_refs.get("notion")
            if notion_ref and notion_ref.raw_data:
                # Apple Music ID
                if "apple_music" in track.platforms:
                    am_ref = track.platform_refs.get("apple_music")
                    if am_ref and not notion_ref.raw_data.get("apple_music_id"):
                        updates["Apple Music ID"] = {
                            "rich_text": [{"text": {"content": am_ref.platform_id}}]
                        }

                # Rekordbox ID
                if "rekordbox" in track.platforms:
                    rb_ref = track.platform_refs.get("rekordbox")
                    if rb_ref and not notion_ref.raw_data.get("rekordbox_id"):
                        updates["Rekordbox ID"] = {"number": int(rb_ref.platform_id)}

                # djay Pro ID
                if "djay_pro" in track.platforms:
                    djay_ref = track.platform_refs.get("djay_pro")
                    if djay_ref and not notion_ref.raw_data.get("djay_pro_id"):
                        updates["djay Pro ID"] = {
                            "rich_text": [{"text": {"content": djay_ref.platform_id}}]
                        }

            # Sync BPM from authoritative source
            if track.canonical_bpm and notion_ref:
                current_bpm = notion_ref.bpm
                if not current_bpm or abs(current_bpm - track.canonical_bpm) > 0.1:
                    updates["Tempo"] = {"number": round(track.canonical_bpm, 1)}

            # Sync Key from authoritative source
            if track.canonical_key and notion_ref:
                current_key = notion_ref.key
                if not current_key or current_key != track.canonical_key:
                    updates["Key"] = {
                        "rich_text": [{"text": {"content": track.canonical_key}}]
                    }

            # Apply updates
            if updates:
                if not dry_run:
                    try:
                        self.notion.pages.update(
                            page_id=track.notion_page_id,
                            properties=updates
                        )
                    except Exception as e:
                        logger.error(f"Failed to update {track.notion_page_id}: {e}")
                        continue

                updated += 1
                logger.debug(
                    f"Updated Notion: {track.canonical_title} - "
                    f"{list(updates.keys())}"
                )

        logger.info(f"Synced {updated} tracks to Notion")
        return updated

    def _sync_to_rekordbox(
        self,
        unified_tracks: List[UnifiedTrackMatch],
        dry_run: bool
    ) -> int:
        """Sync unified tracks to Rekordbox.

        Note: Rekordbox write-back is limited. This primarily
        logs what would be synced.

        Args:
            unified_tracks: List of unified track matches
            dry_run: Don't actually update

        Returns:
            Number of tracks that would be updated
        """
        logger.info("Rekordbox write-back (limited)...")
        would_update = 0

        for track in unified_tracks:
            if "rekordbox" not in track.platforms:
                continue

            rb_ref = track.platform_refs.get("rekordbox")
            if not rb_ref:
                continue

            # Check what would need updating
            needs_update = False

            if track.canonical_bpm and rb_ref.bpm:
                if abs(track.canonical_bpm - rb_ref.bpm) > 0.5:
                    needs_update = True

            if track.canonical_key and rb_ref.key:
                if track.canonical_key != rb_ref.key:
                    needs_update = True

            if needs_update:
                would_update += 1
                if not dry_run:
                    logger.warning(
                        f"Rekordbox write-back not implemented for: "
                        f"{track.canonical_title}"
                    )

        logger.info(f"Rekordbox: {would_update} tracks would be updated")
        return would_update

    def _sync_to_djay(
        self,
        unified_tracks: List[UnifiedTrackMatch],
        dry_run: bool
    ) -> int:
        """Sync unified tracks to djay Pro.

        Note: djay Pro write-back is limited. This primarily
        logs what would be synced.

        Args:
            unified_tracks: List of unified track matches
            dry_run: Don't actually update

        Returns:
            Number of tracks that would be updated
        """
        logger.info("djay Pro write-back (limited)...")
        would_update = 0

        # djay Pro database is primarily read-only for external tools
        # Log what would need updating
        for track in unified_tracks:
            if "djay_pro" not in track.platforms:
                continue

            djay_ref = track.platform_refs.get("djay_pro")
            if not djay_ref:
                continue

            # Check if metadata differs
            if track.canonical_title != djay_ref.title:
                would_update += 1
                logger.debug(
                    f"djay Pro title mismatch: {djay_ref.title} vs {track.canonical_title}"
                )

        logger.info(f"djay Pro: {would_update} tracks have metadata differences")
        return would_update

    def _sync_to_apple_music(
        self,
        unified_tracks: List[UnifiedTrackMatch],
        dry_run: bool
    ) -> int:
        """Sync unified tracks to Apple Music.

        Uses AppleScript to update track properties.

        Args:
            unified_tracks: List of unified track matches
            dry_run: Don't actually update

        Returns:
            Number of tracks updated
        """
        logger.info("Syncing to Apple Music...")
        updated = 0

        if not self.apple_music_reader:
            logger.warning("Apple Music reader not configured")
            return 0

        for track in unified_tracks:
            if "apple_music" not in track.platforms:
                continue

            am_ref = track.platform_refs.get("apple_music")
            if not am_ref:
                continue

            needs_update = False
            updates = {}

            # Check BPM
            if track.canonical_bpm and am_ref.bpm:
                if abs(track.canonical_bpm - am_ref.bpm) > 0.5:
                    needs_update = True
                    updates["bpm"] = int(round(track.canonical_bpm))

            if needs_update:
                if not dry_run:
                    try:
                        # Use AppleScript executor to update
                        executor = self.apple_music_reader.executor
                        if "bpm" in updates:
                            executor.set_track_bpm(
                                am_ref.platform_id,
                                updates["bpm"]
                            )
                        updated += 1
                    except Exception as e:
                        logger.error(f"Failed to update Apple Music track: {e}")
                else:
                    updated += 1

        logger.info(f"Synced {updated} tracks to Apple Music")
        return updated

    def validate_libraries(self) -> Dict[str, Any]:
        """Validate consistency across all libraries.

        Returns:
            Validation report dictionary
        """
        logger.info("Validating library consistency...")

        stats = self.matcher.get_statistics()

        validation = {
            "timestamp": datetime.now().isoformat(),
            "platforms_loaded": {
                "notion": len(self.matcher._notion_tracks) > 0,
                "apple_music": len(self.matcher._apple_music_tracks) > 0,
                "rekordbox": len(self.matcher._rekordbox_tracks) > 0,
                "djay_pro": len(self.matcher._djay_pro_tracks) > 0,
            },
            "track_counts": {
                "notion": len(self.matcher._notion_tracks),
                "apple_music": len(self.matcher._apple_music_tracks),
                "rekordbox": len(self.matcher._rekordbox_tracks),
                "djay_pro": len(self.matcher._djay_pro_tracks),
            },
            "matching_statistics": stats,
            "issues": [],
        }

        # Check for large discrepancies
        counts = validation["track_counts"]
        if counts["notion"] > 0:
            for platform, count in counts.items():
                if platform != "notion" and count > 0:
                    diff = abs(counts["notion"] - count)
                    pct = (diff / counts["notion"]) * 100
                    if pct > 10:
                        validation["issues"].append({
                            "type": "count_mismatch",
                            "message": f"{platform} has {pct:.1f}% difference from Notion",
                            "notion_count": counts["notion"],
                            "platform_count": count,
                        })

        return validation

    def get_unmatched_tracks(self) -> Dict[str, List]:
        """Get tracks that exist in only one platform.

        Returns:
            Dictionary of unmatched tracks per platform
        """
        unified_tracks = self.matcher.build_unified_index()

        unmatched = {
            "notion": [],
            "apple_music": [],
            "rekordbox": [],
            "djay_pro": [],
        }

        for track in unified_tracks:
            if len(track.platforms) == 1:
                platform = list(track.platforms)[0]
                ref = track.platform_refs.get(platform)
                if ref:
                    unmatched[platform].append({
                        "title": ref.title,
                        "artist": ref.artist,
                        "file_path": ref.file_path,
                        "platform_id": ref.platform_id,
                    })

        return unmatched
