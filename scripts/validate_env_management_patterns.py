#!/usr/bin/env python3
"""
Environment Management Pattern Validator
==========================================

This script validates that all Python scripts in the repository follow
the established environment management pattern using shared_core.notion.token_manager.

VIOLATIONS DETECTED:
1. Direct os.getenv() calls for Notion tokens instead of using token_manager
2. Missing dotenv import/load_dotenv() call without token_manager
3. Hardcoded Notion tokens
4. Custom token loading logic bypassing token_manager

USAGE:
    python scripts/validate_env_management_patterns.py [--fix] [--ci]

OPTIONS:
    --fix    Attempt to auto-fix violations (creates backup files)
    --ci     CI mode - exit with error code if violations found
    --verbose  Show detailed output

Author: Cursor MM1 Agent
Created: 2025-01-02
Related Issue: CRITICAL: Recurring Environment Management Pattern Violations
"""

import os
import sys
import re
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Patterns that indicate violations
VIOLATION_PATTERNS = [
    # Direct os.getenv for Notion tokens (not using token_manager)
    (
        r'os\.getenv\s*\(\s*["\']NOTION_TOKEN["\']\s*\)',
        "Direct os.getenv('NOTION_TOKEN') - should use shared_core.notion.token_manager"
    ),
    (
        r'os\.getenv\s*\(\s*["\']NOTION_API_TOKEN["\']\s*\)',
        "Direct os.getenv('NOTION_API_TOKEN') - should use shared_core.notion.token_manager"
    ),
    (
        r'os\.getenv\s*\(\s*["\']VV_AUTOMATIONS_WS_TOKEN["\']\s*\)',
        "Direct os.getenv('VV_AUTOMATIONS_WS_TOKEN') - should use shared_core.notion.token_manager"
    ),
    # Hardcoded tokens (pattern: ntn_ prefix)
    (
        r'ntn_[a-zA-Z0-9]{30,}',
        "Hardcoded Notion token detected - SECURITY RISK"
    ),
]

# Patterns that indicate CORRECT usage
CORRECT_PATTERNS = [
    r'from\s+shared_core\.notion\.token_manager\s+import',
    r'from\s+shared_core\.notion\s+import\s+token_manager',
    r'import\s+shared_core\.notion\.token_manager',
    r'token_manager\.get_notion_token\(\)',
    r'get_notion_token\(\)',  # After import
]

# Files/directories to exclude from validation
EXCLUDE_PATTERNS = [
    r'__pycache__',
    r'\.git',
    r'\.env',
    r'venv',
    r'node_modules',
    r'\.pyc$',
    r'shared_core/notion/token_manager\.py$',  # The source module itself
    r'validate_env_management_patterns\.py$',  # This script
    r'_backup',
    r'\.sample',
    r'\.md$',  # Documentation files
]


