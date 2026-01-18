"""
Shared Core Module
==================

This module provides shared utilities for all scripts in this workspace.

Submodules:
- notion: Notion API integration utilities
- logging: Centralized logging utilities
- notifications: macOS notification utilities

**MANDATORY USAGE:**
All scripts that interact with Notion MUST use the token_manager:

```python
from shared_core.notion.token_manager import get_notion_token, get_notion_client

token = get_notion_token()
# or
notion = get_notion_client()
```
"""
