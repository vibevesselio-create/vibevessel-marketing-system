#!/usr/bin/env python3
"""
Execute DriveSheetsSync via Apps Script API

Uses Google Apps Script API to execute manualRunDriveSheets() function.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from scripts.gas_api_direct_deployment import GASAPIDirectDeployment
except ImportError:
    print("❌ ERROR: Could not import GASAPIDirectDeployment")
    print("   Make sure scripts/gas_api_direct_deployment.py exists")
    sys.exit(1)

def execute_production_workflow():
    """Execute manualRunDriveSheets() via Apps Script API."""
    print("=" * 80)
    print("EXECUTING PRODUCTION WORKFLOW via Apps Script API")
    print("Function: manualRunDriveSheets()")
    print("=" * 80)
    print()
    
    script_id = "1n8vraQ0Rrfbeor7c3seWv2dh8saRVAJBJzgKm0oVQzgJrp5E1dLrAGf-"
    function_name = "manualRunDriveSheets"
    
    try:
        deployer = GASAPIDirectDeployment()
        
        print(f"Executing function: {function_name}")
        print(f"Script ID: {script_id}")
        print()
        
        # Execute the function
        result = deployer.execute_function(script_id, function_name)
        
        if result:
            print("✅ EXECUTION INITIATED")
            print(f"Execution ID: {result.get('execution_id', 'N/A')}")
            print(f"Status: {result.get('status', 'N/A')}")
            print()
            
            if result.get('response'):
                print("Response:")
                print(result['response'])
            
            return 0
        else:
            print("❌ EXECUTION FAILED")
            return 1
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(execute_production_workflow())
