#!/usr/bin/env python3
"""Services Database Gap Analyzer.

Analyzes the Notion Services database for gaps in properties, missing relations,
and synchronization issues with related databases (scripts, workflows, functions).

Part of the Dynamic Discovery Workflow system for self-optimizing task resolution.

Usage:
    python services_gap_analyzer.py analyze          # Full gap analysis
    python services_gap_analyzer.py report           # Generate gap report
    python services_gap_analyzer.py sync-scripts     # Sync with scripts database
    python services_gap_analyzer.py create-tasks     # Create tasks for gaps
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
SERVICES_DB_ID = "26ce7361-6c27-8134-8909-ee25246dfdc4"
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"
AGENT_WORKFLOWS_DB_ID = "259e7361-6c27-8192-ae2e-e6d54b4198e1"
AGENT_TASKS_DB_ID = "136e7361-6c27-804b-85bc-f5b938b32bc6"


# Required properties for a complete service entry
REQUIRED_PROPERTIES = [
    "Name",
    "Description",
    "Status",
    "Primary Type",
]

# Recommended properties for production readiness
RECOMMENDED_PROPERTIES = [
    "API Docs Homepage URL",
    "Auth Method Standardized",
    "Environment Key",
    "API Status",
]

# Important relation properties
RELATION_PROPERTIES = [
    "scripts",
    "Agent-Workflows",
    "Agent-Functions",
    "Documents",
    "Variables",
]


@dataclass
class PropertyGap:
    """Represents a missing or empty property."""

    property_name: str
    property_type: str
    severity: str  # "required", "recommended", "relation"
    current_value: Optional[Any] = None


@dataclass
class ServiceGap:
    """Gaps identified for a single service."""

    service_id: str
    service_name: str
    service_url: str

    missing_required: List[PropertyGap] = field(default_factory=list)
    missing_recommended: List[PropertyGap] = field(default_factory=list)
    missing_relations: List[PropertyGap] = field(default_factory=list)

    gap_score: float = 0.0  # 0.0 = complete, 1.0 = missing everything

    @property
    def total_gaps(self) -> int:
        return len(self.missing_required) + len(self.missing_recommended) + len(self.missing_relations)

    @property
    def has_critical_gaps(self) -> bool:
        return len(self.missing_required) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "service_url": self.service_url,
            "missing_required": [asdict(g) for g in self.missing_required],
            "missing_recommended": [asdict(g) for g in self.missing_recommended],
            "missing_relations": [asdict(g) for g in self.missing_relations],
            "gap_score": self.gap_score,
            "total_gaps": self.total_gaps,
            "has_critical_gaps": self.has_critical_gaps,
        }


@dataclass
class GapAnalysisReport:
    """Complete gap analysis report."""

    timestamp: datetime = field(default_factory=datetime.now)
    total_services: int = 0
    services_with_gaps: int = 0
    services_complete: int = 0

    total_required_gaps: int = 0
    total_recommended_gaps: int = 0
    total_relation_gaps: int = 0

    service_gaps: List[ServiceGap] = field(default_factory=list)

    # Scripts sync status
    orphaned_scripts: List[str] = field(default_factory=list)
    unlinked_services: List[str] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.total_services == 0:
            return 0.0
        return self.services_complete / self.total_services

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_services": self.total_services,
            "services_with_gaps": self.services_with_gaps,
            "services_complete": self.services_complete,
            "completion_rate": self.completion_rate,
            "total_required_gaps": self.total_required_gaps,
            "total_recommended_gaps": self.total_recommended_gaps,
            "total_relation_gaps": self.total_relation_gaps,
            "service_gaps": [g.to_dict() for g in self.service_gaps],
            "orphaned_scripts": self.orphaned_scripts,
            "unlinked_services": self.unlinked_services,
        }

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "# Services Database Gap Analysis Report",
            f"\n**Generated:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Services | {self.total_services} |",
            f"| Services Complete | {self.services_complete} |",
            f"| Services with Gaps | {self.services_with_gaps} |",
            f"| Completion Rate | {self.completion_rate:.1%} |",
            f"| Required Property Gaps | {self.total_required_gaps} |",
            f"| Recommended Property Gaps | {self.total_recommended_gaps} |",
            f"| Missing Relations | {self.total_relation_gaps} |",
            "",
        ]

        if self.service_gaps:
            # Sort by gap score descending
            sorted_gaps = sorted(self.service_gaps, key=lambda g: g.gap_score, reverse=True)

            lines.extend([
                "## Services Requiring Attention",
                "",
                "### Critical (Missing Required Properties)",
                "",
            ])

            critical = [g for g in sorted_gaps if g.has_critical_gaps]
            if critical:
                for gap in critical[:10]:  # Top 10
                    lines.append(f"- **[{gap.service_name}]({gap.service_url})** - {len(gap.missing_required)} required, {len(gap.missing_relations)} relations")
            else:
                lines.append("*No critical gaps found*")

            lines.extend([
                "",
                "### Incomplete (Missing Recommended/Relations)",
                "",
            ])

            incomplete = [g for g in sorted_gaps if not g.has_critical_gaps and g.total_gaps > 0]
            for gap in incomplete[:10]:
                lines.append(f"- [{gap.service_name}]({gap.service_url}) - {gap.total_gaps} gaps")

        if self.orphaned_scripts:
            lines.extend([
                "",
                "## Orphaned Scripts (Not Linked to Services)",
                "",
            ])
            for script in self.orphaned_scripts[:20]:
                lines.append(f"- {script}")

        if self.unlinked_services:
            lines.extend([
                "",
                "## Services Without Script Links",
                "",
            ])
            for service in self.unlinked_services[:20]:
                lines.append(f"- {service}")

        return "\n".join(lines)


class ServicesGapAnalyzer:
    """Analyzes Services database for gaps and sync issues."""

    def __init__(self, notion_token: Optional[str] = None):
        """Initialize the analyzer.

        Args:
            notion_token: Notion API token. Defaults to NOTION_TOKEN env var.
        """
        self.notion_token = notion_token or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
        if not self.notion_token:
            raise RuntimeError("NOTION_TOKEN environment variable required")

        self.notion = Client(auth=self.notion_token)

    def analyze_all_services(self) -> GapAnalysisReport:
        """Analyze all services in the database.

        Returns:
            GapAnalysisReport with all gaps identified
        """
        logger.info("Starting Services database gap analysis...")
        report = GapAnalysisReport()

        # Fetch all services
        services = self._fetch_all_services()
        report.total_services = len(services)

        logger.info(f"Analyzing {len(services)} services...")

        for service in services:
            gap = self._analyze_service(service)

            if gap.total_gaps > 0:
                report.services_with_gaps += 1
                report.service_gaps.append(gap)
                report.total_required_gaps += len(gap.missing_required)
                report.total_recommended_gaps += len(gap.missing_recommended)
                report.total_relation_gaps += len(gap.missing_relations)
            else:
                report.services_complete += 1

        # Sort gaps by score
        report.service_gaps.sort(key=lambda g: g.gap_score, reverse=True)

        logger.info(f"Analysis complete: {report.services_with_gaps} services with gaps")
        return report

    def analyze_scripts_sync(self, report: GapAnalysisReport) -> GapAnalysisReport:
        """Analyze sync status between Services and Scripts databases.

        Args:
            report: Existing report to extend

        Returns:
            Updated report with sync analysis
        """
        logger.info("Analyzing Scripts ↔ Services synchronization...")

        # Get services with script relations
        services_with_scripts: Set[str] = set()

        for service in self._fetch_all_services():
            props = service.get("properties", {})
            scripts_rel = props.get("scripts", {})
            if scripts_rel.get("relation"):
                services_with_scripts.add(self._get_title(props))

        # Get all scripts
        scripts = self._fetch_all_scripts()
        scripts_linked: Set[str] = set()

        for script in scripts:
            props = script.get("properties", {})
            service_rel = props.get("External Data Source", {}) or props.get("services", {})

            script_name = self._get_title(props)

            if service_rel.get("relation"):
                scripts_linked.add(script_name)
            else:
                report.orphaned_scripts.append(script_name)

        # Find services without script links
        all_services = {self._get_title(s.get("properties", {})) for s in self._fetch_all_services()}
        report.unlinked_services = list(all_services - services_with_scripts)

        logger.info(f"Found {len(report.orphaned_scripts)} orphaned scripts, {len(report.unlinked_services)} unlinked services")
        return report

    def _analyze_service(self, service: Dict[str, Any]) -> ServiceGap:
        """Analyze a single service for gaps."""
        props = service.get("properties", {})

        service_name = self._get_title(props)
        service_id = service.get("id", "")
        service_url = service.get("url", f"https://notion.so/{service_id.replace('-', '')}")

        gap = ServiceGap(
            service_id=service_id,
            service_name=service_name,
            service_url=service_url,
        )

        # Check required properties
        for prop_name in REQUIRED_PROPERTIES:
            if not self._has_value(props.get(prop_name)):
                gap.missing_required.append(PropertyGap(
                    property_name=prop_name,
                    property_type=self._get_property_type(props.get(prop_name)),
                    severity="required",
                ))

        # Check recommended properties
        for prop_name in RECOMMENDED_PROPERTIES:
            if not self._has_value(props.get(prop_name)):
                gap.missing_recommended.append(PropertyGap(
                    property_name=prop_name,
                    property_type=self._get_property_type(props.get(prop_name)),
                    severity="recommended",
                ))

        # Check relations
        for prop_name in RELATION_PROPERTIES:
            prop = props.get(prop_name)
            if prop and prop.get("type") == "relation":
                if not prop.get("relation"):
                    gap.missing_relations.append(PropertyGap(
                        property_name=prop_name,
                        property_type="relation",
                        severity="relation",
                    ))

        # Calculate gap score
        total_checks = len(REQUIRED_PROPERTIES) + len(RECOMMENDED_PROPERTIES) + len(RELATION_PROPERTIES)
        gap.gap_score = gap.total_gaps / total_checks if total_checks > 0 else 0.0

        return gap

    def _fetch_all_services(self) -> List[Dict[str, Any]]:
        """Fetch all services from Notion."""
        services = []
        cursor = None

        while True:
            response = self.notion.databases.query(
                database_id=SERVICES_DB_ID,
                start_cursor=cursor,
                page_size=100,
            )

            services.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return services

    def _fetch_all_scripts(self) -> List[Dict[str, Any]]:
        """Fetch all scripts from Notion."""
        scripts = []
        cursor = None

        while True:
            response = self.notion.databases.query(
                database_id=SCRIPTS_DB_ID,
                start_cursor=cursor,
                page_size=100,
            )

            scripts.extend(response.get("results", []))

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")

        return scripts

    def _get_title(self, props: Dict[str, Any]) -> str:
        """Extract title from properties."""
        name_prop = props.get("Name") or props.get("name")
        if not name_prop:
            return "Untitled"

        title = name_prop.get("title", [])
        if title:
            return title[0].get("plain_text", "Untitled")
        return "Untitled"

    def _has_value(self, prop: Optional[Dict[str, Any]]) -> bool:
        """Check if a property has a value."""
        if not prop:
            return False

        prop_type = prop.get("type")

        if prop_type == "title":
            return bool(prop.get("title"))
        elif prop_type == "rich_text":
            return bool(prop.get("rich_text"))
        elif prop_type == "select":
            return bool(prop.get("select"))
        elif prop_type == "multi_select":
            return bool(prop.get("multi_select"))
        elif prop_type == "url":
            return bool(prop.get("url"))
        elif prop_type == "status":
            return bool(prop.get("status"))
        elif prop_type == "relation":
            return bool(prop.get("relation"))
        elif prop_type == "checkbox":
            return True  # Checkbox always has a value
        elif prop_type == "number":
            return prop.get("number") is not None
        elif prop_type == "date":
            return bool(prop.get("date"))

        return False

    def _get_property_type(self, prop: Optional[Dict[str, Any]]) -> str:
        """Get the type of a property."""
        if not prop:
            return "unknown"
        return prop.get("type", "unknown")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Services database for gaps and sync issues"
    )
    parser.add_argument(
        "command",
        choices=["analyze", "report", "sync-scripts", "json"],
        help="Command to run"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path"
    )

    args = parser.parse_args()

    try:
        analyzer = ServicesGapAnalyzer()

        if args.command == "analyze":
            report = analyzer.analyze_all_services()
            report = analyzer.analyze_scripts_sync(report)

            print(report.to_markdown())

        elif args.command == "report":
            report = analyzer.analyze_all_services()
            report = analyzer.analyze_scripts_sync(report)

            output_path = args.output or f"services_gap_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

            with open(output_path, "w") as f:
                f.write(report.to_markdown())

            print(f"Report saved to: {output_path}")

        elif args.command == "json":
            report = analyzer.analyze_all_services()
            report = analyzer.analyze_scripts_sync(report)

            output_path = args.output or f"services_gap_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            with open(output_path, "w") as f:
                json.dump(report.to_dict(), f, indent=2)

            print(f"JSON report saved to: {output_path}")

        elif args.command == "sync-scripts":
            report = GapAnalysisReport()
            report = analyzer.analyze_scripts_sync(report)

            print(f"Orphaned scripts: {len(report.orphaned_scripts)}")
            print(f"Unlinked services: {len(report.unlinked_services)}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
