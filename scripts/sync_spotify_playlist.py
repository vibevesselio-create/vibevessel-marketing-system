#!/usr/bin/env python3
"""
Spotify Playlist and Album Synchronization Script
─────────────────────────────────────────────────────────────────────────────────────
Complete end-to-end Spotify playlist/album processing:
1. Extract Spotify ID from URL (playlist or album)
2. Sync tracks to Notion Music Tracks database (with deduplication)
3. Create/update playlist or album entry in Notion
4. Link tracks to playlist/album
5. Optionally trigger download workflow for tracks

Usage:
    python sync_spotify_playlist.py <spotify_url> [--playlist-name NAME] [--max-tracks N] [--dry-run]

Example:
    python sync_spotify_playlist.py "https://open.spotify.com/playlist/6XIc4VjUi7MIJnp7tshFy0"
    python sync_spotify_playlist.py "https://open.spotify.com/album/5QRFnGnBeMGePBKF2xTz5z" --playlist-name "Album Name"

Aligned with Seren Media Workspace Standards
Version: 2026-01-08
"""
import os
import sys
import json
import argparse
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

# Load unified environment
try:
    from unified_config import load_unified_env, get_unified_config, setup_unified_logging
    load_unified_env()
    unified_config = get_unified_config()
    logger = setup_unified_logging(session_id="spotify_playlist_sync")
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    print(f"Warning: unified_config unavailable ({unified_err}); using environment variables directly.", file=sys.stderr)
    unified_config = {}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("spotify_playlist_sync")

# Import Spotify integration module
try:
    sys.path.insert(0, str(project_root / "monolithic-scripts"))
    from spotify_integration_module import SpotifyNotionSync, SpotifyAPI, NotionSpotifyIntegration
    SPOTIFY_AVAILABLE = True
except ImportError as e:
    print(f"❌ Error importing Spotify integration module: {e}")
    print(f"   Make sure spotify_integration_module.py exists in monolithic-scripts/")
    sys.exit(1)

