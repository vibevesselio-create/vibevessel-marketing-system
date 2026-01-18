# Music Prompts Audit & Optimization Report

**Date:** 2026-01-08  
**Auditor:** Cursor-MM1 Agent  
**Status:** 🔴 **CRITICAL ISSUES IDENTIFIED - UPDATES REQUIRED**

---

## Executive Summary

Comprehensive audit of both Music Track and Playlist Synchronization prompts identified **8 critical issues** and **12 optimization opportunities** that prevent agents from executing tangible, value-adding work and advancing automation. Issues range from incorrect function references to missing verification steps and inadequate error handling guidance.

**Overall Assessment:** ⚠️ **PROMPTS NEED UPDATES** - Multiple misalignments with actual codebase implementation.

---

## Critical Issues Identified

### Issue 1: Incorrect Spotify API Function References (CRITICAL)

**Location:** Both prompts  
**Lines:** Track Prompt Line 193-197, Playlist Prompt Line 213-217

**Problem:**
```python
# Prompt says:
from spotify_integration_module import get_spotify_client
sp = get_spotify_client()
results = sp.current_user_saved_tracks(limit=5)  # ❌ Doesn't exist
results = sp.current_user_playlists(limit=3)     # ❌ Doesn't exist
```

**Reality:**
- `get_spotify_client()` function **DOES NOT EXIST**
- `SpotifyAPI` class has `get_user_playlists()` method (not `current_user_playlists()`)
- `SpotifyAPI` class has **NO** `current_user_saved_tracks()` method
- Must use `SpotifyAPI` and `SpotifyOAuthManager` classes

**Impact:** 🔴 **CRITICAL** - Fallback chain will fail, agent will waste time troubleshooting

**Fix Required:**
```python
# Correct implementation:
from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
oauth = SpotifyOAuthManager()
sp = SpotifyAPI(oauth)
results = sp.get_user_playlists(limit=3)  # ✅ Correct method name

# For saved tracks - NOT AVAILABLE in current implementation
# Must use alternative approach or document as limitation
```

---

### Issue 2: Missing File Creation Verification (CRITICAL)

**Location:** Track Prompt  
**Lines:** Post-Execution Phase 2.1

**Problem:**
Prompt says "Verify files created in correct formats" but doesn't specify:
- **WHERE** to verify (actual file paths)
- **WHAT** to check (file existence, size, location)
- **HOW** to verify (commands to run)

**Impact:** 🔴 **CRITICAL** - Agent won't catch misalignments like Spotify track file creation issue

**Fix Required:**
Add explicit verification steps:
```markdown
2.1 - Verify Production Workflow Execution

**File Creation Verification:**
- Check M4A file exists: `ls -lh "{OUT_DIR}/{playlist_name}/{track_name}.m4a"`
- Check AIFF file exists: `ls -lh "{OUT_DIR}/{playlist_name}/{track_name}.aiff"`
- Check WAV backup exists: `ls -lh "{WAV_BACKUP_DIR}/{track_name}.wav"`
- Check M4A backup exists: `ls -lh "{BACKUP_DIR}/{track_name}.m4a"`
- Verify file sizes are reasonable (> 1MB for audio files)
- Verify Notion properties contain file paths:
  * M4A File Path property
  * AIFF File Path property
  * WAV File Path property
```

---

### Issue 3: Missing Spotify Track YouTube Search Documentation (HIGH)

**Location:** Track Prompt  
**Lines:** Phase 0.1, Phase 1

**Problem:**
Prompt doesn't mention that Spotify tracks now search YouTube for alternative sources. This is critical functionality that was just implemented.

**Impact:** 🟡 **HIGH** - Agent won't understand why Spotify tracks create files (via YouTube)

**Fix Required:**
Add to Phase 0.1:
```markdown
**Spotify Track Processing:**
- Spotify tracks automatically search YouTube for alternative audio source
- If YouTube URL found, track is downloaded and processed through full pipeline
- If no YouTube source found, falls back to metadata-only processing
- YouTube URL is saved to Notion for future reference
```

---

### Issue 4: Fallback Chain Timeout/Retry Logic Missing (HIGH)

