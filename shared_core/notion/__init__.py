"""
Notion Shared Core Module
=========================

This module provides shared utilities for Notion integration across all scripts.

**MANDATORY USAGE:**
All scripts that interact with Notion MUST use these utilities:

```python
# For token access (MANDATORY for all Notion scripts)
from shared_core.notion.token_manager import get_notion_token, get_notion_client

# For execution logging
from shared_core.notion.execution_logs import log_execution

# For task creation with mandatory handoff
from shared_core.notion.task_creation import (
    add_mandatory_next_handoff_instructions,
    create_task_description_with_next_handoff,
    create_handoff_json_data
)

# For issue/question creation with duplicate prevention
from shared_core.notion.issues_questions import create_issue_or_question
```
"""

from .token_manager import (
    get_notion_token,
    get_notion_client,
    validate_token,
    get_token_source,
)

from .issues_questions import (
    create_issue_or_question,
    archive_issues_by_name,
)

from .id_utils import (
    normalize_notion_id,
    compact_notion_id,
    validate_notion_id,
    extract_notion_id_from_url,
)

from .folder_resolver import (
    get_trigger_base_path,
    get_fallback_trigger_base_path,
    get_agent_inbox_path,
    get_folder_by_role,
    validate_folder_exists,
    normalize_agent_folder_name,
    get_all_agent_inbox_paths,
    get_agent_folder_structure,
    ensure_agent_folders_exist,
    get_folder_health_status,
)

from .db_id_resolver import (
    get_agent_tasks_db_id,
    get_agent_projects_db_id,
    get_execution_logs_db_id,
    get_issues_questions_db_id,
    get_photo_library_db_id,
    get_database_id,
)

__all__ = [
    "get_notion_token",
    "get_notion_client",
    "validate_token",
    "get_token_source",
    "create_issue_or_question",
    "archive_issues_by_name",
    "normalize_notion_id",
    "compact_notion_id",
    "validate_notion_id",
    "extract_notion_id_from_url",
    # Folder resolver exports
    "get_trigger_base_path",
    "get_fallback_trigger_base_path",
    "get_agent_inbox_path",
    "get_folder_by_role",
    "validate_folder_exists",
    "normalize_agent_folder_name",
    "get_all_agent_inbox_paths",
    "get_agent_folder_structure",
    "ensure_agent_folders_exist",
    "get_folder_health_status",
    # Database ID resolver exports
    "get_agent_tasks_db_id",
    "get_agent_projects_db_id",
    "get_execution_logs_db_id",
    "get_issues_questions_db_id",
    "get_photo_library_db_id",
    "get_database_id",
]
