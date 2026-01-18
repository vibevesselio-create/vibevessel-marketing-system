#!/usr/bin/env python3
"""
Review Notion Databases for Issues
==================================

Reviews synced Notion databases to identify:
- Duplicate entries
- Misaligned items
- Missing properties
- Data inconsistencies

Usage:
    python review_notion_databases.py
"""

import os
import sys
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Set
from dotenv import load_dotenv

try:
    from notion_client import Client
except ImportError:
    print("Error: notion-client not available. Install with: pip install notion-client")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database IDs
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"
FOLDERS_DB_ID = os.getenv("FOLDERS_DATABASE_ID")
VOLUMES_DB_ID = os.getenv("VOLUMES_DATABASE_ID")

# Get Notion token
NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
if not NOTION_TOKEN:
    logger.error("NOTION_TOKEN or NOTION_API_TOKEN environment variable not set")
    sys.exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)


def query_all_pages(database_id: str) -> List[Dict[str, Any]]:
    """Query all pages from a database with pagination"""
    all_pages = []
    start_cursor = None
    
    while True:
        try:
            response = notion.databases.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100
            )
            
            all_pages.extend(response.get("results", []))
            
            if not response.get("has_more"):
                break
            
            start_cursor = response.get("next_cursor")
        except Exception as e:
            logger.error(f"Error querying database {database_id}: {e}")
            break
    
    return all_pages


def safe_get_property(page: Dict, property_name: str, property_type: str = None) -> Any:
    """Safely extract property value from Notion page"""
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
            if title_list:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "url":
            return prop.get("url")
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return [r.get("id") for r in relation_list] if relation_list else []
        
        return prop
    except Exception as e:
        logger.debug(f"Error extracting property '{property_name}': {e}")
        return None


def review_scripts_database() -> Dict[str, Any]:
    """Review Scripts database for issues"""
    logger.info("=" * 80)
    logger.info("Reviewing Scripts Database")
    logger.info("=" * 80)
    
    issues = {
        "duplicates": [],
        "missing_properties": [],
        "misaligned": [],
        "statistics": {}
    }
    
    pages = query_all_pages(SCRIPTS_DB_ID)
    logger.info(f"Found {len(pages)} scripts in database")
    
    # Track by name and file path
    by_name = defaultdict(list)
    by_path = defaultdict(list)
    
    for page in pages:
        script_name = safe_get_property(page, "Script Name", "title")
        file_path = safe_get_property(page, "File Path", "url")
        language = safe_get_property(page, "Language", "select")
        status = safe_get_property(page, "Status", "status")
        last_sync = safe_get_property(page, "Last Sync Time", "date")
        
        if script_name:
            by_name[script_name].append({
                "id": page["id"],
                "name": script_name,
                "path": file_path,
                "language": language,
                "status": status,
                "last_sync": last_sync
            })
        
        if file_path:
            by_path[file_path].append({
                "id": page["id"],
                "name": script_name,
                "path": file_path,
                "language": language,
                "status": status,
                "last_sync": last_sync
            })
        
        # Check for missing properties
        missing = []
        if not script_name:
            missing.append("Script Name")
        if not file_path:
            missing.append("File Path")
        if not language:
            missing.append("Language")
        
        if missing:
            issues["missing_properties"].append({
                "id": page["id"],
                "url": page.get("url", ""),
                "missing": missing
            })
    
    # Find duplicates
    for name, entries in by_name.items():
        if len(entries) > 1:
            issues["duplicates"].append({
                "type": "name",
                "value": name,
                "count": len(entries),
                "entries": entries
            })
    
    for path, entries in by_path.items():
        if len(entries) > 1:
            issues["duplicates"].append({
                "type": "path",
                "value": path,
                "count": len(entries),
                "entries": entries
            })
    
    # Statistics
    issues["statistics"] = {
        "total": len(pages),
        "with_name": len([p for p in pages if safe_get_property(p, "Script Name", "title")]),
        "with_path": len([p for p in pages if safe_get_property(p, "File Path", "url")]),
        "with_language": len([p for p in pages if safe_get_property(p, "Language", "select")]),
        "duplicate_names": len([e for e in issues["duplicates"] if e["type"] == "name"]),
        "duplicate_paths": len([e for e in issues["duplicates"] if e["type"] == "path"]),
        "missing_properties_count": len(issues["missing_properties"])
    }
    
    return issues


