#!/usr/bin/env python3
"""
Continuous Task Handoff Processor
==================================

Continuously processes Agent-Tasks from Notion, creating handoff trigger files
in the 01_inbox subdirectory for the appropriate agent based on capabilities
and environment.

When tasks complete, automatically creates review handoff tasks back to
Cursor MM1 Agent for validation.

This script runs continuously until 0 tasks remain in the Agent-Tasks database.

Author: Cursor MM1 Agent
Created: 2026-01-05
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

# Import from main.py
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

# Import from continuous_handoff_processor for shared logic
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
        logging.FileHandler('continuous_task_handoff_processor.log')
    ]
)
logger = logging.getLogger(__name__)

# Pause durations (in seconds) to avoid rate limiting
PAUSE_AFTER_NOTION_QUERY = 1.0
PAUSE_AFTER_NOTION_UPDATE = 0.5
PAUSE_AFTER_NOTION_CREATE = 1.0
PAUSE_AFTER_FILE_CREATE = 0.5
PAUSE_BETWEEN_REVIEWS = 2.0


def process_next_handoff_task(notion: NotionManager) -> bool:
    """
    Process the next highest-priority incomplete task by creating a handoff
    trigger file in the appropriate agent's 01_inbox directory.
    
    Returns:
        True if a task was processed, False if no tasks remain
    """
    logger.info("=" * 80)
    logger.info("PROCESSING NEXT HANDOFF TASK")
    logger.info("=" * 80)
    
    # Get incomplete tasks sorted by priority
    tasks = get_incomplete_tasks(notion)
    time.sleep(PAUSE_AFTER_NOTION_QUERY)
    
    if not tasks:
        logger.info("✅ No incomplete tasks found. All tasks complete!")
        return False
    
    logger.info(f"Found {len(tasks)} incomplete task(s)")
    
    # Find the first task that doesn't have a trigger file yet
    task = None
    for candidate_task in tasks:
        task_id = candidate_task.get("id")
        agent_name, agent_id = determine_best_agent(candidate_task, notion)
        time.sleep(PAUSE_AFTER_NOTION_QUERY)
        
        if agent_name and agent_id:
            if not check_existing_trigger_file(task_id, agent_name, agent_id):
                task = candidate_task
                break
    
    if not task:
        logger.info("All incomplete tasks already have trigger files. Waiting for processing...")
        return False
    
    # Extract task information
    task_id = task.get("id")
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_status = safe_get_property(task, "Status", "status") or "Unknown"
    task_priority = safe_get_property(task, "Priority", "select") or "Medium"
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    next_step = safe_get_property(task, "Next Required Step", "rich_text") or ""
    success_criteria = safe_get_property(task, "Success Criteria", "rich_text") or ""
    
    logger.info("")
    logger.info(f"📋 Task: {task_title}")
    logger.info(f"   Status: {task_status}")
    logger.info(f"   Priority: {task_priority}")
    logger.info(f"   URL: {task_url}")
    
    # Determine best agent for this task
    agent_name, agent_id = determine_best_agent(task, notion)
    time.sleep(PAUSE_AFTER_NOTION_QUERY)
    
    if not agent_name or not agent_id:
        logger.error(f"   ❌ Could not determine agent for task. Skipping.")
        return True  # Continue processing other tasks
    
    logger.info(f"   🤖 Assigned to: {agent_name}")
    
    # Build comprehensive handoff instructions
    handoff_instructions = f"""Proceed with the execution of this task. Upon completion, you MUST:

1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.

2. **Update Task Status**: Update the task status in Notion to 'Complete' or 'Completed'

3. **Documentation**: Document all work comprehensively in Notion, including:
   - Implementation details
   - Code changes (if any)
   - Testing results
   - Production validation
   - Any issues encountered and resolutions

4. **Production Validation**: Verify successful execution in production environment and that all workspace requirements are met

5. **Review Handoff**: A review handoff task will be automatically created back to Cursor MM1 Agent for validation. This ensures:
   - All requirements are met
   - Documentation is complete
   - Production execution is successful
   - Workspace requirements are validated

**MANDATORY:** Task is NOT complete until:
- Trigger file is manually moved to 02_processed
- Task status is updated in Notion
- All documentation is complete
- Production execution is validated

## Task Details

**Next Required Step:** {next_step if next_step else "Execute the task as described in the task description"}

