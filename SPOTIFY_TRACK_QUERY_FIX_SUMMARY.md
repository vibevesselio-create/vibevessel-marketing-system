# Spotify Track Query Filter Fix - Issue Resolution Summary

**Date**: 2026-01-09  
**Issue ID**: 2e3e7361-6c27-818d-9a9b-c5508f52d916  
**Issue**: CRITICAL: Spotify Playlist Tracks Not Downloading - Query Filter & YouTube Matching Issues  
**Status**: Fixes Implemented - Requires Testing & Validation

## Problem Summary

Spotify tracks synced to Notion from playlists were NOT being downloaded because the production workflow script excluded Spotify tracks from processing. The query filters required SoundCloud URL to be present, completely excluding Spotify-only tracks.

## Root Causes Identified

1. **Query Filter Excludes Spotify Tracks** - Multiple functions required SoundCloud URL, excluding Spotify tracks
2. **DL Property Not Set** - Already fixed in `create_track_page()` (sets DL=False)
3. **Notion API Query Limitations** - Complex nested AND/OR queries don't work, requiring simplified structure

## Fixes Implemented

### 1. Fixed `find_next_track()` Function (Line 2634)
**Before**: Required SoundCloud URL to be present  
**After**: Includes tracks with SoundCloud URL OR Spotify ID (or both)

```python
# Changed from requiring SoundCloud URL only
# To including: (SoundCloud URL exists) OR (Spotify ID exists)
```

### 2. Fixed `find_tracks_for_processing_batch()` Function (Line 2871)
**Before**: Required SoundCloud URL to be present  
**After**: Includes tracks with SoundCloud URL OR Spotify ID (or both)

### 3. Fixed `find_tracks_for_reprocessing()` Function (Line 3131)
**Before**: Required SoundCloud URL to be present  
**After**: Includes tracks with SoundCloud URL OR Spotify ID (or both)

### 4. Verified `create_track_page()` Function (Line 356)
**Status**: Already correct - Sets DL=False for new Spotify tracks

### 5. Verified Other Query Functions
- `_build_unprocessed_tracks_query()` (Line 2730) - Already includes Spotify tracks ✓
- `build_eligibility_filter()` (Line 8969) - Already includes Spotify tracks ✓

## Technical Details

### Query Structure Changes

All fixed functions now use an OR condition:
```python
source_or = []
sc_url_filter = _filter_is_not_empty("SoundCloud URL")
if sc_url_filter:
    source_or.append(sc_url_filter)
spotify_id_filter = _filter_is_not_empty("Spotify ID")
if spotify_id_filter:
    source_or.append(spotify_id_filter)

if source_or:
    if len(source_or) == 1:
        dynamic_filters.append(source_or[0])
    else:
        dynamic_filters.append({"or": source_or})
```

This ensures that:
- Tracks with SoundCloud URL are included
- Tracks with Spotify ID (but no SoundCloud URL) are included
- Tracks with both are included
- The query works within Notion API constraints

## Files Modified

1. `monolithic-scripts/soundcloud_download_prod_merge-2.py`
   - `find_next_track()` - Fixed query filter
   - `find_tracks_for_processing_batch()` - Fixed query filter
   - `find_tracks_for_reprocessing()` - Fixed query filter

## Testing Required

1. **Verify Query Works**: Test that Spotify tracks are now included in queries
2. **Verify Processing**: Test that Spotify tracks are processed for YouTube download
3. **Verify DL Property**: Confirm new Spotify tracks have DL=False set
4. **End-to-End Test**: Sync a Spotify playlist and verify tracks are downloaded

## Next Steps

1. **Testing**: Run the production workflow script with Spotify tracks
2. **Validation**: Verify Spotify tracks appear in query results
3. **Integration Testing**: Test full workflow from playlist sync to download
4. **Issue Update**: Update Notion issue with test results
5. **Documentation**: Update workflow documentation if needed

## Handoff Instructions

The recipient agent should:
1. Test the fixes by running the production workflow script
2. Verify Spotify tracks are included in queries
3. Test end-to-end workflow with a Spotify playlist
4. Update the issue status in Notion based on test results
5. Create follow-up tasks if additional fixes are needed

## Related Files

- Issue: `2e3e7361-6c27-818d-9a9b-c5508f52d916`
- Production Script: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
- Spotify Integration: `monolithic-scripts/spotify_integration_module.py`
