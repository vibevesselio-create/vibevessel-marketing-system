#!/usr/bin/env python3
"""
Task Completion Analysis Script
Analyzes Notion Agent-Tasks to identify completion issues and review loops
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any
from datetime import datetime

try:
    from notion_client import Client
    NOTION_CLIENT_AVAILABLE = True
except ImportError:
    print("ERROR: notion-client not available")
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = os.getenv("AGENT_TASKS_DB_ID", "284e73616c278018872aeb14e82e0392")
ISSUES_DB_ID = os.getenv("ISSUES_DB_ID", "229e73616c27808ebf06c202b10b5166")

def get_notion_token() -> str:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback to environment variables for backwards compatibility
    token = (
        os.getenv("NOTION_TOKEN") or
        os.getenv("NOTION_API_TOKEN") or
        os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    )
    if token:
        return token

    raise ValueError("NOTION_TOKEN not found in token_manager or environment")

def safe_get_property(page: Dict, property_name: str, property_type: str = None) -> Any:
    """Safely extract property value from Notion page"""
    try:
        properties = page.get("properties", {})
        if not properties:
            return None
        
        prop = properties.get(property_name)
        if not prop:
            return None
        
        actual_type = prop.get("type")
        if property_type and actual_type != property_type:
            return None
        
        if actual_type == "title":
            title_list = prop.get("title", [])
            if title_list and len(title_list) > 0:
                return title_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "rich_text":
            text_list = prop.get("rich_text", [])
            if text_list and len(text_list) > 0:
                return text_list[0].get("plain_text", "")
            return None
        
        elif actual_type == "status":
            status_obj = prop.get("status")
            if status_obj:
                return status_obj.get("name")
            return None
        
        elif actual_type == "select":
            select_obj = prop.get("select")
            if select_obj:
                return select_obj.get("name")
            return None
        
        elif actual_type == "relation":
            relation_list = prop.get("relation", [])
            return relation_list
        
        return None
    except Exception:
        return None

def get_agent_name(client: Client, agent_id: str) -> str:
    """Get agent name from ID"""
    try:
        page = client.pages.retrieve(page_id=agent_id)
        properties = page.get("properties", {})
        for prop_name in ["Name", "Title", "Agent Name"]:
            prop = properties.get(prop_name)
            if prop and prop.get("type") == "title":
                title_list = prop.get("title", [])
                if title_list:
                    return title_list[0].get("plain_text", "")
        return f"Agent_{agent_id[:8]}"
    except:
        return f"Agent_{agent_id[:8]}"

def analyze_tasks(client: Client):
    """Analyze task completion patterns"""
    print("=" * 80)
    print("TASK COMPLETION ANALYSIS")
    print("=" * 80)
    print()
    
    # Get all tasks
    all_tasks = []
    cursor = None
    while True:
        query_params = {"database_id": AGENT_TASKS_DB_ID}
        if cursor:
            query_params["start_cursor"] = cursor
        
        response = client.databases.query(**query_params)
        all_tasks.extend(response.get("results", []))
        
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    
    print(f"Total tasks found: {len(all_tasks)}")
    print()
    
    # Analyze by status
    status_counts = defaultdict(int)
    status_tasks = defaultdict(list)
    
    for task in all_tasks:
        status = safe_get_property(task, "Status", "status") or "Unknown"
        status_counts[status] += 1
        status_tasks[status].append(task)
    
    print("=" * 80)
    print("TASK STATUS DISTRIBUTION")
    print("=" * 80)
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")
    print()
    
    # Analyze by agent
    agent_counts = defaultdict(lambda: {"total": 0, "complete": 0, "in_progress": 0, "ready": 0, "planning": 0})
    
    for task in all_tasks:
        status = safe_get_property(task, "Status", "status") or "Unknown"
        task_name = safe_get_property(task, "Task Name", "title") or "Untitled"
        
        assigned_agent = safe_get_property(task, "Assigned-Agent", "relation") or []
        if assigned_agent:
            agent_id = assigned_agent[0].get("id")
            agent_name = get_agent_name(client, agent_id)
            
            agent_counts[agent_name]["total"] += 1
            if status in ["Complete", "Completed", "Done"]:
                agent_counts[agent_name]["complete"] += 1
            elif status in ["In Progress", "In-Progress"]:
                agent_counts[agent_name]["in_progress"] += 1
            elif status in ["Ready", "Ready for Handoff"]:
                agent_counts[agent_name]["ready"] += 1
            
            # Check if it's a planning task
            if "plan" in task_name.lower() or "review" in task_name.lower() or "analyze" in task_name.lower():
                agent_counts[agent_name]["planning"] += 1
    
    print("=" * 80)
    print("TASK DISTRIBUTION BY AGENT")
    print("=" * 80)
    for agent, counts in sorted(agent_counts.items(), key=lambda x: -x[1]["total"]):
        completion_rate = (counts["complete"] / counts["total"] * 100) if counts["total"] > 0 else 0
        print(f"\n{agent}:")
        print(f"  Total: {counts['total']}")
        print(f"  Complete: {counts['complete']} ({completion_rate:.1f}%)")
        print(f"  In Progress: {counts['in_progress']}")
        print(f"  Ready: {counts['ready']}")
        print(f"  Planning/Review Tasks: {counts['planning']}")
    
    # Identify review loops - tasks that mention "plan", "review", "analyze" but never lead to implementation
    print()
    print("=" * 80)
    print("POTENTIAL REVIEW LOOPS")
    print("=" * 80)
    
    planning_tasks = []
    implementation_tasks = []
    
    for task in all_tasks:
        task_name = safe_get_property(task, "Task Name", "title") or "Untitled"
        status = safe_get_property(task, "Status", "status") or "Unknown"
        description = safe_get_property(task, "Description", "rich_text") or ""
        task_id = task.get("id")
        task_url = task.get("url", "")
        
        is_planning = any(keyword in task_name.lower() for keyword in ["plan", "review", "analyze", "assess", "evaluate"])
        is_implementation = any(keyword in task_name.lower() for keyword in ["implement", "build", "create", "develop", "fix", "resolve", "execute"])
        
        if is_planning:
            planning_tasks.append({
                "id": task_id,
                "name": task_name,
                "status": status,
                "url": task_url,
                "description": description[:200]
            })
        elif is_implementation:
            implementation_tasks.append({
                "id": task_id,
                "name": task_name,
                "status": status,
                "url": task_url
            })
    
    print(f"\nPlanning/Review Tasks: {len(planning_tasks)}")
    print(f"Implementation Tasks: {len(implementation_tasks)}")
    print(f"Ratio: {len(planning_tasks) / len(implementation_tasks) if implementation_tasks else 'N/A'}")
    print()
    
    # Show incomplete planning tasks
    incomplete_planning = [t for t in planning_tasks if t["status"] not in ["Complete", "Completed", "Done"]]
    if incomplete_planning:
        print(f"\n⚠️  INCOMPLETE PLANNING TASKS ({len(incomplete_planning)}):")
        for task in incomplete_planning[:10]:  # Show top 10
            print(f"  - [{task['status']}] {task['name']}")
            print(f"    {task['url']}")
    
    # Check for tasks stuck in Ready/In Progress
    print()
    print("=" * 80)
    print("TASKS STUCK IN READY/IN PROGRESS")
    print("=" * 80)
    
    stuck_tasks = []
    for task in all_tasks:
        status = safe_get_property(task, "Status", "status") or "Unknown"
        if status in ["Ready", "In Progress", "In-Progress", "Ready for Handoff"]:
            task_name = safe_get_property(task, "Task Name", "title") or "Untitled"
            created_time = task.get("created_time", "")
            last_edited = task.get("last_edited_time", "")
            
            # Parse dates
            try:
                if created_time:
                    created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    last_edited_dt = datetime.fromisoformat(last_edited.replace("Z", "+00:00"))
                    now = datetime.now(created_dt.tzinfo)
                    age_days = (now - created_dt).days
                    stale_days = (now - last_edited_dt).days
                    
                    if age_days > 1 or stale_days > 0:  # Older than 1 day or not edited today
                        stuck_tasks.append({
                            "name": task_name,
                            "status": status,
                            "age_days": age_days,
                            "stale_days": stale_days,
                            "url": task.get("url", "")
                        })
            except:
                pass
    
    if stuck_tasks:
        print(f"\n⚠️  FOUND {len(stuck_tasks)} POTENTIALLY STUCK TASKS:")
        for task in sorted(stuck_tasks, key=lambda x: -x["age_days"])[:20]:  # Top 20 oldest
            print(f"  - [{task['status']}] {task['name']} (Age: {task['age_days']} days, stale {task['stale_days']} days)")
            print(f"    {task['url']}")
    else:
        print("\n✅ No stuck tasks found")
    
    # Check issues status
    print()
    print("=" * 80)
    print("OUTSTANDING ISSUES")
    print("=" * 80)
    
    issues = []
    cursor = None
    while True:
        query_params = {"database_id": ISSUES_DB_ID}
        if cursor:
            query_params["start_cursor"] = cursor
        
        response = client.databases.query(**query_params)
        issues.extend(response.get("results", []))
        
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    
    unresolved = [i for i in issues if safe_get_property(i, "Status", "status") not in ["Resolved", "Closed", "Completed"]]
    print(f"\nTotal Issues: {len(issues)}")
    print(f"Unresolved: {len(unresolved)}")
    
    if unresolved:
        print(f"\n⚠️  UNRESOLVED ISSUES:")
        for issue in unresolved[:10]:
            issue_name = safe_get_property(issue, "Name", "title") or "Untitled"
            priority = safe_get_property(issue, "Priority", "select") or "Unknown"
            status = safe_get_property(issue, "Status", "status") or "Unknown"
            print(f"  - [{priority}] [{status}] {issue_name}")
            print(f"    {issue.get('url', '')}")
    
    print()
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()
    
    if len(planning_tasks) > len(implementation_tasks) * 2:
        print("⚠️  CRITICAL: Too many planning tasks relative to implementation tasks!")
        print("   This suggests a review loop where planning tasks create more planning tasks.")
        print("   Recommendation: Ensure planning tasks MUST create implementation tasks, not more planning tasks.")
    
    if incomplete_planning:
        print(f"⚠️  {len(incomplete_planning)} planning tasks are incomplete.")
        print("   Recommendation: Review why planning tasks aren't completing and creating implementation handoffs.")
    
    if stuck_tasks:
        print(f"⚠️  {len(stuck_tasks)} tasks appear stuck in Ready/In Progress.")
        print("   Recommendation: Review these tasks and either complete them or identify blockers.")
    
    completion_rate = (status_counts.get("Complete", 0) + status_counts.get("Completed", 0)) / len(all_tasks) * 100 if all_tasks else 0
    if completion_rate < 20:
        print(f"⚠️  Low completion rate: {completion_rate:.1f}%")
        print("   Recommendation: Investigate why tasks aren't being marked complete.")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    try:
        token = get_notion_token()
        client = Client(auth=token)
        analyze_tasks(client)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

