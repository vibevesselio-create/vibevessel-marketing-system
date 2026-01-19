#!/usr/bin/env python3
"""
Eagle Folder Deduplication Utility
==================================

One-time cleanup script to identify and consolidate duplicate folders
in Eagle Library that were created before the folder lookup bug was fixed.

Root Cause (now fixed in soundcloud_download_prod_merge-2.py lines 6141-6173):
- find_folder_recursive() was checking f.get("parent") but Eagle API
  doesn't return a parent field - it returns nested children structures
- This caused new folders to be created instead of finding existing ones

This utility:
1. Scans Eagle Library for duplicate folder names at the same level
2. Reports all duplicates found
3. Optionally merges items from duplicate folders into the primary
4. Can delete empty duplicate folders after merge

Usage:
    python scripts/eagle_folder_deduplication.py --scan         # Scan only
    python scripts/eagle_folder_deduplication.py --merge        # Scan and merge
    python scripts/eagle_folder_deduplication.py --merge --delete-empty  # Full cleanup

Created: 2026-01-19
Author: Claude Code Agent
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Eagle API configuration
EAGLE_PORT = 41595
EAGLE_BASE_URL = f"http://localhost:{EAGLE_PORT}"


@dataclass
class FolderInfo:
    """Represents an Eagle folder."""
    id: str
    name: str
    parent_id: Optional[str]  # None for root-level folders
    item_count: int
    children_count: int


@dataclass
class DuplicateSet:
    """A set of duplicate folders."""
    name: str
    parent_id: Optional[str]
    folders: List[FolderInfo]

    @property
    def primary(self) -> FolderInfo:
        """The folder to keep (most items or first created)."""
        # Prefer folder with most items
        return max(self.folders, key=lambda f: f.item_count)

    @property
    def duplicates(self) -> List[FolderInfo]:
        """Folders to merge into primary."""
        primary = self.primary
        return [f for f in self.folders if f.id != primary.id]


def eagle_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
    """Make a request to Eagle API."""
    url = f"{EAGLE_BASE_URL}/api/{endpoint}"

    try:
        if method == "POST" and data:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            req = urllib.request.Request(url, method=method)

        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"ERROR: Eagle API not available at {url}: {e}")
        sys.exit(1)


def get_all_folders() -> List[Dict]:
    """Get all folders from Eagle."""
    response = eagle_request("folder/list")
    return response.get("data", [])


def flatten_folders(folders: List[Dict], parent_id: Optional[str] = None) -> List[FolderInfo]:
    """Flatten nested folder structure into flat list with parent tracking."""
    result = []

    for f in folders:
        folder_info = FolderInfo(
            id=f.get("id", ""),
            name=f.get("name", ""),
            parent_id=parent_id,
            item_count=f.get("count", 0),  # Number of items in folder
            children_count=len(f.get("children", []))
        )
        result.append(folder_info)

        # Recursively process children
        children = f.get("children", [])
        if children:
            result.extend(flatten_folders(children, folder_info.id))

    return result


def find_duplicates(folders: List[FolderInfo]) -> List[DuplicateSet]:
    """Find folders with duplicate names at the same parent level."""
    # Group by (name, parent_id)
    groups: Dict[Tuple[str, Optional[str]], List[FolderInfo]] = defaultdict(list)

    for folder in folders:
        key = (folder.name, folder.parent_id)
        groups[key].append(folder)

    # Filter to only groups with duplicates
    duplicates = []
    for (name, parent_id), folder_list in groups.items():
        if len(folder_list) > 1:
            duplicates.append(DuplicateSet(
                name=name,
                parent_id=parent_id,
                folders=folder_list
            ))

    return duplicates


def get_items_in_folder(folder_id: str) -> List[Dict]:
    """Get all items in a folder."""
    response = eagle_request(f"item/list?folderId={folder_id}")
    return response.get("data", [])


def move_item_to_folder(item_id: str, folder_id: str) -> bool:
    """Move an item to a different folder."""
    response = eagle_request(
        "item/update",
        method="POST",
        data={"id": item_id, "folderId": folder_id}
    )
    return response.get("status") == "success"


def delete_folder(folder_id: str) -> bool:
    """Delete an empty folder."""
    # Note: Eagle API requires folder to be empty before deletion
    response = eagle_request(
        "folder/delete",
        method="POST",
        data={"folderId": folder_id}
    )
    return response.get("status") == "success"


def scan_for_duplicates() -> List[DuplicateSet]:
    """Scan Eagle Library for duplicate folders."""
    print("Scanning Eagle Library for duplicate folders...\n")

    raw_folders = get_all_folders()
    flat_folders = flatten_folders(raw_folders)

    print(f"Found {len(flat_folders)} total folders")

    duplicates = find_duplicates(flat_folders)

    return duplicates


def report_duplicates(duplicates: List[DuplicateSet]) -> None:
    """Print a report of duplicate folders."""
    if not duplicates:
        print("\n✅ No duplicate folders found!")
        return

    print(f"\n⚠️  Found {len(duplicates)} duplicate folder sets:\n")
    print("=" * 70)

    for i, dup_set in enumerate(duplicates, 1):
        parent_desc = f"parent={dup_set.parent_id}" if dup_set.parent_id else "root level"
        print(f"\n{i}. Folder Name: \"{dup_set.name}\" ({parent_desc})")
        print("-" * 50)

        primary = dup_set.primary

        for folder in dup_set.folders:
            is_primary = folder.id == primary.id
            marker = "✓ PRIMARY" if is_primary else "  duplicate"
            print(f"   {marker} ID: {folder.id}")
            print(f"            Items: {folder.item_count}, Subfolders: {folder.children_count}")

        total_items = sum(f.item_count for f in dup_set.folders)
        items_to_move = total_items - primary.item_count
        print(f"   → Would merge {items_to_move} items into primary")

    print("\n" + "=" * 70)


def merge_duplicates(duplicates: List[DuplicateSet], delete_empty: bool = False) -> Dict:
    """Merge items from duplicate folders into primaries."""
    stats = {
        "folders_processed": 0,
        "items_moved": 0,
        "folders_deleted": 0,
        "errors": []
    }

    for dup_set in duplicates:
        primary = dup_set.primary
        print(f"\nProcessing: \"{dup_set.name}\" → keeping {primary.id}")

        for dup_folder in dup_set.duplicates:
            print(f"  Merging {dup_folder.id} into {primary.id}...")

            # Get items from duplicate folder
            items = get_items_in_folder(dup_folder.id)

            for item in items:
                item_id = item.get("id")
                if move_item_to_folder(item_id, primary.id):
                    stats["items_moved"] += 1
                    print(f"    ✓ Moved item {item_id}")
                else:
                    stats["errors"].append(f"Failed to move {item_id}")
                    print(f"    ✗ Failed to move {item_id}")

            # Delete empty folder if requested
            if delete_empty and dup_folder.item_count == 0:
                # Re-check if folder is truly empty now
                remaining = get_items_in_folder(dup_folder.id)
                if len(remaining) == 0:
                    if delete_folder(dup_folder.id):
                        stats["folders_deleted"] += 1
                        print(f"    ✓ Deleted empty folder {dup_folder.id}")
                    else:
                        stats["errors"].append(f"Failed to delete {dup_folder.id}")

            stats["folders_processed"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Eagle Library folder deduplication utility"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan and report duplicates (no changes)"
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge items from duplicate folders into primary"
    )
    parser.add_argument(
        "--delete-empty",
        action="store_true",
        help="Delete folders after merging if empty (use with --merge)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    # Default to scan if no action specified
    if not args.scan and not args.merge:
        args.scan = True

    # Check Eagle is running
    try:
        info = eagle_request("application/info")
        print(f"Connected to Eagle: {info.get('data', {}).get('version', 'unknown')}")
    except SystemExit:
        return 1

    # Scan for duplicates
    duplicates = scan_for_duplicates()

    if args.json:
        result = {
            "duplicate_sets": [
                {
                    "name": d.name,
                    "parent_id": d.parent_id,
                    "primary_id": d.primary.id,
                    "duplicate_ids": [f.id for f in d.duplicates],
                    "total_items": sum(f.item_count for f in d.folders)
                }
                for d in duplicates
            ]
        }
        print(json.dumps(result, indent=2))
        return 0

    # Report findings
    report_duplicates(duplicates)

    if not duplicates:
        return 0

    # Merge if requested
    if args.merge:
        print("\n" + "=" * 70)
        print("STARTING MERGE OPERATION")
        print("=" * 70)

        confirm = input("\nProceed with merge? (yes/no): ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return 0

        stats = merge_duplicates(duplicates, delete_empty=args.delete_empty)

        print("\n" + "=" * 70)
        print("MERGE COMPLETE")
        print("=" * 70)
        print(f"Folders processed: {stats['folders_processed']}")
        print(f"Items moved: {stats['items_moved']}")
        print(f"Folders deleted: {stats['folders_deleted']}")
        if stats["errors"]:
            print(f"Errors: {len(stats['errors'])}")
            for err in stats["errors"]:
                print(f"  - {err}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
