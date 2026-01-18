# Trigger File Processing Guide

## Overview

**CRITICAL:** When agents receive trigger files in their `01_inbox` folder, they **MUST manually** move them to `02_processed` (on success) or `03_failed` (on failure). This cannot be automated - the recipient agent is responsible for moving the file.

## Implementation

### Functions Available

The `main.py` script provides two utility functions for trigger file management:

#### 1. `mark_trigger_file_processed(trigger_file_path, success=True, agent_name=None, agent_type=None)`

Moves a trigger file from `01_inbox` to `02_processed` (success) or `03_failed` (failure).

**Parameters:**
- `trigger_file_path`: Path to the trigger file (can be relative or absolute)
- `success`: `True` to move to `02_processed`, `False` to move to `03_failed`
- `agent_name`: Optional agent name for logging
- `agent_type`: Optional agent type "MM1" or "MM2"

**Returns:**
- Path to the moved file, or `None` if failed

**Example:**
```python
from main import mark_trigger_file_processed

# After successfully processing a trigger file
mark_trigger_file_processed("/path/to/trigger/file.json", success=True)

# On error
mark_trigger_file_processed("/path/to/trigger/file.json", success=False)
```

#### 2. `get_trigger_file_path(task_id, agent_name=None, agent_type=None, agent_id=None)`

Finds a trigger file by task ID in the inbox folders.

**Parameters:**
- `task_id`: Task ID to search for
- `agent_name`: Optional agent name to narrow search
- `agent_type`: Optional agent type "MM1" or "MM2"
- `agent_id`: Optional agent ID for normalization

**Returns:**
- Path to trigger file if found, `None` otherwise

**Example:**
```python
from main import get_trigger_file_path

# Find trigger file by task ID
trigger_file = get_trigger_file_path(task_id="2dbe7361-6c27-81fb-9233-c9b808bc219a")
if trigger_file:
    # Process the file
    # ...
    # Move to processed
    mark_trigger_file_processed(trigger_file, success=True)
```

## Default Agent Workflow

### Step 1: Read Trigger File

When an agent starts, it should:
1. Check its `01_inbox` folder for trigger files
2. Read the trigger file (JSON format)
3. Extract task details from the file

### Step 2: Move to Processing (MANUAL - Agent Must Do This)

**IMMEDIATELY** after reading the trigger file, **you MUST manually** move it to `02_processed`:

```python
from main import mark_trigger_file_processed

# Read trigger file
trigger_file = Path("/Users/brianhellemn/Documents/Agents/Agent-Triggers/Claude-MM1-Agent/01_inbox/20260101T191136Z__HANDOFF__...json")

# Move to processed folder (do this FIRST, before processing)
mark_trigger_file_processed(trigger_file, success=True)
```

**Why move immediately?**
- Prevents duplicate processing if the agent is restarted
- Keeps inbox clean
- Provides clear audit trail

**IMPORTANT:** This is a **manual step** that the agent must perform. The system cannot automatically move files - only the agent knows when it has read and is ready to process the file.

### Step 3: Process Task

Process the task as described in the trigger file.

### Step 4: Handle Errors

If an error occurs during processing:

```python
# Move to failed folder
mark_trigger_file_processed(trigger_file, success=False)
```

## Folder Structure

Each agent folder should have this structure:

```
Agent-Name/
├── 01_inbox/          # New trigger files arrive here
├── 02_processed/       # Successfully processed files
└── 03_failed/         # Failed processing attempts
```

## Integration with Agent Scripts

### For Python Agents

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

# Add main.py to path
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')

from main import mark_trigger_file_processed, get_trigger_file_path

# Example: Process trigger file
def process_trigger_file(trigger_file_path):
    try:
        # Move to processed immediately
        processed_path = mark_trigger_file_processed(trigger_file_path, success=True)
        if not processed_path:
            print("Failed to move trigger file")
            return False
        
        # Read and process
        with open(processed_path, 'r') as f:
            trigger_data = json.load(f)
        
        # Process task...
        task_id = trigger_data.get('task_id')
        # ... do work ...
        
        return True
        
    except Exception as e:
        # Move to failed on error
        mark_trigger_file_processed(trigger_file_path, success=False)
        raise
```

### For Shell Scripts

```bash
#!/bin/bash

# Find trigger file by task ID
TRIGGER_FILE=$(python3 -c "
import sys
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')
from main import get_trigger_file_path
path = get_trigger_file_path('$TASK_ID')
print(path) if path else exit(1)
")

# Move to processed
python3 -c "
import sys
sys.path.insert(0, '/Users/brianhellemn/Projects/github-production')
from main import mark_trigger_file_processed
from pathlib import Path
mark_trigger_file_processed(Path('$TRIGGER_FILE'), success=True)
"

# Process task...
```

## Best Practices

1. **Manual Move Required**: You MUST manually call `mark_trigger_file_processed()` - this cannot be automated**
2. **Move Immediately**: Move trigger file to `02_processed` as soon as you start processing it
3. **Handle Errors**: Always move to `03_failed` if processing fails
4. **Idempotency**: The move function handles duplicate files by adding timestamps
5. **Logging**: The function logs all moves for audit trail
6. **Clean Inbox**: Keep `01_inbox` clean by moving files immediately

**Remember:** The recipient agent is responsible for moving the file. This is not automated - you must explicitly call the function.

## Updated Handoff Instructions

All handoff instructions in `main.py` now include:

```
1. **MOVE TRIGGER FILE**: Call mark_trigger_file_processed() to move the trigger file from 01_inbox to 02_processed
2. Update the task status in Notion
3. Create a handoff trigger file for the next task
4. Document all deliverables and artifacts
5. Provide all context needed for the next task to begin
```

This ensures agents know to move trigger files as part of their default workflow.

