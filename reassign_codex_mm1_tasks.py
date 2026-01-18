#!/usr/bin/env python3
"""
Reassign Codex MM1 Agent Tasks to Cursor MM1 Agent
===================================================

This script:
1. Queries Notion Agent-Tasks database for all tasks assigned to "Codex MM1 Agent"
2. Reassigns them to "Cursor MM1 Agent" (Auto)
3. Generates a summary report
"""

import os
import sys
import json
import logging
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
        logging.FileHandler('reassign_codex_mm1_tasks.log')
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
        get_notion_token, safe_get_property,
        AGENT_TASKS_DB_ID, CURSOR_MM1_AGENT_ID
    )
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)


def find_agent_id(notion_client: Client, agent_name: str) -> Optional[str]:
    """
    Find Notion page ID for an agent by name.
    Tries multiple name variations and search strategies.
    
    Args:
        notion_client: Notion client instance
        agent_name: Name of the agent to find
    
    Returns:
        Agent page ID or None if not found
    """
    # Try different name variations
    name_variations = [
        agent_name,
        agent_name.replace(" MM1", ""),
        agent_name.replace("Agent", "").strip(),
        "Codex",
        "codex"
    ]
    
    for name_variant in name_variations:
        try:
            # Search for pages with the agent name
            response = notion_client.search(
                query=name_variant,
                filter={"property": "object", "value": "page"},
                page_size=20
            )
            
            results = response.get("results", [])
            for page in results:
                # Check if this page has the agent name in its title
                title = safe_get_property(page, "Name", "title") or safe_get_property(page, "Agent Name", "title") or safe_get_property(page, "Title", "title")
                if title:
                    title_lower = title.lower()
                    # Check for codex and mm1 specifically (not mm2)
                    if "codex" in title_lower and "mm1" in title_lower and "mm2" not in title_lower:
                        agent_id = page.get("id")
                        logger.info(f"Found agent '{title}': {agent_id}")
                        return agent_id
            
        except Exception as e:
            logger.debug(f"Error searching for agent variant '{name_variant}': {e}")
            continue
    
    logger.warning(f"Could not find agent: {agent_name}")
    return None


def find_codex_agent_from_tasks(notion_client: Client) -> Optional[str]:
    """
    Find Codex MM1 Agent ID by querying tasks and checking their assigned agents.
    
    Args:
        notion_client: Notion client instance
    
    Returns:
        Codex MM1 Agent page ID or None if not found
    """
    try:
        logger.info("Querying all tasks to find Codex MM1 Agent assignments...")
        
        # Query all tasks (or a large sample)
        all_tasks = []
        has_more = True
        start_cursor = None
        
        while has_more and len(all_tasks) < 500:  # Limit to 500 tasks
            query_params = {
                "database_id": AGENT_TASKS_DB_ID,
                "page_size": 100
            }
            
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = notion_client.databases.query(**query_params)
            
            tasks = response.get("results", [])
            all_tasks.extend(tasks)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            logger.info(f"Checked {len(all_tasks)} tasks...")
        
        # Check each task's assigned agent
        codex_agent_ids = set()
        for task in all_tasks:
            assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
            
            for agent_relation in assigned_agent_relation:
                agent_id = agent_relation.get("id")
                try:
                    agent_page = notion_client.pages.retrieve(agent_id)
                    agent_name = safe_get_property(agent_page, "Name", "title") or safe_get_property(agent_page, "Agent Name", "title")
                    
                    if agent_name:
                        agent_name_lower = agent_name.lower()
                        if "codex" in agent_name_lower and ("mm1" in agent_name_lower or "agent" in agent_name_lower):
                            codex_agent_ids.add(agent_id)
                            logger.info(f"Found Codex MM1 Agent: {agent_name} ({agent_id})")
                except Exception as e:
                    logger.debug(f"Error retrieving agent page {agent_id}: {e}")
                    continue
        
        if codex_agent_ids:
            # Return the first one found
            agent_id = list(codex_agent_ids)[0]
            logger.info(f"Using Codex MM1 Agent ID: {agent_id}")
            return agent_id
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding Codex agent from tasks: {e}", exc_info=True)
        return None


def get_tasks_by_agent(notion_client: Client, agent_id: str) -> List[Dict]:
    """
    Query Agent-Tasks database for all tasks assigned to a specific agent.
    
    Args:
        notion_client: Notion client instance
        agent_id: Agent page ID to filter by
    
    Returns:
        List of task page objects
    """
    try:
        # Query for tasks assigned to this agent
        filter_params = {
            "property": "Assigned-Agent",
            "relation": {"contains": agent_id}
        }
        
        all_tasks = []
        has_more = True
        start_cursor = None
        
        while has_more:
            query_params = {
                "database_id": AGENT_TASKS_DB_ID,
                "filter": filter_params,
                "page_size": 100
            }
            
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = notion_client.databases.query(**query_params)
            
            tasks = response.get("results", [])
            all_tasks.extend(tasks)
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            logger.info(f"Retrieved {len(tasks)} tasks (total so far: {len(all_tasks)})")
        
        logger.info(f"Found {len(all_tasks)} total tasks assigned to agent")
        return all_tasks
        
    except Exception as e:
        logger.error(f"Error querying Agent-Tasks database: {e}", exc_info=True)
        return []


