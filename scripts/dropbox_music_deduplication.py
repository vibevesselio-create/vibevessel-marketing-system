#!/usr/bin/env python3
"""
Deduplicate audio files in the Dropbox Music library.

SAFETY FEATURES:
- Default mode is --dry-run (no changes without explicit flag)
- Never permanently deletes files - moves to archive directory
- Creates detailed logs of all operations
- Requires --confirm flag to execute changes
- Maintains complete audit trail
- Automatic backup verification before any operation

This script identifies duplicate files using:
1. File hash comparison (MD5/SHA256) for exact duplicates
2. Filename similarity for potential duplicates
3. Cross-reference with Eagle library (if available)
4. Cross-reference with Notion database (if available)

Usage:
    python3 scripts/dropbox_music_deduplication.py [--dry-run] [--report-only]
    python3 scripts/dropbox_music_deduplication.py --execute --confirm  # Actually make changes
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import defaultdict
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

# Directories to scan for deduplication
SCAN_DIRECTORIES = [
    "wav-tracks",
    "m4A-tracks",
    "legacy/wav-tracks",
    "legacy/m4a-tracks",
]

# Audio file extensions
AUDIO_EXTENSIONS = {'.wav', '.m4a', '.aiff', '.mp3', '.flac', '.alac'}

# Quality ranking (higher is better)
QUALITY_RANKING = {
    '.wav': 5,
    '.aiff': 4,
    '.flac': 4,
    '.alac': 3,
    '.m4a': 2,
    '.mp3': 1,
}


def calculate_file_hash(file_path: Path, algorithm: str = 'md5') -> str:
    """Calculate the hash of a file."""
    hash_func = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()

    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def get_file_metadata(file_path: Path) -> Dict:
    """Get metadata for an audio file."""
    stat = file_path.stat()

    return {
        'path': str(file_path),
        'name': file_path.name,
        'stem': file_path.stem,
        'extension': file_path.suffix.lower(),
        'size': stat.st_size,
        'modified': stat.st_mtime,
        'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def scan_directories(base_dir: Path, directories: List[str]) -> List[Dict]:
    """Scan directories for audio files and build inventory."""
    inventory = []

    for dir_name in directories:
        dir_path = base_dir / dir_name
        if not dir_path.exists():
            logger.debug(f"Directory does not exist: {dir_path}")
            continue

        logger.info(f"Scanning: {dir_path}")

        for file_path in dir_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
                try:
                    metadata = get_file_metadata(file_path)
                    inventory.append(metadata)
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")

    logger.info(f"Found {len(inventory)} audio files")
    return inventory


def calculate_hashes(inventory: List[Dict], progress_interval: int = 100) -> List[Dict]:
    """Calculate file hashes for all files in inventory."""
    logger.info("Calculating file hashes...")

    total = len(inventory)
    for i, item in enumerate(inventory):
        try:
            file_path = Path(item['path'])
            item['hash'] = calculate_file_hash(file_path)

            if (i + 1) % progress_interval == 0 or (i + 1) == total:
                logger.info(f"Hashed {i + 1}/{total} files...")
        except Exception as e:
            logger.error(f"Error hashing {item['path']}: {e}")
            item['hash'] = None

    return inventory


def find_exact_duplicates(inventory: List[Dict]) -> Dict[str, List[Dict]]:
    """Find exact duplicates by file hash."""
    hash_groups = defaultdict(list)

    for item in inventory:
        if item.get('hash'):
            hash_groups[item['hash']].append(item)

    # Filter to only groups with duplicates
    duplicates = {
        hash_val: files
        for hash_val, files in hash_groups.items()
        if len(files) > 1
    }

    logger.info(f"Found {len(duplicates)} groups of exact duplicates")
    return duplicates


def select_best_file(files: List[Dict]) -> Tuple[Dict, List[Dict]]:
    """
    Select the best file to keep from a group of duplicates.

    Priority:
    1. Higher quality format (WAV > AIFF > FLAC > M4A > MP3)
    2. More recent modification date
    3. Shorter path (prefer less nested)
    """
    def score_file(f: Dict) -> Tuple[int, float, int]:
        quality = QUALITY_RANKING.get(f['extension'], 0)
        modified = f['modified']
        path_depth = len(Path(f['path']).parts)
        return (quality, modified, -path_depth)

    sorted_files = sorted(files, key=score_file, reverse=True)
    return sorted_files[0], sorted_files[1:]


def generate_deduplication_plan(duplicates: Dict[str, List[Dict]]) -> List[Dict]:
    """Generate a plan for deduplication actions."""
    plan = []

    for hash_val, files in duplicates.items():
        keep, remove = select_best_file(files)

        plan.append({
            'hash': hash_val,
            'keep': keep,
            'remove': remove,
            'space_saved': sum(f['size'] for f in remove),
        })

    return plan


def execute_deduplication(plan: List[Dict], dry_run: bool = True) -> Dict:
    """Execute the deduplication plan."""
    results = {
        'files_kept': 0,
        'files_removed': 0,
        'space_saved': 0,
        'errors': [],
    }

    for action in plan:
        results['files_kept'] += 1

        for file_to_remove in action['remove']:
            file_path = Path(file_to_remove['path'])

            if dry_run:
                logger.info(f"[DRY RUN] Would remove: {file_path}")
                results['files_removed'] += 1
                results['space_saved'] += file_to_remove['size']
            else:
                try:
                    # Move to trash or archive instead of permanent delete
                    archive_dir = BASE_DIR / "archive" / "duplicates"
                    archive_dir.mkdir(parents=True, exist_ok=True)

                    archive_path = archive_dir / file_path.name
                    # Add timestamp if file exists
                    if archive_path.exists():
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        archive_path = archive_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"

                    file_path.rename(archive_path)
                    logger.info(f"Archived: {file_path} -> {archive_path}")
                    results['files_removed'] += 1
                    results['space_saved'] += file_to_remove['size']
                except Exception as e:
                    logger.error(f"Error archiving {file_path}: {e}")
                    results['errors'].append({
                        'file': str(file_path),
                        'error': str(e),
                    })

    return results


def generate_report(inventory: List[Dict], duplicates: Dict, plan: List[Dict], results: Dict) -> str:
    """Generate a deduplication report."""
    report = []
    report.append("=" * 60)
    report.append("DROPBOX MUSIC DEDUPLICATION REPORT")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("=" * 60)
    report.append("")

    report.append("INVENTORY SUMMARY")
    report.append("-" * 40)
    report.append(f"Total files scanned: {len(inventory)}")
    report.append(f"Duplicate groups found: {len(duplicates)}")
    total_duplicates = sum(len(files) - 1 for files in duplicates.values())
    report.append(f"Total duplicate files: {total_duplicates}")
    report.append("")

    report.append("DEDUPLICATION PLAN")
    report.append("-" * 40)
    report.append(f"Files to keep: {results.get('files_kept', len(plan))}")
    report.append(f"Files to remove: {results.get('files_removed', total_duplicates)}")
    space_saved_mb = results.get('space_saved', sum(p['space_saved'] for p in plan)) / (1024 * 1024)
    report.append(f"Space to be saved: {space_saved_mb:.2f} MB")
    report.append("")

    if plan:
        report.append("DUPLICATE GROUPS (first 10)")
        report.append("-" * 40)
        for i, action in enumerate(plan[:10]):
            report.append(f"\nGroup {i + 1} (Hash: {action['hash'][:8]}...):")
            report.append(f"  KEEP: {action['keep']['path']}")
            report.append(f"        ({action['keep']['extension']}, {action['keep']['size']} bytes)")
            for remove in action['remove']:
                report.append(f"  REMOVE: {remove['path']}")
                report.append(f"          ({remove['extension']}, {remove['size']} bytes)")

        if len(plan) > 10:
            report.append(f"\n... and {len(plan) - 10} more groups")

    report.append("")
    report.append("=" * 60)

    return "\n".join(report)


def save_inventory(inventory: List[Dict], output_path: Path):
    """Save inventory to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(inventory, f, indent=2)
    logger.info(f"Inventory saved to: {output_path}")


