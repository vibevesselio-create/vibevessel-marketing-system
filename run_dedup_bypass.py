#!/usr/bin/env python3
"""
DEPRECATED: This script is deprecated. Use scripts/run_fingerprint_dedup_production.py instead.

This script previously allowed deduplication without fingerprint requirements, which led to
false positives (7,374 files incorrectly moved to trash). The correct workflow is:

1. Embed fingerprints in ALL files FIRST (scripts/batch_fingerprint_embedding.py)
2. Sync fingerprints to Eagle tags (scripts/sync_fingerprints_to_eagle.py)
3. THEN run deduplication that REQUIRES fingerprints (scripts/run_fingerprint_dedup_production.py)

This script now redirects to the proper production workflow.
"""

import sys
import os
from pathlib import Path

# Add the project directory to path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))

if __name__ == "__main__":
    print("\n" + "="*80)
    print("⚠️  DEPRECATED SCRIPT WARNING")
    print("="*80)
    print("\nThis script (run_dedup_bypass.py) is DEPRECATED.")
    print("It previously allowed deduplication without fingerprint requirements,")
    print("which led to false positives (7,374 files incorrectly moved to trash).")
    print("\nThe correct workflow is:")
    print("  1. Embed fingerprints FIRST: scripts/batch_fingerprint_embedding.py")
    print("  2. Sync to Eagle tags: scripts/sync_fingerprints_to_eagle.py")
    print("  3. Run deduplication: scripts/run_fingerprint_dedup_production.py")
    print("\n" + "="*80)
    print("Redirecting to proper production workflow...")
    print("="*80 + "\n")
    
    # Redirect to production script
    production_script = project_dir / "scripts" / "run_fingerprint_dedup_production.py"
    if production_script.exists():
        import subprocess
        sys.exit(subprocess.call([sys.executable, str(production_script)] + sys.argv[1:]))
    else:
        print("ERROR: Production script not found at:", production_script)
        print("Please use scripts/run_fingerprint_dedup_production.py directly.")
        sys.exit(1)
