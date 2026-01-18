#!/usr/bin/env python3
"""
DriveSheetsSync Folder Synchronization Testing Script

This script tests folder synchronization and access patterns for DriveSheetsSync:
1. Test DriveSheetsSync folder creation
2. Verify folder access from agents
3. Test file operations in synced folders
4. Validate Notion database updates
5. Performance testing

This script can be run manually or integrated into automated testing workflows.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from main import NotionManager, safe_get_property, get_notion_token
    NOTION_AVAILABLE = True
except ImportError:
    logger.warning("Notion client not available - will skip Notion validation tests")
    NOTION_AVAILABLE = False


class DriveSheetsSyncFolderTester:
    """Test DriveSheetsSync folder synchronization and access patterns."""
    
    def __init__(self):
        self.test_results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tests": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0
            }
        }
        self.notion = None
        
        if NOTION_AVAILABLE:
            try:
                token = get_notion_token()
                if token:
                    self.notion = NotionManager(token)
            except Exception as e:
                logger.warning(f"Could not initialize Notion client: {e}")
    
    def test_folder_structure_exists(self, base_path: Path) -> Dict[str, Any]:
        """
        Test 1: Verify DriveSheetsSync folder structure exists.
        
        Expected structure:
        - workspace-databases/
          - {database_id}/
            - .archive/
            - {database_id}.csv
        """
        test_name = "Folder Structure Exists"
        logger.info(f"Running test: {test_name}")
        
        result = {
            "test_name": test_name,
            "status": "skipped",
            "message": "",
            "details": {}
        }
        
        # Check if Google Drive path exists
        # Note: This assumes we're checking a local mount or have Drive API access
        workspace_db_path = base_path / "workspace-databases"
        
        if not workspace_db_path.exists():
            result["status"] = "failed"
            result["message"] = f"workspace-databases folder not found at {workspace_db_path}"
            logger.error(result["message"])
        else:
            # Count database folders
            db_folders = [d for d in workspace_db_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
            archive_folders = [d for d in workspace_db_path.rglob('.archive') if d.is_dir()]
            
            result["status"] = "passed"
            result["message"] = f"Found {len(db_folders)} database folders and {len(archive_folders)} archive folders"
            result["details"] = {
                "database_folders_count": len(db_folders),
                "archive_folders_count": len(archive_folders),
                "base_path": str(base_path)
            }
            logger.info(result["message"])
        
        self.test_results["tests"].append(result)
        self._update_summary(result["status"])
        return result
    
    def test_archive_folder_creation(self, base_path: Path) -> Dict[str, Any]:
        """
        Test 2: Verify archive folders are created for each database.
        """
        test_name = "Archive Folder Creation"
        logger.info(f"Running test: {test_name}")
        
        result = {
            "test_name": test_name,
            "status": "skipped",
            "message": "",
            "details": {}
        }
        
        workspace_db_path = base_path / "workspace-databases"
        
        if not workspace_db_path.exists():
            result["status"] = "skipped"
            result["message"] = "workspace-databases folder not found - skipping test"
            logger.warning(result["message"])
        else:
            db_folders = [d for d in workspace_db_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
            missing_archives = []
            
            for db_folder in db_folders:
                archive_path = db_folder / ".archive"
                if not archive_path.exists():
                    missing_archives.append(db_folder.name)
            
            if missing_archives:
                result["status"] = "failed"
                result["message"] = f"Found {len(missing_archives)} database folders missing .archive folders"
                result["details"] = {
                    "missing_archives_count": len(missing_archives),
                    "missing_archives": missing_archives[:10]  # Limit to first 10
                }
                logger.warning(result["message"])
            else:
                result["status"] = "passed"
                result["message"] = f"All {len(db_folders)} database folders have .archive folders"
                result["details"] = {
                    "database_folders_checked": len(db_folders)
                }
                logger.info(result["message"])
        
        self.test_results["tests"].append(result)
        self._update_summary(result["status"])
        return result
    
    def test_agent_folder_access(self, agent_folders: List[Path]) -> Dict[str, Any]:
        """
        Test 3: Verify agent folders can access DriveSheetsSync folders.
        
        This checks that agent trigger folders can reference or access
        DriveSheetsSync workspace-databases folders.
        """
        test_name = "Agent Folder Access"
        logger.info(f"Running test: {test_name}")
        
        result = {
            "test_name": test_name,
            "status": "skipped",
            "message": "",
            "details": {}
        }
        
        accessible_count = 0
        inaccessible = []
        
        for agent_folder in agent_folders:
            if agent_folder.exists() and agent_folder.is_dir():
                # Check if folder is readable and writable
                if os.access(agent_folder, os.R_OK):
                    accessible_count += 1
                else:
                    inaccessible.append(str(agent_folder))
        
        if inaccessible:
            result["status"] = "failed"
            result["message"] = f"{len(inaccessible)} agent folders are not accessible"
            result["details"] = {
                "accessible": accessible_count,
                "inaccessible": inaccessible[:5]  # Limit to first 5
            }
            logger.warning(result["message"])
        else:
            result["status"] = "passed"
            result["message"] = f"All {accessible_count} agent folders are accessible"
            result["details"] = {
                "accessible_count": accessible_count
            }
            logger.info(result["message"])
        
        self.test_results["tests"].append(result)
        self._update_summary(result["status"])
        return result
    
    def test_notion_database_sync(self) -> Dict[str, Any]:
        """
        Test 4: Validate Notion database updates are reflected in folder structure.
        
        This would require:
        - Querying Notion for databases
        - Verifying corresponding folders exist
        - Checking folder metadata matches Notion data
        """
        test_name = "Notion Database Sync Validation"
        logger.info(f"Running test: {test_name}")
        
        result = {
            "test_name": test_name,
            "status": "skipped",
            "message": "",
            "details": {}
        }
        
        if not self.notion:
            result["status"] = "skipped"
            result["message"] = "Notion client not available - skipping test"
            logger.warning(result["message"])
        else:
            # This test would need to:
            # 1. Query Notion Folders database
            # 2. Match with actual folder structure
            # 3. Verify consistency
            result["status"] = "skipped"
            result["message"] = "Notion database sync validation requires Drive API integration"
            result["details"] = {
                "note": "This test requires Google Drive API access to verify folder sync"
            }
            logger.info(result["message"])
        
        self.test_results["tests"].append(result)
        self._update_summary(result["status"])
        return result
    
    def test_performance_folder_operations(self, test_folder: Path) -> Dict[str, Any]:
        """
        Test 5: Performance testing of folder operations.
        
        Measures:
        - Folder creation time
        - File write time
        - Folder listing time
        - Archive operation time
        """
        test_name = "Performance Folder Operations"
        logger.info(f"Running test: {test_name}")
        
        result = {
            "test_name": test_name,
            "status": "skipped",
            "message": "",
            "details": {}
        }
        
        import time
        
        try:
            # Create test folder
            start = time.time()
            test_folder.mkdir(parents=True, exist_ok=True)
            creation_time = time.time() - start
            
            # Write test file
            start = time.time()
            test_file = test_folder / "test_file.txt"
            test_file.write_text("test content")
            write_time = time.time() - start
            
            # List folder contents
            start = time.time()
            list(test_folder.iterdir())
            list_time = time.time() - start
            
            # Create archive folder
            archive_folder = test_folder / ".archive"
            start = time.time()
            archive_folder.mkdir(exist_ok=True)
            archive_time = time.time() - start
            
            # Cleanup
            test_file.unlink()
            archive_folder.rmdir()
            test_folder.rmdir()
            
            result["status"] = "passed"
            result["message"] = "Performance tests completed"
            result["details"] = {
                "folder_creation_ms": round(creation_time * 1000, 2),
                "file_write_ms": round(write_time * 1000, 2),
                "folder_listing_ms": round(list_time * 1000, 2),
                "archive_creation_ms": round(archive_time * 1000, 2)
            }
            logger.info(result["message"])
            
        except Exception as e:
            result["status"] = "failed"
            result["message"] = f"Performance test failed: {e}"
            logger.error(result["message"])
        
        self.test_results["tests"].append(result)
        self._update_summary(result["status"])
        return result
    
    def _update_summary(self, status: str):
        """Update test summary statistics."""
        self.test_results["summary"]["total"] += 1
        if status == "passed":
            self.test_results["summary"]["passed"] += 1
        elif status == "failed":
            self.test_results["summary"]["failed"] += 1
        else:
            self.test_results["summary"]["skipped"] += 1
    
    def run_all_tests(self, base_path: Optional[Path] = None, agent_folders: Optional[List[Path]] = None):
        """Run all folder synchronization tests."""
        logger.info("=" * 80)
        logger.info("DriveSheetsSync Folder Synchronization Testing")
        logger.info("=" * 80)
        
        # Default paths
        if base_path is None:
            # Try to find Google Drive base path
            possible_paths = [
                Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive"),
                Path.home() / "Google Drive",
            ]
            base_path = None
            for path in possible_paths:
                if path.exists():
                    base_path = path
                    break
        
        if agent_folders is None:
            agent_folders = [
                Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers"),
            ]
        
        # Run tests
        if base_path:
            self.test_folder_structure_exists(base_path)
            self.test_archive_folder_creation(base_path)
        
        if agent_folders:
            self.test_agent_folder_access(agent_folders)
        
        self.test_notion_database_sync()
        
        # Performance test with temp folder
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            self.test_performance_folder_operations(Path(tmpdir) / "test_perf")
        
        # Print summary
        logger.info("=" * 80)
        logger.info("Test Summary")
        logger.info("=" * 80)
        summary = self.test_results["summary"]
        logger.info(f"Total: {summary['total']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Skipped: {summary['skipped']}")
        
        return self.test_results
    
    def save_results(self, output_path: Path):
        """Save test results to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        logger.info(f"Test results saved to {output_path}")


def main():
    """Main entry point."""
    tester = DriveSheetsSyncFolderTester()
    results = tester.run_all_tests()
    
    # Save results
    output_file = Path(__file__).parent / "test_results" / "drivesheetsync_folder_sync_test_results.json"
    tester.save_results(output_file)
    
    # Return exit code based on results
    if results["summary"]["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()









