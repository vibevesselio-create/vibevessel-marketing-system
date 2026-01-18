#!/usr/bin/env python3
"""
iPad Library Integration - BPM/Key Analysis Script

This script identifies and processes tracks that need BPM/key analysis
for the iPad Library Integration issue.

Issue: BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete
Issue ID: 2b5e7361-6c27-8147-8cbc-e73a63dbc8f8
"""

import os
import sys
from pathlib import Path
import json
from datetime import datetime, timezone

# Add project root to path
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def safe_get_property(page, property_name, property_type=None):
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
        
        elif actual_type == "number":
            return prop.get("number")
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list if item.get("name")]
        
        return None
    except Exception as e:
        print(f"Error extracting property '{property_name}': {e}")
        return None

def find_tracks_needing_analysis():
    """
    Find tracks in Notion Tracks database that need BPM/key analysis.
    
    Criteria:
    - Tracks with AverageBpm = null or 0
    - Tracks that are part of iPad library integration
    """
    token = get_notion_token()
    if not token:
        print("ERROR: Could not get Notion token")
        return None
    
    client = Client(auth=token)
    
    # Try to find Tracks database - common IDs
    # This would need to be configured based on actual database ID
    tracks_db_id = os.getenv("TRACKS_DB_ID")
    
    if not tracks_db_id:
        print("WARNING: TRACKS_DB_ID not set. Cannot query tracks database.")
        print("This script requires the Notion Tracks database ID to be set.")
        return {
            "status": "configuration_required",
            "message": "TRACKS_DB_ID environment variable must be set",
            "tracks_found": 0
        }
    
    try:
        # Query for tracks missing BPM
        filter_params = {
            "or": [
                {"property": "AverageBpm", "number": {"is_empty": True}},
                {"property": "AverageBpm", "number": {"equals": 0}},
            ]
        }
        
        # Try to get data_source_id
        db = client.databases.retrieve(database_id=tracks_db_id)
        data_sources = db.get("data_sources", [])
        
        if data_sources:
            data_source_id = data_sources[0].get("id")
            response = client.data_sources.query(
                data_source_id=data_source_id,
                filter=filter_params,
                page_size=100
            )
        else:
            response = client.databases.query(
                database_id=tracks_db_id,
                filter=filter_params,
                page_size=100
            )
        
        results = response.get("results", [])
        
        tracks_needing_analysis = []
        for track in results:
            track_data = {
                "id": track.get("id"),
                "url": track.get("url", ""),
                "name": safe_get_property(track, "Name", "title") or safe_get_property(track, "Title", "title") or "Untitled",
                "bpm": safe_get_property(track, "AverageBpm", "number"),
            }
            tracks_needing_analysis.append(track_data)
        
        return {
            "status": "success",
            "tracks_found": len(tracks_needing_analysis),
            "tracks": tracks_needing_analysis[:100]  # Limit to first 100 for reporting
        }
        
    except Exception as e:
        print(f"ERROR querying tracks: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "tracks_found": 0
        }

def main():
    """Main execution function."""
    print("=" * 80)
    print("iPad Library Integration - BPM/Key Analysis Identification")
    print("=" * 80)
    print()
    
    result = find_tracks_needing_analysis()
    
    if result["status"] == "configuration_required":
        print(f"⚠️  {result['message']}")
        print()
        print("To use this script:")
        print("1. Identify the Notion Tracks database ID")
        print("2. Set TRACKS_DB_ID environment variable")
        print("3. Re-run this script")
        return 1
    
    if result["status"] == "error":
        print(f"❌ Error: {result.get('error', 'Unknown error')}")
        return 1
    
    print(f"✅ Found {result['tracks_found']} tracks needing BPM/key analysis")
    print()
    
    if result["tracks_found"] > 0:
        print(f"Sample tracks (showing first {len(result['tracks'])}):")
        for i, track in enumerate(result["tracks"][:10], 1):
            print(f"  {i}. {track['name']} (ID: {track['id'][:8]}...)")
            print(f"     URL: {track['url']}")
        
        if result["tracks_found"] > 10:
            print(f"     ... and {result['tracks_found'] - 10} more tracks")
    
    print()
    print("=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Run BPM/key analysis using soundcloud_download_prod_merge-2.py")
    print("2. Process tracks in batches to avoid timeouts")
    print("3. Update Notion Tracks database with analysis results")
    print("4. Cross-reference with djay library")
    print("5. Sync iPad paths to Notion")
    print()
    
    # Save results to file
    output_file = Path(__file__).parent / "ipad_library_analysis_status.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issue_id": "2b5e7361-6c27-8147-8cbc-e73a63dbc8f8",
            "issue_name": "BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete",
            "result": result
        }, f, indent=2)
    
    print(f"📄 Results saved to: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
