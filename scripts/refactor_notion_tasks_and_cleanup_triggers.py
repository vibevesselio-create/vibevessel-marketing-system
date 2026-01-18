#!/usr/bin/env python3
"""
Refactor Notion Tasks and Cleanup Trigger Files

Updates Notion task statuses for completed work and moves trigger files to 02_processed.
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Completed tasks that need status updates
COMPLETED_TASKS = {
    "2dee7361-6c27-8174-ac1b-e43ec200c666": {
        "name": "DriveSheetsSync Archive Folder Audit",
        "status": "Completed",
        "trigger_files": [
            "20260104T200600Z__HANDOFF__DriveSheetsSync-Archive-Folder-Audit__claude-code.json"
        ]
    },
    "2dfe7361-6c27-815d-bcbc-e4b0c939a946": {
        "name": "Agent Work Validation: DriveSheetsSync Duplicate Folder Fix",
        "status": "Completed",
        "trigger_files": [
            "20260105T024500Z__VALIDATION__DriveSheetsSync-DuplicateFolderFix-Validation__Claude-Code.json"
        ],
        "note": "Issue already resolved, validation task can be marked complete"
    }
}

# Completed trigger files to move (no Notion task or task already completed)
COMPLETED_TRIGGER_FILES = [
    # Already completed in Notion
    "20260104T230000Z__HANDOFF__Sync-Registry-Scripts-Consolidation__2dfe7361.json",
    "20260104T220000Z__HANDOFF__GAS-Script-Sync-Validate-Test__2dfe7361.json",
    "20260104T220744Z__HANDOFF__DriveSheetsSync-DeprecatedEndpoint-Validation__Claude-Code.md",
    "20260104T120000Z__HANDOFF__DriveSheetsSync-DuplicateFolders-Validation__Claude-Code.md",
    "20260103T231554__20260103T231500Z__HANDOFF__DriveSheetsSync-DuplicateFolderFix-Validation__Claude-Opus.md",
    "20260104T211641Z__HANDOFF__ReturnHandoffEnforcement-Validation__Claude-Code.md",
    "20260103T120000Z__HANDOFF__Validate-Task-Handoff-Logic-Updates__Claude-MM1.json",
    "20260103T151308Z__HANDOFF__DriveSheetsSync-ConsolidateDbIds-Execution__Claude-Code.md",
    "20260103T131500Z__HANDOFF__EnvPattern-Validation-Complete__dbdbd04e-e04c-40c5-b7dc-e2d8e5c58d62.md",
    "20260103T160500Z__VALIDATION__Agent-Work-Review-DriveSheetsSync-Deployment__Claude-Opus.md",
    "20260103T151500Z__VALIDATION__Agent-Work-Review-Claude-Code-DriveSheetsSync__Claude-Opus.md",
]

# Inbox and processed directories - use folder_resolver for dynamic paths
try:
    from shared_core.notion.folder_resolver import get_agent_folder_structure
    _cursor_folders = get_agent_folder_structure("Cursor MM1 Agent")
    INBOX_DIR = _cursor_folders["inbox"]
    PROCESSED_DIR = _cursor_folders["processed"]
except ImportError:
    INBOX_DIR = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/01_inbox")
    PROCESSED_DIR = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/02_processed")

def update_notion_task(task_id: str, status: str, notion: NotionManager) -> bool:
    """Update a Notion task status"""
    try:
        update_properties = {
            "Status": {"status": {"name": status}}
        }
        
        if notion.update_page(task_id, update_properties):
            print(f"  ✅ Updated task {task_id} to '{status}'")
            return True
        else:
            # Try alternative status names
            alternatives = ["Complete", "Done", "Finished"]
            for alt in alternatives:
                if alt.lower() != status.lower():
                    update_properties = {
                        "Status": {"status": {"name": alt}}
                    }
                    if notion.update_page(task_id, update_properties):
                        print(f"  ✅ Updated task {task_id} to '{alt}' (alternative)")
                        return True
            
            print(f"  ❌ Failed to update task {task_id}")
            return False
    except Exception as e:
        print(f"  ❌ Error updating task {task_id}: {e}")
        return False

def move_trigger_file(filename: str, source_dir: Path, dest_dir: Path) -> bool:
    """Move a trigger file from inbox to processed"""
    source_path = source_dir / filename
    dest_path = dest_dir / filename
    
    if not source_path.exists():
        print(f"  ⚠️  File not found: {filename}")
        return False
    
    try:
        # Ensure processed directory exists
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Move file
        shutil.move(str(source_path), str(dest_path))
        print(f"  ✅ Moved: {filename}")
        return True
    except Exception as e:
        print(f"  ❌ Error moving {filename}: {e}")
        return False

def main():
    """Main execution"""
    print("=" * 80)
    print("Notion Task Refactoring and Trigger File Cleanup")
    print("=" * 80)
    print()
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    # Update completed tasks in Notion
    print("📝 Updating Notion Task Statuses...")
    print("-" * 80)
    updated_count = 0
    for task_id, task_info in COMPLETED_TASKS.items():
        print(f"\n📋 {task_info['name']}")
        print(f"   Task ID: {task_id}")
        if update_notion_task(task_id, task_info['status'], notion):
            updated_count += 1
    print(f"\n✅ Updated {updated_count}/{len(COMPLETED_TASKS)} tasks in Notion")
    print()
    
    # Move completed trigger files
    print("📦 Moving Completed Trigger Files to 02_processed...")
    print("-" * 80)
    moved_count = 0
    for filename in COMPLETED_TRIGGER_FILES:
        if move_trigger_file(filename, INBOX_DIR, PROCESSED_DIR):
            moved_count += 1
    print(f"\n✅ Moved {moved_count}/{len(COMPLETED_TRIGGER_FILES)} trigger files")
    print()
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"✅ Notion tasks updated: {updated_count}/{len(COMPLETED_TASKS)}")
    print(f"✅ Trigger files moved: {moved_count}/{len(COMPLETED_TRIGGER_FILES)}")
    print()
    
    # List remaining files in inbox
    remaining_files = list(INBOX_DIR.glob("*"))
    remaining_count = len([f for f in remaining_files if f.is_file()])
    print(f"📁 Remaining files in inbox: {remaining_count}")
    
    if remaining_count > 0:
        print("\nRemaining trigger files:")
        for file in sorted(remaining_files):
            if file.is_file():
                print(f"  - {file.name}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
























