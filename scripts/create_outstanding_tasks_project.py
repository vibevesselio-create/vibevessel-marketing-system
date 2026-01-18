#!/usr/bin/env python3
"""
Create Outstanding Tasks Project

Creates a highest-priority Agent-Project for completing all outstanding tasks
with refactored tasks linked to it.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Database IDs
AGENT_TASKS_DB_ID = "284e7361-6c27-8018-872a-eb14e82e0392"
AGENT_PROJECTS_DB_ID = "286e7361-6c27-81ff-a450-db2ecad4b0ba"

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
CLAUDE_CODE_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Review agent

# Outstanding tasks to create
OUTSTANDING_TASKS = [
    {
        "title": "Return Handoff Enforcement Compliance — Create Validation & Monitoring",
        "description": """## Context
A persistent non-compliance issue has been identified: Agents are NOT creating return handoff tasks when completing assigned work.

## Related Issue
- **Issue ID:** 2dae7361-6c27-8103-8c3e-c01ee11b6a2f
- **Issue Title:** Persistent Non-Compliance: Agents Not Creating Return Handoff Tasks
- **Priority:** Highest

## Required Actions
1. Review and validate STEP 7 documentation in AGENT_HANDOFF_TASK_GENERATOR_V3.0.md
2. Create validation script at /Users/brianhellemn/Documents/Agents/Agent-Triggers/scripts/validate_return_handoffs.py
3. Update agent prompts/rules to include explicit return handoff enforcement
4. Generate compliance report showing current state
5. Update issue status in Notion

## Success Criteria
- [ ] STEP 7 documentation validated and complete
- [ ] Validation script created and functional
- [ ] Compliance report generated
- [ ] Agent prompts updated with explicit return handoff enforcement
- [ ] Issue status updated to Solution In Progress or Resolved

## MANDATORY RETURN HANDOFF
Upon completion, create return handoff to Claude Code Agent with validation results.""",
        "trigger_file": "20260105T120000Z__HANDOFF__Return-Handoff-Enforcement-Compliance__Cursor-MM1.json",
        "existing_task_id": "2dfe7361-6c27-8194-9bff-c2b0c28a40f4"
    },
    {
        "title": "Stale Trigger Cleanup and Issue Triage",
        "description": """## Context
Several handoff files in agent inboxes are stale (referencing already-resolved issues).

## Required Actions
1. Move stale handoffs to 02_processed
2. Update Notion Task Statuses
3. Validate In-Progress Projects
4. Process Cloudflare DNS Issue (requires human dashboard access)

## Success Criteria
- [ ] All stale handoff files moved to 02_processed
- [ ] Inbox file count reduced to only active/pending items
- [ ] Notion task statuses accurately reflect current state
- [ ] Return handoff created documenting cleanup results""",
        "trigger_file": "20260105T060000Z__HANDOFF__Stale-Trigger-Cleanup-And-Issue-Triage__Claude-Opus.md"
    },
    {
        "title": "iPad Library P1 Tasks — BPM Analysis & Notion Sync",
        "description": """## Context
P0 tasks for iPad Library Integration have been completed. This task continues with P1 priority work.

## Objective
Complete the remaining P1 tasks to resolve BLOCKER issue 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8.

## Required Actions
1. Run BPM/key analysis on 3,262 missing tracks
2. Cross-reference Notion Tracks DB with djay library
3. Create Notion sync task for discovered tracks
4. Update issue status to Resolved upon completion

## Success Criteria
- [ ] BPM/key analysis completed for all 3,262 tracks
- [ ] Cross-reference report generated
- [ ] Notion Tracks DB updated with new tracks
- [ ] Issue marked Resolved in Notion""",
        "trigger_file": "20260104T091300Z__HANDOFF__iPad-Library-P1-BPM-Analysis-Notion-Sync__2dee7361.json",
        "existing_task_id": "2dee7361-6c27-814a-99e2-c0c6bbf39800",
        "related_issue": "2b5e7361-6c27-8147-8cbc-e73a63dbc8f8"
    },
    {
        "title": "Critical Blockers Investigation",
        "description": """## Context
Two CRITICAL/BLOCKER issues require investigation and resolution:
1. BLOCKER: iPad Library Integration Not Analyzed
2. [BLOCKER] Services Registry STEP 0/1 — Notion DNS Resolution Failure

## Required Actions
1. Investigate iPad Library Integration requirements and document findings
2. Analyze Notion DNS resolution failure and implement fix
3. Update issue status in Notion after resolution
4. Document all findings and changes
5. Create handoff to validation agent when complete

## Success Criteria
- [ ] Both blocker issues have clear resolution paths documented
- [ ] At least one blocker fully resolved with Notion status updated
- [ ] Handoff created for validation of completed work
- [ ] Any blocking dependencies clearly documented""",
        "trigger_file": "20260103T180000Z__HANDOFF__Critical-Blockers-Investigation__claude-opus.json"
    },
    {
        "title": "Music Library Remediation Execution",
        "description": """## Context
Code fixes have been verified and deployed to music_library_remediation.py.

