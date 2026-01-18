#!/usr/bin/env python3
"""
Create Notion Tasks for Music Workflow Gaps

Creates tasks in Agent-Tasks and Issues+Questions databases based on
the gap analysis document.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Database IDs
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"

def get_notion_client():
    """Get Notion API client."""
    try:
        from notion_client import Client
        # Use centralized token manager (MANDATORY per CLAUDE.md)
        try:
            from shared_core.notion.token_manager import get_notion_token
            token = get_notion_token()
        except ImportError:
            token = os.getenv("NOTION_TOKEN")
        if not token:
            print("ERROR: NOTION_TOKEN not set")
            return None
        return Client(auth=token)
    except ImportError:
        print("ERROR: notion-client not available. Install with: pip install notion-client")
        return None

def create_agent_task(notion, title: str, description: str, priority: str = "Medium") -> Optional[str]:
    """Create a task in Agent-Tasks database."""
    try:
        # Get database schema to find correct property names
        db_schema = notion.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        props = db_schema.get("properties", {})
        
        properties = {}
        
        # Find title property (could be "Name", "Task Name", etc.)
        for prop_name in ["Task Name", "Name"]:
            if prop_name in props and props[prop_name].get("type") == "title":
                properties[prop_name] = {
                    "title": [{"text": {"content": title}}]
                }
                break
        
        # Find status property and get valid options
        if "Status" in props and props["Status"].get("type") == "status":
            status_options = props["Status"].get("status", {}).get("options", [])
            for option in status_options:
                option_name = option.get("name", "")
                if option_name in ["Ready", "Not Started", "Proposed", "Draft"]:
                    properties["Status"] = {
                        "status": {"name": option_name}
                    }
                    break
        
        # Find priority property
        if "Priority" in props and props["Priority"].get("type") == "select":
            properties["Priority"] = {
                "select": {"name": priority}
            }
        
        # Find description property
        for prop_name in ["Description", "Notes"]:
            if prop_name in props:
                prop_type = props[prop_name].get("type")
                if prop_type == "rich_text":
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": description}}]
                    }
                    break
        
        page = notion.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        page_id = page["id"]
        print(f"  ✓ Created Agent-Task: {title} ({page_id})")
        return page_id
        
    except Exception as e:
        print(f"  ✗ Failed to create Agent-Task '{title}': {e}")
        return None

def create_issue(notion, title: str, description: str, priority: str = "Medium") -> Optional[str]:
    """Create an issue in Issues+Questions database."""
    try:
        # Get database schema to find correct property names
        db_schema = notion.databases.retrieve(database_id=ISSUES_QUESTIONS_DB_ID)
        props = db_schema.get("properties", {})
        
        properties = {}
        
        # Find title property
        for prop_name in ["Name", "Title"]:
            if prop_name in props and props[prop_name].get("type") == "title":
                properties[prop_name] = {
                    "title": [{"text": {"content": title}}]
                }
                break
        
        # Find status property and get valid options
        if "Status" in props and props["Status"].get("type") == "status":
            status_options = props["Status"].get("status", {}).get("options", [])
            # Try to find a valid non-closed status
            for option in status_options:
                option_name = option.get("name", "")
                if option_name not in ["Closed", "Resolved", "Complete", "Completed"]:
                    properties["Status"] = {
                        "status": {"name": option_name}
                    }
                    break
            # If no valid status found, use first option
            if "Status" not in properties and status_options:
                properties["Status"] = {
                    "status": {"name": status_options[0].get("name", "")}
                }
        
        # Find priority property
        if "Priority" in props and props["Priority"].get("type") == "select":
            properties["Priority"] = {
                "select": {"name": priority}
            }
        
        # Find description property
        for prop_name in ["Description", "Notes", "Details"]:
            if prop_name in props:
                prop_type = props[prop_name].get("type")
                if prop_type == "rich_text":
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": description}}]
                    }
                    break
        
        page = notion.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )
        
        page_id = page["id"]
        print(f"  ✓ Created Issue: {title} ({page_id})")
        return page_id
        
    except Exception as e:
        print(f"  ✗ Failed to create Issue '{title}': {e}")
        return None

def main():
    """Main function to create all gap tasks."""
    print("=" * 80)
    print("Creating Notion Tasks for Music Workflow Gaps")
    print("=" * 80)
    print()
    
    notion = get_notion_client()
    if not notion:
        print("ERROR: Could not initialize Notion client")
        sys.exit(1)
    
    created_tasks = []
    created_issues = []
    
    # Automation Opportunities - Agent-Tasks
    print("Creating Automation Opportunity Tasks...")
    print("-" * 80)
    
    automation_tasks = [
        {
            "title": "Music Workflow: Implement Webhook Triggers for Auto-Sync",
            "description": """Implement webhook triggers for automatic music sync:
