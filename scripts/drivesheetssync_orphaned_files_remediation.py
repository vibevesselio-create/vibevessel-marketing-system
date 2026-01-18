#!/usr/bin/env python3
"""
DriveSheetsSync Orphaned Files Remediation Script
==================================================

Fixes the 274 orphaned files issue by:
1. Reading the audit data to identify orphaned files (duplicate CSVs, non-standard folders)
2. For duplicate CSV files: Move to .archive folder (preserving version history)
3. For non-standard folders: Report for manual review

This addresses Issue ID: 2d9e7361-6c27-816c-8082-eed7eee579ad
"DriveSheetsSync: 274 Orphaned Files - File Management Issues"

Root Cause: Google Drive auto-renaming when duplicates are created, insufficient deduplication logic.

Author: Claude Code Agent (Opus 4.5)
Created: 2026-01-04
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Paths
AUDIT_DATA_PATH = Path("/Users/brianhellemn/Projects/github-production/DRIVESHEETSSYNC_AUDIT_DATA.json")
WORKSPACE_DATABASES_PATH = Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/notion-workspace-gd/Scripting-and- Automations-ws-sync/workspace-databases")

# Log file
LOG_PATH = Path("/Users/brianhellemn/Projects/github-production/logs")
LOG_PATH.mkdir(parents=True, exist_ok=True)


def load_audit_data() -> Dict:
    """Load the audit data JSON file."""
    with open(AUDIT_DATA_PATH, 'r') as f:
        return json.load(f)


def categorize_orphaned_files(orphaned_files: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Categorize orphaned files by type for targeted remediation.

    Categories:
    - duplicate_csv: CSV files with (1), (2), etc. suffixes
    - non_standard_folder: Folders that don't match the expected pattern
    - other: Files that don't fit other categories
    """
    categories = {
        "duplicate_csv": [],
        "non_standard_folder": [],
        "other": []
    }

    for item in orphaned_files:
        name = item.get("name", "")
        reason = item.get("reason", "")

        if "CSV file in database folder but not main CSV" in reason:
            categories["duplicate_csv"].append(item)
        elif "Folder name doesn't match expected pattern" in reason:
            categories["non_standard_folder"].append(item)
        else:
            categories["other"].append(item)

    return categories


def get_parent_archive_path(file_path: Path) -> Path:
    """Get the .archive folder path for a file's parent directory."""
    return file_path.parent / ".archive"


