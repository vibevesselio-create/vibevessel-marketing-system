#!/usr/bin/env python3
"""
Reprocess a SoundCloud track with audio normalization
Unmarks the track as downloaded and triggers the full download workflow with normalization
"""
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv()

# Load unified environment
try:
    from unified_config import load_unified_env, get_unified_config
    load_unified_env()
    unified_config = get_unified_config()
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    print(f"Warning: unified_config unavailable ({unified_err}); using environment variables directly.", file=sys.stderr)
    unified_config = {}

import requests

def get_notion_token():
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    token = (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    return token

NOTION_TOKEN = get_notion_token()
NOTION_VERSION = unified_config.get("notion_version") or os.getenv("NOTION_VERSION", "2022-06-28")

if not NOTION_TOKEN:
    print("❌ NOTION_TOKEN not found")
    sys.exit(1)

def unmark_track_for_reprocessing(page_id: str):
    """Unmark a track as downloaded so it can be reprocessed"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    
    # Use the correct property names from the database
    properties = {}
    
    # Set Downloaded checkbox to False
    properties["Downloaded"] = {"checkbox": False}
    
    # Clear file paths to force re-download
    # This ensures the track will be fully reprocessed
    for path_prop in ["M4A File Path", "AIFF File Path", "WAV File Path"]:
        properties[path_prop] = {"rich_text": []}
    
    # Clear audio processing status to allow re-processing
    properties["Audio Processing Status"] = {"multi_select": []}
    properties["Audio Processing"] = {"multi_select": []}
    
    # Clear Eagle File ID to force re-import
    properties["Eagle File ID"] = {"rich_text": []}
    
    # Clear audio normalization flag
    properties["Audio Normalized"] = {"checkbox": False}
    
    data = {"properties": properties}
    
    try:
        response = requests.patch(url, headers=headers, json=data, timeout=30)
        if response.status_code >= 400:
            print(f"❌ Failed to update Notion page: {response.status_code} - {response.text}")
            return False
        
        print(f"✅ Unmarked track for reprocessing (Page ID: {page_id})")
        print(f"   - DL checkbox set to False")
        print(f"   - File paths cleared")
        print(f"   - Processing status cleared")
        return True
    except Exception as e:
        print(f"❌ Error updating Notion page: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python reprocess_track_with_normalization.py <notion_page_id>")
        print("Example: python reprocess_track_with_normalization.py 2dbe7361-6c27-813d-9230-ce62569a7b6e")
        sys.exit(1)
    
    page_id = sys.argv[1]
    
    print(f"\n{'='*80}")
    print(f"🔄 REPROCESSING TRACK WITH NORMALIZATION")
    print(f"{'='*80}\n")
    print(f"Page ID: {page_id}\n")
    
    # Step 1: Unmark track for reprocessing
    print("Step 1: Unmarking track in Notion...")
    if not unmark_track_for_reprocessing(page_id):
        print("❌ Failed to unmark track")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("Step 2: Triggering download workflow with normalization...")
    print("="*80 + "\n")
    
    # Step 2: Run the download script
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        print(f"❌ Download script not found: {script_path}")
        sys.exit(1)
    
    # Run in single mode - it will pick up the unmarked track
    cmd = ["python3", str(script_path), "--mode", "single"]
    
    print(f"🚀 Running: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        if result.returncode == 0:
            print("\n✅ Track reprocessed successfully with normalization!")
        else:
            print(f"\n⚠️  Download workflow completed with exit code {result.returncode}")
        sys.exit(result.returncode)
    except Exception as e:
        print(f"❌ Failed to run download workflow: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