- Spotify webhook for new liked tracks
- SoundCloud webhook for new likes
- Automatic processing on webhook trigger

Estimated Effort: 2-3 sessions
Impact: Medium - Reduces manual execution
Dependencies: Webhook server infrastructure""",
            "priority": "Medium"
        },
        {
            "title": "Music Workflow: Configure Scheduled Execution",
            "description": """Configure scheduled execution for music sync:
- Cron job for periodic music sync
- Scheduled batch processing
- Automatic cleanup tasks

Estimated Effort: 1 session
Impact: Medium - Automation improvement
Dependencies: System cron or task scheduler""",
            "priority": "Medium"
        },
        {
            "title": "Music Workflow: Enhance Continuous Handoff Integration",
            "description": """Enhance music workflow integration with continuous handoff system:
- Automatic task creation for music sync
- Status updates via continuous handoff
- Error reporting via continuous handoff

Estimated Effort: 1-2 sessions
Impact: Medium - System integration
Dependencies: Continuous handoff orchestrator enhancement""",
            "priority": "Medium"
        },
        {
            "title": "Music Workflow: Implement Error Recovery Automation",
            "description": """Implement automated error recovery for music workflow:
- Automatic retry with exponential backoff
- Alternative source selection on failure
- Error classification and routing

Estimated Effort: 2 sessions
Impact: Medium - Reliability improvement""",
            "priority": "Medium"
        }
    ]
    
    for task in automation_tasks:
        task_id = create_agent_task(notion, task["title"], task["description"], task["priority"])
        if task_id:
            created_tasks.append(task_id)
    
    print()
    
    # Implementation Gaps - Issues+Questions
    print("Creating Implementation Gap Issues...")
    print("-" * 80)
    
    implementation_issues = [
        {
            "title": "Music Workflow: Fix DRM Error Handling",
            "description": """Fix DRM error handling for Spotify tracks:
- Implement YouTube search fallback for Spotify tracks
- Add proper error classification
- Implement retry with alternative source

Status: Critical
Estimated Effort: 1 session
Impact: Blocks Spotify track processing
Source: MONOLITHIC_MAINTENANCE_PLAN.md""",
            "priority": "High"
        },
        {
            "title": "Music Workflow: Create Volume Index File",
            "description": """Create volume index file for performance optimization:
- Path: /var/music_volume_index.json
- Structure: Track metadata index
- Purpose: Performance optimization for file lookups

Status: Medium priority
Estimated Effort: 1 session
Impact: Medium - Performance optimization
Source: MONOLITHIC_MAINTENANCE_PLAN.md""",
            "priority": "Medium"
        },
        {
            "title": "Music Workflow: Begin Modularization Phase 1",
            "description": """Begin Phase 1 of modularization strategy:
- Create music_workflow/core/ module
- Extract logging utilities
- Extract configuration handling
- Extract file path utilities
- Create unit tests

Status: High priority (long-term)
Estimated Effort: 2-3 sessions
Impact: HIGH - Maintainability, testability, extensibility
Source: MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md
Dependencies: Approval of modularization design""",
            "priority": "High"
        },
        {
            "title": "Music Workflow: Create Test Suite Foundation",
            "description": """Create foundation for comprehensive test suite:
- Set up testing framework
- Create test fixtures and mocks
- Establish test coverage baseline
- Document testing strategy

Status: High priority
Estimated Effort: 2-3 sessions
Impact: HIGH - Code quality and regression prevention
Source: Plans directory""",
            "priority": "High"
        },
        {
            "title": "Music Workflow: Document Environment Requirements",
            "description": """Create comprehensive environment documentation:
- Create .env.example with all required variables
- Document TRACKS_DB_ID requirement
- Document optional vs required variables
- Provide setup instructions

Status: Low priority
Estimated Effort: < 1 session
Impact: LOW - Documentation clarity
Source: MONOLITHIC_MAINTENANCE_PLAN.md""",
            "priority": "Low"
        }
    ]
    
    for issue in implementation_issues:
        issue_id = create_issue(notion, issue["title"], issue["description"], issue["priority"])
        if issue_id:
            created_issues.append(issue_id)
    
    print()
    print("=" * 80)
    print(f"Summary: Created {len(created_tasks)} Agent-Tasks and {len(created_issues)} Issues")
    print("=" * 80)
    
    if created_tasks:
        print(f"\nAgent-Tasks created: {len(created_tasks)}")
        for task_id in created_tasks:
            print(f"  - {task_id}")
    
    if created_issues:
        print(f"\nIssues created: {len(created_issues)}")
        for issue_id in created_issues:
            print(f"  - {issue_id}")
    
    return 0 if (created_tasks or created_issues) else 1

if __name__ == "__main__":
    sys.exit(main())
