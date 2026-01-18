# Continuous Task Handoff Processor

## Overview

The `continuous_task_handoff_processor.py` script continuously processes tasks from the Notion **Agent-Tasks** database, creating handoff trigger files in the appropriate agent's `01_inbox` folder. It runs until all tasks are completed.

## Features

- **Automatic Task Selection**: Queries Notion for highest-priority incomplete tasks
- **Smart Agent Assignment**: Uses the task's assigned agent from Notion
- **Duplicate Prevention**: Skips tasks that already have trigger files
- **Status Updates**: Automatically updates task status to "In Progress" when trigger file is created
- **Continuous Processing**: Runs in a loop until 0 incomplete tasks remain
- **Priority Sorting**: Processes tasks in priority order (Critical > High > Medium > Low)

## Usage

### Single Task Processing

Process one task and exit:

```bash
python3 scripts/continuous_task_handoff_processor.py --once
```

### Continuous Processing

Run continuously, checking for new tasks every 30 seconds (default):

```bash
python3 scripts/continuous_task_handoff_processor.py
```

### Custom Interval

Run continuously with a custom interval (e.g., 60 seconds):

```bash
python3 scripts/continuous_task_handoff_processor.py --interval 60
```

## How It Works

1. **Query Notion**: Retrieves all tasks from Agent-Tasks database
2. **Filter Ready Tasks**: Identifies tasks that are:
   - Not completed
   - Have an assigned agent
   - Status is "Ready", "Not Started", "In Progress", etc.
3. **Sort by Priority**: Orders tasks by priority (Critical > High > Medium > Low)
4. **Check for Existing Triggers**: Skips tasks that already have trigger files
5. **Create Handoff File**: Creates a JSON trigger file in the assigned agent's `01_inbox` folder
6. **Update Status**: Updates task status to "In Progress" in Notion
7. **Repeat**: Continues until 0 incomplete tasks remain

## Trigger File Format

Trigger files are created as JSON files in the format:

```
{timestamp}__HANDOFF__{task_title}__{task_id_short}.json
```

Example:
```
20260106T160720Z__HANDOFF__Create-Orchestration-Log-Database-and-Deploy-Orche__2b6e7361.json
```

## Task Completion Flow

When an agent completes a task:

1. **Move Trigger File**: Agent manually calls `mark_trigger_file_processed()` to move file from `01_inbox` to `02_processed`
2. **Update Notion**: Agent updates task status to "Completed" in Notion
3. **Create Review Handoff** (if needed): Agent creates a handoff trigger file for review agent (typically Claude MM1 Agent)
4. **Document**: Agent documents all deliverables and artifacts

## Agent Assignment

Tasks are assigned to agents based on:
- The **Assigned-Agent** property in the Notion task
- Agent capabilities and environment (MM1 vs MM2)
- Task requirements and agent specializations

## Configuration

### Environment Variables

- `NOTION_TOKEN` or `NOTION_API_TOKEN`: Required for Notion API access
- `AGENT_TASKS_DB_ID`: Optional, defaults to `284e73616c278018872aeb14e82e0392`

### Database ID

The script uses the Agent-Tasks database ID:
- Default: `284e73616c278018872aeb14e82e0392`
- Can be overridden with `AGENT_TASKS_DB_ID` environment variable

## Logging

The script logs to:
- **Console**: Real-time processing information
- **File**: `continuous_task_handoff_processor.log` in the project root

## Stopping the Process

- Press `Ctrl+C` to stop continuous processing
- The script will complete the current cycle and exit gracefully
- A summary of processed tasks will be displayed

## Example Output

```
================================================================================
CONTINUOUS TASK HANDOFF PROCESSOR
================================================================================
Agent-Tasks Database ID: 284e73616c278018872aeb14e82e0392
Processing Interval: 30 seconds
================================================================================

🔄 Cycle 1 - 2026-01-06 16:07:20
📊 Incomplete tasks remaining: 27

================================================================================
PROCESSING NEXT TASK
================================================================================
Task: Create Orchestration Log Database and Deploy Orchestration Launcher
Priority: Critical
Assigned Agent: Notion AI Data Operations Agent (MM1)
================================================================================
✅ Created handoff trigger file for task 'Create Orchestration Log Database...'
✅ Updated task status to 'In Progress'
✅ Task processed successfully (Total: 1)
⏳ Waiting 30 seconds before next cycle...
```

## Integration with Review Flow

When tasks are completed, agents should create review handoff tasks that return to this processor:

1. Agent completes task
2. Agent creates review handoff trigger file for review agent (e.g., Claude MM1 Agent)
3. Review agent processes review
4. If review passes, task is marked complete
5. If review requires changes, new task is created
6. Continuous processor picks up next task

## Notes

- The script respects existing trigger files and will not create duplicates
- Tasks must have an assigned agent to be processed
- Only tasks with status "Ready", "Not Started", "In Progress", etc. are processed
- Completed tasks (status "Completed", "Complete", "Done", "Archived") are skipped
























