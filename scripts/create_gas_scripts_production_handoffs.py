#!/usr/bin/env python3
"""
Create handoffs and issues in Notion for DriveSheetsSync and Project Manager Bot Scripts.

This script creates:
1. Agent-Tasks for both workflows
2. Issues+Questions entries for critical issues
3. Trigger files for assigned agents
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

from shared_core.notion.db_id_resolver import (
    get_agent_tasks_db_id,
    get_issues_questions_db_id,
    get_documents_db_id
)

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"

# Trigger file paths
CURSOR_TRIGGER_INBOX = Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd/Cursor-MM1-Agent-Trigger-gd/01_inbox")


def get_notion_token() -> Optional[str]:
    """Get Notion token from environment."""
    return os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")


def create_agent_task(
    client: Client,
    task_name: str,
    description: str,
    assigned_agent_id: str,
    priority: str = "Critical",
    task_type: str = "Implementation",
    dependency_status: str = "Ready",
    related_issue_id: Optional[str] = None
) -> Optional[str]:
    """Create Agent-Task in Notion."""
    try:
        properties: Dict[str, Any] = {
            "Task Name": {
                "title": [{"text": {"content": task_name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
            },
            "Priority": {
                "select": {"name": priority}
            },
            "Status": {
                "status": {"name": "Not Started"}
            },
            "Dependency Status": {
                "select": {"name": dependency_status}
            },
            "Task Type": {
                "select": {"name": task_type}
            },
            "Assigned-Agent": {
                "relation": [{"id": assigned_agent_id}]
            }
        }
        
        if related_issue_id:
            # Try to add related issue if property exists
            try:
                properties["Related Issue"] = {
                    "relation": [{"id": related_issue_id}]
                }
            except:
                pass
        
        page = client.pages.create(
            parent={"database_id": get_agent_tasks_db_id()},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating Agent-Task '{task_name}': {e}", file=sys.stderr)
        return None


def create_issue_entry(
    client: Client,
    title: str,
    description: str,
    issue_type: List[str] = None,
    priority: str = "High",
    status: str = "Unreported",
    component: Optional[str] = None
) -> Optional[str]:
    """Create Issues+Questions entry in Notion."""
    if issue_type is None:
        issue_type = ["Internal Issue"]
    
    try:
        properties: Dict[str, Any] = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
            },
            "Type": {
                "multi_select": [{"name": t} for t in issue_type]
            },
            "Status": {
                "status": {"name": status}
            },
            "Priority": {
                "select": {"name": priority}
            }
        }
        
        if component:
            try:
                properties["Component"] = {
                    "select": {"name": component}
                }
            except:
                pass  # Component property may not exist
        
        page = client.pages.create(
            parent={"database_id": get_issues_questions_db_id()},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating Issue '{title}': {e}", file=sys.stderr)
        return None


def create_trigger_file(
    task_id: str,
    task_url: str,
    task_name: str,
    task_description: str,
    script_name: str
) -> Optional[Path]:
    """Create trigger file for agent."""
    try:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        filename = f"GAS-{script_name}-Production-Readiness-{timestamp}.md"
        filepath = CURSOR_TRIGGER_INBOX / filename
        
        content = f"""# {task_name}

**Date:** {datetime.utcnow().strftime("%Y-%m-%d")}  
**Priority:** 🔴 CRITICAL - PRODUCTION BLOCKER  
**Assigned Agent:** Cursor MM1 Agent  
**Component:** {script_name}  
**Task ID:** `{task_id}`  
**Task URL:** {task_url}

---

## Task Description

{task_description}

---

## Success Criteria

- [ ] All critical issues resolved
- [ ] Script tested and validated
- [ ] Production deployment ready
- [ ] Documentation updated

---

