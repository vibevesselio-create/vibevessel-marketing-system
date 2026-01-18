#!/usr/bin/env python3
"""
Sync and enrich a specific Spotify track in Notion by page ID.

Usage:
    python3 sync_spotify_track_by_page_id.py <notion_page_id> [spotify_track_id]
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import Spotify integration
try:
    from spotify_integration_module import SpotifyAPI, NotionSpotifyIntegration
    SPOTIFY_AVAILABLE = True
except ImportError as e:
    print(f"Error importing Spotify integration: {e}")
    SPOTIFY_AVAILABLE = False
    sys.exit(1)

def extract_spotify_track_id(url_or_id: str) -> str:
    """Extract Spotify track ID from URL or return as-is if already an ID."""
    if "spotify.com/track/" in url_or_id:
        # Extract track ID from URL
        parts = url_or_id.split("spotify.com/track/")
        if len(parts) > 1:
            track_id = parts[1].split("?")[0].split("&")[0]
            return track_id
    return url_or_id

def sync_track(notion_page_id: str, spotify_track_id: str = None):
    """Sync and enrich a Spotify track in Notion."""
    if not SPOTIFY_AVAILABLE:
        print("❌ Spotify integration not available")
        return False
    
    # Initialize APIs
    spotify = SpotifyAPI()
    notion = NotionSpotifyIntegration()
    
    # Get Spotify track ID from Notion page if not provided
    if not spotify_track_id:
        print(f"📄 Fetching Notion page: {notion_page_id}")
        page = notion.get_page(notion_page_id)
        if not page:
            print(f"❌ Failed to fetch Notion page: {notion_page_id}")
            return False
        
        # Try to get Spotify ID from page properties
        props = page.get("properties", {})
        spotify_id_prop = props.get("Spotify ID") or props.get("Spotify Track ID")
        if spotify_id_prop:
            rich_text = spotify_id_prop.get("rich_text", [])
            if rich_text and len(rich_text) > 0:
                spotify_track_id = rich_text[0].get("text", {}).get("content", "")
        
        # If still not found, try Spotify URL
        if not spotify_track_id:
            spotify_url_prop = props.get("Spotify URL")
            if spotify_url_prop:
                spotify_url = spotify_url_prop.get("url", "")
                if spotify_url:
                    spotify_track_id = extract_spotify_track_id(spotify_url)
        
        if not spotify_track_id:
            print("❌ Could not find Spotify track ID in Notion page")
            return False
    
    print(f"🎵 Processing Spotify track: {spotify_track_id}")
    
    # Get track data from Spotify
    print("📡 Fetching track data from Spotify...")
    track_data = spotify.get_track_info(spotify_track_id)
    if not track_data:
        print(f"❌ Failed to fetch track data from Spotify")
        return False
    
    print(f"   Title: {track_data.get('name', 'Unknown')}")
    print(f"   Artist: {', '.join([a.get('name', '') for a in track_data.get('artists', [])])}")
    
    # Get audio features
    print("📊 Fetching audio features...")
    audio_features = spotify.get_audio_features(spotify_track_id)
    if audio_features:
        print(f"   Tempo: {audio_features.get('tempo', 0):.1f} BPM")
        print(f"   Energy: {audio_features.get('energy', 0):.2f}")
        print(f"   Danceability: {audio_features.get('danceability', 0):.2f}")
    else:
        print("   ⚠️  Audio features not available")
    
    # Update Notion page with Spotify data
    print(f"📝 Updating Notion page: {notion_page_id}")
    success = notion.update_track_spotify_fields(notion_page_id, track_data, audio_features)
    
    if success:
        print("✅ Successfully synced track to Notion!")
        
        # Try to link to artists and album
        try:
            artists = track_data.get("artists", [])
            if artists:
                print("🔗 Linking artists...")
                for artist in artists:
                    artist_page_id = notion.find_or_create_artist_page(artist)
                    if artist_page_id:
                        notion.link_track_to_artist(notion_page_id, artist_page_id)
                        print(f"   ✓ Linked to artist: {artist.get('name', 'Unknown')}")
            
            album_data = track_data.get("album", {})
            if album_data:
                print("🔗 Linking album...")
                album_page_id = notion.find_or_create_album_page(album_data)
                if album_page_id:
                    notion.link_track_to_album(notion_page_id, album_page_id)
                    print(f"   ✓ Linked to album: {album_data.get('name', 'Unknown')}")
        except Exception as e:
            print(f"   ⚠️  Artist/Album linking failed (may not be configured): {e}")
        
        return True
    else:
        print("❌ Failed to update Notion page")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sync_spotify_track_by_page_id.py <notion_page_id> [spotify_track_id]")
        print("\nExample:")
        print("  python3 sync_spotify_track_by_page_id.py 2e6e7361-6c27-8007-b3f6-e8f46b9e8233")
        print("  python3 sync_spotify_track_by_page_id.py 2e6e7361-6c27-8007-b3f6-e8f46b9e8233 4cPeIoEz3nKshMqLKgTAfw")
        sys.exit(1)
    
    notion_page_id = sys.argv[1]
    spotify_track_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    if spotify_track_id:
        spotify_track_id = extract_spotify_track_id(spotify_track_id)
    
    success = sync_track(notion_page_id, spotify_track_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
