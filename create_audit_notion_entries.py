#!/usr/bin/env python3
"""
Create Notion entries for Plans Directory Audit.

Creates:
1. Execution-Logs entry for the audit
2. Agent-Tasks for identified gaps
3. Issues+Questions entries for critical findings
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from shared_core.notion.execution_logs import create_execution_log
    from shared_core.notion.issues_questions import create_issue_or_question
    EXECUTION_LOGS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Notion modules not available: {e}")
    EXECUTION_LOGS_AVAILABLE = False

# Try to import agent task creation
try:
    from main import create_agent_task
    TASK_CREATION_AVAILABLE = True
except ImportError:
    TASK_CREATION_AVAILABLE = False
    print("Warning: Agent task creation not available")


def create_audit_execution_log():
    """Create Execution-Logs entry for the audit."""
    if not EXECUTION_LOGS_AVAILABLE:
        print("Skipping Execution-Logs entry (module not available)")
        return None
    
    start_time = datetime.now(timezone.utc)
    
    metrics = {
        "plans_reviewed": 3,
        "deliverables_assessed": 20,
        "completion_rate": "75%",
        "gaps_identified": 5,
        "deliverables_created": 2,
    }
    
    summary = """Comprehensive audit of plans directory completed successfully.

Plans Reviewed:
- MODULARIZED_IMPLEMENTATION_DESIGN.md
- MONOLITHIC_MAINTENANCE_PLAN.md  
- MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md

Key Findings:
- Modular architecture largely implemented (75% complete)
- 62 Python files in music_workflow directory
- Configuration files created during audit
- Documentation and test coverage need completion

Deliverables Created:
- music_workflow.yaml configuration file
- music_volume_index.json index file

Gaps Identified:
- Documentation incomplete
- Test coverage unknown
- DRM error handling status unclear
- Performance profiling missing
- Deprecation plan missing"""
    
    log_id = create_execution_log(
        name="Plans Directory Audit - Music Workflow Plans - 2026-01-13",
        start_time=start_time,
        end_time=datetime.now(timezone.utc),
        status="Success",
        environment="local",
        script_name="Plans Directory Audit Agent",
        script_path=str(Path(__file__)),
        metrics=metrics,
        plain_english_summary=summary,
        type="Audit",
    )
    
    if log_id:
        print(f"✅ Created Execution-Logs entry: {log_id}")
    else:
        print("⚠️ Failed to create Execution-Logs entry")
    
    return log_id


def create_audit_issues():
    """Create Issues+Questions entries for identified gaps."""
    if not EXECUTION_LOGS_AVAILABLE:
        print("Skipping Issues+Questions entries (module not available)")
        return []
    
    issues = []
    
    # Issue 1: Documentation Incomplete
    issue1_id = create_issue_or_question(
        name="[AUDIT] Music Workflow Documentation Incomplete - Modularized Implementation",
        type=["Internal Issue"],
        status="Unreported",
        priority="Medium",
        blocked=False,
        description="""Identified during Plans Directory Audit.

Plan: MODULARIZED_IMPLEMENTATION_DESIGN.md
Expected Deliverable: Complete API documentation, migration guides
Gap Type: Documentation Gap
Impact: Medium - affects usability and onboarding

Deliverable Status: Partial - structure exists but content incomplete
Missing Components:
- API documentation
- Migration guides
- Usage examples
- Configuration documentation

Action Required: Complete documentation for all modules, add migration guide from monolithic to modular, create usage examples.""",
        tags=["Issue", "Audit Finding", "Documentation"],
    )
    if issue1_id:
        issues.append(issue1_id)
        print(f"✅ Created issue: Documentation Incomplete ({issue1_id})")
    
    # Issue 2: Test Coverage Unknown
    issue2_id = create_issue_or_question(
        name="[AUDIT] Music Workflow Test Coverage Unknown - Modularized Implementation",
        type=["Internal Issue"],
        status="Unreported",
        priority="Medium",
        blocked=False,
        description="""Identified during Plans Directory Audit.

Plan: MODULARIZED_IMPLEMENTATION_DESIGN.md
Expected Deliverable: Test coverage > 80%
Gap Type: Quality Gap
Impact: Medium - affects quality assurance

Deliverable Status: Unknown - test files exist (18 files) but coverage percentage unknown
Missing Components:
- Coverage analysis
- Coverage report
- Coverage target verification

Action Required: Run coverage analysis (pytest-cov), verify coverage meets 80% target, document coverage gaps.""",
        tags=["Issue", "Audit Finding", "Testing"],
    )
    if issue2_id:
        issues.append(issue2_id)
        print(f"✅ Created issue: Test Coverage Unknown ({issue2_id})")
    
    # Issue 3: DRM Error Handling Status Unclear
    issue3_id = create_issue_or_question(
        name="[AUDIT] DRM Error Handling Status Unclear - Monolithic Maintenance",
        type=["Bug", "Internal Issue"],
        status="Troubleshooting",
        priority="High",
        blocked=False,
        description="""Identified during Plans Directory Audit.

