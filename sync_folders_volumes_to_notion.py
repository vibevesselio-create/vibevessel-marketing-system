#!/usr/bin/env python3
"""
Synchronize Folders and Volumes to Notion Databases
===================================================

This script synchronizes all folders up to 5 levels deep on all connected volumes
and disks to two Notion databases: "folders" and "Volumes". These entries are
linked via existing relation properties within Notion.

Requirements:
- NOTION_TOKEN: Notion API token
- FOLDERS_DATABASE_ID: Database ID for the "folders" database
- VOLUMES_DATABASE_ID: Database ID for the "Volumes" database

Usage:
    python sync_folders_volumes_to_notion.py
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sync_folders_volumes.log')
    ]
)
logger = logging.getLogger(__name__)

# Try to import required libraries
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    logger.error("psutil not available. Install with: pip install psutil")
    PSUTIL_AVAILABLE = False

try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.error("notion-client not available. Install with: pip install notion-client")
    NOTION_CLIENT_AVAILABLE = False

# Environment variables - use token manager for Notion token
try:
    from shared_core.notion.token_manager import get_notion_token
    NOTION_TOKEN = get_notion_token()
except ImportError:
    # Fallback if token_manager not available
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")

FOLDERS_DATABASE_ID = os.getenv("FOLDERS_DATABASE_ID")
VOLUMES_DATABASE_ID = os.getenv("VOLUMES_DATABASE_ID")

if not NOTION_TOKEN:
    logger.error("NOTION_TOKEN not available from token_manager or environment")
    sys.exit(1)

if not FOLDERS_DATABASE_ID:
    logger.error("FOLDERS_DATABASE_ID environment variable not set")
    sys.exit(1)

if not VOLUMES_DATABASE_ID:
    logger.error("VOLUMES_DATABASE_ID environment variable not set")
    sys.exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)


def get_all_volumes() -> List[Dict[str, str]]:
    """
    Get all connected volumes and disks.
    
    Returns:
        List of dictionaries with volume information (device, mountpoint, fstype)
    """
    if not PSUTIL_AVAILABLE:
        logger.error("psutil not available, cannot get volumes")
        return []
    
    volumes = []
    for part in psutil.disk_partitions():
        # Skip CD-ROM drives and partitions without filesystem type
        if 'cdrom' in part.opts or part.fstype == '':
            continue
        
        volumes.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype
        })
    
    logger.info(f"Found {len(volumes)} volumes")
    return volumes


def get_folders_recursive(path: str, max_depth: int = 5, current_depth: int = 0) -> List[str]:
    """
    Recursively get all folders up to max_depth levels deep.
    
    Args:
        path: Root path to scan
        max_depth: Maximum depth to recurse (default: 5)
        current_depth: Current recursion depth
    
    Returns:
        List of folder paths
    """
    folders = []
    
    if current_depth >= max_depth:
        return folders
    
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith('.'):
                    folders.append(entry.path)
                    # Recursively get subfolders
                    folders.extend(
                        get_folders_recursive(entry.path, max_depth, current_depth + 1)
                    )
    except PermissionError:
        logger.warning(f"Permission denied: {path}")
    except FileNotFoundError:
        logger.warning(f"Path not found: {path}")
    except Exception as e:
        logger.warning(f"Error scanning {path}: {e}")
    
    return folders


def create_notion_page(database_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
    """
    Create a new page in a Notion database with automatic property creation.
    
    Args:
        database_id: Notion database ID
        properties: Dictionary of properties to set
    
    Returns:
        Created page object or None if failed
    """
    try:
        # Import auto-property creator
        try:
            from shared_core.notion.property_auto_creator import create_page_with_auto_properties
            response = create_page_with_auto_properties(notion, database_id, properties)
            return response
        except ImportError:
            # Fallback to direct creation if utility not available
            logger.warning("property_auto_creator not available, using direct creation")
            response = notion.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            return response
    except Exception as e:
        # If direct creation fails with property error, try to create properties
        error_msg = str(e)
        if "is not a property that exists" in error_msg:
            logger.warning(f"Property validation error: {error_msg}")
            try:
                from shared_core.notion.property_auto_creator import ensure_properties_exist, parse_missing_properties_error
                missing_props = parse_missing_properties_error(error_msg)
                if missing_props:
                    # Build property hints from the properties dict
                    property_hints = {}
                    for prop_name in missing_props:
                        if prop_name in properties:
                            from shared_core.notion.property_auto_creator import infer_property_type
                            property_hints[prop_name] = infer_property_type(prop_name, properties[prop_name])
                    
                    success, created = ensure_properties_exist(notion, database_id, 
                                                               {k: v for k, v in properties.items() if k in missing_props},
                                                               property_hints)
                    if success:
                        logger.info(f"Created missing properties, retrying page creation...")
                        # Retry creation
                        response = notion.pages.create(
                            parent={"database_id": database_id},
                            properties=properties
                        )
                        return response
            except ImportError:
                pass
        
        logger.error(f"Error creating Notion page: {e}")
        return None


def get_or_create_notion_volume(volume_info: Dict[str, str]) -> Optional[str]:
    """
    Get existing volume page ID or create a new one in Notion.
    
    Args:
        volume_info: Dictionary with volume information (device, mountpoint, fstype)
    
    Returns:
        Notion page ID for the volume, or None if failed
    """
    mountpoint = volume_info["mountpoint"]
    
    # Check if volume already exists by querying for matching mountpoint
    try:
        response = notion.databases.query(
            database_id=VOLUMES_DATABASE_ID,
            filter={
                "property": "Name",
                "title": {
                    "equals": mountpoint
                }
            }
        )
        
        if response["results"]:
            volume_id = response["results"][0]["id"]
            logger.debug(f"Found existing volume: {mountpoint} (ID: {volume_id})")
            return volume_id
    except Exception as e:
        logger.warning(f"Error querying for existing volume: {e}")
    
    # Create new volume page
    # Build properties - auto-creator will create missing ones
    properties = {
        "Name": {
            "title": [{"text": {"content": mountpoint}}]
        },
        "Device": {
            "rich_text": [{"text": {"content": volume_info["device"]}}]
        },
        "Filesystem Type": {
            "rich_text": [{"text": {"content": volume_info["fstype"]}}]
        }
    }
    
    new_page = create_notion_page(VOLUMES_DATABASE_ID, properties)
    
    if new_page:
        volume_id = new_page["id"]
        logger.info(f"Created new volume: {mountpoint} (ID: {volume_id})")
        return volume_id
    
    return None


def get_or_create_notion_folder(folder_path: str, volume_notion_id: str) -> Optional[str]:
    """
    Get existing folder page ID or create a new one in Notion.
    
    Args:
        folder_path: Full path to the folder
        volume_notion_id: Notion page ID of the parent volume
    
    Returns:
        Notion page ID for the folder, or None if failed
    """
    folder_name = os.path.basename(folder_path)
    
    # Check if folder already exists by querying for matching path
    try:
        response = notion.databases.query(
            database_id=FOLDERS_DATABASE_ID,
            filter={
                "property": "Folder Path",
                "rich_text": {
                    "equals": folder_path
                }
            }
        )
        
        if response["results"]:
            folder_id = response["results"][0]["id"]
            logger.debug(f"Found existing folder: {folder_path} (ID: {folder_id})")
            
            # Update the relation to volume if needed
            try:
                notion.pages.update(
                    page_id=folder_id,
                    properties={
                        "Volume": {
                            "relation": [{"id": volume_notion_id}]
                        }
                    }
                )
            except Exception as e:
                logger.debug(f"Could not update volume relation: {e}")
            
            return folder_id
    except Exception as e:
        logger.warning(f"Error querying for existing folder: {e}")
    
    # Create new folder page
    properties = {
        "Name": {
            "title": [{"text": {"content": folder_name}}]
        },
        "Folder Path": {
            "rich_text": [{"text": {"content": folder_path}}]
        },
        "Folder Name": {
            "rich_text": [{"text": {"content": folder_name}}]
        },
        "Volume": {
            "relation": [{"id": volume_notion_id}]
        }
    }
    
    new_page = create_notion_page(FOLDERS_DATABASE_ID, properties)
    
    if new_page:
        folder_id = new_page["id"]
        logger.debug(f"Created new folder: {folder_path} (ID: {folder_id})")
        return folder_id
    
    return None


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Starting Folder and Volume Synchronization to Notion")
    logger.info("=" * 80)
    
    if not PSUTIL_AVAILABLE or not NOTION_CLIENT_AVAILABLE:
        logger.error("Required libraries not available. Please install missing dependencies.")
        sys.exit(1)
    
    # Get all volumes
    volumes = get_all_volumes()
    
    if not volumes:
        logger.warning("No volumes found to process")
        return
    
    total_folders_processed = 0
    total_folders_created = 0
    total_folders_existing = 0
    
    # Process each volume
    for volume in volumes:
        mountpoint = volume["mountpoint"]
        logger.info(f"\nProcessing volume: {mountpoint}")
        
        # Get or create volume in Notion
        volume_notion_id = get_or_create_notion_volume(volume)
        
        if not volume_notion_id:
            logger.error(f"Could not create/get Notion page for volume: {mountpoint}")
            continue
        
        # Get all folders recursively (up to 5 levels deep)
        logger.info(f"Scanning folders in {mountpoint}...")
        folders = get_folders_recursive(mountpoint, max_depth=5)
        
        logger.info(f"Found {len(folders)} folders in {mountpoint}")
        
        # Process each folder
        for folder_path in folders:
            folder_id = get_or_create_notion_folder(folder_path, volume_notion_id)
            
            if folder_id:
                total_folders_processed += 1
                # Check if it was newly created or already existed
                # (We can't easily determine this without storing state, so we'll just count processed)
            else:
                logger.warning(f"Failed to create/get folder: {folder_path}")
        
        logger.info(f"Processed {len(folders)} folders for volume {mountpoint}")
    
    logger.info("=" * 80)
    logger.info("Synchronization Complete")
    logger.info(f"Total folders processed: {total_folders_processed}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
