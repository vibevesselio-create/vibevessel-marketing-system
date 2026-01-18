# Continuous Handoff Task Processor

## Overview

The Continuous Handoff Task Processor is an automated system that continuously monitors the Notion Agent-Tasks database and creates handoff trigger files for the appropriate agents based on task requirements and agent capabilities.

## Features

- **Automatic Task Processing**: Queries Notion for incomplete tasks sorted by priority (Critical > High > Medium > Low)
- **Intelligent Agent Assignment**: Determines the best agent for each task based on:
  - Pre-assigned agent (if already set in Notion)
  - Task content and keywords matching agent capabilities
  - Task type and requirements
- **Review Handoff Creation**: Automatically creates review tasks back to Cursor MM1 Agent when tasks are completed
- **Duplicate Prevention**: Checks for existing trigger files before creating new ones
- **Continuous Operation**: Runs until 0 tasks remain in the Agent-Tasks database

## Usage

### Single Task Mode
Process one task and exit:
```bash
python3 scripts/continuous_handoff_processor.py --once
```

### Continuous Mode
Run continuously until all tasks are processed:
```bash
python3 scripts/continuous_handoff_processor.py
```

### Custom Interval
Set custom polling interval (default: 600 seconds = 10 minutes):
```bash
# Use default 10-minute interval
python3 scripts/continuous_handoff_processor.py

# Use custom interval (e.g., 5 minutes = 300 seconds)
python3 scripts/continuous_handoff_processor.py --interval 300
```

## Agent Capabilities Mapping

The system uses the following agent capabilities to determine the best agent:

- **Claude MM1 Agent**: planning, review, coordination, investigation, analysis, validation
- **Claude MM2 Agent**: architecture, review, strategic-planning, advanced-analysis
- **Claude Code Agent**: code-review, implementation, debugging, syntax, gas, javascript
- **Cursor MM1 Agent**: implementation, code, fixes, development, debugging, python, typescript
- **Cursor MM2 Agent**: implementation, code, advanced-development, complex-fixes
- **Codex MM1 Agent**: code, implementation, validation, testing
- **ChatGPT Code Review Agent**: code-review, quality-assurance, validation
- **ChatGPT Strategic Agent**: strategic-planning, architecture, coordination
- **ChatGPT Personal Assistant Agent**: coordination, communication
- **Notion AI Data Operations Agent**: notion, data-operations, database, sync, drivesheets
- **Notion AI Research Agent**: research, analysis, notion, investigation

## Workflow

1. **Query Notion**: Retrieves incomplete tasks from Agent-Tasks database
2. **Sort by Priority**: Orders tasks by priority (Critical > High > Medium > Low)
3. **Determine Agent**: Selects the most appropriate agent based on task requirements
4. **Check for Existing Files**: Verifies no trigger file already exists for the task
5. **Create Trigger File**: Creates handoff file in the appropriate agent's `01_inbox` folder
6. **Update Task Status**: Sets task status to "In Progress" if it was "Ready"
7. **Monitor Completions**: Checks for completed tasks and creates review handoffs
8. **Wait 10 Minutes**: Pauses for 10 minutes before next iteration
9. **Repeat**: Continues until 0 tasks remain

## Review Handoff Process

When a task is marked as "Complete" or "Completed" in Notion:

1. System detects the completed task
2. Checks if a review task already exists
3. Creates a new review task assigned to Cursor MM1 Agent
4. Review task includes:
   - Original task details
   - Review requirements
   - Validation checklist

## Trigger File Format

Trigger files are created in JSON format with the following structure:

```json
{
  "task_id": "...",
  "task_title": "...",
  "task_url": "...",
  "description": "...",
  "status": "...",
  "agent_name": "...",
  "agent_type": "MM1",
  "handoff_instructions": "...",
  "created_at": "...",
  "priority": "..."
}
```

## File Locations

- **MM1 Agents**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Folder}/01_inbox/`
- **MM2 Agents**: `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd/{Agent-Folder}-gd/01_inbox/`

## Logging

The script logs to:
- **Console**: Real-time output
- **File**: `continuous_handoff_processor.log` in the project root

## Requirements

- Python 3.x
- Notion API token (via environment variable or .env file)
- Access to Agent-Triggers folder structure
- Required Python packages (from main.py dependencies)

## Rate Limiting & Pauses

The script includes built-in pauses to avoid overwhelming the Notion API:

- **After Notion Queries**: 1.0 second pause
- **After Notion Updates**: 0.5 second pause
- **After Notion Creates**: 1.0 second pause
- **After File Creation**: 0.5 second pause
- **Between Review Handoffs**: 2.0 second pause
- **After Agent Lookups**: 0.3 second pause
- **Between Iterations**: Configurable (default: 600 seconds = 10 minutes)

These pauses ensure smooth operation and prevent API rate limiting.

## Notes

- The script respects existing trigger files and will not create duplicates
- Task status is automatically updated to "In Progress" when a trigger file is created
- The system will continue running until all tasks are complete
- Review handoffs are created automatically for completed tasks
- Agent assignment prioritizes pre-assigned agents over keyword matching
- Built-in rate limiting prevents API throttling

## Integration

This script integrates with:
- `main.py`: Uses NotionManager and trigger file creation utilities
- `trigger_folder_orchestrator.py`: Compatible with existing trigger file structure
- Notion Agent-Tasks database: Primary source of tasks

## Stopping the Script

Press `Ctrl+C` to gracefully stop the continuous processor. The script will complete the current iteration before exiting.

