#!/Users/brianhellemn/Projects/github-production/venv/bin/python3
"""
Notion Task Management and Agent Trigger System
==============================================

This script manages project tasks with a focus on continuing existing work:
1. **PRIORITY 1:** Scans local resources for unfinished work:
   - .cursor/plans/ directory for incomplete plans
   - Agent inbox folders (01_inbox) for pending trigger files
   - Analyzes existing work to understand what was started
2. **PRIORITY 2:** Reviews Notion databases if no unfinished work found:
   - Issues+Questions database for outstanding issues
   - Agent-Projects database for in-progress projects
   - Agent-Tasks database for ready tasks
3. Creates trigger files for MM1 and MM2 agents
4. Provides utilities for agents to mark trigger files as processed

**Workflow Philosophy:**
- Focus on continuing existing work rather than starting new work
- Use available tools (codebase_search, read_file, etc.) to analyze and assess
- Prioritize unfinished plans and pending trigger files
- Less reliance on scripts, more on tool-based analysis

Author: Cursor MM1 Agent

Agent Usage:
-----------
**CRITICAL:** The recipient agent MUST manually move trigger files. This cannot be automated.

When an agent receives a trigger file, it MUST:
1. Read the trigger file from 01_inbox
2. **MANUALLY** call mark_trigger_file_processed(trigger_file_path, success=True) to move it to 02_processed
3. Process the task
4. On error, **MANUALLY** call mark_trigger_file_processed(trigger_file_path, success=False) to move it to 03_failed

**The agent is responsible for moving the file - this is a manual step that cannot be automated.**

Example:
    from main import mark_trigger_file_processed, get_trigger_file_path
    from pathlib import Path
    
    # Find trigger file by task ID
    trigger_file = get_trigger_file_path(task_id="2dbe7361-6c27-81fb-9233-c9b808bc219a")
    
    # Agent MUST manually move to processed after reading/processing
    mark_trigger_file_processed(trigger_file, success=True)
    
    # Or manually move to failed on error
    mark_trigger_file_processed(trigger_file, success=False)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, continue without it

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('notion_task_manager.log')
    ]
)
logger = logging.getLogger(__name__)

# Try to import notion-client
try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    logger.warning("notion-client not available. Install with: pip install notion-client")
    NOTION_CLIENT_AVAILABLE = False

# Try to import task creation helpers for mandatory next handoff
try:
    import sys
    from pathlib import Path
    script_dir = Path(__file__).parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions
    TASK_CREATION_HELPERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Task creation helpers not available: {e}. Next handoff requirement may be missing!")
    TASK_CREATION_HELPERS_AVAILABLE = False

# Database IDs - Use environment variables or defaults from documentation
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")  # Issues+Questions (also used for issues)
PROJECTS_DB_ID = os.getenv("PROJECTS_DB_ID", "286e73616c2781ffa450db2ecad4b0ba")  # Projects
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")  # Agent-Tasks
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID", "229e73616c27808ebf06c202b10b5166")  # Issues+Questions

# Agent IDs
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent (for planning/review tasks)
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent (for implementation tasks)

# Agent Trigger Paths - Use folder_resolver for dynamic path resolution
try:
    from shared_core.notion.folder_resolver import (
        get_trigger_base_path,
        get_fallback_trigger_base_path,
        get_agent_inbox_path,
    )
    MM1_AGENT_TRIGGER_BASE = get_trigger_base_path()
    MM2_AGENT_TRIGGER_BASE = get_fallback_trigger_base_path()
    FOLDER_RESOLVER_AVAILABLE = True
except ImportError:
    # Fallback to hardcoded paths if folder_resolver not available
    _projects_trigger_base = Path("/Users/brianhellemn/Projects/Agents/Agent-Triggers")
    MM1_AGENT_TRIGGER_BASE = (
        _projects_trigger_base
        if _projects_trigger_base.exists()
        else Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
    )
    MM2_AGENT_TRIGGER_BASE = Path("/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd")
    FOLDER_RESOLVER_AVAILABLE = False
    def get_agent_inbox_path(agent_name: str) -> Path:
        """Fallback function when folder_resolver not available."""
        # Use normalize_agent_folder_name if available, otherwise simple replacement
        try:
            from shared_core.notion.folder_resolver import normalize_agent_folder_name
            folder_name = normalize_agent_folder_name(agent_name)
        except ImportError:
            folder_name = agent_name.replace(" ", "-").replace("/", "-")
        return MM1_AGENT_TRIGGER_BASE / folder_name / "01_inbox"

# ============================================================================
# UTILITY FUNCTIONS FOR SAFE NOTION PROPERTY ACCESS
# ============================================================================

def safe_get_property(page: Dict, property_name: str, property_type: str = None) -> Any:
    """
    Safely extract property value from Notion page.
    
    Args:
        page: Notion page object
        property_name: Name of the property
        property_type: Expected type (title, rich_text, status, select, relation, etc.)
    
    Returns:
        Extracted value or None if not found
    """
    try:
        properties = page.get("properties", {})
        if not properties:
            logger.debug(f"No properties found in page {page.get('id', 'unknown')}")
            return None
        
        prop = properties.get(property_name)
        if not prop:
            logger.debug(f"Property '{property_name}' not found in page {page.get('id', 'unknown')}")
            return None
        
        # If property_type is specified, verify it matches
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            logger.warning(
                f"Property '{property_name}' type mismatch: expected {property_type}, got {actual_type}"
            )
            return None
        
        # Extract value based on type
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list] if multi_select_list else []
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return relation_list  # Return list of relation objects
        
        elif actual_type == "date":
            date_obj = prop.get("date")
            if date_obj:
                return date_obj.get("start")
            return None
        
        elif actual_type == "url":
            return prop.get("url")
        
        elif actual_type == "number":
            return prop.get("number")
        
        elif actual_type == "checkbox":
            return prop.get("checkbox", False)
        
        elif actual_type == "multi_select":
            multi_select_list = prop.get("multi_select", [])
            return [item.get("name") for item in multi_select_list if item.get("name")]
        
        else:
            logger.debug(f"Unhandled property type: {actual_type} for property '{property_name}'")
            return prop  # Return raw property object
        
    except Exception as e:
        logger.error(f"Error extracting property '{property_name}': {e}", exc_info=True)
        return None


def get_notion_token() -> Optional[str]:
    """
    Get Notion API token using the CANONICAL shared token manager.

    This function now delegates to shared_core.notion.token_manager
    which provides centralized token management with multiple fallback sources.

    **Token Source Priority (via token_manager):**
    1. Environment variable: NOTION_TOKEN
    2. Environment variable: NOTION_API_TOKEN
    3. Environment variable: VV_AUTOMATIONS_WS_TOKEN
    4. Cache file: ~/.notion_token_cache
    5. Config file: ~/.config/notion_script_runner/config.json
    """
    # Use the canonical token manager from shared_core
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_token
        token = _get_token()
        if token:
            logger.debug("Found Notion token via shared_core.notion.token_manager")
            return token
    except ImportError as e:
        logger.debug(f"shared_core.notion.token_manager import failed: {e}")

    # Fallback to direct environment check if token_manager not available
    token = (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    if token:
        logger.debug("Found Notion token in environment (fallback)")
        return token

    # Legacy fallback to unified_config
    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        if token:
            logger.debug("Found Notion token via unified_config (legacy fallback)")
            return token
    except Exception as e:
        logger.debug(f"unified_config import failed: {e}")

    return None


# ============================================================================
# NOTION CLIENT WRAPPER
# ============================================================================

class NotionManager:
    """Enhanced Notion client with error handling and logging"""
    
    def __init__(self, token: str):
        if not NOTION_CLIENT_AVAILABLE:
            raise ImportError("notion-client library not available")
        self.client = Client(auth=token)
        logger.info("Notion client initialized")
    
    def get_data_source_id(self, database_id: str) -> Optional[str]:
        """
        Get the data source ID for a database (required for API 2025-09-03+).

        As of Notion API version 2025-09-03, databases and data_sources are separate.
        A database can have multiple data sources. This returns the first one.
        """
        try:
            db = self.client.databases.retrieve(database_id=database_id)
            data_sources = db.get("data_sources", [])
            if data_sources:
                return data_sources[0].get("id")
            return None
        except Exception as e:
            logger.error(f"Error retrieving database {database_id}: {e}")
            return None

    def query_database(
        self,
        database_id: str,
        filter_params: Dict = None,
        sorts: List[Dict] = None
    ) -> List[Dict]:
        """
        Query Notion database with error handling.

        Uses data_sources.query() API which is required for Notion API version 2025-09-03+.
        Falls back to databases.query() for older API versions.
        """
        try:
            # First, get the data source ID for this database
            data_source_id = self.get_data_source_id(database_id)

            if data_source_id:
                # Use new data_sources.query API (Notion API 2025-09-03+)
                query_params = {"data_source_id": data_source_id}

                if filter_params:
                    query_params["filter"] = filter_params
                    logger.debug(f"Querying data_source {data_source_id} with filter: {filter_params}")

                if sorts:
                    query_params["sorts"] = sorts
                    logger.debug(f"Querying data_source {data_source_id} with sorts: {sorts}")

                response = self.client.data_sources.query(**query_params)
                results = response.get("results", [])
                logger.info(f"Retrieved {len(results)} pages from data_source {data_source_id}")
                return results
            else:
                # Fallback: try legacy databases.query (older API versions)
                logger.warning(f"No data_source found for database {database_id}, trying legacy API")
                query_params = {"database_id": database_id}

                if filter_params:
                    query_params["filter"] = filter_params

                if sorts:
                    query_params["sorts"] = sorts

                response = self.client.databases.query(**query_params)
                results = response.get("results", [])
                logger.info(f"Retrieved {len(results)} pages from database {database_id}")
                return results

        except Exception as e:
            logger.error(f"Error querying database {database_id}: {e}", exc_info=True)
            return []
    
    def create_page(self, parent_database_id: str, properties: Dict) -> Optional[Dict]:
        """Create a new page in Notion database"""
        try:
            response = self.client.pages.create(
                parent={"database_id": parent_database_id},
                properties=properties
            )
            page_id = response.get("id")
            logger.info(f"Created page {page_id} in database {parent_database_id}")
            return response
        except Exception as e:
            logger.error(f"Error creating page in database {parent_database_id}: {e}", exc_info=True)
            return None
    
    def update_page(self, page_id: str, properties: Dict) -> bool:
        """Update Notion page with error handling"""
        try:
            self.client.pages.update(page_id=page_id, properties=properties)
            logger.info(f"Updated page {page_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {e}", exc_info=True)
            return False
    
    def get_page_title(self, page_id: str) -> Optional[str]:
        """Get title/name of a Notion page"""
        try:
            page = self.client.pages.retrieve(page_id=page_id)
            # Try common title property names
            properties = page.get("properties", {})
            for prop_name in ["Name", "Title", "Task Name", "Agent Name"]:
                prop = properties.get(prop_name)
                if prop:
                    if prop.get("type") == "title":
                        title_list = prop.get("title", [])
                        if title_list:
                            return title_list[0].get("plain_text", "")
            # Fallback: try to get from page object itself
            if "title" in page:
                return page["title"]
            return None
        except Exception as e:
            logger.debug(f"Error retrieving page {page_id} title: {e}")
            return None


# ============================================================================
# RESEARCH MODE DETECTION
# ============================================================================

def detect_research_mode() -> Optional[str]:
    """
    Detect whether Research mode is ON for the current conversation/context.
    
    Detection priority:
    1. Environment variable: NOTION_RESEARCH_MODE (values: "ON", "True", "1", "Research")
    2. Environment variable: RESEARCH_MODE (values: "ON", "True", "1", "Research")
    3. Context detection: Check if conversation context suggests Research mode
    4. Default: None (unknown/not detected)
    
    Returns:
        "Research" if Research mode detected, "Data Operations" if explicitly Data Ops,
        None if cannot be determined
    """
    # Priority 1: Check NOTION_RESEARCH_MODE environment variable
    research_mode_env = os.getenv("NOTION_RESEARCH_MODE", "").strip().upper()
    if research_mode_env in ["ON", "TRUE", "1", "RESEARCH", "YES"]:
        logger.debug("Research mode detected via NOTION_RESEARCH_MODE environment variable")
        return "Research"
    elif research_mode_env in ["OFF", "FALSE", "0", "DATA", "DATA OPERATIONS", "DATA OPS", "NO"]:
        logger.debug("Data Operations mode detected via NOTION_RESEARCH_MODE environment variable")
        return "Data Operations"
    
    # Priority 2: Check RESEARCH_MODE environment variable
    research_mode_env_alt = os.getenv("RESEARCH_MODE", "").strip().upper()
    if research_mode_env_alt in ["ON", "TRUE", "1", "RESEARCH", "YES"]:
        logger.debug("Research mode detected via RESEARCH_MODE environment variable")
        return "Research"
    elif research_mode_env_alt in ["OFF", "FALSE", "0", "DATA", "DATA OPERATIONS", "DATA OPS", "NO"]:
        logger.debug("Data Operations mode detected via RESEARCH_MODE environment variable")
        return "Data Operations"
    
    # Priority 3: Context detection (could be enhanced with conversation analysis)
    # For now, default to None if not explicitly set
    logger.debug("Research mode not explicitly detected, returning None")
    return None


# ============================================================================
# TRIGGER FILE CREATION
# ============================================================================

def determine_agent_type(agent_name: str, agent_id: str = None) -> str:
    """
    Determine if agent is MM1 or MM2 based on name or ID.
    Defaults to MM1 if cannot be determined.
    """
    agent_name_lower = agent_name.lower()
    
    # MM2 agents typically have "MM2" in name or are in Google Drive
    mm2_indicators = ["mm2", "mm-2", "google drive", "gd"]
    if any(indicator in agent_name_lower for indicator in mm2_indicators):
        return "MM2"
    
    # Default to MM1
    return "MM1"


def normalize_agent_folder_name(agent_name: str, agent_id: str = None) -> str:
    """
    Normalize agent name to consistent folder name format.
    
    Removes common suffixes (-Trigger, -Agent-Trigger, -Agent), standardizes format,
    and maps known agent IDs to canonical names.
    
    Args:
        agent_name: Raw agent name from Notion or other source
        agent_id: Optional agent ID for mapping to canonical name
    
    Returns:
        Normalized folder name (e.g., "Claude-MM1-Agent")
    """
    import re
    
    # Map known agent IDs to canonical names
    AGENT_ID_TO_CANONICAL_NAME = {
        "fa54f05c-e184-403a-ac28-87dd8ce9855b": "Claude-MM1-Agent",
        "249e7361-6c27-8100-8a74-de7eabb9fc8d": "Cursor-MM1-Agent",
    }
    
    # If we have an agent ID and it's in our mapping, use canonical name
    if agent_id and agent_id in AGENT_ID_TO_CANONICAL_NAME:
        return AGENT_ID_TO_CANONICAL_NAME[agent_id]
    
    # Start with the agent name
    normalized = agent_name.strip()
    
    # Replace spaces and slashes with hyphens
    normalized = normalized.replace(" ", "-").replace("/", "-")
    
    # Remove trailing "-gd" suffix (for MM2 agents, will be re-added later if needed)
    normalized = re.sub(r'-gd$', '', normalized, flags=re.IGNORECASE)
    
    # Remove common suffixes (in order of specificity)
    # Remove "-Agent-Agent-Trigger" (duplicate word)
    normalized = re.sub(r'-Agent-Agent-Trigger$', '', normalized, flags=re.IGNORECASE)
    # Remove "-Agent-Trigger"
    normalized = re.sub(r'-Agent-Trigger$', '', normalized, flags=re.IGNORECASE)
    # Remove "-Trigger"
    normalized = re.sub(r'-Trigger$', '', normalized, flags=re.IGNORECASE)
    
    # Normalize inconsistent hyphenation BEFORE removing -Agent suffix
    # Fix "ChatGPT" vs "Chat-GPT" -> "ChatGPT" (do this early, before splitting)
    normalized = re.sub(r'Chat-GPT', 'ChatGPT', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'ChatGPT', 'ChatGPT', normalized)  # Ensure consistent
    # Fix "CursorMM1" -> "Cursor-MM1" (add hyphen before capital letters)
    normalized = re.sub(r'([a-z])([A-Z])', r'\1-\2', normalized)
    
    # Remove duplicate hyphens
    normalized = re.sub(r'-+', '-', normalized)
    
    # Remove leading/trailing hyphens
    normalized = normalized.strip('-')
    
    # Determine if we should keep or add "-Agent" suffix
    # Known agent base names that should have "-Agent" suffix
    agent_bases_requiring_suffix = [
        'claude', 'cursor', 'codex', 'chatgpt', 'notion-ai'
    ]
    
    # Check if name contains an agent base
    normalized_lower = normalized.lower()
    has_agent_base = any(base in normalized_lower for base in agent_bases_requiring_suffix)
    has_agent_suffix = normalized_lower.endswith('-agent')
    
    # If it has an agent base but no "-Agent" suffix, add it
    # Exception: Don't add if it's just "Claude-MM2" or "Claude-MM1" (those are valid without -Agent)
    # But "Claude-MM1-Agent" should stay, and "Claude-MM1" should become "Claude-MM1-Agent"
    if has_agent_base and not has_agent_suffix:
        # Check if it ends with just MM1 or MM2 (without -Agent)
        if not re.search(r'-(MM1|MM2)$', normalized, flags=re.IGNORECASE):
            # It's a more complex name, add -Agent
            normalized = f"{normalized}-Agent"
        else:
            # It's just "Claude-MM1" or similar, add -Agent
            normalized = f"{normalized}-Agent"
    
    # Capitalize first letter of each word (Title Case)
    parts = normalized.split('-')
    normalized = '-'.join(part.capitalize() for part in parts)
    
    # Special case: Fix "Chatgpt" or "Chat-Gpt" -> "ChatGPT" (after capitalization)
    normalized = re.sub(r'Chat[Gg]pt', 'ChatGPT', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'Chat-Gpt', 'ChatGPT', normalized, flags=re.IGNORECASE)
    # Fix "Mm1" -> "MM1", "Mm2" -> "MM2" (after capitalization)
    normalized = re.sub(r'-Mm([12])', r'-MM\1', normalized)
    normalized = re.sub(r'^Mm([12])', r'MM\1', normalized)
    # Fix "Ai" -> "AI" (for Notion-AI)
    normalized = re.sub(r'-Ai-', r'-AI-', normalized)
    normalized = re.sub(r'^Ai-', r'AI-', normalized)
    
    return normalized


def create_trigger_file(
    agent_type: str,
    agent_name: str,
    task_details: Dict[str, Any]
) -> Optional[Path]:
    """
    Create trigger file for agent.
    
    Args:
        agent_type: "MM1" or "MM2"
        agent_name: Name of the agent
        task_details: Dictionary containing task information
    
    Returns:
        Path to created trigger file or None if failed
    """
    try:
        # Determine base path
        if agent_type == "MM1":
            base_path = MM1_AGENT_TRIGGER_BASE
        else:
            base_path = MM2_AGENT_TRIGGER_BASE
        
        # Create agent folder name (normalize agent name)
        agent_id = task_details.get("agent_id")  # Get agent_id if available in task_details
        agent_folder = normalize_agent_folder_name(agent_name, agent_id)
        if agent_type == "MM2":
            agent_folder = f"{agent_folder}-gd"
        
        trigger_folder = base_path / agent_folder / "01_inbox"
        trigger_folder.mkdir(parents=True, exist_ok=True)
        
        # CRITICAL: Check for existing trigger file to prevent duplicates
        task_id = task_details.get("task_id", "unknown")
        def _norm_id(value: str) -> str:
            return (value or "").replace("-", "").lower()

        normalized_task_id = _norm_id(task_id) if task_id != "unknown" else ""
        token8 = normalized_task_id[:8] if normalized_task_id else ""
        token16 = (
            f"{normalized_task_id[:8]}{normalized_task_id[-8:]}"
            if len(normalized_task_id) >= 16
            else normalized_task_id
        )

        if normalized_task_id:
            # Check for existing trigger files with this task ID (in inbox, processed, or failed).
            # Use filename patterns to narrow candidates, then validate by reading JSON to avoid
            # collisions (many Notion IDs share the same leading prefix).
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
                        candidate_task_id = _norm_id(data.get("task_id") or "")
                        if candidate_task_id and candidate_task_id == normalized_task_id:
                            logger.warning(
                                f"Trigger file already exists for task {token16} in {subfolder}: {candidate.name}. "
                                f"Skipping duplicate creation."
                            )
                            return candidate  # Return existing file instead of creating duplicate
                    except Exception:
                        continue
        
        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_id_short = token16 if normalized_task_id else "unknown"
        task_title = task_details.get("task_title", "Task")
        safe_title = task_title.replace(" ", "-").replace("/", "-")[:50]
        filename = f"{timestamp}__HANDOFF__{safe_title}__{task_id_short}.json"
        
        trigger_file = trigger_folder / filename
        
        # Build trigger file content
        trigger_content = {
            "task_id": task_details.get("task_id"),
            "task_title": task_details.get("task_title"),
            "task_url": task_details.get("task_url", ""),
            "project_id": task_details.get("project_id"),
            "project_title": task_details.get("project_title"),
            "description": task_details.get("description", ""),
            "status": task_details.get("status"),
            "agent_name": agent_name,
            "agent_type": agent_type,
            "handoff_instructions": task_details.get("handoff_instructions", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "priority": task_details.get("priority", "High")
        }
        
        # Write trigger file
        with open(trigger_file, "w", encoding="utf-8") as f:
            json.dump(trigger_content, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Created trigger file: {trigger_file}")
        return trigger_file
        
    except Exception as e:
        logger.error(f"Error creating trigger file for {agent_name}: {e}", exc_info=True)
        return None


def mark_trigger_file_processed(
    trigger_file_path: Path,
    success: bool = True,
    agent_name: str = None,
    agent_type: str = None
) -> Optional[Path]:
    """
    Move trigger file from 01_inbox to 02_processed (success) or 03_failed (failure).
    
    **IMPORTANT:** This function MUST be called manually by the recipient agent.
    The agent receiving the trigger file is responsible for moving it after reading/processing.
    This cannot be automated - only the agent knows when processing is complete and whether it succeeded.
    
    **Agent Workflow:**
    1. Agent reads trigger file from 01_inbox
    2. Agent calls this function to move file to 02_processed (before or after processing)
    3. If processing fails, agent calls this function with success=False to move to 03_failed
    
    Args:
        trigger_file_path: Path to the trigger file (can be in 01_inbox or absolute path)
        success: True to move to 02_processed, False to move to 03_failed
        agent_name: Optional agent name for logging (if not provided, inferred from path)
        agent_type: Optional agent type "MM1" or "MM2" (if not provided, inferred from path)
    
    Returns:
        Path to the moved file, or None if failed
    
    Example:
        from main import mark_trigger_file_processed
        from pathlib import Path
        
        # After reading trigger file
        trigger_file = Path("/path/to/01_inbox/trigger.json")
        
        # Move to processed (agent must do this manually)
        mark_trigger_file_processed(trigger_file, success=True)
    """
    try:
        trigger_file_path = Path(trigger_file_path)
        
        # If file doesn't exist, try to find it
        if not trigger_file_path.exists():
            # Try to find by filename in inbox folders
            filename = trigger_file_path.name
            for base_path in [MM1_AGENT_TRIGGER_BASE, MM2_AGENT_TRIGGER_BASE]:
                for agent_folder in base_path.iterdir():
                    if agent_folder.is_dir() and not agent_folder.name.startswith("_"):
                        inbox_path = agent_folder / "01_inbox" / filename
                        if inbox_path.exists():
                            trigger_file_path = inbox_path
                            break
                    if trigger_file_path.exists():
                        break
                if trigger_file_path.exists():
                    break
        
        if not trigger_file_path.exists():
            logger.warning(f"Trigger file not found: {trigger_file_path}")
            return None
        
        # Determine agent folder and type from path
        agent_folder_path = trigger_file_path.parent.parent
        agent_folder_name = agent_folder_path.name
        
        # Determine base path and agent type
        if str(MM1_AGENT_TRIGGER_BASE) in str(agent_folder_path):
            base_path = MM1_AGENT_TRIGGER_BASE
            inferred_agent_type = "MM1"
        elif str(MM2_AGENT_TRIGGER_BASE) in str(agent_folder_path):
            base_path = MM2_AGENT_TRIGGER_BASE
            inferred_agent_type = "MM2"
        else:
            logger.error(f"Could not determine base path for trigger file: {trigger_file_path}")
            return None
        
        # Use provided agent_type or inferred
        final_agent_type = agent_type or inferred_agent_type
        
        # Determine destination folder
        if success:
            dest_folder = agent_folder_path / "02_processed"
            action = "processed"
        else:
            dest_folder = agent_folder_path / "03_failed"
            action = "failed"
        
        # Create destination folder if it doesn't exist
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        # Move file
        dest_file = dest_folder / trigger_file_path.name
        
        # If destination file exists, add timestamp to avoid overwrite
        if dest_file.exists():
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            name_parts = dest_file.stem.rsplit("__", 1)
            if len(name_parts) == 2:
                new_name = f"{name_parts[0]}__{timestamp}__{name_parts[1]}{dest_file.suffix}"
            else:
                new_name = f"{dest_file.stem}__{timestamp}{dest_file.suffix}"
            dest_file = dest_folder / new_name
        
        # Move the file
        trigger_file_path.rename(dest_file)
        
        logger.info(f"Moved trigger file to {action} folder: {dest_file}")
        return dest_file
        
    except Exception as e:
        logger.error(f"Error moving trigger file {trigger_file_path}: {e}", exc_info=True)
        return None


def get_trigger_file_path(
    task_id: str,
    agent_name: str = None,
    agent_type: str = None,
    agent_id: str = None
) -> Optional[Path]:
    """
    Find trigger file path for a given task ID.
    
    Searches in 01_inbox folders for trigger files matching the task ID.
    
    Args:
        task_id: Task ID to search for
        agent_name: Optional agent name to narrow search
        agent_type: Optional agent type "MM1" or "MM2" to narrow search
        agent_id: Optional agent ID for normalization
    
    Returns:
        Path to trigger file if found, None otherwise
    """
    try:
        task_id_short = task_id.replace("-", "")[:8]
        
        # Determine which base paths to search
        if agent_type == "MM1":
            base_paths = [MM1_AGENT_TRIGGER_BASE]
        elif agent_type == "MM2":
            base_paths = [MM2_AGENT_TRIGGER_BASE]
        else:
            base_paths = [MM1_AGENT_TRIGGER_BASE, MM2_AGENT_TRIGGER_BASE]
        
        # Search for trigger file
        for base_path in base_paths:
            if not base_path.exists():
                continue
                
            for agent_folder in base_path.iterdir():
                if not agent_folder.is_dir() or agent_folder.name.startswith("_"):
                    continue
                
                # If agent_name provided, check if folder matches
                if agent_name:
                    normalized_folder = normalize_agent_folder_name(agent_name, agent_id)
                    if agent_type == "MM2":
                        normalized_folder = f"{normalized_folder}-gd"
                    if agent_folder.name != normalized_folder:
                        continue
                
                # Search in inbox
                inbox_path = agent_folder / "01_inbox"
                if inbox_path.exists():
                    for trigger_file in inbox_path.glob(f"*{task_id_short}*.json"):
                        return trigger_file
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding trigger file for task {task_id}: {e}", exc_info=True)
        return None


# ============================================================================
# LOCAL RESOURCE ANALYSIS (Plans, Handoff Files, Unfinished Work)
# ============================================================================

def scan_cursor_plans_directory() -> List[Dict[str, Any]]:
    """
    Scan .cursor/plans directory for unfinished plans.
    
    Analyzes plan files to identify:
    - Plans with incomplete todos
    - Recent plans that may need continuation
    - Plans related to critical issues
    
    Returns:
        List of plan analysis dictionaries with metadata
    """
    plans_dir = Path.home() / ".cursor" / "plans"
    if not plans_dir.exists():
        logger.warning(f"Plans directory not found: {plans_dir}")
        return []
    
    unfinished_plans = []
    
    try:
        for plan_file in plans_dir.glob("*.plan.md"):
            try:
                content = plan_file.read_text(encoding="utf-8")
                
                # Parse plan metadata
                plan_info = {
                    "file_path": str(plan_file),
                    "file_name": plan_file.name,
                    "modified_time": datetime.fromtimestamp(plan_file.stat().st_mtime, tz=timezone.utc),
                    "has_incomplete_todos": False,
                    "todo_count": 0,
                    "completed_todo_count": 0,
                    "related_issue": None,
                    "related_project": None,
                }
                
                # Check for incomplete todos
                if "status: completed" in content.lower() or "status: in_progress" in content.lower() or "status: pending" in content.lower():
                    # Count todos
                    import re
                    todo_matches = re.findall(r'status:\s*(completed|in_progress|pending|cancelled)', content, re.IGNORECASE)
                    plan_info["todo_count"] = len(todo_matches)
                    completed = len([m for m in todo_matches if m.lower() == "completed"])
                    plan_info["completed_todo_count"] = completed
                    plan_info["has_incomplete_todos"] = completed < len(todo_matches)
                
                # Extract issue/project references
                if "issue" in content.lower() or "critical" in content.lower():
                    # Try to extract issue IDs or titles
                    issue_refs = re.findall(r'issue[_\s]+id[:\s]+([a-f0-9-]+)', content, re.IGNORECASE)
                    if issue_refs:
                        plan_info["related_issue"] = issue_refs[0]
                
                # Only include plans with incomplete work
                if plan_info["has_incomplete_todos"]:
                    unfinished_plans.append(plan_info)
                    
            except Exception as e:
                logger.debug(f"Error reading plan file {plan_file}: {e}")
                continue
        
        # Sort by modification time (most recent first)
        unfinished_plans.sort(key=lambda x: x["modified_time"], reverse=True)
        
        logger.info(f"Found {len(unfinished_plans)} unfinished plans in .cursor/plans/")
        
    except Exception as e:
        logger.error(f"Error scanning plans directory: {e}", exc_info=True)
    
    return unfinished_plans


def scan_agent_inbox_folders() -> List[Dict[str, Any]]:
    """
    Scan agent inbox folders for unprocessed trigger files.
    
    Checks 01_inbox folders in both MM1 and MM2 agent trigger directories
    to find pending work that needs attention.
    
    Returns:
        List of trigger file analysis dictionaries
    """
    pending_triggers = []
    
    for base_path in [MM1_AGENT_TRIGGER_BASE, MM2_AGENT_TRIGGER_BASE]:
        if not base_path.exists():
            continue
        
        agent_type = "MM1" if base_path == MM1_AGENT_TRIGGER_BASE else "MM2"
        
        try:
            # Scan all agent folders
            for agent_folder in base_path.iterdir():
                if not agent_folder.is_dir() or agent_folder.name.startswith("_"):
                    continue
                
                inbox_path = agent_folder / "01_inbox"
                if not inbox_path.exists():
                    continue
                
                # Find all trigger files in inbox
                for trigger_file in inbox_path.glob("*.json"):
                    try:
                        trigger_data = json.loads(trigger_file.read_text(encoding="utf-8"))
                        
                        trigger_info = {
                            "file_path": str(trigger_file),
                            "file_name": trigger_file.name,
                            "agent_folder": agent_folder.name,
                            "agent_type": agent_type,
                            "task_id": trigger_data.get("task_id"),
                            "task_title": trigger_data.get("task_title", ""),
                            "issue_id": trigger_data.get("issue_id"),
                            "issue_title": trigger_data.get("issue_title", ""),
                            "project_id": trigger_data.get("project_id"),
                            "project_title": trigger_data.get("project_title", ""),
                            "priority": trigger_data.get("priority", "Medium"),
                            "status": trigger_data.get("status", "Unknown"),
                            "created_at": trigger_data.get("created_at"),
                            "modified_time": datetime.fromtimestamp(trigger_file.stat().st_mtime, tz=timezone.utc),
                        }
                        
                        pending_triggers.append(trigger_info)
                        
                    except Exception as e:
                        logger.debug(f"Error reading trigger file {trigger_file}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error scanning inbox folders in {base_path}: {e}", exc_info=True)
    
    # Sort by priority and modification time
    priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    pending_triggers.sort(key=lambda x: (
        priority_map.get(x.get("priority", "Medium"), 99),
        -x["modified_time"].timestamp() if x.get("modified_time") else 0
    ))
    
    logger.info(f"Found {len(pending_triggers)} pending trigger files in agent inboxes")
    
    return pending_triggers


def analyze_unfinished_work(
    notion: NotionManager,
    unfinished_plans: List[Dict[str, Any]],
    pending_triggers: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Analyze unfinished work from plans, trigger files, and Notion to identify what to continue.
    
    Uses available tools to assess:
    - What work was previously started
    - What remains to be done
    - Dependencies and blockers
    - Priority and impact
    
    Returns:
        Dictionary with work item to continue, or None if nothing found
    """
    logger.info("=" * 80)
    logger.info("Analyzing Unfinished Work from Local Resources")
    logger.info("=" * 80)
    
    # Priority order: Critical triggers > Unfinished plans > Other triggers
    
    # 1. Check for critical pending triggers first
    critical_triggers = [t for t in pending_triggers if t.get("priority") == "Critical"]
    if critical_triggers:
        trigger = critical_triggers[0]
        logger.info(f"Found critical pending trigger: {trigger.get('task_title', 'Unknown')}")
        logger.info(f"  File: {trigger.get('file_name')}")
        logger.info(f"  Agent: {trigger.get('agent_folder')}")
        logger.info(f"  Issue: {trigger.get('issue_title', 'N/A')}")
        
        return {
            "type": "trigger_file",
            "source": "inbox",
            "data": trigger,
            "action": "continue_trigger_work",
            "priority": "Critical"
        }
    
    # 2. Check for unfinished plans with incomplete todos
    if unfinished_plans:
        # Prioritize plans related to issues
        issue_plans = [p for p in unfinished_plans if p.get("related_issue")]
        if issue_plans:
            plan = issue_plans[0]
        else:
            plan = unfinished_plans[0]
        
        logger.info(f"Found unfinished plan: {plan.get('file_name')}")
        logger.info(f"  Incomplete todos: {plan.get('todo_count', 0) - plan.get('completed_todo_count', 0)}")
        logger.info(f"  Related issue: {plan.get('related_issue', 'N/A')}")
        
        return {
            "type": "plan",
            "source": "cursor_plans",
            "data": plan,
            "action": "continue_plan_work",
            "priority": "High" if plan.get("related_issue") else "Medium"
        }
    
    # 3. Check for other pending triggers
    if pending_triggers:
        trigger = pending_triggers[0]
        logger.info(f"Found pending trigger: {trigger.get('task_title', 'Unknown')}")
        logger.info(f"  Priority: {trigger.get('priority', 'Unknown')}")
        
        return {
            "type": "trigger_file",
            "source": "inbox",
            "data": trigger,
            "action": "continue_trigger_work",
            "priority": trigger.get("priority", "Medium")
        }
    
    logger.info("No unfinished work found in local resources")
    return None


