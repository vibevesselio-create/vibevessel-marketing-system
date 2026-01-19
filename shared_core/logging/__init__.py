"""
Shared Core Logging Module
==========================

Centralized logging utilities for all scripts in the VibeVessel workspace.

This module provides:
- UnifiedLogger: A comprehensive logger with metrics tracking, triple logging
  (Console + JSONL + Human-readable), and optional Notion execution log integration

Inspired by DriveSheetsSync GAS UnifiedLoggerGAS v2.5 architecture:
- Triple logging: Console, JSONL (machine-readable), and .log (human-readable)
- Canonical log path structure: logs/{script}/{env}/{YYYY}/{MM}/
- Structured context logging with JSON serialization
- Automatic buffer flushing (time-based and size-based)
- Finalization with status update in filenames
- Notion execution log page creation (when enabled)

Usage:
    from shared_core.logging import setup_logging

    logger = setup_logging(
        session_id="my_script",
        log_level="INFO",
        enable_file_logging=True,  # Enable triple logging
        enable_notion=True          # Enable Notion execution logs
    )
    logger.info("Processing started", {"step": 1, "total": 10})

    # At the end:
    logger.finalize(ok=True, summary={"processed": 10, "errors": 0})
    metrics = logger.get_metrics()
    logger.close()

Version: 2026-01-14 (aligned with DriveSheetsSync v2.5)
"""

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime


# Default configuration matching DriveSheetsSync
DEFAULT_CONFIG = {
    "LOG_ROOT_PATH": Path.home() / "Library/Logs/VibeVessel",
    "FLUSH_LINES": 20,      # Flush after N log lines
    "FLUSH_MS": 10000,      # Flush after N milliseconds
    "MAX_CONTEXT_DEPTH": 5, # Max depth for context serialization
}


def _now_iso() -> str:
    """Return current time in ISO 8601 format."""
    return datetime.now().isoformat()


def _safe_serialize(obj: Any, depth: int = 0, max_depth: int = 5) -> Any:
    """Safely serialize an object for JSON, handling non-serializable types."""
    if depth > max_depth:
        return f"<max depth {max_depth} exceeded>"

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    if isinstance(obj, (datetime,)):
        return obj.isoformat()

    if isinstance(obj, Path):
        return str(obj)

    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"

    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v, depth + 1, max_depth) for k, v in obj.items()}

    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(item, depth + 1, max_depth) for item in obj]

    # For unknown types, try str() representation
    try:
        return str(obj)
    except Exception:
        return f"<unserializable {type(obj).__name__}>"