## Required Actions
1. Execute Music Library Remediation script
2. Process 8 audio tracks (BPM/key analysis)
3. iPad library integration
4. Update Notion with audio metadata

## Success Criteria
- [ ] music_library_remediation.py executes without errors
- [ ] At least 3 remediation actions completed successfully
- [ ] Audio metadata (BPM, Key) added to at least 5 tracks
- [ ] Eagle library updated with new tracks
- [ ] No data loss from move operations""",
        "trigger_file": "20260103T214500Z__HANDOFF__Music-Library-Remediation-Execution__Claude-Opus.md",
        "related_issue": "2b5e7361-6c27-8147-8cbc-e73a63dbc8f8"
    },
    {
        "title": "Notion Token Redaction and Rotation",
        "description": """## Context
Local token redaction completed. Token rotation and Notion updates still required.

## Required Actions
1. Rotate Notion tokens (all integrations referenced by repo)
2. Update environment variables in relevant runtime locations
3. Locate and scrub any launchd plist files with hardcoded NOTION_API_TOKEN
4. Update Issues+Questions entry with remediation steps and current status
5. Create downstream handoff for any remaining work

## Success Criteria
- [ ] Notion tokens rotated and stored only in env/.env
- [ ] No plaintext tokens in repo or launchd plists
- [ ] Issues+Questions entry updated with actions and verification notes
- [ ] Follow-up trigger file created for any remaining work""",
        "trigger_file": "20260104T183511Z__HANDOFF__Notion-Token-Redaction-Rotation__Cursor-MM1-Agent.json"
    },
    {
        "title": "Music Sync Handoff — Audio Processing",
        "description": """## Context
Music Track Sync workflow completed. 10 new tracks synced to Notion and downloaded. Audio processing required.

## Required Actions
1. BPM analysis for all downloaded tracks
2. Key detection for all downloaded tracks
3. Eagle library import for all downloaded tracks
4. Update Notion with audio metadata (BPM, Key, etc.)
5. Attempt YouTube fallback download for missing tracks

## Success Criteria
- [ ] BPM analysis completed for all 8 downloaded tracks
- [ ] Key detection completed for all tracks
- [ ] Eagle library updated with new tracks
- [ ] Notion metadata updated
- [ ] Alternative sources attempted for missing tracks""",
        "trigger_file": "music-sync-handoff-2026-01-03.md"
    },
    {
        "title": "GAS Bridge Script Location Resolution — Unblock Critical Task",
        "description": """## Context
The '[Phase 1.2] Fix GAS Bridge Script Syntax Errors' task is blocked due to unknown script location.

## Required Actions
1. Verify Task Target Script - Check Notion task for script URL/ID
2. Check Slack-KM Bridge for Syntax Errors
3. Search for Additional GAS Scripts in Google Drive
4. Check Google Apps Script Dashboard for KM-related projects
5. Once located, fix 8 syntax errors and deploy