def continue_unfinished_work(work_item: Dict[str, Any], notion: NotionManager) -> bool:
    """
    Continue work on an unfinished item identified by analyze_unfinished_work.
    
    Uses available tools (codebase_search, read_file, etc.) to:
    - Understand the current state
    - Assess what needs to be done
    - Identify next steps
    - Create appropriate handoffs
    
    Args:
        work_item: Work item dictionary from analyze_unfinished_work
        notion: NotionManager instance
        
    Returns:
        True if work was continued, False otherwise
    """
    work_type = work_item.get("type")
    work_data = work_item.get("data", {})
    
    logger.info("=" * 80)
    logger.info(f"Continuing {work_type}: {work_data.get('file_name', 'Unknown')}")
    logger.info("=" * 80)
    
    if work_type == "trigger_file":
        # Analyze trigger file to understand work context
        trigger_path = work_data.get("file_path")
        task_id = work_data.get("task_id")
        issue_id = work_data.get("issue_id")
        project_id = work_data.get("project_id")
        
        logger.info(f"Analyzing trigger file: {trigger_path}")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Issue ID: {issue_id}")
        logger.info(f"Project ID: {project_id}")
        
        # Read trigger file for full context
        try:
            trigger_content = json.loads(Path(trigger_path).read_text(encoding="utf-8"))
            description = trigger_content.get("description", "")
            handoff_instructions = trigger_content.get("handoff_instructions", "")
            
            logger.info("Trigger file context:")
            logger.info(f"  Title: {trigger_content.get('task_title', 'Unknown')}")
            logger.info(f"  Status: {trigger_content.get('status', 'Unknown')}")
            logger.info(f"  Description length: {len(description)} chars")
            
            # Check if related issue/project exists in Notion
            if issue_id:
                try:
                    issue_page = notion.client.pages.retrieve(page_id=issue_id)
                    issue_status = safe_get_property(issue_page, "Status", "status")
                    logger.info(f"  Related issue status: {issue_status}")
                except Exception as e:
                    logger.debug(f"Could not retrieve issue {issue_id}: {e}")
            
            if project_id:
                try:
                    project_page = notion.client.pages.retrieve(page_id=project_id)
                    project_status = safe_get_property(project_page, "Status", "status")
                    logger.info(f"  Related project status: {project_status}")
                except Exception as e:
                    logger.debug(f"Could not retrieve project {project_id}: {e}")
            
            # The trigger file is ready for the agent to process
            # We've analyzed it and logged the context
            logger.info("Trigger file analysis complete - ready for agent processing")
            return True
            
        except Exception as e:
            logger.error(f"Error analyzing trigger file: {e}", exc_info=True)
            return False
    
    elif work_type == "plan":
        # Analyze plan file to understand what needs to be done
        plan_path = work_data.get("file_path")
        
        logger.info(f"Analyzing plan file: {plan_path}")
        
        try:
            plan_content = Path(plan_path).read_text(encoding="utf-8")
            
            # Extract incomplete todos
            import re
            todo_pattern = r'- id: (\w+)\s+content: ([^\n]+)\s+status: (completed|in_progress|pending|cancelled)'
            todos = re.findall(todo_pattern, plan_content, re.MULTILINE)
            
            incomplete_todos = [t for t in todos if t[2] not in ["completed", "cancelled"]]
            
            logger.info(f"Plan analysis:")
            logger.info(f"  Total todos: {len(todos)}")
            logger.info(f"  Incomplete todos: {len(incomplete_todos)}")
            
            for todo_id, todo_content, status in incomplete_todos[:5]:  # Show first 5
                logger.info(f"    - [{status}] {todo_content[:60]}...")
            
            # Check if plan is related to an issue
            issue_id = work_data.get("related_issue")
            if issue_id:
                logger.info(f"  Related to issue: {issue_id}")
                # Could create a handoff task here if needed
            
            logger.info("Plan analysis complete - ready for continuation")
            return True
            
        except Exception as e:
            logger.error(f"Error analyzing plan file: {e}", exc_info=True)
            return False
    
    return False


