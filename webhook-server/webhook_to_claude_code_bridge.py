#!/usr/bin/env python3
"""
Webhook-to-Claude-Code Bridge
=============================

Bridges webhook events (Notion, GitHub, Linear) to Claude Code automation.
When critical events occur (errors, issues, blockers), automatically routes
them to Claude Code for resolution.

Integration Points:
1. Notion webhooks → Process task errors/blockers → Submit to Claude Code
2. GitHub issue creation → Format context → Submit to Claude Code
3. Linear issue creation → Format context → Submit to Claude Code
4. Script execution errors → Capture and route → Submit to Claude Code

Author: Claude Code Agent (Opus 4.5)
Created: 2026-01-19
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Setup logging
logger = logging.getLogger("webhook_to_claude_code_bridge")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

# Paths
AGENT_TRIGGERS_DIR = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers")
ERROR_HANDLER = AGENT_TRIGGERS_DIR / "error_to_claude_code.py"
CLAUDE_CODE_AGENT = AGENT_TRIGGERS_DIR / "agents" / "claude_code_agent.py"

# Import claude_code_agent if available
sys.path.insert(0, str(AGENT_TRIGGERS_DIR))
sys.path.insert(0, str(AGENT_TRIGGERS_DIR / "agents"))

try:
    from agents.claude_code_agent import deliver_trigger_content
    DESKTOP_AUTOMATION_AVAILABLE = True
except ImportError:
    DESKTOP_AUTOMATION_AVAILABLE = False
    logger.warning("Desktop automation not available - will use file-based triggers")


@dataclass
class ClaudeCodeTask:
    """Task to be submitted to Claude Code."""
    title: str
    description: str
    source: str  # webhook, github, linear, script
    priority: str  # high, medium, low
    context: Dict[str, Any]
    timestamp: str

    def to_prompt(self) -> str:
        """Format as Claude Code prompt."""
        priority_prefix = {
            "high": "🔴 CRITICAL - IMMEDIATE ACTION REQUIRED",
            "medium": "🟡 IMPORTANT - Action Needed",
            "low": "🟢 TASK - When Available"
        }.get(self.priority, "TASK")

        context_str = "\n".join(f"- **{k}**: {v}" for k, v in self.context.items())

        return f"""{priority_prefix}

## {self.title}

{self.description}

## Context

{context_str}

## Source

- **Type**: {self.source}
- **Timestamp**: {self.timestamp}

## Instructions

