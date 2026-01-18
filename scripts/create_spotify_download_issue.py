#!/usr/bin/env python3
"""
Create comprehensive Notion issue for Spotify track download problem.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    from shared_core.notion.issues_questions import create_issue_or_question
    from shared_core.notion.token_manager import get_notion_token
    import requests
    
    # Comprehensive issue description
    issue_description = """CRITICAL ISSUE: Spotify Playlist Tracks Not Being Downloaded

## Problem Summary
Spotify tracks synced to Notion from playlists are NOT being downloaded. The production workflow script excludes Spotify tracks from processing, preventing YouTube download and audio file creation.

## User Feedback (2026-01-09)

User provided two Spotify URLs:
- Playlist: https://open.spotify.com/playlist/6XIc4VjUi7MIJnp7tshFy0 (phonk - 9 tracks)
- Album: https://open.spotify.com/album/5QRFnGnBeMGePBKF2xTz5z (d00mscrvll, Vol. 1 - 9 tracks)

User's explicit feedback:
"WHERE ARE THE DOWNLOAD TRACKS FROM THE PLAYLIST??"
"THE SOUNDCLOUD AND YOUTUBE TRACK MATCHING FUNCTIONALITY NEEDS TO BE REVIEWED AND IMPLEMENTED CORRECTLY"

## Root Causes Identified

### 1. Query Filter Excludes Spotify Tracks
- Location: monolithic-scripts/soundcloud_download_prod_merge-2.py
- Functions: _build_unprocessed_tracks_query() (line 2730) and build_eligibility_filter() (line 8944)
- Problem: Both functions require SoundCloud URL property to be present, completely excluding Spotify tracks
- Impact: Spotify tracks never match the query filter, so they are never processed for download

### 2. DL Property Not Set for New Spotify Tracks
- Location: monolithic-scripts/spotify_integration_module.py
- Function: create_track_page() (line 356)
- Problem: New Spotify tracks created in Notion do not have DL=False set
- Impact: Even if query was fixed, tracks wouldn't match because DL property is missing/not False

### 3. Notion API Query Limitations
- Problem: Notion API doesn't support complex nested AND/OR queries
- Attempted: (SoundCloud URL exists) OR (Spotify ID exists AND SoundCloud URL is empty)
- Result: Query validation errors (400 Bad Request)
- Solution Needed: Simplified query structure that works within Notion API constraints

## Technical Details

### Current Query Structure (BROKEN)
The query requires SoundCloud URL, excluding all Spotify tracks.

### Required Query Structure (FIXED)
Query must include: (SoundCloud URL exists) OR (Spotify ID exists)
Application code filters Spotify tracks during processing.

### Spotify Track Processing Flow (Already Implemented)
The production script HAS the logic to process Spotify tracks (lines 7028-7135):
1. Detection: is_spotify_track = has spotify_id AND no soundcloud_url
2. YouTube Search: search_youtube_for_track(artist, title)
3. Download Pipeline: Routes through full download_track() function
4. Processing: Full audio pipeline (BPM, key, normalization, multi-format, Eagle import)

BUT: Tracks never reach this code because query filter excludes them."""

    # Create the main issue
    issue_id = create_issue_or_question(
        name="CRITICAL: Spotify Playlist Tracks Not Downloading - Query Filter & YouTube Matching Issues",
        type=["Bug", "Script Issue"],
        status="Unreported",
        priority="Critical",
        component=None,  # Component property may not exist in schema
        description=issue_description,
        tags=["spotify", "youtube", "download", "playlist-sync", "query-filter", "critical"],
        skip_if_exists=False
    )
    
    if issue_id:
        print(f"✅ Created issue: {issue_id}")
        
        # Create comprehensive review tasks as child blocks
        token = get_notion_token()
        headers = {
            'Authorization': f'Bearer {token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        
        # Break description into multiple blocks since Notion has limits
        review_tasks_content = """REVIEW TASKS FOR CURSOR MM1 AGENT & CLAUDE CODE AGENT

## Task 1: Review Query Filter Implementation
- Review _build_unprocessed_tracks_query() in soundcloud_download_prod_merge-2.py (line 2730)
- Verify query includes Spotify tracks (Spotify ID property check)
- Test query with Notion API to ensure it returns both SoundCloud and Spotify tracks
- Verify Notion API query structure respects API limitations (no complex nested AND/OR)