def _redact_sensitive(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive values from a dictionary (tokens, keys, secrets)."""
    sensitive_patterns = [
        "token", "secret", "key", "password", "api_key", "apikey",
        "auth", "credential", "private"
    ]

    result = {}
    for k, v in obj.items():
        key_lower = k.lower()
        is_sensitive = any(pattern in key_lower for pattern in sensitive_patterns)

        if is_sensitive and v:
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = _redact_sensitive(v)
        else:
            result[k] = v

    return result


class UnifiedLogger:
    """
    Unified logger with metrics tracking for workspace scripts.

    Provides standard logging API plus:
    - get_metrics(): Returns runtime and operation metrics
    - close(): Properly closes and flushes handlers
    - finalize(): Finalize logging with status update
    - Triple logging: Console, JSONL, and human-readable log files

    Architecture aligned with DriveSheetsSync UnifiedLoggerGAS v2.5:
    - Structured context logging with automatic JSON serialization
    - Automatic buffer flushing (time-based and size-based)
    - Canonical log path structure
    - Notion execution log integration (when enabled)
    - Finalization with status update in filenames

    Attributes:
        logger: The underlying logging.Logger instance
        session_id: Identifier for this logging session
        run_id: Unique identifier for this execution run
    """

    # Script version for log file naming
    VERSION = "2.5"

    def __init__(
        self,
        name: str = "workspace",
        log_level: str = "INFO",
        log_file: Optional[Path] = None,
        enable_notion: bool = False,
        enable_file_logging: bool = False,
        env: str = "PROD",
        log_root: Optional[Path] = None,
        notion_client: Any = None,
        execution_logs_db_id: Optional[str] = None,
    ):
        """
        Initialize the unified logger.

        Args:
            name: Logger name/session identifier (script name)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Optional explicit path to log file (overrides auto-path)
            enable_notion: Whether to enable Notion execution log creation
            enable_file_logging: Whether to enable triple file logging (JSONL + .log)
            env: Environment name (DEV, PROD, etc.) - used in log paths
            log_root: Root directory for log files (defaults to ~/Library/Logs/VibeVessel)
            notion_client: Optional Notion client for execution log integration
            execution_logs_db_id: Optional Notion database ID for execution logs
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Run metadata
        self.run_id = str(uuid.uuid4())[:12]
        self.session_id = name
        self.env = env
        self.enable_notion = enable_notion
        self.enable_file_logging = enable_file_logging
        self._started = _now_iso()

        # Notion integration
        self._notion_client = notion_client
        self._execution_logs_db_id = execution_logs_db_id
        self._notion_log_page_id: Optional[str] = None

        # Triple logging file handles
        self._jsonl_file: Optional[Path] = None
        self._human_file: Optional[Path] = None
        self._log_folder: Optional[Path] = None

        # Buffer for batch writing (matching DriveSheetsSync flush behavior)
        self._buffer: List[Dict[str, Any]] = []
        self._last_flush = time.time()
        self._flush_lines = DEFAULT_CONFIG["FLUSH_LINES"]
        self._flush_ms = DEFAULT_CONFIG["FLUSH_MS"]

        # Metrics tracking
        self._start_ts = time.time()
        self._closed = False
        self._finalized = False
        self._operation_count = 0
        self._error_count = 0
        self._warning_count = 0

        # Track all log entries for Notion page body
        self._log_entries: List[Dict[str, Any]] = []
        self._error_messages: List[str] = []
        self._warn_messages: List[str] = []
        self._database_results: List[Dict[str, Any]] = []

        # Clear existing handlers to avoid duplicates
        if not self._logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_fmt = logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            console_handler.setFormatter(console_fmt)
            self._logger.addHandler(console_handler)

            # Explicit file handler (if specified)
            if log_file:
                try:
                    file_handler = logging.FileHandler(log_file, encoding="utf-8")
                    file_handler.setLevel(logging.DEBUG)
                    file_fmt = logging.Formatter(
                        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S"
                    )
                    file_handler.setFormatter(file_fmt)
                    self._logger.addHandler(file_handler)
                except Exception as e:
                    self._logger.warning(f"Could not create log file handler: {e}")

        self._logger.propagate = False

        # Initialize triple logging if enabled
        if enable_file_logging:
            self._init_file_logging(log_root or DEFAULT_CONFIG["LOG_ROOT_PATH"])

        # Create Notion execution log page if enabled
        if enable_notion and notion_client and execution_logs_db_id:
            self._create_notion_execution_log()

    def _init_file_logging(self, log_root: Path) -> None:
        """Initialize triple logging (JSONL + human-readable .log files)."""
        try:
            now = datetime.now()
            yyyy = str(now.year)
            mm = str(now.month).zfill(2)
            timestamp = now.strftime("%Y-%m-%d_%H%M%S")

            # Canonical path: logs/{script}/{env}/{YYYY}/{MM}/
            self._log_folder = log_root / self.session_id / self.env / yyyy / mm
            self._log_folder.mkdir(parents=True, exist_ok=True)

            # File naming convention: {Script} — {VER} — {ENV} — {TIMESTAMP} — {STATUS} ({RUNID})
            base_name = f"{self.session_id} — {self.VERSION} — {self.env} — {timestamp} — Running ({self.run_id})"

            self._jsonl_file = self._log_folder / f"{base_name}.jsonl"
            self._human_file = self._log_folder / f"{base_name}.log"

            # Create empty files
            self._jsonl_file.touch()
            self._human_file.touch()

            # Log file creation info
            self._logger.info("=" * 80)
            self._logger.info("📁 LOG FILES CREATED - LOCATION INFORMATION")
            self._logger.info("=" * 80)
            self._logger.info(f"📂 Folder Path: {self._log_folder}")
            self._logger.info(f"📄 JSONL File: {self._jsonl_file.name}")
            self._logger.info(f"📄 Log File: {self._human_file.name}")
            self._logger.info("=" * 80)

        except Exception as e:
            self._logger.warning(f"Could not initialize file logging: {e}")
            self._jsonl_file = None
            self._human_file = None

    def _create_notion_execution_log(self) -> None:
        """Create a Notion execution log page."""
        if not self._notion_client or not self._execution_logs_db_id:
            return

        try:
            # Create execution log page
            properties = {
                "Script Name": {"title": [{"text": {"content": self.session_id}}]},
                "Run ID": {"rich_text": [{"text": {"content": self.run_id}}]},
                "Environment": {"select": {"name": self.env}},
                "Started At": {"date": {"start": self._started}},
                "Status": {"select": {"name": "Running"}},
            }

            response = self._notion_client.pages.create(
                parent={"database_id": self._execution_logs_db_id},
                properties=properties
            )
            self._notion_log_page_id = response.get("id")
            self._logger.info(f"📝 Created Notion execution log: {self._notion_log_page_id}")

        except Exception as e:
            self._logger.warning(f"Could not create Notion execution log: {e}")

    def _log(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Internal logging method with structured context support.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            context: Optional context dictionary for structured logging
        """
        timestamp = _now_iso()

        # Build log entry
        entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": message,
            "context": _safe_serialize(context) if context else {},
            "run_id": self.run_id,
            "session_id": self.session_id,
        }

        # Store for metrics and Notion
        self._log_entries.append(entry)

        if level == "error":
            self._error_messages.append(f"{timestamp}: {message}")
        elif level == "warning":
            self._warn_messages.append(f"{timestamp}: {message}")

        # Add to buffer for file writing
        if self.enable_file_logging:
            self._buffer.append(entry)
            self._flush_if_needed()

    def _flush_if_needed(self, force: bool = False) -> None:
        """Flush buffer to files if threshold reached or forced."""
        if not self.enable_file_logging:
            return

        elapsed_ms = (time.time() - self._last_flush) * 1000
        should_flush = (
            force or
            len(self._buffer) >= self._flush_lines or
            elapsed_ms >= self._flush_ms
        )

        if not should_flush or not self._buffer:
            return

        try:
            # Write to JSONL file
            if self._jsonl_file:
                with open(self._jsonl_file, "a", encoding="utf-8") as f:
                    for entry in self._buffer:
                        f.write(json.dumps(entry, default=str) + "\n")

            # Write to human-readable file
            if self._human_file:
                with open(self._human_file, "a", encoding="utf-8") as f:
                    for entry in self._buffer:
                        ctx_str = ""
                        if entry.get("context"):
                            ctx_str = f" | {json.dumps(entry['context'], default=str)}"
                        f.write(
                            f"{entry['timestamp']} | {entry['level']} | {entry['message']}{ctx_str}\n"
                        )

            self._buffer.clear()
            self._last_flush = time.time()

        except Exception as e:
            self._logger.warning(f"Failed to flush log buffer: {e}")

    # Standard logging API with context support
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log a debug message with optional context."""
        self._log("debug", message, context)
        if context:
            self._logger.debug(f"{message} | {json.dumps(context, default=str)}")
        else:
            self._logger.debug(message)

    def info(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log an info message with optional context."""
        self._operation_count += 1
        self._log("info", message, context)
        if context:
            self._logger.info(f"{message} | {json.dumps(context, default=str)}")
        else:
            self._logger.info(message)

    def warning(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log a warning message with optional context."""
        self._warning_count += 1
        self._log("warning", message, context)
        if context:
            self._logger.warning(f"{message} | {json.dumps(context, default=str)}")
        else:
            self._logger.warning(message)

    def error(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log an error message with optional context."""
        self._error_count += 1
        self._log("error", message, context)
        if context:
            self._logger.error(f"{message} | {json.dumps(context, default=str)}")
        else:
            self._logger.error(message)

    def critical(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log a critical message with optional context."""
        self._error_count += 1
        self._log("critical", message, context)
        if context:
            self._logger.critical(f"{message} | {json.dumps(context, default=str)}")
        else:
            self._logger.critical(message)

    def exception(self, message: str, context: Optional[Dict[str, Any]] = None, **kwargs):
        """Log an exception with traceback and optional context."""
        import traceback
        self._error_count += 1
        ctx = context or {}
        ctx["traceback"] = traceback.format_exc()
        self._log("error", message, ctx)
        self._logger.exception(message)

    def add_database_result(self, result: Dict[str, Any]) -> None:
        """Track a database processing result for summary."""
        self._database_results.append(result)

    @property
    def logger(self) -> logging.Logger:
        """Get the underlying logging.Logger instance."""
        return self._logger

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get runtime metrics for this logging session.

        Returns:
            Dictionary containing:
            - total_runtime: Seconds since logger was created
            - operation_count: Number of info-level log calls
            - error_count: Number of error/critical calls
            - warning_count: Number of warning calls
            - session_id: Logger session identifier
            - run_id: Unique run identifier
            - start_time: ISO timestamp of session start
            - log_files: Paths to log files (if file logging enabled)
            - notion_log_page_id: Notion execution log page ID (if enabled)
        """
        metrics = {
            "total_runtime": time.time() - self._start_ts,
            "operation_count": self._operation_count,
            "error_count": self._error_count,
            "warning_count": self._warning_count,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "start_time": datetime.fromtimestamp(self._start_ts).isoformat(),
        }

        if self.enable_file_logging:
            metrics["log_files"] = {
                "jsonl": str(self._jsonl_file) if self._jsonl_file else None,
                "human": str(self._human_file) if self._human_file else None,
                "folder": str(self._log_folder) if self._log_folder else None,
            }

        if self._notion_log_page_id:
            metrics["notion_log_page_id"] = self._notion_log_page_id

        return metrics

    def finalize(
        self,
        ok: bool = True,
        error: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Finalize logging session with status update.

        Updates log file names with final status (Completed/Failed) and
        updates Notion execution log if enabled.

        Args:
            ok: True if execution succeeded, False if failed
            error: Optional error message if failed
            summary: Optional summary dictionary for final log entry
        """
        if self._finalized:
            return

        self._finalized = True
        status = "Completed" if ok else "Failed"
        end_time = _now_iso()

        # Final log entry
        final_summary = summary or {}
        final_summary.update({
            "status": status,
            "total_runtime_seconds": time.time() - self._start_ts,
            "operation_count": self._operation_count,
            "error_count": self._error_count,
            "warning_count": self._warning_count,
        })
        if error:
            final_summary["error"] = error

        self.info(f"Execution {status}", final_summary)

        # Flush remaining buffer
        self._flush_if_needed(force=True)

        # Rename log files with final status
        if self.enable_file_logging and self._jsonl_file and self._human_file:
            try:
                for old_file in [self._jsonl_file, self._human_file]:
                    if old_file and old_file.exists():
                        new_name = old_file.name.replace(" — Running ", f" — {status} ")
                        new_path = old_file.parent / new_name
                        old_file.rename(new_path)
                        if old_file == self._jsonl_file:
                            self._jsonl_file = new_path
                        else:
                            self._human_file = new_path
            except Exception as e:
                self._logger.warning(f"Could not rename log files with final status: {e}")

        # Update Notion execution log
        if self._notion_client and self._notion_log_page_id:
            try:
                # Build page body content from log entries
                body_content = self._build_notion_log_body()

                # Update page properties and body
                update_props = {
                    "Status": {"select": {"name": status}},
                    "Ended At": {"date": {"start": end_time}},
                    "Runtime (seconds)": {"number": round(time.time() - self._start_ts, 2)},
                    "Error Count": {"number": self._error_count},
                    "Warning Count": {"number": self._warning_count},
                }
                if error:
                    update_props["Error Message"] = {"rich_text": [{"text": {"content": error[:2000]}}]}

                self._notion_client.pages.update(
                    page_id=self._notion_log_page_id,
                    properties=update_props
                )

                # Append log body content
                if body_content:
                    self._notion_client.blocks.children.append(
                        block_id=self._notion_log_page_id,
                        children=body_content
                    )

                self._logger.info(f"📝 Updated Notion execution log: {status}")

            except Exception as e:
                self._logger.warning(f"Could not update Notion execution log: {e}")

    def _build_notion_log_body(self) -> List[Dict[str, Any]]:
        """Build Notion block children for log body content."""
        blocks = []

        # Summary section
        blocks.append({
            "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "Execution Summary"}}]}
        })

        summary_text = (
            f"Run ID: {self.run_id}\n"
            f"Environment: {self.env}\n"
            f"Started: {self._started}\n"
            f"Runtime: {time.time() - self._start_ts:.2f}s\n"
            f"Operations: {self._operation_count}\n"
            f"Errors: {self._error_count}\n"
            f"Warnings: {self._warning_count}"
        )
        blocks.append({
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": summary_text}}]}
        })

        # Error section (if any)
        if self._error_messages:
            blocks.append({
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Errors"}}]}
            })
            for err in self._error_messages[:20]:  # Limit to 20 errors
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"text": {"content": err[:2000]}}]}
                })

        # Database results section (if any)
        if self._database_results:
            blocks.append({
                "type": "heading_2",
                "heading_2": {"rich_text": [{"text": {"content": "Database Results"}}]}
            })
            for result in self._database_results:
                result_text = json.dumps(result, default=str, indent=2)[:2000]
                blocks.append({
                    "type": "code",
                    "code": {
                        "rich_text": [{"text": {"content": result_text}}],
                        "language": "json"
                    }
                })

        return blocks

    def close(self):
        """
        Close the logger and flush all handlers.

        Safe to call multiple times.
        """
        if self._closed:
            return

        # Finalize if not already done
        if not self._finalized:
            self.finalize(ok=self._error_count == 0)

        # Flush buffer
        self._flush_if_needed(force=True)

        for handler in list(self._logger.handlers):
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass

        self._closed = True


