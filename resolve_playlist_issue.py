#!/usr/bin/env python3
"""
Resolve Playlist Organization Issue
Updates issue status and creates handoff trigger files
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    from shared_core.notion.folder_resolver import get_agent_inbox_path
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Database IDs
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")

# Issue ID
ISSUE_ID = "2e4e7361-6c27-8147-9c40-e48e48f6621d"

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent

def safe_get_property(page: dict, property_name: str, property_type: str = None):
    """Safely extract property value from Notion page."""
    try:
        properties = page.get("properties", {})
        if not properties:
            return None
        
        prop = properties.get(property_name)
        if not prop:
            return None
        
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            return None
        
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return relation_list
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def update_issue_status(client: Client, issue_id: str):
    """Update issue status to In Progress."""
    try:
        client.pages.update(
            page_id=issue_id,
            properties={
                "Status": {"status": {"name": "In Progress"}}
            }
        )
        print(f"✅ Updated issue status to 'In Progress'")
        return True
    except Exception as e:
        print(f"❌ Failed to update issue status: {e}")
        return False

def create_validation_task(client: Client, issue_id: str, issue_url: str):
    """Create validation task for the fix."""
    task_description = f"""## Validation Task: Playlist Organization Fix Verification

**Issue:** CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow
**Issue URL:** {issue_url}

## Fix Summary
The playlist mode filtering has been implemented in `efficient_batch_process_tracks()`:
- ✅ Created `find_tracks_with_playlist_relations_batch()` function for efficient batch queries
- ✅ Updated `efficient_batch_process_tracks()` to support playlist filtering
- ✅ Verified `sync_soundcloud_playlist.py` uses `--mode playlist` correctly
- ✅ Verified argparse includes "playlist" in choices

## Required Validation
1. Test playlist mode execution: `python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode playlist --limit 5`
2. Verify tracks are organized into correct playlist directories (not "Unassigned")
3. Verify Eagle tags include playlist names
4. Verify only playlist tracks are processed (not all tracks)

## Success Criteria
- [ ] Playlist mode processes only tracks with playlist relations
- [ ] Files are organized into correct playlist folders
- [ ] Eagle tags include playlist names
- [ ] No tracks end up in "Unassigned" folder when playlist relation exists

## Next Handoff
After validation, create handoff trigger file for:
- **Agent:** Cursor MM1 Agent
- **Task:** Mark issue as resolved if validation passes, or create follow-up issue if problems found
"""
    
    try:
        response = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties={
                "Task Name": {
                    "title": [{"text": {"content": "Validate Playlist Organization Fix"}}]
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
                    "relation": [{"id": CURSOR_MM1_AGENT_ID}]
                }
            }
        )
        task_id = response.get("id")
        task_url = response.get("url", "")
        print(f"✅ Created validation task: {task_url}")
        return task_id, task_url
    except Exception as e:
        print(f"❌ Failed to create validation task: {e}")
        return None, None

def create_handoff_trigger_file(agent_name: str, agent_id: str, task_id: str, task_title: str, task_url: str, description: str):
    """Create handoff trigger file."""
    try:
        inbox_path = get_agent_inbox_path(agent_name, agent_id)
        if not inbox_path:
            print(f"❌ Could not determine inbox path for {agent_name}")
            return None
        
        inbox_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_id_short = task_id.replace("-", "")[:8] if task_id else "unknown"
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.json"
        
        trigger_file = inbox_path / filename
        
        trigger_content = {
            "task_id": task_id,
            "task_title": task_title,
            "task_url": task_url,
            "project_id": None,
            "project_title": None,
            "description": description,
            "status": "Ready",
            "agent_name": agent_name,
            "agent_type": "MM1",
            "handoff_instructions": (
                "Validate the playlist organization fix by:\n"
                "1. Testing playlist mode execution\n"
                "2. Verifying tracks are organized into correct playlist directories\n"
                "3. Verifying Eagle tags include playlist names\n"
                "4. Verifying only playlist tracks are processed\n\n"
                "Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move from 01_inbox to 02_processed\n"
                "2. Update task status in Notion\n"
                "3. Update issue status to 'Resolved' if validation passes\n"
                "4. Create follow-up issue if problems are found\n"
                "5. Document validation results\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and issue status is updated."
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "priority": "High"
        }
        
        with open(trigger_file, "w", encoding="utf-8") as f:
            json.dump(trigger_content, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Created trigger file: {trigger_file}")
        return trigger_file
    except Exception as e:
        print(f"❌ Failed to create trigger file: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main execution."""
    if not NOTION_AVAILABLE:
        print("Notion client not available")
        sys.exit(1)
    
    try:
        token = get_notion_token()
        if not token:
            print("❌ Error: Could not get Notion token")
            sys.exit(1)
        
        client = Client(auth=token)
    except Exception as e:
        print(f"❌ Error initializing Notion client: {e}")
        sys.exit(1)
    
    # Get issue details
    try:
        issue_page = client.pages.retrieve(page_id=ISSUE_ID)
        issue_title = safe_get_property(issue_page, "Name", "title") or "Unknown Issue"
        issue_url = issue_page.get("url", "")
        print(f"\n📋 Issue: {issue_title}")
        print(f"🔗 URL: {issue_url}\n")
    except Exception as e:
        print(f"❌ Error retrieving issue: {e}")
        sys.exit(1)
    
    # Update issue status
    print("1. Updating issue status...")
    update_issue_status(client, ISSUE_ID)
    
    # Create validation task
    print("\n2. Creating validation task...")
    task_id, task_url = create_validation_task(client, ISSUE_ID, issue_url)
    
    if task_id and task_url:
        # Create handoff trigger file
        print("\n3. Creating handoff trigger file...")
        trigger_file = create_handoff_trigger_file(
            agent_name="Cursor MM1 Agent",
            agent_id=CURSOR_MM1_AGENT_ID,
            task_id=task_id,
            task_title="Validate Playlist Organization Fix",
            task_url=task_url,
            description="Validate that playlist mode filtering works correctly and tracks are organized properly."
        )
        
        if trigger_file:
            print(f"\n✅ Successfully created handoff trigger file: {trigger_file}")
        else:
            print("\n⚠️  Failed to create handoff trigger file")
    else:
        print("\n⚠️  Skipping trigger file creation (task creation failed)")
    
    print("\n" + "="*80)
    print("Issue resolution workflow completed")
    print("="*80)

if __name__ == "__main__":
    main()
