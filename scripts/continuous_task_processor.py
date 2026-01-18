#!/usr/bin/env python3
"""
Continuous Task Processor
=========================

Continuously processes Agent-Tasks from Notion, creating handoff files for the
appropriate agents based on task requirements and agent capabilities.

When tasks complete, creates review handoff tasks back to Cursor MM1 Agent.

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
    CLAUDE_MM1_AGENT_ID,
    CURSOR_MM1_AGENT_ID,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('continuous_task_processor.log')
    ]
)
logger = logging.getLogger(__name__)

# Agent mapping from trigger_folder_orchestrator.py
AGENT_MAPPING = {
    "Claude MM1 Agent": "fa54f05c-e184-403a-ac28-87dd8ce9855b",
    "Claude MM2 Agent": "9c4b6040-5e0f-4d31-ae1b-d4a43743b224",
    "Claude Code Agent": "2cfe7361-6c27-805f-857c-e90c3db6efb9",
    "Cursor MM1 Agent": "249e7361-6c27-8100-8a74-de7eabb9fc8d",
    "Cursor MM2 Agent": "26de7361-6c27-80c2-b7cd-c1a2a0279937",
    "Codex MM1 Agent": "2b1e7361-6c27-80fb-8ce9-fd3cf78a5cad",
    "ChatGPT Code Review Agent": "2b4e7361-6c27-8129-8f6f-dff0dfb23e8e",
    "ChatGPT Strategic Agent": "2b1e7361-6c27-80d5-b162-d73c6396c31c",
    "ChatGPT Personal Assistant Agent": "13bb306b-1e55-45be-99c6-b5638618ba04",
    "Notion AI Data Operations Agent": "3e6cfe03-c82e-4aee-974a-e2ee6a69c187",
    "Notion AI Research Agent": "249e7361-6c27-8111-8327-d707f35e2c6a",
}

# Reverse mapping: ID -> Name
AGENT_ID_TO_NAME = {v: k for k, v in AGENT_MAPPING.items()}

# Agent capabilities mapping (simplified - can be expanded)
AGENT_CAPABILITIES = {
    "Claude MM1 Agent": ["planning", "review", "coordination", "investigation", "analysis"],
    "Claude MM2 Agent": ["architecture", "review", "strategic-planning"],
    "Claude Code Agent": ["code-review", "implementation", "debugging"],
    "Cursor MM1 Agent": ["implementation", "code", "fixes", "development", "debugging"],
    "Cursor MM2 Agent": ["implementation", "code", "advanced-development"],
    "Codex MM1 Agent": ["code", "implementation", "validation"],
    "ChatGPT Code Review Agent": ["code-review", "quality-assurance"],
    "ChatGPT Strategic Agent": ["strategic-planning", "architecture", "coordination"],
    "ChatGPT Personal Assistant Agent": ["coordination", "communication"],
    "Notion AI Data Operations Agent": ["notion", "data-operations", "database", "sync"],
    "Notion AI Research Agent": ["research", "analysis", "notion"],
}


def determine_best_agent(task: Dict, notion: NotionManager) -> tuple[Optional[str], Optional[str]]:
    """
    Determine the best agent for a task based on:
    1. Assigned agent (if already assigned)
    2. Task requirements and agent capabilities
    3. Task type keywords
    
    Returns:
        Tuple of (agent_name, agent_id) or (None, None) if cannot determine
    """
    # First, check if task already has an assigned agent
    assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
    if assigned_agent_relation and len(assigned_agent_relation) > 0:
        assigned_agent_id = assigned_agent_relation[0].get("id")
        assigned_agent_name = AGENT_ID_TO_NAME.get(assigned_agent_id)
        if assigned_agent_name:
            logger.info(f"  → Using assigned agent: {assigned_agent_name}")
            return assigned_agent_name, assigned_agent_id
        else:
            # Try to get name from Notion
            assigned_agent_name = notion.get_page_title(assigned_agent_id)
            if assigned_agent_name:
                logger.info(f"  → Using assigned agent from Notion: {assigned_agent_name}")
                return assigned_agent_name, assigned_agent_id
    
    # If no assigned agent, determine based on task content
    task_title = safe_get_property(task, "Task Name", "title") or ""
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    task_type = safe_get_property(task, "Task Type", "select") or ""
    
    combined_text = f"{task_title} {task_description} {task_type}".lower()
    
    # Keyword-based matching
    keyword_matches = {}
    for agent_name, capabilities in AGENT_CAPABILITIES.items():
        score = 0
        for capability in capabilities:
            if capability in combined_text:
                score += 1
        if score > 0:
            keyword_matches[agent_name] = score
    
    if keyword_matches:
        # Get agent with highest score
        best_agent = max(keyword_matches.items(), key=lambda x: x[1])
        agent_name = best_agent[0]
        agent_id = AGENT_MAPPING.get(agent_name)
        logger.info(f"  → Matched agent by keywords: {agent_name} (score: {best_agent[1]})")
        return agent_name, agent_id
    
    # Default to Claude MM1 Agent for planning/coordination tasks
    logger.info(f"  → No specific match, defaulting to Claude MM1 Agent")
    return "Claude MM1 Agent", CLAUDE_MM1_AGENT_ID


def get_incomplete_tasks(notion: NotionManager) -> List[Dict]:
    """
    Query Notion for incomplete tasks, sorted by priority.
    
    Returns:
        List of task pages sorted by priority (Critical > High > Medium > Low)
    """
    # Filter for incomplete tasks (exclude Complete, Completed, and archived)
    filter_params = {
        "and": [
            {
                "and": [
                    {"property": "Status", "status": {"does_not_equal": "Complete"}},
                    {"property": "Status", "status": {"does_not_equal": "Completed"}},
                ]
            },
            {
                "property": "Archive",
                "checkbox": {"equals": False}
            }
        ]
    }
    
    # Sort by priority: Critical > High > Medium > Low
    priority_order = ["Critical", "High", "Medium", "Low"]
    sorts = [
        {
            "property": "Priority",
            "direction": "ascending"
        }
    ]
    
    tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params, sorts=sorts)
    
    # Manual priority sorting (in case Notion sort doesn't work as expected)
    def get_priority_value(task):
        priority = safe_get_property(task, "Priority", "select") or "Medium"
        try:
            return priority_order.index(priority)
        except ValueError:
            return len(priority_order)  # Unknown priority goes to end
    
    tasks_sorted = sorted(tasks, key=get_priority_value)
    
    # Post-filter to ensure we only return truly incomplete tasks
    incomplete_tasks = []
    for task in tasks_sorted:
        status = safe_get_property(task, "Status", "status") or ""
        status_lower = status.lower()
        # Exclude completed tasks
        if status_lower not in ["complete", "completed"]:
            incomplete_tasks.append(task)
    
    return incomplete_tasks


def check_existing_trigger_file(task_id: str, agent_name: str, agent_id: str) -> bool:
    """
    Check if a trigger file already exists for this task.
    
    Returns:
        True if trigger file exists, False otherwise
    """
    agent_type = determine_agent_type(agent_name, agent_id)
    if agent_type == "MM1":
        base_path = MM1_AGENT_TRIGGER_BASE
    else:
        base_path = MM2_AGENT_TRIGGER_BASE
    
    agent_folder = normalize_agent_folder_name(agent_name, agent_id)
    if agent_type == "MM2":
        agent_folder = f"{agent_folder}-gd"
    
    task_id_short = task_id.replace("-", "")[:8]
    
    # Check all subfolders
    for subfolder in ["01_inbox", "02_processed", "03_failed"]:
        check_folder = base_path / agent_folder / subfolder
        if check_folder.exists():
            existing_files = list(check_folder.glob(f"*{task_id_short}*.json"))
            if existing_files:
                logger.info(f"  → Trigger file already exists: {existing_files[0].name}")
                return True
    
    return False


def create_review_handoff(task: Dict, notion: NotionManager) -> Optional[str]:
    """
    Create a review handoff task back to Cursor MM1 Agent when a task completes.
    
    Returns:
        Task ID of created review task or None if failed
    """
    task_id = task.get("id")
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    
    review_title = f"Review: {task_title}"
    # Truncate description to fit Notion's 2000 character limit
    task_desc_truncated = task_description[:800] if len(task_description) > 800 else task_description
    
    review_description = f"""## Task Completion Review

