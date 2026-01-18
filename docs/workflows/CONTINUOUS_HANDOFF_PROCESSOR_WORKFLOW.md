# Continuous Handoff Task Processor Workflow

## Overview

The Continuous Handoff Task Processor is an automated workflow system that continuously monitors the Notion Agent-Tasks database, intelligently assigns tasks to the most appropriate agents based on their capabilities, creates handoff trigger files, and manages the complete task lifecycle from initiation through completion and review.

## Workflow Type

**Type**: Implementation Project  
**Trigger Type**: Scheduled (runs continuously with configurable intervals)  
**Primary Agent**: Cursor MM1 Agent  
**Status**: Running  
**Lifecycle**: Active

## Purpose

This workflow automates the continuous processing of Agent-Tasks from Notion, ensuring:

1. **Automatic Task Discovery**: Queries Notion for incomplete tasks sorted by priority
2. **Intelligent Agent Assignment**: Matches tasks to agents based on capabilities and requirements
3. **Handoff File Creation**: Creates trigger files in appropriate agent inbox folders
4. **Review Task Generation**: Automatically creates review tasks when work is completed
5. **Continuous Operation**: Runs until all tasks are processed

## Workflow Steps

### Step 1: Initialize and Query Notion
- **Function**: Query Agent-Tasks Database
- **Agent**: System (Python Script)
- **Action**: Connect to Notion API and query for incomplete tasks
- **Filter Criteria**:
  - Status ≠ "Complete" AND Status ≠ "Completed"
  - Archive = False
- **Sort**: Priority (Critical > High > Medium > Low)
- **Output**: List of incomplete tasks sorted by priority

### Step 2: Determine Best Agent
- **Function**: Agent Assignment Logic
- **Agent**: System (Python Script)
- **Action**: Analyze task and determine most appropriate agent
- **Decision Logic**:
  1. Check if task has pre-assigned agent → Use assigned agent
  2. Match task keywords against agent capabilities → Select best match
  3. Default to Claude MM1 Agent for planning/coordination tasks
- **Output**: Agent name and ID

### Step 3: Check for Existing Trigger Files
- **Function**: Duplicate Prevention Check
- **Agent**: System (Python Script)
- **Action**: Verify no trigger file already exists for this task
- **Check Locations**:
  - `01_inbox` folder
  - `02_processed` folder
  - `03_failed` folder
- **Output**: Boolean indicating if trigger file exists

### Step 4: Create Handoff Trigger File
- **Function**: Create Trigger File
- **Agent**: System (Python Script)
- **Action**: Generate JSON trigger file in agent's inbox folder
- **File Location**:
  - MM1 Agents: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/{Agent-Folder}/01_inbox/`
  - MM2 Agents: `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd/{Agent-Folder}-gd/01_inbox/`
- **File Format**: JSON with task details, instructions, and metadata
- **Output**: Path to created trigger file

### Step 5: Update Task Status
- **Function**: Update Notion Task Status
- **Agent**: System (Python Script)
- **Action**: Set task status to "In Progress" if it was "Ready"
- **Conditions**: Only updates if status is "Ready", "Ready for Handoff", or "Not Started"
- **Output**: Updated task in Notion

### Step 6: Monitor Completed Tasks
- **Function**: Completion Detection
- **Agent**: System (Python Script)
- **Action**: Query for tasks with status "Complete" or "Completed"
- **Filter**: Exclude archived tasks
- **Output**: List of completed tasks needing review

### Step 7: Create Review Handoff Tasks
- **Function**: Review Task Creation
- **Agent**: System (Python Script)
- **Action**: Create review task assigned to Cursor MM1 Agent
- **Task Properties**:
  - Title: "Review: {Original Task Title}"
  - Status: "Ready"
  - Priority: "High"
  - Task Type: "Review Task"
  - Assigned Agent: Cursor MM1 Agent
  - Description: Includes original task details and review requirements
- **Output**: Review task created in Notion

### Step 8: Wait and Repeat
- **Function**: Interval Management
- **Agent**: System (Python Script)
- **Action**: Pause for configured interval (default: 600 seconds = 10 minutes)
- **Exit Condition**: Stop when 0 tasks remain for 3 consecutive iterations
- **Output**: Continue to next iteration or exit

## Agent Capabilities Mapping

The workflow uses the following agent capabilities for intelligent assignment:

| Agent | Capabilities |
|-------|-------------|
| Claude MM1 Agent | planning, review, coordination, investigation, analysis, validation |
| Claude MM2 Agent | architecture, review, strategic-planning, advanced-analysis |
| Claude Code Agent | code-review, implementation, debugging, syntax, gas, javascript |
| Cursor MM1 Agent | implementation, code, fixes, development, debugging, python, typescript |
| Cursor MM2 Agent | implementation, code, advanced-development, complex-fixes |
| Codex MM1 Agent | code, implementation, validation, testing |
| ChatGPT Code Review Agent | code-review, quality-assurance, validation |
| ChatGPT Strategic Agent | strategic-planning, architecture, coordination |
| ChatGPT Personal Assistant Agent | coordination, communication |
| Notion AI Data Operations Agent | notion, data-operations, database, sync, drivesheets |
| Notion AI Research Agent | research, analysis, notion, investigation |

## Rate Limiting & Pauses

The workflow includes strategic pauses to prevent API rate limiting:

- **After Notion Queries**: 1.0 second
- **After Notion Updates**: 0.5 second
- **After Notion Creates**: 1.0 second
- **After File Creation**: 0.5 second
- **Between Review Handoffs**: 2.0 second
- **After Agent Lookups**: 0.3 second
- **Between Iterations**: 600 seconds (10 minutes) - configurable

## Script Details

**Script Path**: `scripts/continuous_handoff_processor.py`  
**Language**: Python 3.x  
**Dependencies**: 
- `notion-client` (via main.py)
- `main.py` utilities (NotionManager, create_trigger_file, etc.)

**Usage**:
```bash
# Single task mode
python3 scripts/continuous_handoff_processor.py --once

