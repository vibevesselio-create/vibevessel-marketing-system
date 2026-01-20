# HANDOFF: Webhook Server + Desktop Automation Integration

**From:** Claude Code Agent (via Cursor MM1 review)
**To:** Claude Code Agent
**Date:** 2026-01-20T07:00:00Z
**Priority:** HIGH

---

## Objective

Integrate the new desktop automation scripts (`scripts/trigger_claude_code_prompt.py` and `scripts/claude_code_desktop_handoff.py`) with the webhook event subscriptions server to enable:

1. **Webhook-triggered agent handoffs** - When a webhook event arrives, automatically dispatch to the appropriate agent via desktop automation
2. **Replace Keyboard Maestro macros** - Migrate folder trigger macros to Python-based automation
3. **Cross-agent orchestration** - Enable webhook-driven multi-agent workflows

---

## Current State

### Desktop Automation Scripts (Implemented)

1. **`scripts/trigger_claude_code_prompt.py`**
   - Activates Claude app
   - Positions window to right half of screen
   - Pastes content from clipboard
   - Submits (presses Enter)
   - Supports `--submit`, `--verbose`, `--position` flags

2. **`scripts/claude_code_desktop_handoff.py`**
   - Creates structured handoff prompts
   - Supports multiple input modes (direct, file, JSON, builder)
   - Sets Keyboard Maestro variables
   - Integrates with KM macro triggers

### Webhook Server (Existing)

- Located in `mcp-webhook-server/` or similar
- Handles incoming webhook events
- Has event subscription system
- Currently uses folder triggers for agent dispatch

### Keyboard Maestro Macros (To Be Replaced)

- **Folder Trigger: Claude Code Agent** (`91D83B2F-C2C2-44AE-A254-F4EDDC6C4ED4`)
  - Watches `~/Projects/Agents/Agent-Triggers/Claude-Code-Agent/01_inbox`
  - Brings Claude to front
  - Pastes trigger clipboard content
  - Presses Enter

---

## Implementation Tasks

### Phase 1: Webhook Event Handler

Create `services/webhook_agent_dispatcher.py`:

```python
from scripts.trigger_claude_code_prompt import send_to_claude

class WebhookAgentDispatcher:
    """Dispatches webhook events to appropriate agents via desktop automation."""

    AGENT_CONFIGS = {
        'claude-code': {
            'app_name': 'Claude',
            'trigger_script': 'scripts/trigger_claude_code_prompt.py',
            'position': 'right'
        },
        'cursor-mm1': {
            'app_name': 'Cursor',
            'trigger_script': 'scripts/trigger_cursor_prompt.py',  # TODO: Create
            'position': 'left'
        },
        'chatgpt': {
            'app_name': 'ChatGPT',
            'trigger_script': 'scripts/trigger_chatgpt_prompt.py',  # TODO: Create
            'position': 'center'
        }
    }

    def dispatch(self, event_type: str, payload: dict, target_agent: str):
        """Dispatch event to target agent."""
        pass
```

### Phase 2: Webhook Route Integration

Add routes to webhook server:

```python
@app.post("/dispatch/agent/{agent_name}")
async def dispatch_to_agent(agent_name: str, request: AgentDispatchRequest):
    """Dispatch a task to a specific agent via desktop automation."""
    dispatcher = WebhookAgentDispatcher()
    result = dispatcher.dispatch(
        event_type=request.event_type,
        payload=request.payload,
        target_agent=agent_name
    )
    return {"status": "dispatched", "agent": agent_name, "result": result}
```

### Phase 3: Agent-Specific Trigger Scripts

Create trigger scripts for each agent:

1. **`scripts/trigger_cursor_prompt.py`** - For Cursor MM1 Agent
2. **`scripts/trigger_chatgpt_prompt.py`** - For ChatGPT Agent
3. **`scripts/trigger_codex_prompt.py`** - For Codex Agent (VS Code)

Each should follow the pattern in `trigger_claude_code_prompt.py`:
- Activate application
- Position window
- Paste content
- Submit (optional)

### Phase 4: Keyboard Maestro Migration

1. Disable existing folder trigger macros
2. Update agent trigger folders to use file-based triggers instead
3. Create `services/file_trigger_watcher.py` to replace KM folder triggers:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AgentTriggerWatcher:
    """Watches agent inbox folders and dispatches via desktop automation."""

    INBOX_PATHS = {
        'claude-code': '~/Projects/Agents/Agent-Triggers/Claude-Code-Agent/01_inbox',
        'cursor-mm1': '~/Projects/Agents/Agent-Triggers/Cursor-MM1-Agent/01_inbox',
        # ... other agents
    }
```

### Phase 5: Production Testing

1. Test webhook → Claude Code dispatch
2. Test webhook → Cursor MM1 dispatch
3. Test file trigger → agent dispatch
4. Test cross-agent handoff workflows:
   - Claude Code → Cursor MM1 → Claude Code (round trip)
   - Webhook → Multiple agents (parallel dispatch)

---

## Success Criteria

1. **Webhook server** can dispatch tasks to agents via HTTP API
2. **Desktop automation** works reliably for all supported agents
3. **Keyboard Maestro macros** are fully replaced
4. **File trigger watching** works as fallback/alternative
5. **Production workflow** tested end-to-end
6. **Documentation** updated with new dispatch patterns

---

## Files to Create/Modify

### New Files
- `services/webhook_agent_dispatcher.py`
- `services/file_trigger_watcher.py`
- `scripts/trigger_cursor_prompt.py`
- `scripts/trigger_chatgpt_prompt.py`
- `scripts/trigger_codex_prompt.py`
- `docs/WEBHOOK_AGENT_DISPATCH.md`

### Modify
- `mcp-webhook-server/` - Add agent dispatch routes
- `scripts/trigger_claude_code_prompt.py` - Ensure consistent interface
- `.env.example` - Add any new environment variables

---

## Return Handoff Requirements

When complete, create a return handoff with:

1. Summary of implementation
2. List of all new/modified files
3. Test results for each agent
4. Webhook API documentation
5. Migration guide from Keyboard Maestro
6. Any remaining issues or TODOs

---

## References

- Desktop automation scripts: `scripts/trigger_*.py`
- Keyboard Maestro macro analysis in chat transcript
- Webhook server: `mcp-webhook-server/`
- Agent trigger folders: `agents/agent-triggers/`