# ============================================================================
# CLIENT-FACING EXCLUSION FILTERS
# ============================================================================

def build_client_facing_exclusion_filter(base_filter: Dict = None) -> Dict:
    """
    Build a filter that excludes client-facing items unless tagged with 'Client-support-tasks'.
    
    For Issues: Exclude Type contains "Client-Facing Issue" UNLESS Tags contains "Client-support-tasks"
    For Projects/Tasks: Exclude client-facing items UNLESS Tags contains "Client-support-tasks"
    
    Args:
        base_filter: Base filter to combine with client-facing exclusion
        
    Returns:
        Combined filter with client-facing exclusion logic
    """
    client_exclusion = {
        "or": [
            # Include non-client-facing items (Type does NOT contain "Client-Facing Issue")
            {
                "property": "Type",
                "multi_select": {"does_not_contain": "Client-Facing Issue"}
            },
            # OR include client-facing items that ARE tagged with Client-support-tasks
            {
                "and": [
                    {
                        "property": "Type",
                        "multi_select": {"contains": "Client-Facing Issue"}
                    },
                    {
                        "property": "Tags",
                        "multi_select": {"contains": "Client-support-tasks"}
                    }
                ]
            }
        ]
    }
    
    # If base_filter exists, combine with AND
    if base_filter:
        return {
            "and": [
                base_filter,
                client_exclusion
            ]
        }
    else:
        return client_exclusion


