#!/usr/bin/env python3
"""
Verify Eagle Libraries are documented in Notion Music Directories database.
Automatically creates database and properties if missing.
Creates entries for missing libraries.
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from unified_config import load_unified_env, get_unified_config
    from shared_core.notion.token_manager import get_notion_client
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}", file=sys.stderr)
    sys.exit(1)

# Default library paths
DEFAULT_PREVIOUS_LIBRARY = "/Volumes/OF-CP2019-2025/Music Library-2.library"
DEFAULT_CURRENT_LIBRARY = "/Volumes/VIBES/Music Library-2.library"

# Required database properties
REQUIRED_PROPERTIES = {
    "Name": {
        "title": {}
    },
    "Path": {
        "rich_text": {}
    },
    "Status": {
        "select": {
            "options": [
                {"name": "Active", "color": "green"},
                {"name": "Inactive", "color": "gray"},
                {"name": "Archived", "color": "red"}
            ]
        }
    },
    "Type": {
        "select": {
            "options": [
                {"name": "Downloads", "color": "blue"},
                {"name": "Playlists", "color": "purple"},
                {"name": "Djay-Pro-Auto-Import", "color": "orange"},
                {"name": "Apple-Music-Auto-Add", "color": "pink"},
                {"name": "Eagle Library", "color": "yellow"},
                {"name": "Music Directory", "color": "default"},
                {"name": "Backup", "color": "brown"}
            ]
        }
    },
    "Volume": {
        "rich_text": {}
    },
    "Last Verified": {
        "date": {}
    },
    "Library Name": {
        "rich_text": {}
    },
    "Role": {
        "select": {
            "options": [
                {"name": "Previous", "color": "orange"},
                {"name": "Current", "color": "green"},
                {"name": "Archive", "color": "gray"}
            ]
        }
    }
}


def find_eagle_libraries() -> List[str]:
    """Scan filesystem for Eagle library directories."""
    libraries = []
    scan_paths = [
        Path('/Volumes'),
        Path('/Users/brianhellemn/Music'),
    ]
    
    for base_path in scan_paths:
        if not base_path.exists():
            continue
        try:
            for root, dirs, files in os.walk(base_path):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                # Check if this is an Eagle library
                library_json = Path(root) / 'library.json'
                if library_json.exists() or root.endswith('.library'):
                    libraries.append(root)
        except (PermissionError, OSError) as e:
            print(f"WARNING: Could not scan {base_path}: {e}", file=sys.stderr)
    
    return sorted(set(libraries))


def get_documented_libraries(notion: Any, db_id: str) -> List[Dict[str, Any]]:
    """Query Notion for documented Eagle libraries."""
    if not db_id:
        return []
    
    try:
        response = notion.databases.query(
            database_id=db_id,
            filter={
                "or": [
                    {"property": "Type", "select": {"equals": "Eagle Library"}},
                    {"property": "Name", "title": {"contains": "Eagle"}},
                    {"property": "Path", "rich_text": {"contains": ".library"}},
                    {"property": "Path", "url": {"contains": ".library"}}
                ]
            }
        )
        
        documented = []
        for page in response.get("results", []):
            props = page.get("properties", {})
            name = ""
            path = ""
            
            # Get name
            name_prop = props.get("Name") or props.get("Title")
            if name_prop:
                title_list = name_prop.get("title", [])
                if title_list:
                    name = title_list[0].get("plain_text", "")
            
            # Get path
            path_prop = props.get("Path") or props.get("Directory") or props.get("Folder Path")
            if path_prop:
                if path_prop.get("type") == "url":
                    path = path_prop.get("url", "")
                elif path_prop.get("type") == "rich_text":
                    rich_text = path_prop.get("rich_text", [])
                    if rich_text:
                        path = rich_text[0].get("plain_text", "")
            
            documented.append({
                "page_id": page.get("id"),
                "name": name,
                "path": path,
                "properties": props
            })
        
        return documented
    except Exception as e:
        print(f"ERROR: Failed to query Notion database: {e}", file=sys.stderr)
        return []


def get_or_create_database(notion: Any, db_id: Optional[str] = None) -> Optional[str]:
    """Get existing database or create it if it doesn't exist."""
    # If db_id provided, try to retrieve it
    if db_id:
        try:
            db = notion.databases.retrieve(database_id=db_id)
            print(f"✅ Found existing Music Directories database: {db_id}")
            return db_id
        except Exception as e:
            print(f"⚠️  Database ID provided but not accessible: {e}")
            print("   Will attempt to create new database...")
    
    # Try to find existing database by searching
    try:
        search_results = notion.search(
            query="Music Directories",
            filter={"property": "object", "value": "database"},
            page_size=5
        )
        for result in search_results.get("results", []):
            if result.get("object") == "database":
                title = result.get("title", [])
                if title and any("music" in t.get("plain_text", "").lower() and "director" in t.get("plain_text", "").lower() for t in title):
                    found_id = result.get("id")
                    print(f"✅ Found existing Music Directories database: {found_id}")
                    return found_id
    except Exception as e:
        print(f"⚠️  Could not search for existing database: {e}")
    
    # Create new database
    print("🔨 Creating new Music Directories database...")
    
    # Find a suitable parent page
    parent_page_id = None
    try:
        # Try to find workspace or use a known page
        search_results = notion.search(
            query="Music",
            filter={"property": "object", "value": "page"},
            page_size=1
        )
        if search_results.get("results"):
            parent_page_id = search_results["results"][0]["id"]
            print(f"   Using parent page: {parent_page_id[:8]}...")
    except Exception as e:
        print(f"⚠️  Could not find parent page: {e}")
        print("   Attempting to create database without explicit parent...")
    
    try:
        if parent_page_id:
            parent = {"type": "page_id", "page_id": parent_page_id}
        else:
            # Try to get workspace root (might not work depending on permissions)
            parent = {"type": "workspace", "workspace": True}
        
        response = notion.databases.create(
            parent=parent,
            title=[{"type": "text", "text": {"content": "Music Directories"}}],
            properties=REQUIRED_PROPERTIES
        )
        
        new_db_id = response["id"]
        print(f"✅ Created Music Directories database: {new_db_id}")
        print(f"   URL: {response.get('url', 'N/A')}")
        return new_db_id
        
    except Exception as e:
        print(f"❌ Failed to create database: {e}", file=sys.stderr)
        print(f"   Please create the database manually in Notion and set MUSIC_DIRECTORIES_DB_ID", file=sys.stderr)
        return None