## Success Criteria
- [ ] Identify the exact GAS script with 8 syntax errors
- [ ] Fix all 8 syntax errors in the script
- [ ] Deploy fixed script using clasp push
- [ ] Update Notion task to Complete
- [ ] Create validation handoff""",
        "trigger_file": "20260105T050810Z__HANDOFF__GAS-Bridge-Script-Location-Resolution__Claude-Opus.json",
        "related_task": "08cc9525-8740-4ad7-9711-21ee5700a3df"
    }
]

def create_project(notion: NotionManager) -> str:
    """Create the highest priority project"""
    project_title = "Outstanding Tasks Completion — 2026-01-06"
    
    project_properties = {
        "Project Name": {
            "title": [{"text": {"content": project_title}}]
        },
        "Priority": {
            "select": {"name": "Highest"}
        },
        "Status": {
            "status": {"name": "In Progress"}
        }
    }
    
    try:
        response = notion.create_page(
            parent_database_id=AGENT_PROJECTS_DB_ID,
            properties=project_properties
        )
        if response:
            project_id = response.get("id")
            print(f"✅ Created project: {project_title}")
            print(f"   Project ID: {project_id}")
            return project_id
        else:
            print(f"❌ Failed to create project")
            return None
    except Exception as e:
        print(f"❌ Error creating project: {e}")
        return None

def create_task(notion: NotionManager, task_info: dict, project_id: str) -> str:
    """Create or update a task"""
    # Check if task already exists
    task_id = task_info.get("existing_task_id")
    
    if task_id:
        # Update existing task
        update_properties = {
            "Priority": {"select": {"name": "Highest"}},
            "🤖 Agent-Projects": {"relation": [{"id": project_id}]},
            "Assigned-Agent": {"relation": [{"id": CURSOR_MM1_AGENT_ID}]}
        }
        
        try:
            if notion.update_page(task_id, update_properties):
                print(f"  ✅ Updated existing task: {task_info['title']}")
                return task_id
        except Exception as e:
            print(f"  ⚠️  Could not update task {task_id}: {e}")
            # Continue to create new task
    
    # Create new task
    task_properties = {
        "Task Name": {
            "title": [{"text": {"content": task_info["title"]}}]
        },
        "Priority": {
            "select": {"name": "Highest"}
        },
        "Status": {
            "status": {"name": "Ready"}
        },
        "🤖 Agent-Projects": {
            "relation": [{"id": project_id}]
        },
        "Assigned-Agent": {
            "relation": [{"id": CURSOR_MM1_AGENT_ID}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_info["description"]}}]
        }
    }
    
    try:
        response = notion.create_page(
            parent_database_id=AGENT_TASKS_DB_ID,
            properties=task_properties
        )
        if response:
            new_task_id = response.get("id")
            print(f"  ✅ Created new task: {task_info['title']}")
            print(f"     Task ID: {new_task_id}")
            return new_task_id
        else:
            print(f"  ❌ Failed to create task")
            return None
    except Exception as e:
        print(f"  ❌ Error creating task: {e}")
        return None

def reprioritize_other_projects(notion: NotionManager):
    """Reprioritize all other projects to lower priority"""
    print("\n📊 Reprioritizing other projects...")
    
    try:
        # Query all projects (no filter - get all)
        projects = notion.query_database(AGENT_PROJECTS_DB_ID, filter_params=None)
        
        updated = 0
        for project in projects:
            project_id = project.get("id")
            project_title = project.get("properties", {}).get("Project Name", {}).get("title", [{}])[0].get("text", {}).get("content", "Unknown")
            
            # Skip our new project
            if project_id == "2e0e7361-6c27-81d9-bdef-f4d2a0c4e37a" or "Outstanding Tasks Completion" in project_title:
                continue
            
            # Get current priority
            priority = project.get("properties", {}).get("Priority", {}).get("select", {}).get("name", "")
            
            # Skip if already low priority
            if priority in ["Low", "Lowest", "Medium"]:
                continue
            
            # Set to Medium priority
            update_properties = {
                "Priority": {"select": {"name": "Medium"}}
            }
            
            if notion.update_page(project_id, update_properties):
                print(f"  ✅ Reprioritized: {project_title}")
                updated += 1
        
        print(f"\n✅ Reprioritized {updated} projects to Medium priority")
    except Exception as e:
        print(f"⚠️  Could not reprioritize projects: {e}")

def reprioritize_other_tasks(notion: NotionManager):
    """Reprioritize other tasks to lower priority"""
    print("\n📊 Reprioritizing other tasks...")
    
    try:
        # Query all tasks (we'll filter in code)
        tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=None)
        
        updated = 0
        for task in tasks:
            task_id = task.get("id")
            task_title = task.get("properties", {}).get("Task Name", {}).get("title", [{}])[0].get("text", {}).get("content", "Unknown")
            
            # Get current priority
            priority = task.get("properties", {}).get("Priority", {}).get("select", {}).get("name", "")
            
            # Skip if already low priority
            if priority in ["Low", "Lowest", "Medium"]:
                continue
            
            # Skip tasks in our new project
            projects = task.get("properties", {}).get("🤖 Agent-Projects", {}).get("relation", [])
            project_ids = [p.get("id") for p in projects]
            if "2e0e7361-6c27-81d9-bdef-f4d2a0c4e37a" in project_ids:
                continue
            
            # Set to Medium priority
            update_properties = {
                "Priority": {"select": {"name": "Medium"}}
            }
            
            if notion.update_page(task_id, update_properties):
                print(f"  ✅ Reprioritized: {task_title[:50]}")
                updated += 1
        
        print(f"\n✅ Reprioritized {updated} tasks to Medium priority")
    except Exception as e:
        print(f"⚠️  Could not reprioritize tasks: {e}")

def main():
    """Main execution"""
    print("=" * 80)
    print("Create Outstanding Tasks Project")
    print("=" * 80)
    print()
    
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1
    
    notion = NotionManager(token)
    
    # Create project
    print("📋 Creating Agent-Project...")
    print("-" * 80)
    project_id = create_project(notion)
    
    if not project_id:
        print("❌ Failed to create project")
        return 1
    
    print()
    
    # Create/update tasks
    print("📝 Creating/Updating Tasks...")
    print("-" * 80)
    task_ids = []
    for task_info in OUTSTANDING_TASKS:
        task_id = create_task(notion, task_info, project_id)
        if task_id:
            task_ids.append(task_id)
        print()
    
    print(f"✅ Created/Updated {len(task_ids)}/{len(OUTSTANDING_TASKS)} tasks")
    print()
    
    # Reprioritize other projects and tasks
    reprioritize_other_projects(notion)
    reprioritize_other_tasks(notion)
    
    # Summary
    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"✅ Project created: Outstanding Tasks Completion — 2026-01-06")
    print(f"   Project ID: {project_id}")
    print(f"   Priority: Highest")
    print(f"✅ Tasks created/updated: {len(task_ids)}")
    print(f"   All tasks assigned to: Cursor MM1 Agent")
    print(f"   All tasks priority: Highest")
    print(f"✅ Other projects/tasks reprioritized to Medium")
    print()
    print(f"📋 Project URL: https://www.notion.so/{project_id.replace('-', '')}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

