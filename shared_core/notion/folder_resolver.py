#!/usr/bin/env python3
"""
Notion Folder Resolver - CENTRALIZED FOLDER PATH RESOLUTION
============================================================

This module provides the CANONICAL way to get agent trigger folder paths.
ALL scripts that reference trigger folders MUST use this module.

**MANDATORY USAGE:**
```python
from shared_core.notion.folder_resolver import (
    get_trigger_base_path,
    get_agent_inbox_path,
    get_folder_by_role,
)

# Get base trigger path
trigger_base = get_trigger_base_path()

# Get specific agent inbox
inbox = get_agent_inbox_path("Claude-MM1-Agent")
```

**FEATURES:**
- Queries Notion Folders database for dynamic path resolution
- Caches results with configurable TTL
- Falls back to hardcoded paths if Notion unavailable
- Supports both primary (local) and fallback (Google Drive) paths

**Issue Reference:**
DriveSheetsSync Migration: Agent Path Reference Updates (2e1e7361-6c27-8145-af23-c602aa91a757)

Version: 1.0.0
Created: 2026-01-07
Author: Claude Code Agent
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from functools import lru_cache
from datetime import datetime, timezone

# Setup logging
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Folders Database ID (from Notion workspace)
FOLDERS_DB_ID = "26ce7361-6c27-81bb-81b7-dd43760ee6cc"

# Default paths (fallback if Notion unavailable)
PROJECTS_TRIGGER_BASE_PATH = Path("/Users/brianhellemn/Projects/Agents/Agent-Triggers")
DEFAULT_TRIGGER_BASE_PATH = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
DEFAULT_FALLBACK_TRIGGER_PATH = Path(
    "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co"
    "/My Drive/Agents-gd/Agent-Triggers-gd"
)

# Cache TTL in seconds (default 5 minutes)
CACHE_TTL_SECONDS = int(os.getenv("FOLDER_CACHE_TTL", "300"))

# Cache storage
_folder_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0.0

# ============================================================================
# AGENT NAME TO FOLDER MAPPING
# ============================================================================

# Maps agent names (as they appear in Notion) to folder names
AGENT_FOLDER_MAP = {
    "Claude MM1 Agent": "Claude-MM1-Agent",
    "Claude MM2 Agent": "Claude-MM2-Agent",
    "Claude Code Agent": "Claude-Code-Agent",
    "Cursor MM1 Agent": "Cursor-MM1-Agent",
    "Cursor MM2 Agent": "Cursor-MM2-Agent",
    "Codex MM1 Agent": "Codex-MM1-Agent",
    "ChatGPT Code Review Agent": "ChatGPT-Code-Review-Agent",
    "ChatGPT Strategic Agent": "ChatGPT-Strategic-Agent",
    "ChatGPT Personal Assistant Agent": "ChatGPT-Personal-Assistant-Agent",
    "Notion AI Data Operations Agent": "Notion-AI-Data-Operations-Agent",
    "Notion AI Research Agent": "Notion-AI-Research-Agent",
}

# Agent Notion IDs to names mapping
AGENT_ID_TO_NAME = {
    "fa54f05c-e184-403a-ac28-87dd8ce9855b": "Claude MM1 Agent",
    "9c4b6040-5e0f-4d31-ae1b-d4a43743b224": "Claude MM2 Agent",
    "2cfe7361-6c27-805f-857c-e90c3db6efb9": "Claude Code Agent",
    "249e7361-6c27-8100-8a74-de7eabb9fc8d": "Cursor MM1 Agent",
    "26de7361-6c27-80c2-b7cd-c1a2a0279937": "Cursor MM2 Agent",
    "2b1e7361-6c27-80fb-8ce9-fd3cf78a5cad": "Codex MM1 Agent",
    "2b4e7361-6c27-8129-8f6f-dff0dfb23e8e": "ChatGPT Code Review Agent",
    "2b1e7361-6c27-80d5-b162-d73c6396c31c": "ChatGPT Strategic Agent",
    "13bb306b-1e55-45be-99c6-b5638618ba04": "ChatGPT Personal Assistant Agent",
    "3e6cfe03-c82e-4aee-974a-e2ee6a69c187": "Notion AI Data Operations Agent",
    "249e7361-6c27-8111-8327-d707f35e2c6a": "Notion AI Research Agent",
}


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def _is_cache_valid() -> bool:
    """Check if the folder cache is still valid."""
    global _cache_timestamp
    if not _folder_cache:
        return False
    return (time.time() - _cache_timestamp) < CACHE_TTL_SECONDS


def _clear_cache() -> None:
    """Clear the folder cache."""
    global _folder_cache, _cache_timestamp
    _folder_cache = {}
    _cache_timestamp = 0.0
    logger.debug("Folder cache cleared")


def _update_cache(folders: Dict[str, Any]) -> None:
    """Update the folder cache with new data."""
    global _folder_cache, _cache_timestamp
    _folder_cache = folders
    _cache_timestamp = time.time()
    logger.debug(f"Folder cache updated with {len(folders)} entries")


# ============================================================================
# NOTION QUERY FUNCTIONS
# ============================================================================

def _query_folders_from_notion() -> Dict[str, Any]:
    """
    Query the Notion Folders database for folder information.

    Returns:
        Dict mapping folder roles/paths to folder information
    """
    try:
        from .token_manager import get_notion_client
        from .id_utils import normalize_notion_id

        client = get_notion_client()

        # Query the Folders database
        db_id = normalize_notion_id(FOLDERS_DB_ID)

        # First try to get data_source_id (new Notion API)
        try:
            db = client.databases.retrieve(database_id=db_id)
            data_sources = db.get("data_sources", [])

            if data_sources:
                data_source_id = data_sources[0].get("id")
                response = client.data_sources.query(data_source_id=data_source_id)
            else:
                # Fallback to legacy query
                response = client.databases.query(database_id=db_id)
        except AttributeError:
            # data_sources attribute doesn't exist, use legacy API
            response = client.databases.query(database_id=db_id)

        results = response.get("results", [])
        logger.info(f"Retrieved {len(results)} folders from Notion")

        folders = {}
        for page in results:
            props = page.get("properties", {})

            # Extract folder properties
            folder_name = _extract_title(props.get("Folder Name", {}))
            folder_path = _extract_rich_text(props.get("Folder Path", {}))
            folder_role = _extract_select(props.get("Folder Role", {}))
            folder_type = _extract_select(props.get("Folder Type", {}))

            if folder_path:
                folders[folder_path] = {
                    "name": folder_name,
                    "path": folder_path,
                    "role": folder_role,
                    "type": folder_type,
                    "page_id": page.get("id"),
                }

            # Also index by role if available
            if folder_role:
                folders[f"role:{folder_role}"] = {
                    "name": folder_name,
                    "path": folder_path,
                    "role": folder_role,
                    "type": folder_type,
                    "page_id": page.get("id"),
                }

        return folders

    except ImportError as e:
        logger.warning(f"notion-client not available: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Error querying Notion Folders database: {e}")
        return {}


def _extract_title(prop: Dict) -> Optional[str]:
    """Extract title property value."""
    if not prop:
        return None
    title_list = prop.get("title", [])
    if title_list:
        return title_list[0].get("plain_text", "")
    return None


def _extract_rich_text(prop: Dict) -> Optional[str]:
    """Extract rich_text property value."""
    if not prop:
        return None
    text_list = prop.get("rich_text", [])
    if text_list:
        return text_list[0].get("plain_text", "")
    return None


def _extract_select(prop: Dict) -> Optional[str]:
    """Extract select property value."""
    if not prop:
        return None
    select_obj = prop.get("select")
    if select_obj:
        return select_obj.get("name")
    return None


# ============================================================================
# PUBLIC API FUNCTIONS
# ============================================================================

def get_trigger_base_path(use_fallback: bool = False) -> Path:
    """
    Get the base path for agent trigger folders.

    Args:
        use_fallback: If True, return the Google Drive fallback path

    Returns:
        Path to the trigger folder base directory

    Example:
        ```python
        from shared_core.notion.folder_resolver import get_trigger_base_path

        trigger_base = get_trigger_base_path()
        # Returns: /Users/brianhellemn/Documents/Agents/Agent-Triggers
        ```
    """
    if use_fallback:
        return DEFAULT_FALLBACK_TRIGGER_PATH

    # Prefer the Projects-based trigger folder when present (per workspace convention).
    # This intentionally takes precedence over any Notion-provided path so local agent
    # handoff files land in the active Projects tree.
    try:
        if PROJECTS_TRIGGER_BASE_PATH.exists():
            return PROJECTS_TRIGGER_BASE_PATH
    except Exception:
        # If filesystem check fails, continue with Notion/default resolution.
        pass

    # Try to get from Notion cache first
    if _is_cache_valid():
        folder_info = _folder_cache.get("role:agent-triggers-base")
        if folder_info and folder_info.get("path"):
            return Path(folder_info["path"])

    # Query Notion if cache is invalid
    try:
        folders = _query_folders_from_notion()
        if folders:
            _update_cache(folders)
            folder_info = folders.get("role:agent-triggers-base")
            if folder_info and folder_info.get("path"):
                return Path(folder_info["path"])
    except Exception as e:
        logger.debug(f"Notion query failed, using default: {e}")

    # Fallback to default
    return DEFAULT_TRIGGER_BASE_PATH


def get_fallback_trigger_base_path() -> Path:
    """
    Get the Google Drive-synced fallback trigger base path.

    Returns:
        Path to the fallback trigger folder base directory
    """
    return get_trigger_base_path(use_fallback=True)


def get_agent_inbox_path(
    agent_name: str,
    agent_id: Optional[str] = None,
    use_fallback: bool = False
) -> Optional[Path]:
    """
    Get the inbox folder path for a specific agent.

    Args:
        agent_name: Name of the agent (e.g., "Claude MM1 Agent" or "Claude-MM1-Agent")
        agent_id: Optional agent Notion ID for more precise matching
        use_fallback: If True, return the Google Drive fallback path

    Returns:
        Path to the agent's inbox folder, or None if not found

    Example:
        ```python
        from shared_core.notion.folder_resolver import get_agent_inbox_path

        inbox = get_agent_inbox_path("Claude-MM1-Agent")
        # Returns: /Users/brianhellemn/Documents/Agents/Agent-Triggers/Claude-MM1-Agent/01_inbox
        ```
    """
    # Resolve agent name from ID if provided
    if agent_id:
        resolved_name = AGENT_ID_TO_NAME.get(agent_id.strip())
        if resolved_name:
            agent_name = resolved_name

    # Normalize agent name to folder format
    folder_name = normalize_agent_folder_name(agent_name)

    # Get base path
    base_path = get_trigger_base_path(use_fallback=use_fallback)

    # Build inbox path
    if use_fallback:
        # Fallback paths have -gd suffix
        folder_name = f"{folder_name}-gd"

    inbox_path = base_path / folder_name / "01_inbox"

    return inbox_path


def get_folder_by_role(role: str) -> Optional[str]:
    """
    Get folder path by its role identifier.

    Args:
        role: Role identifier (e.g., "agent-triggers-base", "documentation")

    Returns:
        Folder path string, or None if not found

    Example:
        ```python
        from shared_core.notion.folder_resolver import get_folder_by_role

        docs_path = get_folder_by_role("documentation")
        ```
    """
    # Check cache first
    if _is_cache_valid():
        folder_info = _folder_cache.get(f"role:{role}")
        if folder_info:
            return folder_info.get("path")

    # Query Notion
    try:
        folders = _query_folders_from_notion()
        if folders:
            _update_cache(folders)
            folder_info = folders.get(f"role:{role}")
            if folder_info:
                return folder_info.get("path")
    except Exception as e:
        logger.debug(f"Notion query failed for role {role}: {e}")

    return None


def validate_folder_exists(path: str) -> bool:
    """
    Validate that a folder path exists on the filesystem.

    Args:
        path: Folder path to validate

    Returns:
        True if folder exists and is a directory, False otherwise
    """
    try:
        p = Path(path)
        return p.exists() and p.is_dir()
    except Exception:
        return False


def normalize_agent_folder_name(agent_name: str) -> str:
    """
    Normalize agent name to folder name format.

    Handles various input formats:
    - "Claude MM1 Agent" -> "Claude-MM1-Agent"
    - "Claude-MM1-Agent" -> "Claude-MM1-Agent"
    - "Claude-MM1-Agent-Trigger" -> "Claude-MM1-Agent"

    Args:
        agent_name: Agent name in any format

    Returns:
        Normalized folder name
    """
    import re

    # Check if input matches a known agent name
    if agent_name in AGENT_FOLDER_MAP:
        return AGENT_FOLDER_MAP[agent_name]

    # Check if already in folder format
    folder_values = list(AGENT_FOLDER_MAP.values())
    if agent_name in folder_values:
        return agent_name

    # Normalize manually
    normalized = agent_name.strip()

    # Replace spaces with hyphens
    normalized = normalized.replace(" ", "-")

    # Remove common suffixes
    normalized = re.sub(r'-Trigger(-gd)?$', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'-Agent-Trigger$', '', normalized, flags=re.IGNORECASE)

    # Ensure proper capitalization for known patterns
    normalized = re.sub(r'Chat-?Gpt', 'ChatGPT', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'-Mm([12])', r'-MM\1', normalized)
    normalized = re.sub(r'-Ai-', r'-AI-', normalized, flags=re.IGNORECASE)

    # Ensure ends with -Agent if it's an agent folder
    agent_bases = ['claude', 'cursor', 'codex', 'chatgpt', 'notion-ai']
    normalized_lower = normalized.lower()
    has_agent_base = any(base in normalized_lower for base in agent_bases)

    if has_agent_base and not normalized.lower().endswith('-agent'):
        normalized = f"{normalized}-Agent"

    return normalized


def get_all_agent_inbox_paths() -> Dict[str, Path]:
    """
    Get inbox paths for all known agents.

    Returns:
        Dict mapping agent names to their inbox paths

    Example:
        ```python
        from shared_core.notion.folder_resolver import get_all_agent_inbox_paths

        inboxes = get_all_agent_inbox_paths()
        for agent, path in inboxes.items():
            print(f"{agent}: {path}")
        ```
    """
    result = {}
    for agent_name in AGENT_FOLDER_MAP.keys():
        inbox_path = get_agent_inbox_path(agent_name)
        if inbox_path:
            result[agent_name] = inbox_path
    return result


def get_agent_folder_structure(agent_name: str) -> Dict[str, Path]:
    """
    Get all folder paths for a specific agent (inbox, processed, failed).

    Args:
        agent_name: Name of the agent

    Returns:
        Dict with keys 'inbox', 'processed', 'failed' mapping to paths
    """
    base_path = get_trigger_base_path()
    folder_name = normalize_agent_folder_name(agent_name)
    agent_base = base_path / folder_name

    return {
        "inbox": agent_base / "01_inbox",
        "processed": agent_base / "02_processed",
        "failed": agent_base / "03_failed",
    }


def ensure_agent_folders_exist(agent_name: str) -> bool:
    """
    Ensure all agent folders exist (create if missing).

    Args:
        agent_name: Name of the agent

    Returns:
        True if all folders exist or were created successfully
    """
    try:
        folders = get_agent_folder_structure(agent_name)
        for folder_type, path in folders.items():
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured {folder_type} folder exists: {path}")
        return True
    except Exception as e:
        logger.error(f"Error creating agent folders for {agent_name}: {e}")
        return False


def get_folder_health_status() -> Dict[str, Any]:
    """
    Get health status of all agent folders.

    Returns:
        Dict with health status for each agent
    """
    base_path = get_trigger_base_path()
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_path_exists": validate_folder_exists(str(base_path)),
        "fallback_path_exists": validate_folder_exists(str(DEFAULT_FALLBACK_TRIGGER_PATH)),
        "agents": {},
    }

    for agent_name in AGENT_FOLDER_MAP.keys():
        folders = get_agent_folder_structure(agent_name)
        agent_status = {
            "inbox_exists": validate_folder_exists(str(folders["inbox"])),
            "processed_exists": validate_folder_exists(str(folders["processed"])),
            "failed_exists": validate_folder_exists(str(folders["failed"])),
        }
        agent_status["healthy"] = all(agent_status.values())
        status["agents"][agent_name] = agent_status

    status["all_healthy"] = all(
        a["healthy"] for a in status["agents"].values()
    )

    return status


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "get_trigger_base_path",
    "get_fallback_trigger_base_path",
    "get_agent_inbox_path",
    "get_folder_by_role",
    "validate_folder_exists",
    "normalize_agent_folder_name",
    "get_all_agent_inbox_paths",
    "get_agent_folder_structure",
    "ensure_agent_folders_exist",
    "get_folder_health_status",
    # Constants
    "DEFAULT_TRIGGER_BASE_PATH",
    "PROJECTS_TRIGGER_BASE_PATH",
    "DEFAULT_FALLBACK_TRIGGER_PATH",
    "FOLDERS_DB_ID",
    "AGENT_FOLDER_MAP",
    "AGENT_ID_TO_NAME",
]


# ============================================================================
# CLI TEST
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 70)
    print("Folder Resolver - Diagnostic")
    print("=" * 70)

    print(f"\nBase Trigger Path: {get_trigger_base_path()}")
    print(f"Fallback Trigger Path: {get_fallback_trigger_base_path()}")

    print("\n--- Agent Inbox Paths ---")
    for agent_name, path in get_all_agent_inbox_paths().items():
        exists = "EXISTS" if validate_folder_exists(str(path)) else "MISSING"
        print(f"  {agent_name}: {path} [{exists}]")

    print("\n--- Folder Health Status ---")
    health = get_folder_health_status()
    print(f"Base path exists: {health['base_path_exists']}")
    print(f"Fallback exists: {health['fallback_path_exists']}")
    print(f"All healthy: {health['all_healthy']}")

    if not health['all_healthy']:
        print("\nUnhealthy agents:")
        for agent, status in health['agents'].items():
            if not status['healthy']:
                print(f"  - {agent}: {status}")
