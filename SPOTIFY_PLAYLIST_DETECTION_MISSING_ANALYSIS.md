# Spotify Playlist Detection Missing - Analysis Report

**Date:** 2026-01-08  
**Issue:** Track downloaded from Spotify without playlist relationship detection  
**Track:** "Where Are You Now" by Lost Frequencies  
**Status:** 🔴 **CRITICAL GAP IDENTIFIED**

---

## Executive Summary

The Music Track Sync Workflow v3.0 execution script (`execute_music_track_sync_workflow.py`) **does NOT check for Spotify playlist relationships** when processing tracks from the fallback chain. When a Spotify track is detected, the workflow:

1. ✅ Checks if track exists in Notion
2. ✅ Checks if track is fully synced
3. ❌ **MISSING:** Does NOT check which Spotify playlist(s) the track is on
4. ❌ **MISSING:** Does NOT add track to Notion with playlist relationships
5. ❌ **MISSING:** Does NOT use existing Spotify playlist sync functionality

---

## Root Cause Analysis

### Current Implementation (Lines 141-220 in execute_music_track_sync_workflow.py)

**Function: `check_spotify_current_track()`**
- ✅ Detects Spotify currently playing track
- ✅ Extracts track name, artist, ID
- ❌ **DOES NOT:** Check which playlist the track is playing from
- ❌ **DOES NOT:** Use Spotify API to find playlists containing the track

**Function: `query_notion_for_spotify_track()`**
- ✅ Queries Notion for track by Spotify ID
- ✅ Checks if track is fully synced
- ❌ **DOES NOT:** Check playlist relationships in Notion
- ❌ **DOES NOT:** Verify playlist associations

**Function: `execute_fallback_chain()`**
- ✅ Executes priority-based fallback chain
- ✅ Processes Spotify tracks when found
- ❌ **DOES NOT:** Check for playlist context
- ❌ **DOES NOT:** Add playlist relationships to Notion

### Missing Functionality

**1. Spotify Playlist Detection**
The workflow should check which Spotify playlist(s) contain the track using:
- Spotify Web API: `GET /v1/tracks/{id}` doesn't provide playlist info directly
- Spotify Web API: `GET /v1/me/playlists` and check each playlist for the track
- Spotify Web API: Use user's playlists and search for track in each

**2. Notion Playlist Relationship Creation**
The workflow should:
- Use `spotify_integration_module.py` → `SpotifyNotionSync.sync_playlist()` (line 715)
- Or manually link track to playlist using `NotionSpotifyIntegration.link_track_to_playlist()` (line 575)
- Add track to Notion with playlist relation before processing

**3. Playlist-Aware Processing**
The production script (`soundcloud_download_prod_merge-2.py`) DOES have playlist handling:
- `get_playlist_names_from_track()` (line 3804) - extracts playlist names from track
- Uses playlist names for file organization (OUT_DIR / playlist_name /)
- But only works if track already has playlist relationships in Notion

---

## Impact Assessment

### What Was Missed

1. **Playlist Relationship:** Track "Where Are You Now" by Lost Frequencies is on a Spotify playlist, but:
   - Playlist relationship was NOT detected during fallback chain
   - Playlist relationship was NOT added to Notion
   - File was saved to "Unassigned" instead of playlist directory

2. **File Organization:** Files should be organized by playlist:
   - **Expected:** `OUT_DIR / {playlist_name} / {track_name}.m4a`
   - **Actual:** `OUT_DIR / Unassigned / {track_name}.m4a` (if track has no playlist relation)

3. **Workflow Completeness:** The workflow is incomplete because:
   - It doesn't leverage existing Spotify playlist sync functionality
   - It doesn't maintain playlist relationships during processing
   - It doesn't organize files by playlist automatically

---

## Existing Functionality (Not Used)

### Spotify Integration Module (`spotify_integration_module.py`)

**Class: `SpotifyNotionSync`**
- `sync_playlist(playlist_id)` (line 715): Syncs entire playlist to Notion
- Links tracks to playlists automatically (line 755)
- Creates tracks with playlist relationships (line 751-755)

**Class: `NotionSpotifyIntegration`**
- `link_track_to_playlist(track_page_id, playlist_page_id)` (line 575): Links track to playlist
- `find_track_by_spotify_id(spotify_id)` (line 523): Finds track in Notion
- `create_track_page(track, audio_features)` (line 425): Creates track with metadata

### Production Script Playlist Handling

**Function: `get_playlist_names_from_track()` (line 3804)**
- Extracts playlist names from track relations
- Supports multiple playlist property types (relation, rich_text, title, select, multi_select)
- Returns list of playlist names for file organization

