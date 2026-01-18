# SoundCloud Integration Extraction Status

**Date:** 2026-01-12  
**Issue ID:** 2e6e7361-6c27-8174-9eb5-f5036e67b90e  
**Status:** Integration Module Complete, Migration Pending

## Current State

### ✅ Completed

1. **SoundCloud Integration Module Created**
   - Location: `music_workflow/integrations/soundcloud/`
   - Files:
     - `__init__.py` - Module exports
     - `client.py` - SoundCloudClient implementation (431 lines)
   - Features:
     - Track metadata extraction via yt-dlp
     - Track downloading with format selection
     - Playlist extraction
     - Search functionality
     - Error handling and timeouts

2. **Integration Tests Created**
   - Location: `music_workflow/tests/integration/test_soundcloud_integration.py`
   - Tests cover client initialization, URL validation, and error handling

### ⚠️ Pending Migration

**Monolithic Script Still Uses Inline yt-dlp Code**
- File: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
- Current implementation:
  - Direct yt-dlp calls (lines ~9372-9580)
  - Custom error handling and retry logic
  - Preview detection and YouTube fallback
  - Geo-restriction handling
  - Custom temp directory management

## Migration Requirements

### Functions to Replace

1. **Metadata Extraction** (lines ~9372-9516)
   - Current: Direct `yt_dlp.YoutubeDL().extract_info()`
   - Replace with: `SoundCloudClient.extract_info()` or `SoundCloudClient.get_track()`

2. **Track Download** (lines ~9551-9700+)
   - Current: Direct `yt_dlp.YoutubeDL().download()` with custom postprocessing
   - Replace with: `SoundCloudClient.download()` with format selection

3. **URL Parsing** (line ~3956)
   - Current: `parse_soundcloud_url()` function
   - Replace with: `SoundCloudClient.is_soundcloud_url()` and URL parsing

### Compatibility Considerations

The monolithic script has additional features not yet in the integration module:

1. **Preview Detection** (lines ~9390-9455)
   - Detects SoundCloud Go+ preview tracks (~30 seconds)
   - Automatically searches YouTube for full track
   - Updates Notion with YouTube URL
   - Falls back to YouTube download

2. **Geo-Restriction Handling** (lines ~8651, 9583-9610)
   - Detects geo-restriction errors
   - Falls back to YouTube if available
   - Configurable via `enable_youtube_fallback`

3. **Custom Temp Directory Management**
   - Uses unified_config temp_dir
   - UUID-based temp directories
   - Cleanup on error

4. **Enhanced Error Handling**
   - Retry logic with exponential backoff
   - 404 detection and status updates
   - Rate limiting handling

## Recommended Migration Approach

### Phase 1: Extend Integration Module (Recommended)

Add missing features to `SoundCloudClient`:

1. Add preview detection method
2. Add geo-restriction detection helper
3. Support custom temp directories
4. Add retry logic wrapper

### Phase 2: Gradual Migration

1. Create adapter/wrapper function that maintains current behavior
2. Replace direct yt-dlp calls one function at a time
3. Test each replacement thoroughly
4. Maintain backward compatibility during transition

### Phase 3: Cleanup

1. Remove inline yt-dlp code
2. Remove `parse_soundcloud_url()` if redundant
3. Update all call sites
4. Remove compatibility wrappers

## Next Steps

1. **Immediate:** Update Notion issue to reflect current state
2. **Short-term:** Extend SoundCloudClient with missing features OR create compatibility adapter
3. **Medium-term:** Migrate monolithic script to use integration module
4. **Long-term:** Remove legacy code and complete migration

## Related Issues

- All 17 "Missing Deliverable" issues from MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md
- These represent various extraction tasks from the monolithic script

## Notes

- The integration module is production-ready but not yet used
- Migration requires careful testing due to production script complexity
- Consider feature flags for gradual rollout
- Maintain backward compatibility during transition
