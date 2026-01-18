#!/usr/bin/env python3
"""
Re-process LOUDER track with the correct YouTube URL.
Cleans up wrong files and re-downloads from correct source.
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "monolithic-scripts"))

os.chdir(project_root)

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

def cleanup_wrong_files():
    """Remove the incorrectly downloaded files."""
    files_to_remove = [
        "/Volumes/VIBES/Playlists/Unassigned/LOUDER.aiff",
        "/Volumes/VIBES/Playlists/Unassigned/LOUDER.m4a",
        "/Volumes/VIBES/Djay-Pro-Auto-Import/LOUDER.m4a",
        "/Volumes/VIBES/Apple-Music-Auto-Add/LOUDER.wav",
    ]
    
    print("🧹 Cleaning up wrong files...")
    for file_path in files_to_remove:
        path = Path(file_path)
        if path.exists():
            try:
                path.unlink()
                print(f"   ✓ Removed: {file_path}")
            except Exception as e:
                print(f"   ✗ Failed to remove {file_path}: {e}")
        else:
            print(f"   - Not found: {file_path}")

def update_notion_youtube_url(page_id, correct_url):
    """Update Notion with correct YouTube URL and clear wrong one."""
    print(f"\n📝 Updating Notion page {page_id}...")
    
    try:
        # Update YouTube URL field
        module.notion_manager.update_page(page_id, {
            "YouTube URL": {"url": correct_url},
            "SoundCloud URL": {"url": None},  # Clear wrong URL
            "Downloaded": {"checkbox": False},  # Reset so it can be re-processed
        })
        print(f"   ✓ Updated YouTube URL to: {correct_url}")
        print(f"   ✓ Cleared wrong SoundCloud URL")
        print(f"   ✓ Reset Downloaded flag")
        return True
    except Exception as e:
        print(f"   ✗ Failed to update Notion: {e}")
        return False

def main():
    page_id = '2e6e7361-6c27-8007-b3f6-e8f46b9e8233'
    correct_youtube_url = 'https://www.youtube.com/watch?v=Pv_dMQ2Y37w'
    
    print("=" * 80)
    print("RE-PROCESSING LOUDER TRACK WITH CORRECT YOUTUBE URL")
    print("=" * 80)
    
    # Step 1: Clean up wrong files
    cleanup_wrong_files()
    
    # Step 2: Update Notion
    if not update_notion_youtube_url(page_id, correct_youtube_url):
        print("\n❌ Failed to update Notion. Aborting.")
        return 1
    
    # Step 3: Re-process the track
    print(f"\n🔄 Re-processing track from correct YouTube URL...")
    print(f"   URL: {correct_youtube_url}\n")
    
    try:
        page = module.notion_manager._req('get', f'/pages/{page_id}')
        if page:
            result = module.process_track(page)
            if result:
                print("\n✅ SUCCESS: Track re-processed correctly!")
                return 0
            else:
                print("\n❌ FAILED: Track processing failed")
                return 1
        else:
            print("\n❌ Failed to fetch Notion page")
            return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