def setup_logging(
    session_id: str = "session",
    enable_notion: bool = False,
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_file_logging: bool = False,
    env: str = "PROD",
    log_root: Optional[str] = None,
    notion_client: Any = None,
    execution_logs_db_id: Optional[str] = None,
) -> UnifiedLogger:
    """
    Create and configure a UnifiedLogger instance.

    This is the main entry point for scripts to get a configured logger.
    Supports DriveSheetsSync-style comprehensive logging features.

    Args:
        session_id: Identifier for this logging session (used as logger name)
        enable_notion: Whether to enable Notion execution log creation
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional explicit path to log file
        enable_file_logging: Whether to enable triple file logging (JSONL + .log)
        env: Environment name (DEV, PROD) for log paths
        log_root: Optional root directory for log files
        notion_client: Optional Notion client for execution log integration
        execution_logs_db_id: Optional Notion database ID for execution logs

    Returns:
        Configured UnifiedLogger instance

    Example (basic):
        from shared_core.logging import setup_logging

        logger = setup_logging(session_id="my_script", log_level="DEBUG")
        logger.info("Script started")
        logger.info("Processing item", {"item_id": 123, "status": "pending"})
        logger.finalize(ok=True, summary={"processed": 10})
        logger.close()

    Example (with file logging):
        logger = setup_logging(
            session_id="my_script",
            enable_file_logging=True,  # Enable JSONL + .log files
            env="PROD"
        )
        # Log files created at: ~/Library/Logs/VibeVessel/my_script/PROD/YYYY/MM/

    Example (with Notion integration):
        from notion_client import Client
        notion = Client(auth=os.environ["NOTION_TOKEN"])

        logger = setup_logging(
            session_id="my_script",
            enable_notion=True,
            notion_client=notion,
            execution_logs_db_id="your-db-id"
        )
        # Creates execution log page in Notion database
    """
    log_path = Path(log_file) if log_file else None
    log_root_path = Path(log_root) if log_root else None

    logger = UnifiedLogger(
        name=session_id,
        log_level=log_level,
        log_file=log_path,
        enable_notion=enable_notion,
        enable_file_logging=enable_file_logging,
        env=env,
        log_root=log_root_path,
        notion_client=notion_client,
        execution_logs_db_id=execution_logs_db_id,
    )

    logger.debug(f"[shared_core.logging] Initialized logger for session '{session_id}'", {
        "run_id": logger.run_id,
        "env": env,
        "enable_file_logging": enable_file_logging,
        "enable_notion": enable_notion,
    })

    return logger


