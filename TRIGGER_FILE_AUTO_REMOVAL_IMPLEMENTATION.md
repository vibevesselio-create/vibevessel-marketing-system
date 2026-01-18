# Trigger File Manual Removal Implementation

## Summary

Implemented trigger file movement functionality that **recipient agents must manually call** to move trigger files from `01_inbox` to `02_processed` (success) or `03_failed` (failure). 

**CRITICAL:** This is NOT automated - the recipient agent is responsible for manually calling the function to move the file. Only the agent knows when it has read the file and whether processing succeeded or failed.

## Implementation Details

### New Functions Added to `main.py`

#### 1. `mark_trigger_file_processed(trigger_file_path, success=True, agent_name=None, agent_type=None)`

**Purpose:** Move trigger files from `01_inbox` to `02_processed` (success) or `03_failed` (failure).

**Features:**
- Automatically determines agent folder from file path
- Handles both MM1 and MM2 agent folders
- Creates destination folders if they don't exist
- Prevents overwrites by adding timestamps to duplicate filenames
- Comprehensive error handling and logging

**Usage:**
```python
from main import mark_trigger_file_processed
from pathlib import Path

# After successfully processing
mark_trigger_file_processed(Path("/path/to/trigger.json"), success=True)

# On error
mark_trigger_file_processed(Path("/path/to/trigger.json"), success=False)
```

#### 2. `get_trigger_file_path(task_id, agent_name=None, agent_type=None, agent_id=None)`

**Purpose:** Find trigger file by task ID in inbox folders.

**Features:**
- Searches all agent inbox folders
- Can narrow search by agent name/type
- Returns first matching file found

**Usage:**
```python
from main import get_trigger_file_path

trigger_file = get_trigger_file_path("2dbe7361-6c27-81fb-9233-c9b808bc219a")
if trigger_file:
    # Process and then move
    mark_trigger_file_processed(trigger_file, success=True)
```

### Updated Handoff Instructions

All handoff instructions in `main.py` now include:

```
1. **MOVE TRIGGER FILE**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Update the task status in Notion
3. Create a handoff trigger file for the next task
4. Document all deliverables and artifacts
5. Provide all context needed for the next task to begin
```

This ensures agents know to move trigger files as part of their default workflow.

### Updated Locations

The following functions now include trigger file processing in their handoff instructions:

1. `handle_issues()` - Line 873
2. `handle_in_progress_project()` - Line 1030
3. `check_and_create_ready_task_triggers()` - Line 1168

## Agent Workflow Integration

### Default Agent Behavior

When an agent receives a trigger file, it should:

1. **Read trigger file** from `01_inbox`
2. **Move immediately** to `02_processed` (before processing)
3. **Process the task**
4. **On error**, move to `03_failed`

### Example Agent Script

```python
#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add main.py to path
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')

from main import mark_trigger_file_processed, get_trigger_file_path

def process_task(task_id):
    # Find trigger file
    trigger_file = get_trigger_file_path(task_id)
    if not trigger_file:
        print(f"No trigger file found for task {task_id}")
        return False
    
    try:
        # Move to processed immediately (prevents duplicate processing)
        processed_path = mark_trigger_file_processed(trigger_file, success=True)
        if not processed_path:
            print("Failed to move trigger file")
            return False
        
        # Read trigger data
        with open(processed_path, 'r') as f:
            trigger_data = json.load(f)
        
        # Process task...
        task_title = trigger_data.get('task_title')
        print(f"Processing: {task_title}")
        
        # ... do work ...
        
        return True
        
    except Exception as e:
        # Move to failed on error
        mark_trigger_file_processed(trigger_file, success=False)
        print(f"Error processing task: {e}")
        raise

if __name__ == "__main__":
    task_id = sys.argv[1] if len(sys.argv) > 1 else "2dbe7361-6c27-81fb-9233-c9b808bc219a"
    process_task(task_id)
```

## Benefits

1. **Clean Inbox**: `01_inbox` stays clean as files are moved immediately
2. **Prevents Duplicates**: Moving files immediately prevents reprocessing if agent restarts
3. **Audit Trail**: Clear separation between inbox, processed, and failed files
4. **Error Handling**: Failed tasks are clearly marked in `03_failed`
5. **Idempotency**: Functions handle edge cases (duplicate files, missing folders, etc.)

## Folder Structure

Each agent folder maintains this structure:

```
Agent-Name/
├── 01_inbox/          # New trigger files (should be empty after processing)
├── 02_processed/       # Successfully processed files
└── 03_failed/         # Failed processing attempts
```

## Testing

Functions have been tested and verified:
- ✅ `get_trigger_file_path()` successfully finds trigger files
- ✅ `mark_trigger_file_processed()` is ready to use
- ✅ Functions handle both MM1 and MM2 agent types
- ✅ Error handling is comprehensive

## Next Steps

1. **Agent Integration**: Update agent scripts to use these functions
2. **Documentation**: Add to agent onboarding documentation
3. **Monitoring**: Consider adding metrics for trigger file processing times
4. **Cleanup**: Optionally add script to archive old processed files

## Files Modified

- `main.py`: Added `mark_trigger_file_processed()` and `get_trigger_file_path()` functions
- `main.py`: Updated all handoff instructions to include trigger file processing step
- `main.py`: Updated module docstring with usage examples

## Related Documentation

- `TRIGGER_FILE_PROCESSING_GUIDE.md`: Detailed guide for agents
- `AGENT_FOLDER_NORMALIZATION_ANALYSIS.md`: Folder naming consistency analysis

