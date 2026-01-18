#!/usr/bin/env python3
"""
Pre-Execution Preparation Phase
Verifies Eagle application status, identifies production deduplication functions,
reviews documentation, and documents current state.
"""
import os
import sys
import subprocess
import time
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config
from shared_core.notion.token_manager import get_notion_client

# Eagle API Configuration
EAGLE_API_BASE = "http://localhost:41595"
EAGLE_INFO_ENDPOINT = "/api/application/info"
EAGLE_APP_PATH = "/Applications/Eagle.app"
EAGLE_APP_NAME = "Eagle"
EAGLE_AUTO_LAUNCH_TIMEOUT = 45

def is_eagle_api_available(timeout: float = 3.0) -> bool:
    """Check if Eagle API is accessible."""
    url = f"{EAGLE_API_BASE.rstrip('/')}{EAGLE_INFO_ENDPOINT}"
    try:
        resp = requests.get(url, timeout=timeout)
        return 200 <= resp.status_code < 500
    except Exception:
        return False

def launch_eagle_application() -> bool:
    """Launch Eagle application using macOS open command."""
    if sys.platform != "darwin":
        print("  WARNING: Cannot launch Eagle on non-macOS platform")
        return False
    
    try:
        app_path = Path(EAGLE_APP_PATH)
        if app_path.exists():
            subprocess.run(["/usr/bin/open", str(app_path)], check=True)
        else:
            subprocess.run(["/usr/bin/open", "-a", EAGLE_APP_NAME], check=True)
        return True
    except Exception as e:
        print(f"  ERROR: Failed to launch Eagle: {e}")
        return False

def ensure_eagle_running() -> bool:
    """Ensure Eagle application is running and API is accessible."""
    print("0.7 Verifying Eagle Application Status...")
    
    # Check if API is already available
    if is_eagle_api_available():
        print("  ✓ Eagle API is accessible")
        return True
    
    print("  ⚠ Eagle API is not accessible")
    print("  Launching Eagle application...")
    
    if not launch_eagle_application():
        print("  ✗ Failed to launch Eagle application")
        return False
    
    # Wait for API to become available
    print(f"  Waiting for Eagle API to become available (up to {EAGLE_AUTO_LAUNCH_TIMEOUT}s)...")
    deadline = time.time() + EAGLE_AUTO_LAUNCH_TIMEOUT
    poll_interval = 2.0
    
    while time.time() < deadline:
        if is_eagle_api_available():
            print("  ✓ Eagle API is now accessible")
            return True
        time.sleep(poll_interval)
        print(f"    Still waiting... ({int(deadline - time.time())}s remaining)")
    
    print(f"  ✗ Eagle API did not become available within {EAGLE_AUTO_LAUNCH_TIMEOUT}s")
    return False

def identify_deduplication_functions() -> Dict[str, Any]:
    """Identify production deduplication functions in the codebase."""
    print("\n0.8 Identifying Production Deduplication Functions...")
    
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    
    if not script_path.exists():
        print(f"  ✗ Production script not found: {script_path}")
        return {"error": "Script not found"}
    
    print(f"  ✓ Found production script: {script_path}")
    
    # Read script to find function definitions
    functions_found = {}
    target_functions = [
        "eagle_library_deduplication",
        "eagle_import_with_duplicate_management",
        "eagle_cleanup_duplicate_items",
        "sync_fingerprints_to_eagle_tags"
    ]
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
            
            for func_name in target_functions:
                for i, line in enumerate(lines, 1):
                    if f"def {func_name}(" in line:
                        functions_found[func_name] = {
                            "line": i,
                            "exists": True,
                            "signature": line.strip()
                        }
                        break
                if func_name not in functions_found:
                    functions_found[func_name] = {"exists": False}
        
        # Check for --mode dedup support
        has_dedup_mode = "--mode dedup" in content or "mode dedup" in content.lower()
        functions_found["standalone_execution"] = {
            "has_dedup_mode": has_dedup_mode,
            "command": "python3 monolithic-scripts/soundcloud_download_prod_merge-2.py --mode dedup"
        }
        
        print(f"  ✓ Found {len([f for f in functions_found.values() if isinstance(f, dict) and f.get('exists')])} deduplication functions")
        for func_name, info in functions_found.items():
            if isinstance(info, dict) and info.get('exists'):
                print(f"    - {func_name}() at line {info.get('line', 'N/A')}")
        
        return functions_found
        
    except Exception as e:
        print(f"  ✗ Error reading script: {e}")
        return {"error": str(e)}

