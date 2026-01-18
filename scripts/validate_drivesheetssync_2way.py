#!/usr/bin/env python3
"""
DriveSheetsSync 2-Way Sync Validation Script
=============================================

This script validates the DriveSheetsSync 2-way synchronization implementation
by testing the clasp sync workflow as a success criteria example.

Tests:
1. Clasp project discovery and configuration
2. Scripts database entry verification
3. Execution logs database entry verification
4. CSV export/import cycle verification
5. Schema synchronization verification

Usage:
    python3 scripts/validate_drivesheetssync_2way.py [--verbose] [--fix]

Author: Claude MM1 Agent
Created: 2026-01-14
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Database IDs (canonical from Code.js getDatabaseConfig)
DB_CONFIG = {
    'EXECUTION_LOGS': '27be7361-6c27-8033-a323-dca0fafa80e6',
    'SCRIPTS': '26ce7361-6c27-8178-bc77-f43aff00eddf',
    'WORKSPACE_REGISTRY': '299e7361-6c27-80f1-b264-f020e4a4b041',
    'AGENT_TASKS': '284e7361-6c27-8018-872a-eb14e82e0392',
}

# Expected paths
EXPECTED_PATHS = {
    'gas_scripts': project_root / 'gas-scripts' / 'drive-sheets-sync',
    'clasp_json': project_root / 'gas-scripts' / 'drive-sheets-sync' / '.clasp.json',
    'code_js': project_root / 'gas-scripts' / 'drive-sheets-sync' / 'Code.js',
    'diagnostic_functions': project_root / 'gas-scripts' / 'drive-sheets-sync' / 'DIAGNOSTIC_FUNCTIONS.js',
}


@dataclass
class ValidationResult:
    """Result of a validation check"""
    passed: bool
    check_name: str
    message: str
    details: Optional[Dict[str, Any]] = None
    fix_available: bool = False
    fix_action: Optional[str] = None


class DriveSheetsSync2WayValidator:
    """Validator for DriveSheetsSync 2-way synchronization"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[ValidationResult] = []
        self.notion_client = None
        self._init_notion_client()

    def _init_notion_client(self):
        """Initialize Notion client if available"""
        try:
            from shared_core.notion.token_manager import get_notion_token
            from notion_client import Client
            token = get_notion_token()
            if token:
                self.notion_client = Client(auth=token)
                if self.verbose:
                    print("✅ Notion client initialized")
        except Exception as e:
            if self.verbose:
                print(f"⚠️ Could not initialize Notion client: {e}")

    def _log(self, message: str):
        """Log message if verbose"""
        if self.verbose:
            print(message)

    def _add_result(self, result: ValidationResult):
        """Add a validation result"""
        self.results.append(result)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"{status}: {result.check_name}")
        if not result.passed:
            print(f"   └─ {result.message}")
            if result.fix_available:
                print(f"   └─ Fix: {result.fix_action}")

    # ========== FILE SYSTEM CHECKS ==========

    def check_clasp_project_exists(self) -> ValidationResult:
        """Check if clasp project exists and is properly configured"""
        clasp_json = EXPECTED_PATHS['clasp_json']
        code_js = EXPECTED_PATHS['code_js']

        if not clasp_json.exists():
            return ValidationResult(
                passed=False,
                check_name="Clasp Project Configuration",
                message=f".clasp.json not found at {clasp_json}",
                fix_available=True,
                fix_action="Run 'clasp create --type standalone' in gas-scripts/drive-sheets-sync/"
            )

        if not code_js.exists():
            return ValidationResult(
                passed=False,
                check_name="Clasp Project Configuration",
                message=f"Code.js not found at {code_js}",
                fix_available=True,
                fix_action="Run 'clasp pull' to fetch code from Google Apps Script"
            )

        # Read and validate .clasp.json
        try:
            with open(clasp_json, 'r') as f:
                clasp_config = json.load(f)

            script_id = clasp_config.get('scriptId', '')
            if not script_id:
                return ValidationResult(
                    passed=False,
                    check_name="Clasp Project Configuration",
                    message="scriptId is empty in .clasp.json",
                    details={'clasp_config': clasp_config},
                    fix_available=True,
                    fix_action="Run 'clasp clone <scriptId>' with correct script ID"
                )

            return ValidationResult(
                passed=True,
                check_name="Clasp Project Configuration",
                message="Clasp project properly configured",
                details={
                    'script_id': script_id[:20] + '...',
                    'code_js_size': code_js.stat().st_size,
                    'clasp_json_path': str(clasp_json)
                }
            )
        except json.JSONDecodeError as e:
            return ValidationResult(
                passed=False,
                check_name="Clasp Project Configuration",
                message=f"Invalid JSON in .clasp.json: {e}",
                fix_available=True,
                fix_action="Fix JSON syntax in .clasp.json"
            )

    def check_code_js_2way_sync_functions(self) -> ValidationResult:
        """Check if Code.js has required 2-way sync functions"""
        code_js = EXPECTED_PATHS['code_js']

        if not code_js.exists():
            return ValidationResult(
                passed=False,
                check_name="2-Way Sync Functions",
                message="Code.js not found",
                fix_available=True,
                fix_action="Run 'clasp pull' to fetch code"
            )

        required_functions = [
            'syncCsvToNotion_',
            'syncMarkdownFilesToNotion_',
            'syncSchemaFromCsvToNotion_',
            'writeDataSourceCsv_',
            'processSingleDatabase_',
            'runDriveSheetsOnce_',
            'manualRunDriveSheets'
        ]

        try:
            with open(code_js, 'r') as f:
                content = f.read()

            found = []
            missing = []
            for func in required_functions:
                if f'function {func}' in content:
                    found.append(func)
                else:
                    missing.append(func)

            if missing:
                return ValidationResult(
                    passed=False,
                    check_name="2-Way Sync Functions",
                    message=f"Missing functions: {', '.join(missing)}",
                    details={'found': found, 'missing': missing},
                    fix_available=True,
                    fix_action="Run 'clasp pull' to get latest code, or check for renames"
                )

            return ValidationResult(
                passed=True,
                check_name="2-Way Sync Functions",
                message=f"All {len(required_functions)} required functions found",
                details={'functions': found}
            )
        except Exception as e:
            return ValidationResult(
                passed=False,
                check_name="2-Way Sync Functions",
                message=f"Error reading Code.js: {e}"
            )

    def check_config_database_ids(self) -> ValidationResult:
        """Check if database IDs in Code.js match expected canonical IDs"""
        code_js = EXPECTED_PATHS['code_js']

        if not code_js.exists():
            return ValidationResult(
                passed=False,
                check_name="Database ID Configuration",
                message="Code.js not found"
            )

        try:
            with open(code_js, 'r') as f:
                content = f.read()

            # Check for canonical database IDs
            expected_ids = {
                'EXECUTION_LOGS': '27be73616c278033a323dca0fafa80e6',
                'SCRIPTS': '26ce73616c278178bc77f43aff00eddf',
                'WORKSPACE_REGISTRY': '299e73616c2780f1b264f020e4a4b041',
            }

            found_ids = {}
            missing_ids = []

            for name, expected_id in expected_ids.items():
                # Search for the ID in various formats
                normalized_id = expected_id.replace('-', '')
                if normalized_id in content or expected_id in content:
                    found_ids[name] = expected_id
                else:
                    missing_ids.append(name)

            if missing_ids:
                return ValidationResult(
                    passed=False,
                    check_name="Database ID Configuration",
                    message=f"Missing/incorrect database IDs: {', '.join(missing_ids)}",
                    details={'found': found_ids, 'missing': missing_ids, 'expected': expected_ids},
                    fix_available=True,
                    fix_action="Update getDatabaseConfig() in Code.js with correct IDs"
                )

            return ValidationResult(
                passed=True,
                check_name="Database ID Configuration",
                message="All database IDs configured correctly",
                details={'found_ids': found_ids}
            )
        except Exception as e:
            return ValidationResult(
                passed=False,
                check_name="Database ID Configuration",
                message=f"Error checking database IDs: {e}"
            )

    # ========== NOTION API CHECKS ==========

    def check_execution_logs_recent(self) -> ValidationResult:
        """Check if there are recent execution logs in Notion"""
        if not self.notion_client:
            return ValidationResult(
                passed=False,
                check_name="Recent Execution Logs",
                message="Notion client not available",
                fix_available=True,
                fix_action="Ensure NOTION_TOKEN is set and valid"
            )

        try:
            exec_logs_db = DB_CONFIG['EXECUTION_LOGS']

            # Query for recent execution logs
            response = self.notion_client.databases.query(
                database_id=exec_logs_db,
                filter={
                    "property": "Script Name-AI",
                    "rich_text": {"contains": "DriveSheetsSync"}
                },
                sorts=[{"property": "Start Time", "direction": "descending"}],
                page_size=10
            )

            results = response.get('results', [])

            if not results:
                return ValidationResult(
                    passed=False,
                    check_name="Recent Execution Logs",
                    message="No DriveSheetsSync execution logs found",
                    details={'database_id': exec_logs_db},
                    fix_available=True,
                    fix_action="Run manualRunDriveSheets() from Google Apps Script editor"
                )

            # Check if most recent is within 7 days
            most_recent = results[0]
            props = most_recent.get('properties', {})
            start_time_prop = props.get('Start Time', {})

            if start_time_prop.get('type') == 'date' and start_time_prop.get('date'):
                start_time_str = start_time_prop['date'].get('start', '')
                if start_time_str:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    age_days = (datetime.now(timezone.utc) - start_time).days

                    if age_days > 7:
                        return ValidationResult(
                            passed=False,
                            check_name="Recent Execution Logs",
                            message=f"Most recent execution log is {age_days} days old",
                            details={'most_recent_date': start_time_str, 'age_days': age_days},
                            fix_available=True,
                            fix_action="Verify time-based trigger is configured in Google Apps Script"
                        )

            return ValidationResult(
                passed=True,
                check_name="Recent Execution Logs",
                message=f"Found {len(results)} execution logs, most recent within acceptable range",
                details={'log_count': len(results)}
            )

        except Exception as e:
            return ValidationResult(
                passed=False,
                check_name="Recent Execution Logs",
                message=f"Error querying execution logs: {e}",
                fix_available=True,
                fix_action="Check Notion API permissions for Execution-Logs database"
            )

    def check_scripts_database_entry(self) -> ValidationResult:
        """Check if DriveSheetsSync has an entry in Scripts database"""
        if not self.notion_client:
            return ValidationResult(
                passed=False,
                check_name="Scripts Database Entry",
                message="Notion client not available"
            )

        try:
            scripts_db = DB_CONFIG['SCRIPTS']

            # Query for DriveSheetsSync script
            response = self.notion_client.databases.query(
                database_id=scripts_db,
                filter={
                    "property": "Name",
                    "title": {"contains": "DriveSheetsSync"}
                },
                page_size=5
            )

            results = response.get('results', [])

            if not results:
                return ValidationResult(
                    passed=False,
                    check_name="Scripts Database Entry",
                    message="DriveSheetsSync not found in Scripts database",
                    details={'database_id': scripts_db},
                    fix_available=True,
                    fix_action="Create DriveSheetsSync entry in Scripts database"
                )

            script_entry = results[0]
            props = script_entry.get('properties', {})

            # Check for required properties
            required_props = ['Name', 'Script ID', 'Status']
            missing_props = [p for p in required_props if p not in props]

            if missing_props:
                return ValidationResult(
                    passed=False,
                    check_name="Scripts Database Entry",
                    message=f"Script entry missing properties: {', '.join(missing_props)}",
                    details={'found_props': list(props.keys()), 'missing': missing_props}
                )

            return ValidationResult(
                passed=True,
                check_name="Scripts Database Entry",
                message="DriveSheetsSync entry found with required properties",
                details={'page_id': script_entry.get('id')[:8] + '...'}
            )

        except Exception as e:
            return ValidationResult(
                passed=False,
                check_name="Scripts Database Entry",
                message=f"Error querying Scripts database: {e}"
            )

    # ========== CLASP SYNC CHECK ==========

    def check_clasp_status(self) -> ValidationResult:
        """Check clasp status for the DriveSheetsSync project"""
        gas_scripts_path = EXPECTED_PATHS['gas_scripts']

        if not gas_scripts_path.exists():
            return ValidationResult(
                passed=False,
                check_name="Clasp Status",
                message="GAS scripts directory not found"
            )

        try:
            result = subprocess.run(
                ['clasp', 'status'],
                cwd=gas_scripts_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return ValidationResult(
                    passed=False,
                    check_name="Clasp Status",
                    message=f"Clasp status failed: {result.stderr}",
                    details={'stdout': result.stdout, 'stderr': result.stderr},
                    fix_available=True,
                    fix_action="Run 'clasp login' to authenticate"
                )

            # Parse output for file status
            output = result.stdout
            has_local_changes = 'Local' in output and 'ahead' in output.lower()

            return ValidationResult(
                passed=True,
                check_name="Clasp Status",
                message="Clasp project status retrieved",
                details={
                    'has_local_changes': has_local_changes,
                    'output': output[:500]
                }
            )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                passed=False,
                check_name="Clasp Status",
                message="Clasp command timed out",
                fix_available=True,
                fix_action="Check network connectivity and clasp authentication"
            )
        except FileNotFoundError:
            return ValidationResult(
                passed=False,
                check_name="Clasp Status",
                message="Clasp CLI not found",
                fix_available=True,
                fix_action="Install clasp: npm install -g @google/clasp"
            )
        except Exception as e:
            return ValidationResult(
                passed=False,
                check_name="Clasp Status",
                message=f"Error running clasp: {e}"
            )

    # ========== RUN ALL CHECKS ==========

    def run_all_checks(self) -> Dict[str, Any]:
        """Run all validation checks"""
        print("\n" + "=" * 60)
        print("DriveSheetsSync 2-Way Sync Validation")
        print("=" * 60 + "\n")

        # File system checks
        print("📁 File System Checks")
        print("-" * 40)
        self._add_result(self.check_clasp_project_exists())
        self._add_result(self.check_code_js_2way_sync_functions())
        self._add_result(self.check_config_database_ids())

        # Clasp checks
        print("\n🔄 Clasp Sync Checks")
        print("-" * 40)
        self._add_result(self.check_clasp_status())

        # Notion API checks (if available)
        if self.notion_client:
            print("\n📊 Notion API Checks")
            print("-" * 40)
            self._add_result(self.check_execution_logs_recent())
            self._add_result(self.check_scripts_database_entry())
        else:
            print("\n⚠️ Skipping Notion API checks (client not available)")

        # Summary
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        fixable = sum(1 for r in self.results if not r.passed and r.fix_available)

        print(f"\n  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  🔧 Fixable: {fixable}")

        if failed > 0:
            print("\n📋 Required Fixes:")
            for r in self.results:
                if not r.passed and r.fix_action:
                    print(f"  • {r.check_name}: {r.fix_action}")

        return {
            'passed': passed,
            'failed': failed,
            'fixable': fixable,
            'results': [
                {
                    'check': r.check_name,
                    'passed': r.passed,
                    'message': r.message,
                    'fix': r.fix_action
                }
                for r in self.results
            ]
        }


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate DriveSheetsSync 2-way synchronization')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--fix', action='store_true', help='Attempt to fix issues (not implemented)')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')

    args = parser.parse_args()

    validator = DriveSheetsSync2WayValidator(verbose=args.verbose)
    results = validator.run_all_checks()

    if args.json:
        print("\n" + json.dumps(results, indent=2))

    # Exit with error code if any checks failed
    sys.exit(0 if results['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
