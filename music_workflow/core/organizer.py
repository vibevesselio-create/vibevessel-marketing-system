"""
File organization logic for music workflow.

This module provides file path generation, directory organization,
and backup management for music files.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from music_workflow.core.models import TrackInfo, OrganizeResult
from music_workflow.utils.errors import FileOperationError
from music_workflow.utils.file_ops import (
    ensure_directory,
    safe_copy,
    safe_move,
    create_backup,
)
from music_workflow.utils.validators import sanitize_filename
from music_workflow.config.constants import DefaultPaths


@dataclass
class OrganizationOptions:
    """Options for file organization."""
    music_root: Path = DefaultPaths.MUSIC_ROOT
    backup_root: Path = DefaultPaths.BACKUP_ROOT
    create_backups: bool = True
    organize_by_playlist: bool = True
    organize_by_artist: bool = False
    flatten_structure: bool = False


class FileOrganizer:
    """Organize files into structured directories.

    Handles file path generation based on metadata, directory organization,
    backup management, and file movement with verification.
    """

    def __init__(self, options: Optional[OrganizationOptions] = None):
        """Initialize the organizer.

        Args:
            options: Organization options
        """
        self.options = options or OrganizationOptions()

    def get_output_path(
        self,
        track: TrackInfo,
        format: str,
        base_path: Optional[Path] = None,
    ) -> Path:
        """Generate output path for track.

        Args:
            track: Track information
            format: File format (e.g., "m4a", "wav")
            base_path: Base output path (overrides default)

        Returns:
            Generated output path
        """
        base_path = base_path or self.options.music_root

        # Build path components
        components = []

        # Add playlist directory
        if self.options.organize_by_playlist and track.playlist:
            components.append(sanitize_filename(track.playlist))

        # Add artist directory (optional)
        if self.options.organize_by_artist and track.artist:
            components.append(sanitize_filename(track.artist))

        # Generate filename
        filename = self._generate_filename(track, format)

        # Build full path
        if components and not self.options.flatten_structure:
            return base_path / Path(*components) / filename
        else:
            return base_path / filename

    def _generate_filename(self, track: TrackInfo, format: str) -> str:
        """Generate filename from track metadata.

        Args:
            track: Track information
            format: File format

        Returns:
            Generated filename
        """
        # Build filename parts
        parts = []

        if track.artist:
            parts.append(sanitize_filename(track.artist))

        if track.title:
            parts.append(sanitize_filename(track.title))
        else:
            parts.append("untitled")

        # Join with separator
        base_name = " - ".join(parts) if len(parts) > 1 else parts[0]

        return f"{base_name}.{format}"

    def organize(
        self,
        source: Path,
        track: TrackInfo,
        move: bool = True,
    ) -> OrganizeResult:
        """Move or copy file to appropriate location.

        Args:
            source: Source file path
            track: Track information for path generation
            move: Whether to move (True) or copy (False)

        Returns:
            OrganizeResult with operation details

        Raises:
            FileOperationError: If organization fails
        """
        if not source.exists():
            raise FileOperationError(
                f"Source file does not exist: {source}",
                file_path=str(source),
                operation="organize",
            )

        # Get format from source file
        format = source.suffix.lstrip(".")

        # Generate destination path
        destination = self.get_output_path(track, format)

        # Create backup if enabled
        backup_paths = []
        if self.options.create_backups:
            try:
                backup_path, _ = create_backup(
                    source,
                    self.options.backup_root / "pre_organize",
                )
                backup_paths.append(backup_path)
            except Exception:
                pass  # Continue even if backup fails

        # Ensure destination directory exists
        ensure_directory(destination.parent)

        # Move or copy file
        try:
            if move:
                safe_move(source, destination, overwrite=True)
            else:
                safe_copy(source, destination, overwrite=True)

            return OrganizeResult(
                success=True,
                source_path=source,
                destination_path=destination,
                backup_paths=backup_paths,
            )

        except FileOperationError as e:
            return OrganizeResult(
                success=False,
                source_path=source,
                destination_path=destination,
                backup_paths=backup_paths,
                errors=[str(e)],
            )

    def create_backups(
        self,
        source: Path,
        backup_dirs: Optional[List[Path]] = None,
    ) -> List[Path]:
        """Create backup copies in specified directories.

        Args:
            source: Source file path
            backup_dirs: List of backup directories

        Returns:
            List of backup file paths

        Raises:
            FileOperationError: If backup fails
        """
        if not source.exists():
            raise FileOperationError(
                f"Source file does not exist: {source}",
                file_path=str(source),
                operation="backup",
            )

        backup_dirs = backup_dirs or [self.options.backup_root]
        backup_paths = []

        for backup_dir in backup_dirs:
            try:
                backup_path, _ = create_backup(source, backup_dir)
                backup_paths.append(backup_path)
            except FileOperationError as e:
                # Log but continue with other backups
                pass

        return backup_paths

    def organize_batch(
        self,
        tracks: List[tuple],
        move: bool = True,
    ) -> Dict[str, OrganizeResult]:
        """Organize multiple files.

        Args:
            tracks: List of (source_path, track_info) tuples
            move: Whether to move (True) or copy (False)

        Returns:
            Dictionary mapping track IDs to results
        """
        results = {}

        for source, track in tracks:
            try:
                result = self.organize(Path(source), track, move)
                results[track.id] = result
            except Exception as e:
                results[track.id] = OrganizeResult(
                    success=False,
                    source_path=Path(source),
                    destination_path=Path(""),
                    errors=[str(e)],
                )

        return results

    def get_playlist_directory(self, playlist_name: str) -> Path:
        """Get directory path for a playlist.

        Args:
            playlist_name: Playlist name

        Returns:
            Directory path
        """
        safe_name = sanitize_filename(playlist_name)
        return self.options.music_root / safe_name

    def ensure_playlist_structure(self, playlist_name: str) -> Path:
        """Ensure playlist directory structure exists.

        Args:
            playlist_name: Playlist name

        Returns:
            Playlist directory path
        """
        playlist_dir = self.get_playlist_directory(playlist_name)
        ensure_directory(playlist_dir)
        return playlist_dir

    def cleanup_empty_directories(
        self,
        root: Optional[Path] = None,
        dry_run: bool = True,
    ) -> List[Path]:
        """Find and optionally remove empty directories.

        Args:
            root: Root directory to scan
            dry_run: If True, only report empty directories

        Returns:
            List of empty directories (removed if dry_run=False)
        """
        root = root or self.options.music_root
        empty_dirs = []

        for dirpath in root.rglob("*"):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                empty_dirs.append(dirpath)
                if not dry_run:
                    try:
                        dirpath.rmdir()
                    except OSError:
                        pass

        return empty_dirs
