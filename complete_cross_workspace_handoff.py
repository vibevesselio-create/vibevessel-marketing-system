#!/usr/bin/env python3
"""
Complete Cross-Workspace Sync Handoff Task
Update task status and create handoff trigger files
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    from main import (
        create_trigger_file,
        determine_agent_type,
        normalize_agent_folder_name,
        MM1_AGENT_TRIGGER_BASE,
        MM2_AGENT_TRIGGER_BASE,
        safe_get_property,
        NotionManager
    )
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Task IDs
HANDOFF_TASK_ID = "4710421c-02e9-430b-a3fd-d07fbd36948e"
VALIDATION_TASK_ID_1 = "2e4e7361-6c27-818e-b034-c360e5e7988a"
VALIDATION_TASK_ID_2 = "2e4e7361-6c27-81d1-b154-e3a1878708e9"

def main():
    token = get_notion_token()
    if not token:
        print("❌ Error: Could not get Notion token")
        sys.exit(1)
    
    client = Client(auth=token)
    notion = NotionManager(token)
    
    # Step 1: Update handoff task status to Completed
    print("="*80)
    print("Updating Handoff Task Status...")
    print("="*80)
    
    try:
        client.pages.update(
            page_id=HANDOFF_TASK_ID,
            properties={
                "Status": {"status": {"name": "Completed"}}
            }
        )
        print(f"✅ Updated handoff task status to Completed")
    except Exception as e:
        print(f"⚠️  Error updating task status: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 2: Get validation task details
    print("\n" + "="*80)
    print("Retrieving Validation Task Details...")
    print("="*80)
    
    validation_tasks = []
    for task_id in [VALIDATION_TASK_ID_1, VALIDATION_TASK_ID_2]:
        try:
            task = client.pages.retrieve(page_id=task_id)
            task_title = safe_get_property(task, "Task Name", "title") or safe_get_property(task, "Name", "title") or "Untitled Task"
            task_status = safe_get_property(task, "Status", "status") or "Unknown"
            task_description = safe_get_property(task, "Description", "rich_text") or ""
            task_url = task.get("url", "")
            
            # Get assigned agent
            assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
            assigned_agent_id = assigned_agent_relation[0].get("id") if assigned_agent_relation else None
            
            # Determine agent name (default to ChatGPT Code Review Agent for validation tasks)
            agent_name = "ChatGPT Code Review Agent"
            if assigned_agent_id:
                # Try to get agent name from relation
                try:
                    agent_page = client.pages.retrieve(page_id=assigned_agent_id)
                    agent_name = safe_get_property(agent_page, "Name", "title") or agent_name
                except:
                    pass
            
            validation_tasks.append({
                "task_id": task_id,
                "task_title": task_title,
                "task_url": task_url,
                "task_status": task_status,
                "task_description": task_description,
                "assigned_agent_id": assigned_agent_id,
                "agent_name": agent_name
            })
            
            print(f"\nTask: {task_title}")
            print(f"  Status: {task_status}")
            print(f"  Agent: {agent_name}")
            
        except Exception as e:
            print(f"⚠️  Error retrieving task {task_id}: {e}")
            import traceback
            traceback.print_exc()
    
    # Step 3: Create handoff trigger files for validation tasks
    print("\n" + "="*80)
    print("Creating Handoff Trigger Files...")
    print("="*80)
    
    created_triggers = []
    
    for task_info in validation_tasks:
        agent_name = task_info["agent_name"]
        agent_id = task_info["assigned_agent_id"]
        
        # Determine agent type
        agent_type = determine_agent_type(agent_name, agent_id)
        
        # Create task details
        task_details = {
            "task_id": task_info["task_id"],
            "task_title": task_info["task_title"],
            "task_url": task_info["task_url"],
            "description": task_info["task_description"],
            "status": task_info["task_status"],
            "agent_name": agent_name,
            "agent_id": agent_id,
            "priority": "High",
            "handoff_instructions": (
                "VALIDATION TASK - Agent Work Validation\n\n"
                "This task requests a full review and validation of the Cross-Workspace Database Synchronization Phase 1 implementation work.\n\n"
                "SCOPE OF VALIDATION:\n"
                "1. Verify all 4 Phase 1 functions are implemented correctly\n"
                "2. Validate function signatures match specifications\n"
                "3. Review error handling adequacy\n"
                "4. Confirm logging integration completeness\n"
                "5. Check documentation alignment\n"
                "6. Validate handoff chain integrity\n\n"
                "COMPLETION SUMMARY:\n"
                "See: /Users/brianhellemn/Projects/github-production/CROSS_WORKSPACE_SYNC_PHASE1_COMPLETION_SUMMARY.md\n\n"
                "IMPLEMENTATION LOCATION:\n"
                "/Users/brianhellemn/Projects/github-production/gas-scripts/drive-sheets-sync/Code.js\n\n"
                "UPON COMPLETION:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed.\n"
                "2. Update the task status in Notion to 'Completed'\n"
                "3. Create a return handoff trigger file to Claude MM1 Agent for orchestration closure\n"
                "4. Document validation findings in Notion task\n"
                "5. Link validation report to project\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and return handoff is created."
            )
        }
        
        try:
            trigger_file = create_trigger_file(agent_type, agent_name, task_details)
            if trigger_file:
                created_triggers.append(trigger_file)
                print(f"✅ Created trigger file: {trigger_file}")
            else:
                print(f"⚠️  Failed to create trigger file for {task_info['task_title']}")
        except Exception as e:
            print(f"⚠️  Error creating trigger file for {task_info['task_title']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Step 4: Create validation task in Agent-Tasks database
    print("\n" + "="*80)
    print("Creating Validation Task in Notion...")
    print("="*80)
    
    try:
        from main import AGENT_TASKS_DB_ID
        
        validation_task_properties = {
            "Task Name": {
                "title": [{"text": {"content": "[Validation] Cross-Workspace Sync Phase 1 - Work Review & Validation"}}]
            },
            "Status": {"status": {"name": "Ready"}},
            "Priority": {"select": {"name": "High"}},
            "Description": {
                "rich_text": [{"text": {"content": (
                    "AGENT WORK VALIDATION TASK - Created 2026-01-10\n\n"
                    "Created by: Cursor MM1 Agent\n"
                    "Target Reviewer: ChatGPT Code Review Agent\n\n"
                    "SCOPE OF VALIDATION:\n"
                    "1. Cross-Workspace Database Synchronization Phase 1 implementation verification\n"
                    "2. Code quality and standards compliance review\n"
                    "3. Documentation completeness validation\n"
                    "4. Handoff chain integrity verification\n\n"
                    "WORK TO VALIDATE:\n"
                    "- Phase 1 Implementation: All 4 core functions implemented\n"
                    "- Completion Summary: CROSS_WORKSPACE_SYNC_PHASE1_COMPLETION_SUMMARY.md\n"
                    "- Implementation Location: gas-scripts/drive-sheets-sync/Code.js\n"
                    "- Project: Cross-Workspace Database Synchronization — Implementation\n\n"
                    "VERIFICATION CHECKLIST:\n"
                    "- [ ] All 4 core functions implemented correctly\n"
                    "- [ ] Functions match specified signatures\n"
                    "- [ ] Error handling adequate\n"
                    "- [ ] Logging integration complete\n"
                    "- [ ] Documentation updated\n"
                    "- [ ] Handoff chain complete\n\n"
                    "UPON COMPLETION:\n"
                    "Create return handoff to Claude MM1 Agent for orchestration closure."
                )}}]
            },
            "Projects": {
                "relation": [{"id": "dc55d5da-ba67-41f3-a355-3b52f5b2697d"}]
            }
        }
        
        validation_task = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=validation_task_properties
        )
        
        validation_task_id = validation_task.get("id")
        print(f"✅ Created validation task: {validation_task_id}")
        
        # Create trigger file for the new validation task
        task_details = {
            "task_id": validation_task_id,
            "task_title": "[Validation] Cross-Workspace Sync Phase 1 - Work Review & Validation",
            "task_url": validation_task.get("url", ""),
            "description": "Agent work validation task",
            "status": "Ready",
            "agent_name": "ChatGPT Code Review Agent",
            "agent_id": None,
            "priority": "High",
            "handoff_instructions": (
                "VALIDATION TASK - Agent Work Validation\n\n"
                "Review and validate the Cross-Workspace Database Synchronization Phase 1 implementation.\n\n"
                "See completion summary for details."
            )
        }
        
        trigger_file = create_trigger_file("MM1", "ChatGPT Code Review Agent", task_details)
        if trigger_file:
            created_triggers.append(trigger_file)
            print(f"✅ Created trigger file for new validation task: {trigger_file}")
        
    except Exception as e:
        print(f"⚠️  Error creating validation task: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"✅ Handoff task updated to Completed")
    print(f"✅ Created {len(created_triggers)} trigger file(s)")
    for trigger in created_triggers:
        print(f"   - {trigger}")
    
    return {
        "handoff_task_updated": True,
        "triggers_created": len(created_triggers),
        "trigger_files": [str(t) for t in created_triggers]
    }

if __name__ == "__main__":
    main()