# Continuous mode (default: 10-minute intervals)
python3 scripts/continuous_handoff_processor.py

# Custom interval (e.g., 5 minutes)
python3 scripts/continuous_handoff_processor.py --interval 300
```

## Integration Points

### Notion Databases
- **Agent-Tasks Database** (`284e73616c278018872aeb14e82e0392`): Primary source of tasks
- **Agents Database** (`257e7361-6c27-802a-93dd-cb88d1c4607b`): Agent definitions and capabilities

### File System
- **MM1 Agent Triggers**: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/`
- **MM2 Agent Triggers**: `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd/`

### Related Scripts
- `main.py`: Provides NotionManager and trigger file utilities
- `trigger_folder_orchestrator.py`: Compatible with existing trigger file structure
- `desktop_agent_dispatcher.py`: May process created trigger files

## Review Handoff Process

When a task is marked as "Complete" or "Completed":

1. **Detection**: System queries for completed tasks
2. **Validation**: Checks if review task already exists
3. **Creation**: Creates new review task with:
   - Original task reference
   - Review requirements checklist
   - Validation criteria
   - Production verification requirements
4. **Assignment**: Assigns to Cursor MM1 Agent for review

## Success Criteria

- All incomplete tasks are processed
- Tasks are assigned to appropriate agents based on capabilities
- Trigger files are created without duplicates
- Task status is updated correctly
- Review tasks are created for completed work
- No API rate limiting errors occur
- Script runs continuously until all tasks are complete

## Error Handling

- **No Agent Match**: Defaults to Claude MM1 Agent
- **Duplicate Trigger File**: Skips creation, updates status if needed
- **API Errors**: Logged and script continues with next task
- **Missing Dependencies**: Script exits with error message

## Monitoring & Logging

**Log Files**:
- `continuous_handoff_processor.log`: Detailed execution log

**Log Levels**:
- INFO: Normal operation and task processing
- ERROR: Failures and exceptions
- WARNING: Non-critical issues

## Maintenance

**Regular Tasks**:
- Monitor log files for errors
- Verify agent capabilities mapping is current
- Review rate limiting settings if API issues occur
- Update agent folder names if structure changes

## Related Documentation

- `CONTINUOUS_HANDOFF_PROCESSOR_README.md`: User-facing documentation
- `main.py`: Core utilities and Notion integration
- `trigger_folder_orchestrator.py`: Trigger file processing system

## Version History

- **2026-01-05**: Initial implementation
  - Basic task processing
  - Agent assignment logic
  - Review handoff creation
  - Rate limiting implementation
  - 10-minute interval between iterations