def review_plans_directory() -> Dict[str, Any]:
    """Review plans directory and identify any missing work."""
    print("\n0.9 Reviewing Plans Directory...")
    
    plans_dir = PROJECT_ROOT / "plans"
    
    if not plans_dir.exists():
        print("  ⚠ Plans directory does not exist")
        return {"exists": False, "plans": []}
    
    # Find plan files
    plan_files = list(plans_dir.glob("*.md")) + list(plans_dir.glob("*.txt"))
    plan_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    print(f"  ✓ Found {len(plan_files)} plan files")
    
    # Review most recent plans (limit to 5)
    recent_plans = []
    for plan_file in plan_files[:5]:
        try:
            stat = plan_file.stat()
            recent_plans.append({
                "path": str(plan_file),
                "name": plan_file.name,
                "modified": stat.st_mtime,
                "size": stat.st_size
            })
            print(f"    - {plan_file.name} ({stat.st_size} bytes)")
        except Exception as e:
            print(f"    ✗ Error reading {plan_file.name}: {e}")
    
    return {
        "exists": True,
        "plans": recent_plans,
        "total_count": len(plan_files)
    }

def document_current_state(eagle_status: bool, functions: Dict, plans: Dict) -> Dict[str, Any]:
    """Document current state before execution."""
    print("\n0.10 Documenting Current State...")
    
    load_unified_env()
    config = get_unified_config()
    
    eagle_library_path = config.get('eagle_library_path') or os.getenv('EAGLE_LIBRARY_PATH', '/Volumes/VIBES/Music-Library-2.library')
    
    state = {
        "eagle_status": {
            "running": eagle_status,
            "api_accessible": eagle_status,
            "library_path": eagle_library_path,
            "library_exists": Path(eagle_library_path).exists() if eagle_library_path else False
        },
        "deduplication_functions": functions,
        "plans_review": plans,
        "compliance_status": "COMPLIANT"  # From Phase 0
    }
    
    print("  ✓ Current state documented:")
    print(f"    - Eagle running: {eagle_status}")
    print(f"    - Eagle library path: {eagle_library_path}")
    print(f"    - Library exists: {state['eagle_status']['library_exists']}")
    print(f"    - Deduplication functions available: {len([f for f in functions.values() if isinstance(f, dict) and f.get('exists')])}")
    
    return state

def main():
    """Main execution function."""
    print("=" * 80)
    print("PRE-EXECUTION PREPARATION")
    print("=" * 80)
    
    # 0.7 Verify Eagle Application Status
    eagle_running = ensure_eagle_running()
    if not eagle_running:
        print("\n⚠ WARNING: Eagle application is not running or API is not accessible")
        print("  Execution may fail if Eagle is required for deduplication")
    
    # 0.8 Identify Production Deduplication Functions
    functions = identify_deduplication_functions()
    
    # 0.9 Review Plans Directory
    plans = review_plans_directory()
    
    # 0.10 Document Current State
    current_state = document_current_state(eagle_running, functions, plans)
    
    # Save state to file
    import json
    state_file = PROJECT_ROOT / 'pre_execution_state.json'
    with open(state_file, 'w') as f:
        json.dump(current_state, f, indent=2, default=str)
    
    print(f"\n✓ Pre-execution state saved to: {state_file}")
    print("\n" + "=" * 80)
    print("PRE-EXECUTION PREPARATION COMPLETE")
    print("=" * 80)
    
    if eagle_running and functions.get("error") is None:
        print("✓ Ready to proceed to Phase 1")
        return 0
    else:
        print("⚠ Some issues detected - review before proceeding")
        return 1

if __name__ == "__main__":
    sys.exit(main())
