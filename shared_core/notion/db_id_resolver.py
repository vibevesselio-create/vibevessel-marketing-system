"""Notion database ID resolver.

Provides functions to resolve database IDs from environment variables or configuration.
This centralizes database ID management to avoid hardcoding IDs throughout the codebase.
"""

import os
from functools import lru_cache
from typing import Optional

from shared_core.notion.id_utils import normalize_notion_id


# Database ID environment variable names
ENV_AGENT_TASKS_DB = "NOTION_AGENT_TASKS_DB_ID"
ENV_AGENT_PROJECTS_DB = "NOTION_AGENT_PROJECTS_DB_ID"
ENV_EXECUTION_LOGS_DB = "NOTION_EXECUTION_LOGS_DB_ID"
ENV_ISSUES_QUESTIONS_DB = "NOTION_ISSUES_QUESTIONS_DB_ID"
ENV_PHOTO_LIBRARY_DB = "NOTION_PHOTO_LIBRARY_DB_ID"


# Default database IDs (from VibeVessel workspace)
# These are fallbacks if environment variables are not set
# Updated 2026-01-18 with correct IDs from workspace search
DEFAULT_DB_IDS = {
    "agent_tasks": "284e7361-6c27-8018-872a-eb14e82e0392",
    "agent_projects": "286e7361-6c27-81ff-a450-db2ecad4b0ba",
    "agent_workflows": "259e7361-6c27-8192-ae2e-e6d54b4198e1",
    "agent_functions": "256e7361-6c27-80c7-83fa-cd029ff49d2d",
    "execution_logs": "1410763b-ef53-80c3-b3d5-e81bbb1e2f8d",
    "issues_questions": "143e7361-6c27-80e1-afaa-dd8f5b23a430",
    "photo_library": "223e7361-6c27-8157-840c-000ba533ca02",
    "services": "26ce7361-6c27-8134-8909-ee25246dfdc4",
    "scripts": "26ce7361-6c27-8178-bc77-f43aff00eddf",
}


@lru_cache(maxsize=16)
def get_agent_tasks_db_id() -> str:
    """Get the Agent-Tasks database ID.

    Returns:
        Normalized Notion database ID

    Raises:
        RuntimeError: If database ID cannot be resolved
    """
    db_id = os.getenv(ENV_AGENT_TASKS_DB) or DEFAULT_DB_IDS.get("agent_tasks")
    if not db_id:
        raise RuntimeError(
            f"Agent-Tasks database ID not found. Set {ENV_AGENT_TASKS_DB} environment variable."
        )
    return normalize_notion_id(db_id)


@lru_cache(maxsize=16)
def get_agent_projects_db_id() -> str:
    """Get the Agent-Projects database ID.

    Returns:
        Normalized Notion database ID

    Raises:
        RuntimeError: If database ID cannot be resolved
    """
    db_id = os.getenv(ENV_AGENT_PROJECTS_DB) or DEFAULT_DB_IDS.get("agent_projects")
    if not db_id:
        raise RuntimeError(
            f"Agent-Projects database ID not found. Set {ENV_AGENT_PROJECTS_DB} environment variable."
        )
    return normalize_notion_id(db_id)


@lru_cache(maxsize=16)
def get_execution_logs_db_id() -> str:
    """Get the Execution-Logs database ID.

    Returns:
        Normalized Notion database ID

    Raises:
        RuntimeError: If database ID cannot be resolved
    """
    db_id = os.getenv(ENV_EXECUTION_LOGS_DB) or DEFAULT_DB_IDS.get("execution_logs")
    if not db_id:
        raise RuntimeError(
            f"Execution-Logs database ID not found. Set {ENV_EXECUTION_LOGS_DB} environment variable."
        )
    return normalize_notion_id(db_id)


@lru_cache(maxsize=16)
def get_issues_questions_db_id() -> str:
    """Get the Issues-Questions database ID.

    Returns:
        Normalized Notion database ID

    Raises:
        RuntimeError: If database ID cannot be resolved
    """
    db_id = os.getenv(ENV_ISSUES_QUESTIONS_DB) or DEFAULT_DB_IDS.get("issues_questions")
    if not db_id:
        raise RuntimeError(
            f"Issues-Questions database ID not found. Set {ENV_ISSUES_QUESTIONS_DB} environment variable."
        )
    return normalize_notion_id(db_id)


@lru_cache(maxsize=16)
def get_photo_library_db_id() -> str:
    """Get the Photo Library database ID.

    Note: This database is in the VibeVessel-Automation workspace and requires
    the ARCHIVE_WORKSPACE_TOKEN for access.

    Returns:
        Normalized Notion database ID

    Raises:
        RuntimeError: If database ID cannot be resolved
    """
    db_id = os.getenv(ENV_PHOTO_LIBRARY_DB) or DEFAULT_DB_IDS.get("photo_library")
    if not db_id:
        raise RuntimeError(
            f"Photo Library database ID not found. Set {ENV_PHOTO_LIBRARY_DB} environment variable."
        )
    return normalize_notion_id(db_id)


def get_database_id(db_name: str) -> Optional[str]:
    """Get a database ID by name.

    Args:
        db_name: Database name (e.g., "agent_tasks", "execution_logs")

    Returns:
        Database ID or None if not found
    """
    resolvers = {
        "agent_tasks": get_agent_tasks_db_id,
        "agent_projects": get_agent_projects_db_id,
        "execution_logs": get_execution_logs_db_id,
        "issues_questions": get_issues_questions_db_id,
        "photo_library": get_photo_library_db_id,
    }

    resolver = resolvers.get(db_name.lower().replace("-", "_").replace(" ", "_"))
    if resolver:
        try:
            return resolver()
        except RuntimeError:
            return None
    return None


def clear_cache() -> None:
    """Clear the database ID cache.

    Useful for testing or when environment variables change.
    """
    get_agent_tasks_db_id.cache_clear()
    get_agent_projects_db_id.cache_clear()
    get_execution_logs_db_id.cache_clear()
    get_issues_questions_db_id.cache_clear()
    get_photo_library_db_id.cache_clear()


__all__ = [
    "get_agent_tasks_db_id",
    "get_agent_projects_db_id",
    "get_execution_logs_db_id",
    "get_issues_questions_db_id",
    "get_photo_library_db_id",
    "get_database_id",
    "clear_cache",
]
