# Prompt Compliance Analysis: Non-Compliant Response Identification

## Issue Summary
The agent asked questions ("When 'attempting to resolve' an issue, what level of implementation should I perform?") despite explicit "NO QUESTIONS ALLOWED" directives in the prompts.

## Root Causes Identified

### 1. **Missing Implementation Level Specification**
**Problem:** Neither prompt explicitly defines what "attempting to resolve" means in terms of implementation depth.

**Evidence:**
- RTF Prompt (line 159): "attempt to identify and implement a solution to resolve this issue yourself"
- RTF Prompt (line 166): "attempt to complete this task yourself"
- **Missing:** Clear definition of implementation scope (full vs partial vs analysis-only)

**Impact:** Agent lacks clear guidance on how far to go, leading to uncertainty and question-asking behavior.

**Recommendation:** Add explicit implementation level specification:
```
IMPLEMENTATION LEVEL (MANDATORY):
- For issue resolution: Perform FULL implementation (code changes, testing, documentation)
- For project continuation: Complete ALL deliverables specified in the plan
- Only stop if blocked by external dependencies or permissions
- Default to production-ready code unless explicitly specified otherwise
```

### 2. **Conflicting Scope Instructions in Notion AI Prompt**
**Problem:** The Notion AI Data Operations prompt references filesystem paths and execution work, contradicting its "Notion-only" constraint.

**Evidence:**
- Line 8: "No code or CLI execution. No filesystem or local‑machine access"
- Line 48: References `/Users/brianhellemn/Projects/github-production/plans/` directory
- Line 51: "ACTUALLY CREATE THEM (code, config, docs, Notion entries)"
- Line 59: "If code is missing: CREATE the code file"

**Impact:** Creates confusion about what the agent can actually do, leading to uncertainty and question-asking.

**Recommendation:** 
- Remove filesystem references from Notion AI prompt
- Clarify that Notion AI agent should ONLY document execution requirements, not perform them
- Add explicit boundary markers: "STOP HERE - External execution required"

### 3. **Ambiguous "Attempt" Language**
**Problem:** The word "attempt" creates ambiguity about commitment level and success criteria.

**Evidence:**
- RTF Prompt line 159: "attempt to identify and implement"
- RTF Prompt line 166: "attempt to complete this task yourself"
- RTF Prompt line 161: "When your attempt...is completed or has reached a blocking point"

**Impact:** "Attempt" suggests optional/exploratory work rather than mandatory completion, leading to premature handoffs and questions.

**Recommendation:** Replace "attempt" with stronger directive language:
```
MANDATORY EXECUTION REQUIREMENT:
- You MUST implement the solution completely before handoff
- Only proceed to handoff if blocked by:
  1. External API dependencies (not available in your environment)
  2. Permission/authentication failures (after retry)
  3. Missing critical information (after exhaustive codebase search)
```

### 4. **Incomplete Context Discovery Checklist**
**Problem:** The checklist doesn't include all information needed to proceed without questions.

**Evidence:**
- RTF Prompt lines 70-86: Information Discovery Checklist
- **Missing items:**
  - Implementation level/scope definition
  - Success criteria for "completion"
  - When to stop vs when to continue
  - Default values for ambiguous parameters

**Recommendation:** Expand checklist to include:
```
- [ ] Determined implementation level (full/partial/analysis) from codebase patterns
- [ ] Identified success criteria for task completion
- [ ] Located similar implementations to understand expected scope
- [ ] Verified default values for any ambiguous parameters
```

### 5. **Trigger File Instructions Ambiguity**
**Problem:** The prompt mentions "folder_resolver module" but doesn't specify when/how to use it, leading to question #2 in the image.

**Evidence:**
- RTF Prompt lines 172-177: Trigger file paths are hardcoded
- folder_resolver.py exists and provides dynamic path resolution
- Prompt doesn't mention folder_resolver module usage

**Impact:** Agent unsure whether to use hardcoded paths or dynamic resolution, leading to questions.

**Recommendation:** Add explicit instruction:
```
TRIGGER FILE CREATION:
- Use folder_resolver module for path resolution (preferred method)
- Import: from shared_core.notion.folder_resolver import get_agent_inbox_path
- Fallback to hardcoded paths only if folder_resolver unavailable
- Always verify path exists before creating trigger file
```

### 6. **Weak Enforcement of "No Questions" Directive**
**Problem:** While "NO QUESTIONS ALLOWED" is stated, there's no explicit consequence or alternative guidance when uncertainty arises.

