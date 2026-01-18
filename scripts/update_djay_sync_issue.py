#!/usr/bin/env python3
"""
Update Notion issue with djay sync results
Issue ID: 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8
"""

import sys
from pathlib import Path

script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from notion_client import Client
from shared_core.notion.token_manager import get_notion_token
from shared_core.logging import setup_logging

workspace_logger = setup_logging()

ISSUE_ID = "2b5e7361-6c27-8147-8cbc-e73a63dbc8f8"
ISSUES_DB_ID = "229e73616c27808ebf06c202b10b5166"

def update_issue_status(issue_id: str, status: str, description: str = None):
    """Update issue status and description in Notion."""
    try:
        token = get_notion_token()
        if not token:
            workspace_logger.error("Notion token not available")
            return False
        
        notion = Client(auth=token)
        
        properties = {
            "Status": {"status": {"name": status}}
        }
        
        if description:
            properties["Description"] = {
                "rich_text": [{"text": {"content": description}}]
            }
        
        notion.pages.update(page_id=issue_id, properties=properties)
        workspace_logger.info(f"✅ Updated issue {issue_id} to status: {status}")
        return True
        
    except Exception as e:
        workspace_logger.error(f"❌ Error updating issue: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="In Progress", help="Status to set")
    parser.add_argument("--description", help="Description to add")
    args = parser.parse_args()
    
    update_issue_status(ISSUE_ID, args.status, args.description)
