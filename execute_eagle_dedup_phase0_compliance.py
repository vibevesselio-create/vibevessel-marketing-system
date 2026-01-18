#!/usr/bin/env python3
"""
Phase 0: System Compliance Verification for Eagle Library Deduplication Workflow
=============================================================================

Verifies that all music directories and Eagle libraries are documented in Notion
before proceeding with deduplication execution.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from unified_config import load_unified_env, get_unified_config
    from shared_core.notion.token_manager import get_notion_client, get_notion_token
    from scripts.music_library_remediation import load_music_directories, query_database_all, _prop_text_value
    from shared_core.notion.id_utils import normalize_notion_id
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}", file=sys.stderr)
    sys.exit(1)

MUSIC_EXTENSIONS = {'.aiff', '.aif', '.wav', '.m4a', '.mp3', '.flac', '.alac'}
DIR_PROP_CANDIDATES = [
    "Path", "Directory", "Folder", "Folder Path", "Volume Path", 
    "Root Path", "Location", "Music Directory"
]

# Issues+Questions Database ID (from the plan)
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"
# Agent-Tasks Database ID
AGENT_TASKS_DB_ID = "284e7361-6c27-8018-872a-eb14e82e0392"


def find_music_directories() -> List[Dict[str, Any]]:
    """Scan local filesystem to identify all music directories."""
    print("\n" + "=" * 80)
    print("0.2 - SCANNING LOCAL FILESYSTEM FOR MUSIC DIRECTORIES")
    print("=" * 80)
    
    directories = []
    seen_paths = set()
    
    # Focus on specific locations as per plan
    scan_locations = [
        ("/Users/brianhellemn/Music/Downloads/*", "Downloads"),
        ("/Volumes/*/Music/*", "Music"),
        ("/Volumes/*/Playlists", "Playlists"),
        ("/Volumes/*/Djay-Pro-Auto-Import", "Djay Pro Auto-Import"),
        ("/Volumes/*/Apple-Music-Auto-Add", "Apple Music Auto-Add"),
        ("/Volumes/*/*.library", "Eagle Library"),
    ]
    
    # Also check specific known volumes
    volume_paths = [
        Path('/Volumes/VIBES'),
        Path('/Volumes/SYSTEM_SSD'),
    ]
    
    for volume_path in volume_paths:
        if volume_path.exists():
            # Check for specific subdirectories
            for subdir_name in ['Playlists', 'Djay-Pro-Auto-Import', 'Apple-Music-Auto-Add']:
                subdir_path = volume_path / subdir_name
                if subdir_path.exists() and subdir_path.is_dir():
                    # Count audio files recursively
                    audio_count = sum(1 for f in subdir_path.rglob('*') 
                                    if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS)
                    if audio_count > 0:
                        path_str = str(subdir_path.resolve())
                        if path_str not in seen_paths:
                            seen_paths.add(path_str)
                            directories.append({
                                "path": path_str,
                                "file_count": audio_count,
                                "type": subdir_name.replace('-', ' '),
                                "volume": volume_path.name,
                                "exists": True
                            })
                            print(f"   ✓ Found: {subdir_path} ({audio_count} audio files)")
            
            # Check for Eagle libraries
            for lib_file in volume_path.glob('*.library'):
                path_str = str(lib_file.resolve())
                if path_str not in seen_paths:
                    seen_paths.add(path_str)
                    directories.append({
                        "path": path_str,
                        "file_count": 0,  # Don't count internal files
                        "type": "Eagle Library",
                        "volume": volume_path.name,
                        "exists": True
                    })
                    print(f"   ✓ Found: {lib_file} (Eagle Library)")
    
    # Check Music/Downloads
    downloads_base = Path('/Users/brianhellemn/Music/Downloads')
    if downloads_base.exists():
        for subdir in downloads_base.iterdir():
            if subdir.is_dir() and not subdir.name.startswith('.'):
                audio_count = sum(1 for f in subdir.rglob('*')
                                if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS)
                if audio_count > 0:
                    path_str = str(subdir.resolve())
                    if path_str not in seen_paths:
                        seen_paths.add(path_str)
                        directories.append({
                            "path": path_str,
                            "file_count": audio_count,
                            "type": "Downloads",
                            "volume": "Macintosh HD",
                            "exists": True
                        })
                        print(f"   ✓ Found: {subdir} ({audio_count} audio files)")
    
    # Also check Music directory itself for top-level directories
    music_base = Path('/Users/brianhellemn/Music')
    if music_base.exists():
        for item in music_base.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name not in ['Downloads']:
                # Skip if already processed or if it's an internal directory
                if '.library' in str(item) or 'images' in str(item) or 'metadata' in str(item):
                    continue
                audio_count = sum(1 for f in item.rglob('*')
                                if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS)
                if audio_count > 10:  # Only include if substantial number of files
                    path_str = str(item.resolve())
                    if path_str not in seen_paths:
                        seen_paths.add(path_str)
                        directories.append({
                            "path": path_str,
                            "file_count": audio_count,
                            "type": "Music Directory",
                            "volume": "Macintosh HD",
                            "exists": True
                        })
                        print(f"   ✓ Found: {item} ({audio_count} audio files)")
    
    print(f"\n📊 Total directories found: {len(directories)}")
    return sorted(directories, key=lambda x: x["path"])


def search_music_directories_db(notion) -> Optional[str]:
    """Search Notion for Music Directories database."""
    if not notion:
        return None
    
    try:
        # Search for databases
        search_results = notion.search(
            filter={"property": "object", "value": "database"},
            query="Music Directories"
        )
        
        # Also try broader search
        all_results = notion.search(filter={"property": "object", "value": "database"})
        
        # Look for Music Directories database
        for result in search_results.get("results", []) + all_results.get("results", []):
            title_parts = result.get("title", [])
            if title_parts:
                title = "".join(t.get("plain_text", "") for t in title_parts)
                title_lower = title.lower()
                
                # Check if this looks like a Music Directories database
                if any(keyword in title_lower for keyword in ["music directory", "music directories", "directory", "directories"]):
                    db_id = result.get("id", "")
                    print(f"   Found potential database: {title} (ID: {db_id})")
                    return db_id
        
        return None
    except Exception as e:
        print(f"   Error searching for database: {e}")
        return None


def create_agent_task_for_missing_db(notion, task_description: str) -> Optional[str]:
    """Create Agent-Task for missing Music Directories database."""
    if not notion:
        return None
    
    try:
        db_id = normalize_notion_id(AGENT_TASKS_DB_ID)
        props = {
            "Name": {
                "title": [{"text": {"content": "Eagle Deduplication: Setup Music Directories Database"}}]
            },
            "Status": {
                "status": {"name": "Not Started"}
            },
            "Priority": {
                "select": {"name": "High"}
            },
            "Description": {
                "rich_text": [{"text": {"content": task_description}}]
            }
        }
        
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=props
        )
        return page.get("id")
    except Exception as e:
        print(f"   ❌ Failed to create Agent-Task: {e}")
        return None


def verify_music_directories_db(notion, db_id: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Verify Music Directories database exists and is accessible.
    
    Returns:
        Tuple of (success, database_id, info_dict)
    """
    print("\n" + "=" * 80)
    print("0.1 - VERIFYING NOTION MUSIC DIRECTORIES DATABASE")
    print("=" * 80)
    
    # If db_id not set, search for it
    if not db_id or not db_id.strip():
        print("⚠️  MUSIC_DIRECTORIES_DB_ID is not set in configuration")
        if not notion:
            print("   ❌ Notion client not available - cannot search for database")
            return False, "", {"error": "Notion client not available"}
        
        print("   Searching Notion for Music Directories database...")
        
        found_db_id = search_music_directories_db(notion)
        if found_db_id:
            print(f"   ✓ Found database in Notion: {found_db_id}")
            db_id = found_db_id
        else:
            print("   ❌ Music Directories database not found in Notion")
            print("   Creating Agent-Task for database setup...")
            
            task_desc = """CRITICAL: Music Directories Database Missing

The Eagle Library Deduplication Workflow requires a Notion database to track music directories and Eagle libraries.

Required Actions:
1. Create a Notion database named "Music Directories" 
2. Add the following properties:
   - Name (Title)
   - Path (URL or Rich Text)
   - Status (Select: Active, Inactive)
   - Type (Select: Music Directory, Eagle Library, Playlists, Downloads, etc.)
   - Volume (Rich Text)
   - Last Verified (Date)
3. Set MUSIC_DIRECTORIES_DB_ID environment variable with the database ID
4. Re-run Eagle Deduplication Phase 0 compliance check

Without this database, the deduplication workflow cannot verify system compliance and will not proceed."""
            
            task_id = create_agent_task_for_missing_db(notion, task_desc)
            if task_id:
                print(f"   ✓ Created Agent-Task: {task_id}")
            else:
                print("   ❌ Failed to create Agent-Task")
            
            return False, "", {"error": "MUSIC_DIRECTORIES_DB_ID not configured and database not found in Notion"}
    
    if not notion:
        print("   ❌ Notion client not available - cannot verify database")
        return False, db_id, {"error": "Notion client not available"}
    
    db_id = normalize_notion_id(db_id)
    print(f"📋 Database ID: {db_id}")
    
    try:
        # Try to retrieve the database
        database = notion.databases.retrieve(database_id=db_id)
        print(f"✓ Database exists: {database.get('title', [{}])[0].get('plain_text', 'Unknown')}")
        
        # Check schema for path properties
        properties = database.get('properties', {})
        found_props = []
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get('type', '')
            if prop_type in ['url', 'rich_text', 'title']:
                found_props.append(prop_name)
        
        print(f"✓ Found {len(found_props)} relevant properties: {', '.join(found_props[:10])}")
        
        # Try to query the database
        results = query_database_all(notion, db_id)
        print(f"✓ Database accessible - {len(results)} entries found")
        
        return True, db_id, {
            "exists": True,
            "accessible": True,
            "entry_count": len(results),
            "properties": list(properties.keys()),
            "database": database,
            "database_id": db_id
        }
        
    except Exception as e:
        print(f"❌ Error accessing database: {e}")
        return False, db_id, {"error": str(e), "exists": False}