def filter_client_facing_items(items: List[Dict], item_type: str = "issue") -> List[Dict]:
    """
    Filter out client-facing items unless they have 'Client-support-tasks' tag.
    
    This is a post-query filter for cases where Notion filter API doesn't support the logic.
    
    Args:
        items: List of Notion page objects
        item_type: Type of item ("issue", "project", "task")
        
    Returns:
        Filtered list excluding client-facing items without Client-support-tasks tag
    """
    filtered = []
    for item in items:
        # Get Type property (multi_select for issues, may vary for others)
        item_types = safe_get_property(item, "Type", "multi_select") or []
        if not isinstance(item_types, list):
            item_types = [item_types] if item_types else []
        
        # Get Tags property
        tags = safe_get_property(item, "Tags", "multi_select") or []
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        
        # Check if it's client-facing
        is_client_facing = "Client-Facing Issue" in item_types or any(
            "client-facing" in str(tag).lower() for tag in item_types
        )
        
        # Include if:
        # 1. Not client-facing, OR
        # 2. Client-facing but has Client-support-tasks tag
        has_client_support_tag = "Client-support-tasks" in tags or any(
            "client-support" in str(tag).lower() for tag in tags
        )
        
        if not is_client_facing or has_client_support_tag:
            filtered.append(item)
        else:
            logger.debug(f"Excluding client-facing {item_type} (ID: {item.get('id')}) without Client-support-tasks tag")
    
    return filtered


