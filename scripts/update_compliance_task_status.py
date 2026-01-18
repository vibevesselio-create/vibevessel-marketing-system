#!/usr/bin/env python3
"""
Update Return Handoff Compliance Monitoring Task Status

Updates the task status in Notion to reflect completion.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Task ID
TASK_ID = "2e0e7361-6c27-81a5-9f13-fd53ab786359"

def main():
    """Update task status"""
    print(f"Updating task status for {TASK_ID}...")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    # Update task status to "Complete" or "Completed"
    update_properties = {
        "Status": {"status": {"name": "Completed"}}
    }
    
    if notion.update_page(TASK_ID, update_properties):
        print(f"✅ Task status updated to 'Completed'")
        
        # Also add a note in the description about completion
        print("✅ Task status updated successfully")
        return 0
    else:
        # Try "Complete" if "Completed" doesn't work
        update_properties = {
            "Status": {"status": {"name": "Complete"}}
        }
        if notion.update_page(TASK_ID, update_properties):
            print(f"✅ Task status updated to 'Complete'")
            return 0
        else:
            print("❌ Failed to update task status")
            return 1

if __name__ == "__main__":
    sys.exit(main())



























