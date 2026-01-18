# Continuous Handoff Orchestrator Setup

## Overview

A continuous handoff orchestrator has been set up to automatically process tasks from the Notion Agent-Tasks database until all tasks are complete.

## System Architecture

The orchestrator follows this flow:

1. **Query Notion**: Queries the Agent-Tasks database for highest-priority incomplete tasks
2. **Create Handoff**: Creates handoff task files in `01_inbox/Agent-Trigger-Folder/` within `/Users/brianhellemn/Documents/Agents/Agent-Triggers/`
3. **Route to Agents**: Routes those files to the appropriate agent inbox folders based on agent capabilities
4. **Agent Processing**: Agents process tasks and create review handoff tasks back to Auto/Cursor MM1 Agent
5. **Continuous Loop**: Continues until 0 tasks remain in the Agent-Tasks database

## Components

### 1. `create_handoff_from_notion_task.py`
- Queries Notion Agent-Tasks database for incomplete tasks
- Determines appropriate agent based on:
  - Assigned-Agent relation (if present)
  - Task requirements and agent capabilities
  - Default agent selection logic
- Creates handoff task files in `01_inbox/Agent-Trigger-Folder/`

### 2. `process_agent_trigger_folder.py`
- Processes files from `01_inbox/Agent-Trigger-Folder/`
- Routes them to appropriate agent inbox folders based on `target_agent` field
- Moves files from Agent-Trigger-Folder to individual agent folders

### 3. `continuous_handoff_orchestrator.py` (NEW)
- Orchestrates the entire flow
- Runs both scripts in sequence
- Monitors task completion
- Stops automatically when 0 tasks remain

## Agent Assignment Logic

Tasks are assigned to agents based on:

1. **Assigned-Agent relation**: If a task has an assigned agent in Notion, that agent is used
2. **Task content analysis**: Keywords in task title/description determine agent:
   - "validation", "review", "plan", "analysis", "design" → Claude MM1 Agent
   - "research", "notion ai" → Notion AI Research Agent
   - "data", "database", "sync" → Notion AI Data Operations Agent
   - Default → Cursor MM1 Agent (for implementation tasks)

## Review Handoff Flow

When agents complete tasks, they MUST:

1. **Move trigger file**: Call `mark_trigger_file_processed()` to move from `01_inbox` to `02_processed`
2. **Update Notion**: Set task status to "Complete"
3. **Create review handoff**: Create a review/validation task in Agent-Tasks database assigned back to Auto/Cursor MM1 Agent
4. **Document deliverables**: Document all artifacts in Notion
5. **Meet requirements**: Ensure all workspace requirements are met

The orchestrator will automatically pick up review handoff tasks and process them in the same flow.

## Running the Orchestrator

### One-time execution:
```bash
python3 continuous_handoff_orchestrator.py --once
```

### Continuous execution (default):
```bash
python3 continuous_handoff_orchestrator.py
```

### With custom interval:
```bash
python3 continuous_handoff_orchestrator.py --interval 30  # Check every 30 seconds
```

### Background execution:
```bash
nohup python3 continuous_handoff_orchestrator.py --interval 60 > continuous_handoff_orchestrator_output.log 2>&1 &
```

## Status

✅ **Orchestrator is currently running in the background**

- Process ID: Check with `ps aux | grep continuous_handoff_orchestrator`
- Logs: `continuous_handoff_orchestrator.log` and `continuous_handoff_orchestrator_output.log`
- Interval: 60 seconds between cycles
- Auto-stop: Will stop when 0 tasks remain in Agent-Tasks database

## Monitoring

### Check orchestrator status:
```bash
ps aux | grep continuous_handoff_orchestrator | grep -v grep
```

### View logs:
```bash
tail -f continuous_handoff_orchestrator.log
tail -f continuous_handoff_orchestrator_output.log
```

### Check tasks remaining:
The orchestrator logs how many incomplete tasks remain after each cycle.

## File Locations

- **Handoff task files**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/01_inbox/Agent-Trigger-Folder/`
- **Agent inbox folders**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Name}/01_inbox/`
- **Processed files**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Name}/02_processed/`
- **Failed files**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Name}/03_failed/`

## Stopping the Orchestrator

To stop the orchestrator:

```bash
# Find the process
ps aux | grep continuous_handoff_orchestrator | grep -v grep

# Kill it (replace PID with actual process ID)
kill <PID>
```

Or use Ctrl+C if running in foreground.

## Requirements

- Python 3.x
- `notion-client` library
- `dotenv` library (optional, for .env file support)
- Notion API token set in environment or .env file
- Access to Agent-Tasks database in Notion
- Write access to `/Users/brianhellemn/Documents/Agents/Agent-Triggers/`

## Notes

- The orchestrator will automatically stop when 0 incomplete tasks remain
- Tasks are processed in priority order (Critical → High → Medium → Low)
- Duplicate handoff files are prevented (checks for existing files before creating)
- The system handles errors gracefully and continues processing
- Review handoff tasks are automatically picked up and processed

## Troubleshooting

### Orchestrator not processing tasks:
1. Check logs for errors
2. Verify Notion API token is valid
3. Verify Agent-Tasks database ID is correct
4. Check file permissions on Agent-Triggers directory

### Tasks not being routed:
1. Verify `process_agent_trigger_folder.py` is working
2. Check that agent folder names match the `target_agent` field
3. Verify agent folder exists in Agent-Triggers directory

### Review handoffs not being created:
1. Verify agents are following completion instructions
2. Check that review tasks are being created in Agent-Tasks database
3. Verify review tasks are assigned to Auto/Cursor MM1 Agent





