**Status:** Ready for Implementation  
**Blocking:** Yes - Production deployment
"""
        
        filepath.write_text(content)
        print(f"✅ Created trigger file: {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ Error creating trigger file: {e}", file=sys.stderr)
        return None


def main():
    """Create handoffs and issues for DriveSheetsSync and Project Manager Bot."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_API_KEY or NOTION_TOKEN not set")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating handoffs and issues for GAS Scripts Production Readiness...\n")
    
    # DriveSheetsSync Tasks
    drivesheetsync_tasks = [
        {
            "name": "DriveSheetsSync: Complete Production Readiness Review",
            "description": """**CRITICAL:** DriveSheetsSync needs immediate production readiness review and fixes.

**Key Issues Identified:**
1. API Version Mismatch: CONFIG.NOTION_VERSION set to '2022-06-28' but header declares '2025-09-03'
2. Token Handling: May not accept both 'secret_' and 'ntn_' prefixes
3. Diagnostic Functions: Need to be deployed to GAS
4. Archive Folders: 110 missing .archive folders in workspace-databases
5. Multi-Script Compatibility: Verify compatibility with Project Manager Bot

**Required Actions:**
- Review all critical issues from audit
- Fix API version mismatch
- Update token handling if needed
- Deploy diagnostic functions
- Create missing archive folders
- Verify multi-script compatibility
- Test all fixes
- Deploy to production

**Reference Files:**
- `gas-scripts/drive-sheets-sync/Code.gs`
- `gas-scripts/drive-sheets-sync/DIAGNOSTIC_FUNCTIONS.gs`
- `gas-scripts/drive-sheets-sync/README.md`
- `GAS_SCRIPTS_SLACK_WORKFLOW_GUIDE.md`

**Priority:** CRITICAL - Production Blocker""",
            "priority": "Critical",
            "script": "DriveSheetsSync"
        }
    ]
    
    # Project Manager Bot Tasks
    project_manager_bot_tasks = [
        {
            "name": "Project Manager Bot: Complete Production Readiness Review",
            "description": """**CRITICAL:** Project Manager Bot needs immediate production readiness review and fixes.

**Key Issues Identified:**
1. Multi-Script Compatibility: Verify compatibility with DriveSheetsSync
2. Trigger File Format: Ensure .json format is respected by DriveSheetsSync
3. Deduplication Logic: Verify age-based deduplication (10 minutes) works correctly
4. Script Properties: Validate all required properties are set
5. Error Handling: Review error handling and logging

**Required Actions:**
- Review multi-script compatibility implementation
- Verify trigger file format compatibility
- Test deduplication logic
- Validate script properties
- Review error handling
- Test all fixes
- Deploy to production

**Reference Files:**
- `gas-scripts/project-manager-bot/Code.js`
- `gas-scripts/project-manager-bot/README.md`
- `GAS_SCRIPTS_SLACK_WORKFLOW_GUIDE.md`

**Priority:** CRITICAL - Production Blocker""",
            "priority": "Critical",
            "script": "ProjectManagerBot"
        }
    ]
    
    # Create Issues
    issues = [
        {
            "title": "DriveSheetsSync Production Readiness - Multiple Critical Issues",
            "description": """DriveSheetsSync has multiple critical issues preventing production deployment:

1. **API Version Mismatch:** CONFIG.NOTION_VERSION is '2022-06-28' but should be '2025-09-03'
2. **Token Handling:** May not accept both 'secret_' and 'ntn_' prefixes
3. **Diagnostic Functions:** Not deployed to GAS
4. **Archive Folders:** 110 missing .archive folders
5. **Multi-Script Compatibility:** Needs verification with Project Manager Bot

**Impact:** Blocks production deployment of DriveSheetsSync workflow.

**Resolution:** Complete production readiness review and fix all critical issues.""",
            "component": "DriveSheetsSync",
            "priority": "Critical"
        },
        {
            "title": "Project Manager Bot Production Readiness - Multi-Script Compatibility",
            "description": """Project Manager Bot needs production readiness review focusing on multi-script compatibility:

1. **Multi-Script Compatibility:** Verify compatibility with DriveSheetsSync
2. **Trigger File Format:** Ensure .json format is respected
3. **Deduplication Logic:** Verify age-based deduplication works correctly
4. **Script Properties:** Validate all required properties
5. **Error Handling:** Review error handling and logging

**Impact:** Blocks production deployment of Project Manager Bot workflow.

**Resolution:** Complete production readiness review and fix all critical issues.""",
            "component": "ProjectManagerBot",
            "priority": "Critical"
        }
    ]
    
    created_tasks = []
    created_issues = []
    
    # Create issues first
    print("📋 Creating Issues+Questions entries...")
    for issue in issues:
        issue_id = create_issue_entry(
            client,
            issue["title"],
            issue["description"],
            issue_type=["Internal Issue"],
            priority=issue["priority"],
            component=issue.get("component")
        )
        if issue_id:
            created_issues.append((issue_id, issue["title"]))
            print(f"  ✅ Created issue: {issue['title']}")
        else:
            print(f"  ❌ Failed to create issue: {issue['title']}")
    
    print()
    
    # Create DriveSheetsSync tasks
    print("📋 Creating DriveSheetsSync Agent-Tasks...")
    for task in drivesheetsync_tasks:
        # Link to DriveSheetsSync issue
        related_issue_id = created_issues[0][0] if created_issues else None
        
        task_id = create_agent_task(
            client,
            task["name"],
            task["description"],
            CURSOR_MM1_AGENT_ID,
            priority=task["priority"],
            related_issue_id=related_issue_id
        )
        
        if task_id:
            created_tasks.append((task_id, task["name"], task["script"]))
            print(f"  ✅ Created task: {task['name']}")
            
            # Get task URL
            task_url = f"https://notion.so/{task_id.replace('-', '')}"
            
            # Create trigger file
            trigger_file = create_trigger_file(
                task_id,
                task_url,
                task["name"],
                task["description"],
                task["script"]
            )
            if trigger_file:
                print(f"  ✅ Created trigger file: {trigger_file.name}")
        else:
            print(f"  ❌ Failed to create task: {task['name']}")
    
    print()
    
    # Create Project Manager Bot tasks
    print("📋 Creating Project Manager Bot Agent-Tasks...")
    for task in project_manager_bot_tasks:
        # Link to Project Manager Bot issue
        related_issue_id = created_issues[1][0] if len(created_issues) > 1 else None
        
        task_id = create_agent_task(
            client,
            task["name"],
            task["description"],
            CURSOR_MM1_AGENT_ID,
            priority=task["priority"],
            related_issue_id=related_issue_id
        )
        
        if task_id:
            created_tasks.append((task_id, task["name"], task["script"]))
            print(f"  ✅ Created task: {task['name']}")
            
            # Get task URL
            task_url = f"https://notion.so/{task_id.replace('-', '')}"
            
            # Create trigger file
            trigger_file = create_trigger_file(
                task_id,
                task_url,
                task["name"],
                task["description"],
                task["script"]
            )
            if trigger_file:
                print(f"  ✅ Created trigger file: {trigger_file.name}")
        else:
            print(f"  ❌ Failed to create task: {task['name']}")
    
    print()
    print("=" * 80)
    print("✅ SUMMARY")
    print("=" * 80)
    print(f"Created {len(created_issues)} Issues+Questions entries")
    print(f"Created {len(created_tasks)} Agent-Tasks")
    print(f"Created {len(created_tasks)} trigger files")
    print()
    print("📋 Created Issues:")
    for issue_id, title in created_issues:
        print(f"  - {title} (ID: {issue_id})")
    print()
    print("📋 Created Tasks:")
    for task_id, name, script in created_tasks:
        print(f"  - {name} (ID: {task_id}, Script: {script})")
    print()
    print("🎯 Next Steps:")
    print("  1. Review created tasks in Notion Agent-Tasks database")
    print("  2. Review created issues in Notion Issues+Questions database")
    print("  3. Use Slack integration to coordinate workflow fixes")
    print("  4. See GAS_SCRIPTS_SLACK_WORKFLOW_GUIDE.md for Slack usage")


if __name__ == "__main__":
    main()




