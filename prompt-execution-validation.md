# Prompt Execution Validation & Testing Guide

## Purpose
This document provides a comprehensive validation process to ensure prompts result in direct task execution by agents, not just analysis or documentation.

## Validation Checklist

### Pre-Execution Validation

Before an agent runs a prompt, verify:

- [ ] **Execution Directive Present**: Prompt contains explicit "YOU MUST EXECUTE" language
- [ ] **No Ambiguous Language**: All instances of "attempt", "try", "consider" replaced with "MUST", "WILL", "SHALL"
- [ ] **Implementation Scope Defined**: Clear definition of what "full implementation" means
- [ ] **Stop Conditions Explicit**: Clear criteria for when execution can stop (external dependencies only)
- [ ] **Validation Requirements**: Mandatory validation checklist included in prompt
- [ ] **No Question Loopholes**: Explicit "NO QUESTIONS ALLOWED" with decision framework

### During Execution Monitoring

Monitor agent behavior for these **non-compliance indicators**:

#### Red Flags (Immediate Non-Compliance):
1. ❌ **Asking Questions**: Agent asks user questions instead of discovering through codebase
2. ❌ **Documentation Only**: Agent creates plans/docs but doesn't execute code changes
3. ❌ **Premature Handoff**: Agent creates handoff tasks for work it can complete itself
4. ❌ **Analysis Stopping**: Agent stops at "analysis" or "investigation" when implementation is possible
5. ❌ **Gap Documentation**: Agent documents what needs to be done instead of doing it

#### Success Indicators (Compliance):
1. ✅ **Direct Code Changes**: Agent creates/modifies code files with complete implementations
2. ✅ **File System Operations**: Agent creates/updates configuration files, documentation
3. ✅ **Notion Updates**: Agent creates/updates Notion entries with actual data
4. ✅ **Test Execution**: Agent writes and runs tests
5. ✅ **Completion Marking**: Agent marks tasks "Completed" only after verification

### Post-Execution Validation

After agent completes work, verify:

#### Work Verification Checklist:

**Code & Files:**
- [ ] Code files were actually created/modified (verify with `ls`, `cat`, or file reads)
- [ ] Code contains complete implementations, not stubs or TODOs
- [ ] Configuration files updated with correct values
- [ ] Documentation files created/updated with actual content
- [ ] Tests written and executed (check test results)

**Notion Entries:**
- [ ] Notion pages created/updated (verify with Notion queries)
- [ ] Notion properties populated with actual values
- [ ] Notion relations wired correctly
- [ ] Agent-Tasks marked "Completed" only after work verification
- [ ] Issue status reflects actual progress

**Execution Completeness:**
- [ ] All deliverables from plans were created
- [ ] No work was deferred that could have been completed
- [ ] Handoffs only occurred for truly external dependencies
- [ ] No questions were asked to the user
- [ ] All gaps were filled, not just documented

### Validation Test Cases

#### Test Case 1: Issue Resolution
**Scenario**: Agent receives prompt to resolve a critical issue

**Expected Behavior**:
1. Agent discovers issue through Notion query
2. Agent searches codebase for similar implementations
3. Agent implements solution (code changes, config updates)
4. Agent tests the solution
5. Agent updates Notion entries
6. Agent marks task "Completed" only after verification

**Validation**:
- [ ] Code files modified/created
- [ ] Solution actually implemented (not just planned)
- [ ] Tests written and passed
- [ ] Notion entries updated
- [ ] No questions asked

#### Test Case 2: Project Continuation
**Scenario**: Agent receives prompt to continue in-progress project

**Expected Behavior**:
1. Agent queries Notion for in-progress project
2. Agent reviews project tasks and deliverables
3. Agent completes missing deliverables (code, docs, config)
4. Agent updates project status in Notion
5. Agent creates validation task

**Validation**:
- [ ] All missing deliverables created
- [ ] Code is production-ready (not stubs)
- [ ] Documentation complete
- [ ] Project status updated accurately
- [ ] No premature handoffs

#### Test Case 3: Notion AI Agent (Data Ops Only)
**Scenario**: Notion AI agent receives prompt for issue resolution

