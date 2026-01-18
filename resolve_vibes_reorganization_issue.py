#!/usr/bin/env python3
"""
Resolve VIBES Volume Reorganization Issue
Creates implementation plan and handoff tasks.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    print("ERROR: notion-client not available")
    NOTION_AVAILABLE = False
    sys.exit(1)

try:
    from shared_core.notion.token_manager import get_notion_token
    token = get_notion_token()
except ImportError:
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("NOTION_API_KEY")

if not token:
    print("ERROR: No Notion token found")
    sys.exit(1)

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"

# Agent IDs
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"

client = Client(auth=token)

def safe_get_property(page, property_name, property_type=None):
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
            if text_list:
                return ''.join([t.get("plain_text", "") for t in text_list])
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
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def get_database_status_options(database_id):
    """Get available status options for a database."""
    try:
        db = client.databases.retrieve(database_id=database_id)
        status_prop = db.get("properties", {}).get("Status", {})
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            return [opt.get("name") for opt in status_options if opt.get("name")]
    except Exception:
        pass
    return []

def create_agent_task(title, description, assigned_agent_id, priority="High", project_id=None, issue_id=None):
    """Create an Agent-Task in Notion."""
    print(f"\nCreating Agent-Task: {title}")
    
    # Get valid status options
    status_options = get_database_status_options(AGENT_TASKS_DB_ID)
    default_status = None
    for status in ["Ready", "Not Started", "Draft", "Proposed"]:
        if status in status_options:
            default_status = status
            break
    if not default_status and status_options:
        default_status = status_options[0]
    
    properties = {
        "Task Name": {
            "title": [{"text": {"content": title}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": description[:1997]}}]  # Notion limit
        },
        "Priority": {
            "select": {"name": priority}
        },
        "Assigned-Agent": {
            "relation": [{"id": assigned_agent_id}]
        }
    }
    
    if default_status:
        properties["Status"] = {
            "status": {"name": default_status}
        }
    
    if project_id:
        # Try "Projects" (plural) first, then "Project" (singular)
        try:
            properties["Projects"] = {
                "relation": [{"id": project_id}]
            }
        except Exception:
            try:
                properties["Project"] = {
                    "relation": [{"id": project_id}]
                }
            except Exception:
                pass
    
    try:
        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        task_id = response.get("id")
        task_url = response.get("url", "")
        print(f"✅ Created Agent-Task: {task_url}")
        
        # Link issue to task if provided
        if issue_id:
            try:
                # Try to link via "Agent-Tasks" relation in Issues database
                client.pages.update(
                    page_id=issue_id,
                    properties={
                        "Agent-Tasks": {
                            "relation": [{"id": task_id}]
                        }
                    }
                )
                print(f"✅ Linked issue to task")
            except Exception as e:
                print(f"⚠️  Could not link issue to task: {e}")
        
        return task_id, task_url
    except Exception as e:
        print(f"❌ Failed to create Agent-Task: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def create_trigger_file(agent_type, agent_name, task_details, trigger_base_path):
    """Create trigger file for agent."""
    from datetime import datetime, timezone
    
    agent_folder = agent_name.replace(" ", "-")
    if agent_type == "MM2":
        agent_folder = f"{agent_folder}-gd"
    
    trigger_folder = trigger_base_path / agent_folder / "01_inbox"
    trigger_folder.mkdir(parents=True, exist_ok=True)
    
    # Check for existing trigger file
    task_id = task_details.get("task_id", "unknown")
    if task_id != "unknown":
        task_id_short = task_id.replace("-", "")[:8]
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            check_folder = trigger_base_path / agent_folder / subfolder
            if check_folder.exists():
                existing_files = list(check_folder.glob(f"*{task_id_short}*.json"))
                if existing_files:
                    print(f"⚠️  Trigger file already exists: {existing_files[0].name}")
                    return existing_files[0]
    
    # Generate filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    task_id_short = task_id.replace("-", "")[:8] if task_id != "unknown" else "unknown"
    task_title = task_details.get("task_title", "Task")
    safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
    filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.json"
    
    trigger_file = trigger_folder / filename
    
    trigger_content = {
        "task_id": task_details.get("task_id"),
        "task_title": task_details.get("task_title"),
        "task_url": task_details.get("task_url", ""),
        "project_id": task_details.get("project_id"),
        "project_title": task_details.get("project_title"),
        "description": task_details.get("description", ""),
        "status": task_details.get("status"),
        "agent_name": agent_name,
        "agent_type": agent_type,
        "handoff_instructions": task_details.get("handoff_instructions", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "priority": task_details.get("priority", "High")
    }
    
    with open(trigger_file, "w", encoding="utf-8") as f:
        json.dump(trigger_content, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Created trigger file: {trigger_file}")
    return trigger_file

def main():
    """Main execution."""
    print("=" * 80)
    print("VIBES Volume Reorganization Issue Resolution")
    print("=" * 80)
    
    issue_id = "2e4e7361-6c27-814c-b185-e57749b1dc47"
    
    # Get issue details
    try:
        issue_page = client.pages.retrieve(page_id=issue_id)
        issue_title = safe_get_property(issue_page, "Name", "title") or "Untitled Issue"
        issue_description = safe_get_property(issue_page, "Description", "rich_text") or ""
        issue_url = issue_page.get("url", "")
        
        print(f"\nIssue: {issue_title}")
        print(f"URL: {issue_url}")
    except Exception as e:
        print(f"❌ Failed to retrieve issue: {e}")
        return
    
    # Create implementation plan task
    plan_description = f"""## Context