def load_documented_directories(notion, db_id: str) -> List[Dict[str, Any]]:
    """Load all music directories documented in Notion."""
    print("\n" + "=" * 80)
    print("0.3 - LOADING DOCUMENTED DIRECTORIES FROM NOTION")
    print("=" * 80)
    
    documented = []
    
    if not notion or not db_id:
        print("⚠️  Notion client or database ID not available")
        return documented
    
    try:
        pages = query_database_all(notion, db_id)
        print(f"📋 Found {len(pages)} entries in Notion database")
        
        for page in pages:
            props = page.get("properties", {})
            page_id = page.get("id", "unknown")
            
            # Extract name
            name = ""
            if "Name" in props:
                name = _prop_text_value(props["Name"])
            elif "Title" in props:
                name = _prop_text_value(props["Title"])
            
            # Extract path
            path = None
            for candidate in DIR_PROP_CANDIDATES:
                if candidate in props:
                    path = _prop_text_value(props[candidate])
                    if path:
                        break
            
            # Extract other properties
            status = "Unknown"
            if "Status" in props:
                status_prop = props["Status"]
                if status_prop.get("type") == "select":
                    status = status_prop.get("select", {}).get("name", "Unknown")
            
            dir_type = "Unknown"
            if "Type" in props:
                type_prop = props["Type"]
                if type_prop.get("type") == "select":
                    dir_type = type_prop.get("select", {}).get("name", "Unknown")
            
            if path:
                documented.append({
                    "notion_page_id": page_id,
                    "name": name,
                    "path": path,
                    "status": status,
                    "type": dir_type,
                    "properties": props
                })
                print(f"   ✓ {name}: {path} (Status: {status}, Type: {dir_type})")
        
        print(f"\n📊 Total documented directories: {len(documented)}")
        return documented
        
    except Exception as e:
        print(f"❌ Error loading documented directories: {e}")
        return documented


