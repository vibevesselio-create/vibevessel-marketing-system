"""Core workflow modules - download, process, organize."""

from music_workflow.core.models import (
    TrackInfo,
    TrackStatus,
    AudioFormat,
    AudioAnalysis,
    DownloadResult,
    OrganizeResult,
    DeduplicationResult,
)
from music_workflow.core.downloader import (
    Downloader,
    DownloadOptions,
)
from music_workflow.core.processor import (
    AudioProcessor,
    ProcessingOptions,
)
from music_workflow.core.organizer import (
    FileOrganizer,
    OrganizationOptions,
)
from music_workflow.core.workflow import (
    MusicWorkflow,
    WorkflowOptions,
    WorkflowResult,
    process_url,
)

__all__ = [
    # Models
    "TrackInfo",
    "TrackStatus",
    "AudioFormat",
    "AudioAnalysis",
    "DownloadResult",
    "OrganizeResult",
    "DeduplicationResult",
    # Downloader
    "Downloader",
    "DownloadOptions",
    # Processor
    "AudioProcessor",
    "ProcessingOptions",
    # Organizer
    "FileOrganizer",
    "OrganizationOptions",
    # Workflow
    "MusicWorkflow",
    "WorkflowOptions",
    "WorkflowResult",
    "process_url",
]
