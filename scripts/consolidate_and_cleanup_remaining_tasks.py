#!/usr/bin/env python3
"""
Consolidate and Cleanup Remaining Tasks

Handles remaining trigger files and consolidates related tasks.
"""

import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Inbox and processed directories - use folder_resolver for dynamic paths
try:
    from shared_core.notion.folder_resolver import get_agent_folder_structure
    _cursor_folders = get_agent_folder_structure("Cursor MM1 Agent")
    INBOX_DIR = _cursor_folders["inbox"]
    PROCESSED_DIR = _cursor_folders["processed"]
except ImportError:
    INBOX_DIR = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/01_inbox")
    PROCESSED_DIR = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/02_processed")

# Files to consolidate/archive
# Group 1: GAS Bridge Script related (3 files - all about same blocking issue)
GAS_BRIDGE_FILES = [
    "20260105T050810Z__HANDOFF__GAS-Bridge-Script-Location-Resolution__Claude-Opus.json",
    "20260105T050300Z__HANDOFF__GAS-Scripts-Production-Audit-and-KM-Bridge-Investigation__Claude-Opus.json",
    "20260104T214500Z__HANDOFF__Critical-AgentTasks-Execution__Claude-Code.json",
]

# Group 2: Archive folder audit (already completed, issue resolved)
ARCHIVE_AUDIT_FILES = [
    "20260104T200600Z__HANDOFF__DriveSheetsSync-Archive-Folder-Audit__claude-code.json",
]

# Group 3: Validation tasks that can be archived (related issues resolved)
VALIDATION_FILES = [
    "20260105T024500Z__VALIDATION__DriveSheetsSync-DuplicateFolderFix-Validation__Claude-Code.json",
]

# Group 4: Active tasks to keep
ACTIVE_TASKS = [
    "20260105T120000Z__HANDOFF__Return-Handoff-Enforcement-Compliance__Cursor-MM1.json",
    "20260105T060000Z__HANDOFF__Stale-Trigger-Cleanup-And-Issue-Triage__Claude-Opus.md",
    "20260104T091300Z__HANDOFF__iPad-Library-P1-BPM-Analysis-Notion-Sync__2dee7361.json",
    "20260103T180000Z__HANDOFF__Critical-Blockers-Investigation__claude-opus.json",
    "20260103T214500Z__HANDOFF__Music-Library-Remediation-Execution__Claude-Opus.md",
    "20260104T183511Z__HANDOFF__Notion-Token-Redaction-Rotation__Cursor-MM1-Agent.json",
    "music-sync-handoff-2026-01-03.md",
]

def move_to_processed(filename: str, reason: str = ""):
    """Move file to processed with note"""
    source = INBOX_DIR / filename
    dest = PROCESSED_DIR / filename
    
    if not source.exists():
        print(f"  ⚠️  Not found: {filename}")
        return False
    
    try:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
        if reason:
            print(f"  ✅ Moved: {filename} ({reason})")
        else:
            print(f"  ✅ Moved: {filename}")
        return True
    except Exception as e:
        print(f"  ❌ Error: {filename} - {e}")
        return False

def consolidate_gas_bridge_files():
    """Consolidate GAS Bridge Script related files"""
    print("\n📦 Consolidating GAS Bridge Script Files...")
    print("   (All 3 files reference same blocking issue - keeping most recent)")
    
    # Keep the most recent one (050810), archive others
    files_to_archive = GAS_BRIDGE_FILES[1:]  # Archive the other 2
    
    for filename in files_to_archive:
        move_to_processed(filename, "Consolidated - duplicate GAS Bridge Script handoff")
    
    print(f"   ✅ Kept: {GAS_BRIDGE_FILES[0]} (most recent)")
    print(f"   ✅ Archived: {len(files_to_archive)} duplicate handoffs")

def main():
    """Main execution"""
    print("=" * 80)
    print("Consolidate and Cleanup Remaining Tasks")
    print("=" * 80)
    
    # Consolidate GAS Bridge files
    consolidate_gas_bridge_files()
    
    # Archive completed work
    print("\n📦 Archiving Completed Work...")
    for filename in ARCHIVE_AUDIT_FILES:
        move_to_processed(filename, "Issue resolved - work completed")
    
    for filename in VALIDATION_FILES:
        move_to_processed(filename, "Related issue resolved - validation complete")
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    
    remaining = [f for f in INBOX_DIR.iterdir() if f.is_file() and f.name != ".DS_Store"]
    active_count = len([f for f in remaining if f.name in ACTIVE_TASKS])
    
    print(f"✅ Files consolidated/archived")
    print(f"📁 Active tasks remaining: {active_count}")
    print(f"📁 Total files in inbox: {len(remaining)}")
    
    if active_count > 0:
        print("\nActive tasks:")
        for task in ACTIVE_TASKS:
            if (INBOX_DIR / task).exists():
                print(f"  • {task}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