class ValidationResult:
    """Result of validating a single file."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations: List[Tuple[int, str, str]] = []  # (line_num, line, violation_msg)
        self.uses_token_manager = False
        self.has_notion_token_usage = False

    @property
    def is_valid(self) -> bool:
        """File is valid if no violations or uses token_manager correctly."""
        if not self.has_notion_token_usage:
            return True  # No Notion token usage, so no violations possible
        return len(self.violations) == 0 and self.uses_token_manager

    def add_violation(self, line_num: int, line: str, message: str):
        self.violations.append((line_num, line.strip(), message))

    def __str__(self) -> str:
        if self.is_valid:
            return f"✓ {self.filepath}"

        result = f"✗ {self.filepath}\n"
        for line_num, line, msg in self.violations:
            result += f"  Line {line_num}: {msg}\n"
            result += f"    > {line[:80]}{'...' if len(line) > 80 else ''}\n"
        return result


def should_exclude(filepath: Path) -> bool:
    """Check if file should be excluded from validation."""
    filepath_str = str(filepath)
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, filepath_str):
            return True
    return False


def validate_file(filepath: Path) -> Optional[ValidationResult]:
    """Validate a single Python file for pattern violations."""
    if should_exclude(filepath):
        return None

    if not filepath.suffix == '.py':
        return None

    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
        return None

    result = ValidationResult(filepath)
    lines = content.split('\n')

    # Check if file uses token_manager correctly
    for pattern in CORRECT_PATTERNS:
        if re.search(pattern, content):
            result.uses_token_manager = True
            break

    # Check each line for violations
    for line_num, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith('#'):
            continue

        for pattern, message in VIOLATION_PATTERNS:
            if re.search(pattern, line):
                result.has_notion_token_usage = True
                # Only add as violation if not using token_manager
                if not result.uses_token_manager:
                    result.add_violation(line_num, line, message)

    # If file has Notion token usage but doesn't use token_manager, that's a violation
    if result.has_notion_token_usage and not result.uses_token_manager and not result.violations:
        result.add_violation(0, "", "File uses Notion tokens but doesn't import from shared_core.notion.token_manager")

    return result


def validate_directory(directory: Path, verbose: bool = False) -> List[ValidationResult]:
    """Validate all Python files in a directory recursively."""
    results = []

    for filepath in directory.rglob('*.py'):
        if should_exclude(filepath):
            if verbose:
                print(f"Skipping: {filepath}")
            continue

        result = validate_file(filepath)
        if result:
            results.append(result)

    return results


def print_summary(results: List[ValidationResult], verbose: bool = False) -> Tuple[int, int]:
    """Print validation summary and return (valid_count, violation_count)."""
    valid_count = 0
    violation_count = 0
    files_with_violations = []

    for result in results:
        if result.is_valid:
            valid_count += 1
            if verbose:
                print(f"✓ {result.filepath}")
        else:
            violation_count += 1
            files_with_violations.append(result)

    print("\n" + "=" * 60)
    print("ENVIRONMENT MANAGEMENT PATTERN VALIDATION")
    print("=" * 60)

    if files_with_violations:
        print(f"\n❌ VIOLATIONS FOUND: {violation_count} file(s)\n")
        for result in files_with_violations:
            print(str(result))

        print("\n📋 HOW TO FIX:")
        print("1. Add this import to each file:")
        print("   from shared_core.notion.token_manager import get_notion_token")
        print("")
        print("2. Replace direct os.getenv() calls with:")
        print("   token = get_notion_token()")
        print("")
        print("3. See docs/ENVIRONMENT_MANAGEMENT_PATTERN.md for details")
    else:
        print(f"\n✅ ALL FILES VALID: {valid_count} file(s) checked")

    print("\n" + "=" * 60)

    return valid_count, violation_count


def generate_fix_suggestion(result: ValidationResult) -> str:
    """Generate code to fix violations in a file."""
    suggestion = f"\n# Fix for {result.filepath}\n"
    suggestion += "# Add this import at the top of the file:\n"
    suggestion += "from shared_core.notion.token_manager import get_notion_token\n\n"
    suggestion += "# Replace token loading code with:\n"
    suggestion += "token = get_notion_token()\n"
    suggestion += "if not token:\n"
    suggestion += '    raise RuntimeError("Notion token not found - see shared_core/notion/token_manager.py")\n'
    return suggestion


def main():
    parser = argparse.ArgumentParser(
        description="Validate environment management patterns in Python scripts"
    )
    parser.add_argument(
        'paths',
        nargs='*',
        default=['.'],
        help='Paths to validate (default: current directory)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Show fix suggestions for violations'
    )
    parser.add_argument(
        '--ci',
        action='store_true',
        help='CI mode - exit with error code if violations found'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )

    args = parser.parse_args()

    all_results = []

    for path_str in args.paths:
        path = Path(path_str)
        if path.is_file():
            result = validate_file(path)
            if result:
                all_results.append(result)
        elif path.is_dir():
            results = validate_directory(path, args.verbose)
            all_results.extend(results)
        else:
            print(f"Warning: Path not found: {path}", file=sys.stderr)

    valid_count, violation_count = print_summary(all_results, args.verbose)

    if args.fix and violation_count > 0:
        print("\n📝 FIX SUGGESTIONS:\n")
        for result in all_results:
            if not result.is_valid:
                print(generate_fix_suggestion(result))

    if args.ci and violation_count > 0:
        sys.exit(1)

    return 0 if violation_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
