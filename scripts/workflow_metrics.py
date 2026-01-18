#!/usr/bin/env python3
"""Workflow Performance Metrics Framework.

Collects, stores, and analyzes metrics for the Dynamic Discovery Workflow system.
Enables performance review, trend analysis, and self-optimization triggers.

Usage:
    python workflow_metrics.py collect           # Collect current metrics
    python workflow_metrics.py report            # Generate metrics report
    python workflow_metrics.py trends            # Show trend analysis
    python workflow_metrics.py optimize          # Suggest optimizations
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# Metrics storage
METRICS_DIR = REPO_ROOT / "var" / "metrics"
METRICS_FILE = METRICS_DIR / "workflow_metrics.json"


@dataclass
class TaskMetrics:
    """Metrics for task completion."""

    tasks_discovered: int = 0
    tasks_completed: int = 0
    tasks_blocked: int = 0
    tasks_created: int = 0

    avg_resolution_time_hours: float = 0.0
    completion_rate: float = 0.0

    # By source
    by_source: Dict[str, int] = field(default_factory=dict)

    # By type
    by_type: Dict[str, int] = field(default_factory=dict)


@dataclass
class GapMetrics:
    """Metrics for gap closure."""

    services_gaps_identified: int = 0
    services_gaps_resolved: int = 0
    scripts_linked: int = 0
    relations_created: int = 0

    gap_closure_rate: float = 0.0


@dataclass
class QualityMetrics:
    """Metrics for output quality."""

    validation_pass_rate: float = 0.0
    recurrence_rate: float = 0.0
    documentation_coverage: float = 0.0
    test_coverage: float = 0.0


@dataclass
class SystemHealthMetrics:
    """Metrics for system health."""

    sync_accuracy: float = 0.0
    api_success_rate: float = 0.0
    error_count: int = 0
    warning_count: int = 0

    # API-specific
    notion_api_calls: int = 0
    github_api_calls: int = 0
    linear_api_calls: int = 0


@dataclass
class WorkflowMetricsSnapshot:
    """Complete metrics snapshot at a point in time."""

    timestamp: datetime = field(default_factory=datetime.now)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    tasks: TaskMetrics = field(default_factory=TaskMetrics)
    gaps: GapMetrics = field(default_factory=GapMetrics)
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    system: SystemHealthMetrics = field(default_factory=SystemHealthMetrics)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "tasks": asdict(self.tasks),
            "gaps": asdict(self.gaps),
            "quality": asdict(self.quality),
            "system": asdict(self.system),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowMetricsSnapshot":
        snapshot = cls()
        snapshot.timestamp = datetime.fromisoformat(data["timestamp"])
        if data.get("period_start"):
            snapshot.period_start = datetime.fromisoformat(data["period_start"])
        if data.get("period_end"):
            snapshot.period_end = datetime.fromisoformat(data["period_end"])

        if data.get("tasks"):
            snapshot.tasks = TaskMetrics(**data["tasks"])
        if data.get("gaps"):
            snapshot.gaps = GapMetrics(**data["gaps"])
        if data.get("quality"):
            snapshot.quality = QualityMetrics(**data["quality"])
        if data.get("system"):
            snapshot.system = SystemHealthMetrics(**data["system"])

        return snapshot


@dataclass
class OptimizationSuggestion:
    """A suggested optimization based on metrics."""

    trigger: str
    metric_name: str
    current_value: float
    threshold: float
    suggestion: str
    priority: str  # "high", "medium", "low"
    action_type: str  # "automation", "decomposition", "review", "escalate"


class WorkflowMetricsCollector:
    """Collects and stores workflow metrics."""

    # Thresholds for optimization triggers
    THRESHOLDS = {
        "recurrence_rate": 0.15,
        "resolution_time_hours": 48,
        "sync_accuracy": 0.95,
        "validation_pass_rate": 0.90,
        "gap_closure_rate": 0.50,
        "completion_rate": 0.70,
    }

    def __init__(self):
        """Initialize the metrics collector."""
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        self.history: List[WorkflowMetricsSnapshot] = self._load_history()

    def _load_history(self) -> List[WorkflowMetricsSnapshot]:
        """Load metrics history from file."""
        if not METRICS_FILE.exists():
            return []

        try:
            with open(METRICS_FILE) as f:
                data = json.load(f)
            return [WorkflowMetricsSnapshot.from_dict(s) for s in data]
        except Exception as e:
            logger.warning(f"Failed to load metrics history: {e}")
            return []

    def _save_history(self) -> None:
        """Save metrics history to file."""
        try:
            data = [s.to_dict() for s in self.history[-100:]]  # Keep last 100
            with open(METRICS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def collect_current_metrics(self) -> WorkflowMetricsSnapshot:
        """Collect current metrics from all sources.

        Returns:
            WorkflowMetricsSnapshot with current metrics
        """
        snapshot = WorkflowMetricsSnapshot(
            period_start=datetime.now() - timedelta(days=1),
            period_end=datetime.now(),
        )

        # Collect task metrics
        snapshot.tasks = self._collect_task_metrics()

        # Collect gap metrics
        snapshot.gaps = self._collect_gap_metrics()

        # Calculate derived metrics
        self._calculate_derived_metrics(snapshot)

        # Store snapshot
        self.history.append(snapshot)
        self._save_history()

        logger.info("Metrics collected and stored")
        return snapshot

    def _collect_task_metrics(self) -> TaskMetrics:
        """Collect task-related metrics."""
        metrics = TaskMetrics()

        try:
            from scripts.task_discovery_engine import TaskDiscoveryEngine

            engine = TaskDiscoveryEngine()
            tasks = engine.discover_all()

            metrics.tasks_discovered = len(tasks)
            metrics.tasks_blocked = sum(1 for t in tasks if not t.dependencies_ready)

            # Count by source
            for task in tasks:
                source = task.source.value
                metrics.by_source[source] = metrics.by_source.get(source, 0) + 1

            # Count by type
            for task in tasks:
                task_type = task.task_type.value
                metrics.by_type[task_type] = metrics.by_type.get(task_type, 0) + 1

        except Exception as e:
            logger.warning(f"Failed to collect task metrics: {e}")

        return metrics

    def _collect_gap_metrics(self) -> GapMetrics:
        """Collect gap-related metrics."""
        metrics = GapMetrics()

        try:
            from scripts.services_gap_analyzer import ServicesGapAnalyzer

            analyzer = ServicesGapAnalyzer()
            report = analyzer.analyze_all_services()

            total_gaps = sum(g.total_gaps for g in report.service_gaps)
            metrics.services_gaps_identified = total_gaps
            metrics.services_gaps_resolved = report.services_complete

            if report.total_services > 0:
                metrics.gap_closure_rate = report.services_complete / report.total_services

        except Exception as e:
            logger.warning(f"Failed to collect gap metrics: {e}")

        return metrics

    def _calculate_derived_metrics(self, snapshot: WorkflowMetricsSnapshot) -> None:
        """Calculate derived metrics."""
        # Completion rate
        if snapshot.tasks.tasks_discovered > 0:
            snapshot.tasks.completion_rate = (
                snapshot.tasks.tasks_completed / snapshot.tasks.tasks_discovered
            )

    def get_trend_analysis(self, days: int = 7) -> Dict[str, Any]:
        """Analyze trends over the specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with trend analysis
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent = [s for s in self.history if s.timestamp >= cutoff]

        if len(recent) < 2:
            return {"status": "insufficient_data", "snapshots": len(recent)}

        # Calculate trends
        first = recent[0]
        last = recent[-1]

        trends = {
            "period_days": days,
            "snapshots_analyzed": len(recent),
            "tasks": {
                "discovered_change": last.tasks.tasks_discovered - first.tasks.tasks_discovered,
                "completion_rate_change": last.tasks.completion_rate - first.tasks.completion_rate,
            },
            "gaps": {
                "closure_rate_change": last.gaps.gap_closure_rate - first.gaps.gap_closure_rate,
            },
            "direction": "improving" if last.tasks.completion_rate > first.tasks.completion_rate else "declining",
        }

        return trends

    def suggest_optimizations(self) -> List[OptimizationSuggestion]:
        """Generate optimization suggestions based on metrics.

        Returns:
            List of OptimizationSuggestion objects
        """
        suggestions = []

        if not self.history:
            return suggestions

        latest = self.history[-1]

        # Check recurrence rate
        if latest.quality.recurrence_rate > self.THRESHOLDS["recurrence_rate"]:
            suggestions.append(OptimizationSuggestion(
                trigger="high_recurrence",
                metric_name="recurrence_rate",
                current_value=latest.quality.recurrence_rate,
                threshold=self.THRESHOLDS["recurrence_rate"],
                suggestion="Create preventive automation for recurring issues",
                priority="high",
                action_type="automation",
            ))

        # Check resolution time
        if latest.tasks.avg_resolution_time_hours > self.THRESHOLDS["resolution_time_hours"]:
            suggestions.append(OptimizationSuggestion(
                trigger="slow_resolution",
                metric_name="avg_resolution_time_hours",
                current_value=latest.tasks.avg_resolution_time_hours,
                threshold=self.THRESHOLDS["resolution_time_hours"],
                suggestion="Decompose long-running tasks into smaller steps",
                priority="medium",
                action_type="decomposition",
            ))

        # Check sync accuracy
        if latest.system.sync_accuracy < self.THRESHOLDS["sync_accuracy"]:
            suggestions.append(OptimizationSuggestion(
                trigger="low_sync_accuracy",
                metric_name="sync_accuracy",
                current_value=latest.system.sync_accuracy,
                threshold=self.THRESHOLDS["sync_accuracy"],
                suggestion="Review and strengthen cross-system validation rules",
                priority="high",
                action_type="review",
            ))

        # Check gap closure rate
        if latest.gaps.gap_closure_rate < self.THRESHOLDS["gap_closure_rate"]:
            suggestions.append(OptimizationSuggestion(
                trigger="low_gap_closure",
                metric_name="gap_closure_rate",
                current_value=latest.gaps.gap_closure_rate,
                threshold=self.THRESHOLDS["gap_closure_rate"],
                suggestion="Prioritize gap resolution tasks in discovery engine",
                priority="medium",
                action_type="review",
            ))

        # Check completion rate
        if latest.tasks.completion_rate < self.THRESHOLDS["completion_rate"]:
            suggestions.append(OptimizationSuggestion(
                trigger="low_completion",
                metric_name="completion_rate",
                current_value=latest.tasks.completion_rate,
                threshold=self.THRESHOLDS["completion_rate"],
                suggestion="Review blocked tasks and resolve dependencies",
                priority="high",
                action_type="escalate",
            ))

        return suggestions


