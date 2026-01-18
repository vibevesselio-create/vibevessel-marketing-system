#!/usr/bin/env python3
"""
Process a specific track by Notion page ID using the production download script.

Usage:
    python3 process_track_by_page_id.py <notion_page_id>
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import from production script
try:
    sys.path.insert(0, str(project_root / "monolithic-scripts"))
    from soundcloud_download_prod_merge_2 import (
        process_track,
        notion_manager,
        TRACKS_DB_ID,
        workspace_logger
    )
except ImportError:
    # Try alternative import
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(
        "soundcloud_download_prod_merge_2",
        project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    )
    module = importlib.util.module_from_spec(spec)
    # Fix Python 3.13 @dataclass compatibility - register module before exec
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    process_track = module.process_track
    notion_manager = module.notion_manager
    TRACKS_DB_ID = module.TRACKS_DB_ID
    workspace_logger = module.workspace_logger

def process_track_by_id(page_id: str) -> bool:
    """Process a track by its Notion page ID."""
    print(f"📄 Fetching Notion page: {page_id}")
    
    # Get the page from Notion
    try:
        page = notion_manager._req("get", f"/pages/{page_id}")
        if not page:
            print(f"❌ Failed to fetch Notion page: {page_id}")
            return False
        
        print(f"✅ Found page: {page.get('properties', {}).get('Title', {}).get('title', [{}])[0].get('plain_text', 'Unknown')}")
        
        # Process the track using the production script's process_track function
        print("🔄 Processing track through production pipeline...")
        success = process_track(page)
        
        if success:
            print("✅ Successfully processed track!")
        else:
            print("❌ Failed to process track")
        
        return success
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 process_track_by_page_id.py <notion_page_id>")
        print("\nExample:")
        print("  python3 process_track_by_page_id.py 2e6e7361-6c27-8007-b3f6-e8f46b9e8233")
        sys.exit(1)
    
    page_id = sys.argv[1]
    success = process_track_by_id(page_id)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
