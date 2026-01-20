# HANDOFF: Unified Desktop Automation System Implementation

**Timestamp:** 2026-01-20T00:45:00Z  
**From:** Cursor MM1 Agent  
**To:** Claude Code Agent  
**Priority:** CRITICAL  
**Task ID:** `desktop-automation-unified-20260120`

---

## Executive Summary

Implement a comprehensive, unified desktop automation system for all desktop-based agents. This system must consolidate the fragmented implementations scattered across the codebase into a single, maintainable, well-documented module with consistent patterns.

---

## Background Context

### Current State Analysis

After reviewing 200+ desktop automation files across the codebase, the following patterns and issues have been identified:

#### Existing Implementations Found:
1. **Claude Desktop Automation** (`/Volumes/SEREN MEDIA 8TB/local-codebase-backup/Scripts-MM1-Production-Archive-1/claude_desktop_automation.py`)
2. **Cursor MM1 Automation** (`github_legacy_v2_full_backup_*/organized_structure/automation/core/cursor_desktop_automation_mm1.py`)
3. **ChatGPT M2Pro Automation** (`/Users/brianhellemn/Scripts-MM1-Production/chatgpt_MM2Pro_desktop_automation.py`)
4. **Desktop Agent Dispatcher** (`/Users/brianhellemn/Documents/Agents/Agent-Triggers/desktop_agent_dispatcher.py`)
5. **Trigger Desktop Automation** (`/Users/brianhellemn/Documents/Agents/Agent-Triggers/trigger_desktop_automation.py`)
6. **Basic trigger script** (`/Users/brianhellemn/Projects/github-production/scripts/trigger_claude_code_prompt.py`)

#### Key Documentation Reviewed:
- `CLAUDE_DESKTOP_AUTOMATION_SETUP.md` - Claude-specific setup
- `DESKTOP_AUTOMATION_INTEGRATION_SETUP.md` - Multi-agent integration
- `DESKTOP_AUTOMATION_HANDOFF.md` - Handoff system documentation
- `cursor_mm1_desktop_automation_and_gas_hybrid_prompt.md` - Comprehensive L2 spec

#### Identified Problems:
1. **Fragmentation** - Scripts scattered across 10+ locations
2. **Inconsistent patterns** - Different AppleScript approaches per agent
3. **Hardcoded values** - Window positions, click coordinates, app paths
4. **Missing unified configuration** - No central config for all agents
5. **Incomplete error handling** - Inconsistent fallback mechanisms
6. **No unified logging** - Each script has its own logging approach
7. **Duplicate code** - Same AppleScript patterns repeated everywhere

---

## Implementation Requirements

### Phase 1: Cursor MM1 Agent (START HERE)

Create `services/desktop_automation/cursor_automation.py`:

```python
# Core capabilities required:
# 1. Activate Cursor application
# 2. Position window (configurable)
# 3. Open AI chat panel (Cmd+L)
# 4. Paste prompt from clipboard
# 5. Submit (Enter key)
# 6. Keyboard Maestro fallback
# 7. Dry-run mode for testing
# 8. MGM-compliant logging
```

**Cursor-specific requirements:**
- App bundle ID: `com.todesktop.230313mzl4w4u92`
- AI chat shortcut: `Cmd+L`
- Submit: `Enter` key (key code 36)
- Window positioning configurable via environment

### Phase 2: Claude Agent (Code mode)

Create `services/desktop_automation/claude_automation.py`:

**Claude-specific requirements:**
- App bundle ID: `com.anthropic.claudefordesktop`
- New conversation: `Cmd+N`
- Submit: `Enter` key (key code 36)
- Existing KM macros to reference:
  - "Submit Request to Claude MCP"
  - UUID: `91D83B2F-C2C2-44AE-A254-F4EDDC6C4ED4`

### Phase 3: ChatGPT Agent

Create `services/desktop_automation/chatgpt_automation.py`:

**ChatGPT-specific requirements:**
- App bundle ID: `com.openai.chat`
- Similar pattern to Claude

### Phase 4: Codex Agent (VS Code)

Create `services/desktop_automation/vscode_automation.py`:

**VS Code-specific requirements:**
- App bundle ID: `com.microsoft.VSCode`
- Terminal shortcut: `Ctrl+\``
- Command palette: `Cmd+Shift+P`

### Phase 5: Unified Dispatcher

Create `services/desktop_automation/dispatcher.py`:

```python
# Central dispatcher that:
# 1. Auto-detects target agent from folder/context
# 2. Routes to appropriate automation module
# 3. Handles fallback to Keyboard Maestro
# 4. Provides unified logging and metrics
# 5. Manages MCP Tasks integration
```

---

## File Structure

```
services/desktop_automation/
├── __init__.py
├── base.py                    # Abstract base class
├── config.py                  # Unified configuration
├── dispatcher.py              # Central router
├── cursor_automation.py       # Cursor-specific
├── claude_automation.py       # Claude-specific
├── chatgpt_automation.py      # ChatGPT-specific
├── vscode_automation.py       # VS Code/Codex-specific
├── applescript_helpers.py     # Shared AppleScript utilities
├── keyboard_maestro.py        # KM integration layer
└── README.md                  # Module documentation
```

---

## Configuration Schema

Create `services/desktop_automation/config.py`:

```python
AGENT_CONFIG = {
    "cursor_mm1": {
        "app_name": "Cursor",
        "app_path": "/Applications/Cursor.app",
        "bundle_id": "com.todesktop.230313mzl4w4u92",
        "activate_delay": 1.0,
        "chat_shortcut": "l",  # Cmd+L
        "submit_key_code": 36,
        "window_position": [100, 100],
        "window_size": [1400, 900],
        "km_macro_uuid": None,  # No KM macro for Cursor
        "km_macro_name": None,
    },
    "claude_code": {
        "app_name": "Claude",
        "app_path": "/Applications/Claude.app",
        "bundle_id": "com.anthropic.claudefordesktop",
        "activate_delay": 1.5,
        "new_conversation_shortcut": "n",  # Cmd+N
        "submit_key_code": 36,
        "window_position": [400, 0],
        "window_size": [800, 1200],
        "km_macro_uuid": "91D83B2F-C2C2-44AE-A254-F4EDDC6C4ED4",
        "km_macro_name": "Submit Request to Claude MCP",
    },
    "chatgpt": {
        "app_name": "ChatGPT",
        "app_path": "/Applications/ChatGPT.app",
        "bundle_id": "com.openai.chat",
        "activate_delay": 1.0,
        "submit_key_code": 36,
        "window_position": [100, 100],
        "window_size": [1200, 800],
        "km_macro_uuid": None,
        "km_macro_name": None,
    },
    "codex_vscode": {
        "app_name": "Visual Studio Code",
        "app_path": "/Applications/Visual Studio Code.app",
        "bundle_id": "com.microsoft.VSCode",
        "activate_delay": 0.5,
        "terminal_key_code": 50,  # backtick
        "submit_key_code": 36,
        "window_position": [50, 50],
        "window_size": [1600, 1000],
        "km_macro_uuid": None,
        "km_macro_name": None,
    },
}
```

---

## Base Class Design

Create `services/desktop_automation/base.py`:

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import subprocess
import logging

class DesktopAutomationBase(ABC):
    """Abstract base class for all desktop automation modules."""
    
    def __init__(self, config: Dict[str, Any], session_id: Optional[str] = None):
        self.config = config
        self.session_id = session_id or self._generate_session_id()
        self.logger = self._setup_logging()
    
    @abstractmethod
    def activate_app(self) -> bool:
        """Activate the target application."""
        pass
    
    @abstractmethod
    def prepare_input(self) -> bool:
        """Prepare the input area (click, focus, etc.)."""
        pass
    
    @abstractmethod
    def paste_content(self, content: str) -> bool:
        """Paste content into the application."""
        pass
    
    @abstractmethod
    def submit(self) -> bool:
        """Submit the content (press Enter, etc.)."""
        pass
    
    def execute(self, prompt: str, auto_submit: bool = True) -> Dict[str, Any]:
        """Full automation workflow."""
        # Implementation with error handling and logging
        pass
    
    def execute_applescript(self, script: str, timeout: int = 30) -> Tuple[bool, str]:
        """Execute AppleScript and return (success, output)."""
        pass
    
    def set_clipboard(self, content: str) -> bool:
        """Set clipboard content using pbcopy."""
        pass
    
    def fallback_to_km(self) -> bool:
        """Fallback to Keyboard Maestro macro."""
        pass
```

---

## Success Criteria

1. **Cursor MM1 automation works end-to-end**
   - Activates Cursor
   - Opens AI chat (Cmd+L)
   - Pastes prompt
   - Submits (Enter)
   - Returns structured result

2. **All 4 agents have working automation modules**
   - Cursor, Claude, ChatGPT, VS Code

3. **Unified dispatcher routes correctly**
   - Auto-detects agent from context
   - Falls back gracefully on errors

4. **Configuration is externalized**
   - No hardcoded values in automation code
   - Environment variable overrides work

5. **Logging follows MGM standards**
   - Session IDs
   - Correlation IDs
   - Structured evidence logging

6. **Documentation is complete**
   - README.md in module
   - Usage examples
   - Troubleshooting guide

---

## Return Handoff Required

After completing the implementation, create a comprehensive code review handoff task:

**File:** `/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Agents/Agent-Triggers-gd/Cursor-MM1-Agent-Trigger-gd/01_inbox/20260120T______Z__RETURN__Desktop-Automation-Code-Review.md`

The return handoff must include:
1. Summary of all files created/modified
2. Test results for each agent
3. Any issues encountered and how they were resolved
4. Recommendations for future improvements
5. Request for comprehensive code review of the implementation

---

## Reference Files

Read these files for implementation patterns:

1. `/Volumes/SEREN MEDIA 8TB/local-codebase-backup/Scripts-MM1-Production-Archive-1/claude_desktop_automation.py`
2. `/Users/brianhellemn/Documents/Agents/Agent-Triggers/desktop_agent_dispatcher.py`
3. `/Users/brianhellemn/Scripts-MM1-Production/chatgpt_MM2Pro_desktop_automation.py`
4. `/Users/brianhellemn/Projects/github-production/scripts/trigger_claude_code_prompt.py`

---

## Execution Instructions

1. Start with Cursor MM1 automation (Phase 1)
2. Test thoroughly before moving to next phase
3. Use dry-run mode for initial testing
4. Create return handoff after all phases complete
5. Do NOT submit the return handoff - just create the file

---

## Environment Context

- Workspace: `/Users/brianhellemn/Projects/github-production`
- Python version: 3.13+
- macOS with System Events accessibility enabled
- Keyboard Maestro installed and running
- All target applications installed

---

**Created by:** Cursor MM1 Agent  
**Timestamp:** 2026-01-20T00:45:00Z
