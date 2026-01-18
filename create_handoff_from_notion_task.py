#!/usr/bin/env python3
"""
Create Handoff Task from Notion Agent-Tasks Database
====================================================

This script:
1. Queries Notion Agent-Tasks database for highest priority uncompleted tasks
2. Determines appropriate agent based on capabilities
3. Creates handoff task file in Agent-Trigger-Folder/01_inbox
4. The orchestrator will then process this file and route it to the appropriate agent

This is part of the continuous handoff flow that continues until 0 tasks remain.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('create_handoff_from_notion_task.log')
    ]
)
logger = logging.getLogger(__name__)

# Import from main.py
try:
    from main import (
        get_notion_token,
        safe_get_property,
        normalize_agent_folder_name,
        NotionManager,
        MM1_AGENT_TRIGGER_BASE,
        AGENT_TASKS_DB_ID,
    )
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)

# Import shared agent-selection logic (keeps routing consistent across the handoff system)
try:
    from scripts.continuous_handoff_processor import (
        determine_best_agent,
        check_existing_trigger_file,
    )
except ImportError as e:
    logger.error(f"Failed to import determine_best_agent from scripts.continuous_handoff_processor: {e}")
    sys.exit(1)

# Priority mapping for sorting
PRIORITY_ORDER = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
    "P0": 0,
    "P1": 1,
    "P2": 2,
    "P3": 3,
}

# Status values that indicate incomplete tasks
INCOMPLETE_STATUSES = [
    "Ready", "Not Started", "In Progress", "In-Progress", 
    "Ready for Handoff", "Proposed", "Draft", "Blocked"
]


def get_next_tasks(notion: NotionManager, limit: int = 20) -> List[Dict]:
    """
    Query Agent-Tasks database for incomplete tasks.
    
    Args:
        limit: Maximum number of tasks to return
    
    Returns:
        List of task page objects
    """
    try:
        # Query for incomplete tasks
        filter_params = {
            "or": [
                {"property": "Status", "status": {"equals": status}}
                for status in INCOMPLETE_STATUSES
            ]
        }
        
        # Sort by priority (ascending, so Critical/High come first)
        # Then by last edited time (descending, so most recent first)
        sorts = [
            {"property": "Priority", "direction": "ascending"},
            {"timestamp": "last_edited_time", "direction": "descending"}
        ]
        
        tasks = notion.query_database(
            AGENT_TASKS_DB_ID,
            filter_params=filter_params,
            sorts=sorts,
        )[:limit]
        
        if not tasks:
            logger.info("No incomplete tasks found in Agent-Tasks database")
            return []
        
        logger.info(f"Found {len(tasks)} incomplete tasks")
        return tasks
        
    except Exception as e:
        logger.error(f"Error querying Agent-Tasks database: {e}", exc_info=True)
        return []


def determine_agent_for_task(notion: NotionManager, task: Dict) -> Optional[Tuple[str, str]]:
    """
    Determine the appropriate agent for a task using the shared continuous-handoff
    selection logic (Assigned-Agent relation → capability keyword match → default).
    """
    try:
        agent_name, agent_id = determine_best_agent(task, notion)
        if not agent_name or not agent_id:
            return None
        return agent_name, agent_id
    except Exception as e:
        logger.error(f"Error determining agent for task: {e}", exc_info=True)
        return None


def create_handoff_task_file(agent_name: str, task: Dict) -> Optional[Path]:
    """
    Create handoff task file in Agent-Trigger-Folder/01_inbox.
    
    Args:
        agent_name: Target agent name
        task: Task page object from Notion
    
    Returns:
        Path to created trigger file or None
    """
    try:
        # Create the Agent-Trigger-Folder/01_inbox directory
        trigger_folder = MM1_AGENT_TRIGGER_BASE / "01_inbox" / "Agent-Trigger-Folder"
        trigger_folder.mkdir(parents=True, exist_ok=True)
        
        # Get task details
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_url = task.get("url", "")
        task_description = safe_get_property(task, "Description", "rich_text") or ""
        task_priority = safe_get_property(task, "Priority", "select") or "Medium"
        task_status = safe_get_property(task, "Status", "status") or "Ready"
        next_step = safe_get_property(task, "Next Required Step", "rich_text") or safe_get_property(task, "Next Step", "rich_text") or ""
        success_criteria = safe_get_property(task, "Success Criteria", "rich_text") or ""
        
        # Check for existing trigger file to prevent duplicates.
        # NOTE: Many Notion page IDs share the same leading prefix, so we validate by reading JSON.
        def _norm_id(value: Optional[str]) -> str:
            return (value or "").replace("-", "").lower()

        normalized_task_id = _norm_id(task_id)
        token8 = normalized_task_id[:8] if normalized_task_id else "unknown"
        token16 = (
            f"{normalized_task_id[:8]}{normalized_task_id[-8:]}"
            if len(normalized_task_id) >= 16
            else normalized_task_id
        ) or "unknown"

        candidates: List[Path] = []
        for pattern in [f"*{token16}*.json", f"*{normalized_task_id}*.json", f"*{token8}*.json"]:
            candidates.extend(trigger_folder.glob(pattern))

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                candidate_task_id = _norm_id(data.get("task_id") or data.get("agent_task_id"))
                if candidate_task_id and candidate_task_id == normalized_task_id:
                    logger.info(
                        f"Handoff task file already exists for task {token16}: {candidate.name}. Skipping."
                    )
                    return None
            except Exception:
                continue
        
        # Create trigger file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{token16}.json"
        
        trigger_file = trigger_folder / filename
        
        # Check if this is a music workflow task
        task_content_lower = (task_title + " " + task_description).lower()
        music_keywords = [
            "music track sync", "music workflow", "track download",
            "soundcloud download", "spotify track", "youtube track",
            "music sync", "track processing", "music automation"
        ]
        is_music_workflow = any(keyword in task_content_lower for keyword in music_keywords)
        
        # Create trigger content in format expected by orchestrator
        trigger_content = {
            "title": task_title,
            "description": task_description,
            "priority": task_priority,
            "target_agent": agent_name,
            "source_agent": "Auto/Cursor MM1 Agent",
            "task_url": task_url,
            "task_id": task_id,
            "agent_task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "required_action": next_step or "Complete this task as specified in the description.",
            "success_criteria": success_criteria or "Task completed, documented in Notion, and review handoff created back to Auto/Cursor MM1 Agent.",
            "chain_tracking": {
                "agent_task_id": task_id,
                "dedupe_key": f"handoff_{task_id}",
                "source": "continuous_handoff_system"
            },
            "archive_rule": "move_to_02_processed",
        }
        
        # Add music workflow execution instructions if applicable
        if is_music_workflow:
            trigger_content["workflow_type"] = "music_track_sync"
            trigger_content["execution_script"] = "execute_music_track_sync_workflow.py"
            trigger_content["handoff_instructions"] = (
                f"Execute Music Track Sync Workflow v3.0:\n\n"
                f"1. Read the task description for track URL or source requirements\n"
                f"2. Execute: python3 execute_music_track_sync_workflow.py [--url URL] [--mode PROD|DEV]\n"
                f"3. Verify file creation (M4A, AIFF, WAV)\n"
                f"4. Verify Notion database updates\n"
                f"5. Verify Eagle library import\n"
                f"6. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed\n"
                f"7. Update the task status in Notion to 'Complete'\n"
                f"8. Create a review/validation handoff task back to Auto/Cursor MM1 Agent in the Agent-Tasks database\n"
                f"9. Document all deliverables and artifacts in Notion\n\n"
                f"**MANDATORY:** Task is NOT complete until trigger file is moved and review handoff is created."
            )
        else:
            trigger_content["handoff_instructions"] = (
                f"Complete this task as specified. Upon completion, you MUST:\n"
                f"1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed\n"
                f"2. Update the task status in Notion to 'Complete'\n"
                f"3. Create a review/validation handoff task back to Auto/Cursor MM1 Agent in the Agent-Tasks database\n"
                f"4. Document all deliverables and artifacts in Notion\n"
                f"5. Ensure all workspace requirements are met\n\n"
                f"**MANDATORY:** Task is NOT complete until trigger file is moved and review handoff is created. "
                f"The review handoff should be created in the Agent-Tasks database and assigned back to Auto/Cursor MM1 Agent for final validation."
            )
        
        # Write trigger file
        with open(trigger_file, "w", encoding="utf-8") as f:
            json.dump(trigger_content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Created handoff task file: {trigger_file}")
        return trigger_file
        
    except Exception as e:
        logger.error(f"Error creating handoff task file: {e}", exc_info=True)
        return None


def process_next_task(notion: NotionManager) -> bool:
    """
    Process the next task from Agent-Tasks database.
    
    Returns:
        True if a task was processed, False if no tasks available
    """
    logger.info("=" * 80)
    logger.info("Processing next task from Agent-Tasks database")
    logger.info("=" * 80)
    
    # Get multiple tasks at once
    tasks = get_next_tasks(notion, limit=20)
    if not tasks:
        logger.info("No tasks available for processing")
        return False
    
    # Try each task until we find one we can process
    for task in tasks:
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_priority = safe_get_property(task, "Priority", "select") or "Medium"
        task_status = safe_get_property(task, "Status", "status") or "Ready"
        
        logger.info(f"Checking task: '{task_title}' (Priority: {task_priority}, Status: {task_status})")
        
        # Determine agent
        agent = determine_agent_for_task(notion, task)
        if not agent:
            logger.warning(f"Could not determine agent for task '{task_title}', skipping")
            continue
        agent_name, _agent_id = agent

        # Prevent duplicate handoffs: if a trigger already exists in the chosen agent's
        # inbox/processed/failed folders, skip and try the next task.
        task_id = task.get("id") or ""
        if task_id and check_existing_trigger_file(task_id, agent_name, _agent_id):
            logger.info(f"Existing trigger file found for task '{task_title}'. Skipping duplicate handoff creation.")
            continue
        
        # Create handoff task file
        trigger_file = create_handoff_task_file(agent_name, task)
        if trigger_file:
            logger.info(f"✅ Successfully created handoff task file for task '{task_title}' assigned to {agent_name}")
            return True
        else:
            logger.warning(f"Failed to create handoff task file for task '{task_title}', trying next task")
            continue
    
    logger.info("All available tasks already have handoff task files or could not be processed")
    return False


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Create Handoff Task from Notion Agent-Tasks Database")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument("--interval", type=int, default=60, help="Interval between checks in seconds (default: 60)")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Create Handoff Task from Notion Agent-Tasks Database")
    logger.info("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        logger.error("NOTION_TOKEN not found. Cannot proceed.")
        sys.exit(1)
    
    notion_client = NotionManager(token)
    
    # Validate access
    try:
        notion_client.client.users.me()
        logger.info("✅ Notion API access validated")
    except Exception as e:
        logger.error(f"Notion API access validation failed: {e}")
        sys.exit(1)
    
    # Process tasks
    if args.once:
        # Process one task and exit
        process_next_task(notion_client)
    else:
        # Continuous loop
        logger.info(f"Starting continuous processing (checking every {args.interval} seconds)")
        logger.info("Press Ctrl+C to stop")
        logger.info("System will continue until 0 tasks remain in Agent-Tasks database")
        
        import time
        try:
            while True:
                task_processed = process_next_task(notion_client)
                
                if not task_processed:
                    logger.info(f"No tasks available. Waiting {args.interval} seconds before next check...")
                
                time.sleep(args.interval)
                
        except KeyboardInterrupt:
            logger.info("\nStopped by user")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()





















