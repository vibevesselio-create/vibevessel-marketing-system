#!/usr/bin/env python3
"""
Notion Database Property Cleanup Script
========================================
Removes deprecated/unused properties and merges duplicate property values.

Based on PROPERTY_SCHEMA_ANALYSIS.md (2026-01-16)

Usage:
    python notion_property_cleanup.py --dry-run          # Preview changes
    python notion_property_cleanup.py --remove           # Remove deprecated properties
    python notion_property_cleanup.py --merge            # Merge duplicate values
    python notion_property_cleanup.py --all              # Do everything
"""

import os
import sys
import argparse
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import requests

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID")
NOTION_VERSION = "2022-06-28"

if not NOTION_TOKEN:
    print("ERROR: NOTION_TOKEN not set")
    sys.exit(1)
if not TRACKS_DB_ID:
    print("ERROR: TRACKS_DB_ID not set")
    sys.exit(1)

# Format database ID with dashes
def format_db_id(db_id: str) -> str:
    db_id = db_id.replace("-", "")
    if len(db_id) == 32:
        return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"
    return db_id

TRACKS_DB_ID = format_db_id(TRACKS_DB_ID)

# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTIES TO REMOVE (No Data Source, No Value)
# ═══════════════════════════════════════════════════════════════════════════════

PROPERTIES_TO_REMOVE = [
    # Spectral Analysis Properties (NOT IMPLEMENTED)
    "Audio Spectral Centroid",
    "Audio Spectral Flatness",
    "Audio Spectral Rolloff",
    "Audio Harmonic Ratio",
    "Audio Percussive Ratio",
    "Audio THD Approximation",
    "Audio Estimated SNR (dB)",
    "Audio Zero Crossing Rate",
    "Audio Phase Coherence",
    "Audio Tempo Consistency",

    # Debug/Migration Properties (OBSOLETE)
    "Property Mapping",
    "Merge Confidence",
    "Fingerprint File Mapping Notes",
    "Audio Analysis Raw Data",
    "__last_synced_iso",

    # Redundant Formulas (COMPUTED CLIENT-SIDE) - Note: Cannot delete formulas via API
    # "SoundCloud-URL",  # Formula
    # "Spotify-ID*",     # Formula
    # "Traditional Key", # Formula

    # Ambiguous/Orphaned Properties (PURPOSE UNKNOWN)
    "Added By",
    "TrackID",
    "Group",
    "Kind",
    "Lifecycle",
    "Mix",
    "Source",
    "Snapshot ID",
]

# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTIES TO MERGE (Same Data, Multiple Properties)
# Format: (source_property, target_property, converter_function)
# ═══════════════════════════════════════════════════════════════════════════════

def ms_to_seconds(value):
    """Convert milliseconds to seconds."""
    if value is None:
        return None
    return value / 1000.0

def identity(value):
    """Return value unchanged."""
    return value

PROPERTIES_TO_MERGE = [
    # (source, target, converter)
    ("AverageBpm", "Tempo", identity),
    ("Duration (ms)", "Audio Duration (seconds)", ms_to_seconds),
    ("TotalTime", "Audio Duration (seconds)", identity),
    ("TrackNumber", "Track Number", identity),
    ("DiscNumber", "Disc Number", identity),
    ("Spotify Track ID", "Spotify ID", identity),
    ("Track Popularity", "Popularity", identity),
    ("SampleRate", "Audio Sample Rate", identity),
    ("Quality Score", "Audio Quality Score", identity),
    ("Loudness Level", "Audio LUFS Level", identity),
    ("Track ISRC", "ISRC", identity),
    ("Processed At", "Processing Timestamp", identity),
    ("DateAdded", "Added At", identity),
    ("Compression Mode", "Compression Mode Used", identity),
    ("Audio Compression Mode", "Compression Mode Used", identity),
    ("Audio Processing Status", "Audio Processing", identity),  # Multi-select merge
]

# ═══════════════════════════════════════════════════════════════════════════════
# NOTION API HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }

def notion_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a Notion API request with retry logic."""
    url = f"https://api.notion.com/v1{endpoint}"

    for attempt in range(3):
        try:
            if method == "get":
                resp = requests.get(url, headers=notion_headers(), timeout=30)
            elif method == "post":
                resp = requests.post(url, headers=notion_headers(), json=data, timeout=30)
            elif method == "patch":
                resp = requests.patch(url, headers=notion_headers(), json=data, timeout=30)
            elif method == "delete":
                resp = requests.delete(url, headers=notion_headers(), timeout=30)
            else:
                raise ValueError(f"Unknown method: {method}")

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if attempt < 2:
                print(f"  Request failed (attempt {attempt + 1}/3): {e}")
                time.sleep(2 ** attempt)
            else:
                raise

    return {}

def get_database_schema() -> Dict[str, Any]:
    """Retrieve database schema including all properties."""
    return notion_request("get", f"/databases/{TRACKS_DB_ID}")

def get_all_pages(limit: int = None) -> List[dict]:
    """Retrieve all pages from the database."""
    pages = []
    cursor = None

    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        result = notion_request("post", f"/databases/{TRACKS_DB_ID}/query", payload)
        pages.extend(result.get("results", []))

        if limit and len(pages) >= limit:
            return pages[:limit]

        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")

    return pages

def update_page(page_id: str, properties: dict) -> bool:
    """Update a page's properties."""
    try:
        notion_request("patch", f"/pages/{page_id}", {"properties": properties})
        return True
    except Exception as e:
        print(f"  Failed to update {page_id}: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# PROPERTY VALUE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def extract_property_value(prop: dict) -> Any:
    """Extract the actual value from a Notion property object."""
    if not prop:
        return None

    prop_type = prop.get("type")

    if prop_type == "number":
        return prop.get("number")
    elif prop_type == "rich_text":
        rt = prop.get("rich_text", [])
        return "".join(t.get("plain_text", "") for t in rt) if rt else None
    elif prop_type == "title":
        title = prop.get("title", [])
        return "".join(t.get("plain_text", "") for t in title) if title else None
    elif prop_type == "checkbox":
        return prop.get("checkbox")
    elif prop_type == "select":
        sel = prop.get("select")
        return sel.get("name") if sel else None
    elif prop_type == "multi_select":
        ms = prop.get("multi_select", [])
        return [item.get("name") for item in ms] if ms else []
    elif prop_type == "date":
        date = prop.get("date")
        return date.get("start") if date else None
    elif prop_type == "url":
        return prop.get("url")
    elif prop_type == "formula":
        formula = prop.get("formula", {})
        return formula.get(formula.get("type"))
    else:
        return None

def build_property_value(value: Any, target_type: str) -> dict:
    """Build a Notion property value object from a Python value."""
    if value is None:
        return None

    if target_type == "number":
        return {"number": float(value) if value else None}
    elif target_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value)[:2000]}}]} if value else {"rich_text": []}
    elif target_type == "checkbox":
        return {"checkbox": bool(value)}
    elif target_type == "select":
        return {"select": {"name": str(value)}} if value else {"select": None}
    elif target_type == "multi_select":
        if isinstance(value, list):
            return {"multi_select": [{"name": str(v)} for v in value if v]}
        else:
            return {"multi_select": [{"name": str(value)}]} if value else {"multi_select": []}
    elif target_type == "date":
        return {"date": {"start": str(value)}} if value else {"date": None}
    elif target_type == "url":
        return {"url": str(value) if value else None}
    else:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# CLEANUP OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_schema(schema: dict) -> dict:
    """Analyze the database schema and return property info."""
    properties = schema.get("properties", {})

    analysis = {
        "total": len(properties),
        "to_remove": [],
        "to_merge": [],
        "types": {},
    }

    for name, prop in properties.items():
        prop_type = prop.get("type")
        analysis["types"][name] = prop_type

        if name in PROPERTIES_TO_REMOVE:
            analysis["to_remove"].append((name, prop_type))

    for source, target, _ in PROPERTIES_TO_MERGE:
        if source in properties and target in properties:
            analysis["to_merge"].append((source, target))

    return analysis

def remove_properties(dry_run: bool = True, batch_size: int = 5) -> int:
    """Remove deprecated properties from the database schema by setting them to null."""
    print("\n" + "=" * 60)
    print("REMOVING DEPRECATED PROPERTIES")
    print("=" * 60)

    schema = get_database_schema()
    properties = schema.get("properties", {})

    # Build list of properties to remove
    to_remove = []
    for prop_name in PROPERTIES_TO_REMOVE:
        if prop_name in properties:
            prop_type = properties[prop_name].get("type")

            # Cannot remove certain property types via API
            if prop_type in ["formula", "rollup", "relation", "created_time", "created_by",
                            "last_edited_time", "last_edited_by", "title"]:
                print(f"  ⚠️  SKIP: {prop_name} ({prop_type}) - Cannot remove via API")
                continue

            to_remove.append((prop_name, prop_type))
        else:
            print(f"  ✓ Already removed: {prop_name}")

    if not to_remove:
        print("  No properties to remove.")
        return 0

    print(f"\nProperties to remove: {len(to_remove)}")
    for name, ptype in to_remove:
        print(f"  • {name} ({ptype})")

    if dry_run:
        print(f"\n[DRY-RUN] Would remove {len(to_remove)} properties")
        return len(to_remove)

    # Remove properties in batches to avoid API limits
    # To delete a property, set it to null in the properties object
    removed_count = 0

    for i in range(0, len(to_remove), batch_size):
        batch = to_remove[i:i + batch_size]

        # Build update payload - setting properties to null removes them
        update_properties = {}
        for prop_name, _ in batch:
            update_properties[prop_name] = None

        print(f"\n  Removing batch {i // batch_size + 1}: {[p[0] for p in batch]}")

        try:
            notion_request("patch", f"/databases/{TRACKS_DB_ID}", {
                "properties": update_properties
            })
            removed_count += len(batch)
            print(f"    ✅ Removed {len(batch)} properties")

            # Small delay between batches
            if i + batch_size < len(to_remove):
                time.sleep(1)

        except Exception as e:
            print(f"    ❌ Batch failed: {e}")
            # Try one at a time
            for prop_name, prop_type in batch:
                try:
                    print(f"    Retrying: {prop_name}...")
                    notion_request("patch", f"/databases/{TRACKS_DB_ID}", {
                        "properties": {prop_name: None}
                    })
                    removed_count += 1
                    print(f"      ✅ Removed {prop_name}")
                    time.sleep(0.5)
                except Exception as e2:
                    print(f"      ❌ Failed to remove {prop_name}: {e2}")

    print(f"\nTotal properties removed: {removed_count}/{len(to_remove)}")
    return removed_count

