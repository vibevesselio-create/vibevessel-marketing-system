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

### Step 2: CREATE HANDOFF ONLY AT BLOCKING POINTS

Only create a handoff trigger file when:
- The issue requires capabilities the current agent doesn't have
- The issue requires access/permissions the current agent lacks
- The issue is blocked waiting on external input/approval
- The resolution is partially complete and needs another agent to continue

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
   - Create handoff trigger file manually with specific instructions
   - Include all context and work completed so far
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

## ENFORCEMENT

Agents that do not follow this pattern should be documented in Execution-Log entries with violation details:

**Required Details:**
- Which agent violated the pattern
- What issue/task was not resolved
- What resolution steps could have been taken

---

**Last Updated:** 2026-01-02
**Resolution For:** Issue 2dbe7361-6c27-8190-8779-c31275ff8737
