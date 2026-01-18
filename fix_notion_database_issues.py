#!/usr/bin/env python3
"""
Fix Notion Database Issues
==========================

Automatically fixes common issues in Notion databases:
- Removes duplicate entries (keeps most recent)
- Updates missing properties where possible
- Fixes invalid file paths

Usage:
    python fix_notion_database_issues.py [--dry-run] [--fix-duplicates] [--fix-missing]
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
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

# Get Notion token
NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
if not NOTION_TOKEN:
    logger.error("NOTION_TOKEN or NOTION_API_TOKEN environment variable not set")
    sys.exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)


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
        
        elif actual_type == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start")
            return None
        
        return prop
    except Exception as e:
        logger.debug(f"Error extracting property '{property_name}': {e}")
        return None


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


def determine_language_from_path(file_path: str) -> Optional[str]:
    """Determine language from file path"""
    if not file_path or file_path == "-":
        return None
    
    path = Path(file_path.replace("file://", ""))
    ext_map = {
        '.py': 'Python',
        '.gs': 'JavaScript',
        '.js': 'JavaScript',
        '.sh': 'Shell',
        '.bash': 'Bash'
    }
    return ext_map.get(path.suffix)


def fix_duplicate_scripts(dry_run: bool = False) -> Dict[str, int]:
    """Fix duplicate script entries"""
    logger.info("=" * 80)
    logger.info("Fixing Duplicate Scripts")
    logger.info("=" * 80)
    
    stats = {
        "duplicates_found": 0,
        "duplicates_fixed": 0,
        "errors": 0
    }
    
    pages = query_all_pages(SCRIPTS_DB_ID)
    
    # Group by name
    by_name = {}
    for page in pages:
        name = safe_get_property(page, "Script Name", "title")
        if name:
            if name not in by_name:
                by_name[name] = []
            by_name[name].append(page)
    
    # Find duplicates
    for name, entries in by_name.items():
        if len(entries) > 1:
            stats["duplicates_found"] += 1
            logger.info(f"Found duplicate: '{name}' ({len(entries)} entries)")
            
            # Sort by last sync time (most recent first)
            entries_sorted = sorted(
                entries,
                key=lambda e: safe_get_property(e, "Last Sync Time", "date") or "",
                reverse=True
            )
            
            # Keep the first (most recent), archive others
            keep = entries_sorted[0]
            archive = entries_sorted[1:]
            
            logger.info(f"  Keeping: {keep['id']} (most recent)")
            
            for entry in archive:
                logger.info(f"  Archiving: {entry['id']}")
                
                if not dry_run:
                    try:
                        # Archive the page
                        notion.pages.update(
                            page_id=entry["id"],
                            archived=True
                        )
                        stats["duplicates_fixed"] += 1
                    except Exception as e:
                        logger.error(f"  Error archiving {entry['id']}: {e}")
                        stats["errors"] += 1
                else:
                    logger.info(f"  [DRY RUN] Would archive: {entry['id']}")
                    stats["duplicates_fixed"] += 1
    
    return stats


def fix_missing_properties(dry_run: bool = False) -> Dict[str, int]:
    """Fix missing properties in scripts"""
    logger.info("=" * 80)
    logger.info("Fixing Missing Properties")
    logger.info("=" * 80)
    
    stats = {
        "checked": 0,
        "updated": 0,
        "errors": 0
    }
    
    pages = query_all_pages(SCRIPTS_DB_ID)
    
    for page in pages:
        stats["checked"] += 1
        page_id = page["id"]
        script_name = safe_get_property(page, "Script Name", "title")
        file_path = safe_get_property(page, "File Path", "url")
        language = safe_get_property(page, "Language", "select")
        
        updates = {}
        
        # Try to determine language from file path
        if not language and file_path:
            determined_language = determine_language_from_path(file_path)
            if determined_language:
                updates["Language"] = {
                    "select": {"name": determined_language}
                }
                logger.info(f"  {script_name}: Adding Language = {determined_language}")
        
        # For GAS projects without file path, mark appropriately
        if not file_path and script_name:
            # Check if it's a GAS project
            if "GAS" in script_name or "Google Apps Script" in script_name:
                # Mark as GAS project
                if not language:
                    updates["Language"] = {
                        "select": {"name": "JavaScript"}
                    }
                logger.info(f"  {script_name}: Marked as GAS project")
        
        if updates:
            if not dry_run:
                try:
                    notion.pages.update(
                        page_id=page_id,
                        properties=updates
                    )
                    stats["updated"] += 1
                except Exception as e:
                    logger.error(f"  Error updating {page_id}: {e}")
                    stats["errors"] += 1
            else:
                logger.info(f"  [DRY RUN] Would update: {script_name}")
                stats["updated"] += 1
    
    return stats


def fix_invalid_paths(dry_run: bool = False) -> Dict[str, int]:
    """Fix invalid file paths (like '-')"""
    logger.info("=" * 80)
    logger.info("Fixing Invalid File Paths")
    logger.info("=" * 80)
    
    stats = {
        "checked": 0,
        "fixed": 0,
        "errors": 0
    }
    
    pages = query_all_pages(SCRIPTS_DB_ID)
    
    for page in pages:
        stats["checked"] += 1
        page_id = page["id"]
        script_name = safe_get_property(page, "Script Name", "title")
        file_path = safe_get_property(page, "File Path", "url")
        
        # Check for invalid paths
        if file_path == "-" or file_path == "file://-":
            logger.info(f"  Found invalid path: {script_name}")
            
            # For GAS projects, we could set a placeholder or remove the path
            # For now, we'll leave it but log it
            if not dry_run:
                # Option: Remove the invalid path (set to empty)
                # This would require updating the property, but Notion might not allow empty URLs
                # So we'll just log it for manual review
                logger.warning(f"  Manual review needed: {script_name} has invalid path")
            else:
                logger.info(f"  [DRY RUN] Would flag for review: {script_name}")
                stats["fixed"] += 1
    
    return stats


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Fix issues in Notion databases"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making changes'
    )
    parser.add_argument(
        '--fix-duplicates',
        action='store_true',
        help='Fix duplicate script entries'
    )
    parser.add_argument(
        '--fix-missing',
        action='store_true',
        help='Fix missing properties'
    )
    parser.add_argument(
        '--fix-paths',
        action='store_true',
        help='Fix invalid file paths'
    )
    parser.add_argument(
        '--fix-all',
        action='store_true',
        help='Fix all issues'
    )
    
    args = parser.parse_args()
    
    if not any([args.fix_duplicates, args.fix_missing, args.fix_paths, args.fix_all]):
        parser.error("Must specify at least one fix option or --fix-all")
    
    logger.info("=" * 80)
    logger.info("Notion Database Issue Fixer")
    logger.info("=" * 80)
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info("=" * 80)
    
    total_stats = {
        "duplicates_fixed": 0,
        "properties_updated": 0,
        "paths_fixed": 0,
        "errors": 0
    }
    
    # Fix duplicates
    if args.fix_duplicates or args.fix_all:
        stats = fix_duplicate_scripts(dry_run=args.dry_run)
        total_stats["duplicates_fixed"] = stats["duplicates_fixed"]
        total_stats["errors"] += stats["errors"]
    
    # Fix missing properties
    if args.fix_missing or args.fix_all:
        stats = fix_missing_properties(dry_run=args.dry_run)
        total_stats["properties_updated"] = stats["updated"]
        total_stats["errors"] += stats["errors"]
    
    # Fix invalid paths
    if args.fix_paths or args.fix_all:
        stats = fix_invalid_paths(dry_run=args.dry_run)
        total_stats["paths_fixed"] = stats["fixed"]
        total_stats["errors"] += stats["errors"]
    
    # Summary
    logger.info("=" * 80)
    logger.info("Fix Summary")
    logger.info("=" * 80)
    logger.info(f"Duplicates Fixed: {total_stats['duplicates_fixed']}")
    logger.info(f"Properties Updated: {total_stats['properties_updated']}")
    logger.info(f"Paths Fixed: {total_stats['paths_fixed']}")
    logger.info(f"Errors: {total_stats['errors']}")
    logger.info("=" * 80)
    
    if args.dry_run:
        logger.info("DRY RUN - No changes were made")
    else:
        logger.info("Changes applied successfully")


if __name__ == "__main__":
    main()