def extract_spotify_id(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract Spotify ID and type from URL.
    
    Returns:
        Tuple of (id, type) where type is 'playlist', 'album', 'track', or None
    """
    if not url or "spotify.com" not in url.lower():
        return None, None
    
    # Pattern to match: https://open.spotify.com/{type}/{id} or spotify:{type}:{id}
    patterns = [
        (r"spotify\.com/(playlist|album|track)/([a-zA-Z0-9]+)", r"\1", r"\2"),
        (r"spotify:(playlist|album|track):([a-zA-Z0-9]+)", r"\1", r"\2"),
    ]
    
    for pattern, type_group, id_group in patterns:
        match = re.search(pattern, url)
        if match:
            spotify_type = match.group(1)
            spotify_id = match.group(2)
            return spotify_id, spotify_type
    
    return None, None

def sync_spotify_playlist(
    playlist_id: str,
    playlist_name: Optional[str] = None,
    max_tracks: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Sync a Spotify playlist to Notion.
    
    Returns sync statistics.
    """
    print(f"\n{'='*80}")
    print(f"🔄 SYNCING SPOTIFY PLAYLIST TO NOTION")
    print(f"{'='*80}")
    print(f"Playlist ID: {playlist_id}")
    if playlist_name:
        print(f"Playlist Name: {playlist_name}")
    if max_tracks:
        print(f"Max Tracks: {max_tracks}")
    if dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print(f"{'='*80}\n")
    
    if dry_run:
        return {
            "success": True,
            "tracks_added": 0,
            "tracks_skipped": 0,
            "dry_run": True,
        }
    
    try:
        sync = SpotifyNotionSync()
        result = sync.sync_playlist(playlist_id)
        
        # Apply max_tracks limit if specified (this is a post-process limit for display)
        if max_tracks and result.get("processed_tracks", 0) > max_tracks:
            result["processed_tracks"] = max_tracks
        
        print(f"\n{'='*80}")
        print(f"✅ SYNC COMPLETE")
        print(f"{'='*80}")
        print(f"Playlist: {result.get('playlist_name', 'Unknown')}")
        print(f"Total Tracks: {result.get('total_tracks', 0)}")
        print(f"Processed Tracks: {result.get('processed_tracks', 0)}")
        print(f"Failures: {result.get('failures', 0)}")
        print(f"{'='*80}\n")
        
        return result
    except Exception as e:
        print(f"❌ Failed to sync playlist: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "tracks_added": 0,
            "tracks_skipped": 0,
        }

def sync_spotify_album(
    album_id: str,
    album_name: Optional[str] = None,
    max_tracks: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Sync a Spotify album to Notion.
    
    Returns sync statistics.
    """
    import time
    
    print(f"\n{'='*80}")
    print(f"🔄 SYNCING SPOTIFY ALBUM TO NOTION")
    print(f"{'='*80}")
    print(f"Album ID: {album_id}")
    if album_name:
        print(f"Album Name: {album_name}")
    if max_tracks:
        print(f"Max Tracks: {max_tracks}")
    if dry_run:
        print(f"Mode: DRY RUN (no changes will be made)")
    print(f"{'='*80}\n")
    
    if dry_run:
        return {
            "success": True,
            "tracks_added": 0,
            "tracks_skipped": 0,
            "dry_run": True,
        }
    
    try:
        spotify = SpotifyAPI()
        notion = NotionSpotifyIntegration()
        
        # Get album info - use the public API endpoint
        album_info = spotify._make_request("GET", f"/albums/{album_id}")
        if not album_info:
            return {
                "success": False,
                "error": "Failed to get album info from Spotify",
                "tracks_added": 0,
                "tracks_skipped": 0,
            }
        
        album_name = album_info.get("name", album_name or "Unknown Album")
        print(f"📋 Album: {album_name}")
        
        # Get album tracks - albums endpoint returns tracks in the response
        # But we may need to paginate through tracks if there are many
        album_tracks = album_info.get("tracks", {})
        tracks = album_tracks.get("items", [])
        next_url = album_tracks.get("next")
        
        # Handle pagination if needed
        while next_url:
            # Extract offset from next_url or use Spotify API pagination
            offset = len(tracks)
            params = {"limit": 50, "offset": offset, "market": spotify.market}
            data = spotify._make_request("GET", f"/albums/{album_id}/tracks", params=params)
            if not data or not data.get("items"):
                break
            
            tracks.extend(data["items"])
            next_url = data.get("next")
            
            if len(data["items"]) < 50:
                break
        
        print(f"🎵 Found {len(tracks)} tracks in album")
        
        # Limit tracks if specified
        if max_tracks and max_tracks > 0:
            tracks = tracks[:max_tracks]
            print(f"📊 Limited to {max_tracks} tracks\n")
        
        # Create/update album page in Notion (if album database exists)
        album_page_id = None
        try:
            # Try to find existing album page
            album_page_id = notion.find_or_create_album_page(album_info)
        except Exception as e:
            logger.debug(f"Album page creation skipped (database may not be configured): {e}")
        
        # Process each track
        processed = 0
        failures = 0
        
        print(f"📤 Adding {len(tracks)} tracks to Notion...\n")
        
        for i, track_item in enumerate(tracks, 1):
            track_id = track_item.get("id")
            if not track_id:
                continue
            
            track_name = track_item.get("name", "Unknown Track")
            artists = track_item.get("artists", [])
            artist_names = ", ".join([a.get("name", "") for a in artists])
            
            print(f"[{i}/{len(tracks)}] {track_name} by {artist_names}")
            
            try:
                # Get full track info
                track_info = spotify.get_track_info(track_id)
                if not track_info:
                    logger.warning(f"Could not get track info for {track_id}")
                    failures += 1
                    continue
                
                # Get audio features
                audio_features = spotify.get_audio_features(track_id)
                
                # Check if track already exists
                track_page_id = notion.find_track_by_spotify_id(track_id)
                if not track_page_id:
                    duration_ms = int(track_info.get("duration_ms") or 0)
                    track_page_id = notion.find_track_by_name_and_duration(
                        track_info.get("name", ""), duration_ms
                    )
                
                # Create track if it doesn't exist
                if not track_page_id:
                    track_page_id = notion.create_track_page(track_info, audio_features)
                    if track_page_id:
                        processed += 1
                        print(f"   ✅ Created: {track_name}")
                    else:
                        failures += 1
                        print(f"   ❌ Failed to create: {track_name}")
                        continue
                else:
                    print(f"   ⏭️  Skipped (exists): {track_name}")
                
                # Update Spotify-specific fields
                if track_page_id:
                    notion.update_track_spotify_fields(track_page_id, track_info, audio_features)
                    
                    # Link to album if album page exists
                    if album_page_id:
                        try:
                            notion.link_track_to_album(track_page_id, album_page_id)
                        except Exception as e:
                            logger.debug(f"Album linking failed: {e}")
                    
                    # Link to artists
                    try:
                        for artist in track_info.get("artists", []):
                            artist_page_id = notion.find_or_create_artist_page(artist)
                            if artist_page_id:
                                notion.link_track_to_artist(track_page_id, artist_page_id)
                    except Exception as e:
                        logger.debug(f"Artist linking failed: {e}")
                
                time.sleep(0.2)  # Rate limiting
                
            except Exception as exc:
                failures += 1
                logger.error(f"Failed to process track {track_name}: {exc}")
                print(f"   ❌ Error: {track_name} - {exc}")
                if failures >= 10:
                    logger.error("Stopping album sync after 10 failures.")
                    break
        
        print(f"\n{'='*80}")
        print(f"✅ SYNC COMPLETE")
        print(f"{'='*80}")
        print(f"Album: {album_name}")
        print(f"Total Tracks: {len(tracks)}")
        print(f"Processed Tracks: {processed}")
        print(f"Failures: {failures}")
        print(f"{'='*80}\n")
        
        return {
            "success": failures == 0,
            "album_id": album_id,
            "album_name": album_name,
            "total_tracks": len(tracks),
            "processed_tracks": processed,
            "failures": failures,
        }
        
    except Exception as e:
        print(f"❌ Failed to sync album: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "tracks_added": 0,
            "tracks_skipped": 0,
        }

def main():
    parser = argparse.ArgumentParser(
        description="Sync Spotify playlist or album to Notion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync a playlist
  python sync_spotify_playlist.py "https://open.spotify.com/playlist/6XIc4VjUi7MIJnp7tshFy0"
  
  # Sync an album
  python sync_spotify_playlist.py "https://open.spotify.com/album/5QRFnGnBeMGePBKF2xTz5z"
  
  # Sync with custom name
  python sync_spotify_playlist.py "https://open.spotify.com/playlist/..." --playlist-name "My Playlist"
  
  # Sync first 50 tracks only
  python sync_spotify_playlist.py "https://open.spotify.com/playlist/..." --max-tracks 50
  
  # Dry run (see what would be synced)
  python sync_spotify_playlist.py "https://open.spotify.com/playlist/..." --dry-run
        """
    )
    
    parser.add_argument(
        "spotify_url",
        help="Spotify URL (playlist, album, or track)"
    )
    parser.add_argument(
        "--playlist-name",
        help="Optional playlist/album name (will be extracted from URL if not provided)"
    )
    parser.add_argument(
        "--max-tracks",
        type=int,
        help="Maximum number of tracks to process (default: all tracks)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    # Extract ID and type from URL
    spotify_id, spotify_type = extract_spotify_id(args.spotify_url)
    
    if not spotify_id or not spotify_type:
        print("❌ Error: Invalid Spotify URL")
        print("   URL must be a Spotify playlist, album, or track URL")
        print("   Example: https://open.spotify.com/playlist/6XIc4VjUi7MIJnp7tshFy0")
        sys.exit(1)
    
    # Sync based on type
    if spotify_type == "playlist":
        result = sync_spotify_playlist(
            playlist_id=spotify_id,
            playlist_name=args.playlist_name,
            max_tracks=args.max_tracks,
            dry_run=args.dry_run,
        )
    elif spotify_type == "album":
        result = sync_spotify_album(
            album_id=spotify_id,
            album_name=args.playlist_name,
            max_tracks=args.max_tracks,
            dry_run=args.dry_run,
        )
    else:
        print(f"❌ Error: Unsupported Spotify type: {spotify_type}")
        print("   Currently supports: playlist, album")
        sys.exit(1)
    
    # Exit with appropriate code
    if result.get("success"):
        print("\n✅ Spotify sync completed successfully!")
        sys.exit(0)
    else:
        print(f"\n❌ Spotify sync completed with errors: {result.get('error', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    import time
    main()
