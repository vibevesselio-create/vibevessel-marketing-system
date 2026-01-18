#!/usr/bin/env python3
"""
Update Notion Music Directories Database with Final Deduplication Status
Phase 6.2: Update Notion Documentation
"""

import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config
from shared_core.notion.token_manager import get_notion_client

def update_eagle_library_status(notion, db_id: str, eagle_page_id: str, duplicates_removed: int, space_recovered_mb: float):
    """Update Eagle library entry in Notion with deduplication status."""
    try:
        # Get current page to see available properties
        page = notion.pages.retrieve(page_id=eagle_page_id)
        props = page.get("properties", {})
        
        # Build update properties
        update_props = {}
        
        # Last Deduplication date
        if "Last Deduplication" in props or "Last Dedup" in props:
            prop_name = "Last Deduplication" if "Last Deduplication" in props else "Last Dedup"
            update_props[prop_name] = {
                "date": {"start": datetime.now().isoformat()}
            }
        
        # Duplicates Removed count
        if "Duplicates Removed" in props:
            update_props["Duplicates Removed"] = {
                "number": duplicates_removed
            }
        
        # Space Recovered
        if "Space Recovered" in props or "Space Recovered (MB)" in props:
            prop_name = "Space Recovered" if "Space Recovered" in props else "Space Recovered (MB)"
            update_props[prop_name] = {
                "number": int(space_recovered_mb)
            }
        
        # Status
        if "Status" in props:
            update_props["Status"] = {
                "select": {"name": "Deduplicated"}
            }
        
        if update_props:
            notion.pages.update(page_id=eagle_page_id, properties=update_props)
            print(f"✓ Updated Eagle library page: {eagle_page_id}")
            print(f"  Updated properties: {list(update_props.keys())}")
            return True
        else:
            print("⚠️  No matching properties found for update")
            print(f"  Available properties: {list(props.keys())}")
            return False
            
    except Exception as e:
        print(f"✗ Error updating Notion page: {e}")
        return False

def main():
    """Main execution"""
    print("=" * 80)
    print("PHASE 6.2: UPDATE NOTION DOCUMENTATION")
    print("=" * 80)
    
    # Load configuration
    load_unified_env()
    config = get_unified_config()
    notion = get_notion_client()
    
    # Get database ID
    db_id = config.get("music_directories_db_id") or os.getenv("MUSIC_DIRECTORIES_DB_ID", "")
    if not db_id:
        # Search for it
        results = notion.search(filter={"property": "object", "value": "database"}, query="Music Directories")
        for result in results.get("results", []):
            title_parts = result.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_parts) if title_parts else ""
            if "music" in title.lower() and "director" in title.lower():
                db_id = result.get("id", "")
                break
    
    if not db_id:
        print("✗ Music Directories database not found")
        sys.exit(1)
    
    # Find Eagle library entry
    eagle_library_path = config.get("eagle_library_path") or "/Volumes/VIBES/Music-Library-2.library"
    
    query_result = notion.databases.query(
        database_id=db_id,
        filter={
            "or": [
                {"property": "Path", "url": {"contains": "Music-Library-2.library"}},
                {"property": "Path", "rich_text": {"contains": "Music-Library-2.library"}},
                {"property": "Name", "title": {"contains": "Eagle"}},
                {"property": "Type", "select": {"equals": "Eagle Library"}}
            ]
        }
    )
    
    eagle_page_id = None
    for page in query_result.get("results", []):
        props = page.get("properties", {})
        # Check path
        path = None
        for prop_name in ["Path", "Directory", "Location"]:
            if prop_name in props:
                prop = props[prop_name]
                if prop.get("type") == "url":
                    path = prop.get("url", "")
                elif prop.get("type") == "rich_text":
                    path = "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
                if path and ("Music-Library" in path or ".library" in path):
                    eagle_page_id = page.get("id")
                    break
        if eagle_page_id:
            break
    
    if not eagle_page_id:
        print("⚠️  Eagle library entry not found in Notion database")
        print("   Creating new entry...")
        # Create entry would go here if needed
        sys.exit(1)
    
    # Update with deduplication results
    duplicates_removed = 5803  # From live execution
    space_recovered_mb = 188307.70  # From live execution report
    
    print(f"\nUpdating Eagle library entry: {eagle_page_id}")
    print(f"  Duplicates Removed: {duplicates_removed}")
    print(f"  Space Recovered: {space_recovered_mb:.2f} MB ({space_recovered_mb/1024:.2f} GB)")
    
    success = update_eagle_library_status(notion, db_id, eagle_page_id, duplicates_removed, space_recovered_mb)
    
    if success:
        print("\n✓ Notion documentation updated successfully")
    else:
        print("\n⚠️  Notion update had issues (may need manual update)")

if __name__ == "__main__":
    main()