def ensure_database_properties(notion: Any, db_id: str) -> bool:
    """Ensure all required properties exist in the database."""
    try:
        # Get current database schema
        db = notion.databases.retrieve(database_id=db_id)
        existing_props = db.get("properties", {})
        
        # Check which properties are missing
        properties_to_add = {}
        for prop_name, prop_config in REQUIRED_PROPERTIES.items():
            if prop_name not in existing_props:
                properties_to_add[prop_name] = prop_config
                print(f"   ➕ Will create property: {prop_name}")
            else:
                # Check if property type matches (for select properties, check options)
                existing_type = existing_props[prop_name].get("type")
                required_type = prop_config.get("type") or list(prop_config.keys())[0]
                
                if existing_type != required_type:
                    print(f"   ⚠️  Property {prop_name} exists but has wrong type ({existing_type} vs {required_type})")
                    # Don't update type automatically as it might break data
                else:
                    print(f"   ✅ Property already exists: {prop_name}")
        
        if not properties_to_add:
            print("✅ All required properties exist in database")
            return True
        
        # Add missing properties
        print(f"\n🔧 Adding {len(properties_to_add)} missing properties...")
        
        # Update database with new properties
        notion.databases.update(
            database_id=db_id,
            properties=properties_to_add
        )
        
        # Wait a bit to avoid rate limits
        time.sleep(1)
        
        print("✅ Successfully added missing properties")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update database properties: {e}", file=sys.stderr)
        return False


