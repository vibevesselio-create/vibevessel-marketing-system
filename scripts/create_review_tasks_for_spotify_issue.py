#!/usr/bin/env python3
"""
Create Agent-Tasks for reviewing and fixing the Spotify track download issue.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared_core.notion.token_manager import get_notion_token
    import requests
    import json
    
    token = get_notion_token()
    if not token:
        print("❌ No Notion token found")
        sys.exit(1)
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json'
    }
    
    # Agent-Tasks database ID
    agent_tasks_db_id = '284e7361-6c27-8018-872a-eb14e82e0392'
    issue_id = '2e3e7361-6c27-818d-9a9b-c5508f52d916'  # The issue we just created
    
    # Get database schema first
    db_response = requests.get(
        f'https://api.notion.com/v1/databases/{agent_tasks_db_id}',
        headers=headers
    )
    
    if db_response.status_code != 200:
        print(f"❌ Could not access Agent-Tasks database: {db_response.status_code}")
        print(db_response.text[:500])
        sys.exit(1)
    
    db_schema = db_response.json().get('properties', {})
    print("✅ Agent-Tasks database accessible")
    
    # Create review tasks
    tasks = [
        {
            "name": "Review Query Filter Implementation - Spotify Track Inclusion",
            "description": """Review and verify the query filter fixes for including Spotify tracks in batch processing.

**Specific Areas:**
1. Review _build_unprocessed_tracks_query() in soundcloud_download_prod_merge-2.py (line 2730)
2. Verify query includes Spotify tracks via OR condition: (SoundCloud URL exists) OR (Spotify ID exists)
3. Test query with Notion API to ensure it returns both SoundCloud and Spotify tracks
4. Verify Notion API query structure respects API limitations (no complex nested AND/OR)
5. Confirm application code correctly filters Spotify tracks during processing (line 7029)

**Files to Review:**
- monolithic-scripts/soundcloud_download_prod_merge-2.py (lines 2730-2755, 8944-8976)

**Acceptance Criteria:**
- Query successfully returns Spotify tracks from Notion
- Query structure is valid and doesn't cause 400 errors
- Both SoundCloud and Spotify tracks are included in results""",
            "priority": "Critical",
            "assignee": "Cursor MM1 Agent"
        },
        {
            "name": "Review build_eligibility_filter() - Spotify Track Support",
            "description": """Review and verify build_eligibility_filter() includes Spotify tracks.

**Specific Areas:**
1. Review build_eligibility_filter() in soundcloud_download_prod_merge-2.py (line 8944)
2. Ensure filter includes Spotify tracks in OR condition with SoundCloud tracks
3. Verify property name resolution works for both 'DL' and 'Downloaded' property names
4. Test with actual Notion database to ensure query works

**Files to Review:**
- monolithic-scripts/soundcloud_download_prod_merge-2.py (lines 8944-8976)

**Acceptance Criteria:**
- Filter query includes Spotify tracks
- Property name resolution works correctly
- Query executes without errors""",
            "priority": "High",
            "assignee": "Cursor MM1 Agent"
        },
        {
            "name": "Review DL Property Setting for Spotify Tracks",
            "description": """Review and fix DL property setting when creating new Spotify tracks.

**Specific Areas:**
1. Review create_track_page() in spotify_integration_module.py (line 356)
2. Verify DL=False is set when creating new Spotify tracks
3. Test property name detection (DL vs Downloaded) works correctly
4. Verify database schema check works properly
5. Create script to retroactively set DL=False for existing Spotify tracks (if needed)

**Files to Review:**
- monolithic-scripts/spotify_integration_module.py (lines 356-416)

**Acceptance Criteria:**
- New Spotify tracks have DL=False set automatically
- Property name detection works for both 'DL' and 'Downloaded'
- Existing tracks can be updated retroactively""",
            "priority": "High",
            "assignee": "Cursor MM1 Agent"
        },
        {
            "name": "Review YouTube Search & Matching Functionality",
            "description": """Review YouTube search implementation for Spotify track matching.

**Specific Areas:**
1. Review search_youtube_for_track() in soundcloud_download_prod_merge-2.py (line 7377)
2. Test YouTube Data API v3 search functionality
3. Test yt-dlp fallback search functionality  
4. Verify search query format: '{artist} {title} official audio' finds correct videos
5. Test with actual tracks from phonk playlist to verify search accuracy
6. Review error handling when search fails

