#!/usr/bin/env python3
"""
Report Recurring Environment Management Issue
=============================================

Reports the recurring environment management pattern violation issue and creates
Agent-Tasks for multiple agents to coordinate on a permanent solution.

This issue has occurred dozens of times and needs a systematic solution.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Database ID resolver - inline for now
def get_agent_tasks_db_id() -> str:
    """Get Agent-Tasks database ID"""
    return "284e73616c278018872aeb14e82e0392"

def get_issues_questions_db_id() -> str:
    """Get Issues+Questions database ID"""
    return "229e73616c27808ebf06c202b10b5166"

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent
CHATGPT_AGENT_ID = "9c4b6040-5e0f-4d31-ae1b-d4a43743b224"  # ChatGPT

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"


def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")


def create_issue_entry(
    client: Client,
    title: str,
    description: str,
    priority: str = "Critical",
    component: Optional[str] = None
) -> Optional[str]:
    """Create Issues+Questions entry."""
    try:
        properties: Dict[str, Any] = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:2000]}}]
            },
            "Type": {
                "multi_select": [{"name": "Internal Issue"}]
            },
            "Status": {
                "status": {"name": "Unreported"}
            },
            "Priority": {
                "select": {"name": priority}
            }
        }
        
        page = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating issue: {e}", file=sys.stderr)
        return None


def create_agent_task(
    client: Client,
    task_name: str,
    description: str,
    assigned_agent_id: str,
    priority: str = "Critical",
    related_issue_id: Optional[str] = None
) -> Optional[str]:
    """Create Agent-Task."""
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
                "status": {"name": "Ready"}
            },
            "Dependency Status": {
                "select": {"name": "Ready"}
            },
            "Task Type": {
                "select": {"name": "Implementation"}
            },
            "Assigned-Agent": {
                "relation": [{"id": assigned_agent_id}]
            }
        }
        
        # Note: Related Issue property may not exist in Agent-Tasks database
        # Issue ID will be included in task description instead
        
        page = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating task: {e}", file=sys.stderr)
        return None


def main():
    """Main execution."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚨 Reporting Recurring Environment Management Issue...\n")
    print("="*80)
    
    # Create Issues+Questions entry
    issue_title = "CRITICAL: Recurring Environment Management Pattern Violations - Needs Permanent Solution"
    issue_description = """**CRITICAL RECURRING ISSUE - HAS OCCURRED DOZENS OF TIMES**

**Problem:**
Agents (especially Cursor MM1) repeatedly create scripts that violate the established environment management pattern. This happens EVERY SINGLE DAY despite clear documentation and previous fixes.

**Pattern Violations:**
1. Missing `from dotenv import load_dotenv`
2. Missing `load_dotenv()` call
3. Missing `VV_AUTOMATIONS_WS_TOKEN` check
4. Missing `unified_config` fallback
5. Incorrect error messages

**Impact:**
- Scripts fail when environment variables not set
- Breaks workspace token management
- Wastes time fixing the same issue repeatedly
- Creates frustration and reduces trust in agent system

**Root Cause:**
- No automated validation or enforcement
- No pre-commit hooks or linting
- No shared utility function being used
- Agents don't check existing patterns before creating new scripts

**Required Permanent Solutions:**
1. **Shared Utility Function** (Cursor MM1) - Create `shared_core/notion/token_manager.py` with standardized `get_notion_token()`. All scripts MUST import and use this function.

2. **Automated Validation** (Cursor MM1) - Pre-commit hook that validates all Python scripts use correct pattern. Linting rule that flags violations. CI/CD check that fails on violations.

3. **Template System** (Claude MM1) - Create script templates with correct pattern pre-filled. Update agent prompts to reference templates. Add to agent system prompts as mandatory requirement.

4. **Agent Prompt Updates** (ChatGPT) - Update all agent system prompts to mandate pattern compliance. Add pattern check to agent execution checklist. Create agent coordination protocol for pattern enforcement.

5. **Documentation & Training** (Claude MM1) - Make pattern documentation more prominent. Add to agent onboarding checklist. Create visual checklist agents must follow.

**Evidence:**
- Fixed in: `scripts/populate_agent_function_assignments.py` (2025-01-29)
- Fixed in: `scripts/create_drivesheetsync_project_structure.py` (2025-01-29)
- Fixed in: `scripts/create_gas_scripts_production_handoffs.py` (2025-01-29)
- Pattern documented in: `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
- Correct examples in: `scripts/review_agent_functions_compliance.py`, `scripts/create_compliance_issues.py`

**Urgency:** CRITICAL - This must be prevented from happening again. System-wide solution required.

**Coordination Required:**
- Cursor MM1: Implement shared utility and automated validation
- Claude MM1: Create templates and update documentation
- ChatGPT: Update agent prompts and coordination protocols
- All agents: Review and approve solution approach
"""
    
    issue_id = create_issue_entry(
        client=client,
        title=issue_title,
        description=issue_description,
        priority="Critical"
    )
    
    if not issue_id:
        print("❌ Failed to create issue")
        sys.exit(1)
    
    print(f"✅ Created Issues+Questions entry: {issue_id}")
    print(f"   URL: https://www.notion.so/{issue_id.replace('-', '')}\n")
    
    # Create Agent-Tasks for coordinated solution
    print("="*80)
    print("Creating Agent-Tasks for Coordinated Solution")
    print("="*80 + "\n")
    
    # Task 1: Cursor MM1 - Shared Utility Function
    task1_id = create_agent_task(
        client=client,
        task_name="Create Shared Notion Token Manager Utility",
        description=f"""**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}

Create `shared_core/notion/token_manager.py` with standardized `get_notion_token()` function.

**Requirements:**
- Must follow exact pattern from `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
- Must check: NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN
- Must include unified_config fallback
- Must handle all exceptions gracefully
- Must be importable from any script location

**Deliverables:**
- `shared_core/notion/token_manager.py` with `get_notion_token()` function
- Update all existing scripts to use shared utility
- Test that all scripts work with shared utility
- Update documentation to reference shared utility

**Success Criteria:**
- All scripts can import and use shared utility
- No scripts have custom token retrieval functions
- All scripts pass validation tests
- Documentation updated""",
        assigned_agent_id=CURSOR_MM1_AGENT_ID,
        priority="Critical",
        related_issue_id=issue_id
    )
    
    if task1_id:
        print(f"✅ Created Task 1: Shared Utility Function (Cursor MM1)")
        print(f"   ID: {task1_id}\n")
    
    # Task 2: Cursor MM1 - Automated Validation
    task2_id = create_agent_task(
        client=client,
        task_name="Implement Automated Environment Pattern Validation",
        description=f"""**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}

Create automated validation to prevent pattern violations.

**Requirements:**
- Pre-commit hook that checks all Python scripts
- Linting rule (flake8/ruff/pylint plugin) that flags violations
- CI/CD check that fails builds on violations
- Validation script that can be run manually

**Validation Checks:**
1. Script imports `load_dotenv` from `dotenv`
2. Script calls `load_dotenv()` after path setup
3. Token function checks all three env vars
4. Token function includes unified_config fallback
5. Error messages use correct format

**Deliverables:**
- Pre-commit hook script
- Linting rule/plugin
- CI/CD validation step
- Manual validation script
- Documentation on how to use

**Success Criteria:**
- Pre-commit hook prevents commits with violations
- CI/CD fails on violations
- All existing scripts pass validation
- New scripts automatically validated""",
        assigned_agent_id=CURSOR_MM1_AGENT_ID,
        priority="Critical",
        related_issue_id=issue_id
    )
    
    if task2_id:
        print(f"✅ Created Task 2: Automated Validation (Cursor MM1)")
        print(f"   ID: {task2_id}\n")
    
    # Task 3: Claude MM1 - Templates and Documentation
    task3_id = create_agent_task(
        client=client,
        task_name="Create Script Templates and Update Agent Prompts",
        description=f"""**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}

Create script templates and update agent system prompts to prevent violations.

**Requirements:**
- Create Python script template with correct pattern pre-filled
- Update all agent system prompts to reference template
- Add pattern compliance to agent execution checklist
- Make pattern documentation more prominent
- Create visual checklist for agents

**Deliverables:**
- Script template file (`scripts/templates/python_script_template.py`)
- Updated agent system prompts with pattern requirements
- Agent execution checklist with pattern validation step
- Enhanced documentation with visual checklist
- Agent onboarding guide with pattern training

**Success Criteria:**
- All new scripts use template
- Agent prompts explicitly require pattern compliance
- Agents check pattern before creating scripts
- Documentation is clear and prominent
- Zero new violations after implementation""",
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,
        priority="Critical",
        related_issue_id=issue_id
    )
    
    if task3_id:
        print(f"✅ Created Task 3: Templates and Documentation (Claude MM1)")
        print(f"   ID: {task3_id}\n")
    
    # Task 4: ChatGPT - Agent Coordination Protocol
    task4_id = create_agent_task(
        client=client,
        task_name="Update Agent Coordination Protocol for Pattern Enforcement",
        description=f"""**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}

Update Universal Four-Agent Coordination Workflow to enforce pattern compliance.

**Requirements:**
- Add pattern validation to workflow pre-flight checklist
- Create agent coordination protocol for pattern enforcement
- Update handoff procedures to include pattern validation
- Add pattern compliance to agent review criteria
- Create escalation path for pattern violations

**Deliverables:**
- Updated Universal Four-Agent Coordination Workflow
- Pattern enforcement protocol document
- Updated handoff procedures
- Agent review checklist with pattern validation
- Escalation procedures for violations

**Success Criteria:**
- Pattern validation in all workflow phases
- Agents validate pattern before handoffs
- Review agents check pattern compliance
- Violations trigger immediate escalation
- Zero tolerance for pattern violations""",
        assigned_agent_id=CHATGPT_AGENT_ID,
        priority="Critical",
        related_issue_id=issue_id
    )
    
    if task4_id:
        print(f"✅ Created Task 4: Agent Coordination Protocol (ChatGPT)")
        print(f"   ID: {task4_id}\n")
    
    print("="*80)
    print("ISSUE REPORTED AND TASKS CREATED")
    print("="*80)
    print(f"\nIssue ID: {issue_id}")
    print(f"Issue URL: https://www.notion.so/{issue_id.replace('-', '')}")
    print(f"\nTasks Created:")
    if task1_id:
        print(f"  - Task 1: Shared Utility Function (Cursor MM1)")
    if task2_id:
        print(f"  - Task 2: Automated Validation (Cursor MM1)")
    if task3_id:
        print(f"  - Task 3: Templates and Documentation (Claude MM1)")
    if task4_id:
        print(f"  - Task 4: Agent Coordination Protocol (ChatGPT)")
    print("\n✅ All agents coordinated to prevent this issue from recurring")


if __name__ == "__main__":
    main()

