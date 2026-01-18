# Continuous Task Handoff System

This system continuously processes tasks from the Agent-Tasks database in Notion, creates trigger files for appropriate agents, and maintains a continuous workflow until all tasks are complete.

## Overview

The `continuous_task_handoff.py` script:

1. **Queries Agent-Tasks Database**: Finds the highest priority uncompleted tasks
2. **Determines Appropriate Agent**: Assigns tasks to agents based on:
   - Assigned-Agent relation (if present)
   - Task requirements and agent capabilities
   - Default agent selection logic
3. **Creates Trigger Files**: Places trigger files in the appropriate agent's `01_inbox` folder
4. **Continuous Execution**: Runs continuously until all tasks are complete

## Usage

### Process One Task

```bash
python3 continuous_task_handoff.py --once
```

This will process one task and exit. Useful for testing or one-off execution.

### Continuous Execution

```bash
python3 continuous_task_handoff.py
```

This runs continuously, checking for new tasks every 60 seconds (default interval).

### Custom Interval

```bash
python3 continuous_task_handoff.py --interval 30
```

Check for tasks every 30 seconds instead of the default 60 seconds.

## Agent Assignment Logic

Tasks are assigned to agents using the following priority:

1. **Assigned-Agent Relation**: If the task has an assigned agent in Notion, that agent is used
2. **Task Content Analysis**: Based on keywords in task title/description:
   - **Validation/Review/Planning**: Claude MM1 Agent
   - **Research**: Notion AI Research Agent
   - **Data Operations**: Notion AI Data Operations Agent
   - **Implementation (default)**: Cursor MM1 Agent

## Task Completion Flow

When an agent completes a task, they should:

1. **Move Trigger File**: Call `mark_trigger_file_processed()` to move the file from `01_inbox` to `02_processed`
2. **Update Notion**: Update the task status to "Complete" in Notion
3. **Create Review Task**: Create a review/validation handoff task back to the orchestrator (Auto/Cursor MM1 Agent)
4. **Document Deliverables**: Document all deliverables and artifacts in Notion
5. **Ensure Compliance**: Verify all workspace requirements are met

## Continuous Execution

The system runs continuously until:

- **All tasks complete**: When no incomplete tasks remain in the Agent-Tasks database
- **Manual stop**: Press Ctrl+C to stop the process
- **Error**: If a fatal error occurs, the process will exit

## Logging

Logs are written to:
- **Console**: Real-time output
- **File**: `continuous_task_processor.log` in the project root

## Integration with Agent System

This script integrates with:

- **Notion Agent-Tasks Database**: `284e73616c278018872aeb14e82e0392`
- **Agent Trigger Folders**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/`
- **Main Task Manager**: Uses functions from `main.py` for consistency

## Example Output

```
2026-01-05 10:43:07 - INFO - ================================================================================
2026-01-05 10:43:07 - INFO - Continuous Task Handoff System
2026-01-05 10:43:07 - INFO - ================================================================================
2026-01-05 10:43:07 - INFO - ✅ Notion API access validated
2026-01-05 10:43:08 - INFO - Found 20 incomplete tasks
2026-01-05 10:43:08 - INFO - Checking task: 'Execute Music Library Remediation - iPad Integration' (Priority: Critical, Status: Ready)
2026-01-05 10:43:15 - INFO - ✅ Created trigger file: /Users/brianhellemn/Documents/Agents/Agent-Triggers/Cursor-MM1-Agent/01_inbox/20260105T164315Z__HANDOFF__Execute-Music-Library-Remediation---iPad-Integrati__2dde7361.json
2026-01-05 10:43:15 - INFO - ✅ Successfully created trigger file for task in Cursor MM1 Agent's inbox
```

## Requirements

- Python 3.7+
- `notion-client` library
- Notion API token in environment (`NOTION_TOKEN`)
- Access to Agent-Tasks database in Notion
- Access to Agent-Triggers folder structure

## Running as a Background Service

To run continuously as a background service, you can use:

```bash
# Using nohup
nohup python3 continuous_task_handoff.py --interval 60 > continuous_task_handoff.out 2>&1 &

# Using screen
screen -S task_handoff
python3 continuous_task_handoff.py --interval 60
# Press Ctrl+A then D to detach

# Using tmux
tmux new-session -d -s task_handoff 'python3 continuous_task_handoff.py --interval 60'
```

## Notes

- The script skips tasks that already have trigger files in the inbox folder
- Tasks are processed in priority order (Critical → High → Medium → Low)
- The system respects agent assignments in Notion
- Duplicate trigger files are prevented by checking for existing files































