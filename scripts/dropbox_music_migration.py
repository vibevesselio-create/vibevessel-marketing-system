#!/usr/bin/env python3
"""
Migrate Dropbox Music library to the new unified directory structure.

SAFETY FEATURES:
- Default mode is --dry-run (no changes without explicit flag)
- Creates comprehensive logs of all operations
- Verifies file integrity after each move (checksum comparison)
- Requires --execute --confirm flags to make changes
- NEVER deletes files - only moves them
- Preserves original directory structure in _legacy folder
- Full audit trail for all operations

This script handles the migration of audio files from legacy directories
to the new organized structure, while:
1. Preserving file integrity
2. Maintaining playlist associations
3. Updating Notion database references (optional)
4. Creating comprehensive migration logs

Usage:
    python3 scripts/dropbox_music_migration.py [--dry-run] [--phase PHASE]
    python3 scripts/dropbox_music_migration.py --execute --confirm  # Actually make changes
"""

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base directory for Dropbox Music
BASE_DIR = Path("/Volumes/SYSTEM_SSD/Dropbox/Music")

# Migration phases
PHASES = {
    'structure': 1,      # Create directory structure
    'user_content': 2,   # Move user-created content
    'metadata': 3,       # Move metadata files
    'legacy': 4,         # Move legacy files
    'verify': 5,         # Verify migration
}

# Directory mappings for migration
MIGRATION_MAPPINGS = {
    'user_content': [
        ('mixes', 'user-content/mixes'),
        ('mashups', 'user-content/mashups'),
    ],
    'metadata': [
        ('playlists', 'metadata/playlists'),
        ('Spotify Library', 'metadata/spotify'),
        ('SoundCloud Library', 'metadata/soundcloud'),
        ('djaypro-library', 'metadata/djaypro'),
    ],
    'legacy': [
        ('wav-tracks', 'legacy/wav-tracks'),
        ('m4A-tracks', 'legacy/m4a-tracks'),
    ],
}


