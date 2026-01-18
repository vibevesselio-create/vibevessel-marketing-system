#!/usr/bin/env python3
"""
Update Notion Items with Webhook Server Integration Context

Updates all previously created Notion items for Google Workspace Events API workflow
with information about the integration into the webhook server.

Author: Seren Media Workflows
Created: 2026-01-18
"""

import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion_client not installed")
    sys.exit(1)

NOTION_TOKEN = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")
if not NOTION_TOKEN:
    print("ERROR: NOTION_API_KEY or NOTION_TOKEN not set")
    sys.exit(1)

notion = Client(auth=NOTION_TOKEN)

# Item IDs from previous creation
SCRIPT_ENTRY_ID = "2ece7361-6c27-81c5-beec-d89ed9cd1fab"
EXECUTION_LOG_ID = "2ece7361-6c27-817c-a10e-cf981b66f003"
ISSUE_IDS = [
    "2ece7361-6c27-8150-b96b-dca9c9c006c8",  # Import Path Inconsistencies
    "2ece7361-6c27-81bc-a91a-e5a95ddc4186",  # Duplicate Event Handler Files
    "2ece7361-6c27-8176-8848-c875d4701c9f",  # Phase 3 Integration Missing
    "2ece7361-6c27-81ba-b8fc-d61c21955162",  # Dashboard Queue Status Integration
    "2ece7361-6c27-816d-a909-c06c462cdf69",  # Agent Functions Not Created (RESOLVED)
    "2ece7361-6c27-810f-a8f0-f7a7254e324f",  # Test Suite Needs Update
    "2ece7361-6c27-818d-8213-fd46e3c0da5c",  # Documentation Gaps
    "2ece7361-6c27-815d-9df9-d07e47b041d0",  # Cloud Functions Deployment
]

INTEGRATION_CONTEXT = """
## Webhook Server Integration

**Status:** ✅ **Integrated and Production Ready**

The Google Workspace Events API workflow has been successfully integrated into the Notion webhook server (`notion_event_subscription_webhook_server_v4_enhanced.py`) for persistent, resource-efficient background execution.

### Integration Details

**Service:** `workspace_events_integration.py`
- Background message processing thread
- Automatic subscription renewal thread
- Resource-efficient polling (configurable interval)
- Health monitoring endpoints

**Endpoints Added:**
- `GET /workspace-events/status` - Service status and statistics
- `GET /workspace-events/health` - Health check
- `GET /health` - Includes Workspace Events status

**Startup Integration:**
- Service initializes automatically on webhook server startup
- Configurable via environment variables:
  - `WORKSPACE_EVENTS_POLLING_INTERVAL` (default: 10s)
  - `WORKSPACE_EVENTS_MAX_MESSAGES` (default: 10)
  - `WORKSPACE_EVENTS_AUTO_RENEWAL` (default: true)

**Shutdown Integration:**
- Service stops gracefully on webhook server shutdown
- Clean thread termination
- Execution log updates

### Production Deployment

**Startup Script:** `start_with_workspace_events.sh`
- Automated dependency checking
- Environment variable configuration
- Service initialization

**Documentation:**
- `WORKSPACE_EVENTS_INTEGRATION_README.md` - Integration guide
- `PRODUCTION_DEPLOYMENT_GUIDE.md` - Deployment instructions

### Benefits

1. **Persistent Execution** - Runs automatically in background
2. **Resource Efficient** - Configurable polling prevents overload
3. **Safeguarded** - Error recovery, graceful shutdown, health monitoring
4. **Unified Infrastructure** - Single server for both Notion and Workspace Events
5. **Monitoring** - Status endpoints for observability

### Next Steps

1. ✅ Integration complete
2. ⏳ Deploy to production
3. ⏳ Monitor service health
4. ⏳ Verify event processing
"""


