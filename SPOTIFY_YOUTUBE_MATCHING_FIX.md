# Spotify/YouTube Track Matching Implementation Fix

**Date**: 2026-01-09  
**Issue**: Spotify tracks synced to Notion were not being downloaded because query filters excluded them.

## Problem Identified

1. **Query Filter Issue**: Both `_build_unprocessed_tracks_query()` and `build_eligibility_filter()` required SoundCloud URL to be present, excluding Spotify tracks that need YouTube download.

2. **DL Property Not Set**: Spotify tracks created via `create_track_page()` did not set `DL=False`, preventing them from matching the unprocessed filter.

## Fixes Implemented

### 1. Fixed Query Filters to Include Spotify Tracks

**File**: `monolithic-scripts/soundcloud_download_prod_merge-2.py`

#### `_build_unprocessed_tracks_query()` (line 2730)
- **Before**: Required `SoundCloud URL` to be NOT empty
- **After**: Includes tracks with:
  - SoundCloud URL exists, OR
  - Spotify ID exists AND SoundCloud URL is empty (Spotify tracks needing YouTube download)

#### `build_eligibility_filter()` (line 8944)
- **Before**: Required `SoundCloud URL` to be NOT empty
- **After**: Includes both SoundCloud and Spotify tracks using OR logic:
  - SoundCloud tracks: Has SoundCloud URL
  - Spotify tracks: Has Spotify ID AND no SoundCloud URL

### 2. Set DL=False for New Spotify Tracks

**File**: `monolithic-scripts/spotify_integration_module.py`

**Function**: `create_track_page()` (line 356)
- Added logic to set `DL=False` checkbox when creating Spotify tracks
- Checks database schema to use correct property name (`DL` or `Downloaded`)

### 3. Existing Spotify Track Processing Logic (Already Working)

The production script already has complete logic for processing Spotify tracks:

1. **Detection** (line 7029): Detects Spotify tracks (`has Spotify ID` AND `no SoundCloud URL`)
2. **YouTube Search** (line 7057-7058): Searches YouTube using `search_youtube_for_track(artist, title)`
3. **Download Pipeline** (line 7077-7082): Routes through full `download_track()` function with YouTube URL
4. **Audio Processing**: Full pipeline including normalization, multi-format creation, Eagle import

## YouTube Search Implementation

### Function: `search_youtube_for_track(artist, title)` (line 7377)

**Primary Method**: YouTube Data API v3 (if `YOUTUBE_API_KEY` configured)
- Searches with query: `"{artist} {title} official audio"`
- Filters to Music category (videoCategoryId='10')
- Returns first matching video URL

**Fallback Method**: yt-dlp search (no API key required)
- Uses: `ytsearch1:{artist} {title} official audio`
- Less reliable but works without API key

## Testing & Verification

### Completed:

1. ✅ **Set DL=False for existing synced tracks**: Updated 50 Spotify tracks to have `Downloaded=False`

### Next Steps to Test:

1. **Verify TRACKS_DB_ID is correct**:
   - Script is using wrong database ID in some places
   - Ensure `TRACKS_DB_ID=27ce7361-6c27-80fb-b40e-fefdd47d6640` is set in environment
   
2. **Test query directly**:
   ```python
   # Test the fixed query to see if it finds Spotify tracks
   ```

3. **Run batch processing**:
   ```bash
   export TRACKS_DB_ID=27ce7361-6c27-80fb-b40e-fefdd47d6640
   python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode batch --limit 5
   ```

4. **Verify tracks are found and processed**:
   - Query should now include Spotify tracks
   - YouTube search should find videos  
   - Download pipeline should execute
   - Files should be created in `/Volumes/VIBES/Playlists/phonk/`

### Known Issues:

1. **Database ID Mismatch**: Script may be using cached or wrong database ID (`23de7361-6c27-80a9-a867-f78317b32d22` instead of `27ce7361-6c27-80fb-b40e-fefdd47d6640`)
   - Solution: Verify TRACKS_DB_ID environment variable is set correctly
   - Check unified_config.py or .env file

### Expected Behavior:

1. Query finds Spotify tracks (those with Spotify ID, no SoundCloud URL, DL=False, no file paths)
2. For each Spotify track:
   - Searches YouTube using artist and title
   - Downloads audio from YouTube
   - Processes through full pipeline (BPM detection, normalization, formats)
   - Imports to Eagle library
   - Updates Notion with file paths and Eagle File ID
   - Sets DL=True when complete

## Files Modified

1. `monolithic-scripts/soundcloud_download_prod_merge-2.py`
   - `_build_unprocessed_tracks_query()` - Fixed to include Spotify tracks
   - `build_eligibility_filter()` - Fixed to include Spotify tracks

2. `monolithic-scripts/spotify_integration_module.py`
   - `create_track_page()` - Added DL=False for new Spotify tracks

## Additional Recommendations

1. **Update Existing Synced Tracks**: Create a script to set DL=False for tracks already synced
2. **Monitor YouTube Search Success Rate**: Track how often YouTube search finds matches
3. **Consider Alternative Sources**: If YouTube search fails, could try SoundCloud search as fallback
4. **Error Handling**: Ensure proper error messages when YouTube search fails

---

**Status**: ✅ Query filters fixed, DL property setting added  
**Next**: Test with existing synced tracks and verify download workflow