**Usage in Production Script:**
- Called during track processing (line 7025-7026 for Spotify tracks)
- Used to determine output directory (OUT_DIR / playlist_name /)
- Falls back to "Unassigned" if no playlists found

---

## Required Fixes

### Fix 1: Add Spotify Playlist Detection

**Location:** `execute_music_track_sync_workflow.py`

**Add Function:**
```python
def get_spotify_playlists_for_track(spotify_client, track_id: str) -> List[Dict[str, str]]:
    """
    Find which Spotify playlists contain a track.
    
    Returns:
        List of playlist dictionaries with 'id', 'name', 'url'
    """
    playlists_with_track = []
    
    # Get user's playlists
    playlists = spotify_client.get_user_playlists(limit=50, offset=0)
    
    # Check each playlist for the track
    for playlist in playlists:
        playlist_id = playlist.get('id')
        tracks = spotify_client.get_playlist_tracks(playlist_id)
        
        # Check if track is in this playlist
        for item in tracks:
            if item.get('track', {}).get('id') == track_id:
                playlists_with_track.append({
                    'id': playlist_id,
                    'name': playlist.get('name'),
                    'url': playlist.get('external_urls', {}).get('spotify')
                })
                break
    
    return playlists_with_track
```

### Fix 2: Add Playlist Relationship Creation

**Location:** `execute_music_track_sync_workflow.py`

**Modify Function: `execute_fallback_chain()`**
```python
# When Spotify track found and not in Notion:
if spotify_track:
    found, fully_synced = query_notion_for_spotify_track(notion_client, spotify_track['id'])
    
    if not found:
        # NEW: Get playlists for this track
        try:
            from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
            oauth = SpotifyOAuthManager()
            sp = SpotifyAPI(oauth)
            playlists = get_spotify_playlists_for_track(sp, spotify_track['id'])
            
            if playlists:
                logger.info(f"   → Found track on {len(playlists)} playlist(s): {[p['name'] for p in playlists]}")
                # Store playlist info for later use
                spotify_track['playlists'] = playlists
        except Exception as e:
            logger.warning(f"   → Failed to get playlists for track: {e}")
    
    # Continue with processing...
```

### Fix 3: Add Track to Notion with Playlist Relationships

**Location:** `execute_music_track_sync_workflow.py`

**Add Function:**
```python
def add_spotify_track_to_notion_with_playlists(notion_client: Client, spotify_client, 
                                               track_info: Dict, playlists: List[Dict]) -> Optional[str]:
    """
    Add Spotify track to Notion with playlist relationships.
    
    Returns:
        Track page ID or None
    """
    try:
        # Use spotify_integration_module to sync track
        from spotify_integration_module import SpotifyNotionSync, NotionSpotifyIntegration
        
        sync = SpotifyNotionSync()
        notion_integration = NotionSpotifyIntegration()
        
        # Get full track data from Spotify
        track_data = spotify_client.get_track(track_info['id'])
        audio_features = spotify_client.get_audio_features(track_info['id'])
        
        # Create or find track page
        track_page_id = notion_integration.find_track_by_spotify_id(track_info['id'])
        if not track_page_id:
            track_page_id = notion_integration.create_track_page(track_data, audio_features)
        
        # Link to playlists
        for playlist in playlists:
            # Find or create playlist page in Notion
            playlist_page_id = find_or_create_playlist_page(notion_client, playlist)
            if playlist_page_id:
                notion_integration.link_track_to_playlist(track_page_id, playlist_page_id)
        
        return track_page_id
    except Exception as e:
        logger.error(f"Failed to add track to Notion with playlists: {e}")
        return None
```

---

## Verification Checklist

After fixes are implemented, verify:

- [ ] Spotify playlist detection works for currently playing track
- [ ] Playlist relationships added to Notion before track processing
- [ ] Production script receives track with playlist relationships
- [ ] Files organized by playlist directory (not "Unassigned")
- [ ] Multiple playlists handled correctly (if track on multiple playlists)
- [ ] Existing Spotify playlist sync functionality utilized
- [ ] Error handling for playlist detection failures
- [ ] Logging includes playlist information

---

## Related Files

- `execute_music_track_sync_workflow.py` - **Requires fixes**
- `monolithic-scripts/soundcloud_download_prod_merge-2.py` - Already has playlist handling
- `monolithic-scripts/spotify_integration_module.py` - Has playlist sync functionality (not used)
- `EXECUTE: Music Track Sync Workflow.md` - **Requires documentation update**

---

## Priority

**HIGHEST** - This is a core workflow functionality gap that prevents proper playlist organization and relationship tracking.

---

**Analysis Completed:** 2026-01-08  
**Next Action:** Implement fixes in `execute_music_track_sync_workflow.py`
