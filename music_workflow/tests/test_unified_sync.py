"""Tests for unified library sync functionality.

These tests validate the cross-platform matching and sync capabilities
of the unified_sync module.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Import modules under test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.unified_sync.cross_matcher import (
    CrossPlatformMatcher,
    UnifiedTrackMatch,
    PlatformTrackRef,
)
from integrations.unified_sync.orchestrator import (
    UnifiedLibrarySync,
    SyncReport,
    TrackConflict,
    ConflictResolution,
)
from integrations.unified_sync.validators import (
    LibraryValidator,
    ValidationReport,
    ValidationIssue,
    IssueSeverity,
)


class TestPlatformTrackRef:
    """Tests for PlatformTrackRef dataclass."""

    def test_create_basic_ref(self):
        """Test creating a basic platform reference."""
        ref = PlatformTrackRef(
            platform="notion",
            platform_id="abc123",
            title="Test Track",
            artist="Test Artist",
        )
        assert ref.platform == "notion"
        assert ref.platform_id == "abc123"
        assert ref.title == "Test Track"
        assert ref.artist == "Test Artist"

    def test_optional_fields(self):
        """Test optional fields default to None or empty."""
        ref = PlatformTrackRef(
            platform="apple_music",
            platform_id="xyz789",
        )
        assert ref.bpm is None
        assert ref.key is None
        assert ref.file_path is None
        assert ref.play_count == 0


class TestUnifiedTrackMatch:
    """Tests for UnifiedTrackMatch dataclass."""

    def test_create_unified_match(self):
        """Test creating a unified track match."""
        match = UnifiedTrackMatch(
            match_id="unified_1",
            canonical_title="Test Track",
            canonical_artist="Test Artist",
        )
        assert match.match_id == "unified_1"
        assert match.canonical_title == "Test Track"
        assert len(match.platforms) == 0
        assert match.has_conflicts is False

    def test_add_platforms(self):
        """Test adding platforms to match."""
        match = UnifiedTrackMatch(match_id="unified_1")
        match.platforms.add("notion")
        match.platforms.add("apple_music")

        assert "notion" in match.platforms
        assert "apple_music" in match.platforms
        assert len(match.platforms) == 2


class TestCrossPlatformMatcher:
    """Tests for CrossPlatformMatcher."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create mock Notion client."""
        client = Mock()
        client.databases.query.return_value = {
            "results": [],
            "has_more": False,
        }
        return client

    @pytest.fixture
    def matcher(self, mock_notion_client):
        """Create matcher instance."""
        return CrossPlatformMatcher(
            mock_notion_client,
            "test_db_id",
            fuzzy_threshold=0.85,
        )

    def test_init(self, matcher):
        """Test matcher initialization."""
        assert matcher.db_id == "test_db_id"
        assert matcher.fuzzy_threshold == 0.85
        assert len(matcher._notion_tracks) == 0

    def test_make_title_artist_key(self, matcher):
        """Test title/artist key generation."""
        key = matcher._make_title_artist_key("Test Track", "Test Artist")
        assert key == "test track|test artist"

        # Test with None values
        key = matcher._make_title_artist_key("Track", None)
        assert key == "track|"

    def test_authority_ranking(self, matcher):
        """Test authority ranking for field resolution."""
        # BPM should prefer djay_pro
        assert matcher.AUTHORITY_RANKING["bpm"][0] == "djay_pro"

        # Title should prefer Notion
        assert matcher.AUTHORITY_RANKING["title"][0] == "notion"

    def test_load_notion_tracks(self, matcher, mock_notion_client):
        """Test loading Notion tracks."""
        mock_notion_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page_1",
                    "properties": {
                        "Title": {"title": [{"plain_text": "Track 1"}]},
                        "Artist": {"rich_text": [{"plain_text": "Artist 1"}]},
                        "Tempo": {"number": 128.0},
                    }
                }
            ],
            "has_more": False,
        }

        matcher.load_notion_tracks()

        assert len(matcher._notion_tracks) == 1
        assert "page_1" in matcher._notion_tracks

    def test_index_track(self, matcher):
        """Test track indexing."""
        ref = PlatformTrackRef(
            platform="notion",
            platform_id="page_1",
            title="Test Track",
            artist="Test Artist",
            file_path="/path/to/track.mp3",
        )

        matcher._index_track("notion", "page_1", ref)

        # Check path index
        assert "/path/to/track.mp3" in matcher._path_index

        # Check filename index
        assert "track.mp3" in matcher._filename_index

        # Check title/artist index
        assert "test track|test artist" in matcher._title_artist_index

    def test_build_unified_index(self, matcher):
        """Test building unified index."""
        # Add some test tracks
        matcher._notion_tracks["page_1"] = PlatformTrackRef(
            platform="notion",
            platform_id="page_1",
            title="Track 1",
            artist="Artist 1",
            file_path="/path/to/track1.mp3",
        )
        matcher._index_track("notion", "page_1", matcher._notion_tracks["page_1"])

        unified = matcher.build_unified_index()

        assert len(unified) == 1
        assert unified[0].canonical_title == "Track 1"

    def test_get_statistics(self, matcher):
        """Test statistics generation."""
        stats = matcher.get_statistics()

        assert "total_unified_tracks" in stats
        assert "all_platforms" in stats
        assert "platform_coverage" in stats


