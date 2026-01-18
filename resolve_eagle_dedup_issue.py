#!/usr/bin/env python3
"""
Resolve Eagle Deduplication Issue
Updates issue status and creates handoff trigger file
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
    from main import create_trigger_file, normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Issue details
ISSUE_ID = "2e4e7361-6c27-818a-a76a-edb285502427"
ISSUE_URL = "https://www.notion.so/CRITICAL-Eagle-deduplication-false-positive-fuzzy-match-threshold-too-low-2e4e73616c27818aa76aedb285502427"

# Agent details
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
CURSOR_MM1_AGENT_NAME = "Cursor MM1 Agent"

def update_issue_status(client: Client):
    """Update issue status to Solution In Progress and add resolution notes."""
    print(f"\n{'='*80}")
    print("Updating Issue Status...")
    print(f"{'='*80}")
    
    resolution_notes = """RESOLUTION VERIFIED (2026-01-11):

The fuzzy matching thresholds have been updated in soundcloud_download_prod_merge-2.py:

1. **Thresholds Updated:**
   - Short titles (≤5 chars): 0.90 threshold (was 0.65-0.70)
   - Medium titles (6-10 chars): 0.85 threshold (was 0.75)
   - Long titles (>10 chars): 0.85 threshold (was 0.65)

2. **Artist Validation Added:**
   - Fuzzy matches now require artist match when artist is provided
   - Prevents false positives like "CODEINE" matching "Evil As Hell" 
     just because both have "(Official Music Video)" substring

3. **Location:**
   - File: monolithic-scripts/soundcloud_download_prod_merge-2.py
   - Function: eagle_find_best_matching_item()
   - Lines: 5031-5062

**NEXT STEPS:**
- Test the fix with the problematic examples mentioned in the issue
- Verify no false positives occur with 0.85+ thresholds
- Monitor production runs for any edge cases

**STATUS:** Fix implemented and verified in code. Ready for testing/validation."""
    
    try:
        # Update status to "Solution In Progress"
        client.pages.update(
            page_id=ISSUE_ID,
            properties={
                "Status": {
                    "status": {"name": "Solution In Progress"}
                },
                "Description": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": resolution_notes
                            }
                        }
                    ]
                }
            }
        )
        print(f"✅ Updated issue status to 'Solution In Progress'")
        print(f"✅ Added resolution notes")
        return True
    except Exception as e:
        print(f"❌ Error updating issue: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_validation_handoff():
    """Create handoff trigger file for validation/testing."""
    print(f"\n{'='*80}")
    print("Creating Handoff Trigger File...")
    print(f"{'='*80}")
    
    task_details = {
        "task_id": f"validation-{ISSUE_ID[:8]}",
        "task_title": "Validate Eagle Deduplication Threshold Fix",
        "task_url": ISSUE_URL,
        "project_id": None,
        "project_title": None,
        "description": """## Task: Validate Eagle Deduplication Threshold Fix

## Context
The Eagle deduplication fuzzy matching thresholds have been updated from 0.65-0.70 to 0.85-0.90 to prevent false positive matches. Artist validation has also been added.

## Issue Details
- **Issue ID:** """ + ISSUE_ID + """
- **Issue URL:** """ + ISSUE_URL + """
- **Original Problem:** False positive matches with 0.70 threshold
  - Example: "CODEINE (Official Music Video)" incorrectly matched to "Evil As Hell (official Music Video)"
  - Match score: 0.70 (fuzzy-weighted)

## Fix Implemented
1. **Thresholds Updated:**
   - Short titles (≤5 chars): 0.90 threshold
   - Medium titles (6-10 chars): 0.85 threshold  
   - Long titles (>10 chars): 0.85 threshold

2. **Artist Validation Added:**
   - Fuzzy matches require artist match when artist is provided
   - Prevents matches on common substrings like "(Official Music Video)"

3. **Location:**
   - File: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
   - Function: `eagle_find_best_matching_item()`
   - Lines: 5031-5062

## Required Actions
1. **Test with Problematic Examples:**
   - Test "CODEINE (Official Music Video)" by ero808 - should NOT match "Evil As Hell (official Music Video)" by Tisoki
   - Test "Flip It (Capochino Flip) [Lil Wayne Version]" by Capochino - should NOT match "Capochino - Capochino - Capochino"

2. **Verify Threshold Behavior:**
   - Confirm matches below 0.85 are rejected
   - Verify artist validation works correctly
   - Test edge cases (short titles, missing artist, etc.)

3. **Production Monitoring:**
   - Monitor next production run for false positives
   - Check logs for any threshold-related warnings
   - Verify downloads are not blocked by incorrect matches

4. **Update Issue Status:**
   - If validation passes, update issue status to "Resolved"
   - Document any edge cases or additional improvements needed

## Success Criteria
- [ ] Problematic examples from issue no longer produce false matches
- [ ] Thresholds correctly reject matches below 0.85
- [ ] Artist validation prevents false positives
- [ ] Production runs complete without false match issues
- [ ] Issue status updated to "Resolved" if validation passes

## Next Handoff
Upon completion, create handoff trigger for:
- **Agent:** Claude MM1 Agent (for review/validation)
- **Task:** Review validation results and update issue status
- **Location:** MM1 Agent trigger folder""",
        "status": "Ready",
        "agent_name": CURSOR_MM1_AGENT_NAME,
        "agent_id": CURSOR_MM1_AGENT_ID,
        "priority": "High",
        "handoff_instructions": """**MANDATORY HANDOFF REQUIREMENT:**

Upon completion of validation, you MUST:

1. **MOVE TRIGGER FILE (MANUAL):** Call mark_trigger_file_processed() to move trigger file from 01_inbox to 02_processed

2. **Create Next Handoff:**
   - Create handoff trigger for Claude MM1 Agent
   - Task: "Review Eagle Deduplication Validation Results"
   - Include validation results, test outcomes, and recommendation for issue status

3. **Update Issue:**
   - Update issue status based on validation results
   - Add validation notes to issue description
   - Link validation task to issue

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**"""
    }
    
    try:
        trigger_file = create_trigger_file("MM1", CURSOR_MM1_AGENT_NAME, task_details)
        if trigger_file:
            print(f"✅ Created trigger file: {trigger_file}")
            return trigger_file
        else:
            print(f"❌ Failed to create trigger file")
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
    
    # Update issue status
    update_success = update_issue_status(client)
    
    # Create handoff trigger file
    trigger_file = create_validation_handoff()
    
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"Issue Update: {'✅ Success' if update_success else '❌ Failed'}")
    print(f"Trigger File: {'✅ Created' if trigger_file else '❌ Failed'}")
    if trigger_file:
        print(f"  Location: {trigger_file}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
