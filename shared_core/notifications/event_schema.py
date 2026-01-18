"""
Notification event schema shared across webhook and automation services.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EventStatus(str, Enum):
    OK = "ok"
    RUNNING = "running"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass
class NotificationEvent:
    """Structured notification event payload."""
    run_id: str
    script_name: str
    event_type: str
    severity: EventSeverity
    phase: str
    status: EventStatus
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
