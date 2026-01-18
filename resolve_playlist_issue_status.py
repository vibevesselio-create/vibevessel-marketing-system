#!/usr/bin/env python3
"""
Update Playlist Issue Status and Create Validation Trigger
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
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Database IDs
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")

# Issue ID from query results
ISSUE_ID = "2e4e7361-6c27-8147-9c40-e48e48f6621d"

def update_issue_status(client: Client, issue_id: str, status: str):
    """Update issue status in Notion."""
    try:
        client.pages.update(
            page_id=issue_id,
            properties={
                "Status": {
                    "status": {"name": status}
                }
            }
        )
        print(f"✅ Updated issue status to: {status}")
        return True
    except Exception as e:
        print(f"❌ Error updating issue status: {e}")
        return False

def create_validation_trigger_file():
    """Create trigger file for validation task."""
    # Use main.py's create_trigger_file function if available
    try:
        from main import create_trigger_file, get_agent_inbox_path
        from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
        
        agent_type = "MM1"
        agent_name = "Cursor MM1 Agent"
        
        # Task details for validation
        task_details = {
            "task_id": "TO_BE_CREATED",  # Will be created by main.py or agent
            "task_title": "Validate Playlist Track Organization Fix",
            "task_url": "",
            "project_id": None,
            "project_title": "Playlist Organization Issue Resolution",
            "description": add_mandatory_next_handoff_instructions(
                description="""## Validation Task: Playlist Organization Fix Verification

**Issue:** CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow
**Issue ID:** 2e4e7361-6c27-8147-9c40-e48e48f6621d
**Issue URL:** https://www.notion.so/CRITICAL-Playlist-Track-Organization-and-Tagging-Not-Working-in-Production-Workflow-2e4e73616c2781479c40e48e48f6621d

**Fix Status:** Code fixes have been implemented and verified in codebase:
1. ✅ `find_tracks_with_playlist_relations()` now checks multiple playlist property names
2. ✅ `find_tracks_with_playlist_relations_batch()` has the same fix
3. ✅ `sync_soundcloud_playlist.py` uses `--mode playlist` correctly
4. ✅ `--mode playlist` is in argparse choices

**Validation Required:**
1. Test playlist mode execution: `python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode playlist --limit 5`
2. Verify tracks with playlist relations are processed correctly
3. Verify files are organized in correct playlist directories
4. Verify Eagle tags include playlist names
5. Confirm no tracks are placed in "Unassigned" folder incorrectly

**Success Criteria:**
- [ ] Playlist mode executes without errors
- [ ] Tracks with playlist relations are filtered correctly
- [ ] Files are organized in playlist-named directories
- [ ] Eagle tags include playlist information
- [ ] No false positives in "Unassigned" folder
""",
                next_task_name="Update Issue Status to Resolved",
                target_agent="Claude MM1 Agent",
                next_task_id="TO_BE_CREATED",
                inbox_path=str(get_agent_inbox_path("Claude MM1 Agent")) + "/",
                project_name="Playlist-Organization-Issue-Resolution",
                detailed_instructions="Upon successful validation, update the issue status to 'Resolved' in Notion and document validation results."
            ),
            "status": "Ready",
            "agent_name": agent_name,
            "agent_id": "249e7361-6c27-8100-8a74-de7eabb9fc8d",  # Cursor MM1 Agent ID
            "priority": "High",
            "handoff_instructions": (
                "Validate that the playlist organization fix works correctly in production. "
                "Test with a small sample of tracks and verify all aspects of the fix. "
                "Upon completion, create handoff to Claude MM1 Agent to update issue status to Resolved."
            )
        }
        
        trigger_file = create_trigger_file(agent_type, agent_name, task_details)
        if trigger_file:
            print(f"✅ Created validation trigger file: {trigger_file}")
            return trigger_file
        else:
            print("❌ Failed to create trigger file")
            return None
            
    except Exception as e:
        print(f"❌ Error creating trigger file: {e}")
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
    
    # Update issue status to "In Progress" since validation is needed
    print(f"Updating issue {ISSUE_ID} status to 'In Progress'...")
    update_issue_status(client, ISSUE_ID, "In Progress")
    
    # Create validation trigger file
    print("\nCreating validation trigger file...")
    trigger_file = create_validation_trigger_file()
    
    if trigger_file:
        print(f"\n✅ Success! Created validation trigger file: {trigger_file}")
        print("   Issue status updated to 'In Progress'")
        print("   Next step: Cursor MM1 Agent should validate the fix")
    else:
        print("\n⚠️  Warning: Failed to create trigger file, but issue status was updated")

if __name__ == "__main__":
    main()
