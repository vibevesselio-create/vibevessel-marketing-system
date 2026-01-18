# Agent Handoff Task Generation Prompt

**Doc Key:** `DOC_AGENT_HANDOFF_TASK_GENERATOR`
**Version:** 4.1.0
**Last Updated:** 2026-01-08
**Purpose:** Simple, targeted instructions for agents to ensure project setup and task execution

---

## 🔴 IMMEDIATE DIRECTIVE — EXECUTE NOW

Execute the following sequence immediately. Do not ask clarifying questions.

---

## STEP 1: ENSURE AGENT-PROJECT EXISTS

**Query Agent-Projects database** (`286e73616c2781ffa450db2ecad4b0ba`) for an in-progress project:

1. **Filter for:** Status = "In Progress"
   
   **Correct Notion API filter format:**
   ```json
   {
     "filter": {
       "property": "Status",
       "status": {
         "equals": "In Progress"
       }
     }
   }
   ```

2. **If found:** Use this project as your current project
3. **If not found:** Create a new Agent-Project entry with:
   - Status: "In Progress"
   - Required relation properties per system spec
   - Title: Descriptive project name

**Current Project ID:** _______________

---

## STEP 2: ENSURE TASKS ARE CREATED AND LINKED

**For the current Agent-Project, verify:**

1. **Query Agent-Tasks database** (`284e73616c278018872aeb14e82e0392`) for tasks linked to the current project
2. **Check required relation properties:**
   - Tasks must be linked to the Agent-Project via Project relation
   - Tasks must be linked to Agent-Function items (if applicable)
   - All required relation properties per system spec must be populated
3. **If tasks are missing or incomplete:**
   - Create Agent-Task entries with all required relation properties
   - Link tasks to the current Agent-Project
   - Link tasks to appropriate Agent-Function items
   - Ensure all required relation properties are set per system spec

---

## STEP 3: RECREATE FAILED TRIGGER ITEMS

**Check for failed task handoff trigger items:**

1. **Check trigger folders:**
   - Local: `/Users/brianhellemn/Documents/Agents/Agent-Triggers/[Your-Agent-Name]-Agent-Trigger/01_inbox/`
   - Google Drive: `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd/[Your-Agent-Name]-Agent-Trigger-gd/01_inbox/`

2. **Identify failed trigger items:**
   - Look for trigger files that correspond to failed or incomplete tasks
   - Check for trigger files without corresponding completed tasks

3. **If exactly ONE failed trigger item exists:**
   - Create a NEW unique trigger file in the appropriate inbox folder
   - Use unique filename: `[TIMESTAMP]__HANDOFF__[PROJECT_NAME]__[AGENT-NAME].json` or `.md`
   - Include all context needed for task execution
   - Link to the corresponding Agent-Task

**Failed Trigger Item Recreated:** [Yes/No] - [File Path]

---

## STEP 4: EXECUTE OR REMEDIATE TASKS

**For the current Agent-Project, proceed with task execution:**

1. **Query Agent-Tasks linked to current project:**
   - Filter: Status in ["In Progress", "Proposed", "Not Started", "Partial", "Failed"]
   
   **Correct Notion API filter format:**
   ```json
   {
     "filter": {
       "or": [
         {"property": "Status", "status": {"equals": "In Progress"}},
         {"property": "Status", "status": {"equals": "Proposed"}},
         {"property": "Status", "status": {"equals": "Not Started"}},
         {"property": "Status", "status": {"equals": "Partial"}},
         {"property": "Status", "status": {"equals": "Failed"}}
       ]
     },
     "sorts": [
       {"property": "Priority", "direction": "descending"},
       {"timestamp": "created_time", "direction": "ascending"}
     ]
   }
   ```
   
   - Sort by: Priority (Critical → Low), then Created time ascending

2. **For each incomplete or non-compliant task:**
   - **If task is incomplete:** Execute or remediate the task according to its description
   - **If task is non-compliant:** Fix compliance issues (missing relations, properties, etc.)
   - **Update task status** as work progresses
   - **Create Execution-Log entry** documenting work completed

3. **Continue until all tasks linked to the current project are complete or properly blocked**

---

## STEP 5: LOCATE ASSIGNED TASK OR REASSIGN

