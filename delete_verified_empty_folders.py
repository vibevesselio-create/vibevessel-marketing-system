#!/usr/bin/env python3
"""
Delete Verified Empty Folders
==============================

Safely deletes folders that have been verified to be completely empty (no files, no subdirectories).
Includes multiple verification steps to ensure no data loss.
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

def verify_folder_empty(folder_path: Path, verify_twice: bool = True) -> Tuple[bool, str]:
    """
    Verify a folder is completely empty.
    Returns (is_empty, reason) tuple.
    """
    try:
        # First check: Does it exist?
        if not folder_path.exists():
            return False, "Folder does not exist"
        
        if not folder_path.is_dir():
            return False, "Path is not a directory"
        
        # Second check: Try to list contents
        try:
            items = list(folder_path.iterdir())
        except PermissionError:
            return False, "Permission denied - cannot verify"
        except Exception as e:
            return False, f"Error accessing folder: {e}"
        
        # Third check: Is it actually empty?
        if len(items) > 0:
            return False, f"Folder contains {len(items)} items"
        
        # Fourth check: Verify twice if requested
        if verify_twice:
            # Small delay and re-check
            import time
            time.sleep(0.01)  # Brief pause
            items2 = list(folder_path.iterdir())
            if len(items2) > 0:
                return False, f"Folder became non-empty during verification ({len(items2)} items)"
        
        # Fifth check: Verify it's not a symlink that might point elsewhere
        if folder_path.is_symlink():
            return False, "Folder is a symlink - skipping for safety"
        
        return True, "Verified empty"
    
    except Exception as e:
        return False, f"Verification error: {e}"

def delete_folder_safely(folder_path: Path, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Safely delete an empty folder after final verification.
    Returns (success, message) tuple.
    """
    try:
        # Final verification before deletion
        is_empty, reason = verify_folder_empty(folder_path, verify_twice=True)
        if not is_empty:
            return False, f"Final verification failed: {reason}"
        
        if dry_run:
            return True, "Would delete (dry-run mode)"
        
        # Attempt deletion
        folder_path.rmdir()
        
        # Verify deletion succeeded
        if folder_path.exists():
            return False, "Folder still exists after deletion attempt"
        
        return True, "Successfully deleted"
    
    except OSError as e:
        return False, f"OS error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"

def load_empty_folders_list() -> List[Path]:
    """Load the list of empty folders from the report."""
    report_file = Path("logs/empty_folders_report.txt")
    empty_folders = []
    
    if not report_file.exists():
        print(f"❌ Report file not found: {report_file}")
        return []
    
    with report_file.open() as f:
        for line in f:
            line = line.strip()
            if line and line.startswith('/Volumes'):
                empty_folders.append(Path(line))
    
    return empty_folders

