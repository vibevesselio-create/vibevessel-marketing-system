#!/usr/bin/env python3
"""
Create handoff trigger file for playlist issue resolution validation.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from main import (
    create_trigger_file,
    get_notion_token,
    NotionManager,
    CURSOR_MM1_AGENT_ID,
    ISSUES_DB_ID
)

def main():
    """Create handoff trigger file for issue resolution validation."""
    
    issue_id = "2e4e7361-6c27-8147-9c40-e48e48f6621d"
    issue_title = "CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow"
    issue_url = "https://www.notion.so/CRITICAL-Playlist-Track-Organization-and-Tagging-Not-Working-in-Production-Workflow-2e4e73616c2781479c40e48e48f6621d"
    
    # Get Notion token and client
    token = get_notion_token()
    if not token:
        print("❌ Error: Could not get Notion token")
        sys.exit(1)
    
    notion = NotionManager(token)
    
    # Prepare handoff instructions
    handoff_instructions = """## Issue Resolution Summary

**Issue:** CRITICAL: Playlist Track Organization and Tagging Not Working in Production Workflow
**Issue ID:** 2e4e7361-6c27-8147-9c40-e48e48f6621d
**Status:** Code fixes implemented

## Fixes Implemented

### 1. Added "playlist" to argparse choices
**File:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`
**Line:** 10184
**Change:** Added "playlist" to the choices list in argparse

### 2. Implemented playlist mode handling in main()
**File:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`
**Lines:** ~10331-10348
**Change:** Added elif clause to handle `args.mode == "playlist"` with filter_criteria="playlist"

### 3. Updated sync script to use playlist mode
**File:** `scripts/sync_soundcloud_playlist.py`
**Line:** 656
**Change:** Changed `"--mode", "batch"` to `"--mode", "playlist"`

## Required Actions

1. **TEST THE FIXES:**
   - Run a test playlist sync: `python3 scripts/sync_soundcloud_playlist.py <playlist_url> --playlist-name "Test Playlist"`
   - Verify that tracks are organized into correct playlist folders (not "Unassigned")
   - Verify Eagle tags include playlist name
   - Verify only newly-synced playlist tracks are processed (not all tracks)

2. **VERIFY PROPERTY CONSISTENCY:**
   - Confirm that "Playlist" property name is consistent between scripts
   - Both scripts use dynamic property resolution, so this should be fine

3. **UPDATE ISSUE STATUS:**
   - Update issue status to "Solution In Progress" or "Troubleshooting" as appropriate
   - Add test results and any additional findings

4. **CREATE NEXT HANDOFF:**
   - If tests pass, create Agent Work Validation Task for final review
   - If issues found, document in issue and create appropriate follow-up task
   - Ensure downstream handoff awareness is included

5. **DOCUMENTATION:**
   - Document any edge cases discovered during testing
   - Update workflow documentation if needed

## Success Criteria

- ✅ Playlist tracks are downloaded to correct playlist folders
- ✅ Eagle tags include playlist name for organization
- ✅ Only playlist-specific tracks are processed (not all tracks)
- ✅ Issue can be marked as resolved after validation

## Mandatory Handoff Requirement

**CRITICAL:** Upon completion of testing and validation, you MUST create the next handoff trigger file with:
- Test results and validation findings
- Link back to this issue
- Next steps (either mark resolved or create additional tasks)
- Ensure all work is documented and synchronized to Notion

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    task_details = {
        "task_id": f"issue-validation-{issue_id[:8]}",
        "task_title": f"Validate Playlist Issue Resolution: {issue_title[:50]}",
        "task_url": issue_url,
        "project_id": None,
        "project_title": None,
        "description": handoff_instructions,
        "status": "Ready",
        "agent_id": CURSOR_MM1_AGENT_ID,
        "priority": "High",
        "handoff_instructions": handoff_instructions
    }
    
    # Create trigger file for Cursor MM1 Agent (implementation/testing agent)
    trigger_file = create_trigger_file(
        agent_type="MM1",
        agent_name="Cursor MM1 Agent",
        task_details=task_details
    )
    
    if trigger_file:
        print(f"✅ Created handoff trigger file: {trigger_file}")
        print(f"📋 Issue: {issue_title}")
        print(f"🔗 Issue URL: {issue_url}")
        return 0
    else:
        print("❌ Failed to create handoff trigger file")
        return 1

if __name__ == "__main__":
    sys.exit(main())