1. Review the task above
2. Gather necessary context from the codebase
3. Implement the required changes
4. Test your implementation
5. Report completion status
"""


class WebhookToClaudeCodeBridge:
    """
    Routes webhook events to Claude Code for automated processing.
    """

    def __init__(self):
        self.logger = logger
        self.trigger_inbox = AGENT_TRIGGERS_DIR / "01_inbox" / "Claude-Code-MM1-Agent"
        self.trigger_inbox.mkdir(parents=True, exist_ok=True)

    async def route_notion_event(self, event: Dict[str, Any]) -> bool:
        """
        Route Notion webhook event to Claude Code if it's actionable.

        Args:
            event: Notion webhook event payload

        Returns:
            True if routed, False if not actionable
        """
        event_type = event.get("type", "")
        page_id = event.get("data", {}).get("page_id") or event.get("entity", {}).get("id")

        # Check for error/blocker keywords in task name
        task_name = self._extract_task_name(event)
        is_blocker = any(kw in task_name.upper() for kw in ["BLOCKER", "ERROR", "CRITICAL", "URGENT"])
        is_issue = "[ISSUE]" in task_name

        if not (is_blocker or is_issue):
            self.logger.debug(f"Skipping non-actionable event: {task_name}")
            return False

        # Create task for Claude Code
        task = ClaudeCodeTask(
            title=task_name,
            description=self._extract_description(event),
            source="notion_webhook",
            priority="high" if is_blocker else "medium",
            context={
                "page_id": page_id,
                "event_type": event_type,
                "notion_url": f"https://notion.so/{page_id.replace('-', '')}" if page_id else "unknown"
            },
            timestamp=datetime.now().isoformat()
        )

        return await self._submit_task(task)

    async def route_github_issue(self, issue: Dict[str, Any]) -> bool:
        """
        Route GitHub issue to Claude Code.

        Args:
            issue: GitHub issue payload

        Returns:
            True if routed successfully
        """
        title = issue.get("title", "Unknown Issue")
        body = issue.get("body", "")
        labels = [l.get("name", "") for l in issue.get("labels", [])]

        # Check priority from labels
        priority = "high" if "bug" in labels or "critical" in labels else "medium"

        task = ClaudeCodeTask(
            title=f"[GitHub] {title}",
            description=body[:2000],  # Limit description
            source="github_issue",
            priority=priority,
            context={
                "issue_number": issue.get("number"),
                "issue_url": issue.get("html_url"),
                "repo": issue.get("repository", {}).get("full_name"),
                "labels": ", ".join(labels)
            },
            timestamp=datetime.now().isoformat()
        )

        return await self._submit_task(task)

    async def route_linear_issue(self, issue: Dict[str, Any]) -> bool:
        """
        Route Linear issue to Claude Code.

        Args:
            issue: Linear issue payload

        Returns:
            True if routed successfully
        """
        title = issue.get("title", "Unknown Issue")
        description = issue.get("description", "")
        priority_val = issue.get("priority", 0)

        # Map Linear priority (1-4 where 1 is urgent)
        priority = "high" if priority_val <= 2 else "medium"

        task = ClaudeCodeTask(
            title=f"[Linear] {title}",
            description=description[:2000],
            source="linear_issue",
            priority=priority,
            context={
                "issue_id": issue.get("id"),
                "issue_identifier": issue.get("identifier"),
                "issue_url": issue.get("url"),
                "team": issue.get("team", {}).get("name"),
                "state": issue.get("state", {}).get("name")
            },
            timestamp=datetime.now().isoformat()
        )

        return await self._submit_task(task)

    async def route_script_error(
        self,
        script_name: str,
        error_output: str,
        exit_code: int,
        context: str = ""
    ) -> bool:
        """
        Route script execution error to Claude Code.

        Args:
            script_name: Name of the failing script
            error_output: Error output/traceback
            exit_code: Script exit code
            context: Additional context

        Returns:
            True if routed successfully
        """
        task = ClaudeCodeTask(
            title=f"[SCRIPT ERROR] {script_name}",
            description=f"Script failed with exit code {exit_code}.\n\n```\n{error_output[:3000]}\n```",
            source="script_error",
            priority="high",
            context={
                "script": script_name,
                "exit_code": exit_code,
                "additional_context": context[:500]
            },
            timestamp=datetime.now().isoformat()
        )

        return await self._submit_task(task)

    async def _submit_task(self, task: ClaudeCodeTask) -> bool:
        """
        Submit task to Claude Code via desktop automation or file trigger.

        Args:
            task: Task to submit

        Returns:
            True if submitted successfully
        """
        prompt = task.to_prompt()

        # Try desktop automation first
        if DESKTOP_AUTOMATION_AVAILABLE:
            try:
                success = deliver_trigger_content(prompt, create_new=True)
                if success:
                    self.logger.info(f"Submitted to Claude Code via desktop: {task.title}")
                    return True
                else:
                    self.logger.warning("Desktop automation failed, falling back to file trigger")
            except Exception as e:
                self.logger.error(f"Desktop automation error: {e}")

        # Fallback: create trigger file
        trigger_file = self.trigger_inbox / f"{datetime.now().strftime('%Y%m%dT%H%M%SZ')}__{task.source}.md"
        try:
            with open(trigger_file, 'w') as f:
                f.write(prompt)
            self.logger.info(f"Created trigger file: {trigger_file}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create trigger file: {e}")
            return False

    def _extract_task_name(self, event: Dict[str, Any]) -> str:
        """Extract task name from Notion event."""
        # Try various paths in the event structure
        properties = event.get("data", {}).get("properties", {})
        if not properties:
            properties = event.get("properties", {})

        # Try common property names
        for prop_name in ["Task Name", "Name", "Title", "name", "title"]:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "title":
                titles = prop.get("title", [])
                if titles:
                    return titles[0].get("plain_text", "")

        return event.get("entity", {}).get("name", "Unknown Task")

    def _extract_description(self, event: Dict[str, Any]) -> str:
        """Extract description from Notion event."""
        properties = event.get("data", {}).get("properties", {})
        if not properties:
            properties = event.get("properties", {})

        for prop_name in ["Description", "description", "Body", "body"]:
            prop = properties.get(prop_name, {})
            if prop.get("type") == "rich_text":
                texts = prop.get("rich_text", [])
                if texts:
                    return " ".join(t.get("plain_text", "") for t in texts)

        return "No description available"


# Global bridge instance
_bridge: Optional[WebhookToClaudeCodeBridge] = None


def get_bridge() -> WebhookToClaudeCodeBridge:
    """Get or create the global bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = WebhookToClaudeCodeBridge()
    return _bridge


async def route_to_claude_code(event_type: str, payload: Dict[str, Any]) -> bool:
    """
    Convenience function to route any event to Claude Code.

    Args:
        event_type: Type of event (notion, github, linear, script)
        payload: Event payload

    Returns:
        True if routed successfully
    """
    bridge = get_bridge()

    if event_type == "notion":
        return await bridge.route_notion_event(payload)
    elif event_type == "github":
        return await bridge.route_github_issue(payload)
    elif event_type == "linear":
        return await bridge.route_linear_issue(payload)
    elif event_type == "script":
        return await bridge.route_script_error(
            script_name=payload.get("script_name", "unknown"),
            error_output=payload.get("error_output", ""),
            exit_code=payload.get("exit_code", -1),
            context=payload.get("context", "")
        )
    else:
        logger.warning(f"Unknown event type: {event_type}")
        return False


if __name__ == "__main__":
    # Test the bridge
    import asyncio

    async def test():
        bridge = get_bridge()

        # Test script error routing
        success = await bridge.route_script_error(
            script_name="test_script.py",
            error_output="ImportError: No module named 'nonexistent'",
            exit_code=1,
            context="Testing the bridge"
        )
        print(f"Script error routing: {'SUCCESS' if success else 'FAILED'}")

    asyncio.run(test())