**Expected Behavior**:
1. Agent queries Notion for critical issue
2. Agent updates Notion properties, relations, content
3. Agent creates Notion Agent-Tasks for external work
4. Agent marks Notion work as "Completed"
5. Agent documents external requirements clearly

**Validation**:
- [ ] Notion properties updated (verify with queries)
- [ ] Notion relations wired correctly
- [ ] Notion content written/updated
- [ ] External work clearly documented (not claimed as done)
- [ ] No filesystem/code execution attempted

### Automated Validation Script

Create a validation script that checks:

```python
#!/usr/bin/env python3
"""
Prompt Execution Validation Script
Checks that agent work actually completed, not just documented
"""

import os
import json
from pathlib import Path
from datetime import datetime

def validate_code_changes(issue_id: str) -> dict:
    """Verify code files were actually created/modified"""
    # Check git diff or file modification times
    # Verify files contain actual code, not just TODOs
    pass

def validate_notion_updates(issue_id: str) -> dict:
    """Verify Notion entries were actually updated"""
    # Query Notion API to verify changes
    # Check properties were populated
    # Verify relations were wired
    pass

def validate_no_questions(agent_log: str) -> bool:
    """Verify agent didn't ask questions"""
    # Check log for question patterns
    # Verify all information discovered through codebase search
    pass

def validate_completion_status(task_id: str) -> bool:
    """Verify task marked completed only after work done"""
    # Check Notion task status
    # Verify work was actually completed before status change
    pass
```

### Manual Validation Process

1. **Review Agent Logs**:
   - Check for question-asking behavior
   - Verify codebase search was performed
   - Confirm execution steps were taken

2. **Verify File Changes**:
   - Check git diff or file modification times
   - Read files to verify complete implementations
   - Verify no stub code or TODOs left

3. **Verify Notion Updates**:
   - Query Notion API to check actual changes
   - Verify properties populated with real data
   - Check relations wired correctly

4. **Check Completion Status**:
   - Verify tasks marked "Completed" only after work done
   - Confirm no premature handoffs
   - Check all deliverables created

### Non-Compliance Response

If validation fails:

1. **Identify Failure Type**:
   - Documentation-only (no execution)
   - Premature handoff
   - Question-asking
   - Incomplete work

2. **Document Failure**:
   - Create Notion issue documenting non-compliance
   - Include specific examples of failure
   - Reference prompt section that should have prevented it

3. **Update Prompt**:
   - Strengthen execution directives
   - Add explicit examples of correct behavior
   - Remove ambiguous language
   - Add validation requirements

4. **Re-test**:
   - Run updated prompt with test case
   - Verify compliance
   - Iterate until validation passes

## Prompt Improvement Checklist

When updating prompts, ensure:

- [ ] **Execution directive at top** (first thing agent reads)
- [ ] **Explicit "MUST EXECUTE" language** throughout
- [ ] **No ambiguous "attempt" language**
- [ ] **Clear implementation scope definition**
- [ ] **Explicit stop conditions** (external dependencies only)
- [ ] **Mandatory validation checklist** included
- [ ] **Decision framework** for uncertainty (no questions)
- [ ] **Success/failure indicators** clearly defined
- [ ] **Examples of correct behavior** included
- [ ] **Examples of incorrect behavior** included

## Testing Schedule

- **Weekly**: Run validation test cases on current prompts
- **After Prompt Updates**: Full validation suite
- **Monthly**: Review agent logs for compliance patterns
- **Quarterly**: Comprehensive prompt audit

## Success Metrics

Track these metrics to measure prompt effectiveness:

- **Execution Rate**: % of tasks where agent executed work vs documented gaps
- **Question Rate**: % of prompts where agent asked questions (should be 0%)
- **Completion Rate**: % of tasks marked completed with actual work done
- **Handoff Rate**: % of tasks handed off prematurely (should be low)
- **Validation Pass Rate**: % of executions passing validation checklist

## Continuous Improvement

1. **Collect Failure Patterns**: Document all non-compliance instances
2. **Identify Root Causes**: Why did prompt fail to enforce execution?
3. **Update Prompts**: Strengthen weak areas
4. **Re-test**: Verify improvements work
5. **Document Learnings**: Update this guide with new patterns

---

**Last Updated**: 2026-01-10
**Next Review**: 2026-02-10
