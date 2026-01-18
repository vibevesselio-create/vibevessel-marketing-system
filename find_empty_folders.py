#!/usr/bin/env python3
"""
Find Empty Folders
==================

Scans specified directories and all subdirectories to locate empty folders.
"""

import os
import sys
from pathlib import Path
from typing import List, Set

def is_folder_empty(folder_path: Path) -> bool:
    """Check if a folder is empty (no files or subdirectories)."""
    try:
        # Check if directory exists
        if not folder_path.exists() or not folder_path.is_dir():
            return False
        
        # Check if directory is accessible
        try:
            items = list(folder_path.iterdir())
        except PermissionError:
            return False  # Can't access, skip
        
        # Empty if no items
        return len(items) == 0
    
    except Exception:
        return False

def find_empty_folders(root_paths: List[str]) -> List[Path]:
    """Find all empty folders in the given root paths."""
    empty_folders = []
    processed = set()
    
    print(f"Scanning {len(root_paths)} root directories...")
    print("=" * 80)
    
    for root_str in root_paths:
        root_path = Path(root_str)
        
        if not root_path.exists():
            print(f"⚠️  Path does not exist: {root_str}")
            continue
        
        if not root_path.is_dir():
            print(f"⚠️  Not a directory: {root_str}")
            continue
        
        print(f"\n📂 Scanning: {root_str}")
        
        # Walk through all subdirectories
        try:
            for dirpath, dirnames, filenames in os.walk(root_path):
                dir_path = Path(dirpath)
                
                # Skip if already processed (avoid duplicates)
                if str(dir_path) in processed:
                    continue
                
                processed.add(str(dir_path))
                
                # Check if this directory is empty
                if is_folder_empty(dir_path):
                    empty_folders.append(dir_path)
                    print(f"  ⚠️  Empty folder found: {dir_path}")
                
                # Filter out directories we can't access
                dirnames[:] = [d for d in dirnames if not (dir_path / d).is_symlink() or (dir_path / d).exists()]
                
        except PermissionError as e:
            print(f"  ❌ Permission denied: {e}")
        except Exception as e:
            print(f"  ❌ Error scanning {root_str}: {e}")
    
    return sorted(empty_folders)

def main():
    """Main execution"""
    # Directories to scan
    directories = [
        "/Volumes/VIBES/Apple-Music-Auto-Add",
        "/Volumes/VIBES/Djay-Pro-Auto-Import",
        "/Volumes/VIBES/Playlists",
        "/Volumes/VIBES/Music Library-2.library",
        "/Volumes/VIBES/Downloads-Music",
        "/Volumes/VIBES/DAVINCI PROJECT FOLDERS",
        "/Volumes/VIBES/Music",
        "/Volumes/VIBES/Automatically Add to Music.localized",
        "/Volumes/VIBES/Engine Library",
        "/Volumes/VIBES/REKORDBOX",
        "/Volumes/VIBES/Music-dep",
        "/Volumes/VIBES/music-library-2.eaglepack",
        "/Volumes/VIBES/APPLE-MUSIC-LIBRARY-100525.xml",
        "/Volumes/VIBES/python3",
        "/Volumes/VIBES/AIFF_Masters",
        "/Volumes/VIBES/Soundcloud Downloads",
        "/Volumes/VIBES/Soundcloud Downloads M4A"
    ]
    
    print("=" * 80)
    print("EMPTY FOLDER SCAN")
    print("=" * 80)
    print(f"Scanning {len(directories)} root directories...")
    print()
    
    # Find empty folders
    empty_folders = find_empty_folders(directories)
    
    # Report results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total empty folders found: {len(empty_folders)}")
    
    if empty_folders:
        print("\nEmpty folders:")
        print("-" * 80)
        
        # Group by parent directory for better readability
        folders_by_parent = {}
        for folder in empty_folders:
            parent = str(folder.parent)
            if parent not in folders_by_parent:
                folders_by_parent[parent] = []
            folders_by_parent[parent].append(folder)
        
        # Print grouped by parent
        for parent in sorted(folders_by_parent.keys()):
            print(f"\n📁 {parent}")
            for folder in sorted(folders_by_parent[parent]):
                print(f"  └── {folder.name}/")
        
        # Also print flat list
        print("\n" + "-" * 80)
        print("Flat list (all empty folders):")
        print("-" * 80)
        for folder in empty_folders:
            print(folder)
        
        # Save to file
        output_file = Path("logs/empty_folders_report.txt")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with output_file.open("w") as f:
            f.write("Empty Folders Report\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total empty folders found: {len(empty_folders)}\n")
            f.write(f"Generated: {Path(__file__).stat().st_mtime}\n\n")
            f.write("-" * 80 + "\n")
            for folder in empty_folders:
                f.write(f"{folder}\n")
        
        print(f"\n✓ Report saved to: {output_file}")
    else:
        print("\n✓ No empty folders found!")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