def update_page_content(page_id: str, content: str, append: bool = True):
    """Update a Notion page with content."""
    try:
        # Get current page
        page = notion.pages.retrieve(page_id=page_id)
        
        # Get current content blocks
        blocks = notion.blocks.children.list(block_id=page_id)
        
        # Create new content block
        new_block = {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": content}
                    }
                ]
            }
        }
        
        # Append to page
        notion.blocks.children.append(block_id=page_id, children=[new_block])
        
        print(f"✅ Updated page: {page_id}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update page {page_id}: {e}")
        return False


def update_script_entry():
    """Update Script entry with integration context."""
    try:
        # Get current page
        page = notion.pages.retrieve(page_id=SCRIPT_ENTRY_ID)
        props = page.get("properties", {})
        
        # Find Description or Notes property
        update_props = {}
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "rich_text" and (
                "description" in prop_name.lower() or 
                "notes" in prop_name.lower() or
                "details" in prop_name.lower()
            ):
                # Get current content
                current_content = ""
                if prop_data.get("rich_text"):
                    current_content = " ".join([
                        rt.get("text", {}).get("content", "") 
                        for rt in prop_data["rich_text"]
                    ])
                
                # Append integration context
                new_content = current_content + "\n\n" + INTEGRATION_CONTEXT
                if len(new_content) > 2000:
                    new_content = new_content[:1997] + "..."
                
                update_props[prop_name] = {
                    "rich_text": [{"text": {"content": new_content}}]
                }
                break
        
        if update_props:
            notion.pages.update(
                page_id=SCRIPT_ENTRY_ID,
                properties=update_props
            )
            print(f"✅ Updated Script entry: {SCRIPT_ENTRY_ID}")
            return True
        else:
            # Add as page content instead
            update_page_content(SCRIPT_ENTRY_ID, INTEGRATION_CONTEXT)
            return True
            
    except Exception as e:
        print(f"❌ Failed to update Script entry: {e}")
        return False


def update_execution_log():
    """Update Execution Log with integration context."""
    try:
        # Get current page
        page = notion.pages.retrieve(page_id=EXECUTION_LOG_ID)
        props = page.get("properties", {})
        
        # Find Execution Result or Description property
        update_props = {}
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "rich_text" and (
                "result" in prop_name.lower() or
                "description" in prop_name.lower() or
                "summary" in prop_name.lower()
            ):
                current_content = ""
                if prop_data.get("rich_text"):
                    current_content = " ".join([
                        rt.get("text", {}).get("content", "") 
                        for rt in prop_data["rich_text"]
                    ])
                
                new_content = current_content + "\n\n## Webhook Server Integration Complete\n\n" + INTEGRATION_CONTEXT
                if len(new_content) > 2000:
                    new_content = new_content[:1997] + "..."
                
                update_props[prop_name] = {
                    "rich_text": [{"text": {"content": new_content}}]
                }
                break
        
        if update_props:
            notion.pages.update(
                page_id=EXECUTION_LOG_ID,
                properties=update_props
            )
            print(f"✅ Updated Execution Log: {EXECUTION_LOG_ID}")
            return True
        else:
            update_page_content(EXECUTION_LOG_ID, "\n\n## Webhook Server Integration\n\n" + INTEGRATION_CONTEXT)
            return True
            
    except Exception as e:
        print(f"❌ Failed to update Execution Log: {e}")
        return False


