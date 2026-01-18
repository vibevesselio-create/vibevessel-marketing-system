#!/usr/bin/env python3
"""
Query Agent-Tasks by their IDs from project relation
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

# Task IDs from the project's Agent-Tasks relation
TASK_IDS = [
    "63883678-ce77-4c91-8a6a-230a3f9b7db3",
    "0c28e2be-d5c5-4176-a9c7-38ad146760ec",
    "b6e1896a-46e5-4ec0-a400-71cdbb6e6a5d",
    "ff8a9eaa-8296-46f2-8266-fb9e538c636c",
    "4710421c-02e9-430b-a3fd-d07fbd36948e",
    "85df55bc-fa12-4883-9c30-b3d84ed6b6fe",
    "2e4e7361-6c27-81f8-ad58-c45c3707b49d",
    "2e4e7361-6c27-818e-b034-c360e5e7988a",
    "2e4e7361-6c27-81d1-b154-e3a1878708e9"
]

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
                return " ".join([item.get("plain_text", "") for item in text_list])
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
    
    tasks_info = []
    
    print("="*80)
    print("Querying Agent-Tasks by ID...")
    print("="*80)
    
    for task_id in TASK_IDS:
        try:
            task = client.pages.retrieve(page_id=task_id)
            
            task_title = safe_get_property(task, "Task Name", "title") or safe_get_property(task, "Name", "title") or "Untitled Task"
            task_status = safe_get_property(task, "Status", "status") or "Unknown"
            task_description = safe_get_property(task, "Description", "rich_text") or ""
            task_url = task.get("url", "")
            
            # Get assigned agent
            assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
            assigned_agent_id = assigned_agent_relation[0].get("id") if assigned_agent_relation else None
            
            task_info = {
                "id": task_id,
                "title": task_title,
                "status": task_status,
                "description": task_description,
                "url": task_url,
                "assigned_agent_id": assigned_agent_id,
                "task_data": task
            }
            tasks_info.append(task_info)
            
            print(f"\nTask: {task_title}")
            print(f"  Status: {task_status}")
            print(f"  ID: {task_id}")
            print(f"  URL: {task_url}")
            if task_description:
                print(f"  Description: {task_description[:300]}...")
                
        except Exception as e:
            print(f"Error retrieving task {task_id}: {e}")
            import traceback
            traceback.print_exc()
    
    # Filter out completed tasks
    outstanding_tasks = [t for t in tasks_info if t["status"] not in ["Complete", "Completed", "Done"]]
    
    # Sort by status priority
    status_priority = {
        "In-Progress": 0,
        "In Progress": 0,
        "Ready for Handoff": 1,
        "Not Started": 2,
        "Ready": 3,
        "Complete": 99,
        "Completed": 99,
        "Done": 99
    }
    
    outstanding_tasks.sort(key=lambda x: status_priority.get(x["status"], 99))
    
    print(f"\n{'='*80}")
    print(f"Found {len(outstanding_tasks)} outstanding task(s) out of {len(tasks_info)} total")
    print(f"{'='*80}")
    
    # Save to file
    output = {
        "project_id": "dc55d5da-ba67-41f3-a355-3b52f5b2697d",
        "all_tasks": tasks_info,
        "outstanding_tasks": outstanding_tasks
    }
    
    output_file = Path(__file__).parent / "project_agent_tasks_detailed.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_file}")
    
    return output

if __name__ == "__main__":
    main()
