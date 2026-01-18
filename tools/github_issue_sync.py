"""GitHub issue synchronization client.

Provides GitHubIssueSync for creating and updating issues in GitHub repositories.
Uses GitHub's REST API.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from tools.issue_catalog_loader import IssueRecord

logger = logging.getLogger(__name__)


# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"


@dataclass
class GitHubConfig:
    """Configuration for GitHub API client."""

    token: str
    owner: str
    repo: str


class GitHubIssueSync:
    """Client for synchronizing issues with GitHub.

    Supports:
    - Creating new issues
    - Updating issue state (open/closed)
    - Adding labels and assignees
    - Querying existing issues
    """

    def __init__(
        self,
        config: GitHubConfig,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize the GitHub sync client.

        Args:
            config: GitHub API configuration
            dry_run: If True, don't make actual API calls
            logger: Optional logger instance
        """
        self.config = config
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(__name__)

        self._headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        self._base_url = f"{GITHUB_API_URL}/repos/{self.config.owner}/{self.config.repo}"

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an API request to GitHub."""
        url = f"{self._base_url}{endpoint}"

        if self.dry_run:
            self.logger.info(f"[DRY RUN] {method} {url}")
            return {}

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers,
                json=data,
                timeout=30,
            )
            response.raise_for_status()

            if response.status_code == 204:
                return {}

            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"GitHub API request failed: {e}")
            raise

    def sync(self, issues: List[IssueRecord]) -> Dict[str, Dict[str, Any]]:
        """Sync a list of issues to GitHub.

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
                    body=issue.description or issue.body,
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
        body: str = "",
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        milestone: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new issue in GitHub.

        Args:
            title: Issue title
            body: Issue body (markdown supported)
            labels: Optional label names
            assignees: Optional GitHub usernames to assign
            milestone: Optional milestone number

        Returns:
            Created issue data with id, number, url
        """
        data: Dict[str, Any] = {
            "title": title,
            "body": body,
        }

        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees
        if milestone:
            data["milestone"] = milestone

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would create issue: {title}")
            return {
                "id": "dry-run-id",
                "number": 1,
                "title": title,
                "url": f"https://github.com/{self.config.owner}/{self.config.repo}/issues/1",
                "state": "open",
            }

        result = self._request("POST", "/issues", data)

        self.logger.info(f"Created GitHub issue: #{result.get('number')} - {title}")

        return {
            "id": str(result.get("id")),
            "number": result.get("number"),
            "title": result.get("title"),
            "url": result.get("html_url"),
            "state": result.get("state"),
        }

    def update_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update an existing issue in GitHub.

        Args:
            issue_number: Issue number to update
            title: New title (optional)
            body: New body (optional)
            state: New state - "open" or "closed" (optional)
            labels: New labels (replaces existing)
            assignees: New assignees (replaces existing)

        Returns:
            Updated issue data
        """
        data: Dict[str, Any] = {}

        if title:
            data["title"] = title
        if body:
            data["body"] = body
        if state:
            data["state"] = state
        if labels is not None:
            data["labels"] = labels
        if assignees is not None:
            data["assignees"] = assignees

        if not data:
            self.logger.warning("No fields to update")
            return {}

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would update issue #{issue_number}: {data}")
            return {
                "number": issue_number,
                "state": state or "open",
                "url": f"https://github.com/{self.config.owner}/{self.config.repo}/issues/{issue_number}",
            }

        result = self._request("PATCH", f"/issues/{issue_number}", data)

        self.logger.info(f"Updated GitHub issue: #{issue_number}")

        return {
            "id": str(result.get("id")),
            "number": result.get("number"),
            "title": result.get("title"),
            "url": result.get("html_url"),
            "state": result.get("state"),
        }

    def close_issue(self, issue_number: int) -> Dict[str, Any]:
        """Close an issue.

        Args:
            issue_number: Issue number to close

        Returns:
            Updated issue data
        """
        return self.update_issue(issue_number, state="closed")

    def reopen_issue(self, issue_number: int) -> Dict[str, Any]:
        """Reopen a closed issue.

        Args:
            issue_number: Issue number to reopen

        Returns:
            Updated issue data
        """
        return self.update_issue(issue_number, state="open")

    def get_issue(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """Get an issue by number.

        Args:
            issue_number: Issue number

        Returns:
            Issue data or None if not found
        """
        try:
            return self._request("GET", f"/issues/{issue_number}")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def list_issues(
        self,
        state: str = "open",
        labels: Optional[List[str]] = None,
        per_page: int = 30,
    ) -> List[Dict[str, Any]]:
        """List issues in the repository.

        Args:
            state: Filter by state - "open", "closed", or "all"
            labels: Filter by labels (comma-separated in API)
            per_page: Number of issues per page

        Returns:
            List of issue data
        """
        endpoint = f"/issues?state={state}&per_page={per_page}"

        if labels:
            endpoint += f"&labels={','.join(labels)}"

        return self._request("GET", endpoint)

    def add_comment(self, issue_number: int, body: str) -> Dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_number: Issue number
            body: Comment body (markdown supported)

        Returns:
            Created comment data
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would add comment to issue #{issue_number}")
            return {}

        return self._request(
            "POST",
            f"/issues/{issue_number}/comments",
            {"body": body}
        )


def build_client_from_env(
    repo: Optional[str] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> GitHubIssueSync:
    """Build GitHubIssueSync from environment variables.

    Required env vars:
        GITHUB_TOKEN: GitHub personal access token or app token

    Args:
        repo: Repository in "owner/repo" format. If not provided, uses
              GITHUB_REPO or ISSUE_SYNC_GITHUB_REPO env var.
        dry_run: If True, don't make actual API calls
        logger: Optional logger instance
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN environment variable required")

    if not repo:
        repo = os.getenv("GITHUB_REPO") or os.getenv("ISSUE_SYNC_GITHUB_REPO")

    if not repo:
        raise RuntimeError(
            "Repository not specified. Provide repo argument or set "
            "GITHUB_REPO environment variable"
        )

    if "/" not in repo:
        raise RuntimeError(f"Invalid repo format: {repo}. Expected 'owner/repo'")

    owner, repo_name = repo.split("/", 1)

    config = GitHubConfig(
        token=token,
        owner=owner,
        repo=repo_name,
    )

    return GitHubIssueSync(config=config, dry_run=dry_run, logger=logger)


__all__ = ["GitHubIssueSync", "GitHubConfig", "build_client_from_env"]