**Location:** Track Prompt  
**Lines:** Phase 0.2 (Priority 2, Priority 3)

**Problem:**
No timeout or retry limits specified. Agent spent 90+ seconds troubleshooting SoundCloud likes fetch.

**Impact:** 🟡 **HIGH** - Agent wastes time on non-blocking issues

**Fix Required:**
Add timeout/retry guidance:
```markdown
**Fallback Chain Execution Rules:**
- Maximum 2 attempts per priority level
- Timeout after 30 seconds for each fetch operation
- If timeout or 2 failures: Move to next priority immediately
- Document failures but don't block workflow
- After 3 failed priorities: Use production script --mode single as final fallback
```

---

### Issue 5: Incorrect Function Reference in Playlist Prompt (CRITICAL)

**Location:** Playlist Prompt  
**Lines:** 213-217

**Problem:**
```python
from spotify_integration_module import get_spotify_client  # ❌ Doesn't exist
sp = get_spotify_client()
results = sp.current_user_playlists(limit=3)  # ❌ Wrong method name
```

**Reality:**
- Correct method is `get_user_playlists(limit=3, offset=0)`
- Must use `SpotifyAPI` and `SpotifyOAuthManager`

**Impact:** 🔴 **CRITICAL** - Playlist fallback chain will fail

---

### Issue 6: Missing Playlist Script Verification (MEDIUM)

**Location:** Playlist Prompt  
**Lines:** Phase 0.1

**Problem:**
Prompt references `sync_soundcloud_playlist.py` but doesn't verify it exists or check its capabilities.

**Impact:** 🟡 **MEDIUM** - Agent may fail if script doesn't exist or has issues

**Fix Required:**
Add verification step:
```markdown
**Script Verification:**
- Verify sync_soundcloud_playlist.py exists and is executable
- Check script accepts required parameters (playlist_url, --playlist-name, --max-tracks)
- Verify script integrates with production workflow script
```

---

### Issue 7: Missing Batch Processing Error Handling Guidance (MEDIUM)

**Location:** Playlist Prompt  
**Lines:** Phase 1.3

**Problem:**
Prompt mentions batch processing but doesn't specify:
- How to handle partial failures
- When to retry individual tracks
- How to report batch processing results

**Impact:** 🟡 **MEDIUM** - Agent may not handle batch failures correctly

**Fix Required:**
Add batch processing guidance:
```markdown
**Batch Processing Error Handling:**
- If individual track fails: Log error, mark Downloaded=false, continue with next track
- If >50% of batch fails: Stop batch, create Agent-Task for investigation
- Report batch results: X successful, Y failed, Z skipped
- Failed tracks should be retried individually in next execution
```

---

### Issue 8: Missing File Path Verification for Playlist Tracks (HIGH)

**Location:** Playlist Prompt  
**Lines:** Post-Execution Phase 2.1

**Problem:**
Prompt verifies playlist sync but doesn't verify individual track file creation.

**Impact:** 🟡 **HIGH** - May miss track-level file creation issues

**Fix Required:**
Add track-level verification:
```markdown
**Track-Level File Verification:**
- Sample check: Verify files created for at least 3 tracks in playlist
- Check Notion tracks have file paths populated
- Verify Eagle import succeeded for all processed tracks
- Report any tracks missing files or Eagle IDs
```

---

## Optimization Opportunities

### Optimization 1: Add Explicit Timeout Instructions

**Current:** No timeout guidance  
**Recommended:** Add timeout rules for all fallback operations

**Benefit:** Prevents agent from spending excessive time on non-blocking issues

---

### Optimization 2: Add File Path Verification Commands

**Current:** Says "verify files created" but no commands  
**Recommended:** Provide exact commands to verify file existence and paths

**Benefit:** Ensures agent catches file creation misalignments immediately

---

### Optimization 3: Document Spotify Track YouTube Search Flow

**Current:** Doesn't mention YouTube search for Spotify tracks  
**Recommended:** Explicitly document the YouTube search → download flow

**Benefit:** Agent understands why Spotify tracks create files

---

### Optimization 4: Add Production Script Mode Clarification