def create_library_entry(notion: Any, db_id: str, library_path: str, role: str = "Current") -> Optional[str]:
    """Create a Notion entry for an Eagle library."""
    if not db_id:
        print(f"ERROR: No database ID provided", file=sys.stderr)
        return None
    
    library_name = Path(library_path).name
    if role == "Previous":
        name = f"Eagle Music Library - Previous ({library_name})"
    elif role == "Current":
        name = f"Eagle Music Library - Current ({library_name})"
    else:
        name = f"Eagle Music Library ({library_name})"
    
    # Get database schema to check which properties exist
    try:
        db = notion.databases.retrieve(database_id=db_id)
        existing_props = db.get("properties", {})
    except Exception as e:
        print(f"⚠️  Could not retrieve database schema: {e}", file=sys.stderr)
        existing_props = {}
    
    # Build properties dictionary based on what exists
    properties = {}
    
    # Name (title) - required
    if "Name" in existing_props:
        properties["Name"] = {
            "title": [{"text": {"content": name}}]
        }
    elif "Title" in existing_props:
        properties["Title"] = {
            "title": [{"text": {"content": name}}]
        }
    
    # Path (rich_text or url)
    if "Path" in existing_props:
        prop_type = existing_props["Path"].get("type")
        if prop_type == "rich_text":
            properties["Path"] = {
                "rich_text": [{"text": {"content": library_path}}]
            }
        elif prop_type == "url":
            properties["Path"] = {
                "url": library_path
            }
    
    # Type (select)
    if "Type" in existing_props:
        properties["Type"] = {
            "select": {"name": "Eagle Library"}
        }
    
    # Status (select)
    if "Status" in existing_props:
        properties["Status"] = {
            "select": {"name": "Active"}
        }
    
    # Role (select)
    if "Role" in existing_props:
        properties["Role"] = {
            "select": {"name": role}
        }
    
    # Library Name (rich_text)
    if "Library Name" in existing_props:
        properties["Library Name"] = {
            "rich_text": [{"text": {"content": library_name}}]
        }
    
    # Volume (rich_text) - extract from path
    if "Volume" in existing_props:
        volume_match = Path(library_path).parts
        volume = volume_match[1] if len(volume_match) > 1 and volume_match[0] == "/" else ""
        if volume:
            properties["Volume"] = {
                "rich_text": [{"text": {"content": volume}}]
            }
    
    # Last Verified (date)
    if "Last Verified" in existing_props:
        from datetime import datetime
        properties["Last Verified"] = {
            "date": {"start": datetime.now().isoformat()}
        }
    
    if not properties:
        print(f"ERROR: No valid properties found in database schema", file=sys.stderr)
        return None
    
    try:
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=properties
        )
        print(f"✅ Created Notion entry for library: {library_path}")
        print(f"   Page ID: {page.get('id')}")
        return page.get("id")
    except Exception as e:
        print(f"ERROR: Failed to create Notion entry for {library_path}: {e}", file=sys.stderr)
        if hasattr(e, 'body'):
            print(f"   Error details: {e.body}", file=sys.stderr)
        return None


