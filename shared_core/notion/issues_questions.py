#!/usr/bin/env python3
"""
Issues+Questions Database Writer

Creates and manages entries in the Issues+Questions database with duplicate prevention.
Implements deduplication by checking for existing issues with the same name before creation.

Database ID: 229e73616c27808ebf06c202b10b5166
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

try:
    from notion_client import Client  # type: ignore[import]
except ImportError:
    Client = None  # type: ignore[assignment]

# Logger
logger = logging.getLogger(__name__)

# Database ID - resolved via environment or default
ISSUES_QUESTIONS_DB_ID = os.getenv("ISSUES_QUESTIONS_DB_ID") or "229e73616c27808ebf06c202b10b5166"

# Module-level tracking to prevent duplicate creation in same session
_CREATED_ISSUES_THIS_SESSION: Set[str] = set()


def _get_notion_client() -> Optional[Any]:
    """Get Notion client from environment, if available."""
    if Client is None:
        return None

    api_key = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
    if not api_key:
        try:
            from shared_core.notion.token_manager import get_notion_token
            api_key = get_notion_token()
        except ImportError:
            pass

    if not api_key:
        return None

    try:
        return Client(auth=api_key)
    except Exception:
        return None


def _check_existing_issue(client: Any, name: str) -> Optional[str]:
    """
    Check if an issue with the same name already exists.

    Returns:
        Page ID if exists, None otherwise
    """
    try:
        results = client.databases.query(
            database_id=ISSUES_QUESTIONS_DB_ID,
            filter={
                "and": [
                    {"property": "Name", "title": {"equals": name}},
                    {"or": [
                        {"property": "Status", "status": {"equals": "Unreported"}},
                        {"property": "Status", "status": {"equals": "Open"}},
                        {"property": "Status", "status": {"equals": "In Progress"}},
                    ]}
                ]
            },
            page_size=1
        )

        if results.get("results"):
            return results["results"][0].get("id")
        return None
    except Exception as e:
        logger.warning(f"Failed to check for existing issue: {e}")
        return None


def create_issue_or_question(
    name: str,
    type: Optional[List[str]] = None,
    status: str = "Unreported",
    priority: str = "Medium",
    component: Optional[str] = None,
    blocked: bool = False,
    description: Optional[str] = None,
    related_task_id: Optional[str] = None,
    evidence_links: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    skip_if_exists: bool = True,
) -> Optional[str]:
    """
    Create an Issues+Questions entry in Notion with duplicate prevention.

    Args:
        name: Issue title
        type: Issue type (list of values like "Internal Issue", "Question", etc.)
        status: Status (Unreported, Open, In Progress, Resolved, Closed)
        priority: Priority (Low, Medium, High, Critical)
        component: Component/module affected
        blocked: Whether this is a blocker
        description: Detailed description
        related_task_id: Related Agent-Task page ID
        evidence_links: List of evidence URLs
        tags: List of tags
        skip_if_exists: If True, skip creation if issue with same name exists (default: True)

    Returns:
        Page ID if created (or existing page ID if skipped), None on error
    """
    global _CREATED_ISSUES_THIS_SESSION

    client = _get_notion_client()
    if not client:
        logger.error("Notion client not available")
        return None

    # Session-level deduplication
    if name in _CREATED_ISSUES_THIS_SESSION:
        logger.debug(f"Skipping duplicate issue creation (session-level): {name}")
        return None

    # Database-level deduplication
    if skip_if_exists:
        existing_id = _check_existing_issue(client, name)
        if existing_id:
            logger.info(f"Issue already exists, skipping creation: {name} (ID: {existing_id})")
            _CREATED_ISSUES_THIS_SESSION.add(name)
            return existing_id

    # Build properties
    properties: Dict[str, Any] = {
        "Name": {
            "title": [{"text": {"content": name}}]
        },
    }

    # Status
    if status:
        properties["Status"] = {
            "status": {"name": status}
        }

    # Priority
    if priority:
        properties["Priority"] = {
            "select": {"name": priority}
        }

    # Type (multi-select)
    if type:
        properties["Type"] = {
            "multi_select": [{"name": t} for t in type]
        }

    # Description
    if description:
        # Truncate if too long (Notion limit is 2000 chars for rich_text)
        desc_text = description[:1997] + "..." if len(description) > 2000 else description
        properties["Description"] = {
            "rich_text": [{"text": {"content": desc_text}}]
        }

    # Component
    if component:
        properties["Component"] = {
            "select": {"name": component}
        }

    # Tags (multi-select)
    if tags:
        properties["Tags"] = {
            "multi_select": [{"name": tag} for tag in tags]
        }

    # Related task (relation)
    if related_task_id:
        properties["Agent-Tasks"] = {
            "relation": [{"id": related_task_id}]
        }

    try:
        response = client.pages.create(
            parent={"database_id": ISSUES_QUESTIONS_DB_ID},
            properties=properties
        )
        page_id = response.get("id")
        logger.info(f"Created issue: {name} (ID: {page_id})")
        _CREATED_ISSUES_THIS_SESSION.add(name)
        return page_id
    except Exception as e:
        logger.error(f"Failed to create issue: {e}")
        return None


def archive_issues_by_name(
    name_contains: str,
    status_to_set: str = "Resolved",
    keep_first: int = 1,
) -> int:
    """
    Archive/resolve duplicate issues matching a name pattern.

    Keeps the first N issues and resolves the rest.

    Args:
        name_contains: Substring to match in issue name
        status_to_set: Status to set for resolved issues (default: "Resolved")
        keep_first: Number of issues to keep (default: 1)

    Returns:
        Number of issues archived
    """
    client = _get_notion_client()
    if not client:
        return 0

    try:
        # Find all matching issues
        results = client.databases.query(
            database_id=ISSUES_QUESTIONS_DB_ID,
            filter={
                "and": [
                    {"property": "Name", "title": {"contains": name_contains}},
                    {"or": [
                        {"property": "Status", "status": {"equals": "Unreported"}},
                        {"property": "Status", "status": {"equals": "Open"}},
                    ]}
                ]
            },
            sorts=[{"timestamp": "created_time", "direction": "ascending"}]
        )

        issues = results.get("results", [])
        if len(issues) <= keep_first:
            return 0

        # Keep first N, archive the rest
        to_archive = issues[keep_first:]
        archived = 0

        for issue in to_archive:
            try:
                client.pages.update(
                    page_id=issue["id"],
                    properties={
                        "Status": {"status": {"name": status_to_set}}
                    }
                )
                archived += 1
            except Exception as e:
                logger.warning(f"Failed to archive issue {issue['id']}: {e}")

        logger.info(f"Archived {archived} duplicate issues matching '{name_contains}'")
        return archived
    except Exception as e:
        logger.error(f"Failed to archive issues: {e}")
        return 0
