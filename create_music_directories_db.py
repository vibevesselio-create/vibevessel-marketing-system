#!/usr/bin/env python3
"""
Create Music Directories database in Notion
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config
from shared_core.notion.token_manager import get_notion_client

def create_music_directories_database():
    """Create the Music Directories database in Notion."""
    load_unified_env()
    config = get_unified_config()
    
    notion = get_notion_client()
    if not notion:
        print("ERROR: Could not get Notion client")
        return None
    
    # Try to find a suitable parent page - use a page from Agent-Tasks database
    # We'll use the first page we can find, or create it at workspace level
    parent_page_id = None
    
    # Try to find a workspace page or use a known page
    try:
        # Search for pages that could serve as parent
        search_results = notion.search(
            query="Music",
            filter={"property": "object", "value": "page"},
            page_size=1
        )
        if search_results.get("results"):
            parent_page_id = search_results["results"][0]["id"]
            print(f"Using parent page: {parent_page_id[:8]}...")
    except Exception as e:
        print(f"Could not find parent page: {e}")
        # We'll try to create without a parent (might not work)
    
    # Define the database schema
    properties = {
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
                    {"name": "Music Directory", "color": "default"}
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
        }
    }
    
    # Create the database
    try:
        if parent_page_id:
            parent = {"type": "page_id", "page_id": parent_page_id}
        else:
            # Try workspace level (might not work)
            print("WARNING: No parent page found, attempting workspace-level creation...")
            return None  # Can't create without parent
        
        response = notion.databases.create(
            parent=parent,
            title=[{"type": "text", "text": {"content": "Music Directories"}}],
            properties=properties
        )
        
        db_id = response["id"]
        print(f"✓ Created Music Directories database: {db_id}")
        print(f"  URL: {response.get('url', 'N/A')}")
        return db_id
        
    except Exception as e:
        print(f"ERROR: Failed to create database: {e}")
        return None

if __name__ == "__main__":
    db_id = create_music_directories_database()
    if db_id:
        print(f"\nDatabase ID: {db_id}")
        print(f"Please set MUSIC_DIRECTORIES_DB_ID={db_id} in your environment or .env file")
    else:
        print("\nFailed to create database. Please create it manually in Notion.")
        sys.exit(1)
