# Agent-Triggers Folder Naming Inconsistency Analysis

## Problem Summary

Duplicate and varying format folder names exist in `/Users/brianhellemn/Documents/Agents/Agent-Triggers/` due to inconsistent agent name handling.

## Root Causes Identified

### 1. **Notion Database Inconsistency**
Agent names in the Agents database (Notion) have inconsistent titles:
- `"Claude MM1 Agent"` → Creates folder: `Claude-MM1-Agent`
- `"Claude MM1 Agent-Trigger"` → Creates folder: `Claude-MM1-Agent-Trigger`
- `"Claude-MM1-Agent-Trigger"` → Creates folder: `Claude-MM1-Agent-Trigger`
- `"Claude-MM1"` → Creates folder: `Claude-MM1`
- `"CursorMM1"` → Creates folder: `CursorMM1`

### 2. **Code Issue in main.py (line 327)**
The folder name is created with minimal sanitization:
```python
agent_folder = agent_name.replace(" ", "-").replace("/", "-")
```

**Problems:**
- ❌ Doesn't remove "-Trigger" suffixes
- ❌ Doesn't remove "-Agent-Trigger" suffixes  
- ❌ Doesn't standardize format
- ❌ Doesn't handle inconsistent hyphenation (ChatGPT vs Chat-GPT)
- ❌ Doesn't map known agent IDs to canonical names

### 3. **No Normalization Function**
There's no centralized function to normalize agent names before creating folders.

### 4. **Multiple Creation Points**
Folders are created in multiple places without consistent normalization:
- `main.py: create_trigger_file()` (line 327)
- `main.py: handle_in_progress_project()` (line 839)
- `main.py: check_and_create_ready_task_triggers()` (line 839)
- Possibly other scripts or manual creation

## Duplicate Folders Found

| Base Agent | Variations |
|------------|------------|
| Claude Code | `Claude-Code-Agent`, `Claude-Code-Agent-Trigger` |
| Claude MM1 | `Claude-MM1-Agent`, `Claude-MM1-Agent-Trigger` |
| Claude MM2 | `Claude-MM2`, `Claude-MM2-Agent-Trigger` |
| Codex MM1 | `Codex-MM1-Agent`, `Codex-MM1-Agent-Trigger` |
| Cursor MM1 | `Cursor-MM1`, `Cursor-MM1-Agent`, `Cursor-MM1-Agent-Trigger`, `CursorMM1` |
| Notion AI Data Operations | `Notion-AI-Data-Operations-Agent`, `Notion-AI-Data-Operations-Agent-Trigger`, `Notion-AI-Data-Operations-Agent-Agent-Trigger` |
| Notion AI Research | `Notion-AI-Research-Agent`, `Notion-AI-Research-Agent-Trigger` |

## Solution

### Step 1: Create Normalization Function

Add `normalize_agent_folder_name()` function that:
1. Removes common suffixes: `-Trigger`, `-Agent-Trigger`, `-Agent-Agent-Trigger`, `-Agent`
2. Standardizes format: Always use `Agent-Name` format (e.g., `Claude-MM1-Agent`)
3. Maps known agent IDs to canonical names
4. Handles edge cases:
   - `ChatGPT` vs `Chat-GPT` → `ChatGPT`
   - `CursorMM1` vs `Cursor-MM1` → `Cursor-MM1-Agent`
   - Removes duplicate words (e.g., `Agent-Agent`)

### Step 2: Update All Folder Creation Code

Replace all instances of:
```python
agent_folder = agent_name.replace(" ", "-").replace("/", "-")
```

With:
```python
agent_folder = normalize_agent_folder_name(agent_name, agent_id)
```

### Step 3: Agent ID to Canonical Name Mapping

Create a mapping for known agent IDs:
```python
AGENT_ID_TO_CANONICAL_NAME = {
    "fa54f05c-e184-403a-ac28-87dd8ce9855b": "Claude-MM1-Agent",
    "249e7361-6c27-8100-8a74-de7eabb9fc8d": "Cursor-MM1-Agent",
    # ... add more as needed
}
```

### Step 4: (Optional) Migration Script

Create a script to:
1. Identify duplicate folders
2. Consolidate trigger files from duplicates into canonical folder
3. Archive or remove duplicate folders
4. Update any references in code/docs

## Implementation Priority

1. **HIGH**: Add normalization function to prevent future duplicates
2. **MEDIUM**: Update all folder creation code to use normalization
3. **LOW**: Create migration script to consolidate existing duplicates

## Files to Update

- `main.py`: 
  - Add `normalize_agent_folder_name()` function (after line 285)
  - Update `create_trigger_file()` (line 327)
  - Update `handle_in_progress_project()` (line 839)
  - Update `check_and_create_ready_task_triggers()` (line 839)



















































































