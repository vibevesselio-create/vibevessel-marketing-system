#!/usr/bin/env python3
"""
Return Handoff Compliance Monitoring Script
===========================================

Monitors agent compliance with return handoff requirements.
Verifies that agents create return handoffs when completing handoff-assigned tasks.

Usage:
    python3 scripts/monitor_return_handoff_compliance.py [--count N]
    
Options:
    --count N    Monitor N agent executions (default: 3)
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import (
    NotionManager,
    get_notion_token,
    safe_get_property,
    AGENT_TASKS_DB_ID,
    MM1_AGENT_TRIGGER_BASE,
    MM2_AGENT_TRIGGER_BASE,
    normalize_agent_folder_name,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('return_handoff_compliance_monitor.log')
    ]
)
logger = logging.getLogger(__name__)


class ReturnHandoffComplianceMonitor:
    """Monitor agent compliance with return handoff requirements"""
    
    def __init__(self, notion: NotionManager):
        self.notion = notion
        self.compliance_records: List[Dict[str, Any]] = []
        
    def find_recent_processed_handoffs(self, count: int = 3, days_back: int = 7) -> List[Dict[str, Any]]:
        """
        Find recently processed handoff trigger files.
        
        Args:
            count: Number of executions to monitor
            days_back: Number of days to look back
            
        Returns:
            List of handoff execution records
        """
        logger.info(f"Searching for recent handoff executions (last {days_back} days)...")
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        handoff_executions = []
        
        # Search MM1 agent folders
        for base_path in [MM1_AGENT_TRIGGER_BASE]:
            if not base_path.exists():
                logger.warning(f"Base path does not exist: {base_path}")
                continue
                
            for agent_folder in base_path.iterdir():
                if not agent_folder.is_dir() or agent_folder.name.startswith("_"):
                    continue
                
                processed_folder = agent_folder / "02_processed"
                if not processed_folder.exists():
                    continue
                
                # Look for HANDOFF files in processed folder
                for trigger_file in processed_folder.glob("*__HANDOFF__*.json"):
                    try:
                        # Get file modification time
                        file_mtime = datetime.fromtimestamp(
                            trigger_file.stat().st_mtime, 
                            tz=timezone.utc
                        )
                        
                        if file_mtime < cutoff_date:
                            continue
                        
                        # Read trigger file
                        with open(trigger_file, 'r', encoding='utf-8') as f:
                            trigger_data = json.load(f)
                        
                        task_id = trigger_data.get("task_id")
                        if not task_id:
                            continue
                        
                        handoff_executions.append({
                            "trigger_file": str(trigger_file),
                            "trigger_data": trigger_data,
                            "task_id": task_id,
                            "agent_name": trigger_data.get("agent_name", "Unknown"),
                            "task_title": trigger_data.get("task_title", "Unknown"),
                            "processed_time": file_mtime.isoformat(),
                            "agent_folder": agent_folder.name
                        })
                        
                    except Exception as e:
                        logger.warning(f"Error processing trigger file {trigger_file}: {e}")
                        continue
        
        # Sort by processed time (newest first)
        handoff_executions.sort(
            key=lambda x: x["processed_time"], 
            reverse=True
        )
        
        # Return only the requested count
        return handoff_executions[:count]
    
    def check_return_handoff_task(self, original_task_id: str, executing_agent: str) -> Optional[Dict[str, Any]]:
        """
        Check if a return handoff task was created in Notion.
        
        Args:
            original_task_id: ID of the original task
            executing_agent: Name of the agent who executed the task
            
        Returns:
            Return handoff task data if found, None otherwise
        """
        logger.debug(f"Checking for return handoff task for original task {original_task_id}")
        
        # Search for tasks with "Return Handoff" in title and relation to original task
        filter_params = {
            "and": [
                {
                    "property": "Task Name",
                    "title": {"contains": "Return Handoff"}
                }
            ]
        }
        
        return_handoff_tasks = self.notion.query_database(
            AGENT_TASKS_DB_ID,
            filter_params=filter_params
        )
        
        # Filter for tasks related to our original task
        # Check task description or title for original task ID
        for task in return_handoff_tasks:
            task_title = safe_get_property(task, "Task Name", "title") or ""
            task_description = safe_get_property(task, "Description", "rich_text") or ""
            
            # Check if this return handoff is related to our original task
            if original_task_id in task_description or original_task_id in task_title:
                # Check if executing agent matches
                if executing_agent.lower() in task_description.lower() or executing_agent.lower() in task_title.lower():
                    return {
                        "task_id": task.get("id"),
                        "task_url": task.get("url", ""),
                        "task_title": task_title,
                        "task_description": task_description,
                        "status": safe_get_property(task, "Status", "status"),
                        "found": True
                    }
        
        return None
    
    def check_return_trigger_file(self, original_task_id: str, originating_agent: str, executing_agent: str) -> Optional[str]:
        """
        Check if a return trigger file was created.
        
        Args:
            original_task_id: ID of the original task
            originating_agent: Name of the agent who created the original handoff
            executing_agent: Name of the agent who executed the task
            
        Returns:
            Path to return trigger file if found, None otherwise
        """
        logger.debug(f"Checking for return trigger file from {executing_agent} to {originating_agent}")
        
        # Determine originating agent folder
        originating_agent_folder = normalize_agent_folder_name(originating_agent)
        inbox_folder = MM1_AGENT_TRIGGER_BASE / f"{originating_agent_folder}-Agent" / "01_inbox"
        
        if not inbox_folder.exists():
            # Try without -Agent suffix
            inbox_folder = MM1_AGENT_TRIGGER_BASE / originating_agent_folder / "01_inbox"
        
        if not inbox_folder.exists():
            logger.warning(f"Inbox folder not found for {originating_agent}: {inbox_folder}")
            return None
        
        # Look for RETURN files
        task_id_short = original_task_id.replace("-", "")[:8]
        for return_file in inbox_folder.glob("*__RETURN__*.json"):
            try:
                with open(return_file, 'r', encoding='utf-8') as f:
                    return_data = json.load(f)
                
                # Check if this return file is for our task
                orig_task_id = return_data.get("originating_task_id") or return_data.get("original_task_id")
                if orig_task_id == original_task_id or task_id_short in return_file.name:
                    return str(return_file)
                    
            except Exception as e:
                logger.warning(f"Error reading return file {return_file}: {e}")
                continue
        
        return None
    
    def check_chat_response_anti_pattern(self, task_id: str, agent_name: str) -> Dict[str, Any]:
        """
        Check if agent responded directly in chat (anti-pattern).
        
        This is difficult to detect programmatically, but we can check:
        1. If return handoff was created (indicates compliance)
        2. Task completion notes that might indicate chat response
        
        Args:
            task_id: Task ID
            agent_name: Agent name
            
        Returns:
            Anti-pattern detection results
        """
        # If return handoff exists, it's likely compliant
        # If no return handoff exists, it might be an anti-pattern
        # We can't definitively detect chat responses without access to chat logs
        # So we'll infer based on missing return handoffs
        
        return {
            "chat_response_detected": False,  # Cannot definitively detect
            "inference": "Cannot programmatically detect direct chat responses. Check manually if return handoff missing.",
            "requires_manual_review": True
        }
    
    def get_original_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get original task information from Notion"""
        try:
            # Try to retrieve the task
            task = self.notion.client.pages.retrieve(page_id=task_id)
            
            return {
                "task_id": task_id,
                "task_url": task.get("url", ""),
                "task_title": safe_get_property(task, "Task Name", "title") or "Unknown",
                "task_status": safe_get_property(task, "Status", "status"),
                "assigned_agent": safe_get_property(task, "Assigned-Agent", "relation"),
                "description": safe_get_property(task, "Description", "rich_text") or ""
            }
        except Exception as e:
            logger.warning(f"Could not retrieve task {task_id}: {e}")
            return None
    
    def monitor_execution(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        """
        Monitor a single agent execution for compliance.
        
        Args:
            execution: Execution record from find_recent_processed_handoffs
            
        Returns:
            Compliance record
        """
        logger.info(f"Monitoring execution: {execution['task_title']} by {execution['agent_name']}")
        
        task_id = execution["task_id"]
        executing_agent = execution["agent_name"]
        
        # Get original task info
        original_task = self.get_original_task_info(task_id)
        if not original_task:
            logger.warning(f"Could not retrieve original task {task_id}")
            return {
                "execution": execution,
                "original_task": None,
                "compliant": False,
                "errors": ["Could not retrieve original task information"]
            }
        
        # Determine originating agent from task or trigger data
        # If task has handoff_instructions, it was a handoff-assigned task
        trigger_data = execution["trigger_data"]
        handoff_instructions = trigger_data.get("handoff_instructions", "")
        
        # Try to infer originating agent from task description or handoff instructions
        # Common pattern: "assigned to [Agent]" or handoff from [Agent]
        originating_agent = None
        if "Claude MM1" in handoff_instructions:
            originating_agent = "Claude MM1 Agent"
        elif "Cursor MM1" in handoff_instructions:
            originating_agent = "Cursor MM1 Agent"
        elif "Codex MM1" in handoff_instructions:
            originating_agent = "Codex MM1 Agent"
        else:
            # Default assumption - need to check task relations or description
            originating_agent = "Unknown"
        
        # Check for return handoff task
        return_handoff_task = self.check_return_handoff_task(task_id, executing_agent)
        
        # Check for return trigger file
        return_trigger_file = None
        if originating_agent != "Unknown":
            return_trigger_file = self.check_return_trigger_file(
                task_id,
                originating_agent,
                executing_agent
            )
        
        # Check for chat response anti-pattern
        chat_check = self.check_chat_response_anti_pattern(task_id, executing_agent)
        
        # Determine compliance
        compliant = (
            return_handoff_task is not None and
            return_trigger_file is not None
        )
        
        compliance_record = {
            "execution": execution,
            "original_task": original_task,
            "originating_agent": originating_agent,
            "executing_agent": executing_agent,
            "return_handoff_task": return_handoff_task,
            "return_trigger_file": return_trigger_file,
            "chat_response_check": chat_check,
            "compliant": compliant,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }
        
        if not compliant:
            errors = []
            if return_handoff_task is None:
                errors.append("Return handoff Agent-Task not found in Notion")
            if return_trigger_file is None:
                errors.append("Return trigger file not found")
            compliance_record["errors"] = errors
        
        return compliance_record
    
    def monitor_executions(self, count: int = 3) -> List[Dict[str, Any]]:
        """
        Monitor multiple agent executions for compliance.
        
        Args:
            count: Number of executions to monitor
            
        Returns:
            List of compliance records
        """
        logger.info(f"Starting compliance monitoring for {count} agent executions...")
        
        # Find recent handoff executions
        executions = self.find_recent_processed_handoffs(count=count)
        
        if not executions:
            logger.warning("No recent handoff executions found")
            return []
        
        logger.info(f"Found {len(executions)} recent handoff execution(s)")
        
        # Monitor each execution
        compliance_records = []
        for execution in executions:
            record = self.monitor_execution(execution)
            compliance_records.append(record)
        
        self.compliance_records = compliance_records
        return compliance_records
    
    def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate compliance report from monitored executions"""
        if not self.compliance_records:
            return {
                "total_monitored": 0,
                "total_compliant": 0,
                "total_non_compliant": 0,
                "compliance_rate": 0.0,
                "records": []
            }
        
        total = len(self.compliance_records)
        compliant = sum(1 for r in self.compliance_records if r.get("compliant", False))
        non_compliant = total - compliant
        compliance_rate = (compliant / total * 100) if total > 0 else 0.0
        
        # Summary by agent
        agent_summary = defaultdict(lambda: {"total": 0, "compliant": 0})
        for record in self.compliance_records:
            agent = record.get("executing_agent", "Unknown")
            agent_summary[agent]["total"] += 1
            if record.get("compliant", False):
                agent_summary[agent]["compliant"] += 1
        
        return {
            "total_monitored": total,
            "total_compliant": compliant,
            "total_non_compliant": non_compliant,
            "compliance_rate": compliance_rate,
            "agent_summary": dict(agent_summary),
            "records": self.compliance_records,
            "report_generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def save_report(self, report: Dict[str, Any], output_path: Path) -> None:
        """Save compliance report to file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Compliance report saved to {output_path}")


def main():
    """Main execution"""
    parser = argparse.ArgumentParser(description="Monitor return handoff compliance")
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of agent executions to monitor (default: 3)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="return_handoff_compliance_report.json",
        help="Output file path for compliance report"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Return Handoff Compliance Monitoring")
    logger.info("=" * 80)
    
    # Initialize Notion client
    token = get_notion_token()
    if not token:
        logger.error("Failed to get Notion token")
        sys.exit(1)
    
    notion = NotionManager(token)
    
    # Create monitor
    monitor = ReturnHandoffComplianceMonitor(notion)
    
    # Monitor executions
    compliance_records = monitor.monitor_executions(count=args.count)
    
    # Generate report
    report = monitor.generate_compliance_report()
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("COMPLIANCE SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total Monitored: {report['total_monitored']}")
    logger.info(f"Compliant: {report['total_compliant']}")
    logger.info(f"Non-Compliant: {report['total_non_compliant']}")
    logger.info(f"Compliance Rate: {report['compliance_rate']:.1f}%")
    
    if report['agent_summary']:
        logger.info("\nBy Agent:")
        for agent, stats in report['agent_summary'].items():
            rate = (stats['compliant'] / stats['total'] * 100) if stats['total'] > 0 else 0
            logger.info(f"  {agent}: {stats['compliant']}/{stats['total']} ({rate:.1f}%)")
    
    # Print detailed records
    logger.info("\n" + "=" * 80)
    logger.info("DETAILED RECORDS")
    logger.info("=" * 80)
    
    for i, record in enumerate(compliance_records, 1):
        logger.info(f"\nExecution {i}:")
        logger.info(f"  Task: {record.get('execution', {}).get('task_title', 'Unknown')}")
        logger.info(f"  Executing Agent: {record.get('executing_agent', 'Unknown')}")
        logger.info(f"  Compliant: {'✅ YES' if record.get('compliant', False) else '❌ NO'}")
        
        if record.get('return_handoff_task'):
            logger.info(f"  ✅ Return Handoff Task: {record['return_handoff_task'].get('task_url', 'N/A')}")
        else:
            logger.info(f"  ❌ Return Handoff Task: NOT FOUND")
        
        if record.get('return_trigger_file'):
            logger.info(f"  ✅ Return Trigger File: {record['return_trigger_file']}")
        else:
            logger.info(f"  ❌ Return Trigger File: NOT FOUND")
        
        if record.get('errors'):
            logger.info(f"  Errors: {', '.join(record['errors'])}")
    
    # Save report
    output_path = project_root / args.output
    monitor.save_report(report, output_path)
    
    logger.info("\n" + "=" * 80)
    logger.info(f"Report saved to: {output_path}")
    logger.info("=" * 80)
    
    return report


if __name__ == "__main__":
    main()

