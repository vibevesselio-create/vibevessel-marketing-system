#!/usr/bin/env python3
"""
Create Unified Issues Entry in Notion
=====================================

Creates a comprehensive issues entry in Notion Issues+Questions database
documenting all findings from the system audit.

Part of Phase 2: Issue Identification and Logging
"""

import os
import sys
import json
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

ISSUES_DB_ID = "229e73616c27808ebf06c202b10b5166"


def create_unified_issues_entry() -> Optional[str]:
    """Create unified issues entry in Notion."""
    if not NOTION_AVAILABLE:
        print("Notion client not available. Cannot create issues entry.")
        return None
    
    # Load inventory data
    inventory_file = Path(__file__).parent.parent / "reports" / "SYSTEM_INVENTORY_20260114_052425.json"
    if not inventory_file.exists():
        # Find most recent inventory
        reports_dir = Path(__file__).parent.parent / "reports"
        inventory_files = sorted(reports_dir.glob("SYSTEM_INVENTORY_*.json"), reverse=True)
        if inventory_files:
            inventory_file = inventory_files[0]
        else:
            print("No inventory file found")
            return None
    
    with open(inventory_file) as f:
        inventory = json.load(f)
    
    # Build comprehensive issues content
    title = "Agent Coordination System Audit - Comprehensive Issues Log"
    
    # Build rich text content for the page body
    content_blocks = []
    
    # Executive Summary
    content_blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{"type": "text", "text": {"content": "Executive Summary"}}]
        }
    })
    
    summary_text = f"""This comprehensive audit identified critical gaps in the agent coordination system, DriveSheetsSync execution logging, and Notion synchronization.

**Audit Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**Inventory File:** {inventory_file.name}

**Key Findings:**
- {inventory['trigger_files']['total_inbox']} trigger files pending in inbox folders
- {inventory['notion_execution_logs'].get('total', 0)} DriveSheetsSync execution logs in Notion (CRITICAL: Expected logs missing)
- {len(inventory['drivesheetsync_logs']['local_logs'])} local DriveSheetsSync logs found
- {inventory['notion_scripts'].get('total', 0)} scripts synced to Notion
- {len(inventory['plans_and_reports']['plans'])} plans and {len(inventory['plans_and_reports']['reports'])} reports found
"""
    
    content_blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": summary_text}}]
        }
    })
    
    # Critical Issues Section
    content_blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Critical Issues"}}]
        }
    })
    
    critical_issues = """**1. DriveSheetsSync Execution Logs Missing in Notion**
- **Severity:** CRITICAL
- **Status:** Unreported
- **Description:** DriveSheetsSync script should create execution logs in Notion Execution-Logs database (ID: 27be7361-6c27-8033-a323-dca0fafa80e6), but inventory shows 0 entries for DriveSheetsSync.
- **Impact:** No visibility into script execution history, errors, or performance metrics in Notion.
- **Root Cause:** Script may not be executing, or execution log creation is failing silently.
- **Remediation:** 
  1. Verify DriveSheetsSync is configured to run (time-based trigger or manual execution)
  2. Check UnifiedLoggerGAS implementation in Code.js
  3. Verify EXECUTION_LOGS_DB_ID is correctly configured
  4. Test execution log creation manually
  5. Review Google Drive logs for execution history

**2. Incomplete Work from Previous Audits**
- **Severity:** HIGH
- **Status:** Unreported
- **Description:** Multiple issues identified in CURSOR_MM1_AUDIT_REPORT_20260113_233710.md remain unresolved:
  - VOLUMES_DATABASE_ID not configured (blocks folder/volume sync)
  - Script sync ran in validate-only mode (never actually synced)
  - Folder/volume sync script created but never executed
- **Impact:** Critical synchronization workflows are blocked or incomplete.
- **Remediation:** 
  1. Investigate VOLUMES_DATABASE_ID requirement (create database or document why not needed)
  2. Re-run script sync without --validate-only flag
  3. Execute folder/volume sync script if prerequisites are met

**3. Trigger File Processing Gaps**
- **Severity:** HIGH
- **Status:** Unreported
- **Description:** {inbox_count} trigger files found in 01_inbox folders that should have been processed.
- **Impact:** Tasks may be stuck, agents may not be receiving work assignments.
- **Remediation:**
  1. Review each trigger file to determine if it should be processed or archived
  2. Move stale triggers to 02_processed or 03_failed as appropriate
  3. Verify agents are checking inbox folders regularly
""".format(inbox_count=inventory['trigger_files']['total_inbox'])
    
    content_blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": critical_issues}}]
        }
    })
    
    # Medium Priority Issues
    content_blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Medium Priority Issues"}}]
        }
    })
    
    medium_issues = """**4. Agent Folder Naming Inconsistencies**
- **Severity:** MEDIUM
- **Status:** Unreported
- **Description:** Multiple folder name variations exist (Claude-MM1-Agent vs Claude-MM1-Agent-Trigger), causing duplicate folders and routing issues.
- **Impact:** Trigger files may be routed to wrong folders, agents may miss assignments.
- **Remediation:** Implement normalize_agent_folder_name() function in main.py (already exists in folder_resolver.py, needs to be used consistently)

**5. Documentation Synchronization Gaps**
- **Severity:** MEDIUM
- **Status:** Unreported
- **Description:** Plans and reports may not be synced to Notion. Need to verify synchronization status.
- **Impact:** Documentation may be out of sync between local and Notion.
- **Remediation:** 
  1. Verify plans are synced to appropriate Notion database
  2. Verify reports are synced to appropriate Notion database
  3. Create synchronization workflow if missing
"""
    
    content_blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": medium_issues}}]
        }
    })
    
    # Inventory Summary
    content_blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Inventory Summary"}}]
        }
    })
    
    inventory_summary = f"""**Trigger Files:**
- Inbox: {inventory['trigger_files']['total_inbox']}
- Processed: {inventory['trigger_files']['total_processed']}
- Failed: {inventory['trigger_files']['total_failed']}

**Plans and Reports:**
- Plans: {len(inventory['plans_and_reports']['plans'])}
- Reports: {len(inventory['plans_and_reports']['reports'])}
- Cursor Reports: {len(inventory['plans_and_reports']['cursor_reports'])}
- Claude Reports: {len(inventory['plans_and_reports']['claude_reports'])}

**Notion Synchronization:**
- Scripts in Notion: {inventory['notion_scripts'].get('total', 0)}
- DriveSheetsSync Execution Logs: {inventory['notion_execution_logs'].get('total', 0)} (CRITICAL: Missing)
- Related Issues: {inventory['notion_issues'].get('total', 0)}

**DriveSheetsSync Logs:**
- Local logs: {len(inventory['drivesheetsync_logs']['local_logs'])}
- Notion logs: {len(inventory['drivesheetsync_logs']['notion_logs'])}
"""
    
    content_blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": inventory_summary}}]
        }
    })
    
    # Create the page
    try:
        page = notion.pages.create(
            parent={"database_id": ISSUES_DB_ID},
            properties={
                "Name": {
                    "title": [
                        {"text": {"content": title}}
                    ]
                },
                "Status": {
                    "status": {"name": "Unreported"}
                },
                "Priority": {
                    "select": {"name": "High"}
                },
            },
            children=content_blocks
        )
        
        page_id = page.get("id")
        print(f"Created issues entry: {page_id}")
        print(f"Notion URL: https://notion.so/{page_id.replace('-', '')}")
        return page_id
        
    except Exception as e:
        print(f"Error creating issues entry: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    page_id = create_unified_issues_entry()
    if page_id:
        print(f"\n✅ Successfully created unified issues entry: {page_id}")
    else:
        print("\n❌ Failed to create issues entry")
