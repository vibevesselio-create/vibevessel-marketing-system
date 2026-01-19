#!/usr/bin/env python3
"""Unified export script for Rekordbox, Apple Music, djay Pro, and Notion.

This script orchestrates a complete export and sync operation across all
music library platforms, generating reports and optionally syncing data.

Usage:
    python rekordbox_unified_export.py [options]

Options:
    --dry-run           Don't actually update any databases
    --sync-notion       Push updates to Notion
    --sync-all          Sync all platforms bidirectionally
    --export-csv        Export unified library to CSV
    --validate-only     Only run validation, no sync
    --output-dir DIR    Output directory for reports (default: ./exports)

Environment Variables:
    NOTION_TOKEN        Notion API token
    MUSIC_TRACKS_DB_ID  Notion Music Tracks database ID

Example:
    # Dry run with validation
    python rekordbox_unified_export.py --dry-run --validate-only

    # Full sync to Notion
    python rekordbox_unified_export.py --sync-notion

    # Export to CSV
    python rekordbox_unified_export.py --export-csv --output-dir ~/exports
"""

import os
import sys
import json
import csv
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'unified_export_{datetime.now():%Y%m%d_%H%M%S}.log')
    ]
)
logger = logging.getLogger("unified_export")


def setup_notion_client():
    """Initialize Notion client from environment."""
    try:
        from notion_client import Client
    except ImportError:
        logger.error("notion-client not installed. Run: pip install notion-client")
        return None

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        logger.error("NOTION_TOKEN environment variable not set")
        return None

    return Client(auth=token)


def setup_apple_music_reader():
    """Initialize Apple Music library reader."""
    try:
        from integrations.apple_music import AppleMusicLibraryReader
        return AppleMusicLibraryReader()
    except Exception as e:
        logger.warning(f"Could not initialize Apple Music reader: {e}")
        return None


def setup_rekordbox_reader():
    """Initialize Rekordbox database reader."""
    try:
        from integrations.rekordbox import RekordboxDbReader
        return RekordboxDbReader()
    except Exception as e:
        logger.warning(f"Could not initialize Rekordbox reader: {e}")
        return None


def setup_djay_pro_reader():
    """Initialize djay Pro database reader."""
    try:
        from integrations.djay_pro import DjayProDbReader
        return DjayProDbReader()
    except Exception as e:
        logger.warning(f"Could not initialize djay Pro reader: {e}")
        return None