**Original Task:** {task_title}
**Task URL:** {task_url}
**Task ID:** {task_id}

## Review Requirements

1. **Validate Completion**: Verify all task requirements have been met
2. **Check Documentation**: Ensure all work is properly documented in Notion
3. **Verify Production**: Confirm successful execution in production environment
4. **Workspace Requirements**: Validate that all workspace requirements are met
5. **Next Steps**: Determine if any follow-up work is needed

## Original Task Description

{task_desc_truncated}

## Review Instructions

Please review the completed task and:
- Confirm all deliverables are complete
- Verify documentation is comprehensive
- Check that production execution was successful
- Validate workspace requirements are met
- Create any necessary follow-up tasks if work remains
"""
    
    # Ensure total length is under 2000 characters
    if len(review_description) > 2000:
        # Truncate more aggressively
        available_space = 2000 - len(review_description) + len(task_desc_truncated)
        task_desc_truncated = task_description[:max(0, available_space - 200)]
        review_description = f"""## Task Completion Review

**Original Task:** {task_title}
**Task URL:** {task_url}
**Task ID:** {task_id}

## Review Requirements

1. **Validate Completion**: Verify all task requirements have been met
2. **Check Documentation**: Ensure all work is properly documented in Notion
3. **Verify Production**: Confirm successful execution in production environment
4. **Workspace Requirements**: Validate that all workspace requirements are met
5. **Next Steps**: Determine if any follow-up work is needed