def review_folders_database() -> Dict[str, Any]:
    """Review Folders database for issues"""
    logger.info("=" * 80)
    logger.info("Reviewing Folders Database")
    logger.info("=" * 80)
    
    if not FOLDERS_DB_ID:
        logger.warning("FOLDERS_DATABASE_ID not set - skipping folders review")
        return {"error": "FOLDERS_DATABASE_ID not configured"}
    
    issues = {
        "duplicates": [],
        "missing_properties": [],
        "orphaned": [],
        "statistics": {}
    }
    
    pages = query_all_pages(FOLDERS_DB_ID)
    logger.info(f"Found {len(pages)} folders in database")
    
    # Track by path
    by_path = defaultdict(list)
    
    for page in pages:
        folder_name = safe_get_property(page, "Name", "title")
        folder_path = safe_get_property(page, "Path", "rich_text")
        volume_relation = safe_get_property(page, "Volume", "relation")
        
        if folder_path:
            by_path[folder_path].append({
                "id": page["id"],
                "name": folder_name,
                "path": folder_path,
                "volume_ids": volume_relation
            })
        
        # Check for missing properties
        missing = []
        if not folder_name:
            missing.append("Name")
        if not folder_path:
            missing.append("Path")
        if not volume_relation:
            missing.append("Volume (relation)")
        
        if missing:
            issues["missing_properties"].append({
                "id": page["id"],
                "url": page.get("url", ""),
                "missing": missing
            })
        
        # Check for orphaned folders (no volume relation)
        if not volume_relation:
            issues["orphaned"].append({
                "id": page["id"],
                "name": folder_name,
                "path": folder_path
            })
    
    # Find duplicates
    for path, entries in by_path.items():
        if len(entries) > 1:
            issues["duplicates"].append({
                "type": "path",
                "value": path,
                "count": len(entries),
                "entries": entries
            })
    
    # Statistics
    issues["statistics"] = {
        "total": len(pages),
        "with_name": len([p for p in pages if safe_get_property(p, "Name", "title")]),
        "with_path": len([p for p in pages if safe_get_property(p, "Path", "rich_text")]),
        "with_volume": len([p for p in pages if safe_get_property(p, "Volume", "relation")]),
        "duplicate_paths": len(issues["duplicates"]),
        "orphaned_count": len(issues["orphaned"]),
        "missing_properties_count": len(issues["missing_properties"])
    }
    
    return issues


def review_volumes_database() -> Dict[str, Any]:
    """Review Volumes database for issues"""
    logger.info("=" * 80)
    logger.info("Reviewing Volumes Database")
    logger.info("=" * 80)
    
    if not VOLUMES_DB_ID:
        logger.warning("VOLUMES_DATABASE_ID not set - skipping volumes review")
        return {"error": "VOLUMES_DATABASE_ID not configured"}
    
    issues = {
        "duplicates": [],
        "missing_properties": [],
        "statistics": {}
    }
    
    pages = query_all_pages(VOLUMES_DB_ID)
    logger.info(f"Found {len(pages)} volumes in database")
    
    # Track by name
    by_name = defaultdict(list)
    
    for page in pages:
        volume_name = safe_get_property(page, "Name", "title")
        device = safe_get_property(page, "Device", "rich_text")
        fstype = safe_get_property(page, "Filesystem Type", "rich_text")
        
        if volume_name:
            by_name[volume_name].append({
                "id": page["id"],
                "name": volume_name,
                "device": device,
                "fstype": fstype
            })
        
        # Check for missing properties
        missing = []
        if not volume_name:
            missing.append("Name")
        
        if missing:
            issues["missing_properties"].append({
                "id": page["id"],
                "url": page.get("url", ""),
                "missing": missing
            })
    
    # Find duplicates
    for name, entries in by_name.items():
        if len(entries) > 1:
            issues["duplicates"].append({
                "type": "name",
                "value": name,
                "count": len(entries),
                "entries": entries
            })
    
    # Statistics
    issues["statistics"] = {
        "total": len(pages),
        "with_name": len([p for p in pages if safe_get_property(p, "Name", "title")]),
        "duplicate_names": len(issues["duplicates"]),
        "missing_properties_count": len(issues["missing_properties"])
    }
    
    return issues


