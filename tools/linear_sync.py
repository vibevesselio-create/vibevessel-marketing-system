"""Linear issue synchronization client.

Provides LinearSyncClient for creating and updating issues in Linear.
Uses Linear's GraphQL API.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from tools.issue_catalog_loader import IssueRecord

logger = logging.getLogger(__name__)


# Linear GraphQL endpoint
LINEAR_API_URL = "https://api.linear.app/graphql"


@dataclass
class LinearConfig:
    """Configuration for Linear API client."""

    api_key: str
    team_id: str
    default_project_id: Optional[str] = None


class LinearSyncClient:
    """Client for synchronizing issues with Linear.

    Supports:
    - Creating new issues
    - Updating issue status
    - Querying existing issues
    """

    # State name to ID mapping (populated on first use)
    _state_cache: Dict[str, str] = {}

    def __init__(
        self,
        config: LinearConfig,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the Linear sync client.

        Args:
            config: Linear API configuration
            dry_run: If True, don't make actual API calls
            logger: Optional logger instance
        """
        self.config = config
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(__name__)

        self._headers = {
            "Authorization": self.config.api_key,
            "Content-Type": "application/json",
        }

    def _execute_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query against Linear API."""
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would execute query: {query[:100]}...")
            return {}

        try:
            response = requests.post(
                LINEAR_API_URL,
                headers=self._headers,
                json={"query": query, "variables": variables or {}},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                errors = data["errors"]
                self.logger.error(f"Linear API errors: {errors}")
                raise RuntimeError(f"Linear API error: {errors[0].get('message')}")

            return data.get("data", {})
        except requests.RequestException as e:
            self.logger.error(f"Linear API request failed: {e}")
            raise

    def get_workflow_states(self) -> Dict[str, str]:
        """Get workflow states for the team.

        Returns:
            Dict mapping state name to state ID
        """
        if self._state_cache:
            return self._state_cache

        query = """
        query WorkflowStates($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                    }
                }
            }
        }
        """

        data = self._execute_query(query, {"teamId": self.config.team_id})
        states = data.get("team", {}).get("states", {}).get("nodes", [])

        self._state_cache = {state["name"]: state["id"] for state in states}
        return self._state_cache

    def sync(self, issues: List[IssueRecord]) -> Dict[str, Dict[str, Any]]:
        """Sync a list of issues to Linear.

        Args:
            issues: List of IssueRecord objects to sync

        Returns:
            Dict mapping source ID to created issue data
        """
        results = {}

        for issue in issues:
            try:
                result = self.create_issue(
                    title=issue.title,
                    description=issue.description or issue.body,
                    priority=self._map_priority(issue.priority),
                    labels=issue.labels,
                )
                results[issue.id] = result
            except Exception as e:
                self.logger.error(f"Failed to sync issue {issue.id}: {e}")
                results[issue.id] = {"error": str(e)}

        return results

    def create_issue(
        self,
        title: str,
        description: str = "",
        priority: int = 0,
        labels: Optional[List[str]] = None,
        state_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new issue in Linear.

        Args:
            title: Issue title
            description: Issue description (markdown supported)
            priority: Priority level (0=none, 1=urgent, 2=high, 3=medium, 4=low)
            labels: Optional label names
            state_name: Optional workflow state name

        Returns:
            Created issue data with id, identifier, url
        """
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                }
            }
        }
        """

        input_data: Dict[str, Any] = {
            "teamId": self.config.team_id,
            "title": title,
            "description": description,
            "priority": priority,
        }

        if self.config.default_project_id:
            input_data["projectId"] = self.config.default_project_id

        if state_name:
            states = self.get_workflow_states()
            if state_name in states:
                input_data["stateId"] = states[state_name]

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would create issue: {title}")
            return {
                "id": "dry-run-id",
                "identifier": "DRY-1",
                "title": title,
                "url": "https://linear.app/dry-run",
            }

        data = self._execute_query(mutation, {"input": input_data})
        result = data.get("issueCreate", {})

        if not result.get("success"):
            raise RuntimeError("Failed to create Linear issue")

        issue = result.get("issue", {})
        self.logger.info(f"Created Linear issue: {issue.get('identifier')} - {title}")

        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "state": issue.get("state", {}).get("name"),
        }

    def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        state_name: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update an existing issue in Linear.

        Args:
            issue_id: Linear issue ID
            title: New title (optional)
            description: New description (optional)
            state_name: New workflow state name (optional)
            priority: New priority level (optional)

        Returns:
            Updated issue data
        """
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                success
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        name
                    }
                }
            }
        }
        """

        input_data: Dict[str, Any] = {}

        if title:
            input_data["title"] = title
        if description:
            input_data["description"] = description
        if priority is not None:
            input_data["priority"] = priority
        if state_name:
            states = self.get_workflow_states()
            if state_name in states:
                input_data["stateId"] = states[state_name]
            else:
                self.logger.warning(f"Unknown state: {state_name}")

        if not input_data:
            self.logger.warning("No fields to update")
            return {}

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would update issue {issue_id}: {input_data}")
            return {"id": issue_id, "state": state_name}

        data = self._execute_query(mutation, {"id": issue_id, "input": input_data})
        result = data.get("issueUpdate", {})

        if not result.get("success"):
            raise RuntimeError(f"Failed to update Linear issue {issue_id}")

        issue = result.get("issue", {})
        self.logger.info(f"Updated Linear issue: {issue.get('identifier')}")

        return {
            "id": issue.get("id"),
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "url": issue.get("url"),
            "state": issue.get("state", {}).get("name"),
        }

    def get_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Get an issue by ID.

        Args:
            issue_id: Linear issue ID

        Returns:
            Issue data or None if not found
        """
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                url
                state {
                    name
                    type
                }
                priority
                createdAt
                updatedAt
            }
        }
        """

        data = self._execute_query(query, {"id": issue_id})
        return data.get("issue")

    def _map_priority(self, priority: Optional[str]) -> int:
        """Map priority string to Linear priority number."""
        mapping = {
            "urgent": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
        }
        if priority:
            return mapping.get(priority.lower(), 0)
        return 0


def build_client_from_env(
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> LinearSyncClient:
    """Build LinearSyncClient from environment variables.

    Required env vars:
        LINEAR_API_KEY: Linear API key
        LINEAR_TEAM_ID: Team ID to create issues in

    Optional env vars:
        LINEAR_PROJECT_ID: Default project ID
    """
    api_key = os.getenv("LINEAR_API_KEY")
    if not api_key:
        raise RuntimeError("LINEAR_API_KEY environment variable required")

    team_id = os.getenv("LINEAR_TEAM_ID")
    if not team_id:
        raise RuntimeError("LINEAR_TEAM_ID environment variable required")

    config = LinearConfig(
        api_key=api_key,
        team_id=team_id,
        default_project_id=os.getenv("LINEAR_PROJECT_ID"),
    )

    return LinearSyncClient(config=config, dry_run=dry_run, logger=logger)


__all__ = ["LinearSyncClient", "LinearConfig", "build_client_from_env"]
