#!/usr/bin/env python3
"""
Create handoff for next highest-priority incomplete task without existing trigger file.
This script finds the first task that doesn't have a trigger file and creates one.
"""

import os
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import (
    get_notion_token,
    NotionManager,
    safe_get_property,
    determine_agent_type,
    normalize_agent_folder_name,
    create_trigger_file,
    AGENT_TASKS_DB_ID,
    MM1_AGENT_TRIGGER_BASE,
    MM2_AGENT_TRIGGER_BASE,
)

# Import from continuous_handoff_processor
from scripts.continuous_handoff_processor import (
    get_incomplete_tasks,
    determine_best_agent,
    check_existing_trigger_file,
    AGENT_MAPPING,
)

def create_handoff_for_next_task():
    """Find next task without trigger file and create handoff"""
    token = get_notion_token()
    if not token:
        print("ERROR: No Notion token")
        return False
    
    notion = NotionManager(token)
    
    print("Querying for incomplete tasks...")
    tasks = get_incomplete_tasks(notion)
    
    if not tasks:
        print("No incomplete tasks found.")
        return False
    
    print(f"Found {len(tasks)} incomplete task(s)")
    print("")
    
    # Find first task without existing trigger file
    for task in tasks:
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_status = safe_get_property(task, "Status", "status") or "Unknown"
        task_priority = safe_get_property(task, "Priority", "select") or "Medium"
        task_url = task.get("url", "")
        task_description = safe_get_property(task, "Description", "rich_text") or ""
        next_step = safe_get_property(task, "Next Required Step", "rich_text") or ""
        success_criteria = safe_get_property(task, "Success Criteria", "rich_text") or ""
        
        print(f"Checking task: {task_title}")
        print(f"  Priority: {task_priority}")
        print(f"  Status: {task_status}")
        
        # Determine best agent
        agent_name, agent_id = determine_best_agent(task, notion)
        
        if not agent_name or not agent_id:
            print(f"  → Could not determine agent. Skipping.")
            print("")
            continue
        
        print(f"  → Assigned to: {agent_name}")
        
        # Check if trigger file already exists
        if check_existing_trigger_file(task_id, agent_name, agent_id):
            print(f"  → Trigger file already exists. Skipping.")
            print("")
            continue
        
        # Create trigger file
        print(f"  → Creating handoff file for {agent_name}...")
        
        # Build handoff instructions
        handoff_instructions = f"""Proceed with the execution of this task. Upon completion, you MUST:

1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.

2. Update the task status in Notion to 'Complete'

3. Document all work comprehensively in Notion

4. Verify production execution and workspace requirements are met

5. A review handoff task will be automatically created back to Cursor MM1 Agent for validation

**MANDATORY:** Task is NOT complete until trigger file is manually moved, status is updated, and all documentation is complete.

## Task Details

**Next Required Step:** {next_step if next_step else "Execute the task as described"}

**Success Criteria:** {success_criteria if success_criteria else "All task requirements met, documented, and validated"}
"""
        
        # Prepare task_details
        task_details = {
            "task_id": task_id,
            "task_title": task_title,
            "task_url": task_url,
            "description": task_description,
            "status": task_status,
            "agent_id": agent_id,
            "handoff_instructions": handoff_instructions,
            "priority": task_priority
        }
        
        agent_type = determine_agent_type(agent_name, agent_id)
        trigger_file = create_trigger_file(agent_type, agent_name, task_details)
        time.sleep(0.5)  # Pause after creating trigger file
        
        if trigger_file:
            print(f"  → Created trigger file: {trigger_file}")
            
            # Update task status to In Progress
            if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
                update_properties = {
                    "Status": {"status": {"name": "In Progress"}}
                }
                notion.update_page(task_id, update_properties)
                time.sleep(0.5)
                print(f"  → Updated task status to 'In Progress'")
            
            print("")
            print("=" * 60)
            print("SUCCESS: Handoff task created!")
            print(f"Task: {task_title}")
            print(f"Agent: {agent_name}")
            print(f"Trigger File: {trigger_file}")
            print("=" * 60)
            return True
        else:
            print(f"  → Failed to create trigger file")
            print("")
            continue
    
    print("No tasks found without existing trigger files.")
    return False

if __name__ == "__main__":
    create_handoff_for_next_task()






























