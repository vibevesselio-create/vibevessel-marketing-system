#!/usr/bin/env python3
"""
Create new directory structure for Dropbox Music reorganization.

This script creates the unified directory structure for the music library
as defined in DROPBOX_MUSIC_CLEANUP_AND_REORGANIZATION_STRATEGY.md.

Usage:
    python3 scripts/create_dropbox_music_structure.py [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base directory for Dropbox Music
BASE_DIR = Path("/Volumes/SYSTEM_SSD/Dropbox/Music")

# Directory structure to create
DIRECTORIES = [
    # Processed files (workflow outputs)
    "processed/playlists/Unassigned",
    "processed/backups/m4a",
    "processed/backups/wav",
    "processed/temp/eagle-import",

    # Legacy files (to be deduplicated)
    "legacy/wav-tracks",
    "legacy/m4a-tracks",

    # User-created content
    "user-content/mixes",
    "user-content/mashups",

    # Metadata and library files
    "metadata/playlists",
    "metadata/spotify",
    "metadata/soundcloud",
    "metadata/djaypro",

    # Archive for migrated content
    "archive",
]


def check_base_directory() -> bool:
    """Check if the base directory is accessible."""
    if not BASE_DIR.exists():
        logger.error(f"Base directory does not exist: {BASE_DIR}")
        logger.error("Make sure the SYSTEM_SSD volume is mounted.")
        return False

    if not BASE_DIR.is_dir():
        logger.error(f"Base path is not a directory: {BASE_DIR}")
        return False

    return True


def create_directories(dry_run: bool = False) -> List[Path]:
    """
    Create the directory structure.

    Args:
        dry_run: If True, only report what would be created

    Returns:
        List of created directories
    """
    created = []
    existing = []

    for dir_path in DIRECTORIES:
        full_path = BASE_DIR / dir_path

        if full_path.exists():
            existing.append(full_path)
            logger.debug(f"Already exists: {full_path}")
        else:
            if dry_run:
                logger.info(f"[DRY RUN] Would create: {full_path}")
            else:
                try:
                    full_path.mkdir(parents=True, exist_ok=True)
                    created.append(full_path)
                    logger.info(f"Created: {full_path}")
                except PermissionError:
                    logger.error(f"Permission denied: {full_path}")
                except Exception as e:
                    logger.error(f"Failed to create {full_path}: {e}")

    return created, existing


def verify_structure() -> bool:
    """Verify that all directories were created successfully."""
    all_exist = True

    for dir_path in DIRECTORIES:
        full_path = BASE_DIR / dir_path
        if not full_path.exists():
            logger.error(f"Missing directory: {full_path}")
            all_exist = False

    return all_exist


def print_summary(created: List[Path], existing: List[Path]):
    """Print a summary of the operation."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("DIRECTORY STRUCTURE CREATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info(f"Directories created: {len(created)}")
    logger.info(f"Directories already existing: {len(existing)}")
    logger.info(f"Total directories: {len(DIRECTORIES)}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Create Dropbox Music directory structure"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be created without making changes"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the directory structure exists"
    )

    args = parser.parse_args()

    logger.info("Dropbox Music Structure Creation Script")
    logger.info("-" * 40)

    # Check base directory
    if not check_base_directory():
        sys.exit(1)

    if args.verify:
        logger.info("Verifying directory structure...")
        if verify_structure():
            logger.info("All directories exist.")
            sys.exit(0)
        else:
            logger.error("Directory structure incomplete.")
            sys.exit(1)

    # Create directories
    created, existing = create_directories(dry_run=args.dry_run)

    # Print summary
    print_summary(created, existing)

    # Verify if not dry run
    if not args.dry_run:
        if verify_structure():
            logger.info("Directory structure verification: PASSED")
        else:
            logger.error("Directory structure verification: FAILED")
            sys.exit(1)

    logger.info("Done.")


if __name__ == "__main__":
    main()