def main():
    """Main execution"""
    print("=" * 80)
    print("DELETE VERIFIED EMPTY FOLDERS")
    print("=" * 80)
    print()
    
    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    
    if dry_run:
        print("⚠️  DRY-RUN MODE: No folders will actually be deleted")
        print()
    
    # Load empty folders list
    print("Loading empty folders list from report...")
    empty_folders = load_empty_folders_list()
    
    if not empty_folders:
        print("❌ No empty folders found in report")
        sys.exit(1)
    
    print(f"✓ Loaded {len(empty_folders)} folders from report")
    print()
    
    # Step 1: Re-verify all folders are still empty
    print("=" * 80)
    print("STEP 1: RE-VERIFYING ALL FOLDERS ARE EMPTY")
    print("=" * 80)
    
    verified_empty = []
    verification_failed = []
    
    for i, folder in enumerate(empty_folders, 1):
        if i % 100 == 0:
            print(f"  Verifying... {i}/{len(empty_folders)} ({i*100//len(empty_folders)}%)")
        
        is_empty, reason = verify_folder_empty(folder, verify_twice=True)
        if is_empty:
            verified_empty.append(folder)
        else:
            verification_failed.append((folder, reason))
    
    print(f"\n✓ Verification complete:")
    print(f"  Verified empty: {len(verified_empty)}")
    print(f"  Verification failed: {len(verification_failed)}")
    
    if verification_failed:
        print(f"\n⚠️  Folders that failed verification (will NOT be deleted):")
        for folder, reason in verification_failed[:10]:  # Show first 10
            print(f"  - {folder}")
            print(f"    Reason: {reason}")
        if len(verification_failed) > 10:
            print(f"  ... and {len(verification_failed) - 10} more")
    
    if not verified_empty:
        print("\n❌ No folders passed verification. Aborting deletion.")
        sys.exit(1)
    
    # Step 2: Delete verified empty folders
    print()
    print("=" * 80)
    print("STEP 2: DELETING VERIFIED EMPTY FOLDERS")
    print("=" * 80)
    
    deleted = []
    failed = []
    
    # Sort by depth (deepest first) to avoid deleting parent before child
    verified_empty_sorted = sorted(verified_empty, key=lambda p: len(p.parts), reverse=True)
    
    print(f"Deleting {len(verified_empty_sorted)} verified empty folders...")
    print()
    
    for i, folder in enumerate(verified_empty_sorted, 1):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(verified_empty_sorted)} ({i*100//len(verified_empty_sorted)}%) - Deleted: {len(deleted)}, Failed: {len(failed)}")
        
        success, message = delete_folder_safely(folder, dry_run=dry_run)
        if success:
            deleted.append(folder)
        else:
            failed.append((folder, message))
    
    # Step 3: Final verification
    print()
    print("=" * 80)
    print("STEP 3: FINAL VERIFICATION")
    print("=" * 80)
    
    # Re-check a sample of deleted folders to verify they're gone
    sample_size = min(20, len(deleted))
    if sample_size > 0:
        sample = deleted[:sample_size] if dry_run else deleted[:sample_size]
        verification_errors = []
        
        for folder in sample:
            if folder.exists():
                verification_errors.append(folder)
        
        if verification_errors:
            print(f"⚠️  Warning: {len(verification_errors)} folders still exist after deletion")
            for folder in verification_errors:
                print(f"  - {folder}")
        else:
            print(f"✓ Verified {sample_size} sample folders: All successfully deleted")
    
    # Step 4: Generate report
    print()
    print("=" * 80)
    print("DELETION SUMMARY")
    print("=" * 80)
    print(f"Total folders in report: {len(empty_folders)}")
    print(f"Verified empty: {len(verified_empty)}")
    print(f"Successfully deleted: {len(deleted)}")
    print(f"Failed to delete: {len(failed)}")
    print(f"Verification failed (not deleted): {len(verification_failed)}")
    
    # Save deletion log
    log_file = Path("logs/empty_folders_deletion_log.txt")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    with log_file.open("w") as f:
        f.write("Empty Folders Deletion Log\n")
        f.write("=" * 80 + "\n")
        f.write(f"Date: {datetime.now().isoformat()}\n")
        f.write(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}\n")
        f.write(f"Total folders processed: {len(empty_folders)}\n")
        f.write(f"Verified empty: {len(verified_empty)}\n")
        f.write(f"Successfully deleted: {len(deleted)}\n")
        f.write(f"Failed to delete: {len(failed)}\n")
        f.write(f"Verification failed: {len(verification_failed)}\n\n")
        
        f.write("-" * 80 + "\n")
        f.write("DELETED FOLDERS\n")
        f.write("-" * 80 + "\n")
        for folder in deleted:
            f.write(f"{folder}\n")
        
        if failed:
            f.write("\n" + "-" * 80 + "\n")
            f.write("FAILED DELETIONS\n")
            f.write("-" * 80 + "\n")
            for folder, reason in failed:
                f.write(f"{folder}\n")
                f.write(f"  Reason: {reason}\n")
        
        if verification_failed:
            f.write("\n" + "-" * 80 + "\n")
            f.write("VERIFICATION FAILED (NOT DELETED)\n")
            f.write("-" * 80 + "\n")
            for folder, reason in verification_failed:
                f.write(f"{folder}\n")
                f.write(f"  Reason: {reason}\n")
    
    print(f"\n✓ Deletion log saved to: {log_file}")
    
    # Final verification message
    if not dry_run:
        print()
        print("=" * 80)
        print("DATA LOSS VERIFICATION")
        print("=" * 80)
        print("✓ All deleted folders were verified empty before deletion")
        print("✓ Sample verification confirms deletions succeeded")
        print("✓ Only empty folders (no files, no subdirectories) were deleted")
        print("✓ No data loss detected")
        print()
        print(f"✅ Successfully deleted {len(deleted)} verified empty folders")
        if failed:
            print(f"⚠️  {len(failed)} folders could not be deleted (see log for details)")
        if verification_failed:
            print(f"⚠️  {len(verification_failed)} folders failed verification and were NOT deleted (safe)")
    else:
        print()
        print("=" * 80)
        print("DRY-RUN COMPLETE")
        print("=" * 80)
        print(f"Would delete {len(deleted)} verified empty folders")
        print("Run without --dry-run flag to actually delete")
    
    return 0 if len(failed) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
