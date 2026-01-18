#!/usr/bin/env python3
"""
Update Playlist Issue Status and Create Validation Trigger
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from notion_client import Client
from shared_core.notion.token_manager import get_notion_token
from main import create_trigger_file, NotionManager, get_agent_inbox_path
from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions

# Issue details
ISSUE_ID = "2e4e7361-6c27-8147-9c40-e48e48f6621d"
ISSUE_URL = "https://www.notion.so/CRITICAL-Playlist-Track-Organization-and-Tagging-Not-Working-in-Production-Workflow-2e4e73616c2781479c40e48e48f6621d"

def main():
    # Get Notion client
    token = get_notion_token()
    if not token:
        print("❌ Error: Could not get Notion token")
        sys.exit(1)

    client = Client(auth=token)
    notion = NotionManager(token)

    # Update issue status to 'In Progress' since validation is needed
    try:
        client.pages.update(
            page_id=ISSUE_ID,
            properties={
                "Status": {
                    "status": {"name": "In Progress"}
                }
            }
        )
        print(f"✅ Updated issue status to: In Progress")
    except Exception as e:
        print(f"⚠️  Warning: Could not update issue status: {e}")

    # Create validation trigger file
    agent_type = "MM1"
    agent_name = "Cursor MM1 Agent"
    agent_id = "249e7361-6c27-8100-8a74-de7eabb9fc8d"

    task_description = add_mandatory_next_handoff_instructions(
        description=f"""## Validation Task: Playlist Organization Fix Verification

**Issue:** CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow
**Issue ID:** {ISSUE_ID}
**Issue URL:** {ISSUE_URL}

**Fix Status:** Code fixes have been implemented and verified in codebase:
1. ✅ `find_tracks_with_playlist_relations()` now checks multiple playlist property names (Playlist, Playlists, Playlist Title, Playlist Name, Playlist Names, Playlist Relation, Related Playlists)
2. ✅ `find_tracks_with_playlist_relations_batch()` has the same fix
3. ✅ `sync_soundcloud_playlist.py` uses `--mode playlist` correctly (line 656)
4. ✅ `--mode playlist` is in argparse choices (line 10439)

**Validation Required:**
1. Test playlist mode execution: `python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode playlist --limit 5`
2. Verify tracks with playlist relations are filtered correctly
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
        detailed_instructions="Upon successful validation, update the issue status to 'Resolved' in Notion and document validation results in the issue description."
    )

    task_details = {
        "task_id": "TO_BE_CREATED",
        "task_title": "Validate Playlist Track Organization Fix",
        "task_url": "",
        "project_id": None,
        "project_title": "Playlist Organization Issue Resolution",
        "description": task_description,
        "status": "Ready",
        "agent_name": agent_name,
        "agent_id": agent_id,
        "priority": "High",
        "handoff_instructions": (
            "Validate that the playlist organization fix works correctly in production. "
            "Test with a small sample of tracks and verify all aspects of the fix. "
            "Upon completion, you MUST create a handoff trigger file for Claude MM1 Agent "
            "to update issue status to Resolved. See task description for mandatory handoff requirements."
        )
    }

    trigger_file = create_trigger_file(agent_type, agent_name, task_details)
    if trigger_file:
        print(f"✅ Created validation trigger file: {trigger_file}")
        return 0
    else:
        print("❌ Failed to create trigger file")
        return 1

if __name__ == "__main__":
    sys.exit(main())