## Task 2: Review build_eligibility_filter() Implementation  
- Review build_eligibility_filter() in soundcloud_download_prod_merge-2.py (line 8944)
- Ensure filter includes Spotify tracks in OR condition with SoundCloud tracks
- Verify property name resolution works for both 'DL' and 'Downloaded' property names

## Task 3: Review DL Property Setting for Spotify Tracks
- Review create_track_page() in spotify_integration_module.py (line 356)
- Verify DL=False is set when creating new Spotify tracks
- Test property name detection (DL vs Downloaded) works correctly
- Create script to retroactively set DL=False for existing Spotify tracks (if needed)

## Task 4: Review YouTube Search & Matching Functionality
- Review search_youtube_for_track() in soundcloud_download_prod_merge-2.py (line 7377)
- Test YouTube Data API v3 search functionality
- Test yt-dlp fallback search functionality
- Verify search query format: '{artist} {title} official audio' finds correct videos
- Test with tracks from phonk playlist to verify search accuracy

## Task 5: Review Spotify Track Processing Flow
- Review process_track() Spotify track handling (lines 7028-7135)
- Verify Spotify track detection logic: is_spotify_track = has spotify_id AND no soundcloud_url
- Test full workflow: Detection → YouTube Search → Download → Processing → Eagle Import → Notion Update
- Verify error handling when YouTube search fails (metadata-only processing)

## Task 6: Review Database ID Configuration
- Verify TRACKS_DB_ID is correctly loaded from environment (27ce7361-6c27-80fb-b40e-fefdd47d6640)
- Check for hardcoded or cached database IDs in codebase
- Ensure unified_config.py correctly provides TRACKS_DB_ID

## Task 7: End-to-End Testing & Validation
- Test Case 1: Sync and download phonk playlist (9 tracks)
- Test Case 2: Sync and download d00mscrvll album (9 tracks)
- Verify files created in /Volumes/VIBES/Playlists/phonk/ directory
- Verify Eagle library import successful for all tracks
- Verify Notion database updated with file paths, Eagle File IDs, and metadata
- Verify DL=True set after successful download

## Task 8: Error Handling & Edge Cases
- Test behavior when YouTube search returns no results
- Test behavior when YouTube API quota exceeded
- Test behavior when download fails (network error, invalid URL, etc.)
- Verify proper error logging and Notion status updates

## Task 9: Performance & Optimization Review
- Review batch processing efficiency with Spotify tracks
- Verify rate limiting for YouTube API calls
- Review concurrent processing settings (max 4 tracks simultaneously)

## Task 10: Documentation & Code Review
- Review all code changes for correctness and best practices
- Update inline code comments explaining query filter logic
- Document Notion API query limitations and workarounds
- Create comprehensive test documentation"""
        
        # Split into paragraphs and create blocks
        paragraphs = [p.strip() for p in review_tasks_content.split('\n\n') if p.strip()]
        
        blocks = []
        for para in paragraphs:
            if para.startswith('#'):
                # Heading
                level = len(para) - len(para.lstrip('#'))
                heading_text = para.lstrip('# ').strip()
                block_type = f"heading_{min(level, 3)}"
                blocks.append({
                    "object": "block",
                    "type": block_type,
                    block_type: {
                        "rich_text": [{"type": "text", "text": {"content": heading_text}}]
                    }
                })
            elif para.startswith('- '):
                # Bullet point
                text = para[2:].strip()
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    }
                })
            else:
                # Regular paragraph
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": para}}]
                    }
                })
        
        # Append blocks to the issue page
        response = requests.patch(
            f'https://api.notion.com/v1/blocks/{issue_id}/children',
            headers=headers,
            json={'children': blocks}
        )
        
        if response.status_code == 200:
            print("✅ Added comprehensive review tasks to issue")
            print(f"   Issue page ID: {issue_id}")
            print(f"   View in Notion: https://www.notion.so/{issue_id.replace('-', '')}")
        else:
            print(f"⚠️  Could not add tasks: {response.status_code}")
            print(response.text[:500])
            
    else:
        print("❌ Failed to create issue")
        
except Exception as e:
    print(f"❌ Error creating issue: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
