#!/usr/bin/env python3
"""
Report Prompt Execution Failure to Notion

This script creates an issue in Notion reporting that the prompt submission
failed to complete tasks or resolve issues as intended.
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Try to import notion-client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.error("notion-client library not available. Install with: pip install notion-client")
    sys.exit(1)

# Database IDs
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")  # Issues+Questions

def get_notion_token():
    """Get Notion API token from environment or unified_config"""
    token = (
        os.getenv("NOTION_TOKEN") or 
        os.getenv("NOTION_API_TOKEN") or 
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    if token:
        return token
    
    # Fallback to unified_config
    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        if token:
            return token
    except Exception as e:
        logger.debug(f"unified_config import failed: {e}")
    
    return None

def create_failure_report_issue(notion_client):
    """Create an issue in Notion reporting the prompt execution failure"""
    
    issue_title = "CRITICAL: Prompt Execution Failure — main.py Script Did Not Resolve Issues"
    
    issue_description = """**Issue Type:** Prompt Execution Failure / Script Behavior Gap

**Summary:**
The prompt submission explicitly requested that the script "attempt to identify and implement a solution to resolve this issue yourself" before creating handoff tasks. However, the script execution did NOT result in task completion or issue resolution, which is a failure of the prompt's intended purpose.

**Expected Behavior (per prompt):**
1. ✅ Review all outstanding issues in Notion - **COMPLETED**
2. ✅ Identify the most critical and actionable issue - **COMPLETED**
3. ❌ **FAILED**: Attempt to identify and implement a solution to resolve this issue directly
4. ❌ **FAILED**: Only create handoff tasks when blocked or after completion
5. ❌ **FAILED**: Complete tasks or resolve issues

**Actual Behavior:**
- Script found 100 outstanding issues ✅
- Script identified critical issue ✅
- Script immediately created planning task for Claude MM1 Agent ❌
- Script did NOT attempt direct resolution ❌
- Script did NOT complete any tasks ❌
- Script did NOT resolve any issues ❌

**Evidence:**
- **Execution Log:** `notion_task_manager.log`
- **Last Execution:** 2026-01-01 19:39:41 UTC
- **Pattern Observed:** Script repeatedly creates "Plan Resolution" tasks instead of attempting resolution
- **Related Issue:** "CRITICAL: main.py Script Gap — Creates Handoff Tasks Instead of Resolving Issues Directly" (ID: 2dbe7361-6c27-8190-8779-c31275ff8737)
- **Script Location:** `main.py` lines 673-911 (`handle_issues` function)

**Impact:**
- Prompt purpose is not being fulfilled
- Issues remain unresolved
- Tasks are not being completed
- Creates unnecessary planning tasks instead of resolution attempts
- Script behavior does not match prompt requirements

**Root Cause:**
The `handle_issues()` function in `main.py` is designed to create planning tasks rather than attempt direct resolution. The function:
- Finds critical issues ✅
- Immediately creates "Plan Resolution" task for Claude MM1 Agent ❌
- Does NOT include any resolution attempt logic ❌
- Does NOT analyze issue to determine if it can be resolved directly ❌

**Required Actions:**
1. **IMMEDIATE:** Enhance `handle_issues()` function to attempt direct issue resolution
2. Add issue type classification and resolution strategies
3. Implement resolution attempt logic based on issue type/description
4. Only create handoff tasks when blocked or after completion
5. Add resolution attempt logging and outcomes tracking
6. Update script to fulfill prompt requirements

**Related Files:**
- `main.py` (lines 673-911: `handle_issues` function)
- `execute_notion_workflow.py` (has placeholder `attempt_issue_resolution` function)
- `PROMPT_EXECUTION_REVIEW_REPORT.md` (analysis document)

**Timestamp:** 2026-01-01 19:40:00 UTC
"""
    
    # Truncate description if too long (Notion has limits)
    if len(issue_description) > 1999:
        issue_description = issue_description[:1996] + "..."
    
    try:
        # Get database schema to find valid status values
        default_status = None
        try:
            db_schema = notion_client.databases.retrieve(database_id=ISSUES_DB_ID)
            status_prop = db_schema.get("properties", {}).get("Status", {})
            if status_prop.get("type") == "status":
                status_options = status_prop.get("status", {}).get("options", [])
                # Try to find "Unreported" or "Open" or first available status
                for option in status_options:
                    option_name = option.get("name", "")
                    if option_name in ["Unreported", "Open", "In Progress"]:
                        default_status = option_name
                        break
                # If no preferred status found, use first non-completed one
                if not default_status and status_options:
                    for option in status_options:
                        option_name = option.get("name", "")
                        if option_name not in ["Resolved", "Closed", "Completed", "Done"]:
                            default_status = option_name
                            break
        except Exception as e:
            logger.debug(f"Could not retrieve database schema: {e}")
        
        # Build properties
        properties = {
            "Name": {
                "title": [{"text": {"content": issue_title}}]
            },
            "Description": {
                "rich_text": [{"text": {"content": issue_description}}]
            },
            "Priority": {
                "select": {"name": "Critical"}
            },
            "Type": {
                "multi_select": [
                    {"name": "Internal Issue"},
                    {"name": "Script Issue"}
                ]
            }
        }
        
        # Only add Status if we have a valid default_status
        if default_status:
            properties["Status"] = {
                "status": {"name": default_status}
            }
        
        # Create the issue page
        response = notion_client.pages.create(
            parent={"database_id": ISSUES_DB_ID},
            properties=properties
        )
        
        issue_id = response.get("id")
        issue_url = response.get("url", "")
        
        logger.info(f"✅ Created failure report issue in Notion:")
        logger.info(f"   Issue ID: {issue_id}")
        logger.info(f"   Issue URL: {issue_url}")
        logger.info(f"   Issue Title: {issue_title}")
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Failed to create failure report issue: {e}", exc_info=True)
        return None

def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Reporting Prompt Execution Failure to Notion")
    logger.info("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        logger.error("NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    # Initialize Notion client
    try:
        notion_client = Client(auth=token)
        logger.info("Notion client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        sys.exit(1)
    
    # Create failure report issue
    result = create_failure_report_issue(notion_client)
    
    if result:
        logger.info("=" * 80)
        logger.info("✅ Failure report issue created successfully")
        logger.info("=" * 80)
        sys.exit(0)
    else:
        logger.error("=" * 80)
        logger.error("❌ Failed to create failure report issue")
        logger.error("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()