class TestUnifiedLibrarySync:
    """Tests for UnifiedLibrarySync orchestrator."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create mock Notion client."""
        client = Mock()
        client.databases.query.return_value = {
            "results": [],
            "has_more": False,
        }
        client.pages.update.return_value = {"id": "test_page"}
        return client

    @pytest.fixture
    def sync(self, mock_notion_client):
        """Create sync instance."""
        return UnifiedLibrarySync(
            notion_client=mock_notion_client,
            music_tracks_db_id="test_db_id",
        )

    def test_init(self, sync):
        """Test sync initialization."""
        assert sync.db_id == "test_db_id"
        assert sync.conflict_resolution == ConflictResolution.AUTHORITY

    def test_full_sync_dry_run(self, sync):
        """Test full sync in dry run mode."""
        report = sync.full_sync(dry_run=True)

        assert isinstance(report, SyncReport)
        assert report.dry_run is True
        assert report.total_tracks >= 0

    def test_sync_report_summary(self):
        """Test sync report summary generation."""
        report = SyncReport(
            total_tracks=100,
            total_matched=80,
            synced_to_notion=50,
            conflicts=[TrackConflict(
                unified_match_id="test",
                field="bpm",
                values={"notion": 128, "djay_pro": 130},
            )],
        )

        summary = report.summary()

        assert "100" in summary
        assert "80" in summary
        assert "50" in summary
        assert "UNIFIED LIBRARY SYNC REPORT" in summary

    def test_sync_report_to_dict(self):
        """Test sync report serialization."""
        report = SyncReport(
            total_tracks=50,
            synced_to_notion=25,
        )

        d = report.to_dict()

        assert d["total_tracks"] == 50
        assert d["synced_to_notion"] == 25
        assert "timestamp" in d


class TestLibraryValidator:
    """Tests for LibraryValidator."""

    @pytest.fixture
    def mock_matcher(self):
        """Create mock matcher."""
        matcher = Mock(spec=CrossPlatformMatcher)
        matcher._notion_tracks = {}
        matcher._apple_music_tracks = {}
        matcher._rekordbox_tracks = {}
        matcher._djay_pro_tracks = {}
        matcher._path_index = {}
        matcher._filename_index = {}
        matcher._title_artist_index = {}
        matcher.build_unified_index.return_value = []
        matcher.get_statistics.return_value = {
            "total_unified_tracks": 0,
            "all_platforms": 0,
            "multi_platform": 0,
            "single_platform": 0,
            "with_conflicts": 0,
        }
        return matcher

    @pytest.fixture
    def validator(self, mock_matcher):
        """Create validator instance."""
        return LibraryValidator(mock_matcher)

    def test_init(self, validator, mock_matcher):
        """Test validator initialization."""
        assert validator.matcher == mock_matcher

    def test_full_validation_empty(self, validator):
        """Test validation with no tracks."""
        report = validator.full_validation()

        assert isinstance(report, ValidationReport)
        assert report.total_tracks == 0
        assert report.health_score == 100.0

    def test_validation_report_summary(self):
        """Test validation report summary."""
        report = ValidationReport(
            total_tracks=100,
            health_score=85.5,
            platforms_checked=["notion", "apple_music"],
        )

        summary = report.summary()

        assert "85.5%" in summary
        assert "100" in summary
        assert "notion" in summary

    def test_validation_issue_creation(self):
        """Test validation issue creation."""
        issue = ValidationIssue(
            severity=IssueSeverity.WARNING,
            category="test_issue",
            message="Test message",
            affected_tracks=["track_1", "track_2"],
        )

        assert issue.severity == IssueSeverity.WARNING
        assert issue.category == "test_issue"
        assert len(issue.affected_tracks) == 2

    def test_quick_check(self, validator, mock_matcher):
        """Test quick validation check."""
        result = validator.quick_check()

        assert "timestamp" in result
        assert "platforms_loaded" in result
        assert "status" in result

    def test_calculate_health_score(self, validator):
        """Test health score calculation."""
        report = ValidationReport()

        # Add some issues
        report.issues = [
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                category="test",
                message="Test",
            ),
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                category="test",
                message="Test",
            ),
        ]

        score = validator._calculate_health_score(report)

        # Should deduct 3 for warning, 10 for error
        assert score == 87.0


