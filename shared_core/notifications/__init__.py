"""
Shared Core Notifications Module
================================

macOS notification utilities for workspace scripts.

Usage:
    from shared_core.notifications import send_notification

    send_notification(
        title="Script Complete",
        message="Processing finished successfully",
        sound=True
    )
"""

import subprocess
import sys
from typing import Optional, List

from .event_schema import NotificationEvent, EventSeverity, EventStatus


def send_notification(
    title: str,
    message: str,
    subtitle: Optional[str] = None,
    sound: bool = True,
    sound_name: str = "default"
) -> bool:
    """
    Send a macOS notification.

    Args:
        title: Notification title
        message: Notification body text
        subtitle: Optional subtitle
        sound: Whether to play a sound
        sound_name: Name of the sound to play

    Returns:
        True if notification was sent successfully, False otherwise
    """
    if sys.platform != "darwin":
        # Not on macOS, silently skip
        return False

    try:
        # Build AppleScript
        script_parts = [f'display notification "{message}" with title "{title}"']

        if subtitle:
            script_parts[0] = f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'

        if sound:
            script_parts[0] += f' sound name "{sound_name}"'

        script = script_parts[0]

        # Execute
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )

        return result.returncode == 0

    except Exception:
        return False


def notify_success(task_name: str, details: Optional[str] = None) -> bool:
    """Send a success notification."""
    message = details if details else f"{task_name} completed successfully"
    return send_notification(
        title="Task Complete",
        message=message,
        subtitle=task_name,
        sound=True,
        sound_name="Glass"
    )


def notify_error(task_name: str, error: Optional[str] = None) -> bool:
    """Send an error notification."""
    message = error if error else f"{task_name} failed"
    return send_notification(
        title="Task Failed",
        message=message,
        subtitle=task_name,
        sound=True,
        sound_name="Basso"
    )

class NotificationManager:
    """Async-friendly notification helper used by webhook services."""

    async def send(self, event: NotificationEvent, channels: Optional[List[str]] = None) -> bool:
        # Channels are not routed yet; kept for API compatibility.
        title = f"{event.script_name}: {event.summary}"
        message = f"{event.event_type} ({event.status.value})"
        subtitle = event.phase
        return send_notification(title=title, message=message, subtitle=subtitle, sound=False)


__all__ = [
    "send_notification",
    "notify_success",
    "notify_error",
    "NotificationManager",
    "NotificationEvent",
    "EventSeverity",
    "EventStatus",
]