## Original Task Description

{task_desc_truncated}

## Review Instructions

Please review the completed task and confirm all deliverables are complete, documentation is comprehensive, production execution was successful, and workspace requirements are met.
"""
    
    # Create review task properties
    properties = {
        "Task Name": {
            "title": [{"text": {"content": review_title}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": review_description}}]
        },
        "Status": {
            "status": {"name": "Ready"}
        },
        "Priority": {
            "select": {"name": "High"}
        },
        "Task Type": {
            "select": {"name": "Review Task"}
        },
        "Assigned-Agent": {
            "relation": [{"id": CURSOR_MM1_AGENT_ID}]
        }
    }
    
    try:
        review_task = notion.create_page(AGENT_TASKS_DB_ID, properties)
        if review_task:
            review_task_id = review_task.get("id")
            review_task_url = review_task.get("url", "")
            logger.info(f"  → Created review handoff task: {review_task_url}")
            return review_task_id
    except Exception as e:
        logger.error(f"  → Failed to create review handoff: {e}")
    
    return None


def process_next_task(notion: NotionManager) -> bool:
    """
    Process the next highest priority incomplete task.
    
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
    
    # Process the first (highest priority) task
    task = tasks[0]
    task_id = task.get("id")
    task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
    task_status = safe_get_property(task, "Status", "status") or "Unknown"
    task_priority = safe_get_property(task, "Priority", "select") or "Medium"
    task_url = task.get("url", "")
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    
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
    
    # Check if trigger file already exists
    if check_existing_trigger_file(task_id, agent_name, agent_id):
        logger.info(f"  → Trigger file already exists. Skipping creation.")
        # Update task status to In Progress if it's Ready
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            notion.update_page(task_id, update_properties)
        return True
    
    # Create trigger file
    logger.info(f"  → Creating handoff file for {agent_name}...")
    
    task_details = {
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url,
        "description": task_description,
        "status": task_status,
        "agent_name": agent_name,
        "agent_id": agent_id,
        "priority": task_priority,
        "handoff_instructions": (
            "Proceed with the execution of this task. Upon completion, you MUST:\n"
            "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
            "2. Update the task status in Notion to 'Complete'\n"
            "3. Document all work comprehensively in Notion\n"
            "4. Verify production execution and workspace requirements are met\n"
            "5. A review handoff task will be automatically created back to Cursor MM1 Agent for validation\n\n"
            "**MANDATORY:** Task is NOT complete until trigger file is manually moved, status is updated, and all documentation is complete."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_agent": "Cursor MM1 Agent (Continuous Task Processor)",
        "chain_tracking": {
            "chain_id": f"continuous-processing-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "step_number": 1,
            "previous_step": None,
            "next_expected": "Task Completion and Review Handoff"
        },
        "archive_rule": "move_to_02_processed"
    }
    
    agent_type = determine_agent_type(agent_name, agent_id)
    trigger_file = create_trigger_file(agent_type, agent_name, task_details)
    
    if trigger_file:
        logger.info(f"  → Created trigger file: {trigger_file}")
        
        # Update task status to In Progress
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            notion.update_page(task_id, update_properties)
            logger.info(f"  → Updated task status to 'In Progress'")
        
        return True
    else:
        logger.error(f"  → Failed to create trigger file")
        return True  # Continue processing other tasks


def check_completed_tasks(notion: NotionManager):
    """
    Check for recently completed tasks and create review handoffs.
    """
    # Filter for completed tasks that might need review
    filter_params = {
        "and": [
            {
                "or": [
                    {"property": "Status", "status": {"equals": "Complete"}},
                    {"property": "Status", "status": {"equals": "Completed"}},
                ]
            },
            {
                "property": "Archive",
                "checkbox": {"equals": False}
            }
        ]
    }
    
    completed_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    for task in completed_tasks:
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or ""
        
        # Check if review task already exists (simple check - look for "Review:" in title)
        # This is a simplified check - in production, you might want to track review tasks more carefully
        review_filter = {
            "and": [
                {
                    "property": "Task Name",
                    "title": {"contains": f"Review: {task_title[:50]}"}
                }
            ]
        }
        existing_reviews = notion.query_database(AGENT_TASKS_DB_ID, filter_params=review_filter)
        
        if not existing_reviews:
            logger.info(f"Creating review handoff for completed task: {task_title}")
            create_review_handoff(task, notion)


def main():
    """Main continuous processing loop"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Continuous Task Processor")
    parser.add_argument(
        '--once',
        action='store_true',
        help='Process only one task and exit'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=10,
        help='Interval between iterations in seconds (default: 10)'
    )
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("CONTINUOUS TASK PROCESSOR")
    logger.info("=" * 60)
    if args.once:
        logger.info("Running in single-task mode.")
    else:
        logger.info("This script will continuously process Agent-Tasks until 0 tasks remain.")
        logger.info("Press Ctrl+C to stop.")
    logger.info("")
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token. Exiting.")
        return
    
    notion = NotionManager(token)
    
    iteration = 0
    consecutive_no_tasks = 0
    
    try:
        while True:
            iteration += 1
            logger.info("")
            logger.info(f"Iteration {iteration}")
            logger.info("-" * 60)
            
            # Check for completed tasks and create review handoffs
            check_completed_tasks(notion)
            
            # Process next task
            task_processed = process_next_task(notion)
            
            if not task_processed:
                consecutive_no_tasks += 1
                if consecutive_no_tasks >= 3 or args.once:
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
            
            if args.once:
                break
            
            # Wait before next iteration
            logger.info("")
            logger.info(f"Waiting {args.interval} seconds before next iteration...")
            time.sleep(args.interval)
    
    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Interrupted by user. Exiting.")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    main()

