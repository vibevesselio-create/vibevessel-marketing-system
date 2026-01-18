# Spotify Track Download Issue - Notion Issue & Review Tasks Created

**Date**: 2026-01-09  
**Status**: ✅ ISSUE CREATED, REVIEW TASKS ASSIGNED

## Issue Created

**Issue ID**: `2e3e7361-6c27-818d-9a9b-c5508f52d916`  
**View in Notion**: https://www.notion.so/2e3e73616c27818d9a9bc5508f52d916

**Title**: CRITICAL: Spotify Playlist Tracks Not Downloading - Query Filter & YouTube Matching Issues

**Properties**:
- **Status**: Unreported
- **Priority**: Critical
- **Type**: Bug, Script Issue
- **Tags**: spotify, youtube, download, playlist-sync, query-filter, critical

## Problem Summary

Spotify tracks synced to Notion from playlists are NOT being downloaded. The production workflow script excludes Spotify tracks from processing, preventing YouTube download and audio file creation.

## User Feedback Included

- **Playlist URL**: https://open.spotify.com/playlist/6XIc4VjUi7MIJnp7tshFy0 (phonk - 9 tracks)
- **Album URL**: https://open.spotify.com/album/5QRFnGnBeMGePBKF2xTz5z (d00mscrvll, Vol. 1 - 9 tracks)

**User's Explicit Feedback**:
- "WHERE ARE THE DOWNLOAD TRACKS FROM THE PLAYLIST??"
- "THE SOUNDCLOUD AND YOUTUBE TRACK MATCHING FUNCTIONALITY NEEDS TO BE REVIEWED AND IMPLEMENTED CORRECTLY"

## Root Causes Documented

1. **Query Filter Excludes Spotify Tracks**: Both `_build_unprocessed_tracks_query()` and `build_eligibility_filter()` require SoundCloud URL, excluding Spotify tracks
2. **DL Property Not Set**: New Spotify tracks don't have `DL=False` set
3. **Notion API Query Limitations**: Complex nested AND/OR queries not supported

## Review Tasks Created

✅ **10 Comprehensive Review Tasks** created in Agent-Tasks database, linked to the issue:

### Task 1: Review Query Filter Implementation - Spotify Track Inclusion
- **Assignee**: Cursor MM1 Agent
- **Priority**: Critical
- **Focus**: `_build_unprocessed_tracks_query()` function (line 2730)

### Task 2: Review build_eligibility_filter() - Spotify Track Support
- **Assignee**: Cursor MM1 Agent
- **Priority**: High
- **Focus**: `build_eligibility_filter()` function (line 8944)

### Task 3: Review DL Property Setting for Spotify Tracks
- **Assignee**: Cursor MM1 Agent
- **Priority**: High
- **Focus**: `create_track_page()` function (line 356)

### Task 4: Review YouTube Search & Matching Functionality
- **Assignee**: Claude Code Agent
- **Priority**: High
- **Focus**: `search_youtube_for_track()` function (line 7377)

### Task 5: Review Spotify Track Processing Flow - End-to-End
- **Assignee**: Claude Code Agent
- **Priority**: Critical
- **Focus**: Complete workflow (lines 7028-7135, 7750-8300)

### Task 6: Review Database ID Configuration & Environment Setup
- **Assignee**: Cursor MM1 Agent
- **Priority**: Medium
- **Focus**: Environment variable and database ID configuration

### Task 7: End-to-End Testing - Spotify Playlist Download Workflow
- **Assignee**: Claude Code Agent
- **Priority**: Critical
- **Focus**: Complete testing with actual playlist tracks

### Task 8: Error Handling & Edge Cases Review
- **Assignee**: Claude Code Agent
- **Priority**: Medium
- **Focus**: Error scenarios and edge case handling

### Task 9: Performance & Optimization Review
- **Assignee**: Cursor MM1 Agent
- **Priority**: Low
- **Focus**: Batch processing efficiency and optimization

### Task 10: Code Review & Documentation
- **Assignee**: Claude Code Agent
- **Priority**: Medium
- **Focus**: Code quality, comments, and documentation updates

## Technical Details in Issue

The issue includes comprehensive technical documentation:
- Current query structure (broken)
- Required query structure (fixed)
- Spotify track processing flow (already implemented)
- YouTube search implementation details
- Files requiring review
- Test cases needed
- Known limitations and edge cases

## Next Steps

1. ✅ Issue created in Notion
2. ✅ Review tasks created and assigned
3. ⏭️ **Awaiting agent review**: Cursor MM1 Agent and Claude Code Agent should review assigned tasks
4. ⏭️ **Implementation**: Fixes should be implemented based on review findings
5. ⏭️ **Testing**: End-to-end testing with actual playlist tracks
6. ⏭️ **Verification**: Confirm tracks download successfully

## Related Files

- Issue Documentation: See Notion issue page
- Implementation Details: `SPOTIFY_YOUTUBE_MATCHING_IMPLEMENTATION_COMPLETE.md`
- Sync Results: `SPOTIFY_SYNC_RESULTS_20260109.md`
- Test Script: `scripts/test_spotify_track_query.py`
- Sync Script: `scripts/sync_spotify_playlist.py`

---

**Issue Status**: Open (Unreported)  
**Review Tasks**: 10 tasks created, ready for agent review  
**Action Required**: Agents should review assigned tasks and implement fixes
