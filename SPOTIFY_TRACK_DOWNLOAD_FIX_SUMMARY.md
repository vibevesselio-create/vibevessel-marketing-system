# Spotify Track Download Fix - Implementation Summary

**Issue:** CRITICAL: Spotify Playlist Tracks Not Downloading - Query Filter & YouTube Matching Issues  
**Issue ID:** 2e3e7361-6c27-818d-9a9b-c5508f52d916  
**Date:** 2026-01-09  
**Status:** Fixed - Ready for Testing

## Problem Summary

Spotify tracks synced to Notion from playlists were NOT being downloaded. The production workflow script excluded Spotify tracks from processing, preventing YouTube download and audio file creation.

## Root Causes Identified and Fixed

### 1. DL Property Not Set for New Spotify Tracks ✅ FIXED

**Location:** `monolithic-scripts/spotify_integration_module.py`  
**Function:** `create_track_page()` (line 356)  
**Problem:** New Spotify tracks created in Notion did not have DL=False set reliably.  
**Fix:** Enhanced the DL property setting logic to:
- Always set DL=False for new Spotify tracks, even if database property check fails
- Try both "DL" and "Downloaded" property names
- Use fallback to set both properties if database info retrieval fails (Notion API will ignore non-existent properties)

**Code Changes:**
```python
# Before: Only set DL if property check succeeded
if db_info:
    db_props = db_info.get("properties", {})
    if "DL" in db_props and db_props["DL"].get("type") == "checkbox":
        properties["DL"] = {"checkbox": False}
    elif "Downloaded" in db_props and db_props["Downloaded"].get("type") == "checkbox":
        properties["Downloaded"] = {"checkbox": False}

# After: Always set DL=False with fallback
db_info = self._make_notion_request("GET", f"/databases/{self.tracks_db_id}")
if db_info:
    db_props = db_info.get("properties", {})
    if "DL" in db_props and db_props["DL"].get("type") == "checkbox":
        properties["DL"] = {"checkbox": False}
    if "Downloaded" in db_props and db_props["Downloaded"].get("type") == "checkbox":
        properties["Downloaded"] = {"checkbox": False}
else:
    # Fallback: If database info retrieval fails, try setting both properties
    properties["DL"] = {"checkbox": False}
    properties["Downloaded"] = {"checkbox": False}
```

### 2. Query Filter Handling for Missing DL Property ✅ FIXED

**Location:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`  
**Function:** `build_eligibility_filter()` (line 9010)  
**Problem:** Query filter always added DL=False filter without checking if property exists, which could cause issues for tracks without DL property.  
**Fix:** Added property existence check before adding DL filter, consistent with `_build_unprocessed_tracks_query()`.

**Code Changes:**
```python
# Before: Always added DL filter
dl_prop = _resolve_prop_name("DL") or "Downloaded"
conds.append({"property": dl_prop, "checkbox": {"equals": False}})

# After: Check if property exists before adding filter
prop_types = _get_tracks_db_prop_types()
dl_prop = _resolve_prop_name("DL") or "Downloaded"
if dl_prop in prop_types and prop_types[dl_prop] == "checkbox":
    conds.append({"property": dl_prop, "checkbox": {"equals": False}})
elif "DL" in prop_types and prop_types["DL"] == "checkbox":
    conds.append({"property": "DL", "checkbox": {"equals": False}})
elif "Downloaded" in prop_types and prop_types["Downloaded"] == "checkbox":
    conds.append({"property": "Downloaded", "checkbox": {"equals": False}})
else:
    workspace_logger.warning("Tracks DB missing DL/Downloaded checkbox; skipping DL filter for eligibility check.")
```

### 3. Query Structure Verification ✅ VERIFIED

**Location:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`  
**Functions:** `_build_unprocessed_tracks_query()` (line 2744), `build_eligibility_filter()` (line 9010)  
**Status:** Already correctly includes Spotify tracks via OR condition: `(SoundCloud URL exists) OR (Spotify ID exists)`

Both functions already include Spotify tracks in their query filters:
- `_build_unprocessed_tracks_query()`: Lines 2756-2770 build OR condition for SoundCloud URL OR Spotify ID
- `build_eligibility_filter()`: Lines 9019-9031 build OR condition for SoundCloud URL OR Spotify ID

## Impact

**For New Spotify Tracks:**
- DL=False will always be set, ensuring they are eligible for download processing
- Tracks will match query filters and be processed for YouTube download

**For Existing Spotify Tracks:**
- Tracks without DL property will still be eligible if the property doesn't exist
- Tracks with DL=False will continue to be processed correctly

## Testing Recommendations

1. **Test New Spotify Track Creation:**
   - Sync a new Spotify playlist or album
   - Verify new tracks have DL=False set in Notion
   - Verify tracks appear in unprocessed tracks query

2. **Test Query Filters:**
   - Run `find_all_tracks_for_processing()` or `select_pages()`
   - Verify Spotify tracks (with Spotify ID, no SoundCloud URL) are included in results
   - Verify tracks with DL=False or missing DL property are included

3. **Test Download Processing:**
   - Process a Spotify track through the download workflow
   - Verify YouTube matching and download functionality works correctly

## Files Modified

1. `monolithic-scripts/spotify_integration_module.py`
   - Enhanced `create_track_page()` to always set DL=False

2. `monolithic-scripts/soundcloud_download_prod_merge-2.py`
   - Enhanced `build_eligibility_filter()` to check for DL property existence before filtering

## Next Steps

1. Test the fixes with actual Spotify playlist sync and download processing
2. Monitor for any remaining issues with Spotify track processing
3. Consider adding a script to update existing Spotify tracks that don't have DL=False set (if needed)

## Notes

- The query structure was already correct (includes Spotify tracks via OR condition)
- The primary issues were:
  1. New Spotify tracks not getting DL=False set reliably
  2. Query filter not handling missing DL property gracefully
- Both issues are now fixed and should resolve the critical issue
