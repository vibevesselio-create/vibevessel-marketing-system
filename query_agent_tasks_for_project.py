#!/usr/bin/env python3
"""
Query Agent-Tasks for the In-Progress Project
"""

import os
import sys
import json
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

AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
PROJECT_ID = "2e5e7361-6c27-819d-91fc-dc2707c7b36a"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def safe_get_property(page, property_name):
    """Safely extract property value from Notion page."""
    try:
        properties = page.get("properties", {})
        prop = properties.get(property_name)
        if not prop:
            return None

        actual_type = prop.get("type")

        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list:
                return title_list[0].get("plain_text", "")
            return None
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list:
                return text_list[0].get("plain_text", "")
            return None
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None

        return None
    except Exception as e:
        return None


def query_project_tasks():
    """Query agent tasks for the project."""

    # Query tasks that are not complete (filter by status only)
    filter_params = {
        "filter": {
            "and": [
                {
                    "property": "Status",
                    "status": {"does_not_equal": "Completed"}
                },
                {
                    "property": "Status",
                    "status": {"does_not_equal": "Archived"}
                }
            ]
        },
        "sorts": [{"property": "Status", "direction": "ascending"}],
        "page_size": 20
    }

    try:
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{AGENT_TASKS_DB_ID}/query",
            headers=HEADERS,
            json=filter_params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        tasks = data.get("results", [])

        print(f"Found {len(tasks)} incomplete tasks for project")

        task_list = []
        for task in tasks:
            task_info = {
                "id": task.get("id"),
                "url": task.get("url"),
                "title": safe_get_property(task, "Task Name") or safe_get_property(task, "Name"),
                "status": safe_get_property(task, "Status"),
                "priority": safe_get_property(task, "Priority"),
                "description": safe_get_property(task, "Description")
            }
            task_list.append(task_info)
            print(f"  - [{task_info['status']}] {task_info['title']}")
            print(f"    ID: {task_info['id']}")
            print(f"    URL: {task_info['url']}")
            print()

        return task_list

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    tasks = query_project_tasks()

    # Save to file
    output_file = Path(__file__).parent / "project_incomplete_tasks.json"
    with open(output_file, "w") as f:
        json.dump(tasks, f, indent=2, default=str)

    print(f"\nSaved to {output_file}")
