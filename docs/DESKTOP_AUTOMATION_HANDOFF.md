# Desktop Automation Handoff System

**Created:** 2026-01-20  
**Author:** Cursor MM1 Agent

---

## Overview

This document describes the desktop automation handoff system for sending tasks to Claude Code Agent (and potentially other agents) via Keyboard Maestro macros instead of the traditional file-based trigger folder method.

---

## Why Desktop Automation?

The traditional trigger folder method has several limitations:

1. **File watching delays** - Folder triggers may have polling delays
2. **File format complexity** - JSON/Markdown files require parsing
3. **Manual cleanup** - Processed files accumulate in folders
4. **Cross-platform issues** - File paths and permissions vary

Desktop automation provides:

1. **Immediate execution** - Direct macro triggering via AppleScript
2. **Variable passing** - Prompts passed directly to KM variables
3. **No file management** - No files to create, move, or clean up
4. **Reliable execution** - Keyboard Maestro handles all UI automation

---

## Components

### 1. Python Script: `scripts/claude_code_desktop_handoff.py`

The main interface for sending handoffs via desktop automation.

#### Usage Examples

```bash
# Check if Keyboard Maestro is running
python scripts/claude_code_desktop_handoff.py --check-status

# Send a direct prompt
python scripts/claude_code_desktop_handoff.py --prompt "Review and fix the bug in utils.py"

# Send a prompt from a file
python scripts/claude_code_desktop_handoff.py --file /path/to/handoff.md

# Send a JSON-structured handoff
python scripts/claude_code_desktop_handoff.py --handoff-json '{
  "title": "Fix Database Sync",
  "description": "The sync is failing on relation properties",
  "priority": "HIGH",
  "success_criteria": ["Sync completes without errors", "All relations mapped"],
  "references": ["scripts/cross_workspace_sync.py"]
}'

# Build a structured handoff with arguments
python scripts/claude_code_desktop_handoff.py --build-handoff \
  --title "Implement New Feature" \
  --description "Add support for multi-select filtering" \
  --priority CRITICAL

# Dry run (show what would be sent)
python scripts/claude_code_desktop_handoff.py --dry-run --prompt "Test prompt"
```

#### Command Line Options

| Option | Description |
|--------|-------------|
| `--prompt`, `-p` | Direct prompt text to send |
| `--file`, `-f` | Path to a file containing the prompt |
| `--handoff-json`, `-j` | JSON handoff specification |
| `--build-handoff`, `-b` | Build a structured handoff using additional args |
| `--title` | Task title (for --build-handoff) |
| `--description` | Task description (for --build-handoff) |
| `--priority` | Priority: CRITICAL, HIGH, MEDIUM, LOW |
| `--wait`, `-w` | Wait for macro completion (default: async) |
| `--dry-run` | Show what would be sent without sending |
| `--check-status` | Check Keyboard Maestro availability |

---

### 2. Keyboard Maestro Macro

**Macro Name:** Automated Generic Task Orchestration Prompt: Claude Code Agent  
**Macro UID:** `AF8B2D96-56E5-4FDA-9E9F-18BC7ACD776B`  
**Variable:** `In Task Orchestration Prompt`

The macro:
1. Reads the prompt from the KM variable
2. Activates the Claude Code application
3. Navigates to the chat input
4. Pastes the prompt
5. Submits to Claude Code

---

## How It Works

```
┌─────────────────────┐
│  Python Script      │
│  claude_code_       │
│  desktop_handoff.py │
└─────────┬───────────┘
          │
          │ 1. Set KM Variable
          │    via AppleScript
          ▼
┌─────────────────────┐
│  Keyboard Maestro   │
│  Variable:          │
│  "In Task           │
│  Orchestration      │
│  Prompt"            │
└─────────┬───────────┘
          │
          │ 2. Trigger Macro
          │    via AppleScript
          ▼
┌─────────────────────┐
│  KM Macro:          │
│  AF8B2D96-56E5-...  │
│  (Claude Code Agent │
│  Orchestration)     │
└─────────┬───────────┘
          │
          │ 3. Desktop Automation
          │    (UI interactions)
          ▼
┌─────────────────────┐
│  Claude Code Agent  │
│  Application        │
│  (receives prompt)  │
└─────────────────────┘
```

---

## Integration with Existing Workflows

### From Python Scripts

```python
import subprocess

def send_to_claude_code(prompt: str) -> bool:
    """Send a task to Claude Code Agent via desktop automation."""
    result = subprocess.run([
        'python3',
        'scripts/claude_code_desktop_handoff.py',
        '--prompt', prompt
    ], capture_output=True, text=True)
    return result.returncode == 0
```

### From Shell Scripts

```bash
#!/bin/bash
# send_handoff.sh

PROMPT="$1"
python3 /Users/brianhellemn/Projects/github-production/scripts/claude_code_desktop_handoff.py \
  --prompt "$PROMPT"
```

---

## Comparison: Desktop Automation vs Trigger Folders

| Feature | Desktop Automation | Trigger Folders |
|---------|-------------------|-----------------|
| Execution Speed | Immediate | Polling delay (seconds) |
| File Management | None | Files created/moved |
| Dependencies | Keyboard Maestro | File system |
| Error Handling | AppleScript errors | File I/O errors |
| Cross-machine | macOS only | Any system |
| Persistence | In memory | On disk |

---

## Troubleshooting

### Keyboard Maestro Not Running

```bash
python scripts/claude_code_desktop_handoff.py --check-status
# Output: Keyboard Maestro Engine: NOT RUNNING
```

**Solution:** Start Keyboard Maestro from /Applications

### Macro Not Found

If the macro UID has changed:

```bash
# Find current macro UID
plutil -convert xml1 -o - \
  "/Users/brianhellemn/Library/Application Support/Keyboard Maestro/Keyboard Maestro Macros.plist" \
  | grep -A 30 "Automated Generic Task Orchestration Prompt: Claude Code Agent"
```

Update `CLAUDE_CODE_MACRO_UID` in the Python script.

### Variable Not Set

Check variable value:

```bash
osascript -e 'tell application "Keyboard Maestro Engine" to return value of variable "In Task Orchestration Prompt"'
```

---

## Available Macros

| Macro Name | UID | Purpose |
|------------|-----|---------|
| Automated Generic Task Orchestration Prompt: Claude Code Agent | AF8B2D96-56E5-4FDA-9E9F-18BC7ACD776B | General task handoff to Claude Code |
| Automated Generic Task Orchestration Prompt: Claude MM1 Agent | 7071C62B-129C-4C04-8B8B-2AF5ED928768 | General task handoff to Claude MM1 |
| Automated Generic Task Orchestration Prompt: Codex MM1 Agent | (TBD) | General task handoff to Codex |

---

## Security Considerations

1. **Prompts in memory** - KM variables persist in memory until overwritten
2. **No token exposure** - Tokens should be referenced by name, not value
3. **Local only** - Desktop automation only works on the local machine
4. **Sensitive data** - Avoid including secrets in prompts

---

## Future Enhancements

1. **Return handoff parsing** - Receive responses from Claude Code
2. **Queue management** - Handle multiple pending handoffs
3. **Status tracking** - Monitor macro execution status
4. **Multi-agent support** - Unified interface for all agents
5. **Webhook integration** - Combine with webhook server for remote triggering