**Current:** Says "--mode url" for all URLs  
**Recommended:** Clarify when to use --mode single vs --mode batch vs --mode url

**Benefit:** Agent uses correct mode for each scenario

---

### Optimization 5: Add Environment Variable Verification

**Current:** Lists env vars but doesn't verify they're set  
**Recommended:** Add verification step before execution

**Benefit:** Catches configuration issues early

---

### Optimization 6: Add Notion Property Verification

**Current:** Says "verify Notion updated" but doesn't specify properties  
**Recommended:** List exact properties to verify (M4A File Path, AIFF File Path, etc.)

**Benefit:** Ensures all required data is stored

---

### Optimization 7: Add Eagle Import Verification

**Current:** Says "verify Eagle import" but no verification method  
**Recommended:** Provide commands to verify Eagle item exists

**Benefit:** Catches Eagle import failures

---

### Optimization 8: Add Automation Gap Documentation Template

**Current:** Says "identify automation gaps" but no structure  
**Recommended:** Provide template for documenting gaps

**Benefit:** Consistent, actionable automation task creation

---

### Optimization 9: Add Error Recovery Guidance

**Current:** Lists error types but no recovery steps  
**Recommended:** Add recovery steps for each error type

**Benefit:** Agent can self-recover from common issues

---

### Optimization 10: Add Performance Metrics Collection

**Current:** No metrics collection guidance  
**Recommended:** Add instructions to collect and document performance metrics

**Benefit:** Enables optimization and monitoring

---

### Optimization 11: Add Duplicate Detection Verification

**Current:** Says "no duplicates created" but no verification method  
**Recommended:** Add commands to verify no duplicates in Notion/Eagle

**Benefit:** Ensures deduplication is working correctly

---

### Optimization 12: Add Playlist-Track Relationship Verification

**Location:** Playlist Prompt  
**Current:** Doesn't verify tracks are linked to playlist  
**Recommended:** Add verification that playlist relations are created

**Benefit:** Ensures playlist organization is maintained

---

## Recommended Prompt Updates

### Update 1: Fix Spotify API References

**Track Prompt - Priority 3 (Line 193-215):**
```python
# BEFORE:
from spotify_integration_module import get_spotify_client
sp = get_spotify_client()
results = sp.current_user_saved_tracks(limit=5)

# AFTER:
# NOTE: Spotify saved tracks API not available in current implementation
# Fallback: Use production script --mode single to process newest eligible track
# OR: Skip this priority and proceed to production script execution

# Alternative if Spotify API available:
from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
try:
    oauth = SpotifyOAuthManager()
    sp = SpotifyAPI(oauth)
    # Note: get_user_playlists() available, but saved tracks requires different approach
    # For now, skip to production script --mode single
except Exception as e:
    workspace_logger.warning(f"Spotify API unavailable: {e}")
    # Proceed to production script --mode single
```

---

### Update 2: Add File Creation Verification

**Track Prompt - Post-Execution Phase 2.1:**
```markdown
2.1 - Verify Production Workflow Execution

**CRITICAL: File Creation Verification**

Execute the following verification commands:

```bash
# Get track name from Notion or workflow output
TRACK_NAME="Obsidian Factum"  # Replace with actual track name
PLAYLIST_NAME="Unassigned"    # Replace with actual playlist name

# Verify M4A file in playlist directory
M4A_PATH="/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2/${PLAYLIST_NAME}/${TRACK_NAME}.m4a"
if [ -f "$M4A_PATH" ]; then
    echo "✅ M4A file exists: $(ls -lh "$M4A_PATH")"
else
    echo "❌ M4A file MISSING: $M4A_PATH"
fi

# Verify AIFF file
AIFF_PATH="/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2/${PLAYLIST_NAME}/${TRACK_NAME}.aiff"
if [ -f "$AIFF_PATH" ]; then
    echo "✅ AIFF file exists: $(ls -lh "$AIFF_PATH")"
else
    echo "❌ AIFF file MISSING: $AIFF_PATH"
fi

