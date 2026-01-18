#!/usr/bin/env python3
"""
Resolve VIBES Volume Reorganization Issue - Workflow Execution
Creates handoff triggers and updates issue status.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import (
    NotionManager,
    get_notion_token,
    safe_get_property,
    create_trigger_file,
    determine_agent_type,
    normalize_agent_folder_name,
    ISSUES_QUESTIONS_DB_ID,
    AGENT_TASKS_DB_ID,
    CLAUDE_MM1_AGENT_ID,
    CURSOR_MM1_AGENT_ID,
    MM1_AGENT_TRIGGER_BASE,
)

try:
    from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
    TASK_CREATION_AVAILABLE = True
except ImportError:
    TASK_CREATION_AVAILABLE = False

def main():
    """Main execution."""
    print("=" * 80)
    print("VIBES Volume Reorganization Issue Resolution Workflow")
    print("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        print("❌ Error: Could not get Notion token")
        return 1
    
    # Initialize Notion manager
    try:
        notion = NotionManager(token)
    except Exception as e:
        print(f"❌ Error initializing Notion manager: {e}")
        return 1
    
    issue_id = "2e4e7361-6c27-814c-b185-e57749b1dc47"
    
    # Get issue details
    try:
        issue = notion.client.pages.retrieve(page_id=issue_id)
        issue_title = safe_get_property(issue, "Name", "title") or "Untitled Issue"
        issue_url = issue.get("url", "")
        issue_description = safe_get_property(issue, "Description", "rich_text") or ""
        
        print(f"\nIssue: {issue_title}")
        print(f"URL: {issue_url}")
    except Exception as e:
        print(f"❌ Failed to retrieve issue: {e}")
        return 1
    
    # Get linked Agent-Tasks
    agent_tasks_relation = safe_get_property(issue, "Agent-Tasks", "relation") or []
    
    if agent_tasks_relation:
        print(f"\nFound {len(agent_tasks_relation)} linked Agent-Task(s)")
        
        # Process each task
        for task_ref in agent_tasks_relation:
            task_id = task_ref.get("id")
            try:
                task = notion.client.pages.retrieve(page_id=task_id)
                task_name = safe_get_property(task, "Task Name", "title") or safe_get_property(task, "Name", "title")
                task_status = safe_get_property(task, "Status", "status")
                task_url = task.get("url", "")
                task_description = safe_get_property(task, "Description", "rich_text") or ""
                
                print(f"\n  Task: {task_name}")
                print(f"  Status: {task_status}")
                print(f"  URL: {task_url}")
                
                # Get assigned agent
                assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
                assigned_agent_id = None
                assigned_agent_name = "Unknown Agent"
                
                if assigned_agent_relation and len(assigned_agent_relation) > 0:
                    assigned_agent_id = assigned_agent_relation[0].get("id")
                    assigned_agent_name = notion.get_page_title(assigned_agent_id) or f"Agent_{assigned_agent_id[:8]}"
                
                print(f"  Assigned Agent: {assigned_agent_name}")
                
                # Determine agent type
                agent_type = determine_agent_type(assigned_agent_name, assigned_agent_id)
                
                # Create handoff instructions
                handoff_instructions = f"""## Work Completed
- Enhanced reorganize_vibes_volume.py script with resume/checkpoint capability
- Added error handling and progress tracking
- Script ready for Phase 1 execution (metadata extraction and indexing)

## Next Steps
1. Review the enhanced script: `reorganize_vibes_volume.py`
2. Execute Phase 1: `python3 reorganize_vibes_volume.py --phase 1 --checkpoint logs/vibes_reorganization_checkpoint.json`
3. Monitor progress and use `--resume` flag if interrupted
4. Complete metadata extraction for all 20,148 files
5. Generate comprehensive file index
6. Proceed to Phase 2 (Deduplication Planning)

## Script Enhancements Made
- ✅ Resume capability with checkpoint files
- ✅ Progress tracking every 500 files
- ✅ Error recovery and retry logic
- ✅ Checkpoint saved on interruption

## Mandatory Handoff Requirements
Upon completion of this task, you MUST:
1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Update the task status in Notion
3. Create the next handoff trigger file for the execution agent (Cursor MM1 Agent) if work continues
4. Document all deliverables and artifacts
5. Provide all context needed for the next task to begin

**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created.
"""
                
                # Build task details for trigger file
                task_details = {
                    "task_id": task_id,
                    "task_title": task_name,
                    "task_url": task_url,
                    "project_id": None,
                    "project_title": None,
                    "description": task_description,
                    "status": task_status,
                    "agent_name": assigned_agent_name,
                    "agent_id": assigned_agent_id,
                    "priority": safe_get_property(task, "Priority", "select") or "High",
                    "handoff_instructions": handoff_instructions
                }
                
                # Create trigger file if task is ready
                if task_status in ["Ready", "Not Started", "Proposed", "Draft"]:
                    trigger_file = create_trigger_file(agent_type, assigned_agent_name, task_details)
                    if trigger_file:
                        print(f"  ✅ Created trigger file: {trigger_file}")
                    else:
                        print(f"  ⚠️  Failed to create trigger file")
                else:
                    print(f"  ℹ️  Task status '{task_status}' - skipping trigger file creation")
            
            except Exception as e:
                print(f"  ❌ Error processing task {task_id}: {e}")
                continue
    
    else:
        print("\n⚠️  No linked Agent-Tasks found")
        print("Creating a new execution task...")
        
        # Create execution task
        execution_description = f"""## Context
