# CRITICAL SYSTEM REQUIREMENTS - NEVER FORGET

**Date:** 2025-12-31  
**Status:** ✅ SYSTEM-ENFORCED  
**Purpose:** These requirements are SO CRITICAL that they must be system-enforced and impossible to forget.

---

## 🚨 REQUIREMENT #1: MANDATORY NEXT HANDOFF INSTRUCTIONS

**EVERY Agent-Task description MUST include explicit instructions for the execution agent to create the NEXT task's handoff trigger file upon completion.**

### System Enforcement

**File:** `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`

**Functions:**
- `add_mandatory_next_handoff_instructions()` - Automatically adds next handoff section
- `create_task_description_with_next_handoff()` - Creates complete description with handoff
- `create_handoff_json_data()` - Creates handoff JSON with mandatory next handoff

**Usage:**
```python
from shared_core.notion.task_creation import add_mandatory_next_handoff_instructions

description = add_mandatory_next_handoff_instructions(
    description=base_description,
    next_task_name="Next Task Name",  # MANDATORY
    target_agent="Target Agent Name",  # MANDATORY
    next_task_id="task-id",
    inbox_path="/absolute/path/to/inbox/",
    project_name="Project Name"
)
```

**ALL task creation scripts MUST:**
1. Import from `shared_core.notion.task_creation`
2. Use helper functions to add next handoff instructions
3. Pass `next_task_name` and `next_target_agent` to `create_task()` functions

---

## 🚨 REQUIREMENT #2: ENVIRONMENT MANAGEMENT PATTERN

**ALL scripts that access Notion MUST use the correct environment management pattern.**

### System Enforcement

**File:** `/Users/brianhellemn/Projects/github-production/docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`

**Pattern:**
```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv  # MANDATORY

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()  # MANDATORY - Must be called before checking env vars

def get_notion_token() -> Optional[str]:
    """Get Notion API token from environment or unified_config"""
    # Check environment first
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if token:
        return token
    
    # Fallback to unified_config
    try:
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        return token
    except Exception:
        return None
```

**ALL scripts MUST:**
1. Import `load_dotenv` from `dotenv`
2. Call `load_dotenv()` after adding project root to path
3. Check all three env vars: NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN
4. Include unified_config fallback with try/except

---

## How to Remember These Requirements

### For Next Handoff Instructions:
1. **ALWAYS** import from `shared_core.notion.task_creation`
2. **ALWAYS** use helper functions when creating tasks
3. **ALWAYS** pass `next_task_name` and `next_target_agent` parameters
4. **NEVER** create a task description without next handoff instructions

### For Environment Management:
1. **ALWAYS** check `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md` before creating scripts
2. **ALWAYS** copy the exact pattern from the documentation
3. **ALWAYS** use the helper functions from `shared_core.notion.task_creation` if available
4. **NEVER** create custom token retrieval functions

---

## Files to Reference

**Before creating ANY task:**
- `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`
- `/Users/brianhellemn/Projects/github-production/docs/agents/AGENT_HANDOFF_TASK_GENERATOR_V3.0.md`

**Before creating ANY script:**
- `/Users/brianhellemn/Projects/github-production/docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`
- `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`

---

## Validation Checklist

**Before creating a task:**
- [ ] Imported from `shared_core.notion.task_creation`
- [ ] Used helper function to add next handoff instructions
- [ ] Passed `next_task_name` parameter
- [ ] Passed `next_target_agent` parameter
- [ ] Description contains "MANDATORY HANDOFF REQUIREMENT"

**Before creating a script:**
- [ ] Imported `load_dotenv` from `dotenv`
- [ ] Called `load_dotenv()` after path setup
- [ ] Token function checks all three env vars
- [ ] Token function includes unified_config fallback
- [ ] Error message uses correct format

---

**Last Updated:** 2025-12-31  
**Status:** ✅ SYSTEM-ENFORCED - REFERENCE THIS BEFORE EVERY TASK/SCRIPT CREATION











































































































