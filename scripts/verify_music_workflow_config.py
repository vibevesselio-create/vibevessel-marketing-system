#!/usr/bin/env python3
"""
Music Workflow Configuration Verification Script

Verifies that all required environment variables and database IDs are configured
correctly for the music track sync workflow.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def check_environment_variable(var_name: str, fallback: str = None, required: bool = True) -> tuple[bool, str, str]:
    """Check if an environment variable is set."""
    value = os.getenv(var_name)
    if value:
        return True, value, "Set"
    elif fallback:
        return True, fallback, f"Using fallback: {fallback}"
    elif required:
        return False, "", f"Required but not set"
    else:
        return True, "", "Optional, not set"

def verify_database_id(db_id: str, name: str) -> bool:
    """Verify database ID format (UUID-like)."""
    if not db_id:
        return False
    # Check if it looks like a UUID (32 hex chars with optional hyphens)
    cleaned = db_id.replace("-", "")
    return len(cleaned) == 32 and all(c in "0123456789abcdefABCDEF" for c in cleaned)

def verify_production_script() -> tuple[bool, str]:
    """Verify production script exists and is accessible."""
    script_path = project_root / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if script_path.exists():
        return True, str(script_path)
    return False, "Script not found"

def main():
    """Main verification function."""
    print("=" * 80)
    print("Music Workflow Configuration Verification")
    print("=" * 80)
    print()
    
    all_valid = True
    results = []
    
    # Check required environment variables
    print("Environment Variables:")
    print("-" * 80)
    
    checks = [
        ("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640", True),
        ("ARTISTS_DB_ID", "20ee7361-6c27-816d-9817-d4348f6de07c", False),
        ("SOUNDCLOUD_PROFILE", "vibe-vessel", False),
        ("NOTION_TOKEN", None, True),
        ("SPOTIFY_CLIENT_ID", None, False),
        ("SPOTIFY_CLIENT_SECRET", None, False),
    ]
    
    for var_name, fallback, required in checks:
        is_valid, value, status = check_environment_variable(var_name, fallback, required)
        status_icon = "✓" if is_valid else "✗"
        print(f"  {status_icon} {var_name:25} {status}")
        if value and ("DB_ID" in var_name):
            if verify_database_id(value, var_name):
                print(f"    → Valid format: {value[:8]}...")
            else:
                print(f"    → WARNING: Invalid format: {value}")
                all_valid = False
        elif not is_valid:
            all_valid = False
        results.append((var_name, is_valid, value, status))
    
    print()
    
    # Check production script
    print("Production Script:")
    print("-" * 80)
    script_valid, script_path = verify_production_script()
    if script_valid:
        print(f"  ✓ Found: {script_path}")
    else:
        print(f"  ✗ {script_path}")
        all_valid = False
    
    print()
    
    # Summary
    print("=" * 80)
    if all_valid:
        print("✓ All critical configurations are valid")
        return 0
    else:
        print("✗ Some configurations are missing or invalid")
        print()
        print("Missing/Invalid items:")
        for var_name, is_valid, value, status in results:
            if not is_valid:
                print(f"  - {var_name}: {status}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
