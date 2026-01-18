#!/usr/bin/env python3
"""
DriveSheetsSync Race Condition Fix - Code Verification Test

This script verifies that the race condition fix (commit a7d8c35) is properly
implemented in the Code.js file by checking code patterns and structure.

Note: This is a code verification test, not a runtime test. Runtime tests
should be performed in the Apps Script environment.
"""

import re
import sys
from pathlib import Path

# Path to Code.js
CODE_JS_PATH = Path(__file__).parent.parent / "gas-scripts" / "drive-sheets-sync" / "Code.js"


def read_code_file():
    """Read the Code.js file."""
    try:
        with open(CODE_JS_PATH, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"❌ ERROR: Code.js not found at {CODE_JS_PATH}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: Failed to read Code.js: {e}")
        sys.exit(1)


def verify_race_condition_fix(code):
    """Verify that ensureDbFolder_() uses lock-first pattern."""
    print("\n=== Race Condition Fix Verification ===")
    
    checks = {
        'lock_before_check': False,
        'lock_in_finally': False,
        'exponential_backoff': False,
        'error_handling': False,
        'lock_release': False
    }
    
    # Check 1: Lock acquired before folder checks
    # Pattern: LockService.getScriptLock() appears before findMatchingFolders_()
    lock_pattern = r'const\s+lock\s*=\s*LockService\.getScriptLock\(\)'
    find_folders_pattern = r'findMatchingFolders_\(\)'
    
    lock_positions = [m.start() for m in re.finditer(lock_pattern, code)]
    find_folders_positions = [m.start() for m in re.finditer(find_folders_pattern, code)]
    
    # Find ensureDbFolder_ function
    ensure_db_folder_match = re.search(r'function\s+ensureDbFolder_\([^)]*\)\s*\{', code)
    if ensure_db_folder_match:
        function_start = ensure_db_folder_match.start()
        # Get function code (check first 3000 chars which should contain the lock logic)
        function_code = code[function_start:function_start + 3000]
        
        # Find positions of lock acquisition and findMatchingFolders call
        lock_match = re.search(lock_pattern, function_code)
        find_match = re.search(find_folders_pattern, function_code)
        
        if lock_match and find_match:
            # Lock should be acquired before findMatchingFolders is called
            # Also verify findMatchingFolders is inside a try block after lock
            lock_pos = lock_match.start()
            find_pos = find_match.start()
            
            # Check that lock comes before findMatchingFolders
            if lock_pos < find_pos:
                # Verify findMatchingFolders is inside a try block that comes after lock
                # Look for try block between lock and findMatchingFolders
                code_between = function_code[lock_pos:find_pos]
                try_before_find = re.search(r'try\s*\{', code_between)
                checks['lock_before_check'] = try_before_find is not None
            else:
                checks['lock_before_check'] = False
        else:
            checks['lock_before_check'] = False
    
    # Check 2: Lock released in finally block
    finally_pattern = r'finally\s*\{[^}]*lock\.releaseLock\(\)'
    checks['lock_in_finally'] = bool(re.search(finally_pattern, code, re.DOTALL))
    
    # Check 3: Exponential backoff retry logic
    backoff_pattern = r'\[1000,\s*2000,\s*4000\]'
    checks['exponential_backoff'] = bool(re.search(backoff_pattern, code))
    
    # Check 4: Error handling for lock timeout
    # Look for pattern where lockAcquired check leads to error throw
    error_pattern1 = r'if\s*\(!lockAcquired\)[\s\S]{0,1000}throw\s+new\s+Error'
    error_pattern2 = r'Lock timeout.*deferring creation'
    checks['error_handling'] = (
        bool(re.search(error_pattern1, code, re.DOTALL)) or
        bool(re.search(error_pattern2, code, re.IGNORECASE))
    )
    
    # Check 5: Lock release in finally block
    release_pattern = r'finally\s*\{[\s\S]*?if\s*\(lockAcquired\)[\s\S]*?lock\.releaseLock\(\)'
    checks['lock_release'] = bool(re.search(release_pattern, code, re.DOTALL))
    
    # Report results
    print(f"Lock acquired before folder checks: {'✅' if checks['lock_before_check'] else '❌'}")
    print(f"Lock released in finally block: {'✅' if checks['lock_in_finally'] else '❌'}")
    print(f"Exponential backoff implemented: {'✅' if checks['exponential_backoff'] else '❌'}")
    print(f"Error handling for lock timeout: {'✅' if checks['error_handling'] else '❌'}")
    print(f"Lock release check: {'✅' if checks['lock_release'] else '❌'}")
    
    all_passed = all(checks.values())
    print(f"\nOverall Status: {'✅ FIX VERIFIED' if all_passed else '⚠️ ISSUES DETECTED'}")
    
    return {
        'passed': all_passed,
        'checks': checks
    }


