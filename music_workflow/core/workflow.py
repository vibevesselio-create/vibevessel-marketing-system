"""
Workflow orchestration for music workflow.

This module provides the main workflow orchestration, coordinating
the downloader, processor, and organizer modules for complete
track processing pipelines.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from music_workflow.core.models import (
    TrackInfo,
    TrackStatus,
    DownloadResult,
    OrganizeResult,
    AudioAnalysis,
)
from music_workflow.core.downloader import Downloader, DownloadOptions
from music_workflow.core.processor import AudioProcessor, ProcessingOptions
from music_workflow.core.organizer import FileOrganizer, OrganizationOptions
from music_workflow.utils.errors import (
    MusicWorkflowError,
    DownloadError,
    ProcessingError,
    DuplicateFoundError,
)
from music_workflow.utils.logging import MusicWorkflowLogger


@dataclass
class WorkflowOptions:
    """Options for workflow execution."""
    download_formats: List[str] = None
    analyze_audio: bool = True
    organize_files: bool = True
    create_backups: bool = True
    skip_duplicates: bool = True
    dry_run: bool = False

    def __post_init__(self):
        if self.download_formats is None:
            self.download_formats = ["m4a", "aiff", "wav"]


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    success: bool
    track: TrackInfo
    download_result: Optional[DownloadResult] = None
    audio_analysis: Optional[AudioAnalysis] = None
    organize_result: Optional[OrganizeResult] = None
    errors: List[str] = None
    warnings: List[str] = None
    execution_time_seconds: float = 0.0

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class MusicWorkflow:
    """Main workflow orchestrator.

    Coordinates the download -> process -> organize pipeline for
    music tracks, handling errors and providing progress callbacks.
    """

    def __init__(
        self,
        options: Optional[WorkflowOptions] = None,
        download_options: Optional[DownloadOptions] = None,
        processing_options: Optional[ProcessingOptions] = None,
        organization_options: Optional[OrganizationOptions] = None,
        logger: Optional[MusicWorkflowLogger] = None,
    ):
        """Initialize the workflow.

        Args:
            options: Workflow options
            download_options: Download configuration
            processing_options: Processing configuration
            organization_options: Organization configuration
            logger: Logger instance
        """
        self.options = options or WorkflowOptions()
        self.logger = logger or MusicWorkflowLogger("MusicWorkflow")

        # Initialize components
        self.downloader = Downloader(download_options)
        self.processor = AudioProcessor(processing_options)
        self.organizer = FileOrganizer(organization_options)

        # Progress callback
        self._progress_callback: Optional[Callable[[TrackInfo, str], None]] = None

    def set_progress_callback(
        self, callback: Callable[[TrackInfo, str], None]
    ) -> None:
        """Set a callback for progress updates.

        Args:
            callback: Function called with (track, status_message)
        """
        self._progress_callback = callback

    def _report_progress(self, track: TrackInfo, message: str) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(track, message)
        self.logger.log_track_operation(track.id, "progress", message)

    def process_url(
        self,
        url: str,
        track: Optional[TrackInfo] = None,
        output_dir: Optional[Path] = None,
    ) -> WorkflowResult:
        """Process a track from URL through the full workflow.

        Args:
            url: Source URL (YouTube, SoundCloud, etc.)
            track: Optional existing track info to update
            output_dir: Optional output directory override

        Returns:
            WorkflowResult with all operation results
        """
        start_time = datetime.now()

        # Create or update track info
        if track is None:
            track = TrackInfo(
                id=f"track_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                source_url=url,
            )
        else:
            track.source_url = url

        track.status = TrackStatus.DOWNLOADING
        self._report_progress(track, "Starting download")

        result = WorkflowResult(success=False, track=track)

        try:
            # Step 1: Download
            download_result = self._download_track(url, output_dir)
            result.download_result = download_result

            if not download_result.success:
                track.add_error("Download failed")
                result.errors.append("Download failed")
                return result

            # Update track with download metadata
            self._update_track_from_download(track, download_result)
            track.status = TrackStatus.DOWNLOADED
            self._report_progress(track, "Download complete")

            # Step 2: Process (if enabled and files exist)
            if self.options.analyze_audio and download_result.files:
                track.status = TrackStatus.PROCESSING
                self._report_progress(track, "Analyzing audio")

                try:
                    analysis = self._analyze_track(download_result.files[0])
                    result.audio_analysis = analysis
                    self._update_track_from_analysis(track, analysis)
                    track.status = TrackStatus.PROCESSED
                    self._report_progress(track, "Audio analysis complete")
                except ProcessingError as e:
                    result.warnings.append(f"Audio analysis failed: {e}")
                    track.add_warning(f"Audio analysis failed: {e}")

            # Step 3: Organize (if enabled)
            if self.options.organize_files and download_result.files:
                self._report_progress(track, "Organizing files")

                try:
                    organize_result = self._organize_track(
                        download_result.files[0], track
                    )
                    result.organize_result = organize_result

                    if organize_result.success:
                        track.file_paths[download_result.files[0].suffix.lstrip(".")] = (
                            organize_result.destination_path
                        )
                except Exception as e:
                    result.warnings.append(f"Organization failed: {e}")
                    track.add_warning(f"Organization failed: {e}")

            # Mark complete
            track.status = TrackStatus.COMPLETE
            track.processed = True
            result.success = True
            self._report_progress(track, "Workflow complete")

        except DownloadError as e:
            result.errors.append(str(e))
            track.add_error(str(e))
            self.logger.log_error(e, {"url": url})

        except DuplicateFoundError as e:
            track.status = TrackStatus.DUPLICATE
            dup_info = e.existing_track_id or e.existing_track_title or "unknown"
            result.warnings.append(f"Duplicate found: {dup_info}")
            track.add_warning(f"Duplicate of: {dup_info}")
            result.success = True  # Not an error, just skipped

        except MusicWorkflowError as e:
            result.errors.append(str(e))
            track.add_error(str(e))
            self.logger.log_error(e, {"url": url})

        except Exception as e:
            result.errors.append(f"Unexpected error: {e}")
            track.add_error(f"Unexpected error: {e}")
            self.logger.log_error(
                MusicWorkflowError(f"Workflow failed: {e}"),
                {"url": url}
            )

        finally:
            end_time = datetime.now()
            result.execution_time_seconds = (end_time - start_time).total_seconds()

        return result

    def process_track(
        self,
        track: TrackInfo,
        output_dir: Optional[Path] = None,
    ) -> WorkflowResult:
        """Process a track through the workflow using its source URL.

        Args:
            track: Track info with source URL
            output_dir: Optional output directory override

        Returns:
            WorkflowResult with all operation results
        """
        if not track.source_url:
            return WorkflowResult(
                success=False,
                track=track,
                errors=["No source URL provided"],
            )

        return self.process_url(track.source_url, track, output_dir)

    def process_batch(
        self,
        urls: List[str],
        output_dir: Optional[Path] = None,
    ) -> Dict[str, WorkflowResult]:
        """Process multiple URLs through the workflow.

        Args:
            urls: List of source URLs
            output_dir: Optional output directory override

        Returns:
            Dictionary mapping URLs to results
        """
        results = {}
        total = len(urls)

        self.logger.log_workflow_event(
            "batch_start",
            {"total_tracks": total}
        )

        for i, url in enumerate(urls, 1):
            self.logger.info(f"Processing {i}/{total}: {url}")

            try:
                result = self.process_url(url, output_dir=output_dir)
                results[url] = result
            except Exception as e:
                results[url] = WorkflowResult(
                    success=False,
                    track=TrackInfo(id=f"track_{i}", source_url=url),
                    errors=[str(e)],
                )

        # Log summary
        successful = sum(1 for r in results.values() if r.success)
        self.logger.log_workflow_event(
            "batch_complete",
            {
                "total_tracks": total,
                "successful": successful,
                "failed": total - successful,
            }
        )

        return results

    def _download_track(
        self,
        url: str,
        output_dir: Optional[Path] = None,
    ) -> DownloadResult:
        """Download a track from URL.

        Args:
            url: Source URL
            output_dir: Output directory

        Returns:
            DownloadResult
        """
        return self.downloader.download(
            url,
            output_dir=output_dir,
            formats=self.options.download_formats,
        )

    def _analyze_track(self, file_path: Path) -> AudioAnalysis:
        """Analyze audio file.

        Args:
            file_path: Path to audio file

        Returns:
            AudioAnalysis
        """
        return self.processor.analyze(file_path)

    def _organize_track(
        self,
        source: Path,
        track: TrackInfo,
    ) -> OrganizeResult:
        """Organize track file.

        Args:
            source: Source file path
            track: Track info for path generation

        Returns:
            OrganizeResult
        """
        return self.organizer.organize(source, track)

    def _update_track_from_download(
        self,
        track: TrackInfo,
        result: DownloadResult,
    ) -> None:
        """Update track info from download result."""
        if result.metadata:
            track.title = result.metadata.get("title", track.title)
            track.artist = result.metadata.get("uploader", track.artist)
            track.duration = result.duration_seconds

            # Add platform-specific IDs
            if "id" in result.metadata:
                if "youtube" in (result.source_url or "").lower():
                    track.extra_metadata["youtube_id"] = result.metadata["id"]
                elif "soundcloud" in (result.source_url or "").lower():
                    track.extra_metadata["soundcloud_id"] = result.metadata["id"]

        # Add file paths
        for file_path in result.files:
            format = file_path.suffix.lstrip(".")
            track.add_file(format, file_path)

    def _update_track_from_analysis(
        self,
        track: TrackInfo,
        analysis: AudioAnalysis,
    ) -> None:
        """Update track info from audio analysis."""
        track.bpm = analysis.bpm
        track.key = analysis.key
        track.duration = analysis.duration
        track.loudness = analysis.loudness
        track.extra_metadata["sample_rate"] = analysis.sample_rate
        track.extra_metadata["channels"] = analysis.channels


# Convenience function for simple usage
def process_url(url: str, **options) -> WorkflowResult:
    """Process a single URL through the default workflow.

    Args:
        url: Source URL
        **options: Workflow options

    Returns:
        WorkflowResult
    """
    workflow_options = WorkflowOptions(**options) if options else None
    workflow = MusicWorkflow(options=workflow_options)
    return workflow.process_url(url)