# ============================================================================
# ISSUE HANDLING
# ============================================================================

def handle_issues(notion: NotionManager) -> bool:
    """
    Check for outstanding issues and create handoff tasks.
    
    Returns:
        True if issues were found and handled, False otherwise
    """
    logger.info("Checking for outstanding issues...")
    
    # Filter for outstanding issues - try multiple status values
    # Issues+Questions database uses Status property with values like "Unreported", "Open", "In Progress", etc.
    # Try to find issues that are not resolved
    status_filter = {
        "or": [
            {
                "property": "Status",
                "status": {"equals": "Unreported"}
            },
            {
                "property": "Status",
                "status": {"equals": "Open"}
            },
            {
                "property": "Status",
                "status": {"equals": "In Progress"}
            }
        ]
    }
    
    # Add client-facing exclusion filter
    filter_params = build_client_facing_exclusion_filter(status_filter)
    
    issues = notion.query_database(ISSUES_DB_ID, filter_params=filter_params)
    
    # If no results with those statuses, try a simpler approach - get all issues and filter by priority
    if not issues:
        logger.debug("No issues found with Unreported/Open/In Progress status, trying broader query")
        # Get all issues and we'll filter by priority/status in code
        issues = notion.query_database(ISSUES_DB_ID, filter_params=None)
    
    # Filter out resolved issues in code if needed
    if issues:
        issues = [
            issue for issue in issues
            if safe_get_property(issue, "Status", "status") not in ["Resolved", "Closed", "Completed"]
        ]
        
        # Apply client-facing exclusion filter (post-query as fallback)
        issues = filter_client_facing_items(issues, item_type="issue")
    
    if not issues:
        logger.info("No outstanding issues found.")
        return False
    
    logger.info(f"Found {len(issues)} outstanding issues.")
    
    # Sort by priority (if available) - prioritize Critical, then High, then others
    def get_priority_value(issue):
        priority = safe_get_property(issue, "Priority", "select")
        priority_map = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        return priority_map.get(priority, 99)
    
    issues_sorted = sorted(issues, key=get_priority_value)
    critical_issue = issues_sorted[0]
    
    # Extract issue information safely
    issue_title = safe_get_property(critical_issue, "Name", "title") or "Untitled Issue"
    issue_id = critical_issue.get("id")
    issue_url = critical_issue.get("url", "")
    issue_description = safe_get_property(critical_issue, "Description", "rich_text") or ""
    issue_priority = safe_get_property(critical_issue, "Priority", "select") or "High"
    
    logger.info(f"Addressing critical issue: {issue_title} (ID: {issue_id})")
    
    # Create handoff task in Agent-Tasks DB
    # Try to get the database to find valid status values
    default_status = None
    try:
        db_schema = notion.client.databases.retrieve(database_id=AGENT_TASKS_DB_ID)
        status_prop = db_schema.get("properties", {}).get("Status", {})
        if status_prop.get("type") == "status":
            status_options = status_prop.get("status", {}).get("options", [])
            # Find first available status option (prefer non-completed statuses)
            for option in status_options:
                option_name = option.get("name", "")
                if option_name in ["Ready", "Proposed", "Draft", "Not Started"]:
                    default_status = option_name
                    break
            # If no preferred status found, use first non-completed one
            if not default_status and status_options:
                for option in status_options:
                    option_name = option.get("name", "")
                    if option_name not in ["Complete", "Completed", "Done", "Closed"]:
                        default_status = option_name
                        break
    except Exception as e:
        logger.debug(f"Could not retrieve database schema: {e}")
        # Don't set status if we can't determine valid values
    
    # Build base description
    base_description = f"""## Context
A critical issue has been identified that requires immediate attention and resolution planning.

## Issue Details
- **Issue Title:** {issue_title}
- **Issue ID:** {issue_id}
- **Issue URL:** {issue_url}
- **Priority:** {issue_priority}
- **Description:** {issue_description}

## Objective
Review this issue and create a detailed plan for resolution. Identify the responsible agent(s), break down the work into actionable tasks, and prepare the next handoff to the execution agent.

## Required Actions
1. Analyze the issue thoroughly
2. Identify root cause(s) and contributing factors
3. Determine the appropriate agent(s) for resolution
4. Create a detailed implementation plan
5. Break down work into discrete, actionable tasks
6. Identify dependencies and prerequisites
7. Create the next handoff task for the execution agent

## Success Criteria
- [ ] Issue analysis completed
- [ ] Root cause identified
- [ ] Resolution plan created
- [ ] Execution agent identified
- [ ] Next handoff task created with all required context
"""
    
    # Add mandatory next handoff instructions
    cursor_inbox_path = str(get_agent_inbox_path("Cursor MM1 Agent")) + "/"
    if TASK_CREATION_HELPERS_AVAILABLE:
        task_description = add_mandatory_next_handoff_instructions(
            description=base_description,
            next_task_name="Issue Resolution Implementation",
            target_agent="Cursor MM1 Agent",  # Default to Cursor MM1 for execution
            next_task_id="TO_BE_CREATED",
            inbox_path=cursor_inbox_path,
            project_name=f"Issue-{issue_title[:30].replace(' ', '-')}",
            detailed_instructions=(
                f"Create handoff trigger file with the complete resolution plan, all identified tasks, "
                f"dependencies, and context needed to begin implementation. Include link to issue ({issue_url}) "
                f"and the planning task. Ensure all deliverables and artifacts are documented."
            )
        )
    else:
        # Fallback without helpers
        task_description = base_description + f"""

## 🚨 MANDATORY HANDOFF REQUIREMENT

**CRITICAL:** Upon completion of this task, you MUST create a handoff trigger file for **Issue Resolution Implementation** assigned to **Cursor MM1 Agent**.

**Handoff File Location:** `{cursor_inbox_path}`

**Required Content:**
- Complete resolution plan
- All identified tasks
- Dependencies and prerequisites
- Link to issue ({issue_url})
- All context needed for implementation to begin

**NO EXCEPTIONS. TASK IS NOT COMPLETE UNTIL HANDOFF FILE IS CREATED.**
"""
    
    # Truncate if too long (Notion has 2000 char limit for rich_text)
    if len(task_description) > 1999:
        task_description = task_description[:1996] + "..."
    
    handoff_task_properties = {
        "Task Name": {
            "title": [{"text": {"content": f"Plan Resolution for Issue: {issue_title[:50]}"}}]
        },
        "Description": {
            "rich_text": [{"text": {"content": task_description}}]
        },
        "Priority": {
            "select": {"name": issue_priority}
        },
        "Assigned-Agent": {
            "relation": [{"id": CLAUDE_MM1_AGENT_ID}]  # Planning tasks go to Claude MM1
        }
    }
    
    # Detect and persist Research mode state
    research_mode = detect_research_mode()
    if research_mode:
        handoff_task_properties["Research Mode Detected"] = {
            "select": {"name": research_mode}
        }
        logger.info(f"Set Research Mode Detected to '{research_mode}' for task creation")
    
    # Only add Status if we have a valid default_status
    if default_status:
        handoff_task_properties["Status"] = {
            "status": {"name": default_status}
        }
    
    new_task = notion.create_page(AGENT_TASKS_DB_ID, handoff_task_properties)
    
    if new_task:
        task_id = new_task.get("id")
        task_url = new_task.get("url", "")
        logger.info(f"Created handoff task in Agent-Tasks: {task_url}")
        
        # Try to link issue to task via relation (if property exists)
        # The Issues+Questions database uses "Agent-Tasks" as the relation property
        try:
            for prop_name in ["Agent-Tasks", "Related Tasks", "Tasks", "Linked Tasks"]:
                try:
                    update_properties = {
                        prop_name: {
                            "relation": [{"id": task_id}]
                        }
                    }
                    notion.update_page(issue_id, update_properties)
                    logger.info(f"Linked issue to task via {prop_name}")
                    break
                except Exception as prop_error:
                    logger.debug(f"Property {prop_name} not found, trying next...")
                    continue
        except Exception as e:
            logger.debug(f"Could not link issue to task: {e}")
        
        # Create trigger file for Claude MM1 Agent if task is ready
        if default_status in ["Ready", "Proposed", "Not Started"]:
            task_details = {
                "task_id": task_id,
                "task_title": f"Plan Resolution for Issue: {issue_title[:50]}",
                "task_url": task_url,
                "project_id": None,
                "project_title": None,
                "description": task_description,
                "status": default_status or "Ready",
                "agent_name": "Claude MM1 Agent",
                "agent_id": CLAUDE_MM1_AGENT_ID,  # Include agent_id for normalization
                "priority": issue_priority,
                "handoff_instructions": (
                    "Review the issue and create a detailed resolution plan. Upon completion, you MUST:\n"
                    "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
                    "2. Update the task status in Notion\n"
                    "3. Create a handoff trigger file for the implementation task (see task description for details)\n"
                    "4. Document all deliverables and artifacts\n"
                    "5. Provide all context needed for the implementation task to begin\n\n"
                    "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
                )
            }
            trigger_file = create_trigger_file("MM1", "Claude MM1 Agent", task_details)
            if trigger_file:
                logger.info(f"Created trigger file for planning task: {trigger_file}")
        
        return True
    else:
        logger.error("Failed to create handoff task for issue")
        return False


