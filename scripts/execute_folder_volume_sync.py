#!/usr/bin/env python3
"""
Execute Folder/Volume Sync to Notion
=====================================

This script executes the folder/volume synchronization to Notion databases.
It sets the required environment variables and runs the sync script.

Part of Phase 3: Remediation
"""

import os
import sys
import subprocess
from pathlib import Path

# Set required environment variables
FOLDERS_DB_ID = "26ce7361-6c27-81bb-81b7-dd43760ee6cc"
VOLUMES_DB_ID = "26ce7361-6c27-8148-8719-fbd26a627d17"

# Set environment variables
os.environ["FOLDERS_DATABASE_ID"] = FOLDERS_DB_ID
os.environ["VOLUMES_DATABASE_ID"] = VOLUMES_DB_ID

# Ensure NOTION_TOKEN is set
if not os.getenv("NOTION_TOKEN") and not os.getenv("NOTION_API_KEY"):
    print("ERROR: NOTION_TOKEN or NOTION_API_KEY environment variable not set")
    sys.exit(1)

# Get the sync script path
workspace_root = Path(__file__).parent.parent
sync_script = workspace_root / "sync_folders_volumes_to_notion.py"

if not sync_script.exists():
    print(f"ERROR: Sync script not found at {sync_script}")
    sys.exit(1)

print("=" * 70)
print("Folder/Volume Synchronization to Notion")
print("=" * 70)
print(f"FOLDERS_DATABASE_ID: {FOLDERS_DB_ID}")
print(f"VOLUMES_DATABASE_ID: {VOLUMES_DB_ID}")
print(f"Sync Script: {sync_script}")
print()

# Execute the sync script
try:
    result = subprocess.run(
        [sys.executable, str(sync_script)],
        env=os.environ.copy(),
        capture_output=False,
        text=True
    )
    
    if result.returncode == 0:
        print("\n✅ Folder/Volume sync completed successfully")
        sys.exit(0)
    else:
        print(f"\n❌ Folder/Volume sync failed with exit code {result.returncode}")
        sys.exit(result.returncode)
        
except Exception as e:
    print(f"\n❌ Error executing sync script: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
