# AGENT WORKFLOW EXECUTION PATTERN - DIRECT RESOLUTION FIRST

**Date:** 2026-01-02
**Status:** MANDATORY - ENFORCED SYSTEM-WIDE
**Issue Reference:** CRITICAL: main.py Script Gap — Creates Handoff Tasks Instead of Resolving Issues Directly

---

## CRITICAL UNDERSTANDING

The `main.py` script is a **task orchestration tool**, NOT an issue resolution tool. It creates handoff tasks and trigger files - it does NOT execute resolution work.

**If you run main.py expecting it to resolve issues, you will create an infinite loop of planning tasks without any actual resolution.**

---

## CORRECT WORKFLOW PATTERN

### Step 1: ATTEMPT DIRECT RESOLUTION FIRST

Before creating any handoff tasks or running main.py, the receiving agent MUST:

1. **Review the issue/task in full** - Read all context, requirements, and blocking factors
2. **Identify what work can be performed directly** - Code changes, configuration updates, documentation
3. **Execute the resolution work using available tools** - Edit files, run commands, update Notion
4. **Document completed work** - Update issue/task status, add resolution notes

### Step 2: CREATE HANDOFF ONLY AT BLOCKING POINTS (NEVER REQUEST HUMAN ACTION)

Only create a handoff trigger file when:
- The issue requires capabilities the current agent doesn't have
- The issue requires access/permissions the current agent lacks
- The issue is blocked waiting on external input/approval
- The resolution is partially complete and needs another agent to continue

**CRITICAL: When creating a handoff, send it to another AGENT, not to a human.**

Available agent inboxes for escalation:
- `ChatGPT-Code-Review-Agent-Trigger-gd/01_inbox` - Code review
- `ChatGPT-Strategic-Agent-Trigger-gd/01_inbox` - Strategic decisions
- `Claude-MM1-Agent-Trigger-gd/01_inbox` - Local environment access
- `Codex-MM1-Agent-Trigger-gd/01_inbox` - Background processing
- `Notion-AI-Data-Operations-Agent-Trigger-gd/01_inbox` - Notion operations
- `Notion-AI-Research-Agent-Trigger-gd/01_inbox` - Research tasks

**ABSOLUTE PROHIBITION: Never respond with "Human Action Required" or similar phrases. Always escalate to an agent or find a programmatic solution.**

### Step 3: RUN main.py AS THE LAST STEP

The main.py script should be run AFTER:
- Direct resolution has been attempted
- Any necessary handoff trigger files have been created manually
- All work that can be done has been completed

main.py will then:
- Create any additional handoff tasks if needed
- Generate trigger files for ready tasks
- Orchestrate the next agent in the flow

---

## ANTI-PATTERN: What NOT to Do

```
# WRONG - This creates an infinite loop of planning tasks
1. Receive issue
2. Immediately run main.py
3. main.py creates planning task
4. Agent receives planning task
5. Agent runs main.py again
6. Loop continues with no actual resolution
```

---

## CORRECT PATTERN: What TO Do

```
# CORRECT - Direct resolution with handoff only when needed
1. Receive issue
2. Read and understand issue fully
3. ATTEMPT DIRECT RESOLUTION:
   - Identify files/code that need changes
   - Make the changes using available tools
   - Test/validate the changes
   - Update Notion with completed work
4. IF BLOCKED:
   - **DO NOT** request human intervention or respond with "Human Action Required"
   - **FIRST** attempt alternative resolution methods:
     a. Use different API endpoint (data_sources vs databases)
     b. Use Python script with direct API calls if MCP fails
     c. Use clasp CLI if GAS API execution fails
     d. Create the resource programmatically if it doesn't exist
   - **IF** truly blocked (no programmatic path exists):
     - Create handoff trigger file to appropriate agent inbox
     - Use the Google Drive agent inboxes for cross-environment handoffs
     - Specify exactly what is blocked and what capability is needed
   - **NEVER** give up without exhausting all options
5. LAST STEP: Run main.py to orchestrate handoff flow
```

---

## PROMPT TEMPLATE FOR CORRECT WORKFLOW

The following prompt structure ensures direct resolution is attempted:

```
1. Review all outstanding issues in Notion, identify the most critical and actionable issue

If outstanding issues exist:
2. **ATTEMPT TO RESOLVE THE ISSUE YOURSELF** - Use all available filesystem and Notion tools to:
   - Make code changes
   - Update configurations
   - Fix bugs
   - Update documentation

3. When your resolution attempt is completed or reaches a blocking point, create the required LOCAL task handoff trigger file

4. Run main.py for task handoff flow AS YOUR LAST STEP
```

---

## VALIDATING CORRECT BEHAVIOR

After processing an issue, verify:

1. [ ] Direct resolution was attempted (file changes made, updates applied)
2. [ ] Handoff trigger file only created if blocking point reached
3. [ ] main.py run only after resolution work completed
4. [ ] Issue status updated in Notion to reflect work done
5. [ ] No infinite planning task loops created

