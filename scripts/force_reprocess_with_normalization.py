#!/usr/bin/env python3
"""
Force reprocess a SoundCloud track with audio normalization
Deletes Eagle item and unmarks track to force full re-download and processing
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
    return (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )

NOTION_TOKEN = get_notion_token()
NOTION_VERSION = unified_config.get("notion_version") or os.getenv("NOTION_VERSION", "2022-06-28")

if not NOTION_TOKEN:
    print("❌ NOTION_TOKEN not found")
    sys.exit(1)

def get_page_properties(page_id: str):
    """Get Notion page properties"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code >= 400:
            print(f"❌ Failed to get page: {response.status_code} - {response.text}")
            return None
        return response.json()
    except Exception as e:
        print(f"❌ Error getting page: {e}")
        return None

def delete_eagle_item(eagle_id: str):
    """Delete Eagle item by moving to trash"""
    try:
        import requests as req
        eagle_api_base = os.getenv("EAGLE_API_BASE", "http://localhost:41595")
        eagle_token = os.getenv("EAGLE_TOKEN", "15f0d3c8-a1f8-4cc6-991a-7d5947d3cb82")
        
        url = f"{eagle_api_base}/api/item/moveToTrash"
        headers = {"Content-Type": "application/json"}
        params = {"token": eagle_token}
        data = {"id": eagle_id}
        
        response = req.post(url, headers=headers, params=params, json=data, timeout=10)
        if response.status_code == 200:
            print(f"✅ Moved Eagle item {eagle_id} to trash")
            return True
        else:
            print(f"⚠️  Failed to delete Eagle item: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"⚠️  Error deleting Eagle item: {e}")
        return False

def delete_physical_files(page):
    """Delete physical files associated with the track"""
    props = page.get("properties", {})
    files_deleted = 0
    
    for path_prop in ["M4A File Path", "AIFF File Path", "WAV File Path"]:
        prop = props.get(path_prop, {})
        if prop.get("type") == "rich_text":
            rich_text = prop.get("rich_text", [])
            if rich_text:
                file_path = rich_text[0].get("text", {}).get("content", "").strip()
                if file_path:
                    try:
                        path = Path(file_path)
                        if path.exists():
                            path.unlink()
                            print(f"   🗑️  Deleted: {file_path}")
                            files_deleted += 1
                    except Exception as e:
                        print(f"   ⚠️  Failed to delete {file_path}: {e}")
    
    return files_deleted

def unmark_track_for_reprocessing(page_id: str):
    """Unmark a track as downloaded so it can be reprocessed"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    
    properties = {}
    
    # Set Downloaded checkbox to False
    properties["Downloaded"] = {"checkbox": False}
    
    # Clear file paths to force re-download
    for path_prop in ["M4A File Path", "AIFF File Path", "WAV File Path"]:
        properties[path_prop] = {"rich_text": []}
    
    # Clear audio processing status
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
        return True
    except Exception as e:
        print(f"❌ Error updating Notion page: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python force_reprocess_with_normalization.py <notion_page_id>")
        print("Example: python force_reprocess_with_normalization.py 2dbe7361-6c27-813d-9230-ce62569a7b6e")
        sys.exit(1)
    
    page_id = sys.argv[1]
    
    print(f"\n{'='*80}")
    print(f"🔄 FORCE REPROCESSING TRACK WITH NORMALIZATION")
    print(f"{'='*80}\n")
    print(f"Page ID: {page_id}\n")
    
    # Step 1: Get page to find Eagle ID
    print("Step 1: Getting track information from Notion...")
    page = get_page_properties(page_id)
    if not page:
        print("❌ Failed to get page information")
        sys.exit(1)
    
    # Extract Eagle File ID if it exists
    props = page.get("properties", {})
    eagle_prop = props.get("Eagle File ID", {})
    eagle_id = None
    if eagle_prop.get("type") == "rich_text":
        rich_text = eagle_prop.get("rich_text", [])
        if rich_text:
            eagle_id = rich_text[0].get("text", {}).get("content", "").strip()
    
    # Step 2: Delete physical files
    print("\nStep 2: Deleting physical files...")
    files_deleted = delete_physical_files(page)
    print(f"   Deleted {files_deleted} file(s)")
    
    # Step 3: Delete Eagle item if it exists
    if eagle_id:
        print(f"\nStep 3: Deleting existing Eagle item ({eagle_id})...")
        delete_eagle_item(eagle_id)
    else:
        print("\nStep 3: No Eagle item found, skipping deletion")
    
    # Step 4: Unmark track for reprocessing
    print("\nStep 4: Unmarking track in Notion...")
    if not unmark_track_for_reprocessing(page_id):
        print("❌ Failed to unmark track")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("Step 5: Triggering download workflow with normalization...")
    print("="*80 + "\n")
    
    # Step 5: Run the download script
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