**Files to Review:**
- monolithic-scripts/soundcloud_download_prod_merge-2.py (lines 7377-7430)

**Acceptance Criteria:**
- YouTube search finds correct videos for Spotify tracks
- Fallback mechanism works when API key unavailable
- Search accuracy is acceptable (>80% correct matches)
- Proper error handling and logging""",
            "priority": "High",
            "assignee": "Claude Code Agent"
        },
        {
            "name": "Review Spotify Track Processing Flow - End-to-End",
            "description": """Review complete Spotify track processing workflow from detection to completion.

**Specific Areas:**
1. Review process_track() Spotify track handling (lines 7028-7135)
2. Verify Spotify track detection logic: is_spotify_track = has spotify_id AND no soundcloud_url
3. Test full workflow: Detection → YouTube Search → Download → Processing → Eagle Import → Notion Update
4. Verify error handling when YouTube search fails (metadata-only processing)
5. Test with actual playlist tracks (phonk playlist - 9 tracks)

**Files to Review:**
- monolithic-scripts/soundcloud_download_prod_merge-2.py (lines 7019-7135, 7750-8300)

**Acceptance Criteria:**
- Complete workflow executes successfully for Spotify tracks
- Files created in correct locations (/Volumes/VIBES/Playlists/phonk/)
- Eagle library import works
- Notion metadata updates correctly
- Error handling graceful when steps fail""",
            "priority": "Critical",
            "assignee": "Claude Code Agent"
        },
        {
            "name": "Review Database ID Configuration & Environment Setup",
            "description": """Review database ID configuration and ensure correct IDs are used.

**Specific Areas:**
1. Verify TRACKS_DB_ID is correctly loaded from environment (27ce7361-6c27-80fb-b40e-fefdd47d6640)
2. Check for hardcoded or cached database IDs in codebase
3. Ensure unified_config.py correctly provides TRACKS_DB_ID
4. Verify all code paths use correct database ID (no 404 errors)
5. Check environment variable loading order and precedence

**Files to Review:**
- unified_config.py
- monolithic-scripts/soundcloud_download_prod_merge-2.py (database ID loading)
- .env files

**Acceptance Criteria:**
- Correct database ID used throughout
- No hardcoded IDs
- Environment variable loading works correctly
- No 404 database errors in logs""",
            "priority": "Medium",
            "assignee": "Cursor MM1 Agent"
        },
        {
            "name": "End-to-End Testing - Spotify Playlist Download Workflow",
            "description": """Execute comprehensive end-to-end testing of Spotify playlist download workflow.

**Test Cases:**
1. Test Case 1: Sync and download phonk playlist (9 tracks)
   - Sync playlist to Notion ✅
   - Verify tracks appear in query results
   - Run batch processing
   - Verify all 9 tracks download successfully
   - Verify files created in /Volumes/VIBES/Playlists/phonk/
   - Verify Eagle library import
   - Verify Notion updates

2. Test Case 2: Sync and download d00mscrvll album (9 tracks)
   - Sync album to Notion ✅
   - Verify tracks appear in query results  
   - Run batch processing
   - Verify tracks download (or skip if already downloaded from playlist)
   - Verify deduplication works

**Verification Steps:**
- Files created in correct directory structure
- Audio files are correct format (M4A/ALAC, WAV, AIFF)
- Eagle library import successful
- Notion database updated with file paths, Eagle File IDs, metadata
- DL=True set after successful download
- BPM, key, and other metadata populated

**Expected Results:**
- All 9 tracks from phonk playlist downloaded and processed
- Files accessible and playable
- Metadata complete in Notion
- No errors in processing logs""",
            "priority": "Critical",
            "assignee": "Claude Code Agent"
        },
        {
            "name": "Error Handling & Edge Cases Review",
            "description": """Review and test error handling for edge cases in Spotify track processing.

**Edge Cases to Test:**
1. YouTube search returns no results
   - Expected: Track marked as metadata-only, logged for manual review
   
2. YouTube API quota exceeded
   - Expected: Falls back to yt-dlp search, continues processing
   
