#!/usr/bin/env python3
"""
Continuous Handoff Orchestrator
================================

This orchestrator continuously:
1. Queries Notion Agent-Tasks database for highest priority incomplete tasks
2. Creates handoff task files in 01_inbox/Agent-Trigger-Folder/
3. Routes those files to appropriate agent inbox folders
4. Continues until 0 tasks remain in the Agent-Tasks database

When agents complete tasks, they create review handoff tasks back to Auto/Cursor MM1 Agent,
which will be picked up by this orchestrator and processed in the same flow.

Author: Auto/Cursor MM1 Agent
Created: 2026-01-06
"""

import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('continuous_handoff_orchestrator.log')
    ]
)
logger = logging.getLogger(__name__)

# Import from main.py for Notion access
try:
    from main import (
        get_notion_token,
        safe_get_property,
        AGENT_TASKS_DB_ID,
        NotionManager,
    )
    from scripts.continuous_handoff_processor import check_completed_tasks
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    NotionManager = None

# Script paths
CREATE_HANDOFF_SCRIPT = project_root / "create_handoff_from_notion_task.py"
PROCESS_TRIGGER_SCRIPT = project_root / "process_agent_trigger_folder.py"
MUSIC_SYNC_SCRIPT = project_root / "scripts" / "music_track_sync_auto_detect.py"
PLAYLIST_SYNC_SCRIPT = project_root / "scripts" / "sync_soundcloud_playlist.py"

# Status values that indicate incomplete tasks
INCOMPLETE_STATUSES = [
    "Ready", "Not Started", "In Progress", "In-Progress", 
    "Ready for Handoff", "Proposed", "Draft", "Blocked"
]

# Music workflow scheduling configuration
MUSIC_SYNC_ENABLED = os.getenv("MUSIC_SYNC_ENABLED", "true").lower() == "true"
MUSIC_SYNC_INTERVAL = int(os.getenv("MUSIC_SYNC_INTERVAL", "21600"))  # Default: 6 hours in seconds
MUSIC_SYNC_LAST_RUN_FILE = project_root / "var" / "music_sync_last_run.json"


def detect_music_workflow_tasks(notion: NotionManager) -> List[Dict]:
    """
    Detect music workflow-related tasks in Agent-Tasks database.
    Includes both track sync and playlist sync tasks.
    
    Returns:
        List of music workflow task page objects
    """
    try:
        # Music workflow keywords for detection (includes playlist-specific keywords)
        music_keywords = ["music", "track", "sync", "soundcloud", "spotify", "download", "playlist"]
        
        filter_params = {
            "and": [
                {
                    "or": [
                        {"property": "Status", "status": {"equals": status}}
                        for status in INCOMPLETE_STATUSES
                    ]
                },
                {
                    "or": [
                        {
                            "property": "Name",
                            "title": {
                                "contains": keyword
                            }
                        }
                        for keyword in music_keywords
                    ]
                }
            ]
        }
        
        # NOTE: Agent-Tasks uses "Task Name" as the title property.
        filter_params["and"][1]["or"] = [
            {"property": "Task Name", "title": {"contains": keyword}}
            for keyword in music_keywords
        ]

        tasks = notion.query_database(
            AGENT_TASKS_DB_ID,
            filter_params=filter_params,
        )
        return tasks[:20]
        
    except Exception as e:
        logger.warning(f"Error detecting music workflow tasks: {e}", exc_info=True)
        return []


def check_tasks_remaining(notion: NotionManager) -> int:
    """
    Check how many incomplete tasks remain in Agent-Tasks database.
    
    Returns:
        Number of incomplete tasks
    """
    try:
        filter_params = {
            "or": [
                {"property": "Status", "status": {"equals": status}}
                for status in INCOMPLETE_STATUSES
            ]
        }
        
        tasks = notion.query_database(
            AGENT_TASKS_DB_ID,
            filter_params=filter_params,
        )
        return len(tasks)
        
    except Exception as e:
        logger.error(f"Error checking tasks remaining: {e}", exc_info=True)
        return -1  # Return -1 on error to continue processing


