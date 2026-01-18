#!/usr/bin/env python3
"""
Create Notion Issues for Webhook Server Integration

Identifies and documents issues related to integrating Google Workspace Events API
into the webhook server.

Author: Seren Media Workflows
Created: 2026-01-18
"""

import os
import sys
from datetime import datetime
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

# Database IDs
ISSUES_DB_ID = os.getenv("NOTION_ISSUES_DB_ID") or os.getenv("ISSUES_QUESTIONS_DB_ID") or "229e73616c27808ebf06c202b10b5166"
SCRIPT_ENTRY_ID = "2ece7361-6c27-81c5-beec-d89ed9cd1fab"

# Integration-related issues
INTEGRATION_ISSUES = [
    {
        "title": "Google Workspace Events API: Webhook Server Integration - Pub/Sub Message Structure",
        "description": """**Integration Issue:** Pub/Sub message structure handling needs verification.

**Current State:**
- Integration uses `pull()` API which returns `ReceivedMessage` objects
- Event handler expects `pubsub_v1.subscriber.message.Message` (streaming pull format)
- Mock message wrapper created to bridge the gap

**Potential Issues:**
1. Message data extraction may fail if Pub/Sub API structure differs
2. Attributes handling needs verification
3. Message ID extraction may be incorrect

**Required Actions:**
1. Test with actual Pub/Sub messages
2. Verify message structure matches expectations
3. Add error handling for structure mismatches
4. Document message format requirements

**Impact:** Medium - May cause message processing failures

**Related Items:**
- Script: Google Workspace Events API - Event Handler
- Integration: workspace_events_integration.py""",
        "priority": "Medium",
        "status": "Unreported"
    },
    {
        "title": "Google Workspace Events API: Webhook Server Integration - Dependency Installation",
        "description": """**Integration Issue:** Google Cloud Pub/Sub dependencies may not be installed in webhook server environment.

**Current State:**
- `requirements.txt` updated with Google Cloud dependencies
- Dependencies marked as optional
- Service gracefully degrades if unavailable

**Potential Issues:**
1. Dependencies not installed in production environment
2. Version conflicts with other packages
3. Missing system-level dependencies

**Required Actions:**
1. Verify dependencies install correctly: `pip3 install -r requirements.txt`
2. Test import availability
3. Document installation process
4. Add dependency check to startup script

**Impact:** High - Service won't start if dependencies missing

**Related Items:**
- Script: Google Workspace Events API - Event Handler
- Integration: workspace_events_integration.py
- Requirements: requirements.txt""",
        "priority": "High",
        "status": "Unreported"
    },
    {
        "title": "Google Workspace Events API: Webhook Server Integration - Path Resolution",
        "description": """**Integration Issue:** Workspace events module path resolution may fail in webhook server context.

**Current State:**
- Integration tries multiple possible paths
- Path resolution happens at import time
- May fail if workspace_events directory not found

**Potential Issues:**
1. Path resolution fails in production
2. Import errors prevent service startup
3. Hardcoded paths may not work in all environments

**Required Actions:**
1. Test path resolution in production-like environment
2. Add environment variable for explicit path
3. Improve error messages for path resolution failures
4. Document path requirements

**Impact:** High - Service won't start if modules not found

**Related Items:**
- Script: Google Workspace Events API - Event Handler
- Integration: workspace_events_integration.py""",
        "priority": "High",
        "status": "Unreported"
    },
    {
        "title": "Google Workspace Events API: Webhook Server Integration - Thread Safety",
        "description": """**Integration Issue:** Thread safety of Workspace Events service needs verification.

**Current State:**
- Service uses daemon threads for background processing
- Thread-safe queue processing
- Statistics tracking may have race conditions

**Potential Issues:**
1. Statistics updates may not be thread-safe
2. Error list appends may have race conditions
3. Service state changes may not be atomic

**Required Actions:**
1. Review thread safety of statistics updates
2. Add locks for shared state if needed
3. Test concurrent access scenarios
4. Document thread safety guarantees

**Impact:** Low - May cause minor data inconsistencies

**Related Items:**
- Script: Google Workspace Events API - Event Handler
- Integration: workspace_events_integration.py""",
        "priority": "Low",
        "status": "Unreported"
    },
    {
        "title": "Google Workspace Events API: Webhook Server Integration - Error Recovery",
        "description": """**Integration Issue:** Error recovery and retry logic needs enhancement.

**Current State:**
- Failed messages are nacked for retry
- Errors are logged to statistics
- No exponential backoff for retries

**Potential Issues:**
1. Rapid retries may overwhelm system
2. No circuit breaker for persistent failures
3. Error accumulation may cause memory issues

**Required Actions:**
1. Implement exponential backoff for retries
2. Add circuit breaker pattern
3. Limit error history size (already done - 100 max)
4. Add alerting for high error rates

**Impact:** Medium - May cause resource exhaustion

**Related Items:**
- Script: Google Workspace Events API - Event Handler
- Integration: workspace_events_integration.py""",
        "priority": "Medium",
        "status": "Unreported"
    }
]