# Alias for backward compatibility
# Some scripts use get_unified_logger (legacy name) instead of setup_logging
def get_unified_logger(
    script_name: str = "script",
    env: str = "PROD",
    enable_notion: bool = False,
    log_level: str = "INFO",
    enable_file_logging: bool = False,
    notion_client: Any = None,
    execution_logs_db_id: Optional[str] = None,
) -> UnifiedLogger:
    """
    Alias for setup_logging (backward compatibility).

    Legacy scripts may call get_unified_logger() instead of setup_logging().
    This wrapper translates the legacy parameter names.

    Args:
        script_name: Name of the script (maps to session_id)
        env: Environment name (DEV, PROD)
        enable_notion: Whether to enable Notion execution log creation
        log_level: Logging level
        enable_file_logging: Whether to enable triple file logging
        notion_client: Optional Notion client for execution log integration
        execution_logs_db_id: Optional Notion database ID for execution logs

    Returns:
        Configured UnifiedLogger instance
    """
    return setup_logging(
        session_id=script_name,
        enable_notion=enable_notion,
        log_level=log_level,
        enable_file_logging=enable_file_logging,
        env=env,
        notion_client=notion_client,
        execution_logs_db_id=execution_logs_db_id,
    )


# ============================================================================
# Backward Compatibility Aliases
# ============================================================================
# These aliases provide drop-in compatibility with legacy logging modules:
# - music_workflow.utils.logging.MusicWorkflowLogger
# - seren_utils.logging.StructuredLogger
# - unified_config.setup_unified_logging
#
# MIGRATION NOTE: All scripts should migrate to using:
#   from shared_core.logging import setup_logging
# ============================================================================

