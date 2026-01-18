#!/usr/bin/env python3
"""
DriveSheetsSync Archive Folder Remediation Script
==================================================

Fixes the 103 missing .archive folders issue by:
1. Reading the audit data to identify folders without .archive
2. Creating the missing .archive folders directly

This addresses Issue ID: 2d9e7361-6c27-81f4-8528-d98b9e755c2c
"DriveSheetsSync: 101 Missing Archive Folders - No Version History"

Author: Claude Code Agent (Opus 4.5)
Created: 2026-01-04
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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


def find_missing_archive_databases(audit_data: Dict) -> List[Dict]:
    """Find all databases where has_archive is false."""
    missing = []
    for db_id, db_info in audit_data.get("structure", {}).get("databases", {}).items():
        if not db_info.get("has_archive", True):
            db_info["db_id"] = db_id
            missing.append(db_info)
    return missing


def remediate_missing_archives(dry_run: bool = True) -> Dict:
    """
    Main remediation function.

    Args:
        dry_run: If True, only report what would be done. If False, perform actions.

    Returns:
        Dictionary with remediation results
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_file = LOG_PATH / f"archive_remediation_{timestamp}.log"

    results = {
        "timestamp": timestamp,
        "dry_run": dry_run,
        "databases_analyzed": 0,
        "archives_created": 0,
        "archives_skipped": 0,
        "errors": [],
        "actions": []
    }

    def log(msg: str):
        print(msg)
        with open(log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")

    log(f"=== DriveSheetsSync Archive Remediation {'(DRY RUN)' if dry_run else '(LIVE)'} ===")
    log(f"Timestamp: {timestamp}")

    # Load audit data
    try:
        audit_data = load_audit_data()
        log(f"Loaded audit data from {AUDIT_DATA_PATH}")
    except Exception as e:
        log(f"ERROR: Failed to load audit data: {e}")
        results["errors"].append(str(e))
        return results

    # Find databases with missing archives
    missing_archive_dbs = find_missing_archive_databases(audit_data)
    log(f"Audit shows {len(missing_archive_dbs)} databases with missing .archive folders")

    for db_info in missing_archive_dbs:
        results["databases_analyzed"] += 1

        folder_path = Path(db_info.get("path", ""))
        folder_name = db_info.get("name", "")
        archive_path = folder_path / ".archive"

        log(f"\n--- Processing: {folder_name} ---")
        log(f"    Path: {folder_path}")

        # Verify the folder exists
        if not folder_path.exists():
            log(f"    SKIP: Folder does not exist (may have been deleted)")
            results["archives_skipped"] += 1
            results["actions"].append({
                "folder_name": folder_name,
                "status": "skipped",
                "reason": "folder_not_found"
            })
            continue

        # Check if .archive already exists (audit data might be stale)
        if archive_path.exists():
            log(f"    SKIP: .archive folder already exists")
            results["archives_skipped"] += 1
            results["actions"].append({
                "folder_name": folder_name,
                "status": "skipped",
                "reason": "already_exists"
            })
            continue

        action = {
            "folder_name": folder_name,
            "archive_path": str(archive_path)
        }

        if dry_run:
            log(f"    DRY RUN: Would create .archive folder")
            action["status"] = "dry_run"
        else:
            try:
                archive_path.mkdir(parents=False, exist_ok=False)
                log(f"    SUCCESS: Created .archive folder")
                action["status"] = "success"
                results["archives_created"] += 1
            except FileExistsError:
                log(f"    SKIP: .archive already exists (race condition)")
                action["status"] = "skipped"
                action["reason"] = "already_exists"
                results["archives_skipped"] += 1
            except Exception as e:
                log(f"    ERROR: Failed to create: {e}")
                action["status"] = "error"
                action["error"] = str(e)
                results["errors"].append(f"Create failed for {folder_name}: {e}")

        results["actions"].append(action)

    log(f"\n=== Summary ===")
    log(f"Databases analyzed: {results['databases_analyzed']}")
    log(f"Archives created: {results['archives_created']}")
    log(f"Archives skipped: {results['archives_skipped']}")
    log(f"Errors: {len(results['errors'])}")
    log(f"Log file: {log_file}")

    # Save results
    results_file = LOG_PATH / f"archive_remediation_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    log(f"Results saved to: {results_file}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix missing .archive folders in DriveSheetsSync workspace-databases"
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
    print(f"DriveSheetsSync Archive Remediation Script")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE EXECUTION'}")
    print(f"{'=' * 60}\n")

    results = remediate_missing_archives(dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("Remediation Complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