def remediate_orphaned_files(dry_run: bool = True) -> Dict:
    """
    Main remediation function.

    Strategy:
    1. Duplicate CSV files -> Move to .archive folder with timestamp
    2. Non-standard folders -> Report only (requires manual review)
    3. Other files -> Report only (requires manual review)

    Args:
        dry_run: If True, only report what would be done. If False, perform actions.

    Returns:
        Dictionary with remediation results
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_file = LOG_PATH / f"orphaned_files_remediation_{timestamp}.log"

    results = {
        "timestamp": timestamp,
        "dry_run": dry_run,
        "total_orphaned": 0,
        "duplicate_csvs_found": 0,
        "duplicate_csvs_archived": 0,
        "duplicate_csvs_skipped": 0,
        "non_standard_folders": 0,
        "other_files": 0,
        "errors": [],
        "actions": [],
        "manual_review_required": []
    }

    def log(msg: str):
        print(msg)
        with open(log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")

    log(f"=== DriveSheetsSync Orphaned Files Remediation {'(DRY RUN)' if dry_run else '(LIVE)'} ===")
    log(f"Timestamp: {timestamp}")

    # Load audit data
    try:
        audit_data = load_audit_data()
        log(f"Loaded audit data from {AUDIT_DATA_PATH}")
    except Exception as e:
        log(f"ERROR: Failed to load audit data: {e}")
        results["errors"].append(str(e))
        return results

    # Get orphaned files
    orphaned_files = audit_data.get("structure", {}).get("orphaned_files", [])
    results["total_orphaned"] = len(orphaned_files)
    log(f"Found {len(orphaned_files)} orphaned files in audit data")

    # Categorize orphaned files
    categories = categorize_orphaned_files(orphaned_files)
    log(f"\nCategories:")
    log(f"  - Duplicate CSVs: {len(categories['duplicate_csv'])}")
    log(f"  - Non-standard folders: {len(categories['non_standard_folder'])}")
    log(f"  - Other: {len(categories['other'])}")

    results["duplicate_csvs_found"] = len(categories['duplicate_csv'])
    results["non_standard_folders"] = len(categories['non_standard_folder'])
    results["other_files"] = len(categories['other'])

    # Process duplicate CSV files - move to archive
    log(f"\n{'='*60}")
    log("Processing Duplicate CSV Files")
    log(f"{'='*60}")

    for item in categories['duplicate_csv']:
        file_path = Path(item.get("path", ""))
        file_name = item.get("name", "")
        expected_name = item.get("expected", "")

        log(f"\n--- Processing: {file_name} ---")
        log(f"    Path: {file_path}")
        log(f"    Expected canonical: {expected_name}")

        # Verify file still exists
        if not file_path.exists():
            log(f"    SKIP: File no longer exists")
            results["duplicate_csvs_skipped"] += 1
            continue

        # Get archive path
        archive_folder = get_parent_archive_path(file_path)

        # Create archive folder if it doesn't exist
        if not archive_folder.exists() and not dry_run:
            try:
                archive_folder.mkdir(parents=False, exist_ok=True)
                log(f"    Created archive folder: {archive_folder}")
            except Exception as e:
                log(f"    ERROR: Failed to create archive folder: {e}")
                results["errors"].append(f"Failed to create archive: {e}")
                continue

        # Generate archive filename with timestamp
        archive_filename = f"{file_path.stem}__archived_{timestamp}{file_path.suffix}"
        archive_path = archive_folder / archive_filename

        action = {
            "type": "archive_duplicate_csv",
            "source": str(file_path),
            "destination": str(archive_path),
            "original_name": file_name,
            "expected_canonical": expected_name
        }

        if dry_run:
            log(f"    DRY RUN: Would move to .archive/{archive_filename}")
            action["status"] = "dry_run"
        else:
            try:
                shutil.move(str(file_path), str(archive_path))
                log(f"    SUCCESS: Moved to .archive/{archive_filename}")
                action["status"] = "success"
                results["duplicate_csvs_archived"] += 1
            except Exception as e:
                log(f"    ERROR: Failed to move: {e}")
                action["status"] = "error"
                action["error"] = str(e)
                results["errors"].append(f"Move failed for {file_name}: {e}")

        results["actions"].append(action)

    # Report non-standard folders for manual review
    if categories['non_standard_folder']:
        log(f"\n{'='*60}")
        log("Non-Standard Folders (Manual Review Required)")
        log(f"{'='*60}")

        for item in categories['non_standard_folder']:
            folder_path = item.get("path", "")
            folder_name = item.get("name", "")
            reason = item.get("reason", "")

            log(f"\n  - {folder_name}")
            log(f"    Path: {folder_path}")
            log(f"    Reason: {reason}")

            results["manual_review_required"].append({
                "type": "non_standard_folder",
                "name": folder_name,
                "path": folder_path,
                "reason": reason
            })

    # Report other files for manual review
    if categories['other']:
        log(f"\n{'='*60}")
        log("Other Orphaned Files (Manual Review Required)")
        log(f"{'='*60}")

        for item in categories['other']:
            file_path = item.get("path", "")
            file_name = item.get("name", "")
            reason = item.get("reason", "")

            log(f"\n  - {file_name}")
            log(f"    Path: {file_path}")
            log(f"    Reason: {reason}")

            results["manual_review_required"].append({
                "type": "other",
                "name": file_name,
                "path": file_path,
                "reason": reason
            })

    # Summary
    log(f"\n{'='*60}")
    log("Summary")
    log(f"{'='*60}")
    log(f"Total orphaned files: {results['total_orphaned']}")
    log(f"Duplicate CSVs found: {results['duplicate_csvs_found']}")
    log(f"Duplicate CSVs archived: {results['duplicate_csvs_archived']}")
    log(f"Duplicate CSVs skipped: {results['duplicate_csvs_skipped']}")
    log(f"Non-standard folders (needs review): {results['non_standard_folders']}")
    log(f"Other files (needs review): {results['other_files']}")
    log(f"Errors: {len(results['errors'])}")
    log(f"Log file: {log_file}")

    # Save results
    results_file = LOG_PATH / f"orphaned_files_remediation_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    log(f"Results saved to: {results_file}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix orphaned files in DriveSheetsSync workspace-databases"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually perform the fixes (default is dry-run)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    dry_run = not args.execute

    print(f"\n{'=' * 60}")
    print(f"DriveSheetsSync Orphaned Files Remediation Script")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE EXECUTION'}")
    print(f"{'=' * 60}\n")

    if not dry_run:
        print("WARNING: This will move orphaned files to .archive folders.")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    results = remediate_orphaned_files(dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("Remediation Complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