**Success Criteria:** {success_criteria if success_criteria else "All task requirements met, documented, validated, and production execution successful"}
"""
    
    # Prepare task_details for trigger file
    task_details = {
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url,
        "description": task_description,
        "status": task_status,
        "agent_id": agent_id,
        "handoff_instructions": handoff_instructions,
        "priority": task_priority,
        "next_step": next_step,
        "success_criteria": success_criteria
    }
    
    # Determine agent type (MM1 or MM2)
    agent_type = determine_agent_type(agent_name, agent_id)
    
    # Create trigger file in 01_inbox
    logger.info(f"   📁 Creating handoff trigger file in 01_inbox...")
    trigger_file = create_trigger_file(agent_type, agent_name, task_details)
    time.sleep(PAUSE_AFTER_FILE_CREATE)
    
    if trigger_file:
        logger.info(f"   ✅ Created trigger file: {trigger_file}")
        
        # Update task status to In Progress if it's Ready/Not Started
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            if notion.update_page(task_id, update_properties):
                time.sleep(PAUSE_AFTER_NOTION_UPDATE)
                logger.info(f"   ✅ Updated task status to 'In Progress'")
        
        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ HANDOFF TASK CREATED SUCCESSFULLY")
        logger.info(f"   Task: {task_title}")
        logger.info(f"   Agent: {agent_name}")
        logger.info(f"   Trigger File: {trigger_file}")
        logger.info("=" * 80)
        return True
    else:
        logger.error(f"   ❌ Failed to create trigger file")
        return True  # Continue processing other tasks


def main():
    """Main continuous processing loop"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Continuous Task Handoff Processor - Processes Agent-Tasks until 0 remain"
    )
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
        '--skip-reviews',
        action='store_true',
        help='Skip checking for completed tasks and creating review handoffs'
    )
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("CONTINUOUS TASK HANDOFF PROCESSOR")
    logger.info("=" * 80)
    if args.once:
        logger.info("Running in single-task mode.")
    else:
        logger.info("Running in continuous mode until 0 tasks remain.")
        logger.info("This will:")
        logger.info("  1. Process highest-priority incomplete tasks")
        logger.info("  2. Create handoff trigger files in 01_inbox")
        logger.info("  3. Assign tasks to appropriate agents")
        logger.info("  4. Create review tasks when tasks complete")
        logger.info("  5. Continue until 0 tasks remain")
        logger.info("")
        logger.info("Press Ctrl+C to stop.")
    logger.info("")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        logger.error("❌ Failed to get Notion token. Exiting.")
        return 1
    
    notion = NotionManager(token)
    logger.info("✅ Notion client initialized")
    logger.info("")
    
    iteration = 0
    consecutive_no_tasks = 0
    
    try:
        while True:
            iteration += 1
            logger.info("")
            logger.info(f"🔄 Iteration {iteration}")
            logger.info("-" * 80)
            
            # Check for completed tasks and create review handoffs
            if not args.skip_reviews:
                logger.info("Checking for completed tasks...")
                check_completed_tasks(notion)
                time.sleep(PAUSE_AFTER_NOTION_QUERY)
            
            # Process next handoff task
            task_processed = process_next_handoff_task(notion)
            time.sleep(PAUSE_AFTER_NOTION_QUERY)
            
            if not task_processed:
                consecutive_no_tasks += 1
                # Double-check that we truly have 0 tasks
                if consecutive_no_tasks >= 3:
                    logger.info("")
                    logger.info("Verifying no tasks remain...")
                    final_check = get_incomplete_tasks(notion)
                    time.sleep(PAUSE_AFTER_NOTION_QUERY)
                    if not final_check:
                        logger.info("")
                        logger.info("=" * 80)
                        logger.info("✅ VERIFIED: 0 tasks remaining. All tasks complete!")
                        logger.info("=" * 80)
                        break
                    else:
                        logger.info(f"Tasks still exist ({len(final_check)}), continuing...")
                        consecutive_no_tasks = 0  # Reset counter
                elif args.once:
                    logger.info("")
                    logger.info("=" * 80)
                    logger.info("Single task mode complete. Exiting.")
                    logger.info("=" * 80)
                    break
            else:
                consecutive_no_tasks = 0
            
            if args.once:
                break
            
            # Wait before next iteration
            interval_minutes = args.interval / 60
            logger.info("")
            logger.info(f"⏳ Waiting {args.interval} seconds ({interval_minutes:.1f} minutes) before next iteration...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 80)
        logger.info("Interrupted by user. Exiting.")
        logger.info("=" * 80)
        return 0
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
