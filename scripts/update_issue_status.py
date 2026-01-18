#!/usr/bin/env python3
"""
Update issue status after workflow spec resolution

ENVIRONMENT MANAGEMENT: Uses shared_core.notion.token_manager (MANDATORY)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# MANDATORY: Use centralized token manager
from shared_core.notion.token_manager import get_notion_token
from main import NotionManager

ISSUE_PAGE_ID = "2ce34994-b6bb-4efb-913a-527484baf2e1"

def update_issue_status():
    """Update issue status to Solution In Progress"""
    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not found")
        return False
    
    notion = NotionManager(token)
    
    # Update status to "Solution In Progress"
    update_properties = {
        "Status": {
            "status": {"name": "Solution In Progress"}
        }
    }
    
    success = notion.update_page(ISSUE_PAGE_ID, update_properties)
    
    if success:
        print(f"✓ Updated issue status to 'Solution In Progress'")
        return True
    else:
        print(f"✗ Failed to update issue status")
        return False

if __name__ == "__main__":
    update_issue_status()

