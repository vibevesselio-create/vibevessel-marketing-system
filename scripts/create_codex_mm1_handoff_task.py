#!/usr/bin/env python3
"""
Create Handoff Task for Codex MM1 Agent
========================================

Creates an Agent-Task in Notion for Codex MM1 Agent to perform
secondary audit and validation of DriveSheetsSync analysis.

Part of Phase 5: Handoff Task Creation
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from notion_client import Client
    from dotenv import load_dotenv
    load_dotenv()
    NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    if NOTION_TOKEN:
        notion = Client(auth=NOTION_TOKEN)
        NOTION_AVAILABLE = True
    else:
        NOTION_AVAILABLE = False
except Exception as e:
    NOTION_AVAILABLE = False
    print(f"Notion client not available: {e}")

AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
CODEX_MM1_AGENT_ID = "2b1e7361-6c27-80fb-8ce9-fd3cf78a5cad"  # From folder_resolver.py


def create_handoff_task() -> Optional[str]:
    """Create handoff task for Codex MM1 Agent."""
    if not NOTION_AVAILABLE:
        print("Notion client not available. Cannot create handoff task.")
        return None
    
    title = "DriveSheetsSync Secondary Audit and Validation"
    
    # Build task description
    description = """Perform secondary audit and gap analysis of DriveSheetsSync workflow using local clasp synchronization workflows.

**Primary Audit Completed By:** System Audit Agent
**Audit Date:** 2026-01-14
**Related Issues:** Notion Issue 2e8e7361-6c27-819c-b431-e1549e8e6823

## Task Requirements

1. **Review Primary Audit Findings**
   - Review DRIVESHEETSSYNC_GAP_ANALYSIS_20260114.md
   - Review SYSTEM_INVENTORY_20260114_052425.json
   - Review unified issues entry in Notion

2. **Perform Secondary Audit Using Clasp Workflows**
   - Use local clasp synchronization workflows to validate DriveSheetsSync
   - Verify execution log creation mechanism
   - Test execution log creation manually if needed
   - Review Google Apps Script execution history

3. **Validate Gap Analysis**
   - Verify all gaps identified in primary audit
   - Identify any additional gaps
   - Validate remediation recommendations

4. **Create Validation Report**
   - Document validation findings
   - Confirm or dispute primary audit conclusions
   - Provide additional remediation recommendations if needed

## Key Findings from Primary Audit

**CRITICAL:** DriveSheetsSync execution logs completely missing from Notion
- Expected: Execution logs in Notion Execution-Logs database
- Actual: 0 execution logs found
- Impact: No visibility into script execution, errors, or performance

**Additional Findings:**
- Script may not be executing (no recent evidence)
- Execution log creation may be failing silently
- Configuration issues possible

## Resources

- DriveSheetsSync Script: `gas-scripts/drive-sheets-sync/Code.js`
- Gap Analysis Report: `reports/DRIVESHEETSSYNC_GAP_ANALYSIS_20260114.md`
- System Inventory: `reports/SYSTEM_INVENTORY_20260114_052425.json`
- Unified Issues Entry: Notion Issue 2e8e7361-6c27-819c-b431-e1549e8e6823
- Execution-Logs Database ID: 27be7361-6c27-8033-a323-dca0fafa80e6

## Success Criteria

1. ✅ Secondary audit completed using clasp workflows
2. ✅ Primary audit findings validated or disputed
3. ✅ Validation report created
4. ✅ Additional gaps identified if any
5. ✅ Remediation recommendations provided
"""
    
    # Split description into chunks (Notion has 2000 char limit per paragraph)
    description_parts = [
        """Perform secondary audit and gap analysis of DriveSheetsSync workflow using local clasp synchronization workflows.

**Primary Audit Completed By:** System Audit Agent
**Audit Date:** 2026-01-14
**Related Issues:** Notion Issue 2e8e7361-6c27-819c-b431-e1549e8e6823""",
        """## Task Requirements

1. **Review Primary Audit Findings**
   - Review DRIVESHEETSSYNC_GAP_ANALYSIS_20260114.md
   - Review SYSTEM_INVENTORY_20260114_052425.json
   - Review unified issues entry in Notion""",
        """2. **Perform Secondary Audit Using Clasp Workflows**
   - Use local clasp synchronization workflows to validate DriveSheetsSync
   - Verify execution log creation mechanism
   - Test execution log creation manually if needed
   - Review Google Apps Script execution history""",
        """3. **Validate Gap Analysis**
   - Verify all gaps identified in primary audit
   - Identify any additional gaps
   - Validate remediation recommendations""",
        """4. **Create Validation Report**
   - Document validation findings
   - Confirm or dispute primary audit conclusions
   - Provide additional remediation recommendations if needed""",
        """## Key Findings from Primary Audit

**CRITICAL:** DriveSheetsSync execution logs completely missing from Notion
- Expected: Execution logs in Notion Execution-Logs database
- Actual: 0 execution logs found
- Impact: No visibility into script execution, errors, or performance""",
        """**Additional Findings:**
- Script may not be executing (no recent evidence)
- Execution log creation may be failing silently
- Configuration issues possible""",
        """## Resources

- DriveSheetsSync Script: `gas-scripts/drive-sheets-sync/Code.js`
- Gap Analysis Report: `reports/DRIVESHEETSSYNC_GAP_ANALYSIS_20260114.md`
- System Inventory: `reports/SYSTEM_INVENTORY_20260114_052425.json`
- Unified Issues Entry: Notion Issue 2e8e7361-6c27-819c-b431-e1549e8e6823
- Execution-Logs Database ID: 27be7361-6c27-8033-a323-dca0fafa80e6""",
        """## Success Criteria

1. ✅ Secondary audit completed using clasp workflows
2. ✅ Primary audit findings validated or disputed
3. ✅ Validation report created
4. ✅ Additional gaps identified if any
5. ✅ Remediation recommendations provided"""
    ]
    
    # Build content blocks
    content_blocks = []
    for part in description_parts:
        content_blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": part}}]
            }
        })
    
    try:
        # Create the task
        page = notion.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties={
                "Task Name": {
                    "title": [
                        {"text": {"content": title}}
                    ]
                },
                "Status": {
                    "status": {"name": "Ready"}
                },
                "Assigned-Agent": {
                    "relation": [
                        {"id": CODEX_MM1_AGENT_ID}
                    ]
                },
            },
            children=content_blocks
        )
        
        page_id = page.get("id")
        print(f"Created handoff task: {page_id}")
        print(f"Notion URL: https://notion.so/{page_id.replace('-', '')}")
        return page_id
        
    except Exception as e:
        print(f"Error creating handoff task: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    page_id = create_handoff_task()
    if page_id:
        print(f"\n✅ Successfully created handoff task for Codex MM1 Agent: {page_id}")
    else:
        print("\n❌ Failed to create handoff task")
