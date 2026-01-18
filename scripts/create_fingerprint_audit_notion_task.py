#!/usr/bin/env python3
"""
Create Notion Agent-Tasks item for Fingerprint Batch Embedding Audit Review
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    print("notion-client not available")

# Database IDs
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
CLAUDE_CODE_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent (used for code review)

def create_notion_task():
    """Create Notion Agent-Tasks item for audit review."""

    if not NOTION_AVAILABLE:
        print("Notion client not available. Install with: pip install notion-client")
        return None

    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token
        token = get_notion_token()
    except ImportError:
        token = os.getenv("NOTION_TOKEN")

    if not token:
        print("NOTION_TOKEN not found in token_manager or environment")
        return None

    notion = Client(auth=token)
    
    audit_report_path = PROJECT_ROOT / "FINGERPRINT_BATCH_EMBEDDING_AUDIT_REPORT.md"
    
    # Read audit report summary
    report_summary = ""
    if audit_report_path.exists():
        with open(audit_report_path, 'r') as f:
            content = f.read()
            # Extract key metrics section
            if "### Key Metrics" in content:
                start = content.find("### Key Metrics")
                end = content.find("##", start + 1)
                if end > start:
                    report_summary = content[start:end]
    
    task_description = f"""## Objective

Review the comprehensive audit and performance report for batch fingerprint embedding execution and continue with remediation or implementation work as needed.

## Context

Batch fingerprint embedding script was executed to embed fingerprints in existing Eagle library audio files. This task requires review of the execution results, identification of issues, and continuation of remediation work.

## Audit Report

A comprehensive audit report has been generated documenting execution metrics, performance, issues encountered, and recommendations.

**Report Location:** {audit_report_path}

{report_summary}

## Known Issues Identified

1. **Eagle Client Sync Error:** 
   - urllib import issue (FIXED in code, but running process didn't pick up fix)
   - Impact: Eagle tag syncing failed, falling back to direct API
   - Resolution: Fix applied to `music_workflow/integrations/eagle/client.py`

2. **WAV File Limitations:**
   - WAV files cannot have fingerprints embedded in metadata
   - Recommendation: Consider converting WAV files to M4A/FLAC for fingerprint support

## Required Actions

1. **Review Audit Report:** Read and analyze the comprehensive audit report
2. **Verify Results:** Check that fingerprints were successfully embedded in processed files
3. **Address Issues:** Fix any remaining issues identified in the report
4. **Continue Processing:** If needed, continue batch processing with remaining files
5. **Update Notion:** Update Agent-Tasks with review results and next steps
6. **Create Next Handoff:** Create handoff for next phase of work if needed

## Success Criteria

- [ ] Audit report reviewed and understood
- [ ] All issues identified and documented
- [ ] Remediation plan created for remaining issues
- [ ] Notion tasks updated with results
- [ ] Next handoff created if needed

## Files and Artifacts

- **Audit Report:** {audit_report_path}
- **Log File:** /tmp/batch_fingerprint_embedding.log
- **Script:** scripts/batch_fingerprint_embedding.py
- **Eagle Client Fix:** music_workflow/integrations/eagle/client.py

## Next Steps

After review, determine:
1. Whether to continue batch processing with remaining files
2. What remediation is needed for identified issues
3. Whether fingerprint coverage verification is needed
4. What the next phase of work should be

## Post-Completion Handoff

Upon completion, create handoff trigger file for next agent in the workflow chain with:
- Review findings
- Remediation recommendations
- Next phase execution plan
"""
    
    # Truncate if too long
    if len(task_description) > 1999:
        task_description = task_description[:1996] + "..."
    
    properties = {
        "Task Name": {
            "title": [{"text": {"content": "Review Fingerprint Batch Embedding Audit Report and Continue Remediation"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description}}]
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Status": {
            "status": {"name": "Ready"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_CODE_AGENT_ID}]
        },
        "Task Type": {
            "select": {"name": "Agent Handoff Task"}
        }
    }
    
    try:
        new_page = notion.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=properties
        )
        
        task_id = new_page.get("id")
        task_url = new_page.get("url", "")
        
        print(f"✅ Created Notion Agent-Tasks item:")
        print(f"   Task ID: {task_id}")
        print(f"   URL: {task_url}")
        
        return task_id, task_url, new_page
        
    except Exception as e:
        print(f"❌ Error creating Notion task: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

if __name__ == "__main__":
    task_id, task_url, page = create_notion_task()
    if task_id:
        print(f"\n✅ Success! Task created: {task_url}")
