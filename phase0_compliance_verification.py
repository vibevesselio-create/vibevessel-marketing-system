#!/usr/bin/env python3
"""
Phase 0: System Compliance Verification
========================================

Verifies that all music directories and Eagle libraries are documented in Notion
before deduplication execution begins.
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
    from shared_core.notion.token_manager import get_notion_client
    from scripts.music_library_remediation import load_music_directories
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}", file=sys.stderr)
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"

MUSIC_EXTENSIONS = {'.aiff', '.aif', '.wav', '.m4a', '.mp3', '.flac', '.alac'}


def log_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def phase0_1_verify_notion_db(config: Dict, notion) -> Tuple[bool, Optional[str]]:
    """Phase 0.1: Verify Notion Music Directories Database"""
    log_section("PHASE 0.1: VERIFY NOTION MUSIC DIRECTORIES DATABASE")
    
    db_id = config.get("music_directories_db_id") or os.getenv("MUSIC_DIRECTORIES_DB_ID", "").strip()
    
    if not db_id:
        print("⚠️  MUSIC_DIRECTORIES_DB_ID not set, searching Notion...")
        try:
            # Use search API to find the database
            results = notion.search(
                filter={"property": "object", "value": "database"},
                query="Music Directories"
            )
            for result in results.get("results", []):
                title_parts = result.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_parts) if title_parts else ""
                if "music" in title.lower() and "director" in title.lower():
                    db_id = result.get("id", "")
                    print(f"✓ Found database: {title} (ID: {db_id})")
                    break
        except Exception as e:
            print(f"✗ Error searching for database: {e}")
            return False, None
    
    if not db_id:
        print("✗ Music Directories database not found")
        return False, None
    
    # Verify database exists and is accessible
    try:
        db = notion.databases.retrieve(database_id=db_id)
        db_title = "".join(t.get("plain_text", "") for t in db.get("title", [])) if db.get("title") else "Untitled"
        props = db.get("properties", {})
        
        # Check for path properties
        path_props = [k for k in props.keys() if any(p in k.lower() for p in ["path", "directory", "folder", "location"])]
        
        print(f"✓ Database exists: {db_title}")
        print(f"✓ Database ID: {db_id}")
        print(f"✓ Found {len(path_props)} path-related properties: {path_props[:5]}")
        print(f"✓ Total properties: {len(props)}")
        
        # Query to get entry count
        query_result = notion.databases.query(database_id=db_id, page_size=1)
        print(f"✓ Database accessible - entries present")
        
        return True, db_id
    except Exception as e:
        print(f"✗ Error accessing database: {e}")
        return False, None


def phase0_2_scan_filesystem() -> List[Dict[str, Any]]:
    """Phase 0.2: Scan local filesystem for music directories"""
    log_section("PHASE 0.2: SCAN LOCAL FILESYSTEM FOR MUSIC DIRECTORIES")
    
    directories = []
    scan_paths = [
        Path('/Users/brianhellemn/Music'),
        Path('/Volumes'),
    ]
    
    for base_path in scan_paths:
        if not base_path.exists():
            print(f"⚠️  Base path does not exist: {base_path}")
            continue
        
        print(f"Scanning: {base_path}")
        for root, dirs, files in os.walk(base_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            # Check if directory contains music files
            has_music = False
            file_count = 0
            for file_name in files:
                if file_name.startswith('.'):
                    continue
                if Path(file_name).suffix.lower() in MUSIC_EXTENSIONS:
                    has_music = True
                    file_count += 1
            
            if has_music:
                dir_path = Path(root)
                directory_type = "Unknown"
                if "Playlists" in str(dir_path):
                    directory_type = "Playlists"
                elif "Downloads" in str(dir_path):
                    directory_type = "Downloads"
                elif "Djay-Pro-Auto-Import" in str(dir_path):
                    directory_type = "Djay-Pro Auto-Import"
                elif "Apple-Music-Auto-Add" in str(dir_path):
                    directory_type = "Apple Music Auto-Add"
                elif ".library" in str(dir_path):
                    directory_type = "Eagle Library"
                
                volume_name = ""
                if "/Volumes/" in str(dir_path):
                    parts = str(dir_path).split("/")
                    if "Volumes" in parts:
                        vol_idx = parts.index("Volumes")
                        if vol_idx + 1 < len(parts):
                            volume_name = parts[vol_idx + 1]
                
                directories.append({
                    "path": str(dir_path),
                    "file_count": file_count,
                    "type": directory_type,
                    "volume": volume_name,
                    "mounted": dir_path.exists()
                })
                print(f"  ✓ Found: {dir_path} ({file_count} music files, {directory_type})")
    
    print(f"\n✓ Total directories found: {len(directories)}")
    return directories


def phase0_3_load_documented_dirs(notion, db_id: str) -> List[Dict[str, Any]]:
    """Phase 0.3: Load documented directories from Notion"""
    log_section("PHASE 0.3: LOAD DOCUMENTED DIRECTORIES FROM NOTION")
    
    documented_dirs = []
    
    if not notion or not db_id:
        print("⚠️  Notion client or database ID not available")
        return documented_dirs
    
    try:
        from scripts.music_library_remediation import query_database_all, _prop_text_value
        
        pages = query_database_all(notion, db_id)
        print(f"Found {len(pages)} entries in database")
        
        for page in pages:
            props = page.get("properties", {})
            page_id = page.get("id", "")
            
            # Try to extract path from various property names
            path = None
            path_prop_name = None
            for prop_name in ["Path", "Directory", "Folder", "Folder Path", "Volume Path", "Root Path", "Location", "Music Directory"]:
                if prop_name in props:
                    path = _prop_text_value(props.get(prop_name))
                    if path:
                        path_prop_name = prop_name
                        break
            
            if path:
                # Get name/title
                name = ""
                for title_prop in ["Name", "Title"]:
                    if title_prop in props:
                        name = _prop_text_value(props.get(title_prop))
                        if name:
                            break
                
                # Get status
                status = "Unknown"
                if "Status" in props:
                    status_prop = props.get("Status")
                    if status_prop.get("type") == "select":
                        status = status_prop.get("select", {}).get("name", "Unknown")
                    elif status_prop.get("type") == "status":
                        status = status_prop.get("status", {}).get("name", "Unknown")
                
                documented_dirs.append({
                    "path": path,
                    "name": name,
                    "page_id": page_id,
                    "path_property": path_prop_name,
                    "status": status
                })
                print(f"  ✓ {name or path}: {path} ({status})")
        
        print(f"\n✓ Total documented directories: {len(documented_dirs)}")
        return documented_dirs
    
    except Exception as e:
        print(f"✗ Error loading documented directories: {e}")
        import traceback
        traceback.print_exc()
        return documented_dirs


def phase0_4_compare_and_document(notion, db_id: str, local_dirs: List[Dict], documented_dirs: List[Dict]) -> Dict[str, Any]:
    """Phase 0.4: Compare local vs Notion and create/update entries"""
    log_section("PHASE 0.4: COMPARE LOCAL VS NOTION DOCUMENTATION")
    
    comparison = {
        "missing": [],
        "updated": [],
        "matches": [],
        "compliance_status": "COMPLIANT"
    }
    
    # Normalize paths for comparison
    documented_paths = {d["path"].rstrip("/") for d in documented_dirs}
    
    print("\nComparison Matrix:")
    print("=" * 100)
    print(f"{'Local Directory':<50} {'In Notion':<12} {'Page ID':<40}")
    print("=" * 100)
    
    for local_dir in local_dirs:
        local_path = local_dir["path"].rstrip("/")
        found = local_path in documented_paths or any(
            local_path.startswith(doc_path.rstrip("/")) or doc_path.rstrip("/").startswith(local_path)
            for doc_path in documented_paths
        )
        
        if found:
            # Find matching documented entry
            doc_entry = None
            for doc_dir in documented_dirs:
                doc_path = doc_dir["path"].rstrip("/")
                if local_path == doc_path or local_path.startswith(doc_path) or doc_path.startswith(local_path):
                    doc_entry = doc_dir
                    break
            
            if doc_entry:
                comparison["matches"].append({
                    "local": local_dir,
                    "documented": doc_entry
                })
                page_id = doc_entry.get("page_id", "N/A")[:36]
                print(f"{local_path:<50} {'Yes':<12} {page_id:<40}")
        else:
            comparison["missing"].append(local_dir)
            print(f"{local_path:<50} {'No':<12} {'N/A':<40}")
    
    print("=" * 100)
    
    # Create entries for missing directories
    if comparison["missing"]:
        print(f"\n⚠️  Found {len(comparison['missing'])} directories not in Notion")
        comparison["compliance_status"] = "NON-COMPLIANT"
        
        for missing_dir in comparison["missing"]:
            try:
                # Create Notion entry
                properties = {
                    "Name": {
                        "title": [{"text": {"content": Path(missing_dir["path"]).name}}]
                    }
                }
                
                # Add Path property (try URL first, then rich_text)
                path_value = missing_dir["path"]
                properties["Path"] = {
                    "url": path_value if path_value.startswith("http") else None,
                    "rich_text": [{"text": {"content": path_value}}] if not path_value.startswith("http") else None
                }
                
                # Add Status
                properties["Status"] = {"select": {"name": "Active"}}
                
                # Add Type if we know it
                if missing_dir.get("type") and missing_dir["type"] != "Unknown":
                    properties["Type"] = {"select": {"name": missing_dir["type"]}}
                
                # Add Volume if we have it
                if missing_dir.get("volume"):
                    properties["Volume"] = {"rich_text": [{"text": {"content": missing_dir["volume"]}}]}
                
                # Add Last Verified
                properties["Last Verified"] = {
                    "date": {"start": datetime.now().isoformat()}
                }
                
                # Remove None values
                cleaned_properties = {k: v for k, v in properties.items() if v is not None}
                if "Path" in cleaned_properties:
                    if cleaned_properties["Path"].get("url") is None:
                        cleaned_properties["Path"] = {"rich_text": cleaned_properties["Path"]["rich_text"]}
                    elif cleaned_properties["Path"].get("rich_text") is None:
                        cleaned_properties["Path"] = {"url": cleaned_properties["Path"]["url"]}
                
                page = notion.pages.create(
                    parent={"database_id": db_id},
                    properties=cleaned_properties
                )
                
                print(f"  ✓ Created Notion entry: {Path(missing_dir['path']).name} (Page ID: {page['id']})")
                comparison["updated"].append({
                    "action": "created",
                    "path": missing_dir["path"],
                    "page_id": page["id"]
                })
                
            except Exception as e:
                print(f"  ✗ Failed to create entry for {missing_dir['path']}: {e}")
                comparison["compliance_status"] = "NON-COMPLIANT"
    
    if not comparison["missing"]:
        print(f"\n✓ All local directories are documented in Notion")
    
    return comparison


def phase0_5_verify_eagle_library(notion, db_id: str, config: Dict) -> Tuple[bool, Optional[str]]:
    """Phase 0.5: Verify Eagle library documentation"""
    log_section("PHASE 0.5: VERIFY EAGLE LIBRARY DOCUMENTATION")
    
    eagle_library_path = config.get("eagle_library_path", "") or "/Volumes/VIBES/Music-Library-2.library"
    
    print(f"Looking for Eagle library: {eagle_library_path}")
    
    if not notion or not db_id:
        print("⚠️  Notion client or database ID not available")
        return False, None
    
    try:
        from scripts.music_library_remediation import query_database_all, _prop_text_value
        
        # Query for Eagle library
        pages = query_database_all(notion, db_id)
        
        eagle_entry = None
        for page in pages:
            props = page.get("properties", {})
            
            # Check if this is the Eagle library entry
            is_eagle = False
            path = None
            
            # Check Type property
            if "Type" in props:
                type_prop = props.get("Type")
                if type_prop.get("type") == "select":
                    type_value = type_prop.get("select", {}).get("name", "")
                    if "eagle" in type_value.lower():
                        is_eagle = True
            
            # Check Path property
            for prop_name in ["Path", "Directory", "Folder", "Folder Path", "Volume Path", "Root Path", "Location"]:
                if prop_name in props:
                    path = _prop_text_value(props.get(prop_name))
                    if path and ("Music-Library-2.library" in path or "Music Library-2.library" in path):
                        is_eagle = True
                        break
            
            # Check Name property
            if "Name" in props:
                name = _prop_text_value(props.get("Name"))
                if name and "eagle" in name.lower():
                    is_eagle = True
            
            if is_eagle:
                eagle_entry = {
                    "page_id": page.get("id"),
                    "path": path or eagle_library_path,
                    "properties": props
                }
                break
        
        if eagle_entry:
            print(f"✓ Eagle library documented (Page ID: {eagle_entry['page_id']})")
            return True, eagle_entry["page_id"]
        else:
            print(f"⚠️  Eagle library not found in Notion, creating entry...")
            
            # Create Eagle library entry
            try:
                properties = {
                    "Name": {
                        "title": [{"text": {"content": "Eagle Music Library - Active"}}]
                    },
                    "Path": {
                        "rich_text": [{"text": {"content": eagle_library_path}}]
                    },
                    "Type": {
                        "select": {"name": "Eagle Library"}
                    },
                    "Status": {
                        "select": {"name": "Active"}
                    },
                    "Library Name": {
                        "rich_text": [{"text": {"content": "Music-Library-2"}}]
                    },
                    "Last Verified": {
                        "date": {"start": datetime.now().isoformat()}
                    }
                }
                
                page = notion.pages.create(
                    parent={"database_id": db_id},
                    properties=properties
                )
                
                print(f"✓ Created Eagle library entry (Page ID: {page['id']})")
                return True, page["id"]
                
            except Exception as e:
                print(f"✗ Failed to create Eagle library entry: {e}")
                return False, None
    
    except Exception as e:
        print(f"✗ Error verifying Eagle library: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def phase0_6_document_compliance_status(
    local_dirs: List[Dict],
    documented_dirs: List[Dict],
    comparison: Dict,
    eagle_documented: bool,
    eagle_page_id: Optional[str]
) -> Dict[str, Any]:
    """Phase 0.6: Document compliance status"""
    log_section("PHASE 0.6: DOCUMENT COMPLIANCE STATUS")
    
    compliance_report = {
        "timestamp": datetime.now().isoformat(),
        "total_local_directories": len(local_dirs),
        "total_documented_directories": len(documented_dirs),
        "directories_missing_from_notion": len(comparison.get("missing", [])),
        "missing_directories_list": [d["path"] for d in comparison.get("missing", [])],
        "directories_updated": len(comparison.get("updated", [])),
        "eagle_library_documented": eagle_documented,
        "eagle_library_page_id": eagle_page_id,
        "compliance_status": comparison.get("compliance_status", "UNKNOWN")
    }
    
    print("\nCompliance Report:")
    print(f"  Total local directories found: {compliance_report['total_local_directories']}")
    print(f"  Total documented in Notion: {compliance_report['total_documented_directories']}")
    print(f"  Directories missing from Notion: {compliance_report['directories_missing_from_notion']}")
    if compliance_report['missing_directories_list']:
        print("  Missing directories:")
        for path in compliance_report['missing_directories_list']:
            print(f"    - {path}")
    print(f"  Directories created/updated: {compliance_report['directories_updated']}")
    print(f"  Eagle library documented: {'Yes' if eagle_documented else 'No'}")
    if eagle_page_id:
        print(f"  Eagle library page ID: {eagle_page_id}")
    print(f"  Compliance Status: {compliance_report['compliance_status']}")
    
    # Save report
    report_path = PROJECT_ROOT / "phase0_compliance_report.json"
    import json
    with open(report_path, 'w') as f:
        json.dump(compliance_report, f, indent=2)
    
    print(f"\n✓ Compliance report saved to: {report_path}")
    
    return compliance_report


def main():
    """Execute Phase 0: System Compliance Verification"""
    print("=" * 80)
    print("PHASE 0: SYSTEM COMPLIANCE VERIFICATION")
    print("=" * 80)
    
    # Load configuration
    load_unified_env()
    config = get_unified_config()
    
    # Get Notion client
    try:
        notion = get_notion_client()
    except Exception as e:
        print(f"ERROR: Failed to get Notion client: {e}")
        sys.exit(1)
    
    # 0.1 Verify Notion Music Directories Database
    db_verified, db_id = phase0_1_verify_notion_db(config, notion)
    if not db_verified:
        print("\n❌ CRITICAL: Music Directories database not found or not accessible")
        print("Cannot proceed without database. Please create Agent-Task to set up database.")
        sys.exit(1)
    
    # 0.2 Scan local filesystem
    local_dirs = phase0_2_scan_filesystem()
    
    # 0.3 Load documented directories
    documented_dirs = phase0_3_load_documented_dirs(notion, db_id)
    
    # 0.4 Compare and document
    comparison = phase0_4_compare_and_document(notion, db_id, local_dirs, documented_dirs)
    
    # 0.5 Verify Eagle library
    eagle_documented, eagle_page_id = phase0_5_verify_eagle_library(notion, db_id, config)
    
    # 0.6 Document compliance status
    compliance_report = phase0_6_document_compliance_status(
        local_dirs, documented_dirs, comparison, eagle_documented, eagle_page_id
    )
    
    # Final status
    print("\n" + "=" * 80)
    if compliance_report["compliance_status"] == "COMPLIANT" and eagle_documented:
        print("✅ PHASE 0 COMPLETE: COMPLIANT")
        print("Proceeding to Pre-Execution phase...")
        return 0
    else:
        print("❌ PHASE 0 INCOMPLETE: NON-COMPLIANT")
        print("Please fix compliance issues before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