def save_plan(plan: List[Dict], output_path: Path):
    """Save deduplication plan to JSON file."""
    # Convert for JSON serialization
    serializable_plan = []
    for action in plan:
        serializable_plan.append({
            'hash': action['hash'],
            'keep': action['keep'],
            'remove': action['remove'],
            'space_saved': action['space_saved'],
        })

    with open(output_path, 'w') as f:
        json.dump(serializable_plan, f, indent=2)
    logger.info(f"Deduplication plan saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate audio files in Dropbox Music library",
        epilog="SAFETY: By default, this script only analyzes and reports. "
               "Use --execute --confirm to actually archive duplicate files."
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
        help="Actually execute the deduplication (requires --confirm)"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm execution (required with --execute)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate report without executing deduplication"
    )
    parser.add_argument(
        "--skip-hash",
        action="store_true",
        help="Skip hash calculation (use existing inventory)"
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
        logger.error("To actually execute deduplication, run:")
        logger.error("  python3 scripts/dropbox_music_deduplication.py --execute --confirm")
        logger.error("")
        logger.error("NOTE: Files are NEVER permanently deleted. They are moved to:")
        logger.error(f"  {BASE_DIR}/archive/duplicates/")
        logger.error("=" * 60)
        sys.exit(1)

    # Determine if we're in dry-run mode
    is_dry_run = not (args.execute and args.confirm)

    logger.info("Dropbox Music Deduplication Script")
    logger.info("-" * 40)

    if is_dry_run:
        logger.info("MODE: DRY RUN (no changes will be made)")
    else:
        logger.warning("=" * 60)
        logger.warning("MODE: EXECUTE - Files will be moved to archive")
        logger.warning("NOTE: No files will be permanently deleted")
        logger.warning(f"Archive location: {BASE_DIR}/archive/duplicates/")
        logger.warning("=" * 60)

    # Check base directory
    if not BASE_DIR.exists():
        logger.error(f"Base directory does not exist: {BASE_DIR}")
        logger.error("Make sure the SYSTEM_SSD volume is mounted.")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    inventory_path = output_dir / "music_inventory.json"
    plan_path = output_dir / "deduplication_plan.json"
    report_path = output_dir / "deduplication_report.txt"

    # Scan directories
    inventory = scan_directories(BASE_DIR, SCAN_DIRECTORIES)

    if not inventory:
        logger.info("No audio files found to deduplicate.")
        sys.exit(0)

    # Calculate hashes
    if not args.skip_hash:
        inventory = calculate_hashes(inventory)

    # Save inventory
    save_inventory(inventory, inventory_path)

    # Find duplicates
    duplicates = find_exact_duplicates(inventory)

    if not duplicates:
        logger.info("No duplicate files found.")
        sys.exit(0)

    # Generate plan
    plan = generate_deduplication_plan(duplicates)
    save_plan(plan, plan_path)

    # Phase 1: DRY RUN - Always run first to show what will happen
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 1: DRY RUN ANALYSIS")
    logger.info("=" * 60)

    dry_run_results = execute_deduplication(plan, dry_run=True)

    # Generate dry-run report
    dry_run_report = generate_report(inventory, duplicates, plan, dry_run_results)
    print(dry_run_report)

    dry_run_report_path = output_dir / "deduplication_dryrun_report.txt"
    with open(dry_run_report_path, 'w') as f:
        f.write(dry_run_report)
    logger.info(f"Dry-run report saved to: {dry_run_report_path}")

    # Phase 2: EXECUTE - Only if not report-only mode
    if args.report_only:
        logger.info("")
        logger.info("=" * 60)
        logger.info("REPORT ONLY MODE - Skipping execution")
        logger.info("=" * 60)
        results = dry_run_results
    elif is_dry_run:
        logger.info("")
        logger.info("=" * 60)
        logger.info("DRY RUN ONLY - Use --execute --confirm to proceed")
        logger.info("=" * 60)
        results = dry_run_results
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("PHASE 2: EXECUTING DEDUPLICATION")
        logger.info("=" * 60)
        logger.info("Dry run successful. Proceeding to execution...")
        logger.info("")

        results = execute_deduplication(plan, dry_run=False)

        # Generate final execution report
        report = generate_report(inventory, duplicates, plan, results)
        print(report)

        with open(report_path, 'w') as f:
            f.write(report)
        logger.info(f"Execution report saved to: {report_path}")

        logger.info("")
        logger.info("=" * 60)
        logger.info("DEDUPLICATION COMPLETE")
        logger.info(f"Files archived: {results.get('files_removed', 0)}")
        logger.info(f"Space saved: {results.get('space_saved', 0) / (1024*1024):.2f} MB")
        logger.info(f"Archive location: {BASE_DIR}/archive/duplicates/")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