# Alias: MusicWorkflowLogger compatibility
class MusicWorkflowLogger(UnifiedLogger):
    """
    Backward-compatible wrapper for music_workflow.utils.logging.MusicWorkflowLogger.

    Migration path: Replace `from music_workflow.utils.logging import get_logger`
    with `from shared_core.logging import get_music_logger`
    """

    def track_start(self, track_title: str, operation: str) -> None:
        """Log start of track operation."""
        self.info(f"[START] {operation}", {"track": track_title})

    def track_complete(self, track_title: str, operation: str) -> None:
        """Log completion of track operation."""
        self.info(f"[COMPLETE] {operation}", {"track": track_title})

    def track_error(self, track_title: str, operation: str, error: str) -> None:
        """Log track operation error."""
        self.error(f"[ERROR] {operation}", {"track": track_title, "error": error})

    def workflow_start(self, workflow_name: str, total_tracks: int) -> None:
        """Log workflow start."""
        self.info(f"Starting {workflow_name}", {"total_tracks": total_tracks})

    def workflow_complete(
        self, workflow_name: str, processed: int, failed: int, skipped: int
    ) -> None:
        """Log workflow completion."""
        self.info(
            f"Completed {workflow_name}",
            {"processed": processed, "failed": failed, "skipped": skipped}
        )

    def log_track_operation(
        self, track_id: str, operation: str, message: str, **kwargs
    ) -> None:
        """Log a track operation (called from workflow.py)."""
        self.info(f"[{operation.upper()}] {message}", {"track_id": track_id, **kwargs})

    def log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """Log an error with optional context (called from workflow.py)."""
        error_message = str(error)
        error_type = type(error).__name__
        ctx = context or {}
        ctx.update({"error_type": error_type, "error_message": error_message})
        self.error(f"[ERROR] {error_type}: {error_message}", ctx)

    def log_workflow_event(
        self, event: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a workflow event (called from workflow.py for batch processing)."""
        self.info(f"[WORKFLOW] {event}", context or {})


def get_music_logger(
    name: str = "music_workflow",
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> MusicWorkflowLogger:
    """
    Get a MusicWorkflowLogger instance (backward compatible).

    Migration from: music_workflow.utils.logging.get_logger
    """
    log_path = Path(log_file) if log_file else None
    return MusicWorkflowLogger(
        name=name,
        log_level=level,
        log_file=log_path,
        enable_file_logging=log_file is not None,
    )


# Alias: StructuredLogger compatibility with correlation ID support
class StructuredLogger(UnifiedLogger):
    """
    Backward-compatible wrapper for seren_utils.logging.StructuredLogger.

    Adds correlation_id tracking for distributed systems.

    Migration path: Replace `from seren_utils.logging import get_logger`
    with `from shared_core.logging import get_structured_logger`
    """

    def __init__(
        self,
        name: str,
        correlation_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.correlation_id = correlation_id or self.run_id

    def _log(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Override to add correlation_id to every log entry."""
        ctx = context or {}
        ctx["correlation_id"] = self.correlation_id
        super()._log(level, message, ctx)

    def operation(self, operation_name: str, **kwargs):
        """
        Context manager for timing operations.

        Usage:
            with logger.operation("sync_script", script_name="test.py"):
                # do work
        """
        import time as time_module
        from contextlib import contextmanager

        @contextmanager
        def _operation_context():
            start_time = time_module.time()
            self.info(f"Starting {operation_name}", {"operation": operation_name, **kwargs})

            try:
                yield
                duration = time_module.time() - start_time
                self.info(
                    f"Completed {operation_name}",
                    {
                        "operation": operation_name,
                        "duration_seconds": round(duration, 3),
                        "status": "success",
                        **kwargs
                    }
                )
            except Exception as e:
                duration = time_module.time() - start_time
                self.error(
                    f"Failed {operation_name}",
                    {
                        "operation": operation_name,
                        "duration_seconds": round(duration, 3),
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__,
                        **kwargs
                    }
                )
                raise

        return _operation_context()


def get_structured_logger(
    name: str,
    correlation_id: Optional[str] = None,
) -> StructuredLogger:
    """
    Get a StructuredLogger instance with correlation ID support.

    Migration from: seren_utils.logging.get_logger
    """
    return StructuredLogger(name=name, correlation_id=correlation_id)


# Convenience exports
__all__ = [
    # Primary unified logging
    "UnifiedLogger",
    "setup_logging",
    "get_unified_logger",
    "DEFAULT_CONFIG",
    "_safe_serialize",
    "_redact_sensitive",
    # Backward compatibility - MusicWorkflowLogger
    "MusicWorkflowLogger",
    "get_music_logger",
    # Backward compatibility - StructuredLogger
    "StructuredLogger",
    "get_structured_logger",
]
