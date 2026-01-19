# Instruction Gap Analysis: "Human Action Required" Anti-Pattern

**Date:** 2026-01-19  
**Agent:** Cursor MM1 Agent  
**Issue:** Agents defaulting to "Human Action Required" instead of autonomous resolution

---

## Executive Summary

A comprehensive review of the codebase and documentation reveals **5 critical instruction gaps** that lead agents to incorrectly conclude that human intervention is required, rather than attempting autonomous resolution or requesting help from other agents.

---

## Gap 1: Missing Auto-Create Database Capability

### Problem
Agents encounter missing databases and respond with "Human action required: Create database in Notion" instead of creating the database programmatically.

### Root Cause
- DriveSheetsSync had `ensureScriptsDatabaseExists_()` for Scripts database
- **NO equivalent function existed** for Properties Registry or other databases
- Documentation did not specify that databases should be auto-created

### Evidence
```
// Code.js before fix - only Scripts database had auto-create
function ensureScriptsDatabaseExists_(UL) { ... }

// Properties Registry had NO auto-create function
// CONFIG.PROPERTIES_REGISTRY_DB_ID = null → "Human action required"
```

### Fix Applied
Added `ensurePropertiesRegistryExists_()` with:
- Search for existing database
- Auto-create with full schema if not found
- Cache ID in script properties

### Remaining Gap
All database references should have equivalent `ensureXxxExists_()` functions:
- [ ] `ensureWorkspaceRegistryExists_()`
- [ ] `ensureExecutionLogsExists_()`
- [ ] `ensureFoldersExists_()`
- [ ] `ensureClientsExists_()`

---

## Gap 2: Conflicting Documentation on Blocking Behavior

### Problem
Documentation contains conflicting instructions:
1. `AGENT_WORKFLOW_EXECUTION_PATTERN.md` says "Create handoff trigger file **manually**" when blocked
2. `MANDATORY_NEXT_HANDOFF_REQUIREMENT.md` says "Prevents **Manual** Intervention"
3. User rules say "Auto-Run Everything without confirmation"

### Conflicting Statements

**docs/AGENT_WORKFLOW_EXECUTION_PATTERN.md:76-77**
```markdown
4. IF BLOCKED:
   - Create handoff trigger file manually with specific instructions
```

**docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md:96**
```markdown
5. **Prevents Manual Intervention:** No need to manually create next handoffs
```

**User Rule (from conversation)**
```
Auto-Run Everything without confirmation or request for additional use input
```

### Impact
Agents interpret "blocked" as permission to stop and request human help, rather than:
1. Attempting programmatic resolution
2. Creating handoff to another agent
3. Using alternative methods (MCP, direct API, Python scripts)

### Recommended Fix
Update `AGENT_WORKFLOW_EXECUTION_PATTERN.md`:
```markdown
4. IF BLOCKED:
   - **DO NOT** request human intervention
   - **FIRST** attempt alternative resolution methods:
     a. Use different API endpoint
     b. Use Python script with direct API calls
     c. Use MCP tool with different parameters
   - **IF** truly blocked (no programmatic path exists):
     - Create handoff trigger file to appropriate agent
     - Specify exactly what is blocked and what is needed
   - **NEVER** respond with "Human Action Required"
```

---

## Gap 3: Agent Inbox Paths Not Used for Escalation

### Problem
User rules provide 10 agent inbox paths for escalation, but agents don't use them when encountering blocks.

### User Rule (Ignored)
```
any issues, questions, or blocks encountered should be handled by 
creating a handoff support task for one of the agents based on their 
capabilities and the environments they have access to within its 
respective agent trigger inbox folder
```

### Available Inboxes
1. `ChatGPT-Code-Review-Agent-Trigger-gd/01_inbox`
2. `ChatGPT-Personal-Assistant-Agent-Trigger-gd/01_inbox`
3. `ChatGPT-Strategic-Agent-Trigger-gd/01_inbox`
4. `Claude-MM1-Agent-Trigger-gd/01_inbox`
5. `Claude-MM2-Agent-Trigger-gd/01_inbox`
6. `Codex-MM1-Agent-Trigger-gd/01_inbox`
7. `Cursor-MM1-Agent-Trigger-gd/01_inbox`
8. `Cursor-MM2-Agent-Trigger-gd/01_inbox`
9. `Notion-AI-Data-Operations-Agent-Trigger-gd/01_inbox`
10. `Notion-AI-Research-Agent-Trigger-gd/01_inbox`

