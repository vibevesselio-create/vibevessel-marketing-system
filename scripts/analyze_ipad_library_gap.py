#!/usr/bin/env python3
"""
iPad Library Integration Gap Analysis

Analyzes the djay Pro database to identify discrepancies between
CloudKit sync records, local media items, and global (iPad) locations.

Author: Claude Code Agent
Date: 2026-01-03
Issue: BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Configuration
DJAY_DB_PATH = Path.home() / "Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db"
OUTPUT_DIR = Path.home() / "Projects/github-production/scripts/logs"
EXPORT_DIR = Path.home() / "Projects/github-production/djay_pro_export"

def analyze_database():
    """Main analysis function."""
    conn = sqlite3.connect(DJAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    analysis = {
        "timestamp": datetime.now().isoformat(),
        "database_path": str(DJAY_DB_PATH),
        "collections": {},
        "cloudkit_sync": {},
        "integration_gaps": [],
        "recommendations": []
    }

    # Get collection counts
    cursor.execute("""
        SELECT collection, COUNT(*) as count
        FROM database2
        GROUP BY collection
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        analysis["collections"][row["collection"]] = row["count"]

    # Analyze CloudKit records
    cursor.execute("SELECT COUNT(*) as total FROM cloudKit_record_cloudKit")
    analysis["cloudkit_sync"]["total_records"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM cloudKit_mapping_cloudKit")
    analysis["cloudkit_sync"]["mapping_records"] = cursor.fetchone()["total"]

    # Identify integration gaps
    user_data_count = analysis["collections"].get("mediaItemUserData", 0)
    media_items_count = analysis["collections"].get("mediaItems", 0)
    local_locations_count = analysis["collections"].get("localMediaItemLocations", 0)
    global_locations_count = analysis["collections"].get("globalMediaItemLocations", 0)
    analyzed_data_count = analysis["collections"].get("mediaItemAnalyzedData", 0)

    # Gap 1: User data without corresponding media items
    gap_userdata_vs_items = user_data_count - media_items_count
    if gap_userdata_vs_items > 0:
        analysis["integration_gaps"].append({
            "type": "userdata_without_mediaitem",
            "count": gap_userdata_vs_items,
            "description": f"{gap_userdata_vs_items} user data records have no corresponding media item",
            "impact": "User preferences/settings may exist for tracks not in library"
        })

    # Gap 2: Media items without local or global location
    total_locations = local_locations_count + global_locations_count
    gap_items_without_location = media_items_count - total_locations
    if gap_items_without_location > 0:
        analysis["integration_gaps"].append({
            "type": "mediaitem_without_location",
            "count": abs(gap_items_without_location),
            "description": f"{abs(gap_items_without_location)} media items may lack file location",
            "impact": "Tracks visible in library but file paths unknown"
        })

    # Gap 3: Media items without analysis data
    gap_without_analysis = media_items_count - analyzed_data_count
    if gap_without_analysis > 0:
        analysis["integration_gaps"].append({
            "type": "mediaitem_without_analysis",
            "count": gap_without_analysis,
            "description": f"{gap_without_analysis} media items lack BPM/key analysis",
            "impact": "Tracks may not have BPM/key detection completed"
        })

    # Gap 4: CloudKit mapping vs user data
    cloudkit_mapping_count = analysis["cloudkit_sync"]["mapping_records"]
    gap_cloudkit_vs_userdata = cloudkit_mapping_count - user_data_count
    if abs(gap_cloudkit_vs_userdata) > 0:
        analysis["integration_gaps"].append({
            "type": "cloudkit_sync_discrepancy",
            "count": abs(gap_cloudkit_vs_userdata),
            "description": f"CloudKit mapping ({cloudkit_mapping_count}) differs from user data ({user_data_count})",
            "impact": "Sync state may be inconsistent between devices"
        })

    # Sample global locations to understand iPad integration
    cursor.execute("""
        SELECT key, LENGTH(data) as data_size
        FROM database2
        WHERE collection = 'globalMediaItemLocations'
        LIMIT 10
    """)
    sample_global = []
    for row in cursor.fetchall():
        sample_global.append({"key": row["key"], "data_size": row["data_size"]})
    analysis["cloudkit_sync"]["sample_global_locations"] = sample_global

    # Recommendations
    analysis["recommendations"] = [
        {
            "priority": "P0",
            "action": "Map CloudKit records to media items",
            "details": "Create lookup table joining cloudKit_mapping_cloudKit.rowid to database2 rows"
        },
        {
            "priority": "P0",
            "action": "Export global locations for iPad path analysis",
            "details": "Decode globalMediaItemLocations data blobs to extract iPad file paths"
        },
        {
            "priority": "P1",
            "action": "Run BPM/key analysis on missing tracks",
            "details": f"{gap_without_analysis} tracks need analysis completion"
        },
        {
            "priority": "P1",
            "action": "Cross-reference Notion Tracks DB with djay library",
            "details": "Identify tracks in djay but not in Notion for sync"
        }
    ]

    # Summary stats
    analysis["summary"] = {
        "total_cloudkit_synced": analysis["cloudkit_sync"]["total_records"],
        "total_media_items": media_items_count,
        "total_local_files": local_locations_count,
        "total_global_ipad_files": global_locations_count,
        "total_analyzed": analyzed_data_count,
        "total_gaps_identified": len(analysis["integration_gaps"]),
        "ipad_coverage_percent": round((global_locations_count / max(media_items_count, 1)) * 100, 2)
    }

    conn.close()
    return analysis

def main():
    """Execute analysis and save results."""
    print("Analyzing djay Pro iPad Library Integration...")

    if not DJAY_DB_PATH.exists():
        print(f"ERROR: Database not found at {DJAY_DB_PATH}")
        return

    analysis = analyze_database()

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"ipad_library_gap_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"\nAnalysis complete. Results saved to: {output_file}")
    print("\n--- SUMMARY ---")
    print(f"CloudKit Synced Records: {analysis['summary']['total_cloudkit_synced']}")
    print(f"Total Media Items: {analysis['summary']['total_media_items']}")
    print(f"Local Files: {analysis['summary']['total_local_files']}")
    print(f"iPad/Global Files: {analysis['summary']['total_global_ipad_files']}")
    print(f"Analyzed (BPM/Key): {analysis['summary']['total_analyzed']}")
    print(f"iPad Coverage: {analysis['summary']['ipad_coverage_percent']}%")
    print(f"Gaps Identified: {analysis['summary']['total_gaps_identified']}")

    print("\n--- INTEGRATION GAPS ---")
    for gap in analysis['integration_gaps']:
        print(f"[{gap['type']}] {gap['count']} items - {gap['description']}")

    print("\n--- RECOMMENDATIONS ---")
    for rec in analysis['recommendations']:
        print(f"[{rec['priority']}] {rec['action']}")

    return analysis

if __name__ == "__main__":
    main()
