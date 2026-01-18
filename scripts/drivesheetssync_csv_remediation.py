#!/usr/bin/env python3
"""
DriveSheetsSync CSV Remediation Script
=======================================

Fixes the 6 missing CSV files issue by:
1. Reading the audit data to identify folders with has_csv=false
2. For each affected folder, finding the most recent duplicate CSV file
3. Renaming/copying it to the canonical name (without suffix)

This addresses Issue ID: 2d9e7361-6c27-8110-bbc0-ea194520bdc2
"DriveSheetsSync: 6 Missing CSV Files - Incomplete Syncs"

Author: Claude Code Agent (Opus 4.5)
Created: 2026-01-03
"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def find_missing_csv_databases(audit_data: Dict) -> List[Tuple[str, Dict]]:
    """Find all databases where has_csv is false but duplicate CSVs exist."""
    missing = []
    for db_id, db_info in audit_data.get("structure", {}).get("databases", {}).items():
        if not db_info.get("has_csv", True):
            files = db_info.get("files", [])
            # Check if there are duplicate CSV files
            csv_files = [f for f in files if f.endswith('.csv')]
            if csv_files:
                missing.append((db_id, db_info))
    return missing


def extract_canonical_name(folder_name: str) -> str:
    """Extract the canonical CSV name from a folder name."""
    # Folder name format: "DatabaseName_UUID"
    # Canonical CSV name: "DatabaseName_UUID.csv"
    return f"{folder_name}.csv"


def find_best_duplicate(csv_files: List[str], folder_path: Path) -> Optional[Tuple[str, Path]]:
    """
    Find the best duplicate CSV to use as the canonical file.
    Prefers files with higher numbers (more recent) and checks file size.
    """
    if not csv_files:
        return None

    # Sort by suffix number (higher = more recent typically)
    def get_suffix_number(filename: str) -> int:
        # Match patterns like "(1)", "(2)", " 2", etc.
        match = re.search(r'\((\d+)\)\.csv$', filename)
        if match:
            return int(match.group(1))
        match = re.search(r'\s(\d+)\.csv$', filename)
        if match:
            return int(match.group(1))
        return 0  # No suffix = original (might be empty)

    # Sort by suffix number descending
    sorted_files = sorted(csv_files, key=get_suffix_number, reverse=True)

    # Find the first file that exists and has content
    for filename in sorted_files:
        file_path = folder_path / filename
        if file_path.exists() and file_path.stat().st_size > 0:
            return (filename, file_path)

    return None


def remediate_missing_csvs(dry_run: bool = True) -> Dict:
    """
    Main remediation function.

    Args:
        dry_run: If True, only report what would be done. If False, perform actions.

    Returns:
        Dictionary with remediation results
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_file = LOG_PATH / f"csv_remediation_{timestamp}.log"

    results = {
        "timestamp": timestamp,
        "dry_run": dry_run,
        "databases_analyzed": 0,
        "databases_fixed": 0,
        "databases_skipped": 0,
        "errors": [],
        "actions": []
    }

    def log(msg: str):
        print(msg)
        with open(log_file, 'a') as f:
            f.write(f"{datetime.now().isoformat()} - {msg}\n")

    log(f"=== DriveSheetsSync CSV Remediation {'(DRY RUN)' if dry_run else '(LIVE)'} ===")
    log(f"Timestamp: {timestamp}")

    # Load audit data
    try:
        audit_data = load_audit_data()
        log(f"Loaded audit data from {AUDIT_DATA_PATH}")
    except Exception as e:
        log(f"ERROR: Failed to load audit data: {e}")
        results["errors"].append(str(e))
        return results

    # Find databases with missing CSVs
    missing_csv_dbs = find_missing_csv_databases(audit_data)
    log(f"Found {len(missing_csv_dbs)} databases with missing canonical CSVs")

    for db_id, db_info in missing_csv_dbs:
        results["databases_analyzed"] += 1

        folder_path = Path(db_info.get("path", ""))
        folder_name = db_info.get("name", "")
        csv_files = [f for f in db_info.get("files", []) if f.endswith('.csv')]

        log(f"\n--- Processing: {folder_name} ---")
        log(f"    Path: {folder_path}")
        log(f"    CSV files found: {csv_files}")

        # Determine canonical name
        canonical_name = extract_canonical_name(folder_name)
        canonical_path = folder_path / canonical_name

        # Check if canonical already exists (audit data might be stale)
        if canonical_path.exists():
            log(f"    SKIP: Canonical file already exists: {canonical_name}")
            results["databases_skipped"] += 1
            continue

        # Find best duplicate to use
        best_dup = find_best_duplicate(csv_files, folder_path)

        if not best_dup:
            log(f"    ERROR: No valid duplicate CSV found to use")
            results["errors"].append(f"No valid duplicate for {folder_name}")
            continue

        source_name, source_path = best_dup
        log(f"    Selected source: {source_name}")
        log(f"    Source size: {source_path.stat().st_size} bytes")

        action = {
            "database_id": db_id,
            "folder_name": folder_name,
            "source_file": source_name,
            "target_file": canonical_name,
            "source_path": str(source_path),
            "target_path": str(canonical_path)
        }

        if dry_run:
            log(f"    DRY RUN: Would copy {source_name} -> {canonical_name}")
            action["status"] = "dry_run"
        else:
            try:
                # Copy (not move) so we don't lose the original
                shutil.copy2(source_path, canonical_path)
                log(f"    SUCCESS: Copied {source_name} -> {canonical_name}")
                action["status"] = "success"
                results["databases_fixed"] += 1
            except Exception as e:
                log(f"    ERROR: Failed to copy: {e}")
                action["status"] = "error"
                action["error"] = str(e)
                results["errors"].append(f"Copy failed for {folder_name}: {e}")

        results["actions"].append(action)

    log(f"\n=== Summary ===")
    log(f"Databases analyzed: {results['databases_analyzed']}")
    log(f"Databases fixed: {results['databases_fixed']}")
    log(f"Databases skipped: {results['databases_skipped']}")
    log(f"Errors: {len(results['errors'])}")
    log(f"Log file: {log_file}")

    # Save results
    results_file = LOG_PATH / f"csv_remediation_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    log(f"Results saved to: {results_file}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fix missing CSV files in DriveSheetsSync workspace-databases"
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
    print(f"DriveSheetsSync CSV Remediation Script")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE EXECUTION'}")
    print(f"{'=' * 60}\n")

    if not dry_run:
        print("WARNING: This will modify files in Google Drive.")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    results = remediate_missing_csvs(dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("Remediation Complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