# Verify WAV backup
WAV_PATH="/Volumes/VIBES/Apple-Music-Auto-Add/${TRACK_NAME}.wav"
if [ -f "$WAV_PATH" ]; then
    echo "✅ WAV backup exists: $(ls -lh "$WAV_PATH")"
else
    echo "❌ WAV backup MISSING: $WAV_PATH"
fi

# Verify M4A backup
M4A_BACKUP="/Volumes/VIBES/Djay-Pro-Auto-Import/${TRACK_NAME}.m4a"
if [ -f "$M4A_BACKUP" ]; then
    echo "✅ M4A backup exists: $(ls -lh "$M4A_BACKUP")"
else
    echo "❌ M4A backup MISSING: $M4A_BACKUP"
fi
```

**Notion Property Verification:**
- Query Notion page for track
- Verify "M4A File Path" property contains correct path
- Verify "AIFF File Path" property contains correct path
- Verify "WAV File Path" property contains correct path
- Verify "Eagle File ID" property is populated
- If any paths missing: Create Agent-Task for investigation

**Eagle Import Verification:**
- Query Eagle API for item by file path or Eagle ID
- Verify item exists in Eagle library
- Verify tags are applied correctly
- If missing: Create Agent-Task for investigation
```

---

### Update 3: Add Spotify Track YouTube Search Documentation

**Track Prompt - Phase 0.1:**
```markdown
**Spotify Track Processing (Updated 2026-01-08):**

Spotify tracks are now processed through full workflow:
1. Check Notion for existing YouTube URL
2. If not found, search YouTube using artist/title from Spotify metadata
3. If YouTube URL found:
   - Download audio from YouTube
   - Process through full pipeline (BPM, Key, normalization, file creation)
   - Create M4A, AIFF, WAV files in correct locations
   - Import to Eagle library
   - Update Notion with all file paths and metadata
4. If no YouTube source found:
   - Fallback to metadata-only processing
   - Update Notion with "Spotify - No Audio Source Found" status
   - No files created (expected behavior)

**Verification:** After processing Spotify track, verify files were created if YouTube source was found.
```

---

### Update 4: Add Fallback Chain Timeout Rules

**Track Prompt - Phase 0.2:**
```markdown
**Fallback Chain Execution Rules:**

- **Timeout Limits:**
  * Priority 1 (Spotify Current Track): 5 seconds max
  * Priority 2 (SoundCloud Likes): 30 seconds max
  * Priority 3 (Spotify Liked Tracks): 30 seconds max

- **Retry Logic:**
  * Maximum 1 retry per priority level
  * If timeout or failure: Move to next priority immediately
  * Don't spend >60 seconds total on fallback chain

- **Final Fallback:**
  * If all priorities fail: Use production script --mode single
  * This processes newest eligible track from Notion
  * Document fallback chain failures as automation gap

- **Non-Blocking Rule:**
  * Fallback failures are NON-BLOCKING when no URL provided
  * Document issues but proceed to production script execution
  * Create Agent-Task for fallback chain improvements
```

---

### Update 5: Fix Playlist Prompt Spotify API References

**Playlist Prompt - Priority 3 (Line 213-231):**
```python
# BEFORE:
from spotify_integration_module import get_spotify_client
sp = get_spotify_client()
results = sp.current_user_playlists(limit=3)

# AFTER:
from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
try:
    oauth = SpotifyOAuthManager()
    sp = SpotifyAPI(oauth)
    results = sp.get_user_playlists(limit=3, offset=0)
    
    if results:
        for playlist in results:
            playlist_id = playlist.get('id')
            playlist_name = playlist.get('name')
            print(f'URL: https://open.spotify.com/playlist/{playlist_id}')
            print(f'TITLE: {playlist_name}')
            print(f'ID: {playlist_id}')
            print('---')
    else:
        print('No playlists found')
except Exception as e:
    workspace_logger.warning(f"Spotify API error: {e}")
    # Proceed to production script or next fallback
```

---

### Update 6: Add Batch Processing Error Handling