class TestConflictDetection:
    """Tests for conflict detection."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with test data."""
        mock_client = Mock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
        }
        return CrossPlatformMatcher(mock_client, "test_db")

    def test_detect_bpm_conflict(self, matcher):
        """Test BPM conflict detection."""
        refs = {
            "notion": PlatformTrackRef(
                platform="notion",
                platform_id="1",
                title="Track",
                bpm=128.0,
            ),
            "djay_pro": PlatformTrackRef(
                platform="djay_pro",
                platform_id="2",
                title="Track",
                bpm=130.5,
            ),
        }

        conflicts = matcher._detect_conflicts(refs)

        assert len(conflicts) == 1
        assert conflicts[0]["field"] == "bpm"
        assert conflicts[0]["max_difference"] == 2.5

    def test_no_conflict_similar_bpm(self, matcher):
        """Test no conflict for similar BPM values."""
        refs = {
            "notion": PlatformTrackRef(
                platform="notion",
                platform_id="1",
                title="Track",
                bpm=128.0,
            ),
            "djay_pro": PlatformTrackRef(
                platform="djay_pro",
                platform_id="2",
                title="Track",
                bpm=128.5,
            ),
        }

        conflicts = matcher._detect_conflicts(refs)

        assert len(conflicts) == 0

    def test_detect_key_conflict(self, matcher):
        """Test key conflict detection."""
        refs = {
            "notion": PlatformTrackRef(
                platform="notion",
                platform_id="1",
                title="Track",
                key="Am",
            ),
            "rekordbox": PlatformTrackRef(
                platform="rekordbox",
                platform_id="2",
                title="Track",
                key="Bm",
            ),
        }

        conflicts = matcher._detect_conflicts(refs)

        assert len(conflicts) == 1
        assert conflicts[0]["field"] == "key"


class TestFieldResolution:
    """Tests for field resolution using authority ranking."""

    @pytest.fixture
    def matcher(self):
        """Create matcher."""
        mock_client = Mock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
        }
        return CrossPlatformMatcher(mock_client, "test_db")

    def test_resolve_bpm_djay_wins(self, matcher):
        """Test BPM resolution with djay Pro authority."""
        refs = {
            "notion": PlatformTrackRef(
                platform="notion",
                platform_id="1",
                bpm=128.0,
            ),
            "djay_pro": PlatformTrackRef(
                platform="djay_pro",
                platform_id="2",
                bpm=130.0,
            ),
        }

        bpm = matcher._resolve_field("bpm", refs)

        assert bpm == 130.0  # djay_pro wins

    def test_resolve_title_notion_wins(self, matcher):
        """Test title resolution with Notion authority."""
        refs = {
            "notion": PlatformTrackRef(
                platform="notion",
                platform_id="1",
                title="Correct Title",
            ),
            "apple_music": PlatformTrackRef(
                platform="apple_music",
                platform_id="2",
                title="Different Title",
            ),
        }

        title = matcher._resolve_field("title", refs)

        assert title == "Correct Title"  # notion wins

    def test_resolve_fallback_to_any(self, matcher):
        """Test fallback when authority source has no value."""
        refs = {
            "rekordbox": PlatformTrackRef(
                platform="rekordbox",
                platform_id="1",
                bpm=125.0,
            ),
        }

        # djay_pro is first in authority but not present
        bpm = matcher._resolve_field("bpm", refs)

        assert bpm == 125.0  # Falls back to rekordbox


class TestAppleMusicIntegration:
    """Tests for Apple Music integration components."""

    def test_apple_music_track_import(self):
        """Test Apple Music track model import."""
        try:
            from integrations.apple_music.models import AppleMusicTrack
            track = AppleMusicTrack(
                persistent_id="ABC123",
                database_id=1,
                name="Test Track",
                artist="Test Artist",
            )
            assert track.persistent_id == "ABC123"
        except ImportError:
            pytest.skip("Apple Music module not available")

    def test_apple_music_matcher_import(self):
        """Test Apple Music matcher import."""
        try:
            from integrations.apple_music.matcher import AppleMusicTrackMatcher
            assert AppleMusicTrackMatcher is not None
        except ImportError:
            pytest.skip("Apple Music matcher not available")


class TestRekordboxIntegration:
    """Tests for Rekordbox integration components."""

    def test_rekordbox_track_import(self):
        """Test Rekordbox track model import."""
        try:
            from integrations.rekordbox.models import RekordboxTrack
            track = RekordboxTrack(
                track_id=1,
                title="Test Track",
                artist="Test Artist",
            )
            assert track.track_id == 1
        except ImportError:
            pytest.skip("Rekordbox module not available")

    def test_rekordbox_matcher_import(self):
        """Test Rekordbox matcher import."""
        try:
            from integrations.rekordbox.matcher import RekordboxTrackMatcher
            assert RekordboxTrackMatcher is not None
        except ImportError:
            pytest.skip("Rekordbox matcher not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
