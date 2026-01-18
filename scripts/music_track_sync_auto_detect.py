#!/usr/bin/env python3
"""
Music Track Sync Auto-Detection Wrapper Script

Implements the sync-aware fallback chain for automatic track detection:
1. Priority 1: Check Spotify Current Track
2. Priority 2: Fetch SoundCloud Likes (up to 5)
3. Priority 3: Fetch Spotify Liked Tracks (up to 5)
4. Final Fallback: Execute --mode single

For each priority, checks Notion sync status before proceeding.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Environment setup
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
ARTISTS_DB_ID = os.getenv("ARTISTS_DB_ID", "20ee7361-6c27-816d-9817-d4348f6de07c")
SOUNDCLOUD_PROFILE = os.getenv("SOUNDCLOUD_PROFILE", "vibe-vessel")
PRODUCTION_SCRIPT = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"

def get_notion_client():
    """Get Notion client for querying database."""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token
        notion_token = get_notion_token()
        if notion_token:
            try:
                from clients.notion_client import NotionClient
                return NotionClient(notion_token=notion_token)
            except ImportError:
                return {"token": notion_token}
    except ImportError:
        pass

    # Fallback to environment variables
    notion_token = os.getenv("NOTION_TOKEN")
    if not notion_token:
        print("WARNING: NOTION_TOKEN not set, skipping Notion queries")
        return None
    return {"token": notion_token}

def query_notion_track(spotify_id: str = None, soundcloud_url: str = None, title: str = None, artist: str = None) -> Optional[Dict]:
    """Query Notion for track by Spotify ID, SoundCloud URL, or title+artist."""
    notion = get_notion_client()
    if not notion:
        return None
    
    try:
        import requests
        
        if isinstance(notion, dict):
            token = notion.get("token")
        else:
            token = os.getenv("NOTION_TOKEN")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # Build filter based on available parameters
        filters = []
        if spotify_id:
            filters.append({
                "property": "Spotify ID",
                "rich_text": {"equals": spotify_id}
            })
        if soundcloud_url:
            filters.append({
                "property": "SoundCloud URL",
                "url": {"contains": soundcloud_url.split("/")[-1]}
            })
        if title and artist:
            filters.append({
                "and": [
                    {"property": "Title", "title": {"contains": title}},
                    {"property": "Artist Name", "rich_text": {"contains": artist}}
                ]
            })
        
        if not filters:
            return None
        
        # Use first filter for now (can be enhanced to try all)
        filter_obj = filters[0] if len(filters) == 1 else {"or": filters}
        
        url = f"https://api.notion.com/v1/databases/{TRACKS_DB_ID}/query"
        response = requests.post(url, headers=headers, json={"filter": filter_obj})
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0]  # Return first match
        elif response.status_code == 401:
            print(f"ERROR: Notion API authentication failed (401)")
        elif response.status_code == 404:
            print(f"ERROR: Notion database not found (404) - TRACKS_DB_ID: {TRACKS_DB_ID}")
        
        return None
    except Exception as e:
        print(f"WARNING: Failed to query Notion: {e}")
        return None

def is_track_fully_synced(track: Dict) -> bool:
    """Check if track is fully synced (has all URLs and is downloaded)."""
    if not track:
        return False
    
    props = track.get("properties", {})
    
    # Check if downloaded
    downloaded = False
    for prop_name in ["Downloaded", "DL"]:
        if prop_name in props:
            prop = props[prop_name]
            if prop.get("type") == "checkbox":
                downloaded = prop.get("checkbox", False)
                break
    
    # Check for file paths
    has_files = False
    for prop_name in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        if prop_name in props:
            prop = props[prop_name]
            if prop.get("type") == "rich_text":
                rich_text = prop.get("rich_text", [])
                if rich_text and rich_text[0].get("plain_text"):
                    has_files = True
                    break
    
    return downloaded and has_files

def priority_1_spotify_current_track() -> Optional[Tuple[str, str, str]]:
    """Priority 1: Check Spotify Current Track."""
    print("=" * 80)
    print("PRIORITY 1: Checking Spotify Current Track")
    print("=" * 80)
    
    try:
        # Use osascript to get current Spotify track
        script = '''
        tell application "Spotify"
            if player state is playing then
                set trackName to name of current track
                set trackArtist to artist of current track
                set trackId to id of current track
                return trackName & "|" & trackArtist & "|" & trackId
            else
                return "NOT_PLAYING"
            end if
        end tell
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            print("  → Spotify not playing or unavailable")
            return None
        
        output = result.stdout.strip()
        if output == "NOT_PLAYING":
            print("  → Spotify not currently playing")
            return None
        
        parts = output.split("|")
        if len(parts) != 3:
            print(f"  → Unexpected output format: {output}")
            return None
        
        track_name, track_artist, track_id = parts
        
        # Extract Spotify ID from full ID (format: spotify:track:xxxxx)
        if ":" in track_id:
            spotify_id = track_id.split(":")[-1]
        else:
            spotify_id = track_id
        
        spotify_url = f"https://open.spotify.com/track/{spotify_id}"
        
        print(f"  → Current track: {track_name} by {track_artist}")
        print(f"  → Spotify ID: {spotify_id}")
        
        # Check Notion sync status
        notion_track = query_notion_track(spotify_id=spotify_id, title=track_name, artist=track_artist)
        
        if notion_track:
            if is_track_fully_synced(notion_track):
                print(f"  → Track already fully synced in Notion")
                return None
            else:
                print(f"  → Track found in Notion but not fully synced, will update")
                return ("spotify", spotify_url, f"{track_name} by {track_artist}")
        else:
            print(f"  → Track not found in Notion, will sync")
            return ("spotify", spotify_url, f"{track_name} by {track_artist}")
            
    except subprocess.TimeoutExpired:
        print("  → Timeout checking Spotify (5s)")
        return None
    except FileNotFoundError:
        print("  → osascript not available (macOS only)")
        return None
    except Exception as e:
        print(f"  → Error checking Spotify: {e}")
        return None

def priority_2_soundcloud_likes() -> Optional[Tuple[str, str, str]]:
    """Priority 2: Fetch SoundCloud Likes (up to 5)."""
    print()
    print("=" * 80)
    print("PRIORITY 2: Fetching SoundCloud Likes")
    print("=" * 80)
    
    try:
        from yt_dlp import YoutubeDL
        
        likes_url = f"https://soundcloud.com/{SOUNDCLOUD_PROFILE}/likes"
        print(f"  → Fetching likes from: {likes_url}")
        
        opts = {'quiet': True, 'extract_flat': False}
        ytdl = YoutubeDL(opts)
        info = ytdl.extract_info(likes_url, download=False)
        
        if not info or not info.get('entries'):
            print(f"  → No likes found or profile not accessible")
            return None
        
        entries = info['entries'][:5]  # Limit to 5
        
        print(f"  → Found {len(entries)} recent likes")
        
        for track in entries:
            url = track.get('webpage_url') or track.get('url')
            title = track.get('title', 'Unknown')
            artist = track.get('uploader', 'Unknown')
            
            if not url:
                continue
            
            print(f"  → Checking: {title} by {artist}")
            
            # Check Notion sync status
            notion_track = query_notion_track(soundcloud_url=url, title=title, artist=artist)
            
            if notion_track:
                if is_track_fully_synced(notion_track):
                    print(f"    → Already fully synced")
                    continue
                else:
                    print(f"    → Found but not fully synced, will update")
                    return ("soundcloud", url, f"{title} by {artist}")
            else:
                print(f"    → Not found in Notion, will sync")
                return ("soundcloud", url, f"{title} by {artist}")
        
        print(f"  → All {len(entries)} tracks already synced")
        return None
        
    except ImportError:
        print("  → yt-dlp not available, skipping SoundCloud likes")
        return None
    except Exception as e:
        print(f"  → Error fetching SoundCloud likes: {e}")
        return None

def priority_3_spotify_liked_tracks() -> Optional[Tuple[str, str, str]]:
    """Priority 3: Fetch Spotify Liked Tracks (up to 5)."""
    print()
    print("=" * 80)
    print("PRIORITY 3: Fetching Spotify Liked Tracks")
    print("=" * 80)
    
    try:
        from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
        
        oauth = SpotifyOAuthManager()
        sp = SpotifyAPI(oauth)
        
        # Get user playlists and find "Liked Songs" playlist
        playlists = sp.get_user_playlists(limit=50, offset=0)
        liked_songs_playlist = None
        
        for playlist in playlists:
            if playlist.get('name') == 'Liked Songs' or 'liked' in playlist.get('name', '').lower():
                liked_songs_playlist = playlist
                break
        
        if not liked_songs_playlist:
            print("  → Liked Songs playlist not found")
            # Fallback: Use first playlist
            if playlists:
                liked_songs_playlist = playlists[0]
                print(f"  → Using first playlist as fallback: {liked_songs_playlist.get('name')}")
            else:
                print("  → No playlists found")
                return None
        
        playlist_id = liked_songs_playlist.get('id')
        tracks = sp.get_playlist_tracks(playlist_id, limit=5)
        
        if not tracks:
            print("  → No tracks found in playlist")
            return None
        
        print(f"  → Found {len(tracks)} recent tracks")
        
        for item in tracks[:5]:
            track = item.get('track', {})
            if not track:
                continue
            
            track_id = track.get('id')
            track_name = track.get('name', 'Unknown')
            artist_name = track.get('artists', [{}])[0].get('name', 'Unknown')
            spotify_url = f"https://open.spotify.com/track/{track_id}"
            
            print(f"  → Checking: {track_name} by {artist_name}")
            
            # Check Notion sync status
            notion_track = query_notion_track(spotify_id=track_id, title=track_name, artist=artist_name)
            
            if notion_track:
                if is_track_fully_synced(notion_track):
                    print(f"    → Already fully synced")
                    continue
                else:
                    print(f"    → Found but not fully synced, will update")
                    return ("spotify", spotify_url, f"{track_name} by {artist_name}")
            else:
                print(f"    → Not found in Notion, will sync")
                return ("spotify", spotify_url, f"{track_name} by {artist_name}")
        
        print(f"  → All {len(tracks)} tracks already synced")
        return None
        
    except ImportError:
        print("  → Spotify integration module not available, skipping Spotify liked tracks")
        return None
    except Exception as e:
        print(f"  → Error fetching Spotify liked tracks: {e}")
        return None

def execute_production_workflow(url: str) -> int:
    """Execute production workflow script with URL."""
    print()
    print("=" * 80)
    print("EXECUTING PRODUCTION WORKFLOW")
    print("=" * 80)
    print(f"  → URL: {url}")
    print(f"  → Script: {PRODUCTION_SCRIPT}")
    
    if not PRODUCTION_SCRIPT.exists():
        print(f"  ✗ ERROR: Production script not found: {PRODUCTION_SCRIPT}")
        return 1
    
    try:
        env = os.environ.copy()
        env["TRACKS_DB_ID"] = TRACKS_DB_ID
        
        cmd = [
            sys.executable,
            str(PRODUCTION_SCRIPT),
            "--mode", "url",
            "--url", url
        ]
        
        print(f"  → Command: {' '.join(cmd)}")
        print()
        
        result = subprocess.run(cmd, cwd=project_root, env=env)
        return result.returncode
        
    except Exception as e:
        print(f"  ✗ ERROR: Failed to execute production workflow: {e}")
        return 1

def execute_fallback_single_mode() -> int:
    """Final fallback: Execute --mode single."""
    print()
    print("=" * 80)
    print("FINAL FALLBACK: Executing --mode single")
    print("=" * 80)
    
    if not PRODUCTION_SCRIPT.exists():
        print(f"  ✗ ERROR: Production script not found: {PRODUCTION_SCRIPT}")
        return 1
    
    try:
        env = os.environ.copy()
        env["TRACKS_DB_ID"] = TRACKS_DB_ID
        
        cmd = [
            sys.executable,
            str(PRODUCTION_SCRIPT),
            "--mode", "single"
        ]
        
        print(f"  → Command: {' '.join(cmd)}")
        print()
        
        result = subprocess.run(cmd, cwd=project_root, env=env)
        return result.returncode
        
    except Exception as e:
        print(f"  ✗ ERROR: Failed to execute single mode: {e}")
        return 1

def main():
    """Main function implementing fallback chain."""
    print("Music Track Sync Auto-Detection Wrapper")
    print("=" * 80)
    print()
    
    # Priority 1: Spotify Current Track
    result = priority_1_spotify_current_track()
    if result:
        source, url, description = result
        print(f"\n✓ Selected track from Priority 1 ({source}): {description}")
        return execute_production_workflow(url)
    
    # Priority 2: SoundCloud Likes
    result = priority_2_soundcloud_likes()
    if result:
        source, url, description = result
        print(f"\n✓ Selected track from Priority 2 ({source}): {description}")
        return execute_production_workflow(url)
    
    # Priority 3: Spotify Liked Tracks
    result = priority_3_spotify_liked_tracks()
    if result:
        source, url, description = result
        print(f"\n✓ Selected track from Priority 3 ({source}): {description}")
        return execute_production_workflow(url)
    
    # Final Fallback: --mode single
    print()
    print("=" * 80)
    print("All priorities exhausted, using final fallback: --mode single")
    print("=" * 80)
    return execute_fallback_single_mode()

if __name__ == "__main__":
    sys.exit(main())