def export_to_csv(unified_tracks, output_path: Path):
    """Export unified tracks to CSV.

    Args:
        unified_tracks: List of UnifiedTrackMatch objects
        output_path: Output file path
    """
    logger.info(f"Exporting {len(unified_tracks)} tracks to CSV...")

    fieldnames = [
        "match_id",
        "title",
        "artist",
        "album",
        "bpm",
        "key",
        "file_path",
        "platforms",
        "notion_page_id",
        "apple_music_id",
        "rekordbox_id",
        "djay_pro_id",
        "confidence_score",
        "has_conflicts",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for track in unified_tracks:
            row = {
                "match_id": track.match_id,
                "title": track.canonical_title,
                "artist": track.canonical_artist,
                "album": track.canonical_album,
                "bpm": track.canonical_bpm,
                "key": track.canonical_key,
                "file_path": track.file_path,
                "platforms": ",".join(sorted(track.platforms)),
                "notion_page_id": track.notion_page_id,
                "apple_music_id": track.platform_refs.get("apple_music", {}).platform_id
                    if "apple_music" in track.platform_refs else "",
                "rekordbox_id": track.platform_refs.get("rekordbox", {}).platform_id
                    if "rekordbox" in track.platform_refs else "",
                "djay_pro_id": track.platform_refs.get("djay_pro", {}).platform_id
                    if "djay_pro" in track.platform_refs else "",
                "confidence_score": f"{track.confidence_score:.2f}",
                "has_conflicts": "yes" if track.has_conflicts else "no",
            }
            writer.writerow(row)

    logger.info(f"Exported to {output_path}")


def export_conflicts_report(unified_tracks, output_path: Path):
    """Export conflicts to JSON report.

    Args:
        unified_tracks: List of UnifiedTrackMatch objects
        output_path: Output file path
    """
    conflicts = []

    for track in unified_tracks:
        if track.has_conflicts:
            conflicts.append({
                "match_id": track.match_id,
                "title": track.canonical_title,
                "artist": track.canonical_artist,
                "platforms": list(track.platforms),
                "conflicts": track.conflicts,
            })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_conflicts": len(conflicts),
            "conflicts": conflicts,
        }, f, indent=2)

    logger.info(f"Exported {len(conflicts)} conflicts to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Unified music library export and sync"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update any databases"
    )
    parser.add_argument(
        "--sync-notion",
        action="store_true",
        help="Push updates to Notion"
    )
    parser.add_argument(
        "--sync-all",
        action="store_true",
        help="Sync all platforms bidirectionally"
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Export unified library to CSV"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only run validation, no sync"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./exports",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("UNIFIED MUSIC LIBRARY EXPORT")
    logger.info("=" * 60)
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Output Directory: {output_dir}")

    # Setup clients and readers
    notion = setup_notion_client()
    db_id = os.environ.get("MUSIC_TRACKS_DB_ID")

    if not notion or not db_id:
        logger.error("Notion client or database ID not configured")
        sys.exit(1)

    apple_music_reader = setup_apple_music_reader()
    rekordbox_reader = setup_rekordbox_reader()
    djay_pro_reader = setup_djay_pro_reader()

    # Import orchestrator
    try:
        from integrations.unified_sync import (
            UnifiedLibrarySync,
            LibraryValidator,
        )
    except ImportError as e:
        logger.error(f"Could not import unified_sync module: {e}")
        sys.exit(1)

    # Initialize orchestrator
    sync = UnifiedLibrarySync(
        notion_client=notion,
        music_tracks_db_id=db_id,
        apple_music_reader=apple_music_reader,
        rekordbox_reader=rekordbox_reader,
        djay_pro_reader=djay_pro_reader,
    )

    # Load all libraries
    logger.info("Loading libraries...")
    sync.load_all_libraries()

    # Build unified index
    logger.info("Building unified track index...")
    unified_tracks = sync.matcher.build_unified_index()

    logger.info(f"Found {len(unified_tracks)} unique tracks across all platforms")

    # Validation
    if args.validate_only or True:  # Always validate
        logger.info("Running validation...")
        validator = LibraryValidator(sync.matcher)
        validation_report = validator.full_validation()

        # Save validation report
        validation_path = output_dir / f"validation_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(validation_path, "w", encoding="utf-8") as f:
            json.dump(validation_report.to_dict(), f, indent=2)

        logger.info(validation_report.summary())
        logger.info(f"Validation report saved to {validation_path}")

        if args.validate_only:
            logger.info("Validation complete. Exiting.")
            return

    # Export to CSV
    if args.export_csv:
        csv_path = output_dir / f"unified_library_{datetime.now():%Y%m%d_%H%M%S}.csv"
        export_to_csv(unified_tracks, csv_path)

        # Also export conflicts
        conflicts_path = output_dir / f"conflicts_{datetime.now():%Y%m%d_%H%M%S}.json"
        export_conflicts_report(unified_tracks, conflicts_path)

    # Sync operations
    if args.sync_notion or args.sync_all:
        logger.info("Starting sync operation...")

        report = sync.full_sync(
            dry_run=args.dry_run,
            sync_to_notion=True,
            sync_to_rekordbox=args.sync_all,
            sync_to_djay=args.sync_all,
            sync_to_apple_music=args.sync_all,
        )

        # Save sync report
        report_path = output_dir / f"sync_report_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info(report.summary())
        logger.info(f"Sync report saved to {report_path}")

    # Summary
    logger.info("=" * 60)
    logger.info("EXPORT COMPLETE")
    logger.info("=" * 60)

    stats = sync.matcher.get_statistics()
    logger.info(f"Total unified tracks: {stats['total_unified_tracks']}")
    logger.info(f"All platforms: {stats['all_platforms']}")
    logger.info(f"Multi-platform: {stats['multi_platform']}")
    logger.info(f"Single platform: {stats['single_platform']}")
    logger.info(f"With conflicts: {stats['with_conflicts']}")


if __name__ == "__main__":
    main()
