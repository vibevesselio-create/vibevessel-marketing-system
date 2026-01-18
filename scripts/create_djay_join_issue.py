#!/usr/bin/env python3
"""Create Notion issue documenting djay sync JOIN problem."""

import sys
from pathlib import Path

script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from shared_core.notion.issues_questions import create_issue_or_question
from shared_core.logging import setup_logging

workspace_logger = setup_logging()

description = """**Problem:**
The djay Pro BPM/Key sync script is failing to extract file paths because the JOIN condition between secondaryIndex_mediaItemIndex and secondaryIndex_mediaItemLocationIndex is incorrect.

**Current Implementation:**
The script uses: LEFT JOIN secondaryIndex_mediaItemLocationIndex l ON m.titleID = l.rowid

**Issue:**
- m.titleID is a TEXT hash (e.g., "a2ac6506704f69c12a3dd284b56781ab")
- l.rowid is an INTEGER (e.g., 411, 454, 461)
- These cannot match, resulting in all file paths being NULL/None
- This breaks the matching logic since we rely on file paths to match tracks in Notion

**Evidence:**
- Query shows 10,874 tracks with BPM/Key data
- But 0 tracks have file paths (all fileName = None)
- Direct query of secondaryIndex_mediaItemLocationIndex shows valid file paths exist (e.g., "CHRYSALIS (Skysia Remix)_test_processed.wav", "Tick Tick Boom.m4a")

**Impact:**
- Cannot match djay tracks to Notion tracks (all tracks show as "not found")
- Sync script processes 10,874 tracks but updates 0 tracks
- User confirmed ALL tracks in djay library ARE in Notion, so matching should work

**Root Cause:**
The relationship between titleID (hash) and location rowid is not a direct 1:1 match. Need to find the correct join key or relationship.

**Investigation Needed:**
1. Determine correct relationship between secondaryIndex_mediaItemIndex.titleID and secondaryIndex_mediaItemLocationIndex
2. Check if there's an intermediate table or different join key
3. Review djay_pro_library_export.py to see how it correctly extracts file paths
4. May need to use YapDatabase collection queries instead of SQL JOINs

**Related Issue:**
- Parent issue: "BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete" (2b5e7361-6c27-8147-8cbc-e73a63dbc8f8)

**Next Steps:**
1. Investigate djay database schema to find correct relationship
2. Fix JOIN condition or use alternative extraction method
3. Test with sample tracks to verify file paths are extracted
4. Re-run sync once matching works correctly"""

if __name__ == "__main__":
    issue_id = create_issue_or_question(
        name="djay Pro Sync Script: Incorrect JOIN Condition Causing Missing File Paths",
        type=["Bug", "Technical Debt"],
        status="Unreported",
        priority="High",
        component=None,  # Remove component if it doesn't exist
        description=description,
        tags=["djay-pro", "database", "sql-join", "matching-logic"]
    )
    
    if issue_id:
        workspace_logger.info(f"✅ Created issue: {issue_id}")
        print(f"✅ Created issue: {issue_id}")
    else:
        workspace_logger.error("❌ Failed to create issue")
        print("❌ Failed to create issue")