def print_report(scripts_issues: Dict, folders_issues: Dict, volumes_issues: Dict):
    """Print a comprehensive report of all issues"""
    print("\n" + "=" * 80)
    print("NOTION DATABASES REVIEW REPORT")
    print("=" * 80)
    
    # Scripts Database
    print("\n📜 SCRIPTS DATABASE")
    print("-" * 80)
    if scripts_issues.get("statistics"):
        stats = scripts_issues["statistics"]
        print(f"Total Scripts: {stats['total']}")
        print(f"  - With Name: {stats['with_name']}")
        print(f"  - With Path: {stats['with_path']}")
        print(f"  - With Language: {stats['with_language']}")
        print(f"  - Duplicate Names: {stats['duplicate_names']}")
        print(f"  - Duplicate Paths: {stats['duplicate_paths']}")
        print(f"  - Missing Properties: {stats['missing_properties_count']}")
    
    if scripts_issues.get("duplicates"):
        print(f"\n⚠️  Found {len(scripts_issues['duplicates'])} duplicate groups:")
        for dup in scripts_issues["duplicates"][:10]:  # Show first 10
            print(f"  - {dup['type'].upper()}: '{dup['value']}' ({dup['count']} entries)")
            for entry in dup["entries"]:
                print(f"    • {entry['id']} - {entry.get('name', 'N/A')}")
    
    if scripts_issues.get("missing_properties"):
        print(f"\n⚠️  Found {len(scripts_issues['missing_properties'])} scripts with missing properties:")
        for item in scripts_issues["missing_properties"][:10]:  # Show first 10
            print(f"  - {item['id']}: Missing {', '.join(item['missing'])}")
    
    # Folders Database
    if not folders_issues.get("error"):
        print("\n📁 FOLDERS DATABASE")
        print("-" * 80)
        if folders_issues.get("statistics"):
            stats = folders_issues["statistics"]
            print(f"Total Folders: {stats['total']}")
            print(f"  - With Name: {stats['with_name']}")
            print(f"  - With Path: {stats['with_path']}")
            print(f"  - With Volume: {stats['with_volume']}")
            print(f"  - Duplicate Paths: {stats['duplicate_paths']}")
            print(f"  - Orphaned (no volume): {stats['orphaned_count']}")
            print(f"  - Missing Properties: {stats['missing_properties_count']}")
        
        if folders_issues.get("duplicates"):
            print(f"\n⚠️  Found {len(folders_issues['duplicates'])} duplicate folders:")
            for dup in folders_issues["duplicates"][:10]:  # Show first 10
                print(f"  - Path: '{dup['value']}' ({dup['count']} entries)")
        
        if folders_issues.get("orphaned"):
            print(f"\n⚠️  Found {len(folders_issues['orphaned'])} orphaned folders (no volume relation):")
            for item in folders_issues["orphaned"][:10]:  # Show first 10
                print(f"  - {item['id']}: {item.get('name', 'N/A')} - {item.get('path', 'N/A')}")
    else:
        print("\n📁 FOLDERS DATABASE")
        print("-" * 80)
        print("  ⚠️  Not configured (FOLDERS_DATABASE_ID not set)")
    
    # Volumes Database
    if not volumes_issues.get("error"):
        print("\n💾 VOLUMES DATABASE")
        print("-" * 80)
        if volumes_issues.get("statistics"):
            stats = volumes_issues["statistics"]
            print(f"Total Volumes: {stats['total']}")
            print(f"  - With Name: {stats['with_name']}")
            print(f"  - Duplicate Names: {stats['duplicate_names']}")
            print(f"  - Missing Properties: {stats['missing_properties_count']}")
        
        if volumes_issues.get("duplicates"):
            print(f"\n⚠️  Found {len(volumes_issues['duplicates'])} duplicate volumes:")
            for dup in volumes_issues["duplicates"]:
                print(f"  - Name: '{dup['value']}' ({dup['count']} entries)")
                for entry in dup["entries"]:
                    print(f"    • {entry['id']} - {entry.get('name', 'N/A')}")
    else:
        print("\n💾 VOLUMES DATABASE")
        print("-" * 80)
        print("  ⚠️  Not configured (VOLUMES_DATABASE_ID not set)")
    
    print("\n" + "=" * 80)


def main():
    """Main execution function"""
    logger.info("Starting Notion databases review...")
    
    # Review each database
    scripts_issues = review_scripts_database()
    folders_issues = review_folders_database()
    volumes_issues = review_volumes_database()
    
    # Print report
    print_report(scripts_issues, folders_issues, volumes_issues)
    
    # Summary
    total_issues = (
        len(scripts_issues.get("duplicates", [])) +
        len(scripts_issues.get("missing_properties", [])) +
        len(folders_issues.get("duplicates", [])) +
        len(folders_issues.get("orphaned", [])) +
        len(folders_issues.get("missing_properties", [])) +
        len(volumes_issues.get("duplicates", [])) +
        len(volumes_issues.get("missing_properties", []))
    )
    
    if total_issues == 0:
        logger.info("✅ No issues found in any database!")
    else:
        logger.warning(f"⚠️  Found {total_issues} total issue groups across all databases")
    
    return {
        "scripts": scripts_issues,
        "folders": folders_issues,
        "volumes": volumes_issues,
        "total_issues": total_issues
    }


if __name__ == "__main__":
    main()
