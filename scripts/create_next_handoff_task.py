#!/usr/bin/env python3
"""
Create Next Handoff Task
========================

Creates a handoff task for the next highest-priority incomplete task from the Agent-Tasks database.
Assigns the task to the most appropriate agent based on capabilities and environment.

This script can be run:
- Once: Creates handoff for next task and exits
- Continuously: Runs until all tasks are complete (0 tasks remain)

Author: Cursor MM1 Agent
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import from main.py and continuous_handoff_processor
from main import (
    get_notion_token,
    NotionManager,
    safe_get_property,
    determine_agent_type,
    normalize_agent_folder_name,
    create_trigger_file,
    AGENT_TASKS_DB_ID,
    MM1_AGENT_TRIGGER_BASE,
    MM2_AGENT_TRIGGER_BASE,
    CURSOR_MM1_AGENT_ID,
)

# Import agent selection logic from continuous_handoff_processor
from scripts.continuous_handoff_processor import (
    AGENT_MAPPING,
    AGENT_ID_TO_NAME,
    AGENT_CAPABILITIES,
    PRIORITY_ORDER,
    determine_best_agent,
    get_incomplete_tasks,
    check_existing_trigger_file,
    create_review_handoff,
    check_completed_tasks,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('create_next_handoff_task.log')
    ]
)
logger = logging.getLogger(__name__)

# Pause durations (in seconds) to avoid rate limiting
PAUSE_AFTER_NOTION_QUERY = 1.0
PAUSE_AFTER_NOTION_UPDATE = 0.5
PAUSE_AFTER_NOTION_CREATE = 1.0
PAUSE_AFTER_FILE_CREATE = 0.5
PAUSE_BETWEEN_REVIEWS = 2.0


def process_next_task(notion: NotionManager, skip_review_check: bool = False) -> bool:
    """
    Process the next highest priority incomplete task that doesn't have a trigger file.
    
    Args:
        skip_review_check: If True, skip checking for completed tasks (faster)
    
    Returns:
        True if a task was processed, False if no tasks remain
    """
    logger.info("=" * 60)
    logger.info("Querying for incomplete tasks...")
    
    tasks = get_incomplete_tasks(notion)
    
    if not tasks:
        logger.info("No incomplete tasks found. All tasks complete!")
        return False
    
    logger.info(f"Found {len(tasks)} incomplete task(s)")
    
    # Find the first task that doesn't have a trigger file
    task = None
    for candidate_task in tasks:
        task_id = candidate_task.get("id")
        agent_name, agent_id = determine_best_agent(candidate_task, notion)
        
        if agent_name and agent_id:
            if not check_existing_trigger_file(task_id, agent_name, agent_id):
                task = candidate_task
                break
    
    if not task:
        logger.info("All incomplete tasks already have trigger files. No new handoffs needed.")
        return False
    
    # Process the selected task
    task_id = task.get("id")
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_status = safe_get_property(task, "Status", "status") or "Unknown"
    task_priority = safe_get_property(task, "Priority", "select") or "Medium"
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    next_step = safe_get_property(task, "Next Required Step", "rich_text") or ""
    success_criteria = safe_get_property(task, "Success Criteria", "rich_text") or ""
    
    logger.info("")
    logger.info(f"Processing task: {task_title}")
    logger.info(f"  Status: {task_status}")
    logger.info(f"  Priority: {task_priority}")
    logger.info(f"  URL: {task_url}")
    
    # Determine best agent
    agent_name, agent_id = determine_best_agent(task, notion)
    
    if not agent_name or not agent_id:
        logger.error(f"  → Could not determine agent for task. Skipping.")
        return True  # Continue processing other tasks
    
    logger.info(f"  → Assigned to: {agent_name}")
    
    # Create trigger file (we already checked that it doesn't exist)
    logger.info(f"  → Creating handoff file for {agent_name}...")
    
    # Build handoff instructions
    handoff_instructions = f"""Proceed with the execution of this task. Upon completion, you MUST:

1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.

2. Update the task status in Notion to 'Complete'

3. Document all work comprehensively in Notion

4. Verify production execution and workspace requirements are met

5. A review handoff task will be automatically created back to Cursor MM1 Agent for validation

**MANDATORY:** Task is NOT complete until trigger file is manually moved, status is updated, and all documentation is complete.

## Task Details

**Next Required Step:** {next_step if next_step else "Execute the task as described"}

**Success Criteria:** {success_criteria if success_criteria else "All task requirements met, documented, and validated"}
"""
    
    # Prepare task_details in format expected by create_trigger_file
    task_details = {
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url,
        "description": task_description,
        "status": task_status,
        "agent_id": agent_id,  # Include agent_id for normalization
        "handoff_instructions": handoff_instructions,
        "priority": task_priority
    }
    
    agent_type = determine_agent_type(agent_name, agent_id)
    trigger_file = create_trigger_file(agent_type, agent_name, task_details)
    time.sleep(PAUSE_AFTER_FILE_CREATE)
    
    if trigger_file:
        logger.info(f"  → Created trigger file: {trigger_file}")
        
        # Update task status to In Progress
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            notion.update_page(task_id, update_properties)
            time.sleep(PAUSE_AFTER_NOTION_UPDATE)
            logger.info(f"  → Updated task status to 'In Progress'")
        
        return True
    else:
        logger.error(f"  → Failed to create trigger file")
        return True  # Continue processing other tasks


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create Next Handoff Task")
    parser.add_argument(
        '--once',
        action='store_true',
        help='Process only one task and exit'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=600,
        help='Interval between iterations in seconds (default: 600 = 10 minutes)'
    )
    parser.add_argument(
        '--continuous',
        action='store_true',
        help='Run continuously until all tasks are complete'
    )
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("CREATE NEXT HANDOFF TASK")
    logger.info("=" * 60)
    
    if args.once:
        logger.info("Running in single-task mode.")
    elif args.continuous:
        logger.info("Running in continuous mode until 0 tasks remain.")
        logger.info("Press Ctrl+C to stop.")
    else:
        logger.info("Running in single-task mode (default).")
        logger.info("Use --continuous to run until all tasks complete.")
    logger.info("")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token. Exiting.")
        return 1
    
    notion = NotionManager(token)
    
    iteration = 0
    consecutive_no_tasks = 0
    
    try:
        while True:
            iteration += 1
            logger.info("")
            logger.info(f"Iteration {iteration}")
            logger.info("-" * 60)
            
            # Check for completed tasks and create review handoffs (skip in --once mode for speed)
            if not args.once:
                check_completed_tasks(notion)
                time.sleep(PAUSE_AFTER_NOTION_QUERY)
            
            # Process next task
            task_processed = process_next_task(notion, skip_review_check=args.once)
            time.sleep(PAUSE_AFTER_NOTION_QUERY)
            
            if not task_processed:
                consecutive_no_tasks += 1
                if consecutive_no_tasks >= 3 or args.once or not args.continuous:
                    logger.info("")
                    logger.info("=" * 60)
                    if args.once:
                        logger.info("Single task mode complete. Exiting.")
                    else:
                        logger.info("No tasks remaining. Exiting.")
                    logger.info("=" * 60)
                    break
            else:
                consecutive_no_tasks = 0
            
            if args.once or not args.continuous:
                break
            
            # Wait before next iteration
            interval_minutes = args.interval / 60
            logger.info("")
            logger.info(f"Waiting {args.interval} seconds ({interval_minutes:.1f} minutes) before next iteration...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Interrupted by user. Exiting.")
        logger.info("=" * 60)
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

