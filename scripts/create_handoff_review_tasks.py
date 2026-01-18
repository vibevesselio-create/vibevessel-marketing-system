#!/usr/bin/env python3
"""
Create Comprehensive Handoff Review Tasks
=========================================

Creates Issues+Questions entries and Agent-Tasks for all agents (Claude MM1, Cursor MM1, Codex MM1)
to review and validate task handoff instruction logic updates and update their documentation/profiles.
"""

import os
import sys
import json
import uuid
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

# MANDATORY: Import task creation helpers
try:
    from shared_core.notion.task_creation import (
        add_mandatory_next_handoff_instructions,
        create_task_description_with_next_handoff,
        create_handoff_json_data
    )
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError:
    TASK_CREATION_HELPERS_AVAILABLE = False
    print("⚠️  WARNING: Task creation helpers not available!", file=sys.stderr)

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
PROJECTS_DB_ID = "286e73616c2781ffa450db2ecad4b0ba"

# Agent IDs
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CODEX_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Codex MM1 Agent (same as Cursor MM1 per trigger file)

# Related Project
UNIFIED_ENV_PROJECT_ID = "2dae7361-6c27-8105-9aa3-d89689127c7d"

# Agent trigger directories - use unified normalization
from main import normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE

AGENT_TRIGGERS_BASE = MM1_AGENT_TRIGGER_BASE
CLAUDE_MM1_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("Claude MM1 Agent") / "01_inbox"
CURSOR_MM1_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("Cursor MM1 Agent") / "01_inbox"
CODEX_MM1_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("Codex MM1 Agent") / "01_inbox"


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
    priority: str = "Critical"
) -> Optional[str]:
    """Create Issues+Questions entry."""
    try:
        # Query database to get schema
        db = client.databases.retrieve(database_id=ISSUES_QUESTIONS_DB_ID)
        properties = db.get("properties", {})
        
        # Build properties dynamically
        issue_properties = {}
        
        # Find title property
        for prop_name, prop_data in properties.items():
            if prop_data.get("type") == "title":
                issue_properties[prop_name] = {
                    "title": [{"text": {"content": title}}]
                }
                break
        
        # Find description property
        for prop_name in ["Description", "Notes", "Summary"]:
            if prop_name in properties:
                prop_type = properties[prop_name].get("type")
                if prop_type == "rich_text":
                    issue_properties[prop_name] = {
                        "rich_text": [{"text": {"content": description[:2000]}}]
                    }
                    break
        
        # Find type property
        for prop_name in ["Type", "Issue Type"]:
            if prop_name in properties:
                prop_type = properties[prop_name].get("type")
                if prop_type == "multi_select":
                    issue_properties[prop_name] = {
                        "multi_select": [{"name": "Internal Issue"}]
                    }
                    break
        
        # Find status property
        for prop_name in ["Status", "State"]:
            if prop_name in properties:
                prop_type = properties[prop_name].get("type")
                if prop_type == "status":
                    issue_properties[prop_name] = {
                        "status": {"name": "Unreported"}
                    }
                    break
        
        # Find priority property
        for prop_name in ["Priority", "Urgency"]:
            if prop_name in properties:
                prop_type = properties[prop_name].get("type")
                if prop_type == "select":
                    options = properties[prop_name].get("select", {}).get("options", [])
                    option_name = priority
                    if options and priority not in [opt.get("name") for opt in options]:
                        option_name = options[0].get("name", priority)
                    issue_properties[prop_name] = {
                        "select": {"name": option_name}
                    }
                    break
        
        page = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=issue_properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating issue: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_agent_task(
    client: Client,
    task_name: str,
    description: str,
    assigned_agent_id: str,
    project_id: Optional[str] = None,
    priority: str = "Critical",
    next_task_name: Optional[str] = None,
    next_target_agent: Optional[str] = None
) -> Optional[str]:
    """Create Agent-Task with mandatory next handoff instructions."""
    try:
        # MANDATORY: Add next handoff instructions if provided
        if TASK_CREATION_HELPERS_AVAILABLE and next_task_name and next_target_agent:
            description = add_mandatory_next_handoff_instructions(
                description=description,
                next_task_name=next_task_name,
                target_agent=next_target_agent,
                next_task_id="TO_BE_CREATED",
                project_name="Handoff Review & Validation"
            )
        elif next_task_name and next_target_agent:
            # Fallback
            description += f"\n\n## 🚨 MANDATORY HANDOFF REQUIREMENT\n\nUpon completion, you MUST create a handoff trigger file for {next_task_name} assigned to {next_target_agent}."
        
        # Truncate to ensure under 2000 character limit
        if len(description) > 1999:
            description = description[:1996] + "..."
        
        properties = {
            "Task Name": {
                "title": [{"text": {"content": task_name}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": description[:1999]}}]  # Ensure under 2000 limit
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
        
        if project_id:
            try:
                properties["Projects"] = {
                    "relation": [{"id": project_id}]
                }
            except:
                pass
        
        page = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        return page.get("id")
    except Exception as e:
        print(f"❌ Error creating task: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


def create_handoff_trigger_file(
    target_agent: str,
    inbox_path: Path,
    handoff_data: Dict[str, Any]
) -> Path:
    """Create handoff trigger file."""
    inbox_path.mkdir(parents=True, exist_ok=True)
    
    # CRITICAL: Check for existing trigger file to prevent duplicates
    task_id = handoff_data.get("task_url", "").split("/")[-1] if handoff_data.get("task_url") else None
    if task_id:
        task_id_short = task_id.replace("-", "")[:8] if len(task_id) > 8 else task_id
        # Check for existing trigger files with this task ID (in inbox, processed, or failed)
        base_folder = inbox_path.parent
        for subfolder in ["01_inbox", "02_processed", "03_failed"]:
            check_folder = base_folder / subfolder
            if check_folder.exists():
                existing_files = list(check_folder.glob(f"*{task_id_short}*.json"))
                if existing_files:
                    existing_file = existing_files[0]
                    print(f"⚠️  Trigger file already exists for task {task_id_short} in {subfolder}: {existing_file.name}. Skipping duplicate creation.", file=sys.stderr)
                    return existing_file  # Return existing file instead of creating duplicate
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{timestamp}__HANDOFF__Handoff-Review-Validation__{target_agent.replace(' ', '-')}.json"
    file_path = inbox_path / filename
    
    with open(file_path, 'w') as f:
        json.dump(handoff_data, f, indent=2)
    
    return file_path


def main():
    """Create comprehensive handoff review tasks for all agents."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found")
        sys.exit(1)
    
    client = Client(auth=token)
    
    print("🚀 Creating Comprehensive Handoff Review Tasks...\n")
    print("="*80)
    
    # Step 1: Create Issues+Questions entry
    issue_title = "CRITICAL: Task Handoff Instruction Logic Updated - All Agents Must Review & Validate"
    issue_description = """**CRITICAL SYSTEM UPDATE - ALL AGENTS MUST REVIEW**

**What Was Updated:**
1. Created mandatory helper module: `shared_core/notion/task_creation.py`
   - Functions automatically add next handoff instructions to all tasks
   - Cannot be bypassed - system-enforced requirement

2. Updated documentation:
   - `docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md` - Step 3 updated
   - `docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md` - Created
   - `docs/SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md` - Created
   - `docs/CRITICAL_SYSTEM_REQUIREMENTS.md` - Created

3. Updated task creation scripts:
   - `scripts/create_unified_env_management_project.py` - All phases updated
   - All tasks now include mandatory next handoff instructions

**Required Actions for ALL Agents:**
1. Review updated documentation
2. Review helper module implementation
3. Validate that all task creation includes next handoff instructions
4. Update agent profiles/documentation to reflect this requirement
5. Ensure all future tasks include next handoff instructions

**Impact:**
- ALL tasks must now include next handoff instructions
- This is system-enforced, not optional
- Agents must create next handoff trigger files upon task completion

**Related Files:**
- `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`
- `/Users/brianhellemn/Projects/github-production/docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md`
- `/Users/brianhellemn/Projects/github-production/docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md`
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
    
    print("="*80)
    print("Creating Agent-Tasks for All Agents")
    print("="*80 + "\n")
    
    # Task 1: Claude MM1 - Review and Validate
    claude_task_description = f"""**Review and Validate Task Handoff Instruction Logic Updates**

**Review Requirements:**
1. Review `shared_core/notion/task_creation.py` helper module
2. Review updated `docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md` (Step 3)
3. Review `docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md`
4. Review `docs/SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md`
5. Validate that all task creation scripts use helper functions
6. Validate that all tasks include next handoff instructions

**Documentation Updates Required:**
1. Review your agent profile/documentation
2. Update to reflect mandatory next handoff requirement
3. Ensure all examples include next handoff instructions
4. Update any templates or guides you maintain

**Validation Checklist:**
- [ ] Helper module reviewed and validated
- [ ] Documentation updates reviewed
- [ ] Task creation scripts validated
- [ ] Agent profile/documentation updated
- [ ] All examples include next handoff instructions
- [ ] Templates updated (if applicable)

**Deliverables:**
- Review report in Notion
- Updated agent profile/documentation
- Validation confirmation
- Any recommendations for improvements

**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}
**Related Project:** https://www.notion.so/{UNIFIED_ENV_PROJECT_ID.replace('-', '')}
"""
    
    claude_task_id = create_agent_task(
        client=client,
        task_name="Claude MM1: Review & Validate Task Handoff Instruction Logic Updates",
        description=claude_task_description,
        assigned_agent_id=CLAUDE_MM1_AGENT_ID,
        project_id=UNIFIED_ENV_PROJECT_ID,
        priority="Critical",
        next_task_name="Cursor MM1: Review & Validate Task Handoff Instruction Logic Updates",
        next_target_agent="Cursor MM1 Agent"
    )
    
    if claude_task_id:
        print(f"✅ Created Claude MM1 task: {claude_task_id}")
        print(f"   URL: https://www.notion.so/{claude_task_id.replace('-', '')}\n")
    
    # Task 2: Cursor MM1 - Review and Validate
    cursor_task_description = f"""**Review and Validate Task Handoff Instruction Logic Updates**

**Review Requirements:**
1. Review `shared_core/notion/task_creation.py` helper module implementation
2. Review updated documentation (same as Claude MM1)
3. Validate technical implementation is correct
4. Test helper functions work as expected
5. Validate all task creation scripts use helpers correctly

**Documentation Updates Required:**
1. Review your agent profile/documentation
2. Update to reflect mandatory next handoff requirement
3. Ensure all code examples include next handoff instructions
4. Update any technical documentation you maintain

**Validation Checklist:**
- [ ] Helper module code reviewed and validated
- [ ] Functions tested and working correctly
- [ ] Task creation scripts validated
- [ ] Agent profile/documentation updated
- [ ] Code examples include next handoff instructions
- [ ] Technical documentation updated

**Deliverables:**
- Technical review report
- Updated agent profile/documentation
- Validation confirmation
- Any technical recommendations

**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}
**Related Project:** https://www.notion.so/{UNIFIED_ENV_PROJECT_ID.replace('-', '')}
"""
    
    cursor_task_id = create_agent_task(
        client=client,
        task_name="Cursor MM1: Review & Validate Task Handoff Instruction Logic Updates",
        description=cursor_task_description,
        assigned_agent_id=CURSOR_MM1_AGENT_ID,
        project_id=UNIFIED_ENV_PROJECT_ID,
        priority="Critical",
        next_task_name="Codex MM1: Review & Validate Task Handoff Instruction Logic Updates",
        next_target_agent="Codex MM1 Agent"
    )
    
    if cursor_task_id:
        print(f"✅ Created Cursor MM1 task: {cursor_task_id}")
        print(f"   URL: https://www.notion.so/{cursor_task_id.replace('-', '')}\n")
    
    # Task 3: Codex MM1 - Review and Validate
    codex_task_description = f"""**Review and Validate Task Handoff Instruction Logic Updates**

**Review Requirements:**
1. Review `shared_core/notion/task_creation.py` helper module
2. Review updated documentation (same as other agents)
3. Validate filesystem/metadata aspects are correct
4. Review trigger file creation logic
5. Validate handoff file format is correct

**Documentation Updates Required:**
1. Review your agent profile/documentation
2. Update to reflect mandatory next handoff requirement
3. Ensure all filesystem examples include next handoff instructions
4. Update any metadata/documentation you maintain

**Validation Checklist:**
- [ ] Helper module reviewed
- [ ] Filesystem aspects validated
- [ ] Trigger file creation validated
- [ ] Agent profile/documentation updated
- [ ] Filesystem examples include next handoff
- [ ] Metadata/documentation updated

**Deliverables:**
- Review report
- Updated agent profile/documentation
- Validation confirmation
- Any filesystem/metadata recommendations

**Related Issue:** https://www.notion.so/{issue_id.replace('-', '')}
**Related Project:** https://www.notion.so/{UNIFIED_ENV_PROJECT_ID.replace('-', '')}
"""
    
    codex_task_id = create_agent_task(
        client=client,
        task_name="Codex MM1: Review & Validate Task Handoff Instruction Logic Updates",
        description=codex_task_description,
        assigned_agent_id=CODEX_MM1_AGENT_ID if CODEX_MM1_AGENT_ID != "TO_BE_DETERMINED" else CLAUDE_MM1_AGENT_ID,  # Fallback
        project_id=UNIFIED_ENV_PROJECT_ID,
        priority="Critical",
        next_task_name="Final Validation & Documentation Consolidation",
        next_target_agent="Claude MM1 Agent"
    )
    
    if codex_task_id:
        print(f"✅ Created Codex MM1 task: {codex_task_id}")
        print(f"   URL: https://www.notion.so/{codex_task_id.replace('-', '')}\n")
    
    # Step 3: Create handoff trigger files
    print("="*80)
    print("Creating Handoff Trigger Files")
    print("="*80 + "\n")
    
    # Claude MM1 handoff
    if claude_task_id:
        claude_handoff = create_handoff_json_data(
            source_agent="Cursor MM1 Agent",
            target_agent="Claude MM1 Agent",
            task_url=f"https://www.notion.so/{claude_task_id.replace('-', '')}",
            project_url=f"https://www.notion.so/{UNIFIED_ENV_PROJECT_ID.replace('-', '')}",
            related_issue_url=f"https://www.notion.so/{issue_id.replace('-', '')}",
            handoff_reason="Review and validate task handoff instruction logic updates, update agent profile/documentation",
            context={
                "current_step": "Task handoff instruction logic has been updated with system enforcement. Review required.",
                "work_completed": [
                    "Created mandatory helper module: shared_core/notion/task_creation.py",
                    "Updated documentation: AGENT_HANDOFF_TASK_GENERATOR_V3.0.md",
                    "Updated task creation scripts to use helpers",
                    "Created comprehensive documentation"
                ],
                "blocking_issue": None,
                "project_goals": "Ensure all agents understand and implement mandatory next handoff requirement"
            },
            required_action=f"""Review and validate task handoff instruction logic updates:

1. Review `shared_core/notion/task_creation.py` helper module
2. Review updated documentation in `docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md`
3. Review `docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md`
4. Validate that all task creation includes next handoff instructions
5. Update your agent profile/documentation to reflect this requirement
6. Ensure all examples and templates include next handoff instructions

**MANDATORY HANDOFF REQUIREMENT:** Upon completion, create handoff trigger file for Cursor MM1 Agent to perform same review.""",
            success_criteria=[
                "Helper module reviewed and validated",
                "Documentation updates reviewed",
                "Agent profile/documentation updated",
                "All examples include next handoff instructions",
                "Validation confirmation provided",
                "**MANDATORY:** Handoff trigger file created for Cursor MM1 Agent"
            ],
            deliverables={
                "files_to_review": [
                    "/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py",
                    "/Users/brianhellemn/Projects/github-production/docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md",
                    "/Users/brianhellemn/Projects/github-production/docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md",
                    "/Users/brianhellemn/Projects/github-production/docs/SYSTEM_ENFORCEMENT_NEXT_HANDOFF.md"
                ],
                "artifacts": [
                    "Review report in Notion",
                    "Updated agent profile/documentation",
                    "Validation confirmation",
                    "Handoff trigger file for Cursor MM1 Agent"
                ],
                "next_handoff": {
                    "target_agent": "Cursor MM1 Agent",
                    "task_id": cursor_task_id if 'cursor_task_id' in locals() else "TO_BE_CREATED",
                    "task_name": "Cursor MM1: Review & Validate Task Handoff Instruction Logic Updates",
                    "inbox_path": f"{AGENT_TRIGGERS_BASE}/{normalize_agent_folder_name('Cursor MM1 Agent')}/01_inbox/",
                    "required": True,
                    "instructions": "Create handoff trigger file with review findings and validation confirmation for Cursor MM1 to perform technical review."
                }
            }
        )
        
        claude_handoff_file = create_handoff_trigger_file(
            target_agent="Claude MM1 Agent",
            inbox_path=CLAUDE_MM1_INBOX,
            handoff_data=claude_handoff
        )
        print(f"✅ Created Claude MM1 handoff: {claude_handoff_file.name}\n")
    
    print("="*80)
    print("COMPREHENSIVE HANDOFF REVIEW TASKS CREATED")
    print("="*80)
    print(f"\n✅ Issues+Questions entry: {issue_id}")
    print(f"   URL: https://www.notion.so/{issue_id.replace('-', '')}")
    print(f"\n✅ Agent-Tasks created:")
    if claude_task_id:
        print(f"   - Claude MM1: {claude_task_id}")
    if cursor_task_id:
        print(f"   - Cursor MM1: {cursor_task_id}")
    if codex_task_id:
        print(f"   - Codex MM1: {codex_task_id}")
    print(f"\n✅ Handoff trigger files created")
    print(f"\n📋 All tasks include mandatory next handoff instructions")


if __name__ == "__main__":
    main()

