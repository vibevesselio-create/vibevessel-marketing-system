#!/usr/bin/env python3
"""
Continuous Task Handoff System
==============================

This script continuously processes Agent-Tasks from Notion:
1. Queries Agent-Tasks database for highest priority uncompleted tasks
2. Determines appropriate agent based on capabilities
3. Creates trigger files in agent inbox folders
4. Continues until all tasks are complete

Usage:
    python3 continuous_task_handoff.py [--once] [--interval 60]
"""

import os
import sys
import json
import logging
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

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
        logging.FileHandler('continuous_task_processor.log')
    ]
)
logger = logging.getLogger(__name__)

# Try to import notion-client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.error("notion-client not available. Install with: pip install notion-client")
    NOTION_CLIENT_AVAILABLE = False
    Client = None

# Import from main.py
try:
    from main import (
        get_notion_token, safe_get_property, normalize_agent_folder_name,
        MM1_AGENT_TRIGGER_BASE, AGENT_TASKS_DB_ID
    )
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)

# Database ID
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")

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


def get_next_tasks(notion_client: Client, limit: int = 20) -> List[Dict]:
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
        
        response = notion_client.databases.query(
            database_id=AGENT_TASKS_DB_ID,
            filter=filter_params,
            sorts=sorts,
            page_size=limit
        )
        
        tasks = response.get("results", [])
        
        if not tasks:
            logger.info("No incomplete tasks found in Agent-Tasks database")
            return []
        
        logger.info(f"Found {len(tasks)} incomplete tasks")
        return tasks
        
    except Exception as e:
        logger.error(f"Error querying Agent-Tasks database: {e}", exc_info=True)
        return []


def determine_agent_for_task(notion_client: Client, task: Dict) -> Optional[Dict[str, str]]:
    """
    Determine the appropriate agent for a task based on:
    1. Assigned-Agent relation (if present)
    2. Task requirements and agent capabilities
    3. Default agent selection logic
    
    Returns:
        Dict with agent_name, agent_id, agent_type, or None
    """
    try:
        # First, check if task has an assigned agent
        assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
        
        if assigned_agent_relation and len(assigned_agent_relation) > 0:
            agent_id = assigned_agent_relation[0].get("id")
            try:
                agent_page = notion_client.pages.retrieve(agent_id)
                agent_name = safe_get_property(agent_page, "Name", "title") or safe_get_property(agent_page, "Agent Name", "title")
                
                if agent_name:
                    # Determine agent type (MM1 or MM2)
                    agent_name_lower = agent_name.lower()
                    if "mm2" in agent_name_lower or "google drive" in agent_name_lower or "gd" in agent_name_lower:
                        agent_type = "MM2"
                    else:
                        agent_type = "MM1"
                    
                    logger.info(f"Task has assigned agent: {agent_name} ({agent_type})")
                    return {
                        "agent_name": agent_name,
                        "agent_id": agent_id,
                        "agent_type": agent_type
                    }
            except Exception as e:
                logger.warning(f"Error retrieving assigned agent page: {e}")
        
        # If no assigned agent, use default logic based on task title/description
        task_title = safe_get_property(task, "Task Name", "title") or ""
        task_description = safe_get_property(task, "Description", "rich_text") or ""
        task_content = (task_title + " " + task_description).lower()
        
        # Default agent selection logic
        # For code implementation tasks, use Cursor MM1
        # For planning/review tasks, use Claude MM1
        # For research tasks, use Notion AI Research Agent
        # For data operations, use Notion AI Data Operations Agent
        
        if any(keyword in task_content for keyword in ["validation", "review", "plan", "analysis", "design"]):
            agent_name = "Claude MM1 Agent"
            agent_id = "fa54f05c-e184-403a-ac28-87dd8ce9855b"
            agent_type = "MM1"
        elif any(keyword in task_content for keyword in ["research", "notion ai"]):
            agent_name = "Notion AI Research Agent"
            agent_id = None  # Will need to look up
            agent_type = "MM1"
        elif any(keyword in task_content for keyword in ["data", "database", "sync"]):
            agent_name = "Notion AI Data Operations Agent"
            agent_id = None  # Will need to look up
            agent_type = "MM1"
        else:
            # Default to Cursor MM1 for implementation tasks
            agent_name = "Cursor MM1 Agent"
            agent_id = "249e7361-6c27-8100-8a74-de7eabb9fc8d"
            agent_type = "MM1"
        
        logger.info(f"Determined default agent for task: {agent_name} ({agent_type})")
        return {
            "agent_name": agent_name,
            "agent_id": agent_id,
            "agent_type": agent_type
        }
        
    except Exception as e:
        logger.error(f"Error determining agent for task: {e}", exc_info=True)
        return None


