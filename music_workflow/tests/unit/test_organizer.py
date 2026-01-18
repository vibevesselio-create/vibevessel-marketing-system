"""
Unit tests for the file organizer module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

import sys
sys.path.insert(0, '.')

from music_workflow.core.organizer import (
    FileOrganizer,
    OrganizationOptions,
)
from music_workflow.core.models import TrackInfo, OrganizeResult
from music_workflow.utils.errors import FileOperationError


class TestOrganizationOptions:
    """Test OrganizationOptions dataclass."""

    def test_default_options(self):
        """Test default organization options."""
        options = OrganizationOptions()
        assert options.create_backups is True
        assert options.organize_by_playlist is True
        assert options.organize_by_artist is False
        assert options.flatten_structure is False

    def test_custom_options(self):
        """Test custom organization options."""
        options = OrganizationOptions(
            create_backups=False,
            organize_by_playlist=False,
            organize_by_artist=True,
            flatten_structure=True
        )
        assert options.create_backups is False
        assert options.organize_by_playlist is False
        assert options.organize_by_artist is True
        assert options.flatten_structure is True


class TestFileOrganizer:
    """Test FileOrganizer class."""

    def test_organizer_initialization(self):
        """Test organizer can be initialized."""
        organizer = FileOrganizer()
        assert organizer is not None
        assert organizer.options is not None
        assert isinstance(organizer.options, OrganizationOptions)

    def test_organizer_with_options(self):
        """Test organizer with custom options."""
        options = OrganizationOptions(create_backups=False)
        organizer = FileOrganizer(options=options)
        assert organizer.options.create_backups is False


class TestGenerateFilename:
    """Test filename generation."""

    def test_generate_filename_with_artist_and_title(self):
        """Test filename with artist and title."""
        organizer = FileOrganizer()

        track = TrackInfo(
            id="test-123",
            title="My Track",
            artist="Test Artist"
        )

        filename = organizer._generate_filename(track, "m4a")
        assert "Test Artist" in filename
        assert "My Track" in filename
        assert filename.endswith(".m4a")

    def test_generate_filename_title_only(self):
        """Test filename with title only."""
        organizer = FileOrganizer()

        track = TrackInfo(
            id="test-123",
            title="My Track",
            artist=None
        )

        filename = organizer._generate_filename(track, "wav")
        assert "My Track" in filename
        assert filename.endswith(".wav")

    def test_generate_filename_no_title(self):
        """Test filename without title defaults to untitled."""
        organizer = FileOrganizer()

        track = TrackInfo(
            id="test-123",
            title=None,
            artist="Test Artist"
        )

        filename = organizer._generate_filename(track, "aiff")
        assert "untitled" in filename
        assert filename.endswith(".aiff")


class TestGetOutputPath:
    """Test output path generation."""

    def test_get_output_path_with_playlist(self):
        """Test output path includes playlist directory."""
        options = OrganizationOptions(
            music_root=Path("/music"),
            organize_by_playlist=True
        )
        organizer = FileOrganizer(options=options)

        track = TrackInfo(
            id="test-123",
            title="My Track",
            artist="Test Artist",
            playlist="Summer Vibes"
        )

        path = organizer.get_output_path(track, "m4a")
        assert "Summer Vibes" in str(path)
        assert path.suffix == ".m4a"

    def test_get_output_path_with_artist(self):
        """Test output path includes artist directory when enabled."""
        options = OrganizationOptions(
            music_root=Path("/music"),
            organize_by_artist=True,
            organize_by_playlist=False
        )
        organizer = FileOrganizer(options=options)

        track = TrackInfo(
            id="test-123",
            title="My Track",
            artist="Test Artist"
        )

        path = organizer.get_output_path(track, "m4a")
        assert "Test Artist" in str(path)

    def test_get_output_path_flatten(self):
        """Test flat output path structure."""
        options = OrganizationOptions(
            music_root=Path("/music"),
            organize_by_playlist=True,
            flatten_structure=True
        )
        organizer = FileOrganizer(options=options)

        track = TrackInfo(
            id="test-123",
            title="My Track",
            artist="Test Artist",
            playlist="Summer Vibes"
        )

        path = organizer.get_output_path(track, "m4a")
        # With flatten, playlist should not be in path
        assert path.parent == Path("/music")

    def test_get_output_path_custom_base(self):
        """Test output path with custom base path."""
        organizer = FileOrganizer()

        track = TrackInfo(
            id="test-123",
            title="My Track"
        )

        custom_base = Path("/custom/output")
        path = organizer.get_output_path(track, "m4a", base_path=custom_base)
        assert str(path).startswith(str(custom_base))


class TestOrganize:
    """Test organize method."""

    def test_organize_source_not_exists(self):
        """Test organize fails when source doesn't exist."""
        organizer = FileOrganizer()

        track = TrackInfo(id="test-123", title="My Track")

        with pytest.raises(FileOperationError) as exc_info:
            organizer.organize(Path("/nonexistent/file.m4a"), track)
        assert "does not exist" in str(exc_info.value)

    @patch('music_workflow.core.organizer.ensure_directory')
    @patch('music_workflow.core.organizer.safe_move')
    @patch('music_workflow.core.organizer.create_backup')
    def test_organize_success_with_move(
        self,
        mock_backup,
        mock_move,
        mock_ensure
    ):
        """Test successful organize with move."""
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            source_path = Path(f.name)

        try:
            options = OrganizationOptions(
                music_root=Path("/music"),
                create_backups=False
            )
            organizer = FileOrganizer(options=options)

            track = TrackInfo(id="test-123", title="My Track")

            result = organizer.organize(source_path, track, move=True)

            assert result.success is True
            assert result.source_path == source_path
            mock_move.assert_called_once()
        finally:
            source_path.unlink(missing_ok=True)

    @patch('music_workflow.core.organizer.ensure_directory')
    @patch('music_workflow.core.organizer.safe_copy')
    @patch('music_workflow.core.organizer.create_backup')
    def test_organize_success_with_copy(
        self,
        mock_backup,
        mock_copy,
        mock_ensure
    ):
        """Test successful organize with copy."""
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            source_path = Path(f.name)

        try:
            options = OrganizationOptions(
                music_root=Path("/music"),
                create_backups=False
            )
            organizer = FileOrganizer(options=options)

            track = TrackInfo(id="test-123", title="My Track")

            result = organizer.organize(source_path, track, move=False)

            assert result.success is True
            mock_copy.assert_called_once()
        finally:
            source_path.unlink(missing_ok=True)


