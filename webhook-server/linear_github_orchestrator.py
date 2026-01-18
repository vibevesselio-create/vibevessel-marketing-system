#!/usr/bin/env python3
"""
Linear/GitHub Issue-Tracking Orchestrator

Handles bidirectional synchronization between Notion Agent-Tasks, Linear issues, and GitHub issues.
Linear serves as the canonical issue tracker.

Architecture:
- Notion Webhook → Orchestrator → Linear API
                ↓
            GitHub API
                ↓
            Notion API (update Agent-Tasks)

Author: Cursor MM1 Agent
Date: 2025-12-29
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import json

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests
from notion_client import Client

from tools.linear_sync import LinearSyncClient, build_client_from_env as build_linear_client
from tools.github_issue_sync import GitHubIssueSync, build_client_from_env as build_github_client
from shared_core.notion.db_id_resolver import get_agent_tasks_db_id

# Configure logging
logger = logging.getLogger("linear_github_orchestrator")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    )


# State machine mappings
NOTION_TO_LINEAR_STATUS = {
    "Not Started": "Todo",
    "In Progress": "In Progress",
    "Blocked": "Canceled",
    "Completed": "Done",
    "Ready": "Todo",
    "Paused": "In Progress",
}

LINEAR_TO_NOTION_STATUS = {v: k for k, v in NOTION_TO_LINEAR_STATUS.items()}

NOTION_TO_GITHUB_STATE = {
    "Not Started": "open",
    "In Progress": "open",
    "Blocked": "open",
    "Completed": "closed",
    "Ready": "open",
    "Paused": "open",
}

GITHUB_TO_NOTION_STATUS = {
    "open": "In Progress",
    "closed": "Completed",
}


@dataclass
class IssueMapping:
    """Tracks mapping between Notion Task, Linear Issue, and GitHub Issue."""
    notion_task_id: str
    linear_issue_id: Optional[str] = None
    linear_issue_url: Optional[str] = None
    linear_issue_identifier: Optional[str] = None
    github_issue_id: Optional[str] = None
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None
    last_synced: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if self.last_synced:
            data["last_synced"] = self.last_synced.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IssueMapping":
        """Create from dictionary."""
        if "last_synced" in data and data["last_synced"]:
            data["last_synced"] = datetime.fromisoformat(data["last_synced"])
        return cls(**data)


class LinearGitHubOrchestrator:
    """
    Orchestrates bidirectional synchronization between Notion, Linear, and GitHub.
    """

    def __init__(
        self,
        notion_token: Optional[str] = None,
        linear_client: Optional[LinearSyncClient] = None,
        github_client: Optional[GitHubIssueSync] = None,
        mapping_file: Optional[Path] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or logging.getLogger("linear_github_orchestrator")
        self.notion_token = notion_token or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
        if not self.notion_token:
            raise RuntimeError("NOTION_TOKEN or NOTION_API_TOKEN environment variable required")
        
        self.notion = Client(auth=self.notion_token)
        self.agent_tasks_db_id = get_agent_tasks_db_id()
        
        self.linear_client = linear_client or build_linear_client(dry_run=False, logger=self.logger)
        self.github_client = github_client or build_github_client(
            repo=os.getenv("GITHUB_REPO") or os.getenv("ISSUE_SYNC_GITHUB_REPO", ""),
            dry_run=False,
            logger=self.logger
        )
        
        # Load issue mappings
        self.mapping_file = mapping_file or Path(REPO_ROOT) / "var" / "state" / "linear_github_mappings.json"
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        self.mappings: Dict[str, IssueMapping] = self._load_mappings()

    def _load_mappings(self) -> Dict[str, IssueMapping]:
        """Load issue mappings from file."""
        if not self.mapping_file.exists():
            return {}
        
        try:
            with self.mapping_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                task_id: IssueMapping.from_dict(mapping_data)
                for task_id, mapping_data in data.items()
            }
        except Exception as e:
            self.logger.error(f"Failed to load mappings: {e}")
            return {}

    def _save_mappings(self) -> None:
        """Save issue mappings to file."""
        try:
            data = {
                task_id: mapping.to_dict()
                for task_id, mapping in self.mappings.items()
            }
            with self.mapping_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
        except Exception as e:
            self.logger.error(f"Failed to save mappings: {e}")

    def handle_notion_webhook(self, webhook_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle webhook from Notion when Agent-Task is created or updated.
        
        Args:
            webhook_payload: Notion webhook payload
            
        Returns:
            Result dictionary with status and details
        """
        try:
            event_type = webhook_payload.get("type")
            entity = webhook_payload.get("entity", {})
            entity_id = entity.get("id")
            
            if not entity_id or entity.get("type") != "page":
                return {"status": "ignored", "reason": "Not a page event"}
            
            # Fetch full page data
            try:
                page = self.notion.pages.retrieve(entity_id)
            except Exception as e:
                self.logger.error(f"Failed to retrieve Notion page {entity_id}: {e}")
                return {"status": "error", "error": str(e)}
            
            # Check if this is an Agent-Task
            parent = page.get("parent", {})
            if parent.get("database_id") != self.agent_tasks_db_id:
                return {"status": "ignored", "reason": "Not an Agent-Task"}
            
            # Extract task properties
            properties = page.get("properties", {})
            task_name = self._extract_title(properties.get("Task Name") or properties.get("Name"))
            status = self._extract_status(properties.get("Status"))
            
            # Get or create mapping
            mapping = self.mappings.get(entity_id)
            if not mapping:
                mapping = IssueMapping(notion_task_id=entity_id)
                self.mappings[entity_id] = mapping
            
            # Handle different event types
            if event_type == "page.created":
                return self._handle_task_created(page, mapping, task_name, status)
            elif event_type == "page.updated":
                return self._handle_task_updated(page, mapping, task_name, status)
            else:
                return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}
                
        except Exception as e:
            self.logger.error(f"Error handling Notion webhook: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def _handle_task_created(
        self,
        page: Dict[str, Any],
        mapping: IssueMapping,
        task_name: str,
        status: str,
    ) -> Dict[str, Any]:
        """Handle creation of new Agent-Task."""
        self.logger.info(f"Creating issues for new task: {task_name}")
        
        results = {}
        
        # Create Linear issue
        if not mapping.linear_issue_id:
            try:
                from tools.issue_catalog_loader import IssueRecord
                
                # Create IssueRecord from Notion task
                issue_record = IssueRecord(
                    id=mapping.notion_task_id,
                    title=task_name,
                    description=self._extract_description(page.get("properties", {})),
                )
                
                linear_result = self.linear_client.sync([issue_record])
                if mapping.notion_task_id in linear_result:
                    linear_data = linear_result[mapping.notion_task_id]
                    mapping.linear_issue_id = linear_data.get("id")
                    mapping.linear_issue_url = linear_data.get("url")
                    mapping.linear_issue_identifier = linear_data.get("identifier")
                    results["linear"] = {"status": "created", "url": mapping.linear_issue_url}
            except Exception as e:
                self.logger.error(f"Failed to create Linear issue: {e}")
                results["linear"] = {"status": "error", "error": str(e)}
        
        # Create GitHub issue
        if not mapping.github_issue_id:
            try:
                from tools.issue_catalog_loader import IssueRecord
                
                issue_record = IssueRecord(
                    id=mapping.notion_task_id,
                    title=task_name,
                    description=self._extract_description(page.get("properties", {})),
                )
                
                github_result = self.github_client.sync([issue_record])
                if mapping.notion_task_id in github_result:
                    github_data = github_result[mapping.notion_task_id]
                    mapping.github_issue_id = github_data.get("id")
                    mapping.github_issue_number = github_data.get("number")
                    mapping.github_issue_url = github_data.get("url")
                    results["github"] = {"status": "created", "url": mapping.github_issue_url}
            except Exception as e:
                self.logger.error(f"Failed to create GitHub issue: {e}")
                results["github"] = {"status": "error", "error": str(e)}
        
        # Update Notion task with issue IDs and URLs
        if mapping.linear_issue_id or mapping.github_issue_id:
            self._update_notion_task_properties(mapping)
        
        mapping.last_synced = datetime.now(timezone.utc)
        self._save_mappings()
        
        return {"status": "success", "results": results}

    def _handle_task_updated(
        self,
        page: Dict[str, Any],
        mapping: IssueMapping,
        task_name: str,
        status: str,
    ) -> Dict[str, Any]:
        """Handle update to existing Agent-Task."""
        if not mapping.linear_issue_id and not mapping.github_issue_id:
            # Task doesn't have issues yet, treat as creation
            return self._handle_task_created(page, mapping, task_name, status)

        results = {}

        # Update Linear issue status
        if mapping.linear_issue_id:
            try:
                linear_status = NOTION_TO_LINEAR_STATUS.get(status, "Todo")
                update_result = self.linear_client.update_issue(
                    issue_id=mapping.linear_issue_id,
                    state_name=linear_status,
                )
                results["linear"] = {
                    "status": "updated",
                    "new_state": update_result.get("state"),
                    "url": update_result.get("url"),
                }
                self.logger.info(f"Updated Linear issue {mapping.linear_issue_id} to state: {linear_status}")
            except Exception as e:
                self.logger.error(f"Failed to update Linear issue: {e}")
                results["linear"] = {"status": "error", "error": str(e)}

        # Update GitHub issue state
        if mapping.github_issue_number:
            try:
                github_state = NOTION_TO_GITHUB_STATE.get(status, "open")
                update_result = self.github_client.update_issue(
                    issue_number=mapping.github_issue_number,
                    state=github_state,
                )
                results["github"] = {
                    "status": "updated",
                    "new_state": update_result.get("state"),
                    "url": update_result.get("url"),
                }
                self.logger.info(f"Updated GitHub issue #{mapping.github_issue_number} to state: {github_state}")
            except Exception as e:
                self.logger.error(f"Failed to update GitHub issue: {e}")
                results["github"] = {"status": "error", "error": str(e)}

        mapping.last_synced = datetime.now(timezone.utc)
        self._save_mappings()

        return {"status": "success", "results": results}

    def _update_notion_task_properties(self, mapping: IssueMapping) -> None:
        """Update Notion Agent-Task with Linear and GitHub issue IDs/URLs.

        Note: The Agent-Tasks database may not have Linear/GitHub URL properties yet.
        Properties will be created on first sync, or you can add them manually:
        - Linear Issue ID (rich_text)
        - Linear Issue URL (url)
        - GitHub Issue URL (url)
        """
        try:
            # First, get the database schema to check which properties exist
            try:
                db = self.notion.databases.retrieve(self.agent_tasks_db_id)
                existing_props = set(db.get("properties", {}).keys())
            except Exception as e:
                self.logger.warning(f"Could not retrieve database schema: {e}")
                existing_props = set()

            properties = {}
            missing_props = []

            if mapping.linear_issue_id:
                prop_name = "Linear Issue ID"
                if prop_name in existing_props:
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": mapping.linear_issue_identifier or mapping.linear_issue_id}}]
                    }
                else:
                    missing_props.append(prop_name)

            if mapping.linear_issue_url:
                prop_name = "Linear Issue URL"
                if prop_name in existing_props:
                    properties[prop_name] = {
                        "url": mapping.linear_issue_url
                    }
                else:
                    missing_props.append(prop_name)

            if mapping.github_issue_url:
                prop_name = "GitHub Issue URL"
                if prop_name in existing_props:
                    properties[prop_name] = {
                        "url": mapping.github_issue_url
                    }
                else:
                    missing_props.append(prop_name)

            if missing_props:
                self.logger.warning(
                    f"Missing properties in Agent-Tasks database: {missing_props}. "
                    f"Add these properties to enable issue tracking links."
                )

            if properties:
                self.notion.pages.update(mapping.notion_task_id, properties=properties)
                self.logger.info(f"Updated Notion task {mapping.notion_task_id} with issue links")
            else:
                self.logger.info(
                    f"No properties updated for task {mapping.notion_task_id}. "
                    f"Issue URLs stored in local mappings only."
                )
        except Exception as e:
            self.logger.error(f"Failed to update Notion task properties: {e}")

    def _extract_title(self, title_prop: Optional[Dict[str, Any]]) -> str:
        """Extract title from Notion title property."""
        if not title_prop:
            return ""
        title_array = title_prop.get("title", [])
        if title_array:
            return title_array[0].get("plain_text", "")
        return ""

    def _extract_status(self, status_prop: Optional[Dict[str, Any]]) -> str:
        """Extract status from Notion status property."""
        if not status_prop:
            return "Not Started"
        status_obj = status_prop.get("status")
        if not status_obj:
            return "Not Started"
        return status_obj.get("name", "Not Started")

    def _extract_description(self, properties: Dict[str, Any]) -> str:
        """Extract description from Notion properties."""
        desc_prop = properties.get("Description") or properties.get("description")
        if not desc_prop:
            return ""
        rich_text = desc_prop.get("rich_text", [])
        if rich_text:
            return " ".join(item.get("plain_text", "") for item in rich_text)
        return ""


def create_orchestrator_from_env(
    mapping_file: Optional[Path] = None,
    logger: Optional[logging.Logger] = None,
) -> LinearGitHubOrchestrator:
    """Create orchestrator instance from environment variables."""
    return LinearGitHubOrchestrator(
        notion_token=None,  # Will use env var
        linear_client=None,  # Will be built from env
        github_client=None,  # Will be built from env
        mapping_file=mapping_file,
        logger=logger,
    )


__all__ = ["LinearGitHubOrchestrator", "IssueMapping", "create_orchestrator_from_env"]














