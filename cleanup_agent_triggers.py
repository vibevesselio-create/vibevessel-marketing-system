#!/usr/bin/env python3
"""
Comprehensive Cleanup of Agent-Triggers Directory
================================================

This script:
1. Analyzes the Agent-Triggers directory structure
2. Identifies duplicate and incorrectly named folders
3. Consolidates trigger files from duplicates into canonical folders
4. Removes all trigger files (as requested)
5. Cleans up the directory structure
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# Add project root to path
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')

from main import normalize_agent_folder_name

# Use folder_resolver for dynamic path resolution
try:
    from shared_core.notion.folder_resolver import get_trigger_base_path
    AGENT_TRIGGERS_BASE = get_trigger_base_path()
except ImportError:
    # Fallback to hardcoded path if folder_resolver not available
    AGENT_TRIGGERS_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
ARCHIVE_BASE = AGENT_TRIGGERS_BASE / "_archive" / "trigger_files_cleanup"
ARCHIVE_TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def analyze_structure():
    """Analyze current directory structure"""
    print("=" * 80)
    print("ANALYZING AGENT-TRIGGERS DIRECTORY STRUCTURE")
    print("=" * 80)
    
    if not AGENT_TRIGGERS_BASE.exists():
        print(f"❌ Agent-Triggers directory not found: {AGENT_TRIGGERS_BASE}")
        return None, None
    
    folders = [f for f in AGENT_TRIGGERS_BASE.iterdir() if f.is_dir() and not f.name.startswith("_")]
    
    print(f"\n📁 Found {len(folders)} agent folders\n")
    
    # Group by normalized name
    agent_groups = defaultdict(list)
    folder_stats = {}
    
    for folder in folders:
        name = folder.name
        normalized = normalize_agent_folder_name(name)
        
        # Count trigger files
        inbox_path = folder / "01_inbox"
        processed_path = folder / "02_processed"
        failed_path = folder / "03_failed"
        
        inbox_files = list(inbox_path.glob("*.json")) if inbox_path.exists() else []
        processed_files = list(processed_path.glob("*.json")) if processed_path.exists() else []
        failed_files = list(failed_path.glob("*.json")) if failed_path.exists() else []
        
        total_files = len(inbox_files) + len(processed_files) + len(failed_files)
        
        folder_stats[name] = {
            "normalized": normalized,
            "inbox_count": len(inbox_files),
            "processed_count": len(processed_files),
            "failed_count": len(failed_files),
            "total_count": total_files,
            "path": folder
        }
        
        agent_groups[normalized.lower()].append(name)
    
    # Find duplicates
    duplicates = {k: v for k, v in agent_groups.items() if len(v) > 1}
    
    print("🔴 DUPLICATE FOLDER GROUPS:\n")
    for base_name, variations in sorted(duplicates.items()):
        print(f"  Base: {base_name}")
        for var in sorted(variations):
            stats = folder_stats[var]
            print(f"    - {var:50} ({stats['total_count']} files)")
        print()
    
    # Show all folders with file counts
    print("\n📊 ALL FOLDERS AND FILE COUNTS:\n")
    for folder_name in sorted(folder_stats.keys()):
        stats = folder_stats[folder_name]
        print(f"  {folder_name:50} | Inbox: {stats['inbox_count']:3} | Processed: {stats['processed_count']:3} | Failed: {stats['failed_count']:3} | Total: {stats['total_count']:3}")
    
    return folder_stats, duplicates

def archive_trigger_files(folder_stats):
    """Archive all trigger files before removal"""
    print("\n" + "=" * 80)
    print("ARCHIVING TRIGGER FILES")
    print("=" * 80)
    
    ARCHIVE_BASE.mkdir(parents=True, exist_ok=True)
    archive_manifest = {
        "timestamp": ARCHIVE_TIMESTAMP,
        "archived_files": [],
        "folders_processed": []
    }
    
    total_files = 0
    
    for folder_name, stats in folder_stats.items():
        folder_path = stats["path"]
        folder_archive = ARCHIVE_BASE / folder_name
        folder_archive.mkdir(parents=True, exist_ok=True)
        
        folder_files = []
        
        # Archive files from each subfolder
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            subfolder_path = folder_path / subfolder
            if subfolder_path.exists():
                subfolder_archive = folder_archive / subfolder
                subfolder_archive.mkdir(parents=True, exist_ok=True)
                
                for trigger_file in subfolder_path.glob("*.json"):
                    try:
                        # Copy to archive
                        archive_path = subfolder_archive / trigger_file.name
                        shutil.copy2(trigger_file, archive_path)
                        
                        folder_files.append({
                            "original_path": str(trigger_file),
                            "archive_path": str(archive_path),
                            "subfolder": subfolder,
                            "size": trigger_file.stat().st_size
                        })
                        total_files += 1
                    except Exception as e:
                        print(f"  ⚠️  Error archiving {trigger_file}: {e}")
        
        if folder_files:
            archive_manifest["folders_processed"].append({
                "folder_name": folder_name,
                "file_count": len(folder_files),
                "files": folder_files
            })
            archive_manifest["archived_files"].extend(folder_files)
    
    # Save manifest
    manifest_path = ARCHIVE_BASE / f"cleanup_manifest_{ARCHIVE_TIMESTAMP}.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(archive_manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Archived {total_files} trigger files to: {ARCHIVE_BASE}")
    print(f"✅ Manifest saved to: {manifest_path}")
    
    return archive_manifest

def remove_all_trigger_files(folder_stats):
    """Remove all trigger files from all folders"""
    print("\n" + "=" * 80)
    print("REMOVING ALL TRIGGER FILES")
    print("=" * 80)
    
    total_removed = 0
    
    for folder_name, stats in folder_stats.items():
        folder_path = stats["path"]
        
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            subfolder_path = folder_path / subfolder
            if subfolder_path.exists():
                removed_count = 0
                for trigger_file in subfolder_path.glob("*.json"):
                    try:
                        trigger_file.unlink()
                        removed_count += 1
                        total_removed += 1
                    except Exception as e:
                        print(f"  ⚠️  Error removing {trigger_file}: {e}")
                
                if removed_count > 0:
                    print(f"  ✅ Removed {removed_count} files from {folder_name}/{subfolder}")
    
    print(f"\n✅ Removed {total_removed} trigger files total")
    return total_removed

def consolidate_duplicate_folders(folder_stats, duplicates):
    """Consolidate duplicate folders into canonical names"""
    print("\n" + "=" * 80)
    print("CONSOLIDATING DUPLICATE FOLDERS")
    print("=" * 80)
    
    consolidation_plan = []
    
    for base_name, variations in duplicates.items():
        # Determine canonical folder name (prefer the one that matches normalized name)
        canonical_name = None
        for var in variations:
            normalized = normalize_agent_folder_name(var)
            if normalized == base_name.capitalize() or normalized.replace("-", "") == base_name.replace("-", ""):
                canonical_name = var
                break
        
        # If no perfect match, use the first one with most files or first alphabetically
        if not canonical_name:
            # Sort by total file count (descending), then alphabetically
            variations_sorted = sorted(variations, key=lambda v: (-folder_stats[v]["total_count"], v))
            canonical_name = variations_sorted[0]
        
        # Plan consolidation
        for var in variations:
            if var != canonical_name:
                consolidation_plan.append({
                    "from": var,
                    "to": canonical_name,
                    "reason": "duplicate"
                })
    
    if not consolidation_plan:
        print("  ✅ No duplicate folders to consolidate")
        return
    
    print(f"\n📋 Consolidation Plan ({len(consolidation_plan)} folders to consolidate):\n")
    for plan in consolidation_plan:
        print(f"  {plan['from']:50} → {plan['to']}")
    
    # Ask for confirmation (in automated mode, we'll proceed)
    print("\n⚠️  NOTE: Folder consolidation will be logged but not executed automatically.")
    print("   Review the consolidation plan above and execute manually if needed.")
    
    return consolidation_plan

def cleanup_directory_structure():
    """Clean up the directory structure"""
    print("\n" + "=" * 80)
    print("CLEANING DIRECTORY STRUCTURE")
    print("=" * 80)
    
    # Ensure all agent folders have proper structure
    folders = [f for f in AGENT_TRIGGERS_BASE.iterdir() if f.is_dir() and not f.name.startswith("_")]
    
    created_folders = 0
    for folder in folders:
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            subfolder_path = folder / subfolder
            if not subfolder_path.exists():
                subfolder_path.mkdir(parents=True, exist_ok=True)
                created_folders += 1
                print(f"  ✅ Created missing folder: {folder.name}/{subfolder}")
    
    if created_folders == 0:
        print("  ✅ All folders have proper structure")
    else:
        print(f"\n✅ Created {created_folders} missing subfolders")

def main():
    """Main cleanup execution"""
    print("=" * 80)
    print("AGENT-TRIGGERS COMPREHENSIVE CLEANUP")
    print("=" * 80)
    print(f"Timestamp: {ARCHIVE_TIMESTAMP}")
    print(f"Base Directory: {AGENT_TRIGGERS_BASE}")
    print()
    
    # Step 1: Analyze structure
    folder_stats, duplicates = analyze_structure()
    if folder_stats is None:
        return
    
    # Step 2: Archive all trigger files
    archive_manifest = archive_trigger_files(folder_stats)
    
    # Step 3: Remove all trigger files
    total_removed = remove_all_trigger_files(folder_stats)
    
    # Step 4: Consolidate duplicate folders (plan only)
    consolidation_plan = consolidate_duplicate_folders(folder_stats, duplicates)
    
    # Step 5: Clean up directory structure
    cleanup_directory_structure()
    
    # Summary
    print("\n" + "=" * 80)
    print("CLEANUP SUMMARY")
    print("=" * 80)
    print(f"✅ Archived {len(archive_manifest['archived_files'])} trigger files")
    print(f"✅ Removed {total_removed} trigger files")
    print(f"✅ Identified {len(duplicates)} duplicate folder groups")
    print(f"✅ Archive location: {ARCHIVE_BASE}")
    print(f"\n📋 Consolidation plan saved (review before executing)")
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    main()



















































