This task addresses the VIBES Volume Comprehensive Music Reorganization issue.

## Issue Details
- **Issue Title:** {issue_title}
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}

## Current State
The `/Volumes/VIBES/` volume contains:
- **670.24 GB** of music files
- **20,148 files** across **7,578 directories**
- Script framework created: `reorganize_vibes_volume.py`
- Implementation plan: `VIBES_VOLUME_REORGANIZATION_IMPLEMENTATION_PLAN.md`

## Work Completed
- ✅ Enhanced script with resume/checkpoint capability
- ✅ Added error handling and progress tracking
- ✅ Script ready for Phase 1 execution

## Objective
Execute Phase 1: Analysis & Indexing
- Extract metadata from all 20,148 files
- Generate audio fingerprints for deduplication
- Create comprehensive file index database
- Identify duplicate files

## Required Actions
1. Review enhanced script: `reorganize_vibes_volume.py`
2. Execute Phase 1 with checkpoint: `python3 reorganize_vibes_volume.py --phase 1 --checkpoint logs/vibes_reorganization_checkpoint.json`
3. Monitor progress (estimated 4-8 hours)
4. Use `--resume` flag if interrupted
5. Generate comprehensive index report
6. Proceed to Phase 2 when complete

## Success Criteria
- [ ] All 20,148 files processed
- [ ] Metadata extracted for all files
- [ ] File index database created
- [ ] Duplicate groups identified
- [ ] Phase 1 complete and documented
"""
        
        # Add mandatory next handoff instructions
        if TASK_CREATION_AVAILABLE:
            cursor_inbox_path = str(MM1_AGENT_TRIGGER_BASE / "Cursor-MM1-Agent" / "01_inbox") + "/"
            execution_description = add_mandatory_next_handoff_instructions(
                description=execution_description,
                next_task_name="VIBES Reorganization Phase 2: Deduplication Planning",
                target_agent="Cursor MM1 Agent",
                next_task_id="TO_BE_CREATED",
                inbox_path=cursor_inbox_path,
                project_name="VIBES-Reorganization",
                detailed_instructions=(
                    "Create handoff trigger file with Phase 1 results, duplicate analysis, "
                    "and deduplication plan. Include link to issue and Phase 1 task. "
                    "Ensure all deliverables and artifacts are documented."
                )
            )
        
        # Create task properties
        task_properties = {
            "Task Name": {
                "title": [{"text": {"content": "Execute: VIBES Volume Reorganization Phase 1"}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": execution_description[:1997]}}]
            },
            "Priority": {
                "select": {"name": "High"}
            },
            "Assigned-Agent": {
                "relation": [{"id": CURSOR_MM1_AGENT_ID}]
            },
            "Status": {
                "status": {"name": "Ready"}
            }
        }
        
        # Link to issue
        try:
            new_task = notion.create_page(AGENT_TASKS_DB_ID, task_properties)
            if new_task:
                task_id = new_task.get("id")
                task_url = new_task.get("url", "")
                
                # Link issue to task
                notion.update_page(issue_id, {
                    "Agent-Tasks": {
                        "relation": [{"id": task_id}]
                    }
                })
                
                print(f"✅ Created execution task: {task_url}")
                
                # Create trigger file
                task_details = {
                    "task_id": task_id,
                    "task_title": "Execute: VIBES Volume Reorganization Phase 1",
                    "task_url": task_url,
                    "project_id": None,
                    "project_title": None,
                    "description": execution_description,
                    "status": "Ready",
                    "agent_name": "Cursor MM1 Agent",
                    "agent_id": CURSOR_MM1_AGENT_ID,
                    "priority": "High",
                    "handoff_instructions": handoff_instructions
                }
                
                trigger_file = create_trigger_file("MM1", "Cursor MM1 Agent", task_details)
                if trigger_file:
                    print(f"✅ Created trigger file: {trigger_file}")
        except Exception as e:
            print(f"❌ Error creating task: {e}")
            import traceback
            traceback.print_exc()
    
    # Try to update issue status
    try:
        # Try "In Progress" first
        notion.update_page(issue_id, {
            "Status": {
                "status": {"name": "In Progress"}
            }
        })
        print(f"\n✅ Updated issue status to 'In Progress'")
    except Exception as e:
        print(f"⚠️  Could not update issue status: {e}")
        # Try "Open" as fallback
        try:
            notion.update_page(issue_id, {
                "Status": {
                    "status": {"name": "Open"}
                }
            })
            print(f"✅ Updated issue status to 'Open'")
        except Exception as e2:
            print(f"⚠️  Could not update issue status to 'Open' either: {e2}")
    
    print("\n" + "=" * 80)
    print("Workflow Complete")
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
