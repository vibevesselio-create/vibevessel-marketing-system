# Reprocessing Filter and Deduplication Fix Summary

## Date: 2025-01-27
## File: soundcloud_download_prod_merge-2.py

## Issues Fixed

### Issue 1: Reprocessing Filter Too Loose
**Problem**: The `find_tracks_for_reprocessing()` function was finding way too many tracks that didn't need reprocessing. It was matching any track with:
- DL=False AND
- (File paths OR Fingerprint OR Eagle File ID)

This caught virtually every track that had been partially processed, even if files existed and were complete.

**Solution**:
1. **Disabled by default**: Added environment variable check `ENABLE_REPROCESSING_FILTER` (default: disabled)
2. **Stricter criteria**: Removed Fingerprint and Eagle File ID from the OR filter - these don't indicate need for reprocessing
3. **File existence check**: Added verification that files actually DON'T exist on disk before marking for reprocessing
4. **Reduced limit**: Changed from 100 items to 20 items max to prevent overwhelming the system

**Code Location**: Lines 2852-2931

**To enable (if needed)**: Set environment variable `ENABLE_REPROCESSING_FILTER=1`

---

### Issue 2: Deduplication Logic Not Working
**Problem**: The `should_reprocess_page()` function wasn't checking if tracks were already in the Eagle library before allowing re-download. This caused:
- Tracks with existing files and complete metadata being re-downloaded
- No check of Eagle library metadata completeness
- Wasted processing time and disk space

**Solution**:
1. **Eagle library check**: Added Eagle metadata completeness verification before allowing reprocessing
2. **Existing file detection**: Enhanced file existence checking for all file path properties
3. **Metadata validation**: Checks for essential tags (BPM, Key, Genre, Processed) in Eagle before skipping
4. **Metadata-only updates**: If files exist but metadata is incomplete, skip re-download (metadata update only)
5. **Smarter logic**: Only allows reprocessing if files truly don't exist on disk

**Code Location**: Lines 2310-2412

**Metadata completeness criteria**:
- BPM tag present
- Key tag present  
- Genre tag present
- Processed tag present

---

## Behavior Changes

### Before Fix:
- Reprocessing filter would find 100+ tracks automatically
- Would re-download tracks that already existed in Eagle library
- No check for metadata completeness
- Wasted resources processing already-complete tracks

### After Fix:
- Reprocessing filter disabled by default (returns empty list)
- When enabled, maximum 20 tracks, only those with broken file paths
- Checks Eagle library for complete metadata before allowing re-download
- Skips tracks that have existing files with proper metadata
- Only reprocesses tracks where files are truly missing

---

## Testing Recommendations

1. **Test normal workflow** (should work exactly as before):
   ```bash
   python3 soundcloud_download_prod_merge-2.py --mode single
   python3 soundcloud_download_prod_merge-2.py --mode batch --limit 10
   ```

2. **Verify reprocessing is disabled** (should see message):
   ```bash
   python3 soundcloud_download_prod_merge-2.py --mode reprocess
   # Expected: "ℹ️ Reprocessing filter disabled"
   ```

3. **Test reprocessing if needed** (only for broken tracks):
   ```bash
   ENABLE_REPROCESSING_FILTER=1 python3 soundcloud_download_prod_merge-2.py --mode reprocess
   # Should only find tracks with missing files
   ```

4. **Test Eagle deduplication**:
   - Run script on track that's already in Eagle with complete metadata
   - Should skip with message: "Skipping page {id} — files exist with complete metadata in Eagle"

---

## Configuration

### New Environment Variables:
- `ENABLE_REPROCESSING_FILTER`: Set to `1` to enable reprocessing filter (default: `0`/disabled)

### Existing Variables (unchanged):
- `SKIP_REPROCESS_CHECK`: Set to `false` to run reprocessing check (default varies by mode)
- All other environment variables remain the same

---

## Rollback Plan

If issues occur, revert the changes:
```bash
git diff HEAD soundcloud_download_prod_merge-2.py
git checkout soundcloud_download_prod_merge-2.py
```

Or set `ENABLE_REPROCESSING_FILTER=0` (which is already the default).

---

## Files Modified
- `/Users/brianhellemn/Projects/github-production/monolithic-scripts/soundcloud_download_prod_merge-2.py`

## Functions Modified
1. `find_tracks_for_reprocessing()` (lines 2852-2931)
2. `should_reprocess_page()` (lines 2310-2412)

## Lines Changed
- Total: ~150 lines modified
- Added: ~80 lines
- Removed/Modified: ~70 lines