# ============================================================================
# IN-PROGRESS PROJECT HANDLING
# ============================================================================

def handle_in_progress_project(notion: NotionManager):
    """Check for in-progress projects and trigger next agent task"""
    logger.info("Checking for in-progress projects...")
    
    # Filter for in-progress projects
    # Try "In-Progress" first, then "In Progress" as fallback
    status_filter = {
        "property": "Status",
        "status": {"equals": "In-Progress"}
    }
    
    # Add client-facing exclusion filter
    filter_params = build_client_facing_exclusion_filter(status_filter)
    
    in_progress_projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    # If no results, try "In Progress" (with space) as fallback
    if not in_progress_projects:
        logger.debug("No projects found with 'In-Progress' status, trying 'In Progress' (with space)")
        status_filter = {
            "property": "Status",
            "status": {"equals": "In Progress"}
        }
        filter_params = build_client_facing_exclusion_filter(status_filter)
        in_progress_projects = notion.query_database(PROJECTS_DB_ID, filter_params=filter_params)
    
    # Apply client-facing exclusion filter (post-query as fallback)
    if in_progress_projects:
        in_progress_projects = filter_client_facing_items(in_progress_projects, item_type="project")
    
    if not in_progress_projects:
        logger.info("No 'In-Progress' or 'In Progress' projects found.")
        return
    
    logger.info(f"Found {len(in_progress_projects)} 'In-Progress' project(s).")
    
    # For simplicity, process the first project (or could process all)
    current_project = in_progress_projects[0]
    project_title = safe_get_property(current_project, "Name", "title") or "Untitled Project"
    project_id = current_project.get("id")
    
    logger.info(f"Processing project: {project_title} (ID: {project_id})")
    
    # Get agent tasks for this project
    # Try "Projects" (plural) first, then fallback to "Project" (singular)
    base_filter = {
        "and": [
            {
                "property": "Projects",
                "relation": {"contains": project_id}
            },
            {
                "property": "Status",
                "status": {"does_not_equal": "Complete"}
            }
        ]
    }
    
    # Add client-facing exclusion filter
    filter_params = build_client_facing_exclusion_filter(base_filter)
    
    agent_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # If no results with "Projects", try "Project" (singular) as fallback
    if not agent_tasks:
        logger.debug("No tasks found with 'Projects' relation, trying 'Project' (singular)")
        base_filter = {
            "and": [
                {
                    "property": "Project",
                    "relation": {"contains": project_id}
                },
                {
                    "property": "Status",
                    "status": {"does_not_equal": "Complete"}
                }
            ]
        }
        filter_params = build_client_facing_exclusion_filter(base_filter)
        agent_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # Apply client-facing exclusion filter (post-query as fallback)
    if agent_tasks:
        agent_tasks = filter_client_facing_items(agent_tasks, item_type="task")
    
    if not agent_tasks:
        logger.info(f"No outstanding agent tasks for project '{project_title}'.")
        return
    
    logger.info(f"Found {len(agent_tasks)} outstanding agent task(s) for project '{project_title}'.")
    
    # Prioritize tasks: In-Progress/In Progress > Ready for Handoff > Not Started
    def get_task_priority(task):
        status = safe_get_property(task, "Status", "status")
        priority_map = {
            "In-Progress": 0,
            "In Progress": 0,  # Handle both variations
            "Ready for Handoff": 1,
            "Not Started": 2,
            "Ready": 3
        }
        return priority_map.get(status, 99)
    
    agent_tasks_sorted = sorted(agent_tasks, key=get_task_priority)
    current_task = agent_tasks_sorted[0]
    
    # Extract task information safely
    task_title = safe_get_property(current_task, "Task Name", "title") or "Untitled Task"
    task_id = current_task.get("id")
    task_url = current_task.get("url", "")
    task_status = safe_get_property(current_task, "Status", "status") or "Unknown"
    task_description = safe_get_property(current_task, "Description", "rich_text") or ""
    
    # Get assigned agent
    assigned_agent_relation = safe_get_property(current_task, "Assigned-Agent", "relation") or []
    assigned_agent_id = None
    assigned_agent_name = "Unknown Agent"
    
    if assigned_agent_relation and len(assigned_agent_relation) > 0:
        assigned_agent_id = assigned_agent_relation[0].get("id")
        # Try to fetch agent name from the relation
        agent_name = notion.get_page_title(assigned_agent_id)
        if agent_name:
            assigned_agent_name = agent_name
        else:
            # Fallback to ID-based name
            assigned_agent_name = f"Agent_{assigned_agent_id[:8] if assigned_agent_id else 'unknown'}"
            logger.warning(f"Could not retrieve agent name for ID {assigned_agent_id}, using fallback")
    
    logger.info(
        f"Identified task: '{task_title}' (Status: {task_status}) "
        f"for agent: {assigned_agent_name}"
    )
    
    # Determine agent type
    agent_type = determine_agent_type(assigned_agent_name, assigned_agent_id)
    
    # Prepare task details for the trigger file
    task_details = {
        "task_id": task_id,
        "task_title": task_title,
        "task_url": task_url,
        "project_id": project_id,
        "project_title": project_title,
        "description": task_description,
        "status": task_status,
        "agent_name": assigned_agent_name,
        "agent_id": assigned_agent_id,  # Include agent_id for normalization
        "priority": safe_get_property(current_task, "Priority", "select") or "High",
        "handoff_instructions": (
            "Proceed with the execution of this task. Upon completion, you MUST:\n"
            "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
            "2. Update the task status in Notion\n"
            "3. Create a handoff trigger file for the next task (see task description for details)\n"
            "4. Document all deliverables and artifacts\n"
            "5. Provide all context needed for the next task to begin\n\n"
            "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
        )
    }
    
    # Update task with Research mode detection if not already set
    current_research_mode = safe_get_property(current_task, "Research Mode Detected", "select")
    if not current_research_mode:
        research_mode = detect_research_mode()
        if research_mode:
            update_properties = {
                "Research Mode Detected": {
                    "select": {"name": research_mode}
                }
            }
            if notion.update_page(task_id, update_properties):
                logger.info(f"Updated Research Mode Detected to '{research_mode}' for task '{task_title}'")
    
    # Create trigger file
    trigger_file = create_trigger_file(agent_type, assigned_agent_name, task_details)
    
    if trigger_file:
        logger.info(f"Task '{task_title}' trigger file created successfully.")
        
        # Update task status in Notion to 'In-Progress' or 'In Progress' if it's not already
        # Try to match the existing status format in the database
        if task_status not in ["In-Progress", "In Progress"]:
            # Try "In Progress" first (more common), then "In-Progress" as fallback
            update_properties = {
                "Status": {"status": {"name": "In Progress"}}
            }
            if notion.update_page(task_id, update_properties):
                logger.info(f"Task '{task_title}' status updated to 'In Progress'.")
            else:
                # Try with hyphen if space version failed
                update_properties = {
                    "Status": {"status": {"name": "In-Progress"}}
                }
                if notion.update_page(task_id, update_properties):
                    logger.info(f"Task '{task_title}' status updated to 'In-Progress'.")
    else:
        logger.error(f"Failed to create trigger file for task '{task_title}'.")