def create_trigger_file(agent_info: Dict[str, str], task: Dict) -> Optional[Path]:
    """
    Create trigger file in the agent's 01_inbox folder.
    
    Args:
        agent_info: Dict with agent_name, agent_id, agent_type
        task: Task page object from Notion
    
    Returns:
        Path to created trigger file or None
    """
    try:
        agent_name = agent_info["agent_name"]
        agent_id = agent_info.get("agent_id")
        agent_type = agent_info["agent_type"]
        
        # Determine base path
        if agent_type == "MM1":
            base_path = MM1_AGENT_TRIGGER_BASE
        else:
            from main import MM2_AGENT_TRIGGER_BASE
            base_path = MM2_AGENT_TRIGGER_BASE
        
        # Normalize agent folder name
        agent_folder = normalize_agent_folder_name(agent_name, agent_id)
        if agent_type == "MM2":
            agent_folder = f"{agent_folder}-gd"
        
        # Create inbox folder
        inbox_folder = base_path / agent_folder / "01_inbox"
        inbox_folder.mkdir(parents=True, exist_ok=True)
        
        # Get task details
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_url = task.get("url", "")
        task_description = safe_get_property(task, "Description", "rich_text") or ""
        task_priority = safe_get_property(task, "Priority", "select") or "Medium"
        task_status = safe_get_property(task, "Status", "status") or "Ready"
        
        # Check for existing trigger file to prevent duplicates
        # Only skip if file exists in 01_inbox (pending) - allow retry if in 03_failed
        task_id_short = task_id.replace("-", "")[:8] if task_id else "unknown"
        inbox_folder_check = base_path / agent_folder / "01_inbox"
        if inbox_folder_check.exists():
            existing_inbox_files = list(inbox_folder_check.glob(f"*{task_id_short}*.json"))
            if existing_inbox_files:
                logger.info(
                    f"Trigger file already exists in inbox for task {task_id_short}: {existing_inbox_files[0].name}. Skipping."
                )
                return None  # Return None to indicate task should be skipped
        
        # Create trigger file
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.json"
        
        trigger_file = inbox_folder / filename
        
        # Create trigger content
        trigger_content = {
            "task_id": task_id,
            "task_title": task_title,
            "task_url": task_url,
            "description": task_description,
            "status": task_status,
            "priority": task_priority,
            "agent_name": agent_name,
            "agent_type": agent_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "handoff_instructions": (
                f"Complete this task as specified. Upon completion, you MUST:\n"
                f"1. **MOVE TRIGGER FILE (MANUAL)**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed\n"
                f"2. Update the task status in Notion to 'Complete'\n"
                f"3. Create a review/validation handoff task back to the orchestrator (Auto/Cursor MM1 Agent)\n"
                f"4. Document all deliverables and artifacts in Notion\n"
                f"5. Ensure all workspace requirements are met\n\n"
                f"**MANDATORY:** Task is NOT complete until trigger file is moved and review handoff is created."
            )
        }
        
        # Write trigger file
        with open(trigger_file, "w", encoding="utf-8") as f:
            json.dump(trigger_content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Created trigger file: {trigger_file}")
        return trigger_file
        
    except Exception as e:
        logger.error(f"Error creating trigger file: {e}", exc_info=True)
        return None


def task_has_trigger_file_in_inbox(notion_client: Client, task: Dict, agent_info: Dict[str, str]) -> bool:
    """
    Check if a task already has a trigger file in the agent's inbox.
    
    Returns:
        True if trigger file exists in inbox, False otherwise
    """
    try:
        agent_type = agent_info["agent_type"]
        agent_name = agent_info["agent_name"]
        agent_id = agent_info.get("agent_id")
        
        # Determine base path
        if agent_type == "MM1":
            base_path = MM1_AGENT_TRIGGER_BASE
        else:
            from main import MM2_AGENT_TRIGGER_BASE
            base_path = MM2_AGENT_TRIGGER_BASE
        
        # Normalize agent folder name
        agent_folder = normalize_agent_folder_name(agent_name, agent_id)
        if agent_type == "MM2":
            agent_folder = f"{agent_folder}-gd"
        
        # Check inbox folder
        inbox_folder = base_path / agent_folder / "01_inbox"
        if not inbox_folder.exists():
            return False
        
        task_id = task.get("id")
        task_id_short = task_id.replace("-", "")[:8] if task_id else "unknown"
        
        existing_files = list(inbox_folder.glob(f"*{task_id_short}*.json"))
        return len(existing_files) > 0
        
    except Exception as e:
        logger.warning(f"Error checking for existing trigger file: {e}")
        return False


def process_next_task(notion_client: Client) -> bool:
    """
    Process the next task from Agent-Tasks database.
    
    Returns:
        True if a task was processed, False if no tasks available
    """
    logger.info("=" * 80)
    logger.info("Processing next task from Agent-Tasks database")
    logger.info("=" * 80)
    
    # Get multiple tasks at once
    tasks = get_next_tasks(notion_client, limit=20)
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
        agent_info = determine_agent_for_task(notion_client, task)
        if not agent_info:
            logger.warning(f"Could not determine agent for task '{task_title}', skipping")
            continue
        
        # Check if trigger file already exists in inbox
        if task_has_trigger_file_in_inbox(notion_client, task, agent_info):
            logger.info(f"Task '{task_title}' already has trigger file in inbox, skipping")
            continue
        
        # Create trigger file
        trigger_file = create_trigger_file(agent_info, task)
        if trigger_file:
            logger.info(f"✅ Successfully created trigger file for task '{task_title}' in {agent_info['agent_name']}'s inbox")
            return True
        else:
            logger.warning(f"Failed to create trigger file for task '{task_title}', trying next task")
            continue
    
    logger.info("All available tasks already have trigger files or could not be processed")
    return False


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="Continuous Task Handoff System")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument("--interval", type=int, default=60, help="Interval between checks in seconds (default: 60)")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Continuous Task Handoff System")
    logger.info("=" * 80)
    
    # Get Notion token
    token = get_notion_token()
    if not token:
        logger.error("NOTION_TOKEN not found. Cannot proceed.")
        sys.exit(1)
    
    # Initialize Notion client
    if not NOTION_CLIENT_AVAILABLE:
        logger.error("notion-client library not available")
        sys.exit(1)
    
    notion_client = Client(auth=token)
    
    # Validate access
    try:
        notion_client.users.me()
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