def merge_properties(dry_run: bool = True, limit: int = None) -> int:
    """Merge duplicate property values into canonical properties."""
    print("\n" + "=" * 60)
    print("MERGING DUPLICATE PROPERTIES")
    print("=" * 60)

    schema = get_database_schema()
    properties = schema.get("properties", {})

    # Build list of valid merges
    valid_merges = []
    for source, target, converter in PROPERTIES_TO_MERGE:
        if source in properties and target in properties:
            source_type = properties[source].get("type")
            target_type = properties[target].get("type")
            valid_merges.append((source, target, converter, source_type, target_type))
            print(f"  Will merge: {source} ({source_type}) → {target} ({target_type})")
        elif source in properties:
            print(f"  ⚠️  Target missing: {source} → {target}")
        # else source doesn't exist, skip silently

    if not valid_merges:
        print("  No properties to merge.")
        return 0

    print(f"\nFetching pages to process...")
    pages = get_all_pages(limit=limit)
    print(f"  Found {len(pages)} pages")

    merged_count = 0
    updated_pages = 0

    for i, page in enumerate(pages):
        page_id = page["id"]
        page_props = page.get("properties", {})

        updates = {}

        for source, target, converter, source_type, target_type in valid_merges:
            source_prop = page_props.get(source)
            target_prop = page_props.get(target)

            source_value = extract_property_value(source_prop)
            target_value = extract_property_value(target_prop)

            # Only merge if source has value and target is empty
            if source_value and not target_value:
                converted_value = converter(source_value)

                if converted_value is not None:
                    prop_update = build_property_value(converted_value, target_type)
                    if prop_update:
                        updates[target] = prop_update
                        merged_count += 1

        if updates:
            if dry_run:
                title = extract_property_value(page_props.get("Title")) or page_id[:8]
                print(f"  [DRY-RUN] Would update '{title}': {list(updates.keys())}")
            else:
                if update_page(page_id, updates):
                    updated_pages += 1

            # Progress indicator
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(pages)} pages...")

    print(f"\nMerged {merged_count} values across {updated_pages} pages")
    return merged_count

def show_analysis():
    """Show current schema analysis."""
    print("\n" + "=" * 60)
    print("DATABASE SCHEMA ANALYSIS")
    print("=" * 60)

    schema = get_database_schema()
    analysis = analyze_schema(schema)

    print(f"\nDatabase: {schema.get('title', [{}])[0].get('plain_text', 'Unknown')}")
    print(f"Total Properties: {analysis['total']}")

    print(f"\n--- Properties to REMOVE ({len(analysis['to_remove'])}) ---")
    for name, ptype in sorted(analysis["to_remove"]):
        print(f"  • {name} ({ptype})")

    print(f"\n--- Properties to MERGE ({len(analysis['to_merge'])}) ---")
    for source, target in analysis["to_merge"]:
        print(f"  • {source} → {target}")

    # Show properties NOT in either list
    all_props = set(analysis["types"].keys())
    remove_set = set(p[0] for p in analysis["to_remove"])
    merge_sources = set(p[0] for p in analysis["to_merge"])

    remaining = all_props - remove_set - merge_sources
    print(f"\n--- Properties to KEEP ({len(remaining)}) ---")
    for name in sorted(remaining):
        ptype = analysis["types"][name]
        print(f"  • {name} ({ptype})")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Notion database property cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--remove", action="store_true", help="Remove deprecated properties")
    parser.add_argument("--merge", action="store_true", help="Merge duplicate property values")
    parser.add_argument("--all", action="store_true", help="Do everything")
    parser.add_argument("--analyze", action="store_true", help="Show schema analysis")
    parser.add_argument("--limit", type=int, help="Limit number of pages to process")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if args.analyze or not any([args.remove, args.merge, args.all]):
        show_analysis()
        return

    dry_run = args.dry_run

    if dry_run:
        print("\n⚠️  DRY-RUN MODE - No changes will be made")
    elif not args.yes:
        print("\n🔥 LIVE MODE - Changes will be applied!")
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    else:
        print("\n🔥 LIVE MODE - Changes will be applied (--yes flag set)")

    if args.remove or args.all:
        remove_properties(dry_run=dry_run)

    if args.merge or args.all:
        merge_properties(dry_run=dry_run, limit=args.limit)

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