def generate_report(collector: WorkflowMetricsCollector) -> str:
    """Generate a markdown metrics report."""
    if not collector.history:
        return "# Workflow Metrics Report\n\nNo metrics data available."

    latest = collector.history[-1]
    trends = collector.get_trend_analysis(7)
    suggestions = collector.suggest_optimizations()

    lines = [
        "# Workflow Metrics Report",
        f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Period:** Last 24 hours",
        "",
        "## Task Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tasks Discovered | {latest.tasks.tasks_discovered} |",
        f"| Tasks Completed | {latest.tasks.tasks_completed} |",
        f"| Tasks Blocked | {latest.tasks.tasks_blocked} |",
        f"| Completion Rate | {latest.tasks.completion_rate:.1%} |",
        "",
        "## Gap Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Gaps Identified | {latest.gaps.services_gaps_identified} |",
        f"| Gaps Resolved | {latest.gaps.services_gaps_resolved} |",
        f"| Gap Closure Rate | {latest.gaps.gap_closure_rate:.1%} |",
        "",
    ]

    if trends.get("status") != "insufficient_data":
        lines.extend([
            "## 7-Day Trends",
            "",
            f"- **Direction:** {trends['direction'].title()}",
            f"- **Tasks Discovered Change:** {trends['tasks']['discovered_change']:+d}",
            f"- **Completion Rate Change:** {trends['tasks']['completion_rate_change']:+.1%}",
            "",
        ])

    if suggestions:
        lines.extend([
            "## Optimization Suggestions",
            "",
        ])
        for s in suggestions:
            lines.append(f"### [{s.priority.upper()}] {s.trigger.replace('_', ' ').title()}")
            lines.append(f"- **Metric:** {s.metric_name} = {s.current_value:.2f} (threshold: {s.threshold})")
            lines.append(f"- **Suggestion:** {s.suggestion}")
            lines.append(f"- **Action Type:** {s.action_type}")
            lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Workflow performance metrics framework"
    )
    parser.add_argument(
        "command",
        choices=["collect", "report", "trends", "optimize", "json"],
        help="Command to run"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="Days for trend analysis"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path"
    )

    args = parser.parse_args()

    try:
        collector = WorkflowMetricsCollector()

        if args.command == "collect":
            snapshot = collector.collect_current_metrics()
            print(f"Metrics collected at {snapshot.timestamp}")
            print(f"  Tasks discovered: {snapshot.tasks.tasks_discovered}")
            print(f"  Gaps identified: {snapshot.gaps.services_gaps_identified}")

        elif args.command == "report":
            collector.collect_current_metrics()
            report = generate_report(collector)

            if args.output:
                with open(args.output, "w") as f:
                    f.write(report)
                print(f"Report saved to: {args.output}")
            else:
                print(report)

        elif args.command == "trends":
            trends = collector.get_trend_analysis(args.days)
            print(json.dumps(trends, indent=2))

        elif args.command == "optimize":
            collector.collect_current_metrics()
            suggestions = collector.suggest_optimizations()

            if suggestions:
                print(f"\n{'='*60}")
                print(f"OPTIMIZATION SUGGESTIONS ({len(suggestions)})")
                print(f"{'='*60}\n")

                for s in suggestions:
                    print(f"[{s.priority.upper()}] {s.trigger}")
                    print(f"  {s.suggestion}")
                    print(f"  Action: {s.action_type}")
                    print()
            else:
                print("No optimization suggestions - metrics within thresholds!")

        elif args.command == "json":
            snapshot = collector.collect_current_metrics()
            output = snapshot.to_dict()

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