This task addresses the VIBES Volume Comprehensive Music Reorganization issue.

## Issue Details
- **Issue Title:** {issue_title}
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}

## Current State
The `/Volumes/VIBES/` volume contains:
- **670.24 GB** of music files
- **20,148 files** across **7,578 directories**
- Fragmented structure with multiple auto-import directories
- Duplicate files across different locations
- Inconsistent naming and organization

## Objective
Create a comprehensive implementation plan for reorganizing the VIBES volume according to the production music workflow specifications.

## Required Actions
1. Analyze current directory structure and file distribution
2. Review production workflow specifications for target organization
3. Design reorganization strategy that preserves all files
4. Create deduplication plan using existing fingerprint system
5. Design migration path that minimizes disruption
6. Identify automation opportunities
7. Create detailed task breakdown for execution phase
8. Estimate time and resources required

## Deliverables
- [ ] Detailed analysis of current state
- [ ] Target directory structure design
- [ ] Deduplication strategy document
- [ ] Migration plan with rollback procedures
- [ ] Task breakdown for execution phase
- [ ] Risk assessment and mitigation strategies

## Success Criteria
- [ ] Complete implementation plan created
- [ ] All deliverables documented
- [ ] Next handoff task created for execution phase
- [ ] Plan reviewed and approved

## Next Handoff
Upon completion, create a handoff task for **Cursor MM1 Agent** to begin execution of the reorganization plan.
"""
    
    plan_task_id, plan_task_url = create_agent_task(
        title=f"Plan: VIBES Volume Reorganization Implementation",
        description=plan_description,
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,
        priority="High",
        issue_id=issue_id
    )
    
    if plan_task_id:
        # Create trigger file for Claude MM1 Agent
        MM1_TRIGGER_BASE = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
        
        task_details = {
            "task_id": plan_task_id,
            "task_title": f"Plan: VIBES Volume Reorganization Implementation",
            "task_url": plan_task_url,
            "project_id": None,
            "project_title": None,
            "description": plan_description,
            "status": "Ready",
            "priority": "High",
            "handoff_instructions": (
                "Review the issue and create a comprehensive implementation plan. "
                "Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                "2. Update the task status in Notion\n"
                "3. Create a handoff task for Cursor MM1 Agent to execute the plan\n"
                "4. Document all deliverables\n"
                "5. Provide all context needed for execution to begin\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
            )
        }
        
        create_trigger_file("MM1", "Claude-MM1-Agent", task_details, MM1_TRIGGER_BASE)
    
    # Update issue status to "In Progress"
    try:
        client.pages.update(
            page_id=issue_id,
            properties={
                "Status": {
                    "status": {"name": "In Progress"}
                }
            }
        )
        print(f"\n✅ Updated issue status to 'In Progress'")
    except Exception as e:
        print(f"⚠️  Could not update issue status: {e}")
    
    print("\n" + "=" * 80)
    print("Issue Resolution Setup Complete")
    print("=" * 80)
    print(f"✅ Created planning task: {plan_task_url}")
    print(f"✅ Created trigger file for Claude MM1 Agent")
    print(f"✅ Updated issue status to 'In Progress'")

if __name__ == "__main__":
    main()