def compare_local_vs_notion(local_dirs: List[Dict], documented_dirs: List[Dict]) -> Dict[str, Any]:
    """Compare local directories vs Notion documentation."""
    print("\n" + "=" * 80)
    print("0.4 - COMPARING LOCAL vs NOTION DOCUMENTATION")
    print("=" * 80)
    
    # Normalize paths for comparison
    documented_paths = {Path(d["path"]).resolve(): d for d in documented_dirs if d.get("path")}
    local_paths = {Path(d["path"]).resolve(): d for d in local_dirs}
    
    missing_in_notion = []
    incorrect_paths = []
    found_in_notion = []
    
    for local_path, local_info in local_paths.items():
        found = False
        for doc_path, doc_info in documented_paths.items():
            # Try exact match first
            if local_path == doc_path:
                found_in_notion.append({
                    "local": local_info,
                    "notion": doc_info,
                    "match_type": "exact"
                })
                found = True
                break
            # Try parent/child relationship (library files)
            if ".library" in str(local_path) and str(local_path).startswith(str(doc_path).replace(".library", "")):
                found_in_notion.append({
                    "local": local_info,
                    "notion": doc_info,
                    "match_type": "library_path"
                })
                found = True
                break
        
        if not found:
            missing_in_notion.append(local_info)
    
    # Check for documented paths that don't exist locally
    for doc_path, doc_info in documented_paths.items():
        if doc_path.exists():
            continue
        # Check if it's a parent directory
        exists_as_parent = False
        for local_path in local_paths:
            if str(local_path).startswith(str(doc_path)):
                exists_as_parent = True
                break
        if not exists_as_parent:
            incorrect_paths.append({
                "notion": doc_info,
                "issue": "Path does not exist"
            })
    
    print(f"\n📊 Comparison Results:")
    print(f"   ✓ Found in Notion: {len(found_in_notion)}")
    print(f"   ⚠️  Missing from Notion: {len(missing_in_notion)}")
    print(f"   ⚠️  Incorrect paths in Notion: {len(incorrect_paths)}")
    
    if missing_in_notion:
        print(f"\n   Missing directories:")
        for missing in missing_in_notion[:10]:  # Show first 10
            print(f"      - {missing['path']} ({missing['type']})")
    
    if incorrect_paths:
        print(f"\n   Incorrect paths:")
        for incorrect in incorrect_paths[:10]:  # Show first 10
            print(f"      - {incorrect['notion']['path']}: {incorrect['issue']}")
    
    return {
        "found_in_notion": found_in_notion,
        "missing_in_notion": missing_in_notion,
        "incorrect_paths": incorrect_paths,
        "total_local": len(local_paths),
        "total_documented": len(documented_paths)
    }