**Evidence:**
- RTF Prompt line 10: "MANDATORY CONTEXT DISCOVERY - NO QUESTIONS ALLOWED"
- RTF Prompt line 88: "DO NOT ask questions...use fallback values or proceed with best-effort defaults"
- **Missing:** Explicit decision tree for handling uncertainty

**Impact:** Agent defaults to asking questions when uncertain rather than using fallbacks.

**Recommendation:** Add explicit decision framework:
```
UNCERTAINTY RESOLUTION (MANDATORY):
When information is unclear or missing:
1. Search codebase for similar patterns/examples (MANDATORY FIRST STEP)
2. Use production-safe defaults (MANDATORY SECOND STEP)
3. Document assumption in Notion issue/task (MANDATORY THIRD STEP)
4. Proceed with execution (MANDATORY FOURTH STEP)
5. NEVER ask user questions - create Notion issue if clarification needed
```

### 7. **Plan Directory Review Contradiction**
**Problem:** The Notion AI prompt requires reviewing a filesystem directory it cannot access.

**Evidence:**
- Notion AI Prompt line 48: "review the most recent plan files in `/Users/brianhellemn/Projects/github-production/plans/`"
- Notion AI Prompt line 8: "No filesystem or local‑machine access"
- Notion AI Prompt line 51: "ACTUALLY CREATE THEM (code, config, docs)"

**Impact:** Creates impossible requirement, leading to confusion and question-asking.

**Recommendation:** 
- Remove filesystem access requirements from Notion AI prompt
- Replace with: "Query Notion for plan-related pages/databases"
- Clarify: "Document execution requirements in Notion, do not execute code/filesystem operations"

## Specific Non-Compliance Issues

### Question 1: "What level of implementation should I perform?"
**Root Cause:** Missing implementation level specification (Issue #1 above)

**Fix Required:**
```markdown
## IMPLEMENTATION SCOPE (MANDATORY)

When resolving issues or continuing projects, you MUST:

1. **Full Implementation Required:**
   - Write complete, production-ready code
   - Include error handling and logging
   - Add/update documentation
   - Create or update tests where applicable
   - Update Notion entries with completion status

2. **Stop Only If:**
   - Blocked by external API/service unavailable in your environment
   - Missing critical credentials/permissions (after retry)
   - Requires human decision that cannot be inferred from codebase

3. **Default Behavior:**
   - Assume full implementation unless issue explicitly states "analysis only" or "plan only"
   - Complete all deliverables mentioned in plans
   - Do not handoff prematurely - complete your full scope first
```

### Question 2: "For trigger files, should I use the folder_resolver module..."
**Root Cause:** Ambiguous trigger file creation instructions (Issue #5 above)

**Fix Required:**
```markdown
## TRIGGER FILE CREATION (MANDATORY)

1. **Path Resolution (MANDATORY FIRST STEP):**
   ```python
   from shared_core.notion.folder_resolver import get_agent_inbox_path
   inbox_path = get_agent_inbox_path(agent_name)
   ```

2. **Fallback (if folder_resolver unavailable):**
   - MM1 Agents: /Users/brianhellemn/Documents/Agents/Agent-Triggers/{agent-folder}/01_inbox
   - MM2 Agents: /Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd/{agent-folder}-gd/01_inbox

3. **Content Requirements:**
   - Include downstream handoff awareness
   - Specify next agent and handoff instructions
   - Include task completion and documentation requirements
   - Reference related Notion entries (Issue/Project/Task IDs)
```

## Recommended Prompt Improvements

### For RTF Prompt (Cursor/Claude Agents):
1. Add explicit "IMPLEMENTATION SCOPE" section at the top
2. Replace all "attempt" language with "MUST complete"
3. Add "UNCERTAINTY RESOLUTION" decision framework
4. Expand Information Discovery Checklist
5. Add explicit trigger file creation instructions with folder_resolver usage

### For Notion AI Prompt:
1. Remove all filesystem path references
2. Remove code/file creation instructions
3. Add explicit "NOTION-ONLY BOUNDARY" markers
4. Clarify that execution work must be documented, not performed
5. Replace plan directory review with Notion database queries

## Compliance Verification Checklist

After implementing fixes, verify:
- [ ] No ambiguous "attempt" language remains
- [ ] Implementation level explicitly defined
- [ ] Uncertainty resolution framework present
- [ ] Trigger file instructions reference folder_resolver
- [ ] Notion AI prompt has no filesystem/code execution requirements
- [ ] "NO QUESTIONS ALLOWED" reinforced with decision framework
- [ ] All fallback values specified for common scenarios
