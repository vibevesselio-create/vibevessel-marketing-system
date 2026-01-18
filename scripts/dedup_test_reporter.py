#!/usr/bin/env python3
"""Deduplication Test Issue Reporter - Reports issues to Notion Issues+Questions database"""

import sys
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')

from shared_core.notion.issues_questions import create_issue_or_question

def report_dedup_issue(
    title: str,
    phase: str,
    command: str,
    error_msg: str,
    expected: str,
    actual: str,
    priority: str = "Medium",
    stack_trace: str = "",
    extra_tags: list[str] | None = None,
):
    """Report a deduplication testing issue to Notion."""

    description = f"""**Test Phase:** {phase}
**Command:** `{command}`
**Error:** {error_msg}
**Expected:** {expected}
**Actual:** {actual}
**Component:** Deduplication
"""
    if stack_trace:
        description += f"\n**Stack Trace:**\n```\n{stack_trace[:500]}\n```"

    tags = ["deduplication", "production-testing", "codex-mm1", "2026-01-07"]
    if extra_tags:
        tags.extend(extra_tags)

    page_id = create_issue_or_question(
        name=f"[Dedup Test] {title}",
        type=["Internal Issue"],
        status="Open",
        priority=priority,
        description=description,
        tags=tags,
    )

    if page_id:
        print(f"✓ Issue reported: {title} (ID: {page_id})")
    else:
        print(f"✗ Failed to report issue: {title}")

    return page_id


if __name__ == "__main__":
    # Validate reporter works
    page_id = report_dedup_issue(
        title="Reporter Validation Test",
        phase="Setup",
        command="python3 dedup_test_reporter.py",
        error_msg="None - validation only",
        expected="Issue created in Notion",
        actual="Pending verification",
        priority="Low"
    )
    print(f"Reporter test complete. Page ID: {page_id}")
