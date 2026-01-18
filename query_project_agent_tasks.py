#!/usr/bin/env python3
"""
Query Agent-Tasks for a specific project
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
PROJECT_ID = "dc55d5da-ba67-41f3-a355-3b52f5b2697d"

def safe_get_property(page: dict, property_name: str, property_type: str = None):
    """Safely extract property value from Notion page."""
    try:
        properties = page.get("properties", {})
        if not properties:
            return None
        
        prop = properties.get(property_name)
        if not prop:
            return None
        
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            return None
        
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return relation_list
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list if item.get("name")]
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def main():
    token = get_notion_token()
    if not token:
        print("❌ Error: Could not get Notion token")
        sys.exit(1)
    
    client = Client(auth=token)
    
    # Get all agent tasks and filter by project relation
    try:
        response = client.databases.query(
            database_id=AGENT_TASKS_DB_ID,
            page_size=100
        )
        all_tasks = response.get("results", [])
        
        # Filter tasks that relate to our project
        project_tasks = []
        for task in all_tasks:
            # Agent-Tasks schema in this workspace uses a relation named "🤖 Agent-Projects".
            # Older scripts used "Projects"/"Project" which may not exist.
            agent_projects_relation = safe_get_property(task, "🤖 Agent-Projects", "relation") or []
            projects_relation = safe_get_property(task, "Projects", "relation") or []
            project_relation = safe_get_property(task, "Project", "relation") or []
            
            # Check if this task relates to our project
            related_ids = [r.get("id") for r in (agent_projects_relation + projects_relation + project_relation)]
            if PROJECT_ID in related_ids:
                project_tasks.append(task)
        
        print(f"Found {len(project_tasks)} agent task(s) for project")
        
        # Get task details
        tasks_info = []
        for task in project_tasks:
            task_id = task.get("id")
            task_title = safe_get_property(task, "Task Name", "title") or safe_get_property(task, "Name", "title") or "Untitled Task"
            task_status = safe_get_property(task, "Status", "status") or "Unknown"
            task_description = safe_get_property(task, "Description", "rich_text") or ""
            task_url = task.get("url", "")
            
            # Assigned agent is a rollup in current Agent-Tasks schema; keep as None here
            assigned_agent = None
            
            task_info = {
                "id": task_id,
                "title": task_title,
                "status": task_status,
                "description": task_description,
                "url": task_url,
                "assigned_agent_id": assigned_agent,
                "task_data": task
            }
            tasks_info.append(task_info)
            
            print(f"\nTask: {task_title}")
            print(f"  Status: {task_status}")
            print(f"  ID: {task_id}")
            print(f"  URL: {task_url}")
            if task_description:
                print(f"  Description: {task_description[:200]}...")
        
        # Sort by status priority
        status_priority = {
            "In Progress": 0,
            "Review": 1,
            "Ready": 2,
            "Planning": 3,
            "Draft": 4,
            "Blocked": 5,
            "Failed": 6,
            "Completed": 99,
            "Archived": 100,
        }
        
        tasks_info.sort(key=lambda x: status_priority.get(x["status"], 99))
        
        # Save to file
        output = {
            "project_id": PROJECT_ID,
            "tasks": tasks_info
        }
        
        output_file = Path(__file__).parent / "project_agent_tasks.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
        
        print(f"\n{'='*80}")
        print(f"Results saved to: {output_file}")
        print(f"{'='*80}")
        
        return output
        
    except Exception as e:
        print(f"Error querying agent tasks: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    main()
