#!/usr/bin/env python3
"""
Create handoff trigger file for Dropbox Music scripts testing completion.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from main import (
    create_trigger_file,
    normalize_agent_folder_name,
    MM1_AGENT_TRIGGER_BASE,
    CLAUDE_MM1_AGENT_ID
)

def create_handoff_trigger():
    """Create handoff trigger file for review and production execution planning."""
    
    issue_id = "2e2e7361-6c27-8142-bf0c-f18fc419f7b1"
    issue_url = "https://www.notion.so/AUDIT-Dropbox-Music-Cleanup-Scripts-Created-Require-Testing-2e2e73616c278142bf0cf18fc419f7b1"
    
    task_details = {
        "task_id": f"handoff-{issue_id[:8]}",
        "task_title": "Review Dropbox Music Scripts Test Results & Create Production Execution Plan",
        "task_url": issue_url,
        "project_id": None,
        "project_title": "Dropbox Music Cleanup",
        "description": f"""## Context

Testing has been completed for the Dropbox Music cleanup scripts. All three scripts passed dry-run tests successfully.

## Issue Details
- **Issue:** [AUDIT] Dropbox Music Cleanup Scripts Created - Require Testing
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}
- **Status:** Testing completed, ready for review

## Test Results Summary

✅ **ALL SCRIPTS PASSED DRY-RUN TESTS**

### Scripts Tested:
1. `create_dropbox_music_structure.py` - ✅ PASSED
2. `dropbox_music_deduplication.py` - ✅ PASSED (identified 12 duplicate groups, 19 duplicate files, 185.40 MB savings)
3. `dropbox_music_migration.py` - ✅ PASSED (identified 43 user content files, 151 metadata files, 2345 legacy files for migration)

### Test Artifacts:
- Test Report: `DROPBOX_MUSIC_SCRIPTS_TEST_REPORT.md`
- Test Results JSON: `dropbox_music_scripts_test_results.json`
- Test Script: `test_dropbox_music_scripts.py`

## Required Actions

1. **Review Test Results**
   - Review the comprehensive test report
   - Verify all safety mechanisms are working correctly
   - Confirm dry-run outputs are as expected

2. **Create Production Execution Plan**
   - Define execution sequence (structure → deduplication → migration)
   - Identify prerequisites (backup requirements, disk space, etc.)
   - Create rollback procedures
   - Schedule execution time

3. **Create Production Execution Task**
   - Create Agent-Task for production execution
   - Assign to appropriate agent (Cursor MM1 for execution)
   - Include all context and prerequisites

4. **Update Issue Status**
   - Update issue status to reflect testing completion
   - Link production execution task to issue

## Next Handoff Requirements

**MANDATORY:** Upon completion, you MUST create a handoff trigger file for **Production Execution** assigned to **Cursor MM1 Agent**.

**Handoff File Location:** `/Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/01_inbox/`

**Required Content:**
- Complete production execution plan
- Prerequisites checklist
- Rollback procedures
- Link to issue and test report
- All context needed for safe production execution

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
""",
        "status": "Ready",
        "agent_name": "Claude MM1 Agent",
        "agent_id": CLAUDE_MM1_AGENT_ID,
        "priority": "High",
        "handoff_instructions": """Proceed with reviewing the test results and creating a production execution plan. Upon completion, you MUST:

1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.

2. Review the test report: `DROPBOX_MUSIC_SCRIPTS_TEST_REPORT.md`

3. Create a comprehensive production execution plan with:
   - Execution sequence
   - Prerequisites checklist
   - Rollback procedures
   - Safety verification steps

4. Create a handoff trigger file for production execution (assigned to Cursor MM1 Agent) with all required context

5. Update the issue status in Notion

**MANDATORY:** Task is NOT complete until trigger file is manually moved and production execution handoff is created.
"""
    }
    
    trigger_file = create_trigger_file("MM1", "Claude MM1 Agent", task_details)
    
    if trigger_file:
        print(f"✅ Created handoff trigger file: {trigger_file}")
        return trigger_file
    else:
        print("❌ Failed to create handoff trigger file")
        return None

if __name__ == "__main__":
    trigger_file = create_handoff_trigger()
    if trigger_file:
        print(f"\n✅ Handoff trigger file created successfully!")
        print(f"   Location: {trigger_file}")
    else:
        print("\n❌ Failed to create handoff trigger file")
        sys.exit(1)