def reassign_task(notion_client: Client, task: Dict, new_agent_id: str) -> bool:
    """
    Reassign a task to a new agent.
    
    Args:
        notion_client: Notion client instance
        task: Task page object
        new_agent_id: New agent page ID
    
    Returns:
        True if successful, False otherwise
    """
    try:
        task_id = task.get("id")
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        
        # Update the Assigned-Agent relation
        update_properties = {
            "Assigned-Agent": {
                "relation": [{"id": new_agent_id}]
            }
        }
        
        notion_client.pages.update(
            page_id=task_id,
            properties=update_properties
        )
        
        logger.info(f"✅ Reassigned task '{task_title}' to Cursor MM1 Agent")
        return True
        
    except Exception as e:
        logger.error(f"Error reassigning task {task.get('id', 'unknown')}: {e}", exc_info=True)
        return False


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Reassign Codex MM1 Agent Tasks to Cursor MM1 Agent")
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
    
    # Find Codex MM1 Agent ID - try multiple approaches
    logger.info("Searching for Codex MM1 Agent...")
    codex_agent_id = find_agent_id(notion_client, "Codex MM1 Agent")
    
    # If not found via search, try finding from tasks
    if not codex_agent_id:
        logger.info("Agent not found via search, trying to find from task assignments...")
        codex_agent_id = find_codex_agent_from_tasks(notion_client)
    
    # If still not found, query all tasks and find ones with codex agents
    if not codex_agent_id:
        logger.info("Agent ID not found. Querying all tasks to find Codex MM1 Agent assignments...")
        tasks = []
        codex_agent_ids_found = set()
        
        # Query all tasks
        has_more = True
        start_cursor = None
        
        while has_more:
            query_params = {
                "database_id": AGENT_TASKS_DB_ID,
                "page_size": 100
            }
            
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = notion_client.databases.query(**query_params)
            batch_tasks = response.get("results", [])
            
            # Check each task for Codex MM1 Agent assignment
            for task in batch_tasks:
                assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
                
                for agent_relation in assigned_agent_relation:
                    agent_id = agent_relation.get("id")
                    try:
                        agent_page = notion_client.pages.retrieve(agent_id)
                        agent_name = safe_get_property(agent_page, "Name", "title") or safe_get_property(agent_page, "Agent Name", "title")
                        
                        if agent_name:
                            agent_name_lower = agent_name.lower()
                            # Look for codex and mm1 (not mm2)
                            if "codex" in agent_name_lower and "mm1" in agent_name_lower and "mm2" not in agent_name_lower:
                                codex_agent_ids_found.add(agent_id)
                                tasks.append(task)
                                logger.info(f"Found task assigned to Codex MM1 Agent: {agent_name} ({agent_id})")
                                break  # Found the agent for this task, move to next task
                    except Exception as e:
                        logger.debug(f"Error retrieving agent page {agent_id}: {e}")
                        continue
            
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")
            
            if len(tasks) > 0:
                logger.info(f"Found {len(tasks)} tasks so far...")
        
        if codex_agent_ids_found:
            codex_agent_id = list(codex_agent_ids_found)[0]
            logger.info(f"Using Codex MM1 Agent ID: {codex_agent_id}")
        else:
            logger.info("No tasks found assigned to Codex MM1 Agent.")
            return 0
    else:
        # Get all tasks assigned to Codex MM1 Agent using the found ID
        logger.info("Querying tasks assigned to Codex MM1 Agent...")
        tasks = get_tasks_by_agent(notion_client, codex_agent_id)
    
    if not tasks:
        logger.info("No tasks found assigned to Codex MM1 Agent.")
        return 0
    
    logger.info(f"Found {len(tasks)} tasks assigned to Codex MM1 Agent")
    
    # Reassign all tasks to Cursor MM1 Agent
    logger.info("Reassigning tasks to Cursor MM1 Agent...")
    reassigned = []
    failed = []
    
    for task in tasks:
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_id = task.get("id")
        task_url = task.get("url", "")
        task_status = safe_get_property(task, "Status", "status") or "Unknown"
        
        logger.info(f"Processing: {task_title} (Status: {task_status})")
        
        if reassign_task(notion_client, task, CURSOR_MM1_AGENT_ID):
            reassigned.append({
                "title": task_title,
                "id": task_id,
                "url": task_url,
                "status": task_status
            })
        else:
            failed.append({
                "title": task_title,
                "id": task_id,
                "url": task_url,
                "status": task_status
            })
    
    # Generate summary report
    logger.info("=" * 80)
    logger.info("REASSIGNMENT SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total tasks found: {len(tasks)}")
    logger.info(f"Successfully reassigned: {len(reassigned)}")
    logger.info(f"Failed to reassign: {len(failed)}")
    
    # Save detailed report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_agent": "Codex MM1 Agent",
        "target_agent": "Cursor MM1 Agent",
        "source_agent_id": codex_agent_id,
        "target_agent_id": CURSOR_MM1_AGENT_ID,
        "total_tasks": len(tasks),
        "reassigned": reassigned,
        "failed": failed
    }
    
    report_file = Path("codex_mm1_reassignment_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info(f"✅ Detailed report saved to: {report_file}")
    
    if failed:
        logger.warning(f"⚠️  {len(failed)} tasks could not be reassigned. Check the log for details.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