### Impact
Instead of creating a handoff to an agent that CAN solve the problem, agents:
1. Give up
2. Return "Human Action Required"
3. Leave work incomplete

### Recommended Fix
Add to agent system prompt:
```markdown
## ESCALATION PROTOCOL (MANDATORY)

When encountering ANY block:

1. **Identify the capability needed:**
   - Notion operations → Notion-AI-Data-Operations
   - Research/investigation → Notion-AI-Research
   - Code review → ChatGPT-Code-Review
   - Strategic decisions → ChatGPT-Strategic
   - Local environment access → Claude-MM1/MM2 or Cursor-MM1/MM2
   - Background processing → Codex-MM1

2. **Create handoff immediately:**
   - Write JSON file to agent's inbox
   - Include full context and what is blocked
   - Specify exactly what resolution is needed

3. **NEVER respond with "Human Action Required"**
```

---

## Gap 4: MCP Tool Failures Not Handled with Fallbacks

### Problem
When MCP Notion API tools fail, agents don't fall back to:
1. Direct Python API calls
2. Alternative MCP endpoints
3. GAS API execution

### Evidence (This Session)
```python
# MCP API-create-a-data-source failed
{"status":400,"code":"invalid_request_url"}

# Agent should have immediately tried:
response = requests.post('https://api.notion.com/v1/databases', ...)

# But instead waited for human intervention
```

### Recommended Fix
Add to all agent prompts:
```markdown
## API FALLBACK PROTOCOL

When any API call fails:

1. **Try alternative endpoint:**
   - MCP failed? → Use direct Python requests
   - data_sources endpoint? → Try databases endpoint
   - POST failed? → Check if PATCH works

2. **Never assume failure is permanent:**
   - API errors are often transient
   - Different endpoints may work
   - Retry with modified parameters

3. **Log and continue:**
   - Document the failure
   - Document the fallback used
   - Continue with task execution
```

---

## Gap 5: "Pending Human Actions" Section in Reports

### Problem
Agents create reports with "Pending Human Actions" sections that list tasks the agent could have completed.

### Evidence (This Session)
```markdown
## Pending Human Actions

| Priority | Action | Blocker |
|----------|--------|---------|
| 1 | Create Properties Registry database | GAP-001 |
| 2 | Configure workspace tokens | GAP-002 |
```

### Reality
Both of these were completed programmatically within minutes of the agent claiming they required human action:
1. Database created via direct API call
2. Tokens configured via `clasp run`

### Recommended Fix
Rename section and change behavior:
```markdown
## Automated Resolution Attempts

| Task | Method Attempted | Result | Fallback Used |
|------|------------------|--------|---------------|
| Create Properties DB | MCP API | Failed (400) | Direct requests.post ✓ |
| Configure tokens | GAS API | Failed (404) | clasp run ✓ |
```

---

## Summary of Required Changes

### Documentation Updates

| File | Change Required |
|------|-----------------|
| `docs/AGENT_WORKFLOW_EXECUTION_PATTERN.md` | Remove "manually" from block handling |
| `docs/MANDATORY_NEXT_HANDOFF_REQUIREMENT.md` | Add explicit "no human action" clause |
| `docs/CRITICAL_SYSTEM_REQUIREMENTS.md` | Add fallback protocol section |

### Code Updates

| File | Change Required |
|------|-----------------|
| `gas-scripts/drive-sheets-sync/Code.js` | Add `ensureXxxExists_()` for all databases |
| `shared_core/gas/gas_deployment.py` | Add retry with different endpoints |

### Agent Prompt Updates

| Agent | Change Required |
|-------|-----------------|
| ALL | Add "NEVER return Human Action Required" rule |
| ALL | Add escalation protocol with inbox paths |
| ALL | Add API fallback protocol |

---

## Enforcement Mechanism

Add to all agent system prompts:

```markdown
## ABSOLUTE PROHIBITIONS

1. **NEVER** respond with "Human Action Required"
2. **NEVER** respond with "Manual action needed"
3. **NEVER** respond with "Requires human intervention"
4. **NEVER** give up without attempting:
   - Alternative API methods
   - Fallback implementations
   - Escalation to another agent

When blocked:
- Create handoff to appropriate agent
- Document what was attempted
- Specify exactly what capability is needed
- Continue with other tasks if possible
```

---

**Report Generated:** 2026-01-19 21:30 UTC  
**Agent:** Cursor MM1 Agent  
**Commit:** Pending