class TestCreateBackups:
    """Test backup creation."""

    def test_create_backups_source_not_exists(self):
        """Test backup fails when source doesn't exist."""
        organizer = FileOrganizer()

        with pytest.raises(FileOperationError) as exc_info:
            organizer.create_backups(Path("/nonexistent/file.m4a"))
        assert "does not exist" in str(exc_info.value)

    @patch('music_workflow.core.organizer.create_backup')
    def test_create_backups_success(self, mock_backup):
        """Test successful backup creation."""
        mock_backup.return_value = (Path("/backup/file.m4a"), "hash")

        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            source_path = Path(f.name)

        try:
            organizer = FileOrganizer()
            backup_paths = organizer.create_backups(
                source_path,
                backup_dirs=[Path("/backup1"), Path("/backup2")]
            )

            assert len(backup_paths) == 2
            assert mock_backup.call_count == 2
        finally:
            source_path.unlink(missing_ok=True)


class TestPlaylistDirectories:
    """Test playlist directory management."""

    def test_get_playlist_directory(self):
        """Test getting playlist directory path."""
        options = OrganizationOptions(music_root=Path("/music"))
        organizer = FileOrganizer(options=options)

        path = organizer.get_playlist_directory("Summer Vibes 2024")
        assert "Summer Vibes 2024" in str(path)
        assert str(path).startswith("/music")

    @patch('music_workflow.core.organizer.ensure_directory')
    def test_ensure_playlist_structure(self, mock_ensure):
        """Test ensuring playlist structure exists."""
        options = OrganizationOptions(music_root=Path("/music"))
        organizer = FileOrganizer(options=options)

        path = organizer.ensure_playlist_structure("New Playlist")

        mock_ensure.assert_called_once()
        assert "New Playlist" in str(path)


class TestBatchOrganize:
    """Test batch organization."""

    @patch('music_workflow.core.organizer.ensure_directory')
    @patch('music_workflow.core.organizer.safe_move')
    def test_organize_batch_success(self, mock_move, mock_ensure):
        """Test batch organization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            file1 = Path(tmpdir) / "track1.m4a"
            file2 = Path(tmpdir) / "track2.m4a"
            file1.touch()
            file2.touch()

            options = OrganizationOptions(
                music_root=Path(tmpdir) / "output",
                create_backups=False
            )
            organizer = FileOrganizer(options=options)

            track1 = TrackInfo(id="track-1", title="Track 1")
            track2 = TrackInfo(id="track-2", title="Track 2")

            tracks = [
                (file1, track1),
                (file2, track2),
            ]

            results = organizer.organize_batch(tracks)

            assert "track-1" in results
            assert "track-2" in results
            assert results["track-1"].success is True
            assert results["track-2"].success is True


class TestCleanupEmptyDirectories:
    """Test empty directory cleanup."""

    def test_cleanup_empty_directories_dry_run(self):
        """Test finding empty directories in dry run mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create empty directories
            (root / "empty1").mkdir()
            (root / "empty2").mkdir()
            (root / "has_file").mkdir()
            (root / "has_file" / "file.txt").touch()

            options = OrganizationOptions(music_root=root)
            organizer = FileOrganizer(options=options)

            empty_dirs = organizer.cleanup_empty_directories(root, dry_run=True)

            # Should find the empty directories
            empty_names = [d.name for d in empty_dirs]
            assert "empty1" in empty_names
            assert "empty2" in empty_names
            assert "has_file" not in empty_names

            # Directories should still exist (dry run)
            assert (root / "empty1").exists()
            assert (root / "empty2").exists()

    def test_cleanup_empty_directories_remove(self):
        """Test removing empty directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create empty directories
            (root / "empty1").mkdir()

            options = OrganizationOptions(music_root=root)
            organizer = FileOrganizer(options=options)

            organizer.cleanup_empty_directories(root, dry_run=False)

            # Directory should be removed
            assert not (root / "empty1").exists()
