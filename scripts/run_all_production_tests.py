#!/usr/bin/env python3
"""
Run All Production Tests

Executes all test scripts for the work completed in this session.
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Test scripts to run
TEST_SCRIPTS = [
    'scripts/test_drivesheets_race_condition_fix.py',
    'scripts/test_agent_handoffs.py',
    'scripts/test_oauth_credentials_config.py',
]

def run_test(script_path):
    """Run a test script and return results."""
    print(f"\n{'='*80}")
    print(f"Running: {script_path}")
    print('='*80)
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        return {
            'script': script_path,
            'passed': result.returncode == 0,
            'returncode': result.returncode,
            'output': result.stdout,
            'error': result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            'script': script_path,
            'passed': False,
            'returncode': -1,
            'output': '',
            'error': 'Test timed out after 60 seconds'
        }
    except Exception as e:
        return {
            'script': script_path,
            'passed': False,
            'returncode': -1,
            'output': '',
            'error': str(e)
        }

def main():
    """Run all tests and generate report."""
    print("="*80)
    print("PRODUCTION TEST SUITE - Session Work Verification")
    print("="*80)
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    results = []
    for script in TEST_SCRIPTS:
        script_path = Path(__file__).parent.parent / script
        if not script_path.exists():
            print(f"⚠️  Test script not found: {script_path}")
            results.append({
                'script': script,
                'passed': False,
                'returncode': -1,
                'output': '',
                'error': 'Script not found'
            })
            continue
        
        result = run_test(script_path)
        results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r['passed'])
    total = len(results)
    
    for result in results:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{status} {result['script']}")
        if not result['passed'] and result['error']:
            print(f"      Error: {result['error']}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    print(f"Completed: {datetime.now().isoformat()}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ All session work verified and ready for production")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("Review test output above for details")
        return 1

if __name__ == '__main__':
    sys.exit(main())
