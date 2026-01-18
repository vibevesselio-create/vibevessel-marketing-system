#!/usr/bin/env python3
"""
Re-process LOUDER track with the correct SoundCloud URL.
Cleans up wrong files and re-downloads from SoundCloud.
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
    removed_count = 0
    for file_path in files_to_remove:
        path = Path(file_path)
        if path.exists():
            try:
                size_mb = path.stat().st_size / (1024 * 1024)
                path.unlink()
                print(f"   ✓ Removed: {file_path} ({size_mb:.1f} MB)")
                removed_count += 1
            except Exception as e:
                print(f"   ✗ Failed to remove {file_path}: {e}")
        else:
            print(f"   - Not found: {file_path}")
    
    print(f"\n   Removed {removed_count} file(s)")

def update_notion_soundcloud_url(page_id, soundcloud_url):
    """Update Notion with correct SoundCloud URL and reset flags."""
    print(f"\n📝 Updating Notion page {page_id}...")
    
    try:
        # Update SoundCloud URL and reset processing flags
        module.notion_manager.update_page(page_id, {
            "SoundCloud URL": {"url": soundcloud_url},
            "YouTube URL": {"url": None},  # Clear wrong YouTube URL
            "Downloaded": {"checkbox": False},  # Reset so it can be re-processed
            "M4A File Path": {"rich_text": []},  # Clear file paths
            "AIFF File Path": {"rich_text": []},
            "WAV File Path": {"rich_text": []},
            "Download Source": {"rich_text": []},  # Clear download source
        })
        print(f"   ✓ Updated SoundCloud URL to: {soundcloud_url}")
        print(f"   ✓ Cleared YouTube URL")
        print(f"   ✓ Reset Downloaded flag")
        print(f"   ✓ Cleared file paths")
        return True
    except Exception as e:
        print(f"   ✗ Failed to update Notion: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    page_id = '2e6e7361-6c27-8007-b3f6-e8f46b9e8233'
    soundcloud_url = 'https://soundcloud.com/zekebeats/zeke-beats-louder-final-sep-1'
    
    print("=" * 80)
    print("RE-PROCESSING LOUDER TRACK FROM SOUNDCLOUD")
    print("=" * 80)
    print(f"\n📄 Notion Page ID: {page_id}")
    print(f"🔗 SoundCloud URL: {soundcloud_url}\n")
    
    # Step 1: Clean up wrong files
    cleanup_wrong_files()
    
    # Step 2: Update Notion
    if not update_notion_soundcloud_url(page_id, soundcloud_url):
        print("\n❌ Failed to update Notion. Aborting.")
        return 1
    
    # Step 3: Re-process the track
    print(f"\n🔄 Re-processing track from SoundCloud...")
    print(f"   URL: {soundcloud_url}\n")
    
    try:
        page = module.notion_manager._req('get', f'/pages/{page_id}')
        if page:
            result = module.process_track(page)
            if result:
                print("\n" + "=" * 80)
                print("✅ SUCCESS: Track re-processed correctly from SoundCloud!")
                print("=" * 80)
                return 0
            else:
                print("\n" + "=" * 80)
                print("❌ FAILED: Track processing failed")
                print("=" * 80)
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