def get_database_schema(db_id: str) -> Dict:
    """Get database schema."""
    try:
        db = notion.databases.retrieve(database_id=db_id)
        return db
    except Exception as e:
        print(f"❌ Error retrieving database schema: {e}")
        return {}


def create_issue(
    db_id: str,
    db_schema: Dict,
    title: str,
    description: str,
    priority: str = "Medium",
    status: str = "Unreported",
    related_items: Optional[List[str]] = None
) -> Optional[str]:
    """Create an issue in Notion."""
    try:
        props = db_schema.get("properties", {})
        properties = {}
        
        # Title
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "title":
                properties[prop_name] = {
                    "title": [{"text": {"content": title}}]
                }
                break
        
        # Description
        for prop_name, prop_data in props.items():
            if prop_data.get("type") == "rich_text" and (
                "description" in prop_name.lower() or 
                "notes" in prop_name.lower() or 
                "details" in prop_name.lower()
            ):
                # Truncate if too long
                desc_text = description[:1997] + "..." if len(description) > 2000 else description
                properties[prop_name] = {
                    "rich_text": [{"text": {"content": desc_text}}]
                }
                break
        
        # Priority
        for prop_name, prop_data in props.items():
            if prop_name == "Priority" and prop_data.get("type") == "select":
                properties[prop_name] = {
                    "select": {"name": priority}
                }
                break
        
        # Status
        for prop_name, prop_data in props.items():
            if prop_name == "Status" and prop_data.get("type") == "status":
                # Validate status
                status_options = prop_data.get("status", {}).get("options", [])
                valid_statuses = [opt.get("name") for opt in status_options]
                if status not in valid_statuses:
                    status = "Unreported"
                properties[prop_name] = {
                    "status": {"name": status}
                }
                break
        
        # Related Script
        if SCRIPT_ENTRY_ID:
            for prop_name, prop_data in props.items():
                if (
                    ("script" in prop_name.lower() or "related" in prop_name.lower()) and 
                    prop_data.get("type") == "relation"
                ):
                    related_ids = [{"id": SCRIPT_ENTRY_ID}]
                    if related_items:
                        related_ids.extend([{"id": rid} for rid in related_items])
                    properties[prop_name] = {
                        "relation": related_ids
                    }
                    break
        
        # Create page
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=properties
        )
        
        page_id = page['id']
        print(f"✅ Created issue: {title} - {page_id}")
        return page_id
        
    except Exception as e:
        print(f"❌ Failed to create issue '{title}': {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Create integration issues."""
    print("=" * 70)
    print("Creating Integration Issues")
    print("=" * 70)
    print()
    
    # Get database schema
    print("1. Retrieving Issues+Questions database schema...")
    db_schema = get_database_schema(ISSUES_DB_ID)
    if not db_schema:
        print("❌ Cannot proceed without database schema")
        return
    
    print(f"✅ Retrieved schema")
    print()
    
    # Create issues
    print("2. Creating integration issues...")
    created = []
    for issue in INTEGRATION_ISSUES:
        page_id = create_issue(
            db_id=ISSUES_DB_ID,
            db_schema=db_schema,
            title=issue["title"],
            description=issue["description"],
            priority=issue["priority"],
            status=issue["status"],
            related_items=[SCRIPT_ENTRY_ID]
        )
        if page_id:
            created.append({
                "title": issue["title"],
                "page_id": page_id,
                "priority": issue["priority"]
            })
    
    print()
    print("=" * 70)
    print("✅ Issue Creation Complete!")
    print("=" * 70)
    print()
    print(f"Summary: {len(created)}/{len(INTEGRATION_ISSUES)} issues created")
    print()
    
    if created:
        print("Created Issues:")
        for i, issue in enumerate(created, 1):
            print(f"  {i}. [{issue['priority']}] {issue['title']}")
            print(f"     Page ID: {issue['page_id']}")
            print()


if __name__ == "__main__":
    main()