**Playlist Prompt - Phase 1.3:**
```markdown
**Batch Processing Error Handling:**

- **Individual Track Failures:**
  * Log error with track title and artist
  * Mark track as Downloaded=false in Notion
  * Continue processing remaining tracks
  * Don't stop entire batch for single track failure

- **Batch Failure Thresholds:**
  * If >50% of batch fails: Stop batch, create Agent-Task
  * If <50% fails: Continue, log failures, create summary task
  * If all tracks fail: Stop immediately, create critical Agent-Task

- **Retry Logic:**
  * Failed tracks should be retried individually in next execution
  * Use --mode reprocess for tracks with Downloaded=false
  * Don't retry entire batch if only few tracks failed

- **Reporting:**
  * Report batch results: X successful, Y failed, Z skipped
  * List failed tracks with error messages
  * Create Agent-Task for failed tracks if >3 failures
```

---

## System Alignment Improvements

### Alignment 1: Match Actual Codebase Implementation

**Current:** References non-existent functions  
**Fix:** Update all function references to match actual codebase

**Benefit:** Prompts work correctly, agents execute successfully

---

### Alignment 2: Reflect Recent Fixes

**Current:** Doesn't mention Spotify track YouTube search fix  
**Fix:** Document the fix and expected behavior

**Benefit:** Agents understand current implementation

---

### Alignment 3: Align with Production Workflow Design

**Current:** Some instructions don't match production workflow  
**Fix:** Verify all instructions match actual production script behavior

**Benefit:** Consistent execution, fewer errors

---

## Performance Improvements

### Performance 1: Reduce Troubleshooting Time

**Current:** No timeout/retry limits  
**Fix:** Add explicit timeout and retry rules

**Benefit:** Faster execution, less wasted time

---

### Performance 2: Add Verification Commands

**Current:** Vague verification instructions  
**Fix:** Provide exact commands to run

**Benefit:** Faster verification, catches issues immediately

---

### Performance 3: Streamline Fallback Chain

**Current:** May spend excessive time on fallback  
**Fix:** Add timeout rules and final fallback to --mode single

**Benefit:** Guarantees execution even if fallback fails

---

## Value-Adding Work Improvements

### Value 1: Explicit File Creation Verification

**Benefit:** Catches misalignments immediately, ensures deliverables

---

### Value 2: Automation Gap Documentation

**Benefit:** Creates actionable tasks for automation improvements

---

### Value 3: Error Recovery Guidance

**Benefit:** Agent can self-recover, reduces manual intervention

---

### Value 4: Performance Metrics Collection

**Benefit:** Enables optimization and monitoring

---

## Implementation Priority

### Critical (Fix Immediately)
1. ✅ Fix Spotify API function references (Issue 1, 5)
2. ✅ Add file creation verification (Issue 2, 8)
3. ✅ Add fallback chain timeout rules (Issue 4)

### High Priority (Fix Soon)
4. ✅ Document Spotify track YouTube search (Issue 3)
5. ✅ Add batch processing error handling (Issue 7)
6. ✅ Add playlist script verification (Issue 6)

### Medium Priority (Optimize)
7. ✅ Add all optimization opportunities
8. ✅ Improve error recovery guidance
9. ✅ Add performance metrics collection

---

## Recommended Next Steps

1. **Update Track Prompt:**
   - Fix Spotify API references
   - Add file creation verification
   - Add timeout/retry rules
   - Document YouTube search flow

2. **Update Playlist Prompt:**
   - Fix Spotify API references
   - Add batch processing error handling
   - Add playlist script verification
   - Add track-level file verification

3. **Test Updated Prompts:**
   - Execute with test tracks/playlists
   - Verify all instructions work correctly
   - Confirm verification catches issues

4. **Document Changes:**
   - Update prompt version numbers
   - Document changes in changelog
   - Create migration guide if needed

---

## Related Documents

- **Spotify Track Fix:** `SPOTIFY_TRACK_FILE_CREATION_MISALIGNMENT_REPORT.md`
- **Spotify Track Fix Audit:** `SPOTIFY_TRACK_FIX_AUDIT_REPORT.md`
- **Production Workflow:** `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md`

---

**Status:** 🔴 **CRITICAL UPDATES REQUIRED**  
**Priority:** **HIGHEST** - Prompts contain incorrect references that will cause execution failures
