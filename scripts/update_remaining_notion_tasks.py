#!/usr/bin/env python3
"""
Update Remaining Notion Tasks

Updates status for tasks that are completed but still show as Ready.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Tasks that need status updates based on analysis
TASKS_TO_UPDATE = {
    # Validation task - issue already resolved
    "2dfe7361-6c27-815d-bcbc-e4b0c939a946": {
        "name": "Agent Work Validation: DriveSheetsSync Duplicate Folder Fix",
        "status": "Completed",
        "reason": "Related issue 2d9e7361-6c27-816e-b547-cc573b2224c7 is Resolved"
    },
}

def update_task_status(task_id: str, status: str, notion: NotionManager) -> bool:
    """Update task status in Notion"""
    try:
        update_properties = {
            "Status": {"status": {"name": status}}
        }
        
        if notion.update_page(task_id, update_properties):
            print(f"  ✅ Updated to '{status}'")
            return True
        else:
            # Try alternatives
            for alt in ["Complete", "Done"]:
                update_properties = {"Status": {"status": {"name": alt}}}
                if notion.update_page(task_id, update_properties):
                    print(f"  ✅ Updated to '{alt}' (alternative)")
                    return True
            print(f"  ❌ Failed to update")
            return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main execution"""
    print("=" * 80)
    print("Update Remaining Notion Tasks")
    print("=" * 80)
    print()
    
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    updated = 0
    for task_id, info in TASKS_TO_UPDATE.items():
        print(f"📋 {info['name']}")
        print(f"   Task ID: {task_id}")
        print(f"   Reason: {info['reason']}")
        if update_task_status(task_id, info['status'], notion):
            updated += 1
        print()
    
    print("=" * 80)
    print(f"✅ Updated {updated}/{len(TASKS_TO_UPDATE)} tasks")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
























