#!/usr/bin/env python3
"""
Script to remove all empty folders from specified directory paths.
Processes directories bottom-up to handle nested empty folders correctly.
"""

import os
import sys
from pathlib import Path


def is_directory_empty(dir_path):
    """Check if a directory is empty (no files or subdirectories)."""
    try:
        return not any(os.scandir(dir_path))
    except (PermissionError, OSError) as e:
        print(f"Warning: Cannot access {dir_path}: {e}")
        return False


def remove_empty_folders(root_path):
    """
    Recursively remove all empty folders starting from the deepest level.
    Returns count of removed folders.
    """
    removed_count = 0
    
    # Walk bottom-up (deepest directories first)
    for root, dirs, files in os.walk(root_path, topdown=False):
        # Check if current directory is empty
        if is_directory_empty(root):
            try:
                os.rmdir(root)
                print(f"Removed empty folder: {root}")
                removed_count += 1
            except (PermissionError, OSError) as e:
                print(f"Error: Cannot remove {root}: {e}")
    
    return removed_count


def main():
    """Main function to process all specified paths."""
    paths = [
        '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive',
        '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/Shared drives'
    ]
    
    total_removed = 0
    
    for path in paths:
        path_obj = Path(path)
        
        if not path_obj.exists():
            print(f"Warning: Path does not exist: {path}")
            continue
        
        if not path_obj.is_dir():
            print(f"Warning: Path is not a directory: {path}")
            continue
        
        print(f"\n{'='*80}")
        print(f"Processing: {path}")
        print(f"{'='*80}")
        
        removed = remove_empty_folders(path)
        total_removed += removed
        
        print(f"\nRemoved {removed} empty folder(s) from: {path}")
    
    print(f"\n{'='*80}")
    print(f"Total empty folders removed: {total_removed}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
















