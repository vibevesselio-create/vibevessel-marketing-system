#!/usr/bin/env python3
"""
djay Pro / Rekordbox Recording Management Script
─────────────────────────────────────────────────────────────────────────────────────
Manages recording files from DJ applications:
1. Identifies "good" recordings (renamed from generic timestamp format)
2. Imports good recordings to Eagle library with fingerprinting and metadata
3. Cleans up un-renamed generic recordings (with duration safety check)

Recording Identification Logic:
- Generic pattern: "Recording MM-DD-YY, HH.MM.SS.wav" or "Recording M-DD-YY, H.MM.SS AM/PM.m4a"
- Renamed recordings: Any file NOT matching the generic pattern = GOOD (keep)
- Generic recordings < 1 minute duration = safe to delete
- Generic recordings >= 1 minute duration = require manual review

Aligned with Seren Media Workspace Standards
Version: 2026-01-15
"""

from __future__ import annotations

import os
import sys
import re
import argparse
import subprocess
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import unified configuration
try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
    unified_config = get_unified_config()
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    import importlib
    fallback_search = [script_dir, script_dir.parent / "scripts"]
    for candidate in fallback_search:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
    try:
        fallback_module = importlib.import_module("unified_config_fallback")
        sys.modules.setdefault("unified_config", fallback_module)
        load_unified_env = fallback_module.load_unified_env
        get_unified_config = fallback_module.get_unified_config
        load_unified_env()
        unified_config = get_unified_config()
    except ImportError:
        unified_config = {}
        print(f"[manage_djay_recordings] unified_config unavailable ({unified_err}); using defaults.", file=sys.stderr)

# Import logging
try:
    from shared_core.logging import setup_logging
    workspace_logger = setup_logging(session_id="manage_djay_recordings", enable_notion=False)
except (TimeoutError, OSError, ModuleNotFoundError):
    import logging
    workspace_logger = logging.getLogger("manage_djay_recordings")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

# Import Notion client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    NOTION_CLIENT_AVAILABLE = False
    Client = None

# Import shared_core token manager
try:
    from shared_core.notion.token_manager import get_notion_token
except ImportError:
    def get_notion_token():
        return os.getenv("NOTION_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")

# ─────────────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────────────

# Recording directories to scan
DEFAULT_RECORDING_DIRS = [
    Path.home() / "Music" / "djay" / "Recordings",
    Path("/Volumes/VIBES/Music/Unknown Artist/Unknown Album"),
    Path("/Volumes/VIBES/Djay-Pro-Auto-Import"),
]

# Environment-based configuration
EAGLE_API_BASE = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "http://localhost:41595")
EAGLE_LIBRARY_PATH = unified_config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")
TRACKS_DB_ID = unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
MUSIC_PLAYLISTS_DB_ID = os.getenv("MUSIC_PLAYLISTS_DB_ID", "") or os.getenv("PLAYLISTS_DB_ID", "")

# Minimum duration (seconds) for generic recordings to be protected from deletion
MIN_DURATION_FOR_REVIEW = 60  # 1 minute

# Generic recording filename patterns
GENERIC_RECORDING_PATTERNS = [
    # djay Pro WAV format: "Recording 11-15-25, 15.29.42.wav"
    re.compile(r"^Recording\s+\d{1,2}-\d{1,2}-\d{2,4},?\s+\d{1,2}\.\d{2}\.\d{2}\.wav$", re.IGNORECASE),
    # djay Pro M4A format: "Recording 1-15-26, 1.48.25 AM.m4a"
    re.compile(r"^Recording\s+\d{1,2}-\d{1,2}-\d{2,4},?\s+\d{1,2}\.\d{2}\.\d{2}\s*(AM|PM)?\.m4a$", re.IGNORECASE),
    # Generic timestamp format: "Recording 2026-01-15 at 13.45.32.m4a"
    re.compile(r"^Recording\s+\d{4}-\d{2}-\d{2}\s+at\s+\d{2}\.\d{2}\.\d{2}\.\w+$", re.IGNORECASE),
    # Rekordbox format variations
    re.compile(r"^REC\s*\d{4}-\d{2}-\d{2}\s+\d{2}-\d{2}-\d{2}\.\w+$", re.IGNORECASE),
]


class RecordingStatus(Enum):
    """Status classification for recording files."""
    RENAMED_GOOD = "renamed_good"  # Renamed from generic = keep
    GENERIC_SHORT = "generic_short"  # Generic name, < 1 min = delete
    GENERIC_LONG = "generic_long"  # Generic name, >= 1 min = review
    ALREADY_PROCESSED = "already_processed"  # Already in Eagle/Notion
    ERROR = "error"  # Error processing file


