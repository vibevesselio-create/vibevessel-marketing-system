#!/usr/bin/env python3
"""
Sync All Scripts to Notion and Validate Sync Scripts
=====================================================

This script:
1. Syncs all scripts in the codebase to Notion (including newly created ones)
2. Validates existing script synchronization scripts
3. Ensures all scripts are properly synced

Usage:
    python sync_all_scripts_to_notion.py [--dry-run] [--validate-only]
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sync_all_scripts.log')
    ]
)
logger = logging.getLogger(__name__)

# Scripts database ID
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"

# Paths to sync scripts
SYNC_SCRIPTS = [
    {
        "name": "Hardened Sync Script",
        "path": "seren-media-workflows/scripts/sync_codebase_to_notion_hardened.py",
        "type": "hardened"
    },
    {
        "name": "Standard Sync Script",
        "path": "seren-media-workflows/scripts/sync_codebase_to_notion.py",
        "type": "standard"
    },
    {
        "name": "GAS Script Sync",
        "path": "scripts/gas_script_sync.py",
        "type": "gas"
    }
]

# Newly created scripts to sync
NEW_SCRIPTS = [
    {
        "name": "Sync Folders and Volumes",
        "path": "sync_folders_volumes_to_notion.py",
        "type": "sync"
    }
]


def check_script_exists(script_path: str) -> bool:
    """Check if a script file exists"""
    full_path = Path(script_path)
    if full_path.is_absolute():
        return full_path.exists()
    else:
        # Try relative to current directory
        return (Path.cwd() / script_path).exists() or (Path(__file__).parent / script_path).exists()


def validate_sync_script(script_info: Dict) -> Dict[str, any]:
    """Validate a sync script exists and can be imported"""
    result = {
        "name": script_info["name"],
        "path": script_info["path"],
        "exists": False,
        "valid": False,
        "error": None
    }
    
    # Check if file exists
    if check_script_exists(script_info["path"]):
        result["exists"] = True
        
        # Try to validate Python syntax
        try:
            script_path = Path(script_info["path"])
            if not script_path.is_absolute():
                # Try to find it
                if (Path.cwd() / script_path).exists():
                    script_path = Path.cwd() / script_path
                elif (Path(__file__).parent / script_path).exists():
                    script_path = Path(__file__).parent / script_path
            
            # Check Python syntax
            compile(script_path.read_text(), str(script_path), 'exec')
            result["valid"] = True
        except SyntaxError as e:
            result["error"] = f"Syntax error: {e}"
        except Exception as e:
            result["error"] = f"Validation error: {e}"
    else:
        result["error"] = "Script file not found"
    
    return result


def sync_script_to_notion(script_path: str, dry_run: bool = False) -> bool:
    """
    Sync a single script to Notion using the hardened sync script.
    
    Args:
        script_path: Path to the script to sync
        dry_run: If True, perform a dry run
    
    Returns:
        True if sync was successful, False otherwise
    """
    # Find the hardened sync script
    hardened_sync_path = None
    for sync_script in SYNC_SCRIPTS:
        if sync_script["type"] == "hardened":
            if check_script_exists(sync_script["path"]):
                hardened_sync_path = sync_script["path"]
                break
    
    if not hardened_sync_path:
        logger.error("Hardened sync script not found")
        return False
    
    # Resolve full path
    sync_script_full_path = Path(hardened_sync_path)
    if not sync_script_full_path.is_absolute():
        if (Path.cwd() / sync_script_full_path).exists():
            sync_script_full_path = Path.cwd() / sync_script_full_path
        elif (Path(__file__).parent / sync_script_full_path).exists():
            sync_script_full_path = Path(__file__).parent / sync_script_full_path
    
    # Resolve script path
    script_full_path = Path(script_path)
    if not script_full_path.is_absolute():
        if (Path.cwd() / script_full_path).exists():
            script_full_path = Path.cwd() / script_full_path
        elif (Path(__file__).parent / script_full_path).exists():
            script_full_path = Path(__file__).parent / script_full_path
    
    if not script_full_path.exists():
        logger.error(f"Script not found: {script_path}")
        return False
    
    # Get relative path from project root
    project_root = Path(__file__).parent
    try:
        relative_path = script_full_path.relative_to(project_root)
    except ValueError:
        # Script is outside project root, use absolute path
        relative_path = script_full_path
    
    logger.info(f"Syncing script: {relative_path}")
    
    # Run the sync script
    cmd = [
        sys.executable,
        str(sync_script_full_path),
        "--script-path",
        str(relative_path)
    ]
    
    if dry_run:
        cmd.append("--dry-run")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully synced: {relative_path}")
            if result.stdout:
                logger.debug(f"Output: {result.stdout}")
            return True
        else:
            logger.error(f"Failed to sync {relative_path}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
            if result.stdout:
                logger.error(f"Output: {result.stdout}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"Sync timed out for: {relative_path}")
        return False
    except Exception as e:
        logger.error(f"Error running sync: {e}")
        return False


def sync_all_scripts(dry_run: bool = False) -> Dict[str, int]:
    """Sync all scripts to Notion"""
    stats = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0
    }
    
    # Sync newly created scripts first
    logger.info("=" * 80)
    logger.info("Syncing Newly Created Scripts")
    logger.info("=" * 80)
    
    for script_info in NEW_SCRIPTS:
        stats["total"] += 1
        if check_script_exists(script_info["path"]):
            if sync_script_to_notion(script_info["path"], dry_run=dry_run):
                stats["successful"] += 1
            else:
                stats["failed"] += 1
        else:
            logger.warning(f"Script not found: {script_info['path']}")
            stats["skipped"] += 1
    
    # Sync sync scripts themselves
    logger.info("=" * 80)
    logger.info("Syncing Script Synchronization Scripts")
    logger.info("=" * 80)
    
    for script_info in SYNC_SCRIPTS:
        stats["total"] += 1
        if check_script_exists(script_info["path"]):
            if sync_script_to_notion(script_info["path"], dry_run=dry_run):
                stats["successful"] += 1
            else:
                stats["failed"] += 1
        else:
            logger.warning(f"Script not found: {script_info['path']}")
            stats["skipped"] += 1
    
    return stats


def validate_all_sync_scripts() -> List[Dict]:
    """Validate all sync scripts"""
    logger.info("=" * 80)
    logger.info("Validating Script Synchronization Scripts")
    logger.info("=" * 80)
    
    results = []
    for script_info in SYNC_SCRIPTS:
        result = validate_sync_script(script_info)
        results.append(result)
        
        status = "✅" if result["valid"] else "❌"
        logger.info(f"{status} {result['name']}: {result['path']}")
        if result["error"]:
            logger.warning(f"  Error: {result['error']}")
    
    return results


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Sync all scripts to Notion and validate sync scripts"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making changes to Notion'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate sync scripts, do not sync'
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Script Synchronization and Validation")
    logger.info("=" * 80)
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Validate Only: {args.validate_only}")
    logger.info("=" * 80)
    
    # Validate sync scripts
    validation_results = validate_all_sync_scripts()
    
    valid_count = sum(1 for r in validation_results if r["valid"])
    total_count = len(validation_results)
    
    logger.info("=" * 80)
    logger.info(f"Validation Results: {valid_count}/{total_count} scripts valid")
    logger.info("=" * 80)
    
    if args.validate_only:
        logger.info("Validation only mode - skipping sync")
        return
    
    # Check if we have at least one valid sync script
    if valid_count == 0:
        logger.error("No valid sync scripts found - cannot proceed with sync")
        sys.exit(1)
    
    # Sync all scripts
    stats = sync_all_scripts(dry_run=args.dry_run)
    
    # Print summary
    logger.info("=" * 80)
    logger.info("Synchronization Summary")
    logger.info("=" * 80)
    logger.info(f"Total scripts: {stats['total']}")
    logger.info(f"Successful: {stats['successful']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Skipped: {stats['skipped']}")
    logger.info("=" * 80)
    
    if stats['failed'] > 0:
        logger.warning("Some scripts failed to sync")
        sys.exit(1)
    else:
        logger.info("All scripts synced successfully")


if __name__ == "__main__":
    main()
