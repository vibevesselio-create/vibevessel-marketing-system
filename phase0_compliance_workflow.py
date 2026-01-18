#!/usr/bin/env python3
"""
Phase 0: System Compliance Verification
Music Directories & Eagle Libraries Documentation
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from unified_config import load_unified_env, get_unified_config
    from shared_core.notion.token_manager import get_notion_client
    from scripts.music_library_remediation import load_music_directories
except ImportError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    sys.exit(1)

MUSIC_EXTENSIONS = {'.aiff', '.aif', '.wav', '.m4a', '.mp3', '.flac', '.alac'}

def scan_primary_music_directories() -> List[str]:
    """Scan primary music directories (not library files)."""
    directories = set()
    
    # Primary scan locations from plan
    scan_paths = [
        Path('/Users/brianhellemn/Music/Downloads'),
        Path('/Volumes/VIBES/Playlists'),
        Path('/Volumes/VIBES/Djay-Pro-Auto-Import'),
        Path('/Volumes/VIBES/Apple-Music-Auto-Add'),
    ]
    
    # Also check mounted volumes
    volumes_path = Path('/Volumes')
    if volumes_path.exists():
        for vol in volumes_path.iterdir():
            if vol.is_dir() and not vol.name.startswith('.'):
                for subdir in ['Music', 'Playlists', 'Djay-Pro-Auto-Import', 'Apple-Music-Auto-Add']:
                    scan_paths.append(vol / subdir)
    
    for base_path in scan_paths:
        if not base_path.exists():
            continue
        try:
            # Skip library files
            if '.library' in str(base_path):
                continue
                
            # Count music files at this level
            music_files = [f for f in base_path.iterdir() 
                          if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS]
            if music_files:
                directories.add(str(base_path))
            
            # Also check subdirectories (limited depth)
            for item in base_path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    sub_music = [f for f in item.rglob('*') 
                               if f.is_file() and f.suffix.lower() in MUSIC_EXTENSIONS]
                    if sub_music:
                        directories.add(str(base_path))
                        break  # Found music, include parent
        except (PermissionError, OSError) as e:
            print(f"Warning: Could not scan {base_path}: {e}", file=sys.stderr)
    
    return sorted(directories)

def main():
    load_unified_env()
    config = get_unified_config()
    
    # Get database ID
    db_id = config.get('music_directories_db_id') or os.getenv('MUSIC_DIRECTORIES_DB_ID', '')
    
    # Check phase0 report for existing ID
    phase0_report = PROJECT_ROOT / 'phase0_compliance_report.json'
    if not db_id and phase0_report.exists():
        try:
            with open(phase0_report) as f:
                data = json.load(f)
                db_id = data.get('music_directories_db_id', '')
        except:
            pass
    
    print(f"Music Directories DB ID: {db_id or 'NOT CONFIGURED'}")
    print(f"Eagle Library Path: {config.get('eagle_library_path', 'NOT CONFIGURED')}")
    
    # Scan local directories
    print("\nScanning local filesystem for music directories...")
    local_dirs = scan_primary_music_directories()
    print(f"Found {len(local_dirs)} local directories with music files")
    for d in local_dirs[:20]:  # Show first 20
        print(f"  {d}")
    if len(local_dirs) > 20:
        print(f"  ... and {len(local_dirs) - 20} more")
    
    # Load from Notion if DB ID is configured
    documented_dirs = []
    if db_id:
        try:
            notion = get_notion_client()
            documented_dirs = load_music_directories(notion, db_id)
            print(f"\nFound {len(documented_dirs)} documented directories in Notion")
        except Exception as e:
            print(f"Warning: Could not load from Notion: {e}", file=sys.stderr)
    else:
        print("\n⚠️  MUSIC_DIRECTORIES_DB_ID not configured, skipping Notion check")
    
    # Create compliance report
    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "music_directories_db_id": db_id,
        "eagle_library_path": config.get("eagle_library_path", ""),
        "local_directories_count": len(local_dirs),
        "local_directories": local_dirs[:100],  # Limit to first 100
        "documented_directories_count": len(documented_dirs),
        "documented_directories": documented_dirs[:100],  # Limit to first 100
        "compliance_status": "UNKNOWN"
    }
    
    # Save report
    report_path = PROJECT_ROOT / 'phase0_compliance_report.json'
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
