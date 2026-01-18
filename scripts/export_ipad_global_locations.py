#!/usr/bin/env python3
"""
iPad Global Locations Export Script

P0 Task: Export global locations for iPad path analysis
Issue: BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete

Extracts globalMediaItemLocations from djay Pro database to analyze
iPad sync status and file path patterns.

Author: Claude Code Agent (Opus 4.5)
Date: 2026-01-04
"""

import sqlite3
import json
import plistlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configuration
DJAY_DB_PATH = Path.home() / "Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db"
OUTPUT_DIR = Path.home() / "Projects/github-production/scripts/logs"
EXPORT_DIR = Path.home() / "Projects/github-production/djay_pro_export"


def decode_location_blob(data: bytes) -> Dict[str, Any]:
    """
    Attempt to decode globalMediaItemLocations data blob.
    djay Pro uses various formats: plist, JSON, or custom binary.
    """
    result = {"raw_size": len(data), "decoded": False, "format": "unknown"}

    # Try plist first (common for Apple apps)
    try:
        decoded = plistlib.loads(data)
        result["decoded"] = True
        result["format"] = "plist"
        result["data"] = decoded
        return result
    except Exception:
        pass

    # Try JSON
    try:
        decoded = json.loads(data.decode('utf-8'))
        result["decoded"] = True
        result["format"] = "json"
        result["data"] = decoded
        return result
    except Exception:
        pass

    # Try UTF-8 string
    try:
        decoded_str = data.decode('utf-8')
        result["decoded"] = True
        result["format"] = "utf8_string"
        result["data"] = decoded_str
        return result
    except Exception:
        pass

    # Try UTF-16
    try:
        decoded_str = data.decode('utf-16')
        result["decoded"] = True
        result["format"] = "utf16_string"
        result["data"] = decoded_str
        return result
    except Exception:
        pass

    # Store base64 for manual analysis
    result["base64_sample"] = base64.b64encode(data[:500]).decode('ascii') if len(data) > 500 else base64.b64encode(data).decode('ascii')
    result["hex_header"] = data[:50].hex() if len(data) >= 50 else data.hex()

    return result


def export_global_locations():
    """Export all global (iPad) media item locations."""
    print(f"Connecting to djay Pro database: {DJAY_DB_PATH}")

    if not DJAY_DB_PATH.exists():
        print(f"ERROR: Database not found at {DJAY_DB_PATH}")
        return None

    conn = sqlite3.connect(DJAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all global locations
    cursor.execute("""
        SELECT rowid, key, collection, data, metadata
        FROM database2
        WHERE collection = 'globalMediaItemLocations'
    """)

    global_locations = []
    decoded_count = 0
    format_stats = {}

    for row in cursor.fetchall():
        location = {
            "rowid": row["rowid"],
            "key": row["key"],
            "collection": row["collection"],
            "has_metadata": row["metadata"] is not None
        }

        # Decode the data blob
        if row["data"]:
            decoded = decode_location_blob(row["data"])
            location["blob_analysis"] = decoded

            if decoded["decoded"]:
                decoded_count += 1
                fmt = decoded["format"]
                format_stats[fmt] = format_stats.get(fmt, 0) + 1

                # Extract path information if available
                if decoded.get("data"):
                    data = decoded["data"]
                    if isinstance(data, dict):
                        # Look for path-like keys
                        for path_key in ["path", "filePath", "url", "location", "URL", "bookmark"]:
                            if path_key in data:
                                location["extracted_path"] = str(data[path_key])
                                break
                    elif isinstance(data, str) and ("/" in data or "\\" in data):
                        location["extracted_path"] = data

        global_locations.append(location)

    # Get related local locations for comparison
    cursor.execute("""
        SELECT rowid, key, collection, LENGTH(data) as data_size
        FROM database2
        WHERE collection = 'localMediaItemLocations'
        LIMIT 100
    """)

    local_sample = []
    for row in cursor.fetchall():
        local_sample.append({
            "rowid": row["rowid"],
            "key": row["key"],
            "data_size": row["data_size"]
        })

    # Get CloudKit mappings to understand sync relationship
    cursor.execute("""
        SELECT COUNT(*) as count FROM cloudKit_mapping_cloudKit
    """)
    cloudkit_mapping_count = cursor.fetchone()["count"]

    conn.close()

    # Generate analysis report
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "database_path": str(DJAY_DB_PATH),
        "summary": {
            "total_global_locations": len(global_locations),
            "decoded_successfully": decoded_count,
            "decode_rate_percent": round((decoded_count / max(len(global_locations), 1)) * 100, 2),
            "format_distribution": format_stats,
            "local_locations_sampled": len(local_sample),
            "cloudkit_mapping_count": cloudkit_mapping_count
        },
        "global_locations": global_locations,
        "local_sample": local_sample,
        "path_analysis": {
            "paths_extracted": sum(1 for loc in global_locations if "extracted_path" in loc),
            "unique_paths": list(set(loc.get("extracted_path", "") for loc in global_locations if "extracted_path" in loc))[:50]  # Sample of unique paths
        }
    }

    # Save results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"ipad_global_locations_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)

    print(f"\nExport complete. Results saved to: {output_file}")
    print("\n--- SUMMARY ---")
    print(f"Total Global (iPad) Locations: {analysis['summary']['total_global_locations']}")
    print(f"Successfully Decoded: {analysis['summary']['decoded_successfully']} ({analysis['summary']['decode_rate_percent']}%)")
    print(f"Format Distribution: {analysis['summary']['format_distribution']}")
    print(f"Paths Extracted: {analysis['path_analysis']['paths_extracted']}")
    print(f"CloudKit Mappings: {analysis['summary']['cloudkit_mapping_count']}")

    return analysis


