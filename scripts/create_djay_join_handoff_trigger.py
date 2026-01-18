#!/usr/bin/env python3
"""Create handoff trigger file for fixing djay sync JOIN issue."""

import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import create_trigger_file

# Create trigger file for Cursor MM1 Agent (myself)
task_details = {
    'task_id': '2e7e7361-6c27-8146-9160-d143baaeb5fd',  # Issue ID
    'task_title': 'Fix djay Pro Sync Script JOIN Condition',
    'task_url': 'https://notion.so/2e7e7361-6c27-8146-9160-d143baaeb5fd',
    'description': '''Fix the incorrect JOIN condition in scripts/sync_djay_bpm_key_to_notion.py that prevents file paths from being extracted.

**Problem:**
- Current JOIN: LEFT JOIN secondaryIndex_mediaItemLocationIndex l ON m.titleID = l.rowid
- m.titleID is TEXT hash (e.g., "a2ac6506704f69c12a3dd284b56781ab")
- l.rowid is INTEGER (e.g., 411, 454, 461)
- These cannot match, resulting in all file paths being NULL/None

**Impact:**
- Cannot match djay tracks to Notion tracks (all tracks show as "not found")
- Sync script processes 10,874 tracks but updates 0 tracks
- User confirmed ALL tracks in djay library ARE in Notion

**Investigation Needed:**
1. Determine correct relationship between secondaryIndex_mediaItemIndex.titleID and secondaryIndex_mediaItemLocationIndex
2. Check if there's an intermediate table or different join key
3. Review djay_pro_library_export.py to see how it correctly extracts file paths
4. May need to use YapDatabase collection queries instead of SQL JOINs

**Files to Review:**
- scripts/sync_djay_bpm_key_to_notion.py (main script to fix)
- scripts/sync_djay_bpm_key_direct.py (reference implementation)
- scripts/djay_pro_library_export.py (see how it extracts file paths)

**Database:**
- Path: ~/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db
- Tables: secondaryIndex_mediaItemIndex, secondaryIndex_mediaItemLocationIndex

**Success Criteria:**
- File paths are correctly extracted from djay database
- Matching logic finds tracks in Notion
- Sync script successfully updates Notion tracks with BPM/Key data''',
    'handoff_instructions': '''**IMMEDIATE ACTION REQUIRED:**

1. **Investigate Database Schema:**
   - Query djay database to understand correct relationship between tables
   - Check if titleID maps to a different field in locationIndex
   - Review djay_pro_library_export.py to see correct extraction method

2. **Fix JOIN Condition:**
   - Update scripts/sync_djay_bpm_key_to_notion.py with correct JOIN
   - Test with sample queries to verify file paths are extracted
   - Ensure all 10,874 tracks have file paths

3. **Test Matching:**
   - Run script with --dry-run --limit 10
   - Verify tracks are matched in Notion
   - Check that file paths are used for matching

4. **Execute Full Sync:**
   - Once matching works, run full sync
   - Monitor progress and verify updates
   - Update issue status in Notion

**Related Issue:** 2e7e7361-6c27-8146-9160-d143baaeb5fd
**Parent Issue:** 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8''',
    'status': 'In Progress',
    'priority': 'High',
    'agent_id': '249e7361-6c27-8100-8a74-de7eabb9fc8d'  # Cursor MM1 Agent ID
}

if __name__ == "__main__":
    trigger_file = create_trigger_file(
        agent_type='MM1',
        agent_name='Cursor MM1 Agent',
        task_details=task_details
    )
    
    if trigger_file:
        print(f'✅ Created handoff trigger file: {trigger_file}')
    else:
        print('❌ Failed to create trigger file')