def verify_eagle_library_documentation(notion, db_id: str, eagle_library_path: str) -> Tuple[bool, Optional[Dict]]:
    """Verify Eagle library is documented in Notion."""
    print("\n" + "=" * 80)
    print("0.5 - VERIFYING EAGLE LIBRARY DOCUMENTATION")
    print("=" * 80)
    
    if not eagle_library_path:
        print("⚠️  EAGLE_LIBRARY_PATH is not set")
        return False, None
    
    print(f"📚 Eagle Library Path: {eagle_library_path}")
    
    eagle_path_obj = Path(eagle_library_path)
    if not eagle_path_obj.exists():
        print(f"⚠️  Eagle library path does not exist: {eagle_library_path}")
        print("   This may be okay if the volume is not mounted")
    
    if not notion or not db_id:
        print("⚠️  Cannot query Notion - client or database ID not available")
        return False, None
    
    try:
        # Search for Eagle library in database
        pages = query_database_all(notion, db_id)
        
        eagle_entry = None
        for page in pages:
            props = page.get("properties", {})
            
            # Check if this is an Eagle library entry
            dir_type = "Unknown"
            if "Type" in props:
                type_prop = props["Type"]
                if type_prop.get("type") == "select":
                    dir_type = type_prop.get("select", {}).get("name", "Unknown")
            
            if dir_type == "Eagle Library":
                # Check path
                for candidate in DIR_PROP_CANDIDATES:
                    if candidate in props:
                        path = _prop_text_value(props[candidate])
                        if path and (path == eagle_library_path or eagle_library_path in path or path in eagle_library_path):
                            eagle_entry = {
                                "notion_page_id": page.get("id"),
                                "path": path,
                                "properties": props
                            }
                            break
            
            if eagle_entry:
                break
        
        if eagle_entry:
            print(f"✓ Eagle library is documented in Notion")
            print(f"   Page ID: {eagle_entry['notion_page_id']}")
            print(f"   Path: {eagle_entry['path']}")
            return True, eagle_entry
        else:
            print(f"⚠️  Eagle library is NOT documented in Notion")
            return False, None
            
    except Exception as e:
        print(f"❌ Error checking Eagle library documentation: {e}")
        return False, None