@dataclass
class RecordingFile:
    """Represents a recording file with metadata."""
    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_time: datetime
    duration_seconds: Optional[float] = None
    status: RecordingStatus = RecordingStatus.ERROR
    fingerprint: Optional[str] = None
    eagle_id: Optional[str] = None
    notion_page_id: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RecordingManager:
    """Manages DJ application recordings: identification, import, and cleanup."""

    def __init__(
        self,
        recording_dirs: List[Path],
        dry_run: bool = False,
        skip_eagle: bool = False,
        skip_notion: bool = False,
        verbose: bool = False,
        min_duration_for_review: int = MIN_DURATION_FOR_REVIEW
    ):
        self.recording_dirs = [Path(d) for d in recording_dirs]
        self.dry_run = dry_run
        self.skip_eagle = skip_eagle
        self.skip_notion = skip_notion
        self.verbose = verbose
        self.min_duration_for_review = min_duration_for_review

        self.recordings: List[RecordingFile] = []
        self.duplicates: List[RecordingFile] = []  # Duplicate recordings to be cleaned up
        self.stats = {
            "total_scanned": 0,
            "renamed_good": 0,
            "generic_short": 0,
            "generic_long": 0,
            "already_processed": 0,
            "duplicates_found": 0,
            "duplicates_removed": 0,
            "imported_to_eagle": 0,
            "synced_to_notion": 0,
            "deleted": 0,
            "errors": 0
        }

        # Initialize Notion client
        self.notion_client = None
        if not skip_notion and NOTION_CLIENT_AVAILABLE:
            try:
                token = get_notion_token()
                if token:
                    self.notion_client = Client(auth=token)
                    workspace_logger.info("Notion client initialized")
            except Exception as e:
                workspace_logger.warning(f"Failed to initialize Notion client: {e}")

    def is_generic_recording(self, filename: str) -> bool:
        """Check if filename matches generic recording pattern."""
        for pattern in GENERIC_RECORDING_PATTERNS:
            if pattern.match(filename):
                return True
        return False

    def get_audio_duration(self, file_path: Path) -> Optional[float]:
        """Get audio file duration in seconds using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except subprocess.TimeoutExpired:
            workspace_logger.warning(f"Timeout getting duration for: {file_path.name}")
        except (ValueError, subprocess.SubprocessError) as e:
            workspace_logger.debug(f"Error getting duration for {file_path.name}: {e}")
        return None

    def compute_fingerprint(self, file_path: Path) -> Optional[str]:
        """Compute audio fingerprint using fpcalc (Chromaprint)."""
        try:
            cmd = ["fpcalc", "-json", str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data.get("fingerprint")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, subprocess.SubprocessError) as e:
            workspace_logger.debug(f"Error computing fingerprint for {file_path.name}: {e}")
        return None

    def scan_directories(self) -> List[RecordingFile]:
        """Scan all recording directories and classify files."""
        workspace_logger.info("Scanning recording directories...")

        audio_extensions = {".wav", ".m4a", ".mp3", ".aiff", ".flac", ".aac"}

        for rec_dir in self.recording_dirs:
            if not rec_dir.exists():
                workspace_logger.warning(f"Directory not found: {rec_dir}")
                continue

            workspace_logger.info(f"Scanning: {rec_dir}")

            for file_path in rec_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                ext = file_path.suffix.lower()
                if ext not in audio_extensions:
                    continue

                self.stats["total_scanned"] += 1

                try:
                    stat = file_path.stat()
                    recording = RecordingFile(
                        path=file_path,
                        filename=file_path.name,
                        extension=ext,
                        size_bytes=stat.st_size,
                        modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    )

                    # Classify the recording
                    self._classify_recording(recording)
                    self.recordings.append(recording)

                except Exception as e:
                    workspace_logger.error(f"Error processing {file_path.name}: {e}")
                    self.stats["errors"] += 1

        workspace_logger.info(f"Scan complete: {self.stats['total_scanned']} files found")

        # Detect and handle duplicates
        self._detect_duplicates()

        return self.recordings

    def _detect_duplicates(self):
        """Detect duplicate recordings across directories, keep most recent copy."""
        workspace_logger.info("Detecting duplicate recordings...")

        # Group recordings by normalized filename (case-insensitive, ignoring path)
        # Also group by filename + size for more accurate matching
        by_name: Dict[str, List[RecordingFile]] = {}
        by_name_size: Dict[Tuple[str, int], List[RecordingFile]] = {}

        for recording in self.recordings:
            # Skip generic recordings - they have unique timestamps
            if recording.status in (RecordingStatus.GENERIC_SHORT, RecordingStatus.GENERIC_LONG):
                continue

            # Normalize filename for comparison
            normalized_name = recording.filename.lower().strip()

            # Group by name only
            if normalized_name not in by_name:
                by_name[normalized_name] = []
            by_name[normalized_name].append(recording)

            # Group by name + size for more precise matching
            key = (normalized_name, recording.size_bytes)
            if key not in by_name_size:
                by_name_size[key] = []
            by_name_size[key].append(recording)

        # Find duplicates - prefer name+size match, fallback to name-only
        duplicates_to_remove = set()

        for key, recordings in by_name_size.items():
            if len(recordings) > 1:
                # Sort by modified time, most recent first
                sorted_recs = sorted(recordings, key=lambda r: r.modified_time, reverse=True)
                keeper = sorted_recs[0]

                for dup in sorted_recs[1:]:
                    if dup.path not in duplicates_to_remove:
                        duplicates_to_remove.add(dup.path)
                        self.duplicates.append(dup)
                        self.stats["duplicates_found"] += 1
                        if self.verbose:
                            workspace_logger.info(
                                f"[DUPLICATE] {dup.filename} in {dup.path.parent.name} "
                                f"(keeping {keeper.path.parent.name} - more recent)"
                            )

        # Also check name-only matches with same duration (within 1 second tolerance)
        for name, recordings in by_name.items():
            if len(recordings) > 1:
                # Filter to only those not already marked as duplicates
                remaining = [r for r in recordings if r.path not in duplicates_to_remove]

                if len(remaining) > 1:
                    # Group by duration (with tolerance)
                    duration_groups: Dict[int, List[RecordingFile]] = {}
                    for rec in remaining:
                        if rec.duration_seconds is not None:
                            duration_key = int(rec.duration_seconds)  # Round to nearest second
                            if duration_key not in duration_groups:
                                duration_groups[duration_key] = []
                            duration_groups[duration_key].append(rec)

                    for dur_key, dur_recs in duration_groups.items():
                        if len(dur_recs) > 1:
                            # Same name, same duration = likely duplicate
                            sorted_recs = sorted(dur_recs, key=lambda r: r.modified_time, reverse=True)
                            keeper = sorted_recs[0]

                            for dup in sorted_recs[1:]:
                                if dup.path not in duplicates_to_remove:
                                    duplicates_to_remove.add(dup.path)
                                    self.duplicates.append(dup)
                                    self.stats["duplicates_found"] += 1
                                    if self.verbose:
                                        workspace_logger.info(
                                            f"[DUPLICATE] {dup.filename} ({dur_key}s) in {dup.path.parent.name} "
                                            f"(keeping {keeper.path.parent.name})"
                                        )

        # Remove duplicates from main recordings list
        self.recordings = [r for r in self.recordings if r.path not in duplicates_to_remove]

        workspace_logger.info(f"Found {self.stats['duplicates_found']} duplicate recordings")

    def _classify_recording(self, recording: RecordingFile):
        """Classify a recording based on filename and duration."""
        filename = recording.filename

        # Check if it's a generic recording
        if self.is_generic_recording(filename):
            # Get duration to determine if it should be protected
            duration = self.get_audio_duration(recording.path)
            recording.duration_seconds = duration

            if duration is not None and duration >= self.min_duration_for_review:
                recording.status = RecordingStatus.GENERIC_LONG
                self.stats["generic_long"] += 1
                if self.verbose:
                    workspace_logger.info(f"[REVIEW] Generic recording >= 1 min: {filename} ({duration:.1f}s)")
            else:
                recording.status = RecordingStatus.GENERIC_SHORT
                self.stats["generic_short"] += 1
                if self.verbose:
                    workspace_logger.info(f"[DELETE] Generic recording < 1 min: {filename} ({duration:.1f}s if known)")
        else:
            # Renamed recording = good, should be imported
            recording.status = RecordingStatus.RENAMED_GOOD
            self.stats["renamed_good"] += 1
            if self.verbose:
                workspace_logger.info(f"[IMPORT] Renamed recording (good): {filename}")

            # Get duration and fingerprint for good recordings
            recording.duration_seconds = self.get_audio_duration(recording.path)

    def import_to_eagle(self, recording: RecordingFile) -> bool:
        """Import a recording to Eagle library."""
        if self.skip_eagle:
            return False

        try:
            import requests

            # Prepare Eagle API request
            endpoint = f"{EAGLE_API_BASE}/api/item/addFromPath"

            # Extract metadata for Eagle
            title = recording.path.stem
            tags = ["Recording", "djay Pro", "DJ Mix"]

            # Add date tag
            date_tag = recording.modified_time.strftime("%Y-%m")
            tags.append(date_tag)

            payload = {
                "path": str(recording.path),
                "name": title,
                "tags": tags,
                "annotation": f"Imported from DJ recordings on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            }

            if self.dry_run:
                workspace_logger.info(f"[DRY RUN] Would import to Eagle: {recording.filename}")
                return True

            response = requests.post(endpoint, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    recording.eagle_id = result.get("data", {}).get("id")
                    self.stats["imported_to_eagle"] += 1
                    workspace_logger.info(f"Imported to Eagle: {recording.filename}")
                    return True

            workspace_logger.warning(f"Eagle import failed for {recording.filename}: {response.text}")
            return False

        except Exception as e:
            workspace_logger.error(f"Error importing to Eagle: {e}")
            return False

    def sync_to_notion(self, recording: RecordingFile) -> bool:
        """Sync a recording to Notion Tracks database."""
        if self.skip_notion or not self.notion_client:
            return False

        try:
            # Build properties for Notion
            properties = {
                "Title": {"title": [{"text": {"content": recording.path.stem}}]},
                "Source": {"select": {"name": "DJ Recording"}},
            }

            # Add duration if available
            if recording.duration_seconds:
                properties["Duration (s)"] = {"number": round(recording.duration_seconds, 2)}

            # Add file path
            properties["File Path"] = {"rich_text": [{"text": {"content": str(recording.path)}}]}

            # Add Eagle ID if available
            if recording.eagle_id:
                properties["Eagle File ID"] = {"rich_text": [{"text": {"content": recording.eagle_id}}]}

            if self.dry_run:
                workspace_logger.info(f"[DRY RUN] Would sync to Notion: {recording.filename}")
                return True

            # Create page in Notion
            response = self.notion_client.pages.create(
                parent={"database_id": TRACKS_DB_ID},
                properties=properties
            )

            if response and response.get("id"):
                recording.notion_page_id = response["id"]
                self.stats["synced_to_notion"] += 1
                workspace_logger.info(f"Synced to Notion: {recording.filename}")
                return True

            return False

        except Exception as e:
            workspace_logger.error(f"Error syncing to Notion: {e}")
            return False

    def delete_recording(self, recording: RecordingFile) -> bool:
        """Delete a recording file (move to trash)."""
        try:
            if self.dry_run:
                workspace_logger.info(f"[DRY RUN] Would delete: {recording.filename}")
                return True

            # Use send2trash for safe deletion
            try:
                from send2trash import send2trash
                send2trash(str(recording.path))
            except ImportError:
                # Fallback to os.remove if send2trash not available
                recording.path.unlink()

            self.stats["deleted"] += 1
            workspace_logger.info(f"Deleted: {recording.filename}")
            return True

        except Exception as e:
            workspace_logger.error(f"Error deleting {recording.filename}: {e}")
            return False

    def process_recordings(self) -> Dict[str, int]:
        """Process all scanned recordings based on their classification."""
        workspace_logger.info("Processing recordings...")

        # First, delete duplicate recordings
        if self.duplicates:
            workspace_logger.info(f"Removing {len(self.duplicates)} duplicate recordings...")
            for dup in self.duplicates:
                if self.delete_recording(dup):
                    self.stats["duplicates_removed"] += 1

        # Then process unique recordings
        for recording in self.recordings:
            if recording.status == RecordingStatus.RENAMED_GOOD:
                # Import good recordings to Eagle and Notion
                self.import_to_eagle(recording)
                self.sync_to_notion(recording)

            elif recording.status == RecordingStatus.GENERIC_SHORT:
                # Delete short generic recordings
                self.delete_recording(recording)

            elif recording.status == RecordingStatus.GENERIC_LONG:
                # Log for manual review
                workspace_logger.warning(
                    f"[MANUAL REVIEW] Long generic recording: {recording.filename} "
                    f"({recording.duration_seconds:.1f}s) - not deleted"
                )

        return self.stats

    def generate_report(self) -> str:
        """Generate a summary report of the processing."""
        lines = [
            "",
            "=" * 80,
            "RECORDING MANAGEMENT REPORT",
            "=" * 80,
            f"Timestamp: {datetime.now().isoformat()}",
            f"Dry Run: {self.dry_run}",
            "",
            "SCAN RESULTS:",
            f"  Total files scanned: {self.stats['total_scanned']}",
            f"  Renamed (good) recordings: {self.stats['renamed_good']}",
            f"  Duplicates detected: {self.stats['duplicates_found']}",
            f"  Generic short (< 1 min): {self.stats['generic_short']}",
            f"  Generic long (>= 1 min): {self.stats['generic_long']}",
            "",
            "ACTIONS TAKEN:",
            f"  Imported to Eagle: {self.stats['imported_to_eagle']}",
            f"  Synced to Notion: {self.stats['synced_to_notion']}",
            f"  Duplicates removed: {self.stats['duplicates_removed']}",
            f"  Generic deleted: {self.stats['deleted'] - self.stats['duplicates_removed']}",
            f"  Total deleted: {self.stats['deleted']}",
            f"  Errors: {self.stats['errors']}",
            "",
        ]

        # List duplicates found
        if self.duplicates:
            lines.append("DUPLICATES DETECTED (older copies removed):")
            for r in self.duplicates[:20]:  # Show first 20
                lines.append(f"  - {r.filename} in {r.path.parent.name}")
            if len(self.duplicates) > 20:
                lines.append(f"  ... and {len(self.duplicates) - 20} more")
            lines.append("")

        # List recordings requiring manual review
        review_needed = [r for r in self.recordings if r.status == RecordingStatus.GENERIC_LONG]
        if review_needed:
            lines.append("RECORDINGS REQUIRING MANUAL REVIEW:")
            for r in review_needed:
                dur = f"({r.duration_seconds:.1f}s)" if r.duration_seconds else ""
                lines.append(f"  - {r.filename} {dur}")
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Manage djay Pro / Rekordbox recording files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan and report only (no changes)
  python manage_djay_recordings.py --dry-run

  # Process recordings from default directories
  python manage_djay_recordings.py --execute

  # Process specific directory
  python manage_djay_recordings.py --execute --dir ~/Music/djay/Recordings

  # Skip Eagle import, only sync to Notion
  python manage_djay_recordings.py --execute --skip-eagle
        """
    )

    parser.add_argument(
        "--dir", "-d",
        type=str,
        action="append",
        dest="dirs",
        help="Recording directory to scan (can specify multiple)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report only, don't make any changes"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the full workflow (import, sync, cleanup)"
    )
    parser.add_argument(
        "--skip-eagle",
        action="store_true",
        help="Skip Eagle library import"
    )
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Skip Notion sync"
    )
    parser.add_argument(
        "--skip-delete",
        action="store_true",
        help="Skip deletion of generic short recordings"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--min-duration",
        type=int,
        default=MIN_DURATION_FOR_REVIEW,
        help=f"Minimum duration (seconds) for generic recordings to be protected (default: {MIN_DURATION_FOR_REVIEW})"
    )

    args = parser.parse_args()

    # Determine if we should execute or just scan
    if not args.execute and not args.dry_run:
        workspace_logger.info("No action specified. Use --dry-run to scan or --execute to process.")
        parser.print_help()
        return 1

    # Use provided directories or defaults
    recording_dirs = [Path(d) for d in args.dirs] if args.dirs else DEFAULT_RECORDING_DIRS

    # Use provided min duration
    min_duration = args.min_duration

    workspace_logger.info("=" * 80)
    workspace_logger.info("djay Pro / Rekordbox Recording Manager")
    workspace_logger.info("=" * 80)
    workspace_logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    workspace_logger.info(f"Directories: {[str(d) for d in recording_dirs]}")
    workspace_logger.info(f"Min duration for protection: {min_duration}s")
    workspace_logger.info("=" * 80)

    try:
        manager = RecordingManager(
            recording_dirs=recording_dirs,
            dry_run=args.dry_run or not args.execute,
            skip_eagle=args.skip_eagle,
            skip_notion=args.skip_notion,
            verbose=args.verbose,
            min_duration_for_review=min_duration
        )

        # Scan directories
        manager.scan_directories()

        if not manager.recordings:
            workspace_logger.info("No recording files found.")
            return 0

        # Process recordings (unless skip-delete is set for generic short ones)
        if args.skip_delete:
            # Only process good recordings, skip deletion
            for recording in manager.recordings:
                if recording.status == RecordingStatus.RENAMED_GOOD:
                    manager.import_to_eagle(recording)
                    manager.sync_to_notion(recording)
        else:
            manager.process_recordings()

        # Generate and print report
        report = manager.generate_report()
        print(report)

        return 0

    except KeyboardInterrupt:
        workspace_logger.info("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        workspace_logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
