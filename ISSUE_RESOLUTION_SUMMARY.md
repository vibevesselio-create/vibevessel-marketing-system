# Issue Resolution Summary

## Issue: SoundCloud Go+ preview tracks need YouTube fallback automation

**Issue ID:** 2d2e7361-6c27-81d7-b05b-c2451bee4897  
**Issue URL:** https://www.notion.so/SoundCloud-Go-preview-tracks-need-YouTube-fallback-automation-2d2e73616c2781d7b05bc2451bee4897  
**Status:** Solution In Progress

## Problem
90s Hip Hop playlist: 47/101 tracks are 30-second previews (SoundCloud Go+). Script has preview detection but needs manual YouTube URL. Consider adding automatic YouTube search for preview tracks.

## Solution Implemented

### Changes Made
1. **Added Preview Detection Logic** (lines ~7117-7213 in `soundcloud_download_prod_merge-2.py`)
   - Detects SoundCloud Go+ preview tracks by checking duration (25-35 seconds)
   - Logs warning when preview is detected

2. **Automatic YouTube Search** 
   - When a preview is detected, automatically searches YouTube for the full track
   - Uses existing `search_youtube_for_track()` function with artist and title
   - Supports both YouTube Data API v3 and yt-dlp search fallback

3. **Notion Integration**
   - Automatically updates Notion with YouTube URL when found
   - Sets download source to "YouTube (Auto-Preview)"
   - Saves YouTube URL to "YouTube URL" property in Music Tracks database

4. **Automatic Download**
   - When YouTube URL is found, automatically downloads from YouTube instead of SoundCloud preview
   - Uses existing `try_youtube_download()` function
   - Falls back to SoundCloud preview if YouTube download fails

### Implementation Details

The implementation adds preview detection right after yt-dlp metadata extraction:

```python
# Check if this is a SoundCloud Go+ preview track (typically ~30 seconds)
duration = info.get('duration')
if duration and 25 <= duration <= 35:
    # Detect preview and search YouTube automatically
    # Update Notion and download from YouTube
```

### Benefits
- **Automated**: No manual YouTube URL entry required
- **Seamless**: Automatically switches to YouTube when preview detected
- **Fallback**: Continues with SoundCloud preview if YouTube search/download fails
- **Notion Sync**: Automatically updates database with YouTube URL for future reference

## Testing Required
- Test with actual SoundCloud Go+ preview tracks
- Verify YouTube search finds correct tracks
- Verify Notion updates correctly
- Verify download from YouTube works correctly
- Test fallback behavior when YouTube search/download fails

## Next Steps
1. Test the implementation with real preview tracks
2. Monitor logs for preview detection and YouTube search results
3. Verify Notion updates are working correctly
4. Update issue status to "Resolved" after successful testing

































