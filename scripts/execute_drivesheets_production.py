#!/usr/bin/env python3
"""
Execute DriveSheetsSync Production Workflow

Uses Apps Script API to execute manualRunDriveSheets() function programmatically.
"""

import subprocess
import sys
import json
from pathlib import Path

def execute_production_workflow():
    """Execute manualRunDriveSheets() via clasp."""
    print("=" * 80)
    print("EXECUTING PRODUCTION WORKFLOW: manualRunDriveSheets()")
    print("=" * 80)
    print()
    
    script_dir = Path(__file__).parent.parent / "gas-scripts" / "drive-sheets-sync"
    
    if not script_dir.exists():
        print(f"❌ ERROR: Script directory not found: {script_dir}")
        return 1
    
    # Try to execute via clasp
    print("Attempting to execute via clasp...")
    print()
    
    try:
        # Try with nondev flag (production execution)
        result = subprocess.run(
            ['clasp', 'run', 'manualRunDriveSheets', '--nondev'],
            cwd=str(script_dir),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        print("STDOUT:")
        print(result.stdout)
        print()
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            print()
        
        if result.returncode == 0:
            print("✅ EXECUTION COMPLETED SUCCESSFULLY")
            return 0
        else:
            print(f"⚠️ Execution returned code: {result.returncode}")
            
            # If permission error, try without nondev
            if "permission" in result.stderr.lower() or "permission" in result.stdout.lower():
                print("\nTrying without --nondev flag...")
                result2 = subprocess.run(
                    ['clasp', 'run', 'manualRunDriveSheets'],
                    cwd=str(script_dir),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                print("STDOUT:")
                print(result2.stdout)
                print()
                
                if result2.stderr:
                    print("STDERR:")
                    print(result2.stderr)
                    print()
                
                if result2.returncode == 0:
                    print("✅ EXECUTION COMPLETED SUCCESSFULLY")
                    return 0
            
            return result.returncode
            
    except subprocess.TimeoutExpired:
        print("❌ ERROR: Execution timed out after 10 minutes")
        return 1
    except FileNotFoundError:
        print("❌ ERROR: clasp not found. Install with: npm install -g @google/clasp")
        return 1
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(execute_production_workflow())
