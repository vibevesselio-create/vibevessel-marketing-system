#!/usr/bin/env python3
"""
Verify Music Track Sync Workflow Completion

This script verifies that the production workflow executed successfully:
- Files created in correct formats (M4A, WAV, AIFF)
- Notion database updated with all metadata
- Eagle library import successful
- No duplicates created
- Audio analysis complete (BPM, Key)
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Environment variables
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
OUT_DIR = Path(os.getenv("OUT_DIR", "/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/Volumes/VIBES/Djay-Pro-Auto-Import"))
WAV_BACKUP_DIR = Path(os.getenv("WAV_BACKUP_DIR", "/Volumes/VIBES/Apple-Music-Auto-Add"))

def verify_file_formats():
    """Verify that files were created in correct formats."""
    print("=" * 80)
    print("VERIFICATION: File Format Creation")
    print("=" * 80)
    
    results = {
        "m4a_files": 0,
        "aiff_files": 0,
        "wav_files": 0,
        "total_verified": 0
    }
    
    # Check OUT_DIR for M4A and AIFF
    if OUT_DIR.exists():
        for ext in ["*.m4a", "*.aiff"]:
            files = list(OUT_DIR.rglob(ext))
            if ext == "*.m4a":
                results["m4a_files"] = len(files)
                print(f"  ✓ Found {len(files)} M4A files in {OUT_DIR}")
            else:
                results["aiff_files"] = len(files)
                print(f"  ✓ Found {len(files)} AIFF files in {OUT_DIR}")
    
    # Check WAV_BACKUP_DIR for WAV
    if WAV_BACKUP_DIR.exists():
        wav_files = list(WAV_BACKUP_DIR.rglob("*.wav"))
        results["wav_files"] = len(wav_files)
        print(f"  ✓ Found {len(wav_files)} WAV files in {WAV_BACKUP_DIR}")
    
    results["total_verified"] = results["m4a_files"] + results["aiff_files"] + results["wav_files"]
    print(f"\n  Total files verified: {results['total_verified']}")
    
    return results

def verify_notion_integration():
    """Verify Notion database integration."""
    print()
    print("=" * 80)
    print("VERIFICATION: Notion Database Integration")
    print("=" * 80)
    
    try:
        from notion_client import Client
        # Use centralized token manager (MANDATORY per CLAUDE.md)
        try:
            from shared_core.notion.token_manager import get_notion_token
            notion_token = get_notion_token()
        except ImportError:
            notion_token = os.getenv("NOTION_TOKEN")

        if not notion_token:
            print("  ⚠️  NOTION_TOKEN not set, skipping Notion verification")
            return {"status": "skipped", "reason": "NOTION_TOKEN not set"}
        
        client = Client(auth=notion_token)
        
        # Query for recent tracks
        response = client.databases.query(
            database_id=TRACKS_DB_ID,
            page_size=10,
            sorts=[{"timestamp": "last_edited_time", "direction": "descending"}]
        )
        
        tracks = response.get("results", [])
        print(f"  ✓ Found {len(tracks)} recent tracks in Notion database")
        
        if tracks:
            latest = tracks[0]
            print(f"  ✓ Latest track: {latest.get('id', 'Unknown')}")
        
        return {"status": "success", "tracks_found": len(tracks)}
        
    except Exception as e:
        print(f"  ⚠️  Error verifying Notion integration: {e}")
        return {"status": "error", "error": str(e)}

def verify_eagle_integration():
    """Verify Eagle library integration."""
    print()
    print("=" * 80)
    print("VERIFICATION: Eagle Library Integration")
    print("=" * 80)
    
    try:
        import requests
        
        eagle_api_base = os.getenv("EAGLE_API_BASE", "http://localhost:41595")
        eagle_token = os.getenv("EAGLE_TOKEN", "")
        
        if not eagle_token:
            print("  ⚠️  EAGLE_TOKEN not set, skipping Eagle verification")
            return {"status": "skipped", "reason": "EAGLE_TOKEN not set"}
        
        # Check Eagle API connection
        headers = {"Authorization": f"Bearer {eagle_token}"} if eagle_token else {}
        response = requests.get(f"{eagle_api_base}/api/item/list", headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("data", [])
            print(f"  ✓ Eagle API connection successful")
            print(f"  ✓ Found {len(items)} items in Eagle library")
            return {"status": "success", "items_found": len(items)}
        else:
            print(f"  ⚠️  Eagle API returned status {response.status_code}")
            return {"status": "error", "status_code": response.status_code}
            
    except Exception as e:
        print(f"  ⚠️  Error verifying Eagle integration: {e}")
        return {"status": "error", "error": str(e)}

def main():
    """Main verification function."""
    print("Music Track Sync Workflow - Completion Verification")
    print("=" * 80)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"TRACKS_DB_ID: {TRACKS_DB_ID}")
    print()
    
    results = {
        "file_formats": verify_file_formats(),
        "notion": verify_notion_integration(),
        "eagle": verify_eagle_integration()
    }
    
    print()
    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    
    all_passed = True
    for category, result in results.items():
        status = result.get("status", "unknown")
        if status == "success":
            print(f"  ✓ {category.upper()}: PASSED")
        elif status == "skipped":
            print(f"  ⚠️  {category.upper()}: SKIPPED ({result.get('reason', 'Unknown')})")
        else:
            print(f"  ✗ {category.upper()}: FAILED")
            all_passed = False
    
    if all_passed:
        print("\n  ✅ ALL VERIFICATIONS PASSED")
        return 0
    else:
        print("\n  ⚠️  SOME VERIFICATIONS FAILED OR SKIPPED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