def main():
    """Main verification function."""
    print("=" * 80)
    print("EAGLE LIBRARY NOTION DOCUMENTATION VERIFICATION")
    print("=" * 80)
    print()
    
    # Load configuration
    load_unified_env()
    config = get_unified_config()
    db_id = config.get("music_directories_db_id") or os.getenv("MUSIC_DIRECTORIES_DB_ID", "").strip() or None
    
    # Get Notion client
    try:
        notion = get_notion_client()
    except Exception as e:
        print(f"ERROR: Failed to get Notion client: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Get or create database
    print("=" * 80)
    print("DATABASE VERIFICATION & CREATION")
    print("=" * 80)
    print()
    
    db_id = get_or_create_database(notion, db_id)
    
    if not db_id:
        print("❌ Could not get or create database. Cannot proceed.", file=sys.stderr)
        sys.exit(1)
    
    print(f"📋 Using Music Directories Database ID: {db_id}")
    print()
    
    # Ensure all required properties exist
    print("=" * 80)
    print("PROPERTY VERIFICATION & CREATION")
    print("=" * 80)
    print()
    
    if not ensure_database_properties(notion, db_id):
        print("⚠️  Some properties could not be created. Proceeding anyway...", file=sys.stderr)
    print()
    
    # Find local libraries
    print("🔍 Scanning local filesystem for Eagle libraries...")
    local_libraries = find_eagle_libraries()
    print(f"   Found {len(local_libraries)} Eagle libraries:")
    for lib in local_libraries:
        print(f"      - {lib}")
    print()
    
    # Get documented libraries
    print("📚 Loading documented libraries from Notion...")
    documented_libraries = get_documented_libraries(notion, db_id)
    print(f"   Found {len(documented_libraries)} documented libraries:")
    for doc_lib in documented_libraries:
        print(f"      - {doc_lib['name']}: {doc_lib['path']}")
    print()
    
    # Compare
    print("=" * 80)
    print("COMPARISON MATRIX")
    print("=" * 80)
    print()
    
    documented_paths = {lib["path"].lower(): lib for lib in documented_libraries if lib["path"]}
    
    missing_libraries = []
    found_libraries = []
    
    for local_lib in local_libraries:
        local_lib_lower = local_lib.lower()
        found = False
        
        for doc_path, doc_lib in documented_paths.items():
            if local_lib_lower in doc_path.lower() or doc_path.lower() in local_lib_lower:
                found = True
                found_libraries.append((local_lib, doc_lib))
                print(f"✅ {local_lib}")
                print(f"   Found in Notion: {doc_lib['name']} (Page ID: {doc_lib['page_id'][:8]}...)")
                break
        
        if not found:
            missing_libraries.append(local_lib)
            print(f"❌ {local_lib}")
            print(f"   NOT FOUND in Notion")
    
    print()
    
    # Check for default libraries
    default_previous = Path(DEFAULT_PREVIOUS_LIBRARY)
    default_current = Path(DEFAULT_CURRENT_LIBRARY)
    
    if default_previous.exists() and str(default_previous) not in [f[0] for f in found_libraries]:
        if str(default_previous) not in missing_libraries:
            missing_libraries.append(str(default_previous))
            print(f"⚠️  Default previous library exists but not verified: {default_previous}")
    
    if default_current.exists() and str(default_current) not in [f[0] for f in found_libraries]:
        if str(default_current) not in missing_libraries:
            missing_libraries.append(str(default_current))
            print(f"⚠️  Default current library exists but not verified: {default_current}")
    
    print()
    print("=" * 80)
    print("COMPLIANCE STATUS")
    print("=" * 80)
    print()
    print(f"Total local libraries found: {len(local_libraries)}")
    print(f"Total libraries documented in Notion: {len(documented_libraries)}")
    print(f"Libraries found in Notion: {len(found_libraries)}")
    print(f"Libraries missing from Notion: {len(missing_libraries)}")
    print()
    
    if missing_libraries:
        print("MISSING LIBRARIES:")
        for lib in missing_libraries:
            print(f"   - {lib}")
        print()
        
        # Determine role for missing libraries
        for lib in missing_libraries:
            lib_path = Path(lib)
            if "OF-CP2019-2025" in lib or "previous" in lib.lower():
                role = "Previous"
            elif "VIBES" in lib or "current" in lib.lower():
                role = "Current"
            else:
                role = "Current"  # Default to Current
            
            print(f"Creating Notion entry for: {lib} (Role: {role})")
            page_id = create_library_entry(notion, db_id, lib, role)
            if page_id:
                found_libraries.append((lib, {"page_id": page_id, "name": Path(lib).name, "path": lib}))
        
        print()
    
    # Final compliance check
    all_documented = len(missing_libraries) == 0
    compliance_status = "COMPLIANT" if all_documented else "NON-COMPLIANT"
    
    print("=" * 80)
    print(f"FINAL COMPLIANCE STATUS: {compliance_status}")
    print("=" * 80)
    print()
    
    if all_documented:
        print("✅ All Eagle libraries are documented in Notion")
        print("✅ Compliance verified - ready to proceed with merge workflow")
        print()
        print(f"📝 NOTE: If you haven't already, add this to your .env file:")
        print(f"   MUSIC_DIRECTORIES_DB_ID={db_id}")
        return 0
    else:
        print("❌ Some libraries are missing from Notion")
        print("⚠️  Please review and ensure all libraries are properly documented")
        print()
        print(f"📝 NOTE: If you haven't already, add this to your .env file:")
        print(f"   MUSIC_DIRECTORIES_DB_ID={db_id}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
