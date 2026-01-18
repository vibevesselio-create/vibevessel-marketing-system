#!/usr/bin/env python3
"""
Verification Script for Playlist Organization Issue
Verifies that playlist track organization is working correctly in production workflow.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def verify_argparse_choices():
    """Verify that --mode playlist is in argparse choices."""
    print("=" * 80)
    print("VERIFICATION 1: Checking argparse choices for --mode playlist")
    print("=" * 80)
    
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for playlist in choices
    if 'choices=["single","batch","all","reprocess","url","dedup","fp-sync","merge","playlist"]' in content:
        print("✅ VERIFIED: --mode playlist is in argparse choices")
        return True
    elif '"playlist"' in content and 'choices=' in content:
        print("✅ VERIFIED: --mode playlist found in argparse (format may vary)")
        return True
    else:
        print("❌ FAILED: --mode playlist not found in argparse choices")
        return False

def verify_sync_script_mode():
    """Verify that sync_soundcloud_playlist.py uses --mode playlist."""
    print("\n" + "=" * 80)
    print("VERIFICATION 2: Checking sync_soundcloud_playlist.py uses --mode playlist")
    print("=" * 80)
    
    script_path = project_root / "scripts" / "sync_soundcloud_playlist.py"
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for --mode playlist usage
    if '--mode", "playlist' in content or '--mode", "playlist"' in content:
        print("✅ VERIFIED: sync_soundcloud_playlist.py uses --mode playlist")
        return True
    else:
        print("❌ FAILED: sync_soundcloud_playlist.py does not use --mode playlist")
        # Check what it actually uses
        if '--mode", "batch' in content:
            print("   ⚠️  Found: --mode batch (should be playlist)")
        return False

def verify_playlist_filtering():
    """Verify that playlist filtering logic exists."""
    print("\n" + "=" * 80)
    print("VERIFICATION 3: Checking playlist filtering logic")
    print("=" * 80)
    
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    checks = {
        "find_tracks_with_playlist_relations function": "def find_tracks_with_playlist_relations" in content,
        "playlist filter criteria": 'filter_criteria == "playlist"' in content,
        "get_playlist_names_from_track function": "def get_playlist_names_from_track" in content,
        "playlist directory organization": ('playlist_names = get_playlist_names_from_track' in content or 'get_playlist_names_from_track(track' in content),
    }
    
    all_passed = True
    for check_name, result in checks.items():
        if result:
            print(f"✅ VERIFIED: {check_name}")
        else:
            print(f"❌ FAILED: {check_name}")
            all_passed = False
    
    return all_passed

def verify_playlist_property_names():
    """Verify that playlist property name checking is comprehensive."""
    print("\n" + "=" * 80)
    print("VERIFICATION 4: Checking playlist property name handling")
    print("=" * 80)
    
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Check for multiple property name candidates
    property_candidates = [
        "Playlist",
        "Playlists",
        "Playlist Title",
        "Playlist Name",
    ]
    
    found_candidates = []
    for prop in property_candidates:
        if f'"{prop}"' in content or f"'{prop}'" in content:
            found_candidates.append(prop)
    
    if len(found_candidates) >= 2:
        print(f"✅ VERIFIED: Multiple playlist property name candidates found: {found_candidates}")
        return True
    else:
        print(f"⚠️  WARNING: Only found {len(found_candidates)} property name candidates: {found_candidates}")
        return len(found_candidates) > 0

def main():
    """Run all verifications."""
    print("\n" + "=" * 80)
    print("PLAYLIST ORGANIZATION FIX VERIFICATION")
    print("=" * 80)
    print(f"Project Root: {project_root}")
    print(f"Timestamp: {__import__('datetime').datetime.now().isoformat()}")
    
    results = {
        "argparse_choices": verify_argparse_choices(),
        "sync_script_mode": verify_sync_script_mode(),
        "playlist_filtering": verify_playlist_filtering(),
        "property_names": verify_playlist_property_names(),
    }
    
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    all_passed = all(results.values())
    
    for check_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    if all_passed:
        print("\n✅ ALL VERIFICATIONS PASSED")
        print("   The fixes mentioned in the issue appear to be already implemented.")
        print("   Recommendation: Update issue status to 'Resolved' after manual testing.")
        return 0
    else:
        print("\n⚠️  SOME VERIFICATIONS FAILED")
        print("   Review the failures above and implement missing fixes.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
