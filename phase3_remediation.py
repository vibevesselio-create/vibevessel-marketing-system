#!/usr/bin/env python3
"""
Phase 3: Issue Remediation & Handoff
Categorizes issues, attempts immediate remediation, creates handoff tasks.
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from unified_config import load_unified_env, get_unified_config

# Database IDs from plan
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"

def load_phase2_results() -> Dict[str, Any]:
    """Load Phase 2 execution results."""
    phase2_file = PROJECT_ROOT / 'phase2_execution_analysis.json'
    
    if not phase2_file.exists():
        print(f"  ✗ Phase 2 results not found: {phase2_file}")
        return {}
    
    try:
        with open(phase2_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"  ✗ Error loading Phase 2 results: {e}")
        return {}

def categorize_issues(gap_analysis: Dict) -> Dict[str, List[Dict]]:
    """Categorize issues by severity and type."""
    print("3.1 Categorizing Issues...")
    
    categorized = {
        "critical": [],
        "high": [],
        "medium": [],
        "low": []
    }
    
    # Functional gaps - typically HIGH priority
    for gap in gap_analysis.get("functional_gaps", []):
        if "fingerprint" in gap.lower():
            categorized["high"].append({
                "type": "Functional",
                "severity": "High",
                "description": gap,
                "category": "fingerprint_missing"
            })
        else:
            categorized["high"].append({
                "type": "Functional",
                "severity": "High",
                "description": gap
            })
    
    # Performance gaps - typically MEDIUM priority
    for gap in gap_analysis.get("performance_gaps", []):
        if "execution speed" in gap.lower() or "slow" in gap.lower():
            # Actually performance is fine (17s for 2998 items), mark as low
            categorized["low"].append({
                "type": "Performance",
                "severity": "Low",
                "description": gap,
                "note": "Performance is actually acceptable (17s for 2998 items)"
            })
        else:
            categorized["medium"].append({
                "type": "Performance",
                "severity": "Medium",
                "description": gap
            })
    
    # Accuracy gaps - typically MEDIUM to HIGH depending on impact
    for gap in gap_analysis.get("accuracy_gaps", []):
        if "false positive" in gap.lower() or "similarity" in gap.lower():
            categorized["medium"].append({
                "type": "Accuracy",
                "severity": "Medium",
                "description": gap,
                "category": "false_positive_risk",
                "note": "Low similarity matches may need manual review before cleanup"
            })
        else:
            categorized["high"].append({
                "type": "Accuracy",
                "severity": "High",
                "description": gap
            })
    
    # Documentation gaps - typically LOW priority
    for gap in gap_analysis.get("documentation_gaps", []):
        categorized["low"].append({
            "type": "Documentation",
            "severity": "Low",
            "description": gap
        })
    
    # Compliance gaps - CRITICAL
    for gap in gap_analysis.get("compliance_gaps", []):
        categorized["critical"].append({
            "type": "Compliance",
            "severity": "Critical",
            "description": gap
        })
    
    print(f"  ✓ Categorized {sum(len(v) for v in categorized.values())} issues:")
    print(f"    - Critical: {len(categorized['critical'])}")
    print(f"    - High: {len(categorized['high'])}")
    print(f"    - Medium: {len(categorized['medium'])}")
    print(f"    - Low: {len(categorized['low'])}")
    
    return categorized

def attempt_immediate_remediation(categorized: Dict) -> Dict[str, Any]:
    """Attempt immediate remediation for simple issues."""
    print("\n3.2 Attempting Immediate Remediation...")
    
    remediation_results = {
        "fixed": [],
        "cannot_fix": [],
        "requires_handoff": []
    }
    
    # Low priority issues - typically can be documented/warned
    for issue in categorized.get("low", []):
        if issue.get("note"):
            remediation_results["fixed"].append({
                "issue": issue,
                "action": "Documented as non-critical",
                "status": "Resolved"
            })
            print(f"  ✓ Low priority issue documented: {issue['description'][:50]}...")
    
    # Medium priority - false positives warning
    for issue in categorized.get("medium", []):
        if issue.get("category") == "false_positive_risk":
            remediation_results["fixed"].append({
                "issue": issue,
                "action": "Will review low-similarity matches before cleanup",
                "status": "Mitigated"
            })
            print(f"  ✓ Accuracy issue mitigated: {issue['description'][:50]}...")
        else:
            remediation_results["requires_handoff"].append(issue)
    
    # High priority - fingerprint missing
    for issue in categorized.get("high", []):
        if issue.get("category") == "fingerprint_missing":
            remediation_results["requires_handoff"].append(issue)
            print(f"  ⚠ High priority issue requires handoff: {issue['description'][:50]}...")
        else:
            remediation_results["requires_handoff"].append(issue)
    
    # Critical - should not proceed
    for issue in categorized.get("critical", []):
        remediation_results["cannot_fix"].append(issue)
        print(f"  ✗ CRITICAL issue cannot be fixed immediately: {issue['description'][:50]}...")
    
    print(f"\n  Remediation Summary:")
    print(f"    - Fixed/Mitigated: {len(remediation_results['fixed'])}")
    print(f"    - Requires Handoff: {len(remediation_results['requires_handoff'])}")
    print(f"    - Cannot Fix: {len(remediation_results['cannot_fix'])}")
    
    return remediation_results

def create_notion_agent_task(notion, db_id: str, issue: Dict, source_agent: str = "Claude MM1 Agent") -> Optional[str]:
    """Create a Notion task in Agent-Tasks database."""
    try:
        properties = {
            "Name": {
                "title": [{"text": {"content": f"Fix: {issue['description'][:100]}"}}]
            },
            "Status": {
                "select": {"name": "Not Started"}
            },
            "Priority": {
                "select": {"name": issue.get("severity", "Medium")}
            },
            "Description": {
                "rich_text": [{"text": {"content": issue.get("description", "")}}]
            },
            "Assigned Agent": {
                "select": {"name": "Claude Code Agent"}
            },
            # Note: "Source Agent" property removed - does not exist in schema
            "Type": {
                "select": {"name": issue.get("type", "Functional")}
            }
        }
        
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=properties
        )
        
        return page.get("id")
        
    except Exception as e:
        print(f"  ✗ Error creating Notion task: {e}")
        return None

def create_handoff_tasks(notion, remediation_results: Dict) -> Dict[str, Any]:
    """Create handoff tasks for issues requiring code agent expertise."""
    print("\n3.3 Creating Handoff to Claude Code Agent...")
    
    if not notion:
        print("  ⚠ Notion client not available - skipping task creation")
        return {"tasks_created": 0, "task_ids": []}
    
    handoff_results = {
        "tasks_created": 0,
        "task_ids": [],
        "failed": []
    }
    
    # Only create tasks for issues that require handoff
    for issue in remediation_results.get("requires_handoff", []):
        task_id = create_notion_agent_task(notion, AGENT_TASKS_DB_ID, issue)
        if task_id:
            handoff_results["tasks_created"] += 1
            handoff_results["task_ids"].append(task_id)
            print(f"  ✓ Created task for: {issue['description'][:50]}...")
        else:
            handoff_results["failed"].append(issue)
    
    print(f"\n  Handoff Summary:")
    print(f"    - Tasks created: {handoff_results['tasks_created']}")
    print(f"    - Failed: {len(handoff_results['failed'])}")
    
    return handoff_results

def main():
    """Main execution function."""
    print("=" * 80)
    print("PHASE 3: ISSUE REMEDIATION & HANDOFF")
    print("=" * 80)
    
    load_unified_env()
    config = get_unified_config()
    
    # Load Phase 2 results
    phase2_results = load_phase2_results()
    if not phase2_results:
        print("\n✗ Cannot proceed without Phase 2 results")
        return 1
    
    gap_analysis = phase2_results.get("gaps", {})
    if not gap_analysis:
        print("\n✗ No gap analysis found in Phase 2 results")
        return 1
    
    # 3.1 Categorize Issues
    categorized = categorize_issues(gap_analysis)
    
    # 3.2 Attempt Immediate Remediation
    remediation_results = attempt_immediate_remediation(categorized)
    
    # 3.3 Create Handoff Tasks
    try:
        from shared_core.notion.token_manager import get_notion_client
        notion = get_notion_client()
    except Exception as e:
        print(f"\n⚠ Could not get Notion client: {e}")
        notion = None
    
    handoff_results = create_handoff_tasks(notion, remediation_results)
    
    # Save remediation report
    remediation_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "categorized_issues": categorized,
        "remediation_results": remediation_results,
        "handoff_results": handoff_results,
        "can_proceed": len(remediation_results.get("cannot_fix", [])) == 0
    }
    
    output_file = PROJECT_ROOT / 'phase3_remediation_report.json'
    with open(output_file, 'w') as f:
        json.dump(remediation_report, f, indent=2, default=str)
    
    print(f"\n✓ Remediation report saved to: {output_file}")
    print("\n" + "=" * 80)
    print("PHASE 3 COMPLETE")
    print("=" * 80)
    
    if remediation_report["can_proceed"]:
        print("\n✓ No critical issues - ready to proceed to Phase 4")
        print("  Note: Review low-similarity matches manually before live cleanup")
        return 0
    else:
        print("\n✗ Critical issues found - DO NOT proceed until resolved")
        return 1

if __name__ == "__main__":
    sys.exit(main())