def create_music_directory_entry(notion, db_id: str, directory_info: Dict) -> Optional[str]:
    """Create a Notion entry for a music directory."""
    if not notion or not db_id:
        return None
    
    try:
        props = {
            "Name": {
                "title": [{"text": {"content": directory_info.get("name", Path(directory_info["path"]).name)}}]
            }
        }
        
        # Add Path property (try URL first, fallback to rich_text)
        path_prop = {
            "rich_text": [{"text": {"content": directory_info["path"]}}]
        }
        props["Path"] = path_prop
        
        # Add Status
        if "Status" in directory_info:
            props["Status"] = {"select": {"name": directory_info["Status"]}}
        else:
            props["Status"] = {"select": {"name": "Active"}}
        
        # Add Type
        if "Type" in directory_info:
            props["Type"] = {"select": {"name": directory_info["Type"]}}
        elif "type" in directory_info:
            props["Type"] = {"select": {"name": directory_info["type"]}}
        
        # Add Volume if available
        if "volume" in directory_info:
            props["Volume"] = {"rich_text": [{"text": {"content": directory_info["volume"]}}]}
        
        # Add Last Verified
        props["Last Verified"] = {
            "date": {"start": datetime.now().isoformat()}
        }
        
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=props
        )
        
        return page.get("id")
        
    except Exception as e:
        print(f"   ❌ Failed to create Notion entry: {e}")
        return None


def document_compliance_status(results: Dict[str, Any]) -> Dict[str, Any]:
    """Document compliance status."""
    print("\n" + "=" * 80)
    print("0.6 - DOCUMENTING COMPLIANCE STATUS")
    print("=" * 80)
    
    compliance_status = "COMPLIANT"
    issues = []
    
    # Check Music Directories DB
    if not results.get("music_directories_db", {}).get("exists"):
        compliance_status = "NON-COMPLIANT"
        issues.append("Music Directories database not accessible")
    
    # Check missing directories
    missing_count = len(results.get("comparison", {}).get("missing_in_notion", []))
    if missing_count > 0:
        compliance_status = "NON-COMPLIANT"
        issues.append(f"{missing_count} local directories not documented in Notion")
    
    # Check incorrect paths
    incorrect_count = len(results.get("comparison", {}).get("incorrect_paths", []))
    if incorrect_count > 0:
        compliance_status = "NON-COMPLIANT"
        issues.append(f"{incorrect_count} documented paths are incorrect")
    
    # Check Eagle library
    if not results.get("eagle_library_documented"):
        compliance_status = "NON-COMPLIANT"
        issues.append("Eagle library not documented in Notion")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "compliance_status": compliance_status,
        "total_local_directories": results.get("local_directories_count", 0),
        "total_documented_directories": results.get("documented_directories_count", 0),
        "missing_directories": results.get("comparison", {}).get("missing_in_notion", []),
        "incorrect_paths": results.get("comparison", {}).get("incorrect_paths", []),
        "eagle_library_documented": results.get("eagle_library_documented", False),
        "issues": issues
    }
    
    print(f"\n📊 Compliance Status: {compliance_status}")
    print(f"   Total local directories: {report['total_local_directories']}")
    print(f"   Total documented: {report['total_documented_directories']}")
    print(f"   Missing from Notion: {len(report['missing_directories'])}")
    print(f"   Incorrect paths: {len(report['incorrect_paths'])}")
    print(f"   Eagle library documented: {report['eagle_library_documented']}")
    
    if issues:
        print(f"\n⚠️  Issues found:")
        for issue in issues:
            print(f"      - {issue}")
    else:
        print(f"\n✓ All checks passed!")
    
    return report


