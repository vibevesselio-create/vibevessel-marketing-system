#!/usr/bin/env python3
"""
Test DriveSheetsSync Fixes

This script validates that the fixes are working correctly by:
1. Checking code changes are deployed
2. Verifying API standardization
3. Testing error handling improvements
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def test_api_standardization():
    """Test that all database queries use data_sources API"""
    print("=" * 60)
    print("Testing API Standardization")
    print("=" * 60)
    
    code_file = project_root / "gas-scripts" / "drive-sheets-sync" / "Code.js"
    if not code_file.exists():
        print("❌ Code.js not found")
        return False
    
    content = code_file.read_text()
    
    # Check for legacy database endpoint usage
    legacy_patterns = [
        'databases/${dbId}/query',
        'databases/${databaseId}/query',
        'databases/` + dbId + `/query'
    ]
    
    found_legacy = []
    for pattern in legacy_patterns:
        if pattern in content:
            found_legacy.append(pattern)
    
    if found_legacy:
        print(f"⚠️  Found {len(found_legacy)} potential legacy endpoint usages:")
        for pattern in found_legacy:
            print(f"   - {pattern}")
        return False
    else:
        print("✅ No legacy database endpoint usage found")
        return True

def test_error_handling():
    """Test that error handling improvements are in place"""
    print("\n" + "=" * 60)
    print("Testing Error Handling")
    print("=" * 60)
    
    code_file = project_root / "gas-scripts" / "drive-sheets-sync" / "Code.js"
    content = code_file.read_text()
    
    # Check for improved error handling patterns
    checks = {
        "Early return on missing data_source_id": 'if (!dsId)' in content and 'Cannot query database - data_source_id not available' in content,
        "Warning logging": 'UL?.warn?.(' in content,
        "Graceful degradation": 'return []' in content or 'return null' in content
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        if passed:
            print(f"✅ {check_name}")
        else:
            print(f"❌ {check_name}")
            all_passed = False
    
    return all_passed

def test_archive_audit_function():
    """Test that archive audit function exists"""
    print("\n" + "=" * 60)
    print("Testing Archive Audit Function")
    print("=" * 60)
    
    diagnostic_file = project_root / "gas-scripts" / "drive-sheets-sync" / "DIAGNOSTIC_FUNCTIONS.js"
    if not diagnostic_file.exists():
        print("❌ DIAGNOSTIC_FUNCTIONS.js not found")
        return False
    
    content = diagnostic_file.read_text()
    
    if 'runArchiveFoldersAudit' in content:
        print("✅ Archive audit function found")
        return True
    else:
        print("❌ Archive audit function not found")
        return False

def test_property_matching():
    """Test that property matching enhancements are in place"""
    print("\n" + "=" * 60)
    print("Testing Property Matching")
    print("=" * 60)
    
    code_file = project_root / "gas-scripts" / "drive-sheets-sync" / "Code.js"
    content = code_file.read_text()
    
    # Check for exact match priority
    if 'strategy: \'exact\'' in content and 'priority: \'highest\'' in content:
        print("✅ Exact match priority documented")
        return True
    else:
        print("⚠️  Exact match priority may not be fully documented")
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("DriveSheetsSync Fixes Validation")
    print("=" * 60 + "\n")
    
    results = {
        "API Standardization": test_api_standardization(),
        "Error Handling": test_error_handling(),
        "Archive Audit Function": test_archive_audit_function(),
        "Property Matching": test_property_matching()
    }
    
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
