def run_script(script_path: Path, args: list = None) -> bool:
    """
    Run a Python script and return success status.
    
    Args:
        script_path: Path to the script
        args: Additional arguments to pass
    
    Returns:
        True if script executed successfully, False otherwise
    """
    if not script_path.exists():
        logger.error(f"Script not found: {script_path}")
        return False
    
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Successfully executed: {script_path.name}")
            if result.stdout:
                logger.debug(result.stdout)
            return True
        else:
            logger.warning(f"Script {script_path.name} returned exit code {result.returncode}")
            if result.stderr:
                logger.warning(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"Script {script_path.name} timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"Error running script {script_path.name}: {e}", exc_info=True)
        return False


def should_run_music_sync() -> bool:
    """
    Check if music sync should run based on configured interval.
    
    Returns:
        True if music sync should run, False otherwise
    """
    if not MUSIC_SYNC_ENABLED:
        return False
    
    if not MUSIC_SYNC_LAST_RUN_FILE.exists():
        return True  # First run
    
    try:
        import json
        with open(MUSIC_SYNC_LAST_RUN_FILE, 'r') as f:
            last_run_data = json.load(f)
            last_run_time = last_run_data.get('last_run', 0)
            current_time = time.time()
            time_since_last_run = current_time - last_run_time
            
            return time_since_last_run >= MUSIC_SYNC_INTERVAL
    except Exception as e:
        logger.warning(f"Error checking music sync last run time: {e}")
        return True  # Default to running if we can't check


def run_music_sync() -> bool:
    """
    Execute music sync workflow.
    
    Returns:
        True if successful, False otherwise
    """
    if not MUSIC_SYNC_SCRIPT.exists():
        logger.warning(f"Music sync script not found: {MUSIC_SYNC_SCRIPT}")
        return False
    
    logger.info("=" * 80)
    logger.info("MUSIC SYNC WORKFLOW")
    logger.info("=" * 80)
    logger.info(f"Executing: {MUSIC_SYNC_SCRIPT.name}")
    
    success = run_script(MUSIC_SYNC_SCRIPT)
    
    # Update last run time
    if success:
        try:
            import json
            MUSIC_SYNC_LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MUSIC_SYNC_LAST_RUN_FILE, 'w') as f:
                json.dump({'last_run': time.time()}, f)
            logger.info("✅ Music sync completed successfully")
        except Exception as e:
            logger.warning(f"Failed to update music sync last run time: {e}")
    else:
        logger.warning("⚠️  Music sync completed with errors")
    
    return success


def run_playlist_sync(playlist_url: Optional[str] = None) -> bool:
    """
    Execute playlist sync workflow using sync_soundcloud_playlist.py.
    
    Args:
        playlist_url: Optional playlist URL. If not provided, script will use auto-detection.
    
    Returns:
        True if successful, False otherwise
    """
    if not PLAYLIST_SYNC_SCRIPT.exists():
        logger.warning(f"Playlist sync script not found: {PLAYLIST_SYNC_SCRIPT}")
        return False
    
    logger.info("=" * 80)
    logger.info("PLAYLIST SYNC WORKFLOW")
    logger.info("=" * 80)
    logger.info(f"Executing: {PLAYLIST_SYNC_SCRIPT.name}")
    if playlist_url:
        logger.info(f"Playlist URL: {playlist_url}")
    
    args = []
    if playlist_url:
        args = [playlist_url]
    
    success = run_script(PLAYLIST_SYNC_SCRIPT, args)
    
    if success:
        logger.info("✅ Playlist sync completed successfully")
    else:
        logger.warning("⚠️  Playlist sync completed with errors")
    
    return success


