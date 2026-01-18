#!/usr/bin/env python3
"""
Process a specific Notion track page by ID.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Import required modules
from monolithic_scripts.soundcloud_download_prod_merge_2 import process_track, notion_manager

# Track page ID from Notion
TRACK_PAGE_ID = "285e7361-6c27-81b2-83ca-e6e74829677d"

def main():
    print(f"Processing track page: {TRACK_PAGE_ID}")
    
    # Retrieve the page from Notion
    try:
        page = notion_manager.get_page(TRACK_PAGE_ID)
        if not page:
            print(f"Error: Could not retrieve page {TRACK_PAGE_ID}")
            return 1
        
        print(f"Found track: {page.get('properties', {}).get('Title', {}).get('title', [{}])[0].get('plain_text', 'Unknown')}")
        
        # Process the track
        success = process_track(page)
        
        if success:
            print("✅ Track processed successfully!")
            return 0
        else:
            print("❌ Track processing failed")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
