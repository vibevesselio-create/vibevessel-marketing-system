#!/usr/bin/env python3
"""
Create Issues+Questions entries for Agent-Functions compliance gaps
"""

import os
import sys
from pathlib import Path
from typing import Optional
from notion_client import Client

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Database IDs
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"

def get_notion_token() -> Optional[str]:
    """Get Notion API token from environment or unified_config"""
    # Check environment first
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if token:
        return token
    
    # Fallback to unified_config
    try:
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        return token
    except Exception:
        return None

def create_compliance_issues(client: Client) -> None:
    """Create Issues+Questions entries for compliance gaps"""
    
    # Issue 1: Agent-Functions missing Execution-Agent and Review-Agent
    issue1_title = "Agent-Functions Compliance: 238 items missing Execution-Agent and Review-Agent assignments"
    issue1_description = """**Compliance Gap Identified:** Agent-Functions Compliance Check (Step 1.1)

**Summary:**
A comprehensive compliance review of the Agent-Functions database found that **all 238 Agent-Function items** are missing both Execution-Agent and Review-Agent assignments.

**Details:**
- **Total Items Reviewed:** 238
- **Compliant Items:** 0
- **Missing Both Execution-Agent and Review-Agent:** 238 (100%)
- **Missing Execution-Agent Only:** 0
- **Missing Review-Agent Only:** 0

**Impact:**
- Agent-Functions cannot be properly routed to execution and review agents
- Handoff task generation cannot identify appropriate agents for work delegation
- Agent-Functions compliance requirements are not met

**Required Actions:**
1. Review each Agent-Function item to determine appropriate Execution-Agent assignment
2. Review each Agent-Function item to determine appropriate Review-Agent assignment
3. Update all 238 Agent-Function items with Execution-Agent and Review-Agent relations
4. Verify Agent-Function items have proper agent assignments in both relation properties and page content

**Evidence:**
- Compliance Review Report: `docs/ops/agent_functions_compliance_review.md`
- Review Date: 2025-12-28 23:32:53 UTC
- Review Agent: Cursor MM1 Agent

**Related:**
- This issue was identified during Agent Handoff Task Generation process (DOC_AGENT_HANDOFF_TASK_GENERATOR v2.4)
- Step 1.1: Agent-Functions Compliance Check (MANDATORY)
"""
    
    try:
        properties = {
            "Name": {"title": [{"text": {"content": issue1_title}}]},
            "Description": {"rich_text": [{"text": {"content": issue1_description}}]},
            "Type": {"multi_select": [{"name": "Internal Issue"}]},
            "Status": {"status": {"name": "Unreported"}},
            "Priority": {"select": {"name": "High"}},
        }
        
        response = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )
        
        issue1_id = response.get("id")
        print(f"✅ Created Issues+Questions entry: {issue1_id}")
        print(f"   Title: {issue1_title}")
        print(f"   URL: https://www.notion.so/{issue1_id.replace('-', '')}")
        
        return issue1_id
        
    except Exception as e:
        print(f"❌ Failed to create Issues+Questions entry: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution"""
    print("Creating Issues+Questions entries for compliance gaps...")
    print("=" * 80)
    
    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not set", file=sys.stderr)
        return 1
    
    client = Client(auth=token)
    
    issue_id = create_compliance_issues(client)
    
    if issue_id:
        print("\n" + "=" * 80)
        print("COMPLIANCE ISSUES CREATED")
        print("=" * 80)
        return 0
    else:
        print("\n" + "=" * 80)
        print("FAILED TO CREATE COMPLIANCE ISSUES")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())