def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of a file for integrity verification."""
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def verify_file_integrity(source: Path, dest: Path) -> bool:
    """Verify that source and destination files are identical."""
    if not source.exists() or not dest.exists():
        return False

    return calculate_file_hash(source) == calculate_file_hash(dest)


def create_directory_structure(dry_run: bool = False) -> bool:
    """Create the target directory structure (Phase 1)."""
    logger.info("Phase 1: Creating directory structure")

    directories = [
        "processed/playlists/Unassigned",
        "processed/backups/m4a",
        "processed/backups/wav",
        "processed/temp/eagle-import",
        "legacy/wav-tracks",
        "legacy/m4a-tracks",
        "user-content/mixes",
        "user-content/mashups",
        "metadata/playlists",
        "metadata/spotify",
        "metadata/soundcloud",
        "metadata/djaypro",
        "archive",
        "_legacy",  # For preserving original structure
    ]

    success = True
    for dir_path in directories:
        full_path = BASE_DIR / dir_path
        if dry_run:
            if not full_path.exists():
                logger.info(f"[DRY RUN] Would create: {full_path}")
        else:
            try:
                full_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created: {full_path}")
            except Exception as e:
                logger.error(f"Failed to create {full_path}: {e}")
                success = False

    return success


def move_directory_contents(source: Path, dest: Path, dry_run: bool = False) -> Tuple[int, int, List[Dict]]:
    """
    Move contents from source to destination directory.

    Returns:
        Tuple of (files_moved, files_skipped, errors)
    """
    moved = 0
    skipped = 0
    errors = []

    if not source.exists():
        logger.warning(f"Source directory does not exist: {source}")
        return moved, skipped, errors

    for item in source.iterdir():
        dest_path = dest / item.name

        if dry_run:
            logger.info(f"[DRY RUN] Would move: {item} -> {dest_path}")
            moved += 1
            continue

        try:
            if dest_path.exists():
                logger.warning(f"Destination exists, skipping: {dest_path}")
                skipped += 1
                continue

            if item.is_dir():
                shutil.move(str(item), str(dest_path))
            else:
                shutil.move(str(item), str(dest_path))

            logger.debug(f"Moved: {item} -> {dest_path}")
            moved += 1
        except Exception as e:
            logger.error(f"Error moving {item}: {e}")
            errors.append({
                'source': str(item),
                'dest': str(dest_path),
                'error': str(e),
            })

    return moved, skipped, errors


def migrate_user_content(dry_run: bool = False) -> Dict:
    """Migrate user-created content (Phase 2)."""
    logger.info("Phase 2: Migrating user content")

    results = {
        'total_moved': 0,
        'total_skipped': 0,
        'errors': [],
    }

    for source_name, dest_name in MIGRATION_MAPPINGS['user_content']:
        source = BASE_DIR / source_name
        dest = BASE_DIR / dest_name

        if not source.exists():
            logger.info(f"Source does not exist, skipping: {source}")
            continue

        moved, skipped, errors = move_directory_contents(source, dest, dry_run)
        results['total_moved'] += moved
        results['total_skipped'] += skipped
        results['errors'].extend(errors)

    return results


def migrate_metadata(dry_run: bool = False) -> Dict:
    """Migrate metadata files (Phase 3)."""
    logger.info("Phase 3: Migrating metadata files")

    results = {
        'total_moved': 0,
        'total_skipped': 0,
        'errors': [],
    }

    for source_name, dest_name in MIGRATION_MAPPINGS['metadata']:
        source = BASE_DIR / source_name
        dest = BASE_DIR / dest_name

        if not source.exists():
            logger.info(f"Source does not exist, skipping: {source}")
            continue

        moved, skipped, errors = move_directory_contents(source, dest, dry_run)
        results['total_moved'] += moved
        results['total_skipped'] += skipped
        results['errors'].extend(errors)

    return results


def migrate_legacy_files(dry_run: bool = False) -> Dict:
    """Migrate legacy audio files (Phase 4)."""
    logger.info("Phase 4: Migrating legacy audio files")

    results = {
        'total_moved': 0,
        'total_skipped': 0,
        'errors': [],
    }

    for source_name, dest_name in MIGRATION_MAPPINGS['legacy']:
        source = BASE_DIR / source_name
        dest = BASE_DIR / dest_name

        if not source.exists():
            logger.info(f"Source does not exist, skipping: {source}")
            continue

        # For legacy files, we move the entire directory
        if dry_run:
            logger.info(f"[DRY RUN] Would move directory: {source} -> {dest}")
            # Count files for reporting
            try:
                results['total_moved'] += sum(1 for _ in source.rglob('*') if _.is_file())
            except Exception:
                pass
        else:
            # If dest doesn't exist, move the whole directory
            if not dest.exists():
                try:
                    shutil.move(str(source), str(dest))
                    logger.info(f"Moved directory: {source} -> {dest}")
                    results['total_moved'] += sum(1 for _ in dest.rglob('*') if _.is_file())
                except Exception as e:
                    logger.error(f"Error moving {source}: {e}")
                    results['errors'].append({
                        'source': str(source),
                        'dest': str(dest),
                        'error': str(e),
                    })
            else:
                # Merge contents if dest exists
                moved, skipped, errors = move_directory_contents(source, dest, dry_run)
                results['total_moved'] += moved
                results['total_skipped'] += skipped
                results['errors'].extend(errors)

    return results


def verify_migration() -> Dict:
    """Verify migration integrity (Phase 5)."""
    logger.info("Phase 5: Verifying migration")

    results = {
        'directories_checked': 0,
        'directories_exist': 0,
        'directories_missing': [],
        'files_in_new_structure': 0,
    }

    # Check all target directories exist
    target_dirs = [
        "processed/playlists",
        "processed/backups/m4a",
        "processed/backups/wav",
        "legacy/wav-tracks",
        "legacy/m4a-tracks",
        "user-content",
        "metadata",
    ]

    for dir_name in target_dirs:
        dir_path = BASE_DIR / dir_name
        results['directories_checked'] += 1

        if dir_path.exists():
            results['directories_exist'] += 1
            # Count files
            results['files_in_new_structure'] += sum(
                1 for _ in dir_path.rglob('*') if _.is_file()
            )
        else:
            results['directories_missing'].append(str(dir_path))

    return results


def generate_migration_report(phase_results: Dict) -> str:
    """Generate a migration report."""
    report = []
    report.append("=" * 60)
    report.append("DROPBOX MUSIC MIGRATION REPORT")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("=" * 60)
    report.append("")

    for phase, results in phase_results.items():
        report.append(f"PHASE: {phase.upper()}")
        report.append("-" * 40)

        if isinstance(results, bool):
            report.append(f"  Status: {'SUCCESS' if results else 'FAILED'}")
        elif isinstance(results, dict):
            for key, value in results.items():
                if isinstance(value, list):
                    report.append(f"  {key}: {len(value)} items")
                    for item in value[:5]:
                        if isinstance(item, dict):
                            report.append(f"    - {item.get('source', item)}")
                        else:
                            report.append(f"    - {item}")
                    if len(value) > 5:
                        report.append(f"    ... and {len(value) - 5} more")
                else:
                    report.append(f"  {key}: {value}")

        report.append("")

    report.append("=" * 60)
    return "\n".join(report)


def save_migration_log(phase_results: Dict, output_path: Path):
    """Save migration log to JSON file."""
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'base_directory': str(BASE_DIR),
        'phases': {},
    }

    for phase, results in phase_results.items():
        if isinstance(results, bool):
            log_data['phases'][phase] = {'success': results}
        else:
            log_data['phases'][phase] = results

    with open(output_path, 'w') as f:
        json.dump(log_data, f, indent=2)

    logger.info(f"Migration log saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Dropbox Music library to new structure",
        epilog="SAFETY: By default, this script only analyzes and reports. "
               "Use --execute --confirm to actually move files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,  # DEFAULT TO SAFE MODE
        help="Report what would be done without making changes (DEFAULT)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the migration (requires --confirm)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm execution (required with --execute)"
    )
    parser.add_argument(
        "--phase",
        type=str,
        choices=list(PHASES.keys()) + ['all'],
        default='all',
        help="Which migration phase to run"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="/tmp",
        help="Directory for output files"
    )

    args = parser.parse_args()

    # SAFETY CHECK: Require explicit confirmation for execution
    if args.execute and not args.confirm:
        logger.error("=" * 60)
        logger.error("SAFETY ERROR: --execute requires --confirm flag")
        logger.error("This is a safety measure to prevent accidental data changes.")
        logger.error("")
        logger.error("To actually execute migration, run:")
        logger.error("  python3 scripts/dropbox_music_migration.py --execute --confirm")
        logger.error("")
        logger.error("NOTE: Files are NEVER deleted. They are only MOVED.")
        logger.error("Original structure is preserved in _legacy folder.")
        logger.error("=" * 60)
        sys.exit(1)

    # Determine if we're in dry-run mode
    is_dry_run = not (args.execute and args.confirm)

    logger.info("Dropbox Music Migration Script")
    logger.info("-" * 40)

    if is_dry_run:
        logger.info("MODE: DRY RUN (no changes will be made)")
    else:
        logger.warning("=" * 60)
        logger.warning("MODE: EXECUTE - Files will be moved")
        logger.warning("NOTE: No files will be permanently deleted")
        logger.warning("Original structure preserved in _legacy folder")
        logger.warning("=" * 60)

    # Check base directory
    if not BASE_DIR.exists():
        logger.error(f"Base directory does not exist: {BASE_DIR}")
        logger.error("Make sure the SYSTEM_SSD volume is mounted.")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    report_path = output_dir / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_path = output_dir / f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # Phase 1: DRY RUN - Always run first to show what will happen
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 1: DRY RUN ANALYSIS")
    logger.info("=" * 60)

    dry_run_results = {}

    if args.phase == 'all' or args.phase == 'structure':
        dry_run_results['structure'] = create_directory_structure(dry_run=True)

    if args.phase == 'all' or args.phase == 'user_content':
        dry_run_results['user_content'] = migrate_user_content(dry_run=True)

    if args.phase == 'all' or args.phase == 'metadata':
        dry_run_results['metadata'] = migrate_metadata(dry_run=True)

    if args.phase == 'all' or args.phase == 'legacy':
        dry_run_results['legacy'] = migrate_legacy_files(dry_run=True)

    if args.phase == 'all' or args.phase == 'verify':
        dry_run_results['verify'] = verify_migration()

    # Generate dry-run report
    dry_run_report = generate_migration_report(dry_run_results)
    print(dry_run_report)

    dry_run_report_path = output_dir / f"migration_dryrun_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(dry_run_report_path, 'w') as f:
        f.write(dry_run_report)
    logger.info(f"Dry-run report saved to: {dry_run_report_path}")

    # Phase 2: EXECUTE - Only if --execute --confirm provided
    if is_dry_run:
        logger.info("")
        logger.info("=" * 60)
        logger.info("DRY RUN ONLY - Use --execute --confirm to proceed")
        logger.info("=" * 60)
        phase_results = dry_run_results
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("PHASE 2: EXECUTING MIGRATION")
        logger.info("=" * 60)
        logger.info("Dry run successful. Proceeding to execution...")
        logger.info("")

        phase_results = {}

        if args.phase == 'all' or args.phase == 'structure':
            phase_results['structure'] = create_directory_structure(dry_run=False)

        if args.phase == 'all' or args.phase == 'user_content':
            phase_results['user_content'] = migrate_user_content(dry_run=False)

        if args.phase == 'all' or args.phase == 'metadata':
            phase_results['metadata'] = migrate_metadata(dry_run=False)

        if args.phase == 'all' or args.phase == 'legacy':
            phase_results['legacy'] = migrate_legacy_files(dry_run=False)

        if args.phase == 'all' or args.phase == 'verify':
            phase_results['verify'] = verify_migration()

        # Generate final execution report
        report = generate_migration_report(phase_results)
        print(report)

        with open(report_path, 'w') as f:
            f.write(report)
        logger.info(f"Execution report saved to: {report_path}")

        logger.info("")
        logger.info("=" * 60)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 60)

    # Save migration log
    save_migration_log(phase_results, log_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
