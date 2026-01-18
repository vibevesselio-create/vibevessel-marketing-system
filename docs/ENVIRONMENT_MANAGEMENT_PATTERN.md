# Environment Management Pattern - CRITICAL REFERENCE

**⚠️ MANDATORY PATTERN - USE THIS IN ALL SCRIPTS**

> **Last Updated:** 2025-01-02
> **Enforcement:** Pre-commit hook + validation script
> **Related Issue:** CRITICAL: Recurring Environment Management Pattern Violations

This document defines the **ONLY** correct pattern for environment variable and token management in all scripts. **Automated enforcement** is now in place via pre-commit hooks.

---

## ✅ PREFERRED APPROACH: Use Centralized Token Manager

**NEW (2025-01-02):** Use `shared_core/notion/token_manager.py` for all Notion token access.

### Simple Usage (Recommended)

```python
from shared_core.notion.token_manager import get_notion_token, get_notion_client

# Option 1: Get configured client directly
notion = get_notion_client()

# Option 2: Get token if you need it directly
token = get_notion_token()
if not token:
    raise RuntimeError("Notion token not found - see shared_core/notion/token_manager.py")
```

This approach:
- Handles all fallback sources automatically
- Loads .env files automatically
- Checks NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN, cache files, and config files
- Is validated by the pre-commit hook

---

## Alternative Pattern (Legacy but Acceptable)

If you can't use the centralized token manager, use this exact pattern:

### 1. Imports (ALWAYS include these)

```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv  # ← ALWAYS include this

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()  # ← ALWAYS call this before checking env vars
```

### 2. Token Retrieval Function (ALWAYS use this exact pattern)

```python
def get_notion_token() -> Optional[str]:
    """Get Notion API token from environment or unified_config"""
    # Check environment first
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")
    if token:
        return token

    # Fallback to unified_config
    try:
        from unified_config import get_notion_token as unified_get_token
        token = unified_get_token()
        return token
    except Exception:
        return None
```

### 3. Error Messages (ALWAYS use this format)

```python
token = get_notion_token()
if not token:
    print("❌ NOTION_TOKEN not found in environment or unified_config")
    sys.exit(1)
```

---

## What NOT to Do (Common Mistakes)

### ❌ WRONG: Missing load_dotenv()
```python
# Missing: from dotenv import load_dotenv
# Missing: load_dotenv()

def get_notion_token():
    return os.getenv("NOTION_TOKEN")  # Won't load from .env files
```

### ❌ WRONG: Missing unified_config fallback
```python
def get_notion_token():
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    # Missing: VV_AUTOMATIONS_WS_TOKEN check
    # Missing: unified_config fallback
```

### ❌ WRONG: Missing VV_AUTOMATIONS_WS_TOKEN
```python
def get_notion_token():
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
    # Missing: VV_AUTOMATIONS_WS_TOKEN
```

### ❌ WRONG: Not handling ImportError
```python
def get_notion_token():
    from unified_config import get_notion_token  # Will crash if not available
    return get_notion_token()
```

---

## Environment Variable Priority Order

1. **NOTION_TOKEN** (primary)
2. **NOTION_API_TOKEN** (alternative)
3. **VV_AUTOMATIONS_WS_TOKEN** (workspace-specific)
4. **unified_config.get_notion_token()** (fallback)

---

## Files That Use This Pattern (Reference)

These files implement the correct pattern - use them as templates:

- `scripts/review_agent_functions_compliance.py` (lines 35-48)
- `scripts/create_compliance_issues.py` (lines 19-32)
- `scripts/create_review_handoff_tasks.py` (lines 26-47)
- `shared_core/notion/execution_logs.py` (lines 58-78)

---

## Checklist for New Scripts

When creating a new script that needs Notion access:

- [ ] Import `load_dotenv` from `dotenv`
- [ ] Call `load_dotenv()` after adding project root to path
- [ ] Create `get_notion_token()` function with exact pattern above
- [ ] Check all three env vars: NOTION_TOKEN, NOTION_API_TOKEN, VV_AUTOMATIONS_WS_TOKEN
- [ ] Include unified_config fallback with try/except
- [ ] Use correct error message format
- [ ] Test that script works without env vars set (should use unified_config)

---

## Why This Pattern Exists

1. **load_dotenv()**: Loads .env files from multiple locations automatically
2. **Multiple env var names**: Different systems use different names
3. **unified_config fallback**: Centralized token management for workspace
4. **Exception handling**: Prevents crashes if unified_config unavailable

---

## Testing the Pattern

```bash
# Test 1: With NOTION_TOKEN set
export NOTION_TOKEN="test_token"
python3 scripts/your_script.py  # Should work

# Test 2: Without env vars (should use unified_config)
unset NOTION_TOKEN
unset NOTION_API_TOKEN
unset VV_AUTOMATIONS_WS_TOKEN
python3 scripts/your_script.py  # Should still work via unified_config

# Test 3: With .env file
# Create .env file with NOTION_TOKEN=test_token
python3 scripts/your_script.py  # Should load from .env
```

---

---

## 🚨 Automated Enforcement (NEW 2025-01-02)

### Pre-Commit Hook

A pre-commit hook automatically validates all staged Python files:

- **Blocks** commits using direct `os.getenv()` for Notion tokens without importing from `token_manager`
- **Blocks** commits containing hardcoded tokens (security risk)
- **Allows** commits that properly use `shared_core.notion.token_manager`

### Manual Validation Script

Run the validation script to check for violations:

```bash
# Validate all files
python scripts/validate_env_management_patterns.py

# Validate specific directory
python scripts/validate_env_management_patterns.py scripts/

# CI mode (exit with error code on violations)
python scripts/validate_env_management_patterns.py --ci

# Show fix suggestions
python scripts/validate_env_management_patterns.py --fix
```

### Emergency Override

To skip validation (NOT recommended):

```bash
git commit --no-verify
```

---

## Related Files

- **Token Manager:** `shared_core/notion/token_manager.py`
- **Validation Script:** `scripts/validate_env_management_patterns.py`
- **Pre-Commit Hook:** `.git/hooks/pre-commit`
- **This Documentation:** `docs/ENVIRONMENT_MANAGEMENT_PATTERN.md`

---

**Last Updated:** 2025-01-02
**Status:** MANDATORY REFERENCE - AUTOMATED ENFORCEMENT ENABLED











































































