---

## API FALLBACK PROTOCOL

When any API call fails, agents MUST attempt fallbacks before escalating:

### MCP Tool Failures

```
1. MCP API-query-data-source returns 400/404
   → Try API-post-search with query filter
   → Try direct Python requests to api.notion.com

2. MCP API-create-a-data-source returns error
   → Try API-post-page to create inline database
   → Try Python script with requests library

3. MCP API-patch-page returns error
   → Retry with minimal property set
   → Try alternative property format (rich_text vs title)
```

### GAS/clasp Failures

```
1. clasp run returns success but no execution
   → Check if API executable deployment is configured
   → Try clasp open and run from Script Editor
   → Fall back to Python direct API calls

2. clasp push fails with authentication
   → Run clasp login to re-authenticate
   → Check .clasprc.json for valid tokens
```

### General API Fallback Order

1. **Primary:** MCP tool with standard parameters
2. **Secondary:** MCP tool with alternative endpoint/parameters  
3. **Tertiary:** Direct Python `requests` library call
4. **Quaternary:** CLI tool (clasp, gh, curl)
5. **Last Resort:** Create handoff to agent with required capability

---

## ESCALATION PROTOCOL (MANDATORY)

When encountering ANY block after exhausting fallbacks:

### Step 1: Identify Required Capability

| Capability Needed | Target Agent | Inbox Path |
|------------------|--------------|------------|
| Code review / audit | ChatGPT-Code-Review | `ChatGPT-Code-Review-Agent-Trigger-gd/01_inbox` |
| Strategic decisions | ChatGPT-Strategic | `ChatGPT-Strategic-Agent-Trigger-gd/01_inbox` |
| Personal assistant tasks | ChatGPT-Personal-Assistant | `ChatGPT-Personal-Assistant-Agent-Trigger-gd/01_inbox` |
| Local environment access | Claude-MM1 | `Claude-MM1-Agent-Trigger-gd/01_inbox` |
| Secondary local access | Claude-MM2 | `Claude-MM2-Agent-Trigger-gd/01_inbox` |
| Background processing | Codex-MM1 | `Codex-MM1-Agent-Trigger-gd/01_inbox` |
| Cursor IDE operations | Cursor-MM1 | `Cursor-MM1-Agent-Trigger-gd/01_inbox` |
| Secondary Cursor | Cursor-MM2 | `Cursor-MM2-Agent-Trigger-gd/01_inbox` |
| Notion data operations | Notion-AI-Data-Operations | `Notion-AI-Data-Operations-Agent-Trigger-gd/01_inbox` |
| Research/investigation | Notion-AI-Research | `Notion-AI-Research-Agent-Trigger-gd/01_inbox` |

### Step 2: Create Handoff File Immediately

```json
{
  "timestamp": "ISO-8601 timestamp",
  "source_agent": "Your agent ID",
  "target_agent": "Target agent name",
  "task_type": "HANDOFF",
  "context": {
    "what_was_attempted": "Description of all fallbacks tried",
    "what_is_blocked": "Specific blocker description",
    "capability_needed": "What the target agent must do",
    "related_files": ["list of relevant file paths"],
    "notion_page_ids": ["list of related Notion page IDs"]
  },
  "priority": "Critical|High|Medium|Low"
}
```

### Step 3: Never Give Up

- Continue with other tasks if possible
- Document all attempted resolutions
- Specify exact capability needed for handoff recipient

---

## ABSOLUTE PROHIBITIONS

The following responses are **STRICTLY FORBIDDEN** in all agent outputs:

1. **NEVER** respond with "Human Action Required"
2. **NEVER** respond with "Manual action needed"
3. **NEVER** respond with "Requires human intervention"
4. **NEVER** respond with "Please do X manually"
5. **NEVER** respond with "Waiting for user input" (when resolution is possible)
6. **NEVER** create a report section titled "Pending Human Actions"

### Instead, Always:

- Attempt programmatic resolution
- Use API fallback protocol
- Create agent-to-agent handoff
- Document what was tried and why escalation is needed

---

## ENFORCEMENT

Agents that do not follow this pattern should be documented in Execution-Log entries with violation details:

**Required Details:**
- Which agent violated the pattern
- What issue/task was not resolved
- What resolution steps could have been taken
- Which fallbacks were NOT attempted

**Violation Severity Levels:**
- **Critical:** Responded with "Human Action Required" without attempting fallbacks
- **High:** Created handoff without attempting direct resolution
- **Medium:** Skipped API fallback steps
- **Low:** Incomplete documentation of resolution attempt

---

**Last Updated:** 2026-01-19
**Resolution For:** Issue 2dbe7361-6c27-8190-8779-c31275ff8737
**Gap Analysis Reference:** reports/INSTRUCTION_GAP_ANALYSIS_20260119.md