def process_cycle(notion: NotionManager) -> Tuple[bool, int]:
    """
    Execute one processing cycle:
    1. Check if music sync should run (based on interval)
    2. Create handoff tasks from Notion
    3. Route trigger files to agents
    
    Returns:
        Tuple of (tasks_processed, tasks_remaining)
    """
    logger.info("=" * 80)
    logger.info("PROCESSING CYCLE")
    logger.info("=" * 80)
    
    # Step 0: Check if music sync should run or if music workflow tasks detected
    music_tasks = detect_music_workflow_tasks(notion)
    if MUSIC_SYNC_ENABLED and music_tasks:
        logger.info(f"🎵 Detected {len(music_tasks)} music workflow task(s), executing music sync...")
        run_music_sync()
        time.sleep(1)  # Brief pause between operations
    elif MUSIC_SYNC_ENABLED and should_run_music_sync():
        logger.info("Step 0: Running scheduled music sync...")
        run_music_sync()
        time.sleep(1)  # Brief pause between operations
    
    # Step 1: Create handoff tasks from Notion
    logger.info("Step 1: Creating handoff tasks from Notion Agent-Tasks database...")
    handoff_created = run_script(CREATE_HANDOFF_SCRIPT, ["--once"])
    
    if not handoff_created:
        logger.warning("Failed to create handoff task, continuing anyway...")
    
    time.sleep(1)  # Brief pause between operations
    
    # Step 2: Route trigger files to agents
    logger.info("Step 2: Routing trigger files to agent inbox folders...")
    routing_success = run_script(PROCESS_TRIGGER_SCRIPT)
    
    if not routing_success:
        logger.warning("Failed to route trigger files, continuing anyway...")
    
    time.sleep(1)  # Brief pause
    
    # Step 3: Check how many tasks remain
    # Step 2.5: Create review handoffs for completed tasks (keeps the loop moving)
    try:
        # Avoid creating an unbounded number of review tasks in a single cycle.
        check_completed_tasks(notion, max_to_create=3)
    except Exception as e:
        logger.warning(f"Error checking completed tasks for review handoffs: {e}", exc_info=True)

    time.sleep(1)

    tasks_remaining = check_tasks_remaining(notion)
    
    if tasks_remaining == 0:
        logger.info("✅ All tasks complete! No incomplete tasks remaining.")
        return True, 0
    elif tasks_remaining > 0:
        logger.info(f"📋 {tasks_remaining} incomplete task(s) remaining")
        return False, tasks_remaining
    else:
        # Error case, continue processing
        logger.warning("Could not determine tasks remaining, continuing...")
        return False, -1


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Continuous Handoff Orchestrator")
    parser.add_argument("--once", action="store_true", help="Process one cycle and exit")
    parser.add_argument("--interval", type=int, default=60, help="Interval between cycles in seconds (default: 60)")
    parser.add_argument("--music-sync", action="store_true", help="Force music sync execution (ignores interval)")
    parser.add_argument("--no-music-sync", action="store_true", help="Disable music sync for this run")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("CONTINUOUS HANDOFF ORCHESTRATOR")
    logger.info("=" * 80)
    logger.info("This orchestrator will:")
    logger.info("1. Create handoff tasks in 01_inbox/Agent-Trigger-Folder/")
    logger.info("2. Route them to appropriate agent inbox folders")
    logger.info("3. Continue until 0 tasks remain in Agent-Tasks database")
    logger.info("=" * 80)
    
    # Validate scripts exist
    if not CREATE_HANDOFF_SCRIPT.exists():
        logger.error(f"Create handoff script not found: {CREATE_HANDOFF_SCRIPT}")
        sys.exit(1)
    
    if not PROCESS_TRIGGER_SCRIPT.exists():
        logger.error(f"Process trigger script not found: {PROCESS_TRIGGER_SCRIPT}")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        logger.error("NOTION_TOKEN not found. Cannot proceed.")
        sys.exit(1)

    if NotionManager is None:
        logger.error("NotionManager not available. Cannot proceed.")
        sys.exit(1)

    notion = NotionManager(token)
    
    # Validate access
    try:
        notion.client.users.me()
        logger.info("✅ Notion API access validated")
    except Exception as e:
        logger.error(f"Notion API access validation failed: {e}")
        sys.exit(1)
    
    # Override music sync settings if specified
    global MUSIC_SYNC_ENABLED
    if args.music_sync:
        MUSIC_SYNC_ENABLED = True
        logger.info("🎵 Music sync forced for this run")
    elif args.no_music_sync:
        MUSIC_SYNC_ENABLED = False
        logger.info("🎵 Music sync disabled for this run")
    
    # Log music sync configuration
    if MUSIC_SYNC_ENABLED:
        logger.info(f"🎵 Music sync enabled (interval: {MUSIC_SYNC_INTERVAL}s / {MUSIC_SYNC_INTERVAL/3600:.1f} hours)")
    else:
        logger.info("🎵 Music sync disabled")
    
    # Process tasks
    if args.once:
        # Process one cycle and exit
        logger.info("Running one processing cycle...")
        all_complete, tasks_remaining = process_cycle(notion)
        if all_complete:
            logger.info("✅ All tasks complete!")
        else:
            logger.info(f"📋 {tasks_remaining} task(s) remaining")
    else:
        # Continuous loop
        logger.info(f"Starting continuous processing (checking every {args.interval} seconds)")
        logger.info("Press Ctrl+C to stop")
        logger.info("System will continue until 0 tasks remain in Agent-Tasks database")
        logger.info("")
        
        cycle_count = 0
        consecutive_no_progress = 0
        max_no_progress = 10  # Stop if 10 cycles with no progress
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"\n{'='*80}")
                logger.info(f"CYCLE #{cycle_count}")
                logger.info(f"{'='*80}\n")
                
                all_complete, tasks_remaining = process_cycle(notion)
                
                if all_complete:
                    logger.info("")
                    logger.info("=" * 80)
                    logger.info("🎉 ALL TASKS COMPLETE!")
                    logger.info("=" * 80)
                    logger.info("No incomplete tasks remaining in Agent-Tasks database.")
                    logger.info("Orchestrator stopping.")
                    break
                
                if tasks_remaining == -1:
                    # Error case, continue but track
                    consecutive_no_progress += 1
                elif tasks_remaining > 0:
                    # Reset no-progress counter if we have tasks
                    consecutive_no_progress = 0
                
                if consecutive_no_progress >= max_no_progress:
                    logger.warning(f"⚠️  {max_no_progress} consecutive cycles with errors. Stopping.")
                    break
                
                logger.info(f"\nWaiting {args.interval} seconds before next cycle...")
                time.sleep(args.interval)
                
        except KeyboardInterrupt:
            logger.info("\n\nStopped by user")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()





















