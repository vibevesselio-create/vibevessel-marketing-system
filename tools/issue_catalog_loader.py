"""Issue catalog data models.

Provides IssueRecord dataclass used by Linear and GitHub sync clients.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class IssueRecord:
    """Represents an issue/task that can be synced across platforms.

    Used as the common data model for syncing between Notion, Linear, and GitHub.
    """

    # Core identity
    id: str  # Source system ID (e.g., Notion page ID)
    title: str

    # Content
    description: str = ""
    body: str = ""  # Full body content (markdown)

    # Status/State
    status: str = "open"
    priority: Optional[str] = None  # "urgent", "high", "medium", "low"

    # Metadata
    labels: List[str] = field(default_factory=list)
    assignee: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # External references
    linear_id: Optional[str] = None
    linear_url: Optional[str] = None
    github_id: Optional[str] = None
    github_number: Optional[int] = None
    github_url: Optional[str] = None
    notion_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "body": self.body,
            "status": self.status,
            "priority": self.priority,
            "labels": self.labels,
            "assignee": self.assignee,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "linear_id": self.linear_id,
            "linear_url": self.linear_url,
            "github_id": self.github_id,
            "github_number": self.github_number,
            "github_url": self.github_url,
            "notion_id": self.notion_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IssueRecord":
        """Create from dictionary."""
        if data.get("created_at") and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at") and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


__all__ = ["IssueRecord"]
