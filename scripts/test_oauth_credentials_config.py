#!/usr/bin/env python3
"""
GAS OAuth Credentials Configuration Verification Test

Verifies that OAuth credentials are properly configured and documented.
"""

import sys
from pathlib import Path

# Paths to check
CREDENTIALS_DIR = Path(__file__).parent.parent / "credentials" / "google-oauth"
CREDENTIALS_README = Path(__file__).parent.parent / "credentials" / "README.md"
GITIGNORE = Path(__file__).parent.parent / ".gitignore"


def verify_gitignore():
    """Verify that credentials are in .gitignore."""
    print("\n=== .gitignore Verification ===")
    
    if not GITIGNORE.exists():
        print("❌ .gitignore not found")
        return False
    
    with open(GITIGNORE, 'r', encoding='utf-8') as f:
        gitignore_content = f.read()
    
    # Check for credentials exclusion
    patterns_to_check = [
        'credentials/google-oauth/*.json',
        'credentials/google-oauth',
        '*.json'  # Less specific, but might be there
    ]
    
    found_patterns = []
    for pattern in patterns_to_check:
        if pattern in gitignore_content:
            found_patterns.append(pattern)
            print(f"  ✅ Found pattern: {pattern}")
    
    if not found_patterns:
        print("  ❌ No credentials exclusion pattern found")
        return False
    
    return True


def verify_readme():
    """Verify that README.md exists and has proper content."""
    print("\n=== README.md Verification ===")
    
    if not CREDENTIALS_README.exists():
        print("  ❌ README.md not found")
        return False
    
    with open(CREDENTIALS_README, 'r', encoding='utf-8') as f:
        readme_content = f.read()
    
    # Check for key content
    required_content = [
        'desktop_credentials.json',
        'OAuth',
        'GAS_API_CREDENTIALS_PATH',
        'brian@serenmedia.co',
        'installed',
        'web'
    ]
    
    found_content = []
    missing_content = []
    
    for content in required_content:
        if content in readme_content:
            found_content.append(content)
            print(f"  ✅ Found: {content}")
        else:
            missing_content.append(content)
            print(f"  ⚠️  Missing: {content}")
    
    return len(missing_content) == 0


def verify_directory_structure():
    """Verify that credentials directory structure is correct."""
    print("\n=== Directory Structure Verification ===")
    
    if not CREDENTIALS_DIR.exists():
        print(f"  ⚠️  Directory does not exist: {CREDENTIALS_DIR}")
        print("  (This is OK - credentials are gitignored)")
        return True  # Not an error, credentials are local-only
    
    # Check if directory is empty (expected - credentials are gitignored)
    files = list(CREDENTIALS_DIR.glob('*.json'))
    
    if len(files) == 0:
        print("  ✅ Directory exists but is empty (credentials gitignored - expected)")
    else:
        print(f"  ✅ Found {len(files)} credential file(s) (local only)")
        for file in files:
            print(f"    - {file.name}")
    
    return True


def main():
    """Run OAuth credentials configuration tests."""
    print("=" * 60)
    print("GAS OAuth Credentials Configuration Verification")
    print("=" * 60)
    
    results = {
        'gitignore': verify_gitignore(),
        'readme': verify_readme(),
        'directory': verify_directory_structure()
    }
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f".gitignore configured: {'✅' if results['gitignore'] else '❌'}")
    print(f"README.md complete: {'✅' if results['readme'] else '❌'}")
    print(f"Directory structure: {'✅' if results['directory'] else '❌'}")
    
    all_passed = all(results.values())
    print(f"\nOverall Status: {'✅ ALL TESTS PASSED' if all_passed else '⚠️ SOME ISSUES DETECTED'}")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
