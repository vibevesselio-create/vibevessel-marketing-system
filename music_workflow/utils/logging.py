"""
Logging utilities for music workflow.

DEPRECATED: This module now redirects to shared_core.logging.
All new code should use:
    from shared_core.logging import setup_logging, get_music_logger

This module provides backward compatibility for existing imports.
"""

import warnings
from pathlib import Path
from typing import Optional

# Redirect to unified logging module
from shared_core.logging import (
    MusicWorkflowLogger,
    get_music_logger,
    setup_logging,
    UnifiedLogger,
)

# Issue deprecation warning on import
warnings.warn(
    "music_workflow.utils.logging is deprecated. "
    "Use 'from shared_core.logging import setup_logging' instead.",
    DeprecationWarning,
    stacklevel=2
)


def get_logger(
    name: str = "music_workflow",
    level: str = "INFO",
    log_file: Optional[Path] = None,
) -> MusicWorkflowLogger:
    """
    Get or create a logger instance.

    DEPRECATED: Use shared_core.logging.get_music_logger instead.

    Args:
        name: Logger name
        level: Log level
        log_file: Optional log file path

    Returns:
        MusicWorkflowLogger instance
    """
    return get_music_logger(
        name=name,
        level=level,
        log_file=str(log_file) if log_file else None,
    )


def log_execution(
    script_name: str,
    status: str,
    duration: float,
    metrics: Optional[dict] = None,
) -> dict:
    """Create execution log entry.

    Args:
        script_name: Name of the script/service
        status: Execution status (Success, Failed, Partial)
        duration: Execution duration in seconds
        metrics: Optional execution metrics

    Returns:
        Execution log entry dictionary
    """
    from datetime import datetime
    return {
        "timestamp": datetime.now().isoformat(),
        "script": script_name,
        "status": status,
        "duration_seconds": duration,
        "metrics": metrics or {},
    }


# Re-export for backward compatibility
__all__ = [
    "MusicWorkflowLogger",
    "get_logger",
    "get_music_logger",
    "log_execution",
]