def verify_concurrency_guard(code):
    """Verify that manualRunDriveSheets() has concurrency guard."""
    print("\n=== Concurrency Guard Verification ===")
    
    checks = {
        'lock_acquired': False,
        'clean_exit': False,
        'lock_released': False,
        'logging': False
    }
    
    # Check 1: Lock acquired in manualRunDriveSheets
    manual_run_pattern = r'function\s+manualRunDriveSheets\([^)]*\)\s*\{'
    lock_pattern = r'LockService\.getScriptLock\(\)'
    
    manual_run_match = re.search(manual_run_pattern, code)
    if manual_run_match:
        function_start = manual_run_match.start()
        function_code = code[function_start:function_start + 5000]  # Check first 5000 chars
        
        checks['lock_acquired'] = bool(re.search(lock_pattern, function_code))
    
    # Check 2: Clean exit when lock unavailable
    # Look for pattern where lock unavailable leads to return
    clean_exit_pattern1 = r'if\s*\(!lockAcquired\)[\s\S]{0,500}return'
    clean_exit_pattern2 = r'another run is already in progress.*Aborting'
    checks['clean_exit'] = (
        bool(re.search(clean_exit_pattern1, code, re.DOTALL)) or
        bool(re.search(clean_exit_pattern2, code, re.IGNORECASE))
    )
    
    # Check 3: Lock released in finally
    release_pattern = r'finally\s*\{[\s\S]*?lock\.releaseLock\(\)'
    checks['lock_released'] = bool(re.search(release_pattern, code, re.DOTALL))
    
    # Check 4: Proper logging
    logging_pattern = r'another run is already in progress'
    checks['logging'] = bool(re.search(logging_pattern, code))
    
    # Report results
    print(f"Lock acquired: {'✅' if checks['lock_acquired'] else '❌'}")
    print(f"Clean exit on lock failure: {'✅' if checks['clean_exit'] else '❌'}")
    print(f"Lock released in finally: {'✅' if checks['lock_released'] else '❌'}")
    print(f"Proper logging: {'✅' if checks['logging'] else '❌'}")
    
    all_passed = all(checks.values())
    print(f"\nOverall Status: {'✅ GUARD VERIFIED' if all_passed else '⚠️ ISSUES DETECTED'}")
    
    return {
        'passed': all_passed,
        'checks': checks
    }


def verify_commit_reference(code):
    """Verify that commit a7d8c35 fix is referenced in comments."""
    print("\n=== Commit Reference Verification ===")
    
    # Look for fix comments
    fix_patterns = [
        r'FIX\s+2026-01-18',
        r'race condition',
        r'acquire lock.*BEFORE',
        r'lock-first',
        r'a7d8c35'
    ]
    
    found_patterns = []
    for pattern in fix_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            found_patterns.append(pattern)
    
    print(f"Fix comments found: {len(found_patterns)}/{len(fix_patterns)}")
    for pattern in found_patterns:
        print(f"  ✅ {pattern}")
    for pattern in fix_patterns:
        if pattern not in found_patterns:
            print(f"  ⚠️  {pattern} (not found)")
    
    return len(found_patterns) >= 2  # At least 2 patterns should be found


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("DriveSheetsSync Race Condition Fix - Code Verification")
    print("=" * 60)
    print(f"\nTesting file: {CODE_JS_PATH}")
    
    code = read_code_file()
    print(f"File size: {len(code):,} characters")
    print(f"File lines: {len(code.splitlines()):,}")
    
    # Run verifications
    results = {
        'race_condition_fix': verify_race_condition_fix(code),
        'concurrency_guard': verify_concurrency_guard(code),
        'commit_reference': verify_commit_reference(code)
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = (
        results['race_condition_fix']['passed'] and
        results['concurrency_guard']['passed'] and
        results['commit_reference']
    )
    
    print(f"Race Condition Fix: {'✅ VERIFIED' if results['race_condition_fix']['passed'] else '❌ ISSUES'}")
    print(f"Concurrency Guard: {'✅ VERIFIED' if results['concurrency_guard']['passed'] else '❌ ISSUES'}")
    print(f"Commit Reference: {'✅ VERIFIED' if results['commit_reference'] else '⚠️ WARNING'}")
    print(f"\nOverall Status: {'✅ ALL TESTS PASSED' if all_passed else '⚠️ SOME ISSUES DETECTED'}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
