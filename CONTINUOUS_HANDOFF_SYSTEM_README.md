# Continuous Handoff Task System

## Overview

The Continuous Handoff Task System automatically processes tasks from the **Agent-Tasks** database in Notion, creating handoff trigger files for appropriate agents and managing the full task lifecycle until completion.

## How It Works

### 1. Task Processing Flow

1. **Query Agent-Tasks Database**: System queries Notion for incomplete tasks, sorted by priority (Critical > High > Medium > Low)
2. **Agent Assignment**: For each task, the system determines the best-suited agent based on:
   - Assigned-Agent relation (if already assigned in Notion)
   - Task requirements and agent capabilities (keyword matching)
   - Task type and content analysis
3. **Create Handoff Trigger File**: Creates a JSON trigger file in the agent's `01_inbox` folder:
   - Path: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Folder}/01_inbox/`
   - File format: `{timestamp}__HANDOFF__{task-title}__{task-id-short}.json`
4. **Update Task Status**: Updates task status to "In Progress" in Notion

### 2. Review Handoff Flow

When an agent completes a task:
1. Agent manually moves trigger file from `01_inbox` to `02_processed`
2. Agent updates task status to "Complete" in Notion
3. System detects completed task and automatically creates a **review handoff task** back to **Cursor MM1 Agent**
4. Review task validates:
   - All requirements met
   - Documentation complete
   - Production execution successful
   - Workspace requirements met

### 3. Continuous Execution

The system runs continuously:
- Checks for completed tasks that need review handoffs
- Processes next highest-priority incomplete task
- Only stops when **0 tasks remain** in the Agent-Tasks database
- Default interval: 10 minutes between iterations

## Agent Capabilities

Tasks are matched to agents based on capability keywords:

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

## Usage

### Run Continuously (Default)

```bash
# Run continuously until 0 tasks remain
python3 scripts/run_continuous_handoff.py

# Or use the processor directly
python3 scripts/continuous_handoff_processor.py
```

### Run Once (Test Mode)

```bash
# Process one task and exit
python3 scripts/run_continuous_handoff.py --once
```

### Custom Interval

```bash
# Check every 5 minutes (300 seconds)
python3 scripts/run_continuous_handoff.py --interval 300
```

## Requirements

1. **Notion API Token**: Must be configured (via environment variable or token manager)
2. **Agent-Tasks Database**: Database ID must be set (defaults to `284e73616c278018872aeb14e82e0392`)
3. **Agent Trigger Folders**: Must exist at:
   - MM1: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/`
   - MM2: Google Drive path (if using MM2 agents)

## File Structure

```
/Users/brianhellemn/Documents/Agents/Agent-Triggers/
├── {Agent-Folder}/
│   ├── 01_inbox/          # New handoff trigger files placed here
│   ├── 02_processed/      # Completed tasks moved here by agents
│   └── 03_failed/         # Failed tasks moved here by agents
```

## Trigger File Format

```json
{
  "task_id": "notion-page-id",
  "task_title": "Task Name",
  "task_url": "https://notion.so/...",
  "description": "Task description",
  "status": "In Progress",
  "agent_name": "Cursor MM1 Agent",
  "agent_type": "MM1",
  "handoff_instructions": "Detailed instructions...",
  "created_at": "2026-01-05T12:00:00Z",
  "priority": "High"
}
```

## Agent Responsibilities

When an agent receives a handoff trigger file:

1. **Read trigger file** from `01_inbox`
2. **Move trigger file** manually to `02_processed` (using `mark_trigger_file_processed()`)
3. **Complete the task** as specified
4. **Update task status** to "Complete" in Notion
5. **Document work** comprehensively in Notion
6. **Verify production execution** and workspace requirements

The system will automatically create a review handoff task back to Cursor MM1 Agent.

## Monitoring

Logs are written to:
- Console output
- `continuous_handoff_processor.log`

## Stopping the System

- Press `Ctrl+C` to stop gracefully
- System will stop automatically when 0 tasks remain (after 3 consecutive checks)

## Notes

- System prevents duplicate trigger file creation
- Review tasks are automatically excluded from creating new reviews (prevents loops)
- System respects Notion API rate limits with built-in pauses
- Tasks are processed in priority order (Critical → High → Medium → Low)



























