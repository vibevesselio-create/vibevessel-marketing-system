#!/usr/bin/env python3
"""
Test script for Dropbox Music cleanup scripts.
Runs all three scripts in dry-run mode and documents results.
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime

def run_script(script_path: Path, args: list = None) -> dict:
    """Run a script and capture output."""
    if args is None:
        args = []
    
    cmd = ["python3", str(script_path)] + args
    print(f"\n{'='*80}")
    print(f"Running: {' '.join(cmd)}")
    print('='*80)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        return {
            "script": str(script_path),
            "command": ' '.join(cmd),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "script": str(script_path),
            "command": ' '.join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": "Script timed out after 5 minutes",
            "success": False
        }
    except Exception as e:
        return {
            "script": str(script_path),
            "command": ' '.join(cmd),
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "success": False
        }

def main():
    """Main test execution."""
    script_dir = Path(__file__).parent
    scripts_dir = script_dir / "scripts"
    
    scripts_to_test = [
        ("create_dropbox_music_structure.py", ["--dry-run"]),
        ("dropbox_music_deduplication.py", ["--dry-run"]),
        ("dropbox_music_migration.py", ["--dry-run"]),
    ]
    
    results = {
        "test_timestamp": datetime.now().isoformat(),
        "scripts_tested": [],
        "summary": {
            "total": len(scripts_to_test),
            "passed": 0,
            "failed": 0
        }
    }
    
    print("="*80)
    print("DROPBOX MUSIC SCRIPTS TEST SUITE")
    print("="*80)
    print(f"Test Date: {results['test_timestamp']}")
    print(f"Scripts to test: {len(scripts_to_test)}")
    print("="*80)
    
    for script_name, args in scripts_to_test:
        script_path = scripts_dir / script_name
        
        if not script_path.exists():
            print(f"\n❌ ERROR: Script not found: {script_path}")
            results["scripts_tested"].append({
                "script": script_name,
                "status": "not_found",
                "error": f"Script file does not exist: {script_path}"
            })
            results["summary"]["failed"] += 1
            continue
        
        # Run the script
        result = run_script(script_path, args)
        results["scripts_tested"].append(result)
        
        if result["success"]:
            print(f"\n✅ PASSED: {script_name}")
            results["summary"]["passed"] += 1
        else:
            print(f"\n❌ FAILED: {script_name}")
            print(f"Return code: {result['returncode']}")
            if result["stderr"]:
                print(f"Error output:\n{result['stderr']}")
            results["summary"]["failed"] += 1
        
        # Print stdout if available
        if result["stdout"]:
            print("\nOutput:")
            print(result["stdout"][:500])  # Limit output
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total scripts: {results['summary']['total']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print("="*80)
    
    # Save results to file
    results_file = script_dir / "dropbox_music_scripts_test_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    # Exit with appropriate code
    if results["summary"]["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