**If no failed trigger items exist in Step 3:**

1. **Query Agent-Tasks database for tasks assigned to you:**
   - Filter: Owner relation contains your agent ID AND Status in ["Proposed", "Not Started", "In Progress"]
   
   **Correct Notion API filter format:**
   ```json
   {
     "filter": {
       "and": [
         {
           "property": "Owner",
           "relation": {
             "contains": "[your-agent-user-id]"
           }
         },
         {
           "or": [
             {"property": "Status", "status": {"equals": "Proposed"}},
             {"property": "Status", "status": {"equals": "Not Started"}},
             {"property": "Status", "status": {"equals": "In Progress"}}
           ]
         }
       ]
     }
   }
   ```
   
   - If found: Execute the highest priority assigned task

2. **If no tasks assigned to you:**
   - **Query for tasks missing agent assignment:**
     - Filter: (Owner is empty OR MCP Assigned Agent is empty OR Assigned-Agent is empty) AND Status in ["Proposed", "Not Started"]
     
     **Correct Notion API filter format:**
     ```json
     {
       "filter": {
         "and": [
           {
             "or": [
               {"property": "Owner", "relation": {"is_empty": true}},
               {"property": "MCP Assigned Agent", "relation": {"is_empty": true}},
               {"property": "Assigned-Agent", "relation": {"is_empty": true}}
             ]
           },
           {
             "or": [
               {"property": "Status", "status": {"equals": "Proposed"}},
               {"property": "Status", "status": {"equals": "Not Started"}}
             ]
           }
         ]
       }
     }
     ```
   - **Reassign to yourself** if you can confidently execute the task
   - **Priority order:**
     1. Tasks missing required agent assignment (highest priority)
     2. Tasks assigned to other agents with similar capabilities (if you can confidently execute)

3. **After reassignment:**
   - Update task Owner/Assigned-Agent relation to yourself
   - Update task Status to "In Progress"
   - Execute the task

**Task Executed:** [Task ID] - [Task Title]

---

## STEP 6: CREATE RETURN HANDOFF (MANDATORY)

**🚨 CRITICAL: This step is MANDATORY. Task is NOT complete until return handoff is created.**

When you complete any task assigned via a trigger file handoff, you MUST create a RETURN handoff trigger file to notify the originating agent of completion.

### 6.1 Return Handoff Requirements

1. **Create RETURN trigger file in originating agent's inbox:**
   - **Local agents:** `/Users/brianhellemn/Documents/Agents/Agent-Triggers/[OriginatingAgent]-Agent/01_inbox/`
   - **Google Drive agents:** `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents-gd/Agent-Triggers-gd/[OriginatingAgent]-Agent-gd/01_inbox/`

2. **Filename format:**
   ```
   [TIMESTAMP]__RETURN__[TaskTitle]__[YourAgentName].json
   ```
   Example: `20260108T143000Z__RETURN__Implement-Feature-X__Claude-Code-Agent.json`

3. **Required content in return handoff file:**
   ```json
   {
     "type": "RETURN_HANDOFF",
     "timestamp": "[ISO 8601 timestamp]",
     "executing_agent": "[Your agent name]",
     "originating_agent": "[Agent who assigned the task]",
     "original_task": {
       "task_id": "[Notion task ID]",
       "task_title": "[Task title]",
       "task_url": "[Notion task URL]",
       "status_update": "Complete"
     },
     "execution_summary": {
       "work_completed": ["List of work items completed"],
       "deliverables": [
         {"type": "file", "path": "/absolute/path/to/file", "description": "What this file is"}
       ],
       "findings": ["Any findings during execution"],
       "recommendations": ["Any recommendations"],
       "issues_found": ["Any issues discovered"]
     },
     "next_steps": ["Suggested next steps for originating agent"],
     "archive_rule": "move_to_02_processed"
   }
   ```

### 6.2 Helper Functions (Python)

Use the helper functions in `/Users/brianhellemn/Projects/github-production/shared_core/notion/task_creation.py`:

