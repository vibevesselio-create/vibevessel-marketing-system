# Unified Logging Migration Guide

**Created:** 2026-01-16
**Status:** Active

---

## Overview

All scripts in the VibeVessel codebase MUST use the unified logging module from `shared_core.logging`. This ensures:

1. **Consistent logging format** across all scripts
2. **Triple logging** (Console + JSONL + human-readable log files)
3. **Metrics tracking** (runtime, operations, errors, warnings)
4. **Notion execution log integration** (optional)
5. **Sensitive data redaction** (tokens, keys, passwords)

---

## Quick Migration

### Before (Legacy)

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Processing started")
logger.warning("Something might be wrong")
logger.error("An error occurred")
```

### After (Unified)

```python
from shared_core.logging import setup_logging

logger = setup_logging(
    session_id="my_script_name",
    log_level="INFO",
    enable_file_logging=True,  # Creates JSONL + .log files
)

logger.info("Processing started", {"step": 1})  # Context is optional
logger.warning("Something might be wrong")
logger.error("An error occurred")

# At script end:
logger.finalize(ok=True, summary={"processed": 10})
logger.close()
```

---

## Available Loggers

### 1. UnifiedLogger (Primary)

The main logger for all scripts:

```python
from shared_core.logging import setup_logging

logger = setup_logging(
    session_id="script_name",      # Required: identifies the script
    log_level="INFO",              # DEBUG, INFO, WARNING, ERROR
    enable_file_logging=True,      # Enable JSONL + .log files
    env="PROD",                    # Environment (DEV, PROD, etc.)
)
```

### 2. MusicWorkflowLogger (Domain-Specific)

For music workflow scripts with track-level logging:

```python
from shared_core.logging import get_music_logger

logger = get_music_logger("music_processor")

logger.track_start("Song Title", "download")
logger.track_complete("Song Title", "download")
logger.track_error("Song Title", "download", "Failed to connect")
logger.workflow_complete("batch_process", processed=10, failed=1, skipped=2)
```

### 3. StructuredLogger (Distributed Systems)

For scripts needing correlation ID tracking:

```python
from shared_core.logging import get_structured_logger

logger = get_structured_logger("my_service", correlation_id="request-123")

with logger.operation("sync_task", script_name="test.py"):
    # Operations are automatically timed and logged
    do_work()
```

---

## Log File Locations

Log files are created at:

```
~/Library/Logs/VibeVessel/{script_name}/{env}/{YYYY}/{MM}/
```

Each execution creates two files:
- `{script} — {ver} — {env} — {timestamp} — {status} ({run_id}).jsonl` - Machine-readable
- `{script} — {ver} — {env} — {timestamp} — {status} ({run_id}).log` - Human-readable

---

## Metrics Tracking

```python
# During execution
logger.info("Operation completed")  # Increments operation_count
logger.warning("Warning message")   # Increments warning_count
logger.error("Error message")       # Increments error_count

# Get metrics anytime
metrics = logger.get_metrics()
# Returns: {total_runtime, operation_count, error_count, warning_count, ...}

# At script end
logger.finalize(ok=True, summary={"custom": "data"})
logger.close()
```

---

## Notion Integration

Enable Notion execution logs:

```python
from notion_client import Client
from shared_core.logging import setup_logging

notion = Client(auth=os.environ["NOTION_TOKEN"])

logger = setup_logging(
    session_id="my_script",
    enable_notion=True,
    notion_client=notion,
    execution_logs_db_id="your-execution-logs-db-id",
)

# Execution log page is automatically created and updated
```

---

## Deprecated Modules

These modules now redirect to `shared_core.logging`:

| Legacy Import | Migration Path |
|--------------|----------------|
| `from music_workflow.utils.logging import get_logger` | `from shared_core.logging import get_music_logger` |
| `from seren_utils.logging import get_logger` | `from shared_core.logging import get_structured_logger` |
| `from unified_config import setup_unified_logging` | `from shared_core.logging import setup_logging` |

---

## Scripts Requiring Migration

The following scripts still use raw `logging` module and need migration:

```bash
# Find scripts needing migration
grep -rl "logging\.basicConfig\|logging\.getLogger" --include="*.py" scripts/ monolithic-scripts/
```

### Priority Scripts (Critical Path)

1. `webhook-server/notion_event_subscription_webhook_server_v4_enhanced.py` - **MIGRATED**
2. `monolithic-scripts/soundcloud_download_prod_merge-2.py`
3. `scripts/sync_fingerprints_to_eagle.py`
4. `scripts/continuous_task_handoff_processor.py`

---

## Migration Checklist

For each script:

- [ ] Replace `import logging` with `from shared_core.logging import setup_logging`
- [ ] Replace `logging.basicConfig(...)` with `setup_logging(...)`
- [ ] Replace `logging.getLogger(...)` with the logger returned by `setup_logging`
- [ ] Add context dictionaries to log calls where helpful
- [ ] Add `logger.finalize(ok=True/False)` before script exit
- [ ] Add `logger.close()` at script end
- [ ] Test that logs are created in `~/Library/Logs/VibeVessel/`

---

## Support

For questions or issues with the unified logging system, create an issue in the Issues+Questions database with tag `unified-logging`.
