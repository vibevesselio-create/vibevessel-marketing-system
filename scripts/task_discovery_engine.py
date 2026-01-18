#!/usr/bin/env python3
"""Task Discovery Engine.

Automatically discovers actionable tasks from multiple sources:
- Notion Agent-Tasks (explicit tasks)
- Notion Issues+Questions (problems to solve)
- Services Database gaps (missing properties/relations)
- Codebase gaps (unlinked scripts, missing modules)
- Cross-system sync drift

Part of the Dynamic Discovery Workflow for self-optimizing task resolution.

Usage:
    python task_discovery_engine.py discover          # Discover all tasks
    python task_discovery_engine.py prioritize        # Show prioritized task list
    python task_discovery_engine.py next              # Get next task to work on
    python task_discovery_engine.py metrics           # Show performance metrics
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notion_client import Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# Database IDs
AGENT_TASKS_DB_ID = "136e7361-6c27-804b-85bc-f5b938b32bc6"
AGENT_PROJECTS_DB_ID = "17ee7361-6c27-8066-87dd-f45b3e0c6f4c"
ISSUES_QUESTIONS_DB_ID = "143e7361-6c27-80e1-afaa-dd8f5b23a430"
SERVICES_DB_ID = "26ce7361-6c27-8134-8909-ee25246dfdc4"


class TaskSource(Enum):
    """Source of discovered task."""

    AGENT_TASK = "agent_task"
    AGENT_PROJECT = "agent_project"
    ISSUE = "issue"
    SERVICES_GAP = "services_gap"
    CODEBASE_GAP = "codebase_gap"
    SYNC_DRIFT = "sync_drift"
    METRIC_TRIGGER = "metric_trigger"


class TaskPriority(Enum):
    """Task priority levels."""

    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class TaskType(Enum):
    """Type of work required."""

    CODE_IMPLEMENTATION = "code_implementation"
    DOCUMENTATION = "documentation"
    DATABASE_UPDATE = "database_update"
    API_INTEGRATION = "api_integration"
    REVIEW_AUDIT = "review_audit"
    BUG_FIX = "bug_fix"
    INFRASTRUCTURE = "infrastructure"


@dataclass
class DiscoveredTask:
    """A task discovered by the engine."""

    # Identity
    task_id: str
    title: str
    source: TaskSource

    # Classification
    task_type: TaskType = TaskType.CODE_IMPLEMENTATION
    priority: TaskPriority = TaskPriority.MEDIUM

    # Scoring
    impact_score: float = 0.5    # 0.0 to 1.0
    urgency_score: float = 0.5   # 0.0 to 1.0
    complexity_score: float = 0.5  # 0.0 to 1.0 (lower = simpler)
    priority_score: float = 0.0  # Computed

    # Dependencies
    dependencies_ready: bool = True
    blocked_by: List[str] = field(default_factory=list)

    # Context
    description: str = ""
    notion_url: Optional[str] = None
    related_files: List[str] = field(default_factory=list)
    related_services: List[str] = field(default_factory=list)

    # Metadata
    discovered_at: datetime = field(default_factory=datetime.now)
    due_date: Optional[datetime] = None

    def calculate_priority_score(self) -> float:
        """Calculate priority score.

        Score = (Impact × Urgency × Dependencies_Ready) / Complexity

        Higher score = higher priority.
        """
        deps_factor = 1.0 if self.dependencies_ready else 0.1

        # Avoid division by zero
        complexity = max(self.complexity_score, 0.1)

        self.priority_score = (self.impact_score * self.urgency_score * deps_factor) / complexity

        return self.priority_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "source": self.source.value,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "priority_score": self.priority_score,
            "impact_score": self.impact_score,
            "urgency_score": self.urgency_score,
            "complexity_score": self.complexity_score,
            "dependencies_ready": self.dependencies_ready,
            "blocked_by": self.blocked_by,
            "description": self.description,
            "notion_url": self.notion_url,
            "related_files": self.related_files,
            "related_services": self.related_services,
            "discovered_at": self.discovered_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
        }


@dataclass
class DiscoveryMetrics:
    """Metrics from task discovery."""

    discovery_time: datetime = field(default_factory=datetime.now)

    # Task counts by source
    agent_tasks_found: int = 0
    issues_found: int = 0
    services_gaps_found: int = 0
    codebase_gaps_found: int = 0
    sync_drifts_found: int = 0

    # Summary
    total_tasks: int = 0
    critical_tasks: int = 0
    blocked_tasks: int = 0
    ready_tasks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskDiscoveryEngine:
    """Discovers actionable tasks from multiple sources."""

    def __init__(self, notion_token: Optional[str] = None):
        """Initialize the discovery engine.

        Args:
            notion_token: Notion API token. Defaults to NOTION_TOKEN env var.
        """
        self.notion_token = notion_token or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
        if not self.notion_token:
            raise RuntimeError("NOTION_TOKEN environment variable required")

        self.notion = Client(auth=self.notion_token)
        self.metrics = DiscoveryMetrics()

    def discover_all(self) -> List[DiscoveredTask]:
        """Discover tasks from all sources.

        Returns:
            List of DiscoveredTask objects, prioritized
        """
        logger.info("Starting task discovery...")
        all_tasks = []

        # 1. Scan Agent-Tasks
        tasks = self._scan_agent_tasks()
        self.metrics.agent_tasks_found = len(tasks)
        all_tasks.extend(tasks)

        # 2. Scan Issues+Questions
        issues = self._scan_issues()
        self.metrics.issues_found = len(issues)
        all_tasks.extend(issues)

        # 3. Analyze Services gaps
        gaps = self._analyze_services_gaps()
        self.metrics.services_gaps_found = len(gaps)
        all_tasks.extend(gaps)

        # 4. Detect sync drift
        drifts = self._detect_sync_drift()
        self.metrics.sync_drifts_found = len(drifts)
        all_tasks.extend(drifts)

        # Calculate priority scores and sort
        for task in all_tasks:
            task.calculate_priority_score()

        all_tasks.sort(key=lambda t: t.priority_score, reverse=True)

        # Update metrics
        self.metrics.total_tasks = len(all_tasks)
        self.metrics.critical_tasks = sum(1 for t in all_tasks if t.priority == TaskPriority.CRITICAL)
        self.metrics.blocked_tasks = sum(1 for t in all_tasks if not t.dependencies_ready)
        self.metrics.ready_tasks = sum(1 for t in all_tasks if t.dependencies_ready)

        logger.info(f"Discovered {len(all_tasks)} tasks ({self.metrics.ready_tasks} ready)")
        return all_tasks

    def get_next_task(self) -> Optional[DiscoveredTask]:
        """Get the highest-priority task that's ready to work on.

        Returns:
            The next task to work on, or None if no tasks available
        """
        tasks = self.discover_all()

        for task in tasks:
            if task.dependencies_ready:
                return task

        return None

    def _scan_agent_tasks(self) -> List[DiscoveredTask]:
        """Scan Agent-Tasks for incomplete tasks."""
        tasks = []

        response = self.notion.databases.query(
            database_id=AGENT_TASKS_DB_ID,
            filter={
                "and": [
                    {
                        "property": "Status",
                        "status": {
                            "does_not_equal": "Completed"
                        }
                    },
                    {
                        "property": "Status",
                        "status": {
                            "does_not_equal": "Cancelled"
                        }
                    }
                ]
            },
            page_size=50,
        )

        for page in response.get("results", []):
            props = page.get("properties", {})
            title = self._get_title(props, "Task Name") or self._get_title(props, "Name")
            status = self._get_status(props)

            # Determine urgency based on status
            urgency = 0.5
            if status == "Blocked":
                urgency = 0.8
            elif status == "In Progress":
                urgency = 0.7
            elif status == "Not Started":
                urgency = 0.4

            task = DiscoveredTask(
                task_id=page.get("id", ""),
                title=title,
                source=TaskSource.AGENT_TASK,
                task_type=self._infer_task_type(title),
                urgency_score=urgency,
                notion_url=page.get("url"),
                description=self._get_rich_text(props, "Description"),
            )

            # Check if blocked
            if status == "Blocked":
                task.dependencies_ready = False

            tasks.append(task)

        return tasks

    def _scan_issues(self) -> List[DiscoveredTask]:
        """Scan Issues+Questions for open issues."""
        tasks = []

        try:
            response = self.notion.databases.query(
                database_id=ISSUES_QUESTIONS_DB_ID,
                filter={
                    "property": "Status",
                    "status": {
                        "does_not_equal": "Resolved"
                    }
                },
                page_size=50,
            )

            for page in response.get("results", []):
                props = page.get("properties", {})
                title = self._get_title(props)

                task = DiscoveredTask(
                    task_id=page.get("id", ""),
                    title=f"[Issue] {title}",
                    source=TaskSource.ISSUE,
                    task_type=TaskType.BUG_FIX,
                    priority=TaskPriority.HIGH,
                    impact_score=0.7,
                    urgency_score=0.8,
                    notion_url=page.get("url"),
                )

                tasks.append(task)

        except Exception as e:
            logger.warning(f"Failed to scan Issues database: {e}")

        return tasks

    def _analyze_services_gaps(self) -> List[DiscoveredTask]:
        """Analyze Services database for critical gaps."""
        tasks = []

        try:
            # Import the gap analyzer
            from scripts.services_gap_analyzer import ServicesGapAnalyzer

            analyzer = ServicesGapAnalyzer(self.notion_token)
            report = analyzer.analyze_all_services()

            # Create tasks for services with critical gaps
            for gap in report.service_gaps:
                if gap.has_critical_gaps:
                    task = DiscoveredTask(
                        task_id=f"services-gap-{gap.service_id}",
                        title=f"[Services Gap] Complete required properties for {gap.service_name}",
                        source=TaskSource.SERVICES_GAP,
                        task_type=TaskType.DATABASE_UPDATE,
                        priority=TaskPriority.MEDIUM,
                        impact_score=0.6,
                        urgency_score=0.4,
                        complexity_score=0.3,
                        notion_url=gap.service_url,
                        description=f"Missing: {', '.join(g.property_name for g in gap.missing_required)}",
                        related_services=[gap.service_name],
                    )
                    tasks.append(task)

        except Exception as e:
            logger.warning(f"Failed to analyze Services gaps: {e}")

        return tasks

    def _detect_sync_drift(self) -> List[DiscoveredTask]:
        """Detect sync drift between systems."""
        tasks = []

        # Check for Linear/GitHub sync issues
        mappings_file = REPO_ROOT / "var" / "state" / "linear_github_mappings.json"
        if mappings_file.exists():
            try:
                with open(mappings_file) as f:
                    mappings = json.load(f)

                stale_count = 0
                cutoff = datetime.now() - timedelta(days=7)

                for task_id, mapping in mappings.items():
                    last_synced = mapping.get("last_synced")
                    if last_synced:
                        synced_time = datetime.fromisoformat(last_synced)
                        if synced_time < cutoff:
                            stale_count += 1

                if stale_count > 5:
                    task = DiscoveredTask(
                        task_id="sync-drift-linear-github",
                        title=f"[Sync Drift] {stale_count} tasks have stale Linear/GitHub sync",
                        source=TaskSource.SYNC_DRIFT,
                        task_type=TaskType.INFRASTRUCTURE,
                        priority=TaskPriority.LOW,
                        impact_score=0.4,
                        urgency_score=0.3,
                        complexity_score=0.4,
                        description="Multiple tasks haven't synced to Linear/GitHub in over 7 days",
                    )
                    tasks.append(task)

            except Exception as e:
                logger.warning(f"Failed to check sync drift: {e}")

        return tasks

    def _get_title(self, props: Dict[str, Any], prop_name: str = "Name") -> str:
        """Extract title from properties."""
        name_prop = props.get(prop_name) or props.get("name") or props.get("Name")
        if not name_prop:
            return "Untitled"

        title = name_prop.get("title", [])
        if title:
            return title[0].get("plain_text", "Untitled")
        return "Untitled"

    def _get_status(self, props: Dict[str, Any]) -> str:
        """Get status from properties."""
        status_prop = props.get("Status")
        if not status_prop:
            return "Unknown"

        status = status_prop.get("status")
        if status:
            return status.get("name", "Unknown")
        return "Unknown"

    def _get_rich_text(self, props: Dict[str, Any], prop_name: str) -> str:
        """Get rich text content."""
        prop = props.get(prop_name)
        if not prop:
            return ""

        rich_text = prop.get("rich_text", [])
        if rich_text:
            return " ".join(item.get("plain_text", "") for item in rich_text)
        return ""

    def _infer_task_type(self, title: str) -> TaskType:
        """Infer task type from title."""
        title_lower = title.lower()

        if any(word in title_lower for word in ["implement", "create", "build", "add"]):
            return TaskType.CODE_IMPLEMENTATION
        elif any(word in title_lower for word in ["document", "docs", "readme"]):
            return TaskType.DOCUMENTATION
        elif any(word in title_lower for word in ["fix", "bug", "error", "issue"]):
            return TaskType.BUG_FIX
        elif any(word in title_lower for word in ["review", "audit", "check"]):
            return TaskType.REVIEW_AUDIT
        elif any(word in title_lower for word in ["api", "integration", "connect"]):
            return TaskType.API_INTEGRATION
        elif any(word in title_lower for word in ["database", "notion", "update"]):
            return TaskType.DATABASE_UPDATE

        return TaskType.CODE_IMPLEMENTATION


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Discover actionable tasks from multiple sources"
    )
    parser.add_argument(
        "command",
        choices=["discover", "prioritize", "next", "metrics", "json"],
        help="Command to run"
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="Maximum tasks to show"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path"
    )

    args = parser.parse_args()

    try:
        engine = TaskDiscoveryEngine()

        if args.command in ("discover", "prioritize"):
            tasks = engine.discover_all()

            print(f"\n{'='*60}")
            print(f"DISCOVERED TASKS ({len(tasks)} total, {engine.metrics.ready_tasks} ready)")
            print(f"{'='*60}\n")

            for i, task in enumerate(tasks[:args.limit], 1):
                ready = "✓" if task.dependencies_ready else "⊘"
                print(f"{i:2}. [{ready}] {task.title}")
                print(f"    Source: {task.source.value} | Priority: {task.priority_score:.2f}")
                if task.notion_url:
                    print(f"    URL: {task.notion_url}")
                print()

        elif args.command == "next":
            task = engine.get_next_task()

            if task:
                print(f"\n{'='*60}")
                print("NEXT TASK")
                print(f"{'='*60}\n")
                print(f"Title: {task.title}")
                print(f"Source: {task.source.value}")
                print(f"Type: {task.task_type.value}")
                print(f"Priority Score: {task.priority_score:.2f}")
                if task.description:
                    print(f"Description: {task.description}")
                if task.notion_url:
                    print(f"URL: {task.notion_url}")
            else:
                print("No tasks available!")

        elif args.command == "metrics":
            engine.discover_all()
            m = engine.metrics

            print(f"\n{'='*60}")
            print("DISCOVERY METRICS")
            print(f"{'='*60}\n")
            print(f"Total Tasks: {m.total_tasks}")
            print(f"  Agent Tasks: {m.agent_tasks_found}")
            print(f"  Issues: {m.issues_found}")
            print(f"  Services Gaps: {m.services_gaps_found}")
            print(f"  Sync Drifts: {m.sync_drifts_found}")
            print(f"\nStatus:")
            print(f"  Critical: {m.critical_tasks}")
            print(f"  Ready: {m.ready_tasks}")
            print(f"  Blocked: {m.blocked_tasks}")

        elif args.command == "json":
            tasks = engine.discover_all()

            output = {
                "metrics": engine.metrics.to_dict(),
                "tasks": [t.to_dict() for t in tasks[:args.limit]],
            }

            if args.output:
                with open(args.output, "w") as f:
                    json.dump(output, f, indent=2)
                print(f"JSON output saved to: {args.output}")
            else:
                print(json.dumps(output, indent=2))

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
