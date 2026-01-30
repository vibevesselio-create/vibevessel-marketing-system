# Unified Environment Management System

**Version:** 1.0.0
**Created:** 2026-01-30
**Status:** ACTIVE

## Overview

This document describes the unified environment variable management system that replaces the previous scattered `.env` files across the codebase.

## Architecture

```
/Users/brianhellemn/Projects/github-production/
├── config/
│   └── master.env              # ⭐ SINGLE SOURCE OF TRUTH
├── .env                        # Symlink → config/master.env
├── shared_core/
│   └── config/
│       ├── __init__.py
│       └── env_loader.py       # Unified loader module
```

## Master Configuration File

**Location:** `/Users/brianhellemn/Projects/github-production/config/master.env`

This file contains ALL environment variables for the entire system:
- Notion tokens and database IDs
- Spotify credentials
- SoundCloud configuration
- Eagle configuration
- Google OAuth configuration
- Linear configuration
- GitLab tokens
- Slack configuration
- Webhook server settings

## Usage

### Python Scripts

```python
# Option 1: Use the ENV object (recommended)
from shared_core.config import ENV

notion_token = ENV.NOTION_TOKEN
spotify_client_id = ENV.SPOTIFY_CLIENT_ID
tracks_db_id = ENV.TRACKS_DB_ID

# Option 2: Use the get_env() function
from shared_core.config import get_env

notion_token = get_env("NOTION_TOKEN")
spotify_client_id = get_env("SPOTIFY_CLIENT_ID", default="")

# Option 3: Require a variable (raises error if not found)
from shared_core.config import require_env

notion_token = require_env("NOTION_TOKEN")  # Raises ValueError if missing
```

### Shell Scripts

```bash
# Source the master.env file
source /Users/brianhellemn/Projects/github-production/config/master.env

# Or use the symlink
source /Users/brianhellemn/Projects/github-production/.env
```

## Deprecated Files

The following files have been deprecated and archived to:
`~/.Trash/deprecated_env_files_20260130/`

| Deprecated File | Replacement |
|----------------|-------------|
| `.env` (root) | Symlink to `config/master.env` |
| `webhook-server/.env` | Use `config/master.env` |
| `scripts/.env.test` | Use `config/master.env` |
| `Scripts-MM1/api.env` | Updated with deprecation notice |

## Adding New Variables

1. Open `/Users/brianhellemn/Projects/github-production/config/master.env`
2. Add the variable under the appropriate section
3. Optionally add to `ENV` dataclass in `shared_core/config/env_loader.py`

Example:
```bash
# In master.env
NEW_API_KEY=abc123

# In env_loader.py (optional for type-safe access)
NEW_API_KEY: str = field(default_factory=lambda: get_env("NEW_API_KEY", ""))
```

## Client-Specific Configuration

Client-specific env files remain in `/Users/brianhellemn/Projects/github-production/clients/`:
- `.env.vibevessel`
- `.env.ocean-frontiers-compass-point`
- etc.

These are loaded separately when working with specific clients.

## Migration Guide

If your script uses the old pattern:

```python
# OLD PATTERN (deprecated)
from dotenv import load_dotenv
load_dotenv()
import os
token = os.environ.get("NOTION_TOKEN")
```

Replace with:

```python
# NEW PATTERN (recommended)
from shared_core.config import ENV
token = ENV.NOTION_TOKEN

# Or if you need backward compatibility:
from shared_core.config import load_dotenv
load_dotenv()  # Works the same way
```

## Troubleshooting

### Variable Not Found

1. Check if variable exists in `config/master.env`
2. Ensure you're using the correct variable name (case-sensitive)
3. Try `get_env("VAR_NAME")` to check the actual value

### Import Errors

Ensure `shared_core` is in your Python path:

```python
import sys
sys.path.insert(0, "/Users/brianhellemn/Projects/github-production")
from shared_core.config import ENV
```

### Symlink Issues

If the `.env` symlink is broken:

```bash
cd /Users/brianhellemn/Projects/github-production
rm -f .env
ln -s config/master.env .env
```

## Security

- Never commit `master.env` to git
- The file is already in `.gitignore`
- Use `config/master.env.example` as a template for new installations

---

**Last Updated:** 2026-01-30
