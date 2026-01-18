#!/usr/bin/env python3
"""
Update Agent-Task Status to Completed

Updates the Unified Env Token Pattern Remediation Agent-Task to Completed.
"""

import os
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from shared_core.notion.token_manager import get_notion_token
    NOTION_TOKEN = get_notion_token()
except ImportError:
    NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")

if not NOTION_TOKEN:
    print("Error: No Notion token available")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Agent-Task ID for Unified Env Token Pattern Remediation
TASK_ID = "2e7e7361-6c27-81ef-aad1-e463174b8a51"

def update_task_status():
    """Update task status to Completed."""
    try:
        response = httpx.patch(
            f"https://api.notion.com/v1/pages/{TASK_ID}",
            headers=HEADERS,
            json={
                "properties": {
                    "Status": {"status": {"name": "Completed"}}
                }
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        print(f"Successfully updated Agent-Task status to 'Completed'")
        print(f"Task URL: {data.get('url', 'N/A')}")
        return True
    except Exception as e:
        print(f"Error updating task: {e}")
        return False

if __name__ == "__main__":
    update_task_status()