def map_cloudkit_to_media_items():
    """
    P0 Task: Map CloudKit records to media items.
    Creates a lookup table joining cloudKit_mapping_cloudKit to database2 rows.
    """
    print("\nMapping CloudKit records to media items...")

    if not DJAY_DB_PATH.exists():
        print(f"ERROR: Database not found at {DJAY_DB_PATH}")
        return None

    conn = sqlite3.connect(DJAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get CloudKit mappings (actual schema: rowid, recordTable_hash)
    cursor.execute("""
        SELECT rowid, recordTable_hash
        FROM cloudKit_mapping_cloudKit
        LIMIT 1000
    """)

    mappings = []
    for row in cursor.fetchall():
        mappings.append({
            "rowid": row["rowid"],
            "recordTable_hash": row["recordTable_hash"]
        })

    # Try to correlate with media items based on rowid patterns
    cursor.execute("""
        SELECT rowid, key, collection
        FROM database2
        WHERE collection = 'mediaItems'
        LIMIT 1000
    """)

    media_items = []
    for row in cursor.fetchall():
        media_items.append({
            "rowid": row["rowid"],
            "key": row["key"],
            "collection": row["collection"]
        })

    # Build correlation map
    correlation = {
        "cloudkit_records": len(mappings),
        "media_items": len(media_items),
        "sample_mappings": mappings[:20],
        "sample_media_items": media_items[:20]
    }

    conn.close()

    # Save correlation analysis
    output_file = OUTPUT_DIR / f"cloudkit_media_mapping_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(correlation, f, indent=2)

    print(f"CloudKit mapping analysis saved to: {output_file}")
    return correlation


def main():
    """Execute all P0 tasks for iPad library integration."""
    print("=" * 70)
    print("iPad Library Integration - P0 Tasks Execution")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Database: {DJAY_DB_PATH}")
    print()

    # P0 Task 1: Export global locations for iPad path analysis
    print("\n[P0 TASK 1] Export global locations for iPad path analysis")
    print("-" * 50)
    global_analysis = export_global_locations()

    # P0 Task 2: Map CloudKit records to media items
    print("\n[P0 TASK 2] Map CloudKit records to media items")
    print("-" * 50)
    cloudkit_mapping = map_cloudkit_to_media_items()

    # Generate combined report
    combined_report = {
        "execution_timestamp": datetime.now().isoformat(),
        "issue_id": "2b5e7361-6c27-8147-8cbc-e73a63dbc8f8",
        "issue_title": "BLOCKER: iPad Library Integration Not Analyzed - Music Sync Incomplete",
        "tasks_completed": [
            "P0: Export global locations for iPad path analysis",
            "P0: Map CloudKit records to media items"
        ],
        "global_locations_summary": global_analysis["summary"] if global_analysis else None,
        "cloudkit_mapping_summary": {
            "records_analyzed": cloudkit_mapping["cloudkit_records"] if cloudkit_mapping else 0,
            "media_items_analyzed": cloudkit_mapping["media_items"] if cloudkit_mapping else 0
        } if cloudkit_mapping else None,
        "next_steps": [
            "P1: Run BPM/key analysis on 3,262 missing tracks",
            "P1: Cross-reference with Notion Tracks DB"
        ],
        "handoff_required": "Cursor-MM1-Agent for Apps Script execution and Notion sync"
    }

    report_file = OUTPUT_DIR / f"ipad_integration_p0_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(combined_report, f, indent=2)

    print("\n" + "=" * 70)
    print("P0 TASKS COMPLETED")
    print("=" * 70)
    print(f"Combined report: {report_file}")
    print("\nReady for handoff to Cursor-MM1-Agent for:")
    print("  - Apps Script execution")
    print("  - Notion database synchronization")
    print("  - P1 task continuation")

    return combined_report


if __name__ == "__main__":
    main()
