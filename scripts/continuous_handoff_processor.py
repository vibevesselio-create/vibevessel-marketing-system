#!/usr/bin/env python3
"""
Continuous Handoff Task Processor
=================================

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
import hashlib
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('continuous_handoff_processor.log')
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

# Agent capabilities mapping - determines best agent for task
AGENT_CAPABILITIES = {
    "Claude MM1 Agent": ["planning", "review", "coordination", "investigation", "analysis", "validation"],
    "Claude MM2 Agent": ["architecture", "review", "strategic-planning", "advanced-analysis"],
    "Claude Code Agent": ["code-review", "implementation", "debugging", "syntax", "gas", "javascript"],
    "Cursor MM1 Agent": ["implementation", "code", "fixes", "development", "debugging", "python", "typescript"],
    "Cursor MM2 Agent": ["implementation", "code", "advanced-development", "complex-fixes"],
    "Codex MM1 Agent": ["code", "implementation", "validation", "testing"],
    "ChatGPT Code Review Agent": ["code-review", "quality-assurance", "validation"],
    "ChatGPT Strategic Agent": ["strategic-planning", "architecture", "coordination"],
    "ChatGPT Personal Assistant Agent": ["coordination", "communication"],
    "Notion AI Data Operations Agent": ["notion", "data-operations", "database", "sync", "drivesheets"],
    "Notion AI Research Agent": ["research", "analysis", "notion", "investigation"],
}

# Priority order for sorting
PRIORITY_ORDER = ["Critical", "High", "Medium", "Low"]

# Pause durations (in seconds) to avoid rate limiting
PAUSE_AFTER_NOTION_QUERY = 1.0  # Pause after querying Notion
PAUSE_AFTER_NOTION_UPDATE = 0.5  # Pause after updating Notion page
PAUSE_AFTER_NOTION_CREATE = 1.0  # Pause after creating Notion page
PAUSE_AFTER_FILE_CREATE = 0.5  # Pause after creating trigger file
PAUSE_BETWEEN_REVIEWS = 2.0  # Pause between creating multiple review handoffs
PAUSE_AFTER_AGENT_LOOKUP = 0.3  # Pause after agent name lookup


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
            time.sleep(PAUSE_AFTER_AGENT_LOOKUP)  # Pause after Notion API call
            if assigned_agent_name:
                logger.info(f"  → Using assigned agent from Notion: {assigned_agent_name}")
                return assigned_agent_name, assigned_agent_id
    
    # If no assigned agent, determine based on task content
    task_title = safe_get_property(task, "Task Name", "title") or ""
    task_description = safe_get_property(task, "Description", "rich_text") or ""
    task_type = safe_get_property(task, "Task Type", "select") or ""
    next_step = safe_get_property(task, "Next Required Step", "rich_text") or ""
    
    combined_text = f"{task_title} {task_description} {task_type} {next_step}".lower()
    
    # Fast-path routing rules for common environments (higher signal than generic capability words).
    # These are intentionally conservative and only trigger on strong keywords.
    if any(k in combined_text for k in ["google apps script", "apps script", "appsscript", "code.gs", "gas-scripts", "appsscript.json"]):
        agent_name = "Claude Code Agent"
        return agent_name, AGENT_MAPPING.get(agent_name)

    if any(k in combined_text for k in ["python", ".py", "webhook", "webhook-server", "typescript", ".ts", ".tsx"]):
        agent_name = "Cursor MM1 Agent"
        return agent_name, AGENT_MAPPING.get(agent_name)

    if "notion" in combined_text and any(k in combined_text for k in ["database", "property", "relation", "drivesheets", "sync"]):
        agent_name = "Notion AI Data Operations Agent"
        return agent_name, AGENT_MAPPING.get(agent_name)

    if "research" in combined_text:
        agent_name = "Notion AI Research Agent"
        return agent_name, AGENT_MAPPING.get(agent_name)

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
        # Get agent with highest score (break ties with a stable preference order)
        max_score = max(keyword_matches.values())
        candidates = [name for name, score in keyword_matches.items() if score == max_score]

        tiebreak_preference = [
            "Cursor MM1 Agent",
            "Claude Code Agent",
            "Codex MM1 Agent",
            "Claude MM1 Agent",
            "Notion AI Data Operations Agent",
            "Notion AI Research Agent",
            "ChatGPT Code Review Agent",
            "Claude MM2 Agent",
            "Cursor MM2 Agent",
            "ChatGPT Strategic Agent",
            "ChatGPT Personal Assistant Agent",
        ]
        agent_name = next((n for n in tiebreak_preference if n in candidates), candidates[0])
        agent_id = AGENT_MAPPING.get(agent_name)
        logger.info(f"  → Matched agent by keywords: {agent_name} (score: {max_score})")
        return agent_name, agent_id
    
    # Default selection: prefer Cursor MM1 for execution/implementation work, otherwise Claude MM1.
    implementation_hints = [
        "implement", "implementation", "fix", "bug", "refactor", "script", "code",
        "deploy", "production", "execute", "run", "workflow",
    ]
    if any(k in combined_text for k in implementation_hints):
        agent_name = "Cursor MM1 Agent"
        logger.info("  → No specific match, defaulting to Cursor MM1 Agent (implementation hint detected)")
        return agent_name, AGENT_MAPPING.get(agent_name)

    logger.info("  → No specific match, defaulting to Claude MM1 Agent")
    return "Claude MM1 Agent", AGENT_MAPPING.get("Claude MM1 Agent")


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
    sorts = [
        {
            "property": "Priority",
            "direction": "ascending"
        }
    ]
    
    tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params, sorts=sorts)
    time.sleep(PAUSE_AFTER_NOTION_QUERY)  # Pause after Notion API call
    
    # Manual priority sorting (in case Notion sort doesn't work as expected)
    def get_priority_value(task):
        priority = safe_get_property(task, "Priority", "select") or "Medium"
        try:
            return PRIORITY_ORDER.index(priority)
        except ValueError:
            return len(PRIORITY_ORDER)  # Unknown priority goes to end
    
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
    def _norm_id(value: Optional[str]) -> str:
        return (value or "").replace("-", "").lower()

    agent_type = determine_agent_type(agent_name, agent_id)
    if agent_type == "MM1":
        base_path = MM1_AGENT_TRIGGER_BASE
    else:
        base_path = MM2_AGENT_TRIGGER_BASE
    
    agent_folder = normalize_agent_folder_name(agent_name, agent_id)
    if agent_type == "MM2":
        agent_folder = f"{agent_folder}-gd"

    normalized_task_id = _norm_id(task_id)
    token8 = normalized_task_id[:8]
    token16 = (
        f"{normalized_task_id[:8]}{normalized_task_id[-8:]}"
        if len(normalized_task_id) >= 16
        else normalized_task_id
    )

    # Check all subfolders. We first use filename patterns to narrow candidates,
    # then validate by reading JSON to avoid collisions on short prefixes.
    for subfolder in ["01_inbox", "02_processed", "03_failed"]:
        check_folder = base_path / agent_folder / subfolder
        if not check_folder.exists():
            continue

        candidates: List[Path] = []
        for pattern in [f"*{token16}*.json", f"*{normalized_task_id}*.json", f"*{token8}*.json"]:
            candidates.extend(check_folder.glob(pattern))

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)

            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidate_task_id = _norm_id(
                    data.get("task_id")
                    or data.get("agent_task_id")
                    or data.get("chain_tracking", {}).get("agent_task_id")
                )
                if candidate_task_id and candidate_task_id == normalized_task_id:
                    logger.info(f"  → Trigger file already exists: {candidate.name}")
                    return True
            except Exception:
                # Ignore unreadable/invalid JSON; continue scanning.
                continue

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
        time.sleep(PAUSE_AFTER_NOTION_CREATE)  # Pause after creating Notion page
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
    Process the next highest priority incomplete task that doesn't have a trigger file.
    
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
    
    # Find the first task that doesn't have a trigger file already
    task = None
    for candidate_task in tasks:
        task_id = candidate_task.get("id")
        agent_name, agent_id = determine_best_agent(candidate_task, notion)
        
        if agent_name and agent_id:
            if not check_existing_trigger_file(task_id, agent_name, agent_id):
                task = candidate_task
                break
    
    if not task:
        logger.info("All incomplete tasks already have trigger files. Waiting for processing...")
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
    
    # Check if trigger file already exists
    if check_existing_trigger_file(task_id, agent_name, agent_id):
        logger.info(f"  → Trigger file already exists. Skipping creation.")
        # Update task status to In Progress if it's Ready
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            notion.update_page(task_id, update_properties)
            time.sleep(PAUSE_AFTER_NOTION_UPDATE)  # Pause after updating Notion page
        return True
    
    # Create trigger file
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
    time.sleep(PAUSE_AFTER_FILE_CREATE)  # Pause after creating trigger file
    
    if trigger_file:
        logger.info(f"  → Created trigger file: {trigger_file}")
        
        # Update task status to In Progress
        if task_status in ["Ready", "Ready for Handoff", "Not Started"]:
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            notion.update_page(task_id, update_properties)
            time.sleep(PAUSE_AFTER_NOTION_UPDATE)  # Pause after updating Notion page
            logger.info(f"  → Updated task status to 'In Progress'")
        
        return True
    else:
        logger.error(f"  → Failed to create trigger file")
        return True  # Continue processing other tasks


def check_completed_tasks(notion: NotionManager, max_to_create: int = 10):
    """
    Check for recently completed tasks and create review handoffs.
    Only creates review handoffs for tasks that:
    1. Are completed (status = Complete/Completed)
    2. Are not already review tasks
    3. Don't already have a review handoff task
    4. Are not archived
    """
    if max_to_create <= 0:
        return

    # Filter for completed tasks that might need review
    # Exclude review tasks themselves to avoid infinite loops
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
            },
            {
                "property": "Task Name",
                "title": {"does_not_contain": "Review:"}
            }
        ]
    }
    
    completed_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    time.sleep(PAUSE_AFTER_NOTION_QUERY)  # Pause after querying Notion
    
    if not completed_tasks:
        return
    
    logger.info(f"Found {len(completed_tasks)} completed task(s) to check for review handoffs")
    
    created = 0
    for task in completed_tasks:
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or ""
        
        # Skip if this is already a review task
        if "Review:" in task_title:
            continue
        
        # Check if review task already exists (look for "Review:" prefix with task title)
        review_filter = {
            "and": [
                {
                    "property": "Task Name",
                    "title": {"contains": "Review:"}
                },
                {
                    "property": "Description",
                    "rich_text": {"contains": task_id}
                }
            ]
        }
        existing_reviews = notion.query_database(AGENT_TASKS_DB_ID, filter_params=review_filter)
        time.sleep(PAUSE_AFTER_NOTION_QUERY)  # Pause after querying Notion
        
        if not existing_reviews:
            logger.info(f"  → Creating review handoff for completed task: {task_title}")
            review_task_id = create_review_handoff(task, notion)
            if review_task_id:
                logger.info(f"  → Review handoff created successfully")
                created += 1
                if created >= max_to_create:
                    logger.info(f"Reached max_to_create={max_to_create}; deferring remaining review handoffs to later cycles")
                    break
            time.sleep(PAUSE_BETWEEN_REVIEWS)  # Pause between creating multiple review handoffs
        else:
            logger.debug(f"  → Review handoff already exists for: {task_title}")


def main():
    """Main continuous processing loop"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Continuous Handoff Task Processor")
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
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("CONTINUOUS HANDOFF TASK PROCESSOR")
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
            time.sleep(PAUSE_AFTER_NOTION_QUERY)  # Pause before processing next task
            
            # Process next task
            task_processed = process_next_task(notion)
            time.sleep(PAUSE_AFTER_NOTION_QUERY)  # Pause after processing task
            
            if not task_processed:
                consecutive_no_tasks += 1
                # Double-check that we truly have 0 tasks by querying again
                if consecutive_no_tasks >= 3:
                    final_check = get_incomplete_tasks(notion)
                    if not final_check:
                        logger.info("")
                        logger.info("=" * 60)
                        logger.info("✅ VERIFIED: 0 tasks remaining. All tasks complete!")
                        logger.info("=" * 60)
                        break
                    else:
                        logger.info(f"Tasks still exist ({len(final_check)}), continuing...")
                        consecutive_no_tasks = 0  # Reset counter
                elif args.once:
                    logger.info("")
                    logger.info("=" * 60)
                    logger.info("Single task mode complete. Exiting.")
                    logger.info("=" * 60)
                    break
            else:
                consecutive_no_tasks = 0
            
            if args.once:
                break
            
            # Wait before next iteration (default: 10 minutes = 600 seconds)
            interval_minutes = args.interval / 60
            logger.info("")
            logger.info(f"Waiting {args.interval} seconds ({interval_minutes:.1f} minutes) before next iteration...")
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

