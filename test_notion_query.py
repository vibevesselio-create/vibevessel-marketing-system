#!/usr/bin/env python3
"""Test script for notion_track_queries."""
import sys
from datetime import datetime
import json

from scripts.notion_track_queries import query_tracks_for_processing

if __name__ == "__main__":
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Test timestamp: {timestamp}")
    print("Querying tracks from Notion...")

    try:
        tracks = query_tracks_for_processing(limit=5)
        result = {
            "timestamp": timestamp,
            "count": len(tracks),
            "tracks": []
        }

        # Sample a few tracks to show their properties
        for track in tracks[:3]:
            props = track.get("properties", {})
            track_info = {
                "id": track.get("id"),
                "has_title": bool(props.get("Title") or props.get("title")),
                "has_artist": bool(props.get("Artist Name") or props.get("Artist")),
                "has_fingerprint": bool(props.get("Fingerprint") or props.get("fingerprint")),
                "dl_value": None
            }
            dl_prop = props.get("DL") or props.get("Downloaded")
            if dl_prop and dl_prop.get("type") == "checkbox":
                track_info["dl_value"] = dl_prop.get("checkbox", False)
            result["tracks"].append(track_info)

        print(f"\nFound {len(tracks)} tracks")
        print(json.dumps(result, indent=2))
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
