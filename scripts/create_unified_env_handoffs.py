#!/usr/bin/env python3
"""
Create Handoff Trigger Files for Unified Environment Management Project
======================================================================

Creates handoff trigger files for agents to initiate execution work on
the Unified Environment Management Implementation project.
"""

import os
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

# Project and Task IDs from create_unified_env_management_project.py
PROJECT_ID = "2dae7361-6c27-8105-9aa3-d89689127c7d"
PROJECT_URL = f"https://www.notion.so/{PROJECT_ID.replace('-', '')}"

# Phase Task IDs
PHASE_1_TASK_ID = "2dae7361-6c27-815b-b115-cacc598b9ab6"  # Audit (Claude MM1)
PHASE_3_TASK_ID = "2dae7361-6c27-819a-a349-c8563e8ba758"  # Strategic Review (ChatGPT)
PHASE_5_TASK_ID = "2dae7361-6c27-8119-b9d5-e6fae4197534"  # Coordinated Approval (ALL AGENTS)
PHASE_6_TASK_ID = "2dae7361-6c27-811f-9bd2-ddd73ec82169"  # Implementation (Cursor MM1)
PHASE_7_TASK_ID = "2dae7361-6c27-81eb-aabf-cb350628d7e8"  # Final Validation (Claude MM1)

# Related Issue
RELATED_ISSUE_ID = "2dae7361-6c27-8101-aa42-e875bf8e033b"
RELATED_ISSUE_URL = f"https://www.notion.so/{RELATED_ISSUE_ID.replace('-', '')}"

# Agent trigger directories - use unified normalization
from main import normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE, MM2_AGENT_TRIGGER_BASE

AGENT_TRIGGERS_BASE = MM1_AGENT_TRIGGER_BASE
CLAUDE_MM1_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("Claude MM1 Agent") / "01_inbox"
CURSOR_MM1_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("Cursor MM1 Agent") / "01_inbox"
CHATGPT_INBOX = AGENT_TRIGGERS_BASE / normalize_agent_folder_name("ChatGPT Strategic Agent") / "01_inbox"
NOTION_DATAOPS_INBOX = MM2_AGENT_TRIGGER_BASE / f"{normalize_agent_folder_name('Notion AI Data Operations Agent')}-gd" / "01_inbox"


def create_timestamp() -> str:
    """Create ISO-8601 timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def create_handoff_file(
    target_agent: str,
    inbox_path: Path,
    handoff_data: Dict[str, Any]
) -> Path:
    """Create handoff trigger file."""
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
                    print(f"⚠️  Trigger file already exists for task {task_id_short} in {subfolder}: {existing_file.name}. Skipping duplicate creation.")
                    return existing_file  # Return existing file instead of creating duplicate
    
    timestamp = create_timestamp()
    filename = f"{timestamp}__HANDOFF__Unified-Env-Management__{target_agent.replace(' ', '-')}.json"
    file_path = inbox_path / filename
    
    # Ensure directory exists
    inbox_path.mkdir(parents=True, exist_ok=True)
    
    # Write handoff file
    with open(file_path, 'w') as f:
        json.dump(handoff_data, f, indent=2)
    
    return file_path


def main():
    """Create handoff files for all agents."""
    print("🚀 Creating Handoff Trigger Files for Unified Environment Management Project\n")
    print("="*80)
    
    # Phase 1: Claude MM1 - Audit Existing Implementation
    phase1_handoff = {
        "handoff_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_agent": "Cursor MM1 Agent",
        "target_agent": "Claude MM1 Agent",
        "priority": "Critical",
        "urgency": "Critical",
        "task_url": f"https://www.notion.so/{PHASE_1_TASK_ID.replace('-', '')}",
        "project_url": PROJECT_URL,
        "related_issue_url": RELATED_ISSUE_URL,
        "handoff_reason": "Initiate Phase 1: Audit existing environment management implementation in shared_core/notion/execution_logs.py to determine if it should be replaced or updated as the primary deliverable.",
        "context": {
            "current_step": "Project created with 7 phases. Phase 1 (Audit) is ready to begin.",
            "work_completed": [
                "Created Unified Environment Management Implementation project in Notion",
                "Created 7 phases with proper dependencies and agent assignments",
                "Linked project to related issue about recurring environment management violations",
                "Configured coordinated review process requiring all agents to approve"
            ],
            "blocking_issue": None,
            "project_goals": "Audit existing implementation, create unified solution with coordinated review from ALL agents, and implement system-mandated enforcement mechanisms."
        },
        "required_action": """Audit existing environment management implementation:

1. Review `shared_core/notion/execution_logs.py` - `_get_notion_client()` function (lines 58-78)
2. Compare with documented pattern in `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
3. Identify all gaps and deviations:
   - Missing `load_dotenv()` call
   - Missing `VV_AUTOMATIONS_WS_TOKEN` check
   - Has: `NOTION_API_KEY`, `NOTION_TOKEN`, `NOTION_API_TOKEN` checks
   - Has: `unified_config` fallback
4. Review all other implementations across codebase
5. Document findings in Notion audit report
6. Make recommendation: Replace or Update existing implementation
7. List all files using incorrect pattern

**PRIMARY DELIVERABLE:** Determine if existing implementation should be replaced or updated.\n\n**MANDATORY HANDOFF REQUIREMENT:** Upon completion of this task, you MUST create a handoff trigger file for Phase 2 (Technical Review & Shared Utility Design) assigned to Cursor MM1 Agent. The handoff file must be created in the Cursor MM1 Agent inbox using normalized folder names. Include all audit findings, recommendation, and context needed for Phase 2 to begin.""",
        "success_criteria": [
            "Audit report created in Notion with complete findings",
            "Gap analysis document created",
            "Recommendation made: Replace or Update",
            "List of all files using incorrect pattern documented",
            "All findings linked to project and related issue",
            "**MANDATORY:** Handoff trigger file created for Phase 2 (Cursor MM1 Agent)"
        ],
        "deliverables": {
            "files_to_review": [
                "shared_core/notion/execution_logs.py",
                "docs/ENVIRONMENT_MANAGEMENT_PATTERN.md",
                "scripts/review_agent_functions_compliance.py",
                "scripts/create_compliance_issues.py",
                "scripts/create_drivesheetsync_project_structure.py",
                "scripts/populate_agent_function_assignments.py"
            ],
            "artifacts": [
                "Audit report in Notion",
                "Gap analysis document",
                "Recommendation document",
                "Files inventory with pattern violations",
                "Handoff trigger file for Phase 2 (Cursor MM1 Agent)"
            ],
            "next_handoff": {
                "target_agent": "Cursor MM1 Agent",
                "task_id": "PHASE_2_TASK_ID_TO_BE_CREATED",
                "task_name": "Phase 2: Technical Review & Shared Utility Design",
                "inbox_path": str(CURSOR_MM1_INBOX) + "/",
                "required": True,
                "instructions": "Create handoff trigger file with audit findings, recommendation (Replace/Update), and all context needed for Phase 2 to design the shared utility function."
            }
        },
        "archive_rule": "move_to_02_processed"
    }
    
    phase1_file = create_handoff_file(
        target_agent="Claude MM1 Agent",
        inbox_path=CLAUDE_MM1_INBOX,
        handoff_data=phase1_handoff
    )
    print(f"✅ Created Phase 1 handoff: {phase1_file.name}")
    print(f"   Target: Claude MM1 Agent")
    print(f"   Task: Audit Existing Implementation")
    print(f"   Task URL: {phase1_handoff['task_url']}\n")
    
    # Phase 3: ChatGPT - Strategic Review (can start in parallel after Phase 1)
    phase3_handoff = {
        "handoff_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_agent": "Cursor MM1 Agent",
        "target_agent": "ChatGPT",
        "priority": "Critical",
        "urgency": "Critical",
        "task_url": f"https://www.notion.so/{PHASE_3_TASK_ID.replace('-', '')}",
        "project_url": PROJECT_URL,
        "related_issue_url": RELATED_ISSUE_URL,
        "handoff_reason": "Initiate Phase 3: Strategic Review & Coordination Protocol Design. Can begin after Phase 1 audit findings are available.",
        "context": {
            "current_step": "Waiting for Phase 1 audit findings to inform strategic design.",
            "work_completed": [
                "Project structure created",
                "Strategic review phase defined"
            ],
            "blocking_issue": "Requires Phase 1 audit findings to design effective coordination protocol",
            "project_goals": "Design agent coordination protocol and update Universal Four-Agent Coordination Workflow to enforce pattern compliance."
        },
        "required_action": """Design strategic coordination protocol:

1. Review Phase 1 audit findings (when available)
2. Review Phase 2 technical design (when available)
3. Design agent coordination protocol for pattern enforcement
4. Update Universal Four-Agent Coordination Workflow
5. Create agent prompt update specifications
6. Design approval process requiring all agents
7. Create enforcement strategy

**Note:** Can begin preliminary work, but full design requires Phase 1 and Phase 2 outputs.\n\n**MANDATORY HANDOFF REQUIREMENT:** Upon completion of this task, you MUST create a handoff trigger file for Phase 4 (Data Review & Documentation) assigned to Notion AI DataOps. The handoff file must be created in the Notion AI DataOps inbox using normalized folder names. Include all strategic design documents and context needed for Phase 4 to begin.""",
        "success_criteria": [
            "Agent coordination protocol document created",
            "Updated workflow documentation",
            "Agent prompt update specifications complete",
            "Approval process design documented",
            "Enforcement strategy defined",
            "**MANDATORY:** Handoff trigger file created for Phase 4 (Notion AI DataOps)"
        ],
        "deliverables": {
            "artifacts": [
                "Agent coordination protocol document",
                "Updated workflow documentation",
                "Agent prompt update specifications",
                "Approval process design",
                "Enforcement strategy document",
                "Handoff trigger file for Phase 4 (Notion AI DataOps)"
            ],
            "next_handoff": {
                "target_agent": "Notion AI DataOps",
                "task_id": "PHASE_4_TASK_ID_TO_BE_CREATED",
                "task_name": "Phase 4: Data Review & Documentation",
                "inbox_path": str(NOTION_DATAOPS_INBOX) + "/",
                "required": True,
                "instructions": "Create handoff trigger file with strategic design documents and all context needed for Phase 4 to create documentation and templates."
            }
        },
        "archive_rule": "move_to_02_processed"
    }
    
    phase3_file = create_handoff_file(
        target_agent="ChatGPT",
        inbox_path=CHATGPT_INBOX if CHATGPT_INBOX.exists() else Path("/tmp/chatgpt_inbox"),
        handoff_data=phase3_handoff
    )
    print(f"✅ Created Phase 3 handoff: {phase3_file.name}")
    print(f"   Target: ChatGPT")
    print(f"   Task: Strategic Review & Coordination Protocol")
    print(f"   Task URL: {phase3_handoff['task_url']}\n")
    
    print("="*80)
    print("HANDOFF FILES CREATED")
    print("="*80)
    print(f"\n✅ Phase 1 (Claude MM1 - Audit): {phase1_file}")
    print(f"✅ Phase 3 (ChatGPT - Strategic): {phase3_file}")
    print(f"\n📋 Next Steps:")
    print(f"   1. Claude MM1 Agent should begin Phase 1 audit immediately")
    print(f"   2. ChatGPT can begin Phase 3 preliminary work")
    print(f"   3. Phase 2 (Cursor MM1) will be created after Phase 1 audit")
    print(f"   4. Phase 4 (Notion AI DataOps) will be created after Phase 3")
    print(f"   5. Phase 5 requires ALL agents to approve before Phase 6")
    print(f"\n🔗 Project URL: {PROJECT_URL}")
    print(f"🔗 Related Issue: {RELATED_ISSUE_URL}")


if __name__ == "__main__":
    main()