def main():
    """Main execution function."""
    print("=" * 80)
    print("PHASE 0: SYSTEM COMPLIANCE VERIFICATION")
    print("Eagle Library Deduplication Workflow - System Compliant Edition")
    print("=" * 80)
    
    # Load configuration
    load_unified_env()
    config = get_unified_config()
    
    db_id = config.get("music_directories_db_id") or os.getenv("MUSIC_DIRECTORIES_DB_ID", "")
    eagle_library_path = config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")
    
    # Initialize Notion client
    notion = None
    try:
        notion = get_notion_client()
    except Exception as e:
        print(f"⚠️  Failed to initialize Notion client: {e}")
    
    results = {}
    
    # 0.1 - Verify Music Directories Database
    db_exists, db_id, db_info = verify_music_directories_db(notion, db_id)
    results["music_directories_db"] = db_info
    results["music_directories_db_id"] = db_id
    
    if not db_exists:
        print("\n❌ CRITICAL: Music Directories database not accessible")
        print("   Execution cannot continue without database access")
        print("   Please verify MUSIC_DIRECTORIES_DB_ID is set correctly")
        return 1
    
    # 0.2 - Scan Local Filesystem
    local_dirs = find_music_directories()
    results["local_directories"] = local_dirs
    results["local_directories_count"] = len(local_dirs)
    
    # 0.3 - Load Documented Directories (use verified db_id)
    documented_dirs = load_documented_directories(notion, db_id)
    results["documented_directories"] = documented_dirs
    results["documented_directories_count"] = len(documented_dirs)
    
    # 0.4 - Compare Local vs Notion
    comparison = compare_local_vs_notion(local_dirs, documented_dirs)
    results["comparison"] = comparison
    
    # Create Notion entries for missing directories
    missing = comparison.get("missing_in_notion", [])
    if missing and notion and db_id:
        print(f"\n📝 Creating Notion entries for {len(missing)} missing directories...")
        created_count = 0
        for missing_dir in missing:
            entry_info = {
                "name": Path(missing_dir["path"]).name,
                "path": missing_dir["path"],
                "Status": "Active",
                "Type": missing_dir.get("type", "Music Directory"),
                "volume": missing_dir.get("volume", "Unknown")
            }
            page_id = create_music_directory_entry(notion, db_id, entry_info)
            if page_id:
                created_count += 1
                print(f"   ✓ Created entry for: {missing_dir['path']}")
        print(f"   Created {created_count} out of {len(missing)} entries")
    
    # 0.5 - Verify Eagle Library Documentation
    eagle_documented, eagle_entry = verify_eagle_library_documentation(notion, db_id, eagle_library_path)
    results["eagle_library_documented"] = eagle_documented
    results["eagle_library_entry"] = eagle_entry
    results["eagle_library_path"] = eagle_library_path
    
    # Create Eagle library entry if missing
    if not eagle_documented and eagle_library_path and notion and db_id:
        print(f"\n📝 Creating Notion entry for Eagle library...")
        entry_info = {
            "name": "Eagle Music Library - Active",
            "path": eagle_library_path,
            "Status": "Active",
            "Type": "Eagle Library",
            "volume": Path(eagle_library_path).parts[1] if len(Path(eagle_library_path).parts) > 1 else "VIBES"
        }
        page_id = create_music_directory_entry(notion, db_id, entry_info)
        if page_id:
            print(f"   ✓ Created Eagle library entry")
            results["eagle_library_documented"] = True
            results["eagle_library_entry"] = {"notion_page_id": page_id}
    
    # 0.6 - Document Compliance Status
    compliance_report = document_compliance_status(results)
    results["compliance_report"] = compliance_report
    
    # Save results
    import json
    report_path = PROJECT_ROOT / "phase0_compliance_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📄 Compliance report saved to: {report_path}")
    
    # Final status
    print("\n" + "=" * 80)
    if compliance_report["compliance_status"] == "COMPLIANT":
        print("✓ PHASE 0 COMPLETE - SYSTEM IS COMPLIANT")
        print("   Ready to proceed to Pre-Execution Phase")
        return 0
    else:
        print("⚠️  PHASE 0 COMPLETE - SYSTEM IS NON-COMPLIANT")
        print("   Review issues above and fix before proceeding")
        print("   Attempted to create missing Notion entries")
        return 1


if __name__ == "__main__":
    sys.exit(main())
