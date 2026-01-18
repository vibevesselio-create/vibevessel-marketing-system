#!/usr/bin/env python3
"""
Create handoff trigger files for Cross-Workspace Database Synchronization project
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from main import (
    create_trigger_file,
    determine_agent_type,
    normalize_agent_folder_name,
    MM1_AGENT_TRIGGER_BASE,
    MM2_AGENT_TRIGGER_BASE
)

# Project details
PROJECT_ID = "dc55d5da-ba67-41f3-a355-3b52f5b2697d"
PROJECT_TITLE = "Cross-Workspace Database Synchronization — Implementation"
PROJECT_URL = "https://www.notion.so/Cross-Workspace-Database-Synchronization-Implementation-dc55d5daba6741f3a3553b52f5b2697d"

# Task details
HANDOFF_TASK = {
    "task_id": "4710421c-02e9-430b-a3fd-d07fbd36948e",
    "task_title": "[HANDOFF] Claude Code Agent — Cross-Workspace Sync Audit & Continuation",
    "task_url": "https://www.notion.so/HANDOFF-Claude-Code-Agent-Cross-Workspace-Sync-Audit-Continuation-4710421c02e9430ba3fdd07fbd36948e",
    "status": "Ready",
    "priority": "Critical",
    "description": """HANDOFF TASK FOR CLAUDE CODE AGENT

This task transfers responsibility for code review, audit, and implementation continuation of the Cross-Workspace Database Synchronization project.

Context:
- Unified methodology document created: Cross-Workspace Database Synchronization — Unified Methodology
- Main project created: Cross-Workspace Database Synchronization — Implementation
- Phase 1 tasks completed: All 4 core functions implemented (upsertRegistryPage_, syncWorkspaceDatabasesRow_, syncPropertiesRegistryForDatabase_, evaluateDatabaseCompliance_)
- Implementation location: gas-scripts/drive-sheets-sync/Code.js

Scope of Work:
1. Audit — Review completed Phase 1 implementations in Code.js
2. Gap Analysis — Compare implementations against unified methodology requirements
3. Code Review — Validate function signatures, error handling, logging integration
4. Testing — Verify functions work correctly and handle edge cases
5. Documentation — Ensure JSDoc and inline documentation is complete
6. Next Phase Planning — Identify and plan Phase 2-4 tasks
7. Handoff Return — Prepare handoff to next agent (Cursor MM1 or validation agent) with findings

Key References:
- DriveSheetsSync Code.js (gas-scripts/drive-sheets-sync/Code.js)
- Unified Methodology document
- Phase 1 implementation tasks (all marked Completed)

Return Handoff Requirements:
- Summary of audit findings
- Code review results (pass/fail with specific issues)
- Testing results and coverage
- Recommended next steps for Phase 2-4
- Blockers or risks identified
- Updated task status in Notion""",
    "handoff_instructions": """DOWNSTREAM HANDOFF AWARENESS:

After completing the audit and code review, you MUST:

1. Update the Notion task (4710421c-02e9-430b-a3fd-d07fbd36948e) with:
   - Audit findings summary
   - Code review results
   - Testing results
   - Next phase recommendations

2. Create handoff trigger file for next agent:
   - If code review passes: Create handoff to Cursor MM1 Agent for Phase 2 implementation
   - If issues found: Create handoff to Cursor MM1 Agent for remediation
   - Also create handoff to ChatGPT Code Review Agent for validation

3. Update project status in Notion:
   - Update "Next Required Step" field
   - Update verification checklist
   - Link any new issues or tasks created

4. Document work in Execution-Logs database

5. Synchronize all work to Notion before marking task complete""",
    "agent_name": "Claude Code Agent",
    "agent_id": "2cfe7361-6c27-805f-857c-e90c3db6efb9"
}

VALIDATION_TASK_1 = {
    "task_id": "2e4e7361-6c27-818e-b034-c360e5e7988a",
    "task_title": "[Validation] Cross-Workspace Sync — Phase 1 Implementation Review",
    "task_url": "https://www.notion.so/Validation-Cross-Workspace-Sync-Phase-1-Implementation-Review-2e4e73616c27818eb034c360e5e7988a",
    "status": "Ready",
    "priority": "High",
    "description": """VALIDATION TASK — Agent Work Validation

This task requests a full review and validation of the Cross-Workspace Database Synchronization Phase 1 implementation work.

TARGET AGENT: ChatGPT Code Review Agent

SCOPE OF VALIDATION:
1. Audit report completeness and accuracy
2. Cursor MM1 implementation (when completed)
3. Code quality and compliance with unified methodology
4. Testing coverage and results
5. Documentation completeness
6. Handoff trigger file accuracy
7. Notion task synchronization

Validation Checklist:
- [ ] All Phase 1 functions implemented correctly
- [ ] Function signatures match specifications
- [ ] Error handling is comprehensive
- [ ] Logging integration is complete
- [ ] JSDoc documentation is present
- [ ] Code follows unified methodology standards
- [ ] Notion tasks are properly synchronized
- [ ] Handoff files are correctly formatted""",
    "handoff_instructions": """DOWNSTREAM HANDOFF AWARENESS:

After completing validation, you MUST:

1. Update the Notion task (2e4e7361-6c27-818e-b034-c360e5e7988a) with validation results

2. If validation passes:
   - Mark task as Complete
   - Update project verification checklist
   - Create execution log entry
   - Proceed to Phase 2 planning

3. If validation fails:
   - Create issues in Issues+Questions database
   - Create remediation handoff to appropriate agent
   - Document specific failures and required fixes

4. Synchronize all work to Notion before marking complete""",
    "agent_name": "ChatGPT Code Review Agent",
    "agent_id": None
}

VALIDATION_TASK_2 = {
    "task_id": "2e4e7361-6c27-81d1-b154-e3a1878708e9",
    "task_title": "VALIDATION: Properties Deduplication & Cross-Workspace Sync Work Review",
    "task_url": "https://www.notion.so/VALIDATION-Properties-Deduplication-Cross-Workspace-Sync-Work-Review-2e4e73616c2781d1b154e3a1878708e9",
    "status": "Ready",
    "priority": "High",
    "description": """AGENT WORK VALIDATION TASK — Created 2026-01-10T05:08Z

Created by: Claude Code Agent
Target Reviewer: ChatGPT Code Review Agent

SCOPE OF VALIDATION:
1. Properties database deduplication execution
2. Notion task documentation completeness
3. Handoff trigger file accuracy
4. Project state and readiness for next phase
5. Cross-workspace sync implementation alignment

Validation Requirements:
- Review all completed Phase 1 work
- Verify Properties registry sync functions
- Validate deduplication logic
- Check Notion synchronization
- Review handoff documentation""",
    "handoff_instructions": """DOWNSTREAM HANDOFF AWARENESS:

After completing validation, you MUST:

1. Update the Notion task (2e4e7361-6c27-81d1-b154-e3a1878708e9) with validation results

2. Document findings in project verification checklist

3. If validation passes:
   - Mark task as Complete
   - Update project status
   - Create execution log entry

4. If validation fails:
   - Create issues in Issues+Questions database
   - Create remediation tasks
   - Handoff to appropriate agent for fixes

5. Synchronize all work to Notion""",
    "agent_name": "ChatGPT Code Review Agent",
    "agent_id": None
}

def create_handoff_trigger(task_info: dict, project_id: str, project_title: str, project_url: str):
    """Create a handoff trigger file for a task."""
    # Determine agent type
    agent_name = task_info["agent_name"]
    agent_type = determine_agent_type(agent_name, task_info.get("agent_id"))
    
    # Build task details
    task_details = {
        "task_id": task_info["task_id"],
        "task_title": task_info["task_title"],
        "task_url": task_info["task_url"],
        "project_id": project_id,
        "project_title": project_title,
        "project_url": project_url,
        "description": task_info["description"],
        "status": task_info["status"],
        "priority": task_info["priority"],
        "handoff_instructions": task_info["handoff_instructions"],
        "agent_id": task_info.get("agent_id")
    }
    
    # Create trigger file
    trigger_file = create_trigger_file(
        agent_type=agent_type,
        agent_name=agent_name,
        task_details=task_details
    )
    
    return trigger_file

def main():
    """Create all handoff trigger files."""
    print("="*80)
    print("Creating Handoff Trigger Files for Cross-Workspace Sync Project")
    print("="*80)
    
    triggers_created = []
    
    # Create handoff trigger for Claude Code Agent
    print("\n1. Creating handoff trigger for Claude Code Agent...")
    trigger1 = create_handoff_trigger(
        HANDOFF_TASK,
        PROJECT_ID,
        PROJECT_TITLE,
        PROJECT_URL
    )
    if trigger1:
        triggers_created.append(trigger1)
        print(f"   ✅ Created: {trigger1}")
    else:
        print(f"   ❌ Failed to create trigger")
    
    # Create validation trigger 1
    print("\n2. Creating validation trigger 1 for ChatGPT Code Review Agent...")
    trigger2 = create_handoff_trigger(
        VALIDATION_TASK_1,
        PROJECT_ID,
        PROJECT_TITLE,
        PROJECT_URL
    )
    if trigger2:
        triggers_created.append(trigger2)
        print(f"   ✅ Created: {trigger2}")
    else:
        print(f"   ❌ Failed to create trigger")
    
    # Create validation trigger 2
    print("\n3. Creating validation trigger 2 for ChatGPT Code Review Agent...")
    trigger3 = create_handoff_trigger(
        VALIDATION_TASK_2,
        PROJECT_ID,
        PROJECT_TITLE,
        PROJECT_URL
    )
    if trigger3:
        triggers_created.append(trigger3)
        print(f"   ✅ Created: {trigger3}")
    else:
        print(f"   ❌ Failed to create trigger")
    
    print("\n" + "="*80)
    print(f"Created {len(triggers_created)} trigger file(s)")
    print("="*80)
    
    return triggers_created

if __name__ == "__main__":
    main()