```python
from shared_core.notion.task_creation import create_return_handoff_data, get_return_handoff_filename

# Generate return handoff data
return_data = create_return_handoff_data(
    executing_agent="Your Agent Name",
    originating_agent="Originating Agent Name",
    original_task_id="task-uuid",
    original_task_title="Task Title",
    task_url="https://notion.so/...",
    work_completed=["Item 1", "Item 2"],
    deliverables=[{"type": "file", "path": "/path/to/file", "description": "Description"}],
    status_update="Complete"
)

# Generate filename
filename = get_return_handoff_filename(
    executing_agent="Your Agent Name",
    original_task_title="Task Title"
)
```

### 6.3 When Return Handoff is Required

- **ALWAYS required** when completing a task received via trigger file handoff
- **ALWAYS required** when completing an Agent-Task that was assigned by another agent
- Return handoff enables the originating agent to:
  - Validate work completed
  - Update project status
  - Proceed with next steps in the workflow

### 6.4 Non-Compliance Consequences

Failure to create return handoffs:
- Breaks chain of custody in agent workflows
- Prevents work validation by originating agents
- Causes tasks to appear incomplete in dashboards
- Triggers compliance alerts in validation scripts

**Return Handoff Created:** [Yes/No] - [File Path]

---

## QUICK REFERENCE: DATABASE IDS

| Database | ID |
|----------|-----|
| Agent-Projects | 286e73616c2781ffa450db2ecad4b0ba |
| Agent-Tasks | 284e73616c278018872aeb14e82e0392 |
| Agent-Functions | 256e73616c2780c783facd029ff49d2d |
| Execution-Logs | 27be7361-6c27-8033-a323-dca0fafa80e6 |

---

## TRIGGER FILE PATHS

**Local Trigger Path:**
```
/Users/brianhellemn/Documents/Agents/Agent-Triggers/[AgentName]-Agent-Trigger/01_inbox/
```

**Google Drive Trigger Path:**
```
/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd/[AgentName]-Agent-Trigger-gd/01_inbox/
```

---

## VALIDATION CHECKLIST

Before completing, verify:

- [ ] Agent-Project exists and is "In Progress"
- [ ] All expected tasks for the project are created
- [ ] All tasks are linked to the project via required relation properties
- [ ] All tasks have required relation properties populated per system spec
- [ ] Failed trigger item recreated (if one existed)
- [ ] Incomplete/non-compliant tasks executed or remediated
- [ ] If no failed trigger, assigned task located and executed OR task reassigned and executed
- [ ] **MANDATORY: Return handoff trigger file created for originating agent (STEP 6)**
- [ ] Return handoff file contains all work completed, deliverables, and context

---

## CHANGE LOG

| Date | Version | Author | Changes |
|------|---------|--------|---------|
| 2026-01-08 | 4.1.0 | Claude Code Agent | **RESTORED STEP 6: Return Handoff Creation (MANDATORY):** Re-added critical STEP 6 that was removed in v4.0.0. This step MANDATES creation of RETURN handoff trigger files when completing any task assigned via handoff. Includes: return handoff requirements, filename format, required JSON structure, Python helper function references, when return handoff is required, and non-compliance consequences. Updated validation checklist to include mandatory return handoff items. Fixes Issue: "Persistent Non-Compliance: Agents Not Creating Return Handoff Tasks" (2dae7361-6c27-8103-8c3ec01ee11b6a2f). |
| 2026-01-08 | 4.0.1 | Cursor MM1 | **Fixed API Filter Syntax:** Added correct Notion API filter JSON format examples alongside pseudocode in Steps 1, 4, and 5. Fixes issue where pseudocode filter syntax (`Status = "In Progress"`) would cause 400 errors if used directly with Notion API. Now shows both pseudocode (for readability) and correct JSON API format (for implementation). Per Issue 2d7e7361-6c27-815d-b7cd-fb1a8b45bb3d. |
| 2025-01-29 | 4.0.0 | Simplified | **Major Simplification:** Reduced prompt to core requirements: (1) Ensure in-progress Agent-Project exists, (2) Ensure tasks are created and linked via required relations, (3) Recreate single failed trigger item if exists, (4) Execute or remediate incomplete/non-compliant tasks, (5) If no failed trigger, locate assigned task or reassign and execute. Removed all references to Issues+Questions database. Removed complex orchestration phases, tiered gates, and extensive validation steps. |