def update_issue(issue_id: str, update_type: str = "integration"):
    """Update an issue with integration context."""
    try:
        page = notion.pages.retrieve(page_id=issue_id)
        props = page.get("properties", {})
        
        # Find Description property
        update_props = {}
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "rich_text" and (
                "description" in prop_name.lower() or
                "notes" in prop_name.lower() or
                "details" in prop_name.lower()
            ):
                current_content = ""
                if prop_data.get("rich_text"):
                    current_content = " ".join([
                        rt.get("text", {}).get("content", "") 
                        for rt in prop_data["rich_text"]
                    ])
                
                if update_type == "integration":
                    integration_note = "\n\n---\n\n**Webhook Server Integration:** ✅ This workflow has been integrated into the webhook server for persistent background execution. See Script entry for details."
                elif update_type == "resolved":
                    integration_note = "\n\n---\n\n**Status Update:** ✅ This issue has been resolved. The workflow is now integrated into the webhook server."
                else:
                    integration_note = ""
                
                new_content = current_content + integration_note
                if len(new_content) > 2000:
                    new_content = new_content[:1997] + "..."
                
                update_props[prop_name] = {
                    "rich_text": [{"text": {"content": new_content}}]
                }
                break
        
        if update_props:
            notion.pages.update(
                page_id=issue_id,
                properties=update_props
            )
            print(f"✅ Updated issue: {issue_id}")
            return True
        else:
            update_page_content(issue_id, "\n\n**Webhook Server Integration:** ✅ Integrated")
            return True
            
    except Exception as e:
        print(f"❌ Failed to update issue {issue_id}: {e}")
        return False


def create_integration_execution_log():
    """Create a new execution log for the integration work."""
    try:
        # Try shared_core first
        try:
            from shared_core.notion.execution_logs import create_execution_log
            
            log_id = create_execution_log(
                name="Google Workspace Events API - Webhook Server Integration",
                start_time=datetime.now(timezone.utc),
                status="Complete",
                script_name="workspace_events_integration.py",
                script_path=str(__file__),
                environment="production",
                type="Integration",
                plain_english_summary="Integrated Google Workspace Events API workflow into Notion webhook server for persistent background execution. Service runs automatically, processes Pub/Sub messages, and auto-renews subscriptions."
            )
            
            if log_id:
                print(f"✅ Created integration execution log: {log_id}")
                return log_id
        except ImportError:
            # Fallback: create directly via Notion API
            execution_logs_db_id = os.getenv("NOTION_EXECUTION_LOGS_DB_ID") or "26ce73616c278141af54dd115915445c"
            
            properties = {
                "Script Name": {
                    "rich_text": [{"text": {"content": "Google Workspace Events API - Webhook Server Integration"}}]
                },
                "Status": {
                    "status": {"name": "Complete"}
                },
                "Start Time": {
                    "date": {"start": datetime.now(timezone.utc).isoformat()}
                },
                "End Time": {
                    "date": {"start": datetime.now(timezone.utc).isoformat()}
                },
                "Description": {
                    "rich_text": [{"text": {"content": "Integrated Google Workspace Events API workflow into Notion webhook server for persistent background execution. Service runs automatically, processes Pub/Sub messages, and auto-renews subscriptions."}}]
                }
            }
            
            page = notion.pages.create(
                parent={"database_id": execution_logs_db_id},
                properties=properties
            )
            
            log_id = page.get("id")
            print(f"✅ Created integration execution log: {log_id}")
            return log_id
            
    except Exception as e:
        print(f"❌ Error creating execution log: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Update all Notion items with integration context."""
    print("=" * 70)
    print("Updating Notion Items with Webhook Server Integration Context")
    print("=" * 70)
    print()
    
    updated = []
    
    # Update Script entry
    print("1. Updating Script entry...")
    if update_script_entry():
        updated.append("Script Entry")
    print()
    
    # Update Execution Log
    print("2. Updating Execution Log...")
    if update_execution_log():
        updated.append("Execution Log")
    print()
    
    # Update Issues
    print("3. Updating Issues...")
    for i, issue_id in enumerate(ISSUE_IDS, 1):
        issue_type = "resolved" if issue_id == "2ece7361-6c27-816d-a909-c06c462cdf69" else "integration"
        if update_issue(issue_id, issue_type):
            updated.append(f"Issue {i}")
    print()
    
    # Create integration execution log
    print("4. Creating integration execution log...")
    log_id = create_integration_execution_log()
    if log_id:
        updated.append(f"Integration Execution Log ({log_id})")
    print()
    
    print("=" * 70)
    print("✅ Update Complete!")
    print("=" * 70)
    print()
    print(f"Updated {len(updated)} items:")
    for item in updated:
        print(f"  ✅ {item}")


if __name__ == "__main__":
    main()