Plan: MONOLITHIC_MAINTENANCE_PLAN.md
Expected Deliverable: DRM error handling improvements (YouTube search fallback for Spotify)
Gap Type: Implementation Status Unclear
Impact: High - affects production reliability

Deliverable Status: Unknown - needs verification
Missing Components:
- Verification of DRM error handling implementation
- Test cases for DRM error scenarios
- Documentation of DRM error handling behavior

Action Required: Verify DRM error handling implementation status, test Spotify URL processing with DRM errors, document behavior.""",
        tags=["Issue", "Audit Finding", "Bug"],
    )
    if issue3_id:
        issues.append(issue3_id)
        print(f"✅ Created issue: DRM Error Handling Status Unclear ({issue3_id})")
    
    # Issue 4: Performance Profiling Missing
    issue4_id = create_issue_or_question(
        name="[AUDIT] Performance Profiling Missing - Monolithic Maintenance",
        type=["Internal Issue"],
        status="Unreported",
        priority="Low",
        blocked=False,
        description="""Identified during Plans Directory Audit.

Plan: MONOLITHIC_MAINTENANCE_PLAN.md
Expected Deliverable: Performance profiling and baseline documentation
Gap Type: Missing Deliverable
Impact: Low - affects optimization opportunities

Deliverable Status: Missing
Missing Components:
- Performance profiling tools
- Performance baseline documentation
- Bottleneck identification
- Performance metrics

Action Required: Create performance profiling script, establish baseline metrics, document performance characteristics.""",
        tags=["Issue", "Audit Finding"],
    )
    if issue4_id:
        issues.append(issue4_id)
        print(f"✅ Created issue: Performance Profiling Missing ({issue4_id})")
    
    # Issue 5: Deprecation Plan Missing
    issue5_id = create_issue_or_question(
        name="[AUDIT] Deprecation Plan Missing - Bifurcation Strategy",
        type=["Internal Issue"],
        status="Unreported",
        priority="Low",
        blocked=False,
        description="""Identified during Plans Directory Audit.

Plan: MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md
Expected Deliverable: Deprecation timeline for monolithic script
Gap Type: Missing Plan
Impact: Low - affects long-term strategy

Deliverable Status: Missing
Missing Components:
- Deprecation timeline
- Migration schedule
- Rollback plan
- Communication plan

Action Required: Create deprecation plan with timeline, define migration schedule, document rollback procedures.""",
        tags=["Issue", "Audit Finding"],
    )
    if issue5_id:
        issues.append(issue5_id)
        print(f"✅ Created issue: Deprecation Plan Missing ({issue5_id})")
    
    return issues


def create_audit_tasks():
    """Create Agent-Tasks for identified gaps."""
    if not TASK_CREATION_AVAILABLE:
        print("Skipping Agent-Tasks creation (module not available)")
        return []
    
    tasks = []
    
    # Task 1: Complete Documentation
    try:
        task1_id = create_agent_task(
            name="[AUDIT FINDING] Complete Music Workflow Documentation",
            description="""Identified during Plans Directory Audit.

Plan: MODULARIZED_IMPLEMENTATION_DESIGN.md
Expected Deliverable: Complete API documentation, migration guides
Gap Type: Documentation Gap
Impact: Medium - affects usability

Recommendation: Complete documentation for all modules, add migration guide from monolithic to modular, create usage examples.""",
            priority="Medium",
            status="Not Started",
            source_agent="Plans Directory Audit Agent",
        )
        if task1_id:
            tasks.append(task1_id)
            print(f"✅ Created task: Complete Documentation ({task1_id})")
    except Exception as e:
        print(f"⚠️ Failed to create task: {e}")
    
    # Task 2: Run Test Coverage Analysis
    try:
        task2_id = create_agent_task(
            name="[AUDIT FINDING] Run Music Workflow Test Coverage Analysis",
            description="""Identified during Plans Directory Audit.

Plan: MODULARIZED_IMPLEMENTATION_DESIGN.md
Expected Deliverable: Test coverage > 80%
Gap Type: Quality Gap
Impact: Medium - affects quality assurance

Recommendation: Run coverage analysis (pytest-cov), verify coverage meets 80% target, document coverage gaps.""",
            priority="Medium",
            status="Not Started",
            source_agent="Plans Directory Audit Agent",
        )
        if task2_id:
            tasks.append(task2_id)
            print(f"✅ Created task: Test Coverage Analysis ({task2_id})")
    except Exception as e:
        print(f"⚠️ Failed to create task: {e}")
    
    return tasks


def main():
    """Main function to create all Notion entries."""
    print("Creating Notion entries for Plans Directory Audit...")
    print()
    
    # Create Execution-Logs entry
    log_id = create_audit_execution_log()
    print()
    
    # Create Issues+Questions entries
    issues = create_audit_issues()
    print()
    
    # Create Agent-Tasks
    tasks = create_audit_tasks()
    print()
    
    # Summary
    print("=" * 60)
    print("Summary:")
    print(f"  Execution-Logs entries: {1 if log_id else 0}")
    print(f"  Issues+Questions entries: {len(issues)}")
    print(f"  Agent-Tasks entries: {len(tasks)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