3. Download fails (network error, invalid URL, etc.)
   - Expected: Error logged, track marked with error status, continues with next track
   
4. Track has both Spotify ID and SoundCloud URL
   - Expected: Processed as SoundCloud track (SoundCloud takes priority)

5. Track has Spotify ID but YouTube search finds wrong video
   - Expected: Download proceeds, may need manual verification

**Review Areas:**
- Error handling in search_youtube_for_track()
- Error handling in download_track() for YouTube URLs
- Error handling in process_track() for Spotify tracks
- Logging and Notion status updates on errors

**Acceptance Criteria:**
- All edge cases handled gracefully
- Proper error messages logged
- Notion status updated appropriately
- Processing continues for other tracks when one fails
- No unhandled exceptions""",
            "priority": "Medium",
            "assignee": "Claude Code Agent"
        },
        {
            "name": "Performance & Optimization Review",
            "description": """Review performance and optimization opportunities for Spotify track processing.

**Areas to Review:**
1. Batch processing efficiency with Spotify tracks
   - Verify concurrent processing (max 4 tracks) works correctly
   - Check rate limiting for Notion API calls
   - Check rate limiting for YouTube API calls

2. Query optimization
   - Verify query performance with large number of tracks
   - Check if pagination works correctly
   - Verify query doesn't time out

3. YouTube search optimization
   - Review search query optimization
   - Consider caching YouTube search results in Notion
   - Review API quota usage

**Acceptance Criteria:**
- Batch processing completes efficiently
- No rate limiting issues
- Queries perform well with large datasets
- API quotas used efficiently""",
            "priority": "Low",
            "assignee": "Cursor MM1 Agent"
        },
        {
            "name": "Code Review & Documentation",
            "description": """Comprehensive code review and documentation update.

**Review Areas:**
1. Review all code changes for correctness and best practices
2. Update inline code comments explaining query filter logic
3. Document Notion API query limitations and workarounds
4. Update function docstrings with Spotify track handling notes
5. Create comprehensive test documentation
6. Update workflow documentation files

**Files to Review:**
- All modified files
- All newly created files
- Documentation files

**Documentation Updates Needed:**
- PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md
- MUSIC_WORKFLOW_IMPLEMENTATION_STATUS.md
- SPOTIFY_YOUTUBE_MATCHING_IMPLEMENTATION_COMPLETE.md (already created)

**Acceptance Criteria:**
- Code follows best practices
- Comments explain complex logic
- Documentation is up-to-date
- Test documentation complete""",
            "priority": "Medium",
            "assignee": "Claude Code Agent"
        }
    ]
    
    created_tasks = []
    
    for task_data in tasks:
        # Build task properties based on actual database schema
        properties = {
            "Task Name": {
                "title": [{"text": {"content": task_data["name"]}}]
            },
            "Status": {
                "status": {"name": "Planning"}
            },
            "Priority": {
                "select": {"name": task_data["priority"]}
            },
            "Description": {
                "rich_text": [{"text": {"content": task_data["description"][:1997] + ("..." if len(task_data["description"]) > 2000 else "")}}]
            },
            "Task Type": {
                "select": {"name": "Review"}
            }
        }
        
        # Link to issue
        if "Issues+Questions" in db_schema:
            properties["Issues+Questions"] = {
                "relation": [{"id": issue_id}]
            }
        elif "Issues+Questions 1" in db_schema:
            properties["Issues+Questions 1"] = {
                "relation": [{"id": issue_id}]
            }
        
        # Create task
        try:
            response = requests.post(
                'https://api.notion.com/v1/pages',
                headers=headers,
                json={
                    "parent": {"database_id": agent_tasks_db_id},
                    "properties": properties
                }
            )
            
            if response.status_code == 200:
                task_id = response.json().get("id")
                created_tasks.append(task_id)
                print(f"✅ Created task: {task_data['name'][:60]}...")
            else:
                print(f"⚠️  Failed to create task '{task_data['name'][:40]}': {response.status_code}")
                print(response.text[:300])
                
        except Exception as e:
            print(f"❌ Error creating task '{task_data['name'][:40]}': {e}")
    
    print(f"\n✅ Created {len(created_tasks)} Agent-Tasks")
    print(f"   Issue ID: {issue_id}")
    print(f"   Tasks linked to issue for review and implementation")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
