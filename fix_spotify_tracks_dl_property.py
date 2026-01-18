#!/usr/bin/env python3
"""
Remediation Script: Fix Existing Spotify Tracks Missing DL=False Property

This script identifies and updates existing Spotify tracks in Notion that don't have 
DL=False set, ensuring they are eligible for download processing.

Issue: 2e3e7361-6c27-818d-9a9b-c5508f52d916
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
    NOTION_AVAILABLE = True
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    NOTION_AVAILABLE = False
    sys.exit(1)

# Database ID
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")

def safe_get_property(page: dict, property_name: str, property_type: str = None):
    """Safely extract property value from Notion page."""
    try:
        properties = page.get("properties", {})
        if not properties:
            return None
        
        prop = properties.get(property_name)
        if not prop:
            return None
        
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            return None
        
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "checkbox":
            return prop.get("checkbox", False)
        
        elif actual_type == "url":
            return prop.get("url")
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def fix_spotify_tracks_dl_property(client: Client, dry_run: bool = True):
    """Find and fix Spotify tracks missing DL=False property."""
    print("\n" + "="*80)
    print("Spotify Tracks DL Property Remediation")
    print("="*80)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}\n")
    
    # Query for Spotify tracks
    # Find tracks with Spotify ID that might be missing DL=False
    filter_params = {
        "and": [
            {"property": "Spotify ID", "rich_text": {"is_not_empty": True}},
            {"property": "SoundCloud URL", "url": {"is_empty": True}},
            {"property": "SoundCloud URL", "rich_text": {"is_empty": True}},
        ]
    }
    
    try:
        response = client.databases.query(
            database_id=TRACKS_DB_ID,
            filter=filter_params,
            page_size=100
        )
        tracks = response.get("results", [])
        
        print(f"Found {len(tracks)} Spotify tracks (no SoundCloud URL)\n")
        
        tracks_to_fix = []
        
        for track in tracks:
            track_id = track.get("id")
            title = safe_get_property(track, "Title", "title") or "Untitled"
            spotify_id = safe_get_property(track, "Spotify ID", "rich_text")
            dl_value = safe_get_property(track, "DL", "checkbox")
            downloaded_value = safe_get_property(track, "Downloaded", "checkbox")
            
            # Check if DL or Downloaded property exists and is not False
            needs_fix = False
            
            # Check DL property
            if dl_value is None:
                # Property doesn't exist or is None - needs to be set
                needs_fix = True
            elif dl_value is True:
                # Property is True but should be False for unprocessed tracks
                needs_fix = True
            
            # Also check Downloaded property if it exists
            if downloaded_value is True:
                needs_fix = True
            
            # Also check if file paths exist - if they do, DL should be True, so skip
            m4a_path = safe_get_property(track, "M4A File Path", "rich_text")
            wav_path = safe_get_property(track, "WAV File Path", "rich_text")
            aiff_path = safe_get_property(track, "AIFF File Path", "rich_text")
            
            has_files = any([m4a_path, wav_path, aiff_path])
            
            if needs_fix and not has_files:
                tracks_to_fix.append({
                    "id": track_id,
                    "title": title,
                    "spotify_id": spotify_id,
                    "dl_value": dl_value,
                    "downloaded_value": downloaded_value,
                    "has_files": has_files
                })
        
        print(f"Found {len(tracks_to_fix)} tracks needing DL=False fix\n")
        
        if not tracks_to_fix:
            print("✅ All Spotify tracks already have correct DL property values")
            return
        
        # Show tracks that need fixing
        print("Tracks to fix:")
        for i, track in enumerate(tracks_to_fix[:10], 1):  # Show first 10
            print(f"  {i}. {track['title']} (ID: {track['id'][:8]}...)")
            print(f"     Spotify ID: {track['spotify_id']}")
            print(f"     Current DL: {track['dl_value']}, Downloaded: {track['downloaded_value']}")
        
        if len(tracks_to_fix) > 10:
            print(f"  ... and {len(tracks_to_fix) - 10} more tracks")
        
        if dry_run:
            print(f"\n⚠️  DRY RUN: Would update {len(tracks_to_fix)} tracks with DL=False")
            print("Run with --live to apply changes")
            return
        
        # Apply fixes
        print(f"\n🔄 Updating {len(tracks_to_fix)} tracks...")
        updated = 0
        failed = 0
        
        for track in tracks_to_fix:
            try:
                # Get database schema to check which properties exist
                db_info = client.databases.retrieve(database_id=TRACKS_DB_ID)
                db_props = db_info.get("properties", {})
                
                properties = {}
                
                # Set DL property if it exists
                if "DL" in db_props and db_props["DL"].get("type") == "checkbox":
                    properties["DL"] = {"checkbox": False}
                
                # Set Downloaded property if it exists
                if "Downloaded" in db_props and db_props["Downloaded"].get("type") == "checkbox":
                    properties["Downloaded"] = {"checkbox": False}
                
                if properties:
                    client.pages.update(
                        page_id=track["id"],
                        properties=properties
                    )
                    updated += 1
                    print(f"  ✅ Updated: {track['title']}")
                else:
                    print(f"  ⚠️  Skipped: {track['title']} (DL/Downloaded property not found in database)")
                    failed += 1
                    
            except Exception as e:
                print(f"  ❌ Failed to update {track['title']}: {e}")
                failed += 1
        
        print(f"\n✅ Updated {updated} tracks")
        if failed > 0:
            print(f"⚠️  Failed to update {failed} tracks")
            
    except Exception as e:
        print(f"❌ Error querying tracks: {e}")
        import traceback
        traceback.print_exc()
        return

def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix existing Spotify tracks missing DL=False property")
    parser.add_argument("--live", action="store_true", help="Apply changes (default is dry run)")
    args = parser.parse_args()
    
    if not NOTION_AVAILABLE:
        print("Notion client not available")
        sys.exit(1)
    
    try:
        token = get_notion_token()
        if not token:
            print("❌ Error: Could not get Notion token")
            sys.exit(1)
        
        client = Client(auth=token)
    except Exception as e:
        print(f"❌ Error initializing Notion client: {e}")
        sys.exit(1)
    
    fix_spotify_tracks_dl_property(client, dry_run=not args.live)

if __name__ == "__main__":
    main()