# ============================================================================
# READY TASK TRIGGER CHECK
# ============================================================================

def check_and_create_ready_task_triggers(notion: NotionManager):
    """Check for ready tasks that need trigger files created"""
    logger.info("Checking for ready tasks that need trigger files...")
    
    # Filter for ready tasks with assigned agents
    base_filter = {
        "and": [
            {
                "or": [
                    {"property": "Status", "status": {"equals": "Ready"}},
                    {"property": "Status", "status": {"equals": "Ready for Handoff"}},
                    {"property": "Status", "status": {"equals": "Not Started"}}
                ]
            },
            {
                "property": "Assigned-Agent",
                "relation": {"is_not_empty": True}
            }
        ]
    }
    
    # Add client-facing exclusion filter
    filter_params = build_client_facing_exclusion_filter(base_filter)
    
    ready_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=filter_params)
    
    # Apply client-facing exclusion filter (post-query as fallback)
    if ready_tasks:
        ready_tasks = filter_client_facing_items(ready_tasks, item_type="task")
    
    if not ready_tasks:
        logger.info("No ready tasks found that need trigger files.")
        return
    
    logger.info(f"Found {len(ready_tasks)} ready task(s) with assigned agents.")
    
    # Check which ones already have trigger files
    tasks_needing_triggers = []
    for task in ready_tasks:
        task_id = task.get("id")
        assigned_agent_relation = safe_get_property(task, "Assigned-Agent", "relation") or []
        
        if not assigned_agent_relation:
            continue
        
        assigned_agent_id = assigned_agent_relation[0].get("id")
        assigned_agent_name = notion.get_page_title(assigned_agent_id) or f"Agent_{assigned_agent_id[:8]}"
        
        # Check if trigger file exists (simple check - look for files with task ID in name)
        agent_type = determine_agent_type(assigned_agent_name, assigned_agent_id)
        if agent_type == "MM1":
            base_path = MM1_AGENT_TRIGGER_BASE
        else:
            base_path = MM2_AGENT_TRIGGER_BASE
        
        agent_folder = normalize_agent_folder_name(assigned_agent_name, assigned_agent_id)
        if agent_type == "MM2":
            agent_folder = f"{agent_folder}-gd"
        
        trigger_folder = base_path / agent_folder / "01_inbox"
        task_id_short = task_id.replace("-", "")[:8]
        
        # Check if any trigger file exists with this task ID
        trigger_exists = False
        if trigger_folder.exists():
            for trigger_file in trigger_folder.glob(f"*{task_id_short}*.json"):
                trigger_exists = True
                break
        
        if not trigger_exists:
            tasks_needing_triggers.append((task, assigned_agent_name, assigned_agent_id, agent_type))
    
    if not tasks_needing_triggers:
        logger.info("All ready tasks already have trigger files.")
        return
    
    logger.info(f"Found {len(tasks_needing_triggers)} ready task(s) needing trigger files.")
    
    # Create trigger files for tasks needing them (limit to top 5 to avoid overwhelming)
    for task, agent_name, agent_id, agent_type in tasks_needing_triggers[:5]:
        task_title = safe_get_property(task, "Task Name", "title") or "Untitled Task"
        task_id = task.get("id")
        task_url = task.get("url", "")
        task_status = safe_get_property(task, "Status", "status") or "Ready"
        task_description = safe_get_property(task, "Description", "rich_text") or ""
        
        # Get project info if available
        project_relation = safe_get_property(task, "Project", "relation") or safe_get_property(task, "Projects", "relation") or []
        project_id = None
        project_title = None
        if project_relation and len(project_relation) > 0:
            project_id = project_relation[0].get("id")
            project_title = notion.get_page_title(project_id)
        
        task_details = {
            "task_id": task_id,
            "task_title": task_title,
            "task_url": task_url,
            "project_id": project_id,
            "project_title": project_title,
            "description": task_description,
            "status": task_status,
            "agent_name": agent_name,
            "agent_id": agent_id,  # Include agent_id for normalization
            "priority": safe_get_property(task, "Priority", "select") or "High",
            "handoff_instructions": (
                "Proceed with the execution of this task. Upon completion, you MUST:\n"
                "1. **MOVE TRIGGER FILE (MANUAL)**: You MUST manually call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed. This cannot be automated - you are responsible for moving it.\n"
                "2. Update the task status in Notion\n"
                "3. Create a handoff trigger file for the next task (see task description for details)\n"
                "4. Document all deliverables and artifacts\n"
                "5. Provide all context needed for the next task to begin\n\n"
                "**MANDATORY:** Task is NOT complete until trigger file is manually moved and handoff file is created."
            )
        }
        
        # Update task with Research mode detection if not already set
        current_research_mode = safe_get_property(task, "Research Mode Detected", "select")
        if not current_research_mode:
            research_mode = detect_research_mode()
            if research_mode:
                update_properties = {
                    "Research Mode Detected": {
                        "select": {"name": research_mode}
                    }
                }
                if notion.update_page(task_id, update_properties):
                    logger.info(f"Updated Research Mode Detected to '{research_mode}' for task '{task_title}'")
        
        trigger_file = create_trigger_file(agent_type, agent_name, task_details)
        if trigger_file:
            logger.info(f"Created trigger file for ready task '{task_title}': {trigger_file}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def analyze_task_completion(notion: NotionManager):
    """Analyze task completion patterns to identify review loops"""
    from collections import defaultdict
    
    logger.info("=" * 80)
    logger.info("TASK COMPLETION ANALYSIS")
    logger.info("=" * 80)
    
    # Get all tasks
    all_tasks = notion.query_database(AGENT_TASKS_DB_ID, filter_params=None)
    
    logger.info(f"Total tasks found: {len(all_tasks)}")
    
    # Analyze by status
    status_counts = defaultdict(int)
    for task in all_tasks:
        status = safe_get_property(task, "Status", "status") or "Unknown"
        status_counts[status] += 1
    
    logger.info("Task Status Distribution:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {status}: {count}")
    
    # Identify planning vs implementation tasks
    planning_tasks = []
    implementation_tasks = []
    
    for task in all_tasks:
        task_name = safe_get_property(task, "Task Name", "title") or "Untitled"
        status = safe_get_property(task, "Status", "status") or "Unknown"
        
        is_planning = any(kw in task_name.lower() for kw in ["plan", "review", "analyze", "assess", "evaluate"])
        is_implementation = any(kw in task_name.lower() for kw in ["implement", "build", "create", "develop", "fix", "resolve", "execute"])
        
        if is_planning:
            planning_tasks.append({"name": task_name, "status": status, "url": task.get("url", "")})
        elif is_implementation:
            implementation_tasks.append({"name": task_name, "status": status})
    
    logger.info(f"\nPlanning/Review Tasks: {len(planning_tasks)}")
    logger.info(f"Implementation Tasks: {len(implementation_tasks)}")
    
    if len(planning_tasks) > 0:
        ratio = len(planning_tasks) / len(implementation_tasks) if implementation_tasks else float('inf')
        logger.info(f"Ratio: {ratio:.2f}")
        
        if ratio > 2.0:
            logger.warning("⚠️  CRITICAL: Too many planning tasks relative to implementation tasks!")
            logger.warning("   This suggests a review loop where planning tasks create more planning tasks.")
    
    # Check incomplete planning tasks
    incomplete_planning = [t for t in planning_tasks if t["status"] not in ["Complete", "Completed", "Done"]]
    if incomplete_planning:
        logger.warning(f"\n⚠️  {len(incomplete_planning)} INCOMPLETE PLANNING TASKS:")
        for task in incomplete_planning[:5]:
            logger.warning(f"  - [{task['status']}] {task['name']}")
            logger.warning(f"    {task['url']}")
    
    # Check stuck tasks
    stuck_tasks = []
    for task in all_tasks:
        status = safe_get_property(task, "Status", "status") or "Unknown"
        if status in ["Ready", "In Progress", "In-Progress", "Ready for Handoff"]:
            task_name = safe_get_property(task, "Task Name", "title") or "Untitled"
            created_time = task.get("created_time", "")
            
            if created_time:
                try:
                    from datetime import datetime
                    created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    now = datetime.now(created_dt.tzinfo)
                    age_days = (now - created_dt).days
                    
                    if age_days > 1:
                        stuck_tasks.append({"name": task_name, "status": status, "age_days": age_days, "url": task.get("url", "")})
                except:
                    pass
    
    if stuck_tasks:
        logger.warning(f"\n⚠️  {len(stuck_tasks)} POTENTIALLY STUCK TASKS:")
        for task in sorted(stuck_tasks, key=lambda x: -x["age_days"])[:5]:
            logger.warning(f"  - [{task['status']}] {task['name']} (Age: {task['age_days']} days)")
            logger.warning(f"    {task['url']}")
    
    # Completion rate
    complete_count = status_counts.get("Complete", 0) + status_counts.get("Completed", 0)
    completion_rate = (complete_count / len(all_tasks) * 100) if all_tasks else 0
    logger.info(f"\nCompletion Rate: {completion_rate:.1f}%")
    
    if completion_rate < 20:
        logger.warning("⚠️  Low completion rate - tasks may not be getting completed!")
    
    logger.info("=" * 80)


def preflight_token_validation() -> Optional[str]:
    """
    Phase 0 Preflight Check: Multi-source token validation.
    
    Implements the MANDATORY multi-step troubleshoot process required by workspace
    methodology when encountering Notion API authentication failures.
    
    Process:
    1. Detect token format validity (prefix, length)
    2. Enumerate ALL known token sources
    3. Test EACH token source independently
    4. If valid token found in alternate source, sync it and continue
    5. Only declare failure if ALL sources exhausted
    6. Create structured diagnostic Issue if all sources fail
    
    Returns:
        Valid token string if found, None if all sources exhausted
    
    Raises:
        SystemExit: If all token sources exhausted (after creating Issue)
    """
    logger.info("=" * 80)
    logger.info("Phase 0: Preflight Token Validation")
    logger.info("=" * 80)
    
    try:
        from shared_core.notion.token_manager import (
            multi_source_token_troubleshoot,
            sync_token_to_primary,
            validate_token
        )
        from shared_core.notion.issues_questions import create_issue_or_question
        TROUBLESHOOT_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Could not import troubleshoot functions: {e}")
        TROUBLESHOOT_AVAILABLE = False
        # Fallback to simple token check
        token = get_notion_token()
        if token:
            # Try basic validation by attempting to create a client
            try:
                test_client = Client(auth=token)
                test_client.users.me()  # Simple API call to validate
                logger.info("✅ Token validated via fallback method")
                return token
            except Exception:
                logger.error("Token validation failed and troubleshoot functions unavailable")
                return None
        logger.error("Token validation failed and troubleshoot functions unavailable")
        return None
    
    # Step 1: Get primary token
    primary_token = get_notion_token()
    
    # Step 2: Validate primary token if found
    if primary_token:
        logger.info("Primary token found, validating against API...")
        if validate_token(primary_token):
            logger.info("✅ Primary token is VALID")
            return primary_token
        else:
            logger.warning("⚠️ Primary token failed API validation")
    
    # Step 3: Run multi-source troubleshoot process
    logger.info("Running multi-source token troubleshoot...")
    troubleshoot_result = multi_source_token_troubleshoot()
    
    logger.info(f"Troubleshoot Status: {troubleshoot_result['status']}")
    logger.info(f"Primary Source: {troubleshoot_result['primary_token_source']}")
    logger.info(f"Primary Valid: {troubleshoot_result['primary_token_valid']}")
    
    # Step 4: Handle results
    if troubleshoot_result['status'] == 'valid':
        logger.info("✅ Valid token confirmed from primary source")
        return troubleshoot_result['valid_token']
    
    elif troubleshoot_result['status'] == 'found_alternate':
        logger.warning("⚠️ Valid token found in alternate source - syncing...")
        valid_token = troubleshoot_result['valid_token']
        valid_source = troubleshoot_result['valid_token_source']
        
        # Sync token to primary source
        if sync_token_to_primary(valid_token, primary_source="cache"):
            logger.info(f"✅ Token synced from {valid_source} to primary cache")
            return valid_token
        else:
            logger.warning(f"⚠️ Failed to sync token, but using valid token from {valid_source}")
            return valid_token
    
    elif troubleshoot_result['status'] == 'all_failed':
        logger.error("❌ ALL token sources exhausted - cannot proceed")
        
        # Step 5: Create structured diagnostic Issue
        logger.info("Creating diagnostic Issue in Issues+Questions...")
        
        diagnostic_details = f"""
## Token Validation Failure - Multi-Source Troubleshoot Results

**Status:** All token sources exhausted

**Primary Token Source:** {troubleshoot_result.get('primary_token_source', 'Unknown')}
**Primary Token Valid:** {troubleshoot_result.get('primary_token_valid', False)}

### Sources Checked:
"""
        for source in troubleshoot_result.get('sources_checked', []):
            status = "✅ VALID" if source.get('api_valid') else ("❌ FORMAT_INVALID" if not source.get('format_valid') else "❌ API_FAILED")
            diagnostic_details += f"\n- **{source.get('source')}**: {status}\n"
            diagnostic_details += f"  - Token prefix: `{source.get('token_prefix', 'N/A')}`\n"
        
        diagnostic_details += "\n### Recommendations:\n"
        for rec in troubleshoot_result.get('recommendations', []):
            diagnostic_details += f"\n- {rec}\n"
        
        diagnostic_details += """
### Required Actions:
1. Regenerate Notion API token
2. Update all token sources (environment variables, cache files, config files)
3. Verify token works with: `python3 -m shared_core.notion.token_manager`
4. Create Agent-Task for codebase-wide token scrub if mismatch detected
"""
        
        issue_id = create_issue_or_question(
            name="Notion API Token Validation Failure - All Sources Exhausted",
            type=["Internal Issue", "Script Issue"],
            status="Unreported",
            priority="Critical",
            description=diagnostic_details,
            tags=["token", "authentication", "critical-bug"]
        )
        
        if issue_id:
            logger.info(f"✅ Created diagnostic Issue: {issue_id}")
        else:
            logger.error("❌ Failed to create diagnostic Issue")
        
        logger.error("=" * 80)
        logger.error("PREFLIGHT CHECK FAILED: Cannot proceed without valid token")
        logger.error("=" * 80)
        logger.error("Please review the diagnostic Issue in Issues+Questions and resolve token issue.")
        sys.exit(1)
    
    # Should not reach here, but return None as fallback
    return None


def main():
    """Main execution function"""
    logger.info("=" * 80)
    logger.info("Notion Task Management and Agent Trigger System")
    logger.info("=" * 80)
    
    # Check if notion-client is available
    if not NOTION_CLIENT_AVAILABLE:
        logger.error("notion-client library not available. Install with: pip install notion-client")
        sys.exit(1)
    
    # Phase 0: Preflight token validation with multi-source troubleshoot
    token = preflight_token_validation()
    if not token:
        logger.error("Token validation failed - cannot proceed")
        sys.exit(1)
    
    # Initialize Notion client
    try:
        notion = NotionManager(token)
        logger.info("✅ Notion client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Notion client: {e}")
        # If initialization fails, it's likely a token issue - troubleshoot already ran
        logger.error("Token troubleshoot already performed - cannot recover from initialization failure")
        sys.exit(1)
    
    # Validate database IDs
    if ISSUES_DB_ID.startswith("YOUR_") or PROJECTS_DB_ID.startswith("YOUR_"):
        logger.warning(
            "Database IDs appear to be placeholders. "
            "Please set ISSUES_DB_ID, PROJECTS_DB_ID, AGENT_TASKS_DB_ID environment variables."
        )
    
    # FIRST: Analyze task completion to identify problems
    try:
        analyze_task_completion(notion)
    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
    
    # SECOND: Scan local resources (plans, handoff files) for unfinished work
    logger.info("=" * 80)
    logger.info("Scanning Local Resources for Unfinished Work")
    logger.info("=" * 80)
    
    unfinished_plans = scan_cursor_plans_directory()
    pending_triggers = scan_agent_inbox_folders()
    
    # Analyze unfinished work to determine what to continue
    unfinished_work = analyze_unfinished_work(notion, unfinished_plans, pending_triggers)
    
    # THIRD: Prioritize continuing existing work over starting new work
    work_continued = False
    if unfinished_work:
        logger.info("=" * 80)
        logger.info("PRIORITIZING: Continuing Existing Unfinished Work")
        logger.info("=" * 80)
        work_continued = continue_unfinished_work(unfinished_work, notion)
    
    # FOURTH: If no unfinished work to continue, process Notion databases
    if not work_continued:
        logger.info("=" * 80)
        logger.info("No unfinished work found - Processing Notion Databases")
        logger.info("=" * 80)
        try:
            issues_handled = handle_issues(notion)
            if not issues_handled:
                handle_in_progress_project(notion)
            
            # Also check for ready tasks that need trigger files
            check_and_create_ready_task_triggers(notion)
        except Exception as e:
            logger.error(f"Error during execution: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.info("=" * 80)
        logger.info("Unfinished work analysis complete - Agent should continue existing work")
        logger.info("=" * 80)
    
    logger.info("=" * 80)
    logger.info("Execution completed successfully")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()

