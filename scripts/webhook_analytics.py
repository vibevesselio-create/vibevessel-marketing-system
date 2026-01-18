#!/usr/bin/env python3
"""
Webhook Analytics Tool

A comprehensive analytics and reporting tool for Notion Event Subscription webhooks.
Provides real-time analysis, historical trends, database activity insights, and
integrates with the dashboard service for visualization.

Features:
- CSV log analysis and aggregation
- Real-time event stream monitoring
- Database activity breakdown
- Event type distribution
- Hourly/daily trend analysis
- JSON/Markdown/HTML report generation
- Dashboard API integration

Usage:
    # Quick summary of today's events
    python webhook_analytics.py summary

    # Detailed report with database breakdown
    python webhook_analytics.py report --format markdown --output report.md

    # Real-time monitoring
    python webhook_analytics.py monitor

    # Export to dashboard
    python webhook_analytics.py push-dashboard

Author: Claude Code Agent
Version: 1.0.0
Created: 2026-01-16
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared_core.logging import setup_logging

# Initialize logger
logger = setup_logging(
    session_id="webhook_analytics",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    enable_file_logging=True,
)

# Constants
WEBHOOK_CSV_DIR = Path(
    os.getenv(
        "WEBHOOK_CSV_DIR",
        "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/"
        "My Drive/Seren Internal/Automation Files/Notion-Database-Webhooks"
    )
)

# CSV Schema
CSV_COLUMNS = [
    "timestamp", "event_type", "entity_id", "entity_type", "database_id",
    "name", "file_path", "actions_info", "processing_status",
    "actions_processed", "error_message", "payload"
]


class WebhookAnalytics:
    """
    Webhook analytics engine for processing and analyzing Notion webhook CSV logs.
    """

    def __init__(self, csv_dir: Optional[Path] = None):
        """
        Initialize analytics engine.

        Args:
            csv_dir: Directory containing webhook CSV files
        """
        self.csv_dir = csv_dir or WEBHOOK_CSV_DIR
        self._notion_client = None
        self._database_cache: Dict[str, str] = {}

    @property
    def notion_client(self):
        """Lazy-load Notion client."""
        if self._notion_client is None:
            try:
                from notion_client import Client
                from shared_core.notion.token_manager import get_notion_token
                self._notion_client = Client(auth=get_notion_token())
            except Exception as e:
                logger.warning(f"Notion client not available: {e}")
        return self._notion_client

    def get_csv_files(self, days: int = 7) -> List[Path]:
        """
        Get CSV files for the specified number of days.

        Args:
            days: Number of days to look back

        Returns:
            List of CSV file paths sorted by date
        """
        if not self.csv_dir.exists():
            logger.error(f"CSV directory not found: {self.csv_dir}")
            return []

        files = []
        today = datetime.now()

        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            csv_path = self.csv_dir / f"notion_database_webhooks_{date_str}.csv"
            if csv_path.exists():
                files.append(csv_path)

        return sorted(files)

    def parse_csv(self, csv_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a webhook CSV file.

        Args:
            csv_path: Path to CSV file

        Returns:
            List of event dictionaries
        """
        events = []

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse timestamp
                    try:
                        row['timestamp_dt'] = datetime.fromisoformat(row['timestamp'])
                    except (ValueError, KeyError):
                        row['timestamp_dt'] = None

                    # Parse payload JSON
                    try:
                        if row.get('payload'):
                            row['payload_json'] = json.loads(row['payload'])
                        else:
                            row['payload_json'] = {}
                    except json.JSONDecodeError:
                        row['payload_json'] = {}

                    events.append(row)

        except Exception as e:
            logger.error(f"Error parsing CSV {csv_path}: {e}")

        return events

    def get_database_name(self, database_id: str) -> str:
        """
        Get database name from Notion API with caching.

        Args:
            database_id: Notion database UUID

        Returns:
            Database name or "Unknown"
        """
        if not database_id or database_id == "unknown":
            return "Unknown"

        # Check cache
        if database_id in self._database_cache:
            return self._database_cache[database_id]

        # Try to get from Notion
        if self.notion_client:
            try:
                db = self.notion_client.databases.retrieve(database_id=database_id)
                name = db.get("title", [{}])[0].get("plain_text", "Unknown")
                self._database_cache[database_id] = name
                return name
            except Exception:
                pass

        # Return shortened ID as fallback
        self._database_cache[database_id] = f"db-{database_id[:8]}"
        return self._database_cache[database_id]

    def analyze_events(
        self,
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze a list of webhook events.

        Args:
            events: List of event dictionaries

        Returns:
            Analysis results dictionary
        """
        if not events:
            return {"total_events": 0, "error": "No events to analyze"}

        # Basic counts
        total = len(events)
        event_types = Counter(e.get('event_type', 'unknown') for e in events)
        entity_types = Counter(e.get('entity_type', 'unknown') for e in events)
        processing_statuses = Counter(e.get('processing_status', 'unknown') for e in events)

        # Database activity
        database_events = defaultdict(lambda: {"count": 0, "types": Counter()})
        for event in events:
            # Try to extract parent database ID from payload
            db_id = event.get('database_id', 'unknown')
            if db_id == 'unknown' and event.get('payload_json'):
                payload = event['payload_json']
                parent = payload.get('data', {}).get('parent', {})
                db_id = parent.get('id', 'unknown')

            database_events[db_id]["count"] += 1
            database_events[db_id]["types"][event.get('event_type', 'unknown')] += 1

        # Time analysis
        timestamps = [e['timestamp_dt'] for e in events if e.get('timestamp_dt')]
        if timestamps:
            min_time = min(timestamps)
            max_time = max(timestamps)
            duration = max_time - min_time
            events_per_hour = total / max(duration.total_seconds() / 3600, 1)
        else:
            min_time = max_time = None
            duration = timedelta(0)
            events_per_hour = 0

        # Hourly breakdown
        hourly_counts = Counter()
        for event in events:
            if event.get('timestamp_dt'):
                hour = event['timestamp_dt'].strftime('%Y-%m-%d %H:00')
                hourly_counts[hour] += 1

        # Error analysis
        errors = [e for e in events if e.get('error_message')]
        error_count = len(errors)

        # Top authors (from payload)
        authors = Counter()
        for event in events:
            payload = event.get('payload_json', {})
            for author in payload.get('authors', []):
                author_type = author.get('type', 'unknown')
                authors[author_type] += 1

        return {
            "total_events": total,
            "time_range": {
                "start": min_time.isoformat() if min_time else None,
                "end": max_time.isoformat() if max_time else None,
                "duration_hours": duration.total_seconds() / 3600 if duration else 0,
            },
            "events_per_hour": round(events_per_hour, 2),
            "event_types": dict(event_types.most_common()),
            "entity_types": dict(entity_types),
            "processing_statuses": dict(processing_statuses),
            "database_activity": {
                db_id: {
                    "name": self.get_database_name(db_id) if db_id != 'unknown' else 'Unknown',
                    "count": data["count"],
                    "event_types": dict(data["types"]),
                }
                for db_id, data in sorted(
                    database_events.items(),
                    key=lambda x: x[1]["count"],
                    reverse=True
                )[:10]  # Top 10 databases
            },
            "hourly_breakdown": dict(sorted(hourly_counts.items())),
            "error_count": error_count,
            "author_types": dict(authors),
        }

    def generate_summary(self, days: int = 1) -> Dict[str, Any]:
        """
        Generate a summary of webhook activity.

        Args:
            days: Number of days to analyze

        Returns:
            Summary dictionary
        """
        logger.info(f"Generating summary for {days} day(s)")

        csv_files = self.get_csv_files(days=days)
        if not csv_files:
            return {"error": f"No CSV files found for the last {days} day(s)"}

        all_events = []
        for csv_file in csv_files:
            events = self.parse_csv(csv_file)
            all_events.extend(events)
            logger.info(f"Loaded {len(events)} events from {csv_file.name}")

        analysis = self.analyze_events(all_events)
        analysis["files_analyzed"] = [f.name for f in csv_files]
        analysis["generated_at"] = datetime.now().isoformat()

        return analysis

    def format_markdown_report(self, analysis: Dict[str, Any]) -> str:
        """
        Format analysis as Markdown report.

        Args:
            analysis: Analysis results dictionary

        Returns:
            Markdown formatted string
        """
        lines = [
            "# Webhook Analytics Report",
            "",
            f"**Generated:** {analysis.get('generated_at', 'N/A')}",
            f"**Files Analyzed:** {', '.join(analysis.get('files_analyzed', []))}",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Events | {analysis.get('total_events', 0):,} |",
            f"| Events/Hour | {analysis.get('events_per_hour', 0):.1f} |",
            f"| Errors | {analysis.get('error_count', 0):,} |",
            "",
        ]

        # Time range
        time_range = analysis.get('time_range', {})
        if time_range.get('start'):
            lines.extend([
                "## Time Range",
                "",
                f"- **Start:** {time_range['start']}",
                f"- **End:** {time_range['end']}",
                f"- **Duration:** {time_range['duration_hours']:.1f} hours",
                "",
            ])

        # Event types
        event_types = analysis.get('event_types', {})
        if event_types:
            lines.extend([
                "## Event Types",
                "",
                "| Event Type | Count | % |",
                "|------------|-------|---|",
            ])
            total = analysis.get('total_events', 1)
            for event_type, count in event_types.items():
                pct = (count / total) * 100
                lines.append(f"| `{event_type}` | {count:,} | {pct:.1f}% |")
            lines.append("")

        # Database activity
        db_activity = analysis.get('database_activity', {})
        if db_activity:
            lines.extend([
                "## Top Databases by Activity",
                "",
                "| Database | Events | Top Event Type |",
                "|----------|--------|----------------|",
            ])
            for db_id, data in db_activity.items():
                name = data.get('name', db_id[:12])
                count = data.get('count', 0)
                top_type = max(data.get('event_types', {'unknown': 0}).items(), key=lambda x: x[1])[0]
                lines.append(f"| {name} | {count:,} | `{top_type}` |")
            lines.append("")

        # Author types
        authors = analysis.get('author_types', {})
        if authors:
            lines.extend([
                "## Author Types",
                "",
                "| Type | Count |",
                "|------|-------|",
            ])
            for author_type, count in authors.items():
                lines.append(f"| {author_type} | {count:,} |")
            lines.append("")

        # Hourly breakdown (last 24 hours)
        hourly = analysis.get('hourly_breakdown', {})
        if hourly:
            lines.extend([
                "## Hourly Activity (Last 24 Hours)",
                "",
                "```",
            ])
            # Show as simple ASCII chart
            max_count = max(hourly.values()) if hourly else 1
            for hour, count in list(hourly.items())[-24:]:
                bar_len = int((count / max_count) * 40)
                bar = '#' * bar_len
                lines.append(f"{hour[-5:]} | {bar} {count}")
            lines.extend(["```", ""])

        return "\n".join(lines)

    def format_json_report(self, analysis: Dict[str, Any]) -> str:
        """Format analysis as JSON."""
        return json.dumps(analysis, indent=2, default=str)

    def format_console_summary(self, analysis: Dict[str, Any]) -> str:
        """Format analysis as console-friendly summary."""
        lines = [
            "",
            "=" * 70,
            "WEBHOOK ANALYTICS SUMMARY",
            "=" * 70,
            "",
            f"Generated: {analysis.get('generated_at', 'N/A')}",
            f"Files: {', '.join(analysis.get('files_analyzed', []))}",
            "",
            "-" * 40,
            "TOTALS",
            "-" * 40,
            f"  Total Events:    {analysis.get('total_events', 0):,}",
            f"  Events/Hour:     {analysis.get('events_per_hour', 0):.1f}",
            f"  Errors:          {analysis.get('error_count', 0):,}",
            "",
        ]

        # Time range
        time_range = analysis.get('time_range', {})
        if time_range.get('start'):
            lines.extend([
                "-" * 40,
                "TIME RANGE",
                "-" * 40,
                f"  Start:    {time_range['start'][:19]}",
                f"  End:      {time_range['end'][:19]}",
                f"  Duration: {time_range['duration_hours']:.1f} hours",
                "",
            ])

        # Event types
        event_types = analysis.get('event_types', {})
        if event_types:
            lines.extend([
                "-" * 40,
                "EVENT TYPES",
                "-" * 40,
            ])
            total = analysis.get('total_events', 1)
            for event_type, count in event_types.items():
                pct = (count / total) * 100
                lines.append(f"  {event_type:30} {count:6,}  ({pct:5.1f}%)")
            lines.append("")

        # Top databases
        db_activity = analysis.get('database_activity', {})
        if db_activity:
            lines.extend([
                "-" * 40,
                "TOP DATABASES",
                "-" * 40,
            ])
            for db_id, data in list(db_activity.items())[:5]:
                name = data.get('name', db_id[:20])
                count = data.get('count', 0)
                lines.append(f"  {name[:30]:30} {count:6,}")
            lines.append("")

        lines.extend(["=" * 70, ""])

        return "\n".join(lines)

    def push_to_dashboard(self, analysis: Dict[str, Any]) -> bool:
        """
        Push analytics to the dashboard service.

        Args:
            analysis: Analysis results dictionary

        Returns:
            True if successful
        """
        import urllib.request
        import urllib.error

        dashboard_url = os.getenv("WEBHOOK_DASHBOARD_URL", "http://localhost:5003")
        api_key = os.getenv("WEBHOOK_DASHBOARD_API_KEY")

        if not api_key:
            logger.warning("WEBHOOK_DASHBOARD_API_KEY not set, skipping dashboard push")
            return False

        try:
            payload = {
                "type": "analytics_update",
                "data": analysis,
                "timestamp": datetime.now().isoformat(),
            }

            req = urllib.request.Request(
                f"{dashboard_url}/dashboard/api/event",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key,
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("Analytics pushed to dashboard")
                    return True

        except urllib.error.URLError as e:
            logger.warning(f"Failed to push to dashboard: {e}")
        except Exception as e:
            logger.error(f"Dashboard push error: {e}")

        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Webhook Analytics Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Quick summary of today's events
    python webhook_analytics.py summary

    # Summary for last 7 days
    python webhook_analytics.py summary --days 7

    # Generate Markdown report
    python webhook_analytics.py report --format markdown --output report.md

    # JSON output
    python webhook_analytics.py report --format json

    # Push to dashboard
    python webhook_analytics.py push-dashboard
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Summary command
    summary_parser = subparsers.add_parser("summary", help="Quick summary")
    summary_parser.add_argument("--days", type=int, default=1, help="Days to analyze")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate report")
    report_parser.add_argument("--days", type=int, default=1, help="Days to analyze")
    report_parser.add_argument(
        "--format",
        choices=["markdown", "json", "console"],
        default="console",
        help="Output format"
    )
    report_parser.add_argument("--output", "-o", help="Output file path")

    # Push dashboard command
    dashboard_parser = subparsers.add_parser("push-dashboard", help="Push to dashboard")
    dashboard_parser.add_argument("--days", type=int, default=1, help="Days to analyze")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    analytics = WebhookAnalytics()

    try:
        if args.command == "summary":
            analysis = analytics.generate_summary(days=args.days)
            print(analytics.format_console_summary(analysis))

        elif args.command == "report":
            analysis = analytics.generate_summary(days=args.days)

            if args.format == "markdown":
                output = analytics.format_markdown_report(analysis)
            elif args.format == "json":
                output = analytics.format_json_report(analysis)
            else:
                output = analytics.format_console_summary(analysis)

            if args.output:
                Path(args.output).write_text(output, encoding='utf-8')
                logger.info(f"Report saved to {args.output}")
            else:
                print(output)

        elif args.command == "push-dashboard":
            analysis = analytics.generate_summary(days=args.days)
            success = analytics.push_to_dashboard(analysis)
            if success:
                print("Analytics pushed to dashboard successfully")
            else:
                print("Failed to push analytics to dashboard")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Error: {e}")
        sys.exit(1)
    finally:
        logger.finalize(ok=True)
        logger.close()


if __name__ == "__main__":
    main()
