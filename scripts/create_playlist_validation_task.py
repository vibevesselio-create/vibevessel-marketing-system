#!/usr/bin/env python3
"""
Create validation task for playlist organization fix verification.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
ISSUE_ID = "2e4e7361-6c27-8147-9c40-e48e48f6621d"

def create_validation_task(client: Client):
    """Create validation task in Agent-Tasks database."""
    print("Creating validation task...")
    
    task_description = """## Validation Task: Playlist Organization Fix Verification

### Background
Code verification confirms that all fixes mentioned in the issue are already implemented:
- ✅ `--mode playlist` is in argparse choices
- ✅ `sync_soundcloud_playlist.py` uses `--mode playlist`
- ✅ Playlist filtering logic exists
- ✅ Playlist directory organization implemented

### Required Validation Steps

1. **End-to-End Testing**:
   - Sync a SoundCloud playlist to Notion using `sync_soundcloud_playlist.py`
   - Run production workflow: `python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode playlist`
   - Verify tracks are organized into correct playlist directories (not "Unassigned")
   - Verify Eagle tags include playlist names
   - Check that batch mode only processes playlist tracks, not all tracks

2. **Verification Checklist**:
   - [ ] Tracks sync to Notion with playlist relations
   - [ ] Files output to correct playlist directories
   - [ ] Eagle tags include playlist name
   - [ ] Only playlist tracks processed (not all tracks)
   - [ ] No tracks placed in "Unassigned" when playlist exists

3. **If Validation Passes**:
   - Update issue status to "Resolved"
   - Document test results in issue
   - Close issue

4. **If Validation Fails**:
   - Document actual failure points
   - Create new issue with specific problems found
   - Link to original issue

### Related Issue
Issue ID: 2e4e7361-6c27-8147-9c40-e48e48f6621d
Issue: CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow

### Verification Script
Run: `python3 scripts/verify_playlist_organization_fix.py`
"""
    
    try:
        # Create task
        task_properties = {
            "Task Name": {
                "title": [{"text": {"content": "Validate Playlist Organization Fix - End-to-End Testing"}}]
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
        
        # Try to link to issue if possible
        try:
            task_properties["Related Issues"] = {
                "relation": [{"id": ISSUE_ID}]
            }
        except:
            pass  # Property might not exist
        
        new_task = client.pages.create(
            parent={"database_id": AGENT_TASKS_DB_ID},
            properties=task_properties
        )
        
        task_id = new_task.get("id")
        task_url = new_task.get("url", "")
        print(f"✅ Created validation task: {task_url}")
        return task_id
        
    except Exception as e:
        print(f"❌ Error creating validation task: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_issue_status(client: Client):
    """Update issue status to reflect verification findings."""
    print("\nUpdating issue status...")
    
    try:
        # Add verification results to issue description
        verification_note = """

---

## Verification Results (2026-01-10)

**Status**: Code verification completed - All fixes appear to be implemented

**Verification Script**: `scripts/verify_playlist_organization_fix.py`

**Results**:
- ✅ `--mode playlist` is in argparse choices (line 10184)
- ✅ `sync_soundcloud_playlist.py` uses `--mode playlist` (line 656)
- ✅ Playlist filtering logic exists (`find_tracks_with_playlist_relations()`)
- ✅ Playlist directory organization implemented (`get_playlist_names_from_track()`)
- ✅ Multiple playlist property name candidates supported

**Next Steps**: Manual end-to-end testing required to confirm functionality. Validation task created in Agent-Tasks database.
"""
        
        # Get current issue
        issue = client.pages.retrieve(ISSUE_ID)
        current_description = ""
        
        # Extract current description
        props = issue.get("properties", {})
        desc_prop = props.get("Description", {})
        if desc_prop.get("type") == "rich_text":
            rich_text = desc_prop.get("rich_text", [])
            current_description = "".join([item.get("text", {}).get("content", "") for item in rich_text])
        
        # Append verification note
        new_description = current_description + verification_note
        
        # Update issue
        client.pages.update(
            ISSUE_ID,
            properties={
                "Description": {
                    "rich_text": [{"text": {"content": new_description}}]
                },
                "Status": {
                    "status": {"name": "In Progress"}  # Changed from "Unreported" to "In Progress"
                }
            }
        )
        
        print("✅ Updated issue with verification results")
        print("   Status changed to: In Progress")
        
    except Exception as e:
        print(f"⚠️  Could not update issue status: {e}")
        import traceback
        traceback.print_exc()

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
    
    # Create validation task
    task_id = create_validation_task(client)
    
    # Update issue status
    update_issue_status(client)
    
    print("\n✅ Validation task creation complete")
    if task_id:
        print(f"   Task ID: {task_id}")

if __name__ == "__main__":
    main()
