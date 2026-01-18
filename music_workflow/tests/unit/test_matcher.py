"""
Unit tests for the duplicate matcher module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '.')

from music_workflow.deduplication.matcher import (
    DuplicateMatcher,
    Match,
    check_for_duplicates,
)
from music_workflow.core.models import TrackInfo, DeduplicationResult
from music_workflow.utils.errors import DuplicateFoundError


class TestMatch:
    """Test Match dataclass."""

    def test_match_creation(self):
        """Test Match can be created."""
        match = Match(
            track_id="track-123",
            source="notion",
            similarity_score=0.95,
            fingerprint_match=True,
            metadata_match=True,
            title="Test Track",
            artist="Test Artist"
        )

        assert match.track_id == "track-123"
        assert match.source == "notion"
        assert match.similarity_score == 0.95
        assert match.fingerprint_match is True
        assert match.metadata_match is True
        assert match.title == "Test Track"
        assert match.artist == "Test Artist"

    def test_match_default_values(self):
        """Test Match default values."""
        match = Match(
            track_id="track-123",
            source="eagle",
            similarity_score=0.8,
            fingerprint_match=False,
            metadata_match=True
        )

        assert match.title is None
        assert match.artist is None


class TestDuplicateMatcher:
    """Test DuplicateMatcher class."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_matcher_initialization(self, mock_settings):
        """Test matcher can be initialized."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=True
            )
        )

        matcher = DuplicateMatcher()
        assert matcher is not None
        assert matcher.fingerprint_threshold == 0.95

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_matcher_custom_threshold(self, mock_settings):
        """Test matcher with custom threshold."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=True
            )
        )

        matcher = DuplicateMatcher(fingerprint_threshold=0.9)
        assert matcher.fingerprint_threshold == 0.9

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_matcher_disable_sources(self, mock_settings):
        """Test matcher with disabled sources."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=True
            )
        )

        matcher = DuplicateMatcher(
            check_notion=False,
            check_eagle=False
        )
        assert matcher.check_notion is False
        assert matcher.check_eagle is False


class TestFindMatches:
    """Test find_matches method."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_find_matches_no_sources(self, mock_settings):
        """Test find_matches with no sources enabled."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=False,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(
            check_notion=False,
            check_eagle=False,
            check_files=False
        )

        track = TrackInfo(id="test-123", title="Test Track")
        matches = matcher.find_matches(track)

        assert matches == []

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_find_matches_sorts_by_similarity(self, mock_settings):
        """Test matches are sorted by similarity score."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(check_eagle=False, check_files=False)

        # Mock notion check to return matches
        with patch.object(matcher, '_check_notion') as mock_check:
            mock_check.return_value = [
                Match(track_id="1", source="notion", similarity_score=0.7,
                      fingerprint_match=False, metadata_match=True),
                Match(track_id="2", source="notion", similarity_score=0.95,
                      fingerprint_match=True, metadata_match=True),
                Match(track_id="3", source="notion", similarity_score=0.85,
                      fingerprint_match=False, metadata_match=True),
            ]

            track = TrackInfo(id="test-123", title="Test Track")
            matches = matcher.find_matches(track)

            # Should be sorted descending by similarity
            assert matches[0].similarity_score == 0.95
            assert matches[1].similarity_score == 0.85
            assert matches[2].similarity_score == 0.7


class TestCheckDuplicate:
    """Test check_duplicate method."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_check_duplicate_no_matches(self, mock_settings):
        """Test check_duplicate with no matches."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(check_eagle=False, check_files=False)

        with patch.object(matcher, 'find_matches', return_value=[]):
            track = TrackInfo(id="test-123", title="Test Track")
            result = matcher.check_duplicate(track)

            assert result.is_duplicate is False
            assert result.similarity_score == 0.0

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_check_duplicate_below_threshold(self, mock_settings):
        """Test check_duplicate with match below threshold."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(
            fingerprint_threshold=0.95,
            check_eagle=False,
            check_files=False
        )

        match = Match(
            track_id="existing-123",
            source="notion",
            similarity_score=0.90,  # Below threshold
            fingerprint_match=False,
            metadata_match=True
        )

        with patch.object(matcher, 'find_matches', return_value=[match]):
            track = TrackInfo(id="test-123", title="Test Track")
            result = matcher.check_duplicate(track)

            assert result.is_duplicate is False
            assert result.similarity_score == 0.90

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_check_duplicate_above_threshold(self, mock_settings):
        """Test check_duplicate with match above threshold."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(
            fingerprint_threshold=0.95,
            check_eagle=False,
            check_files=False
        )

        match = Match(
            track_id="existing-123",
            source="notion",
            similarity_score=0.98,  # Above threshold
            fingerprint_match=True,
            metadata_match=True,
            title="Existing Track"
        )

        with patch.object(matcher, 'find_matches', return_value=[match]):
            track = TrackInfo(id="test-123", title="Test Track")
            result = matcher.check_duplicate(track)

            assert result.is_duplicate is True
            assert result.matching_track_id == "existing-123"
            assert result.matching_source == "notion"
            assert result.fingerprint_match is True


class TestResolve:
    """Test resolve method."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_resolve_no_matches(self, mock_settings):
        """Test resolve with no matches."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        action, reason = matcher.resolve([])
        assert action == "keep"
        assert "No duplicates" in reason

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_resolve_fingerprint_match(self, mock_settings):
        """Test resolve with fingerprint match."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        matches = [
            Match(
                track_id="existing-123",
                source="notion",
                similarity_score=0.99,
                fingerprint_match=True,
                metadata_match=True
            )
        ]

        action, reason = matcher.resolve(matches)
        assert action == "skip"
        assert "Fingerprint match" in reason

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_resolve_metadata_only_match(self, mock_settings):
        """Test resolve with metadata-only match."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        matches = [
            Match(
                track_id="existing-123",
                source="notion",
                similarity_score=0.85,
                fingerprint_match=False,
                metadata_match=True
            )
        ]

        action, reason = matcher.resolve(matches)
        assert action == "merge"
        assert "different version" in reason

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_resolve_below_threshold(self, mock_settings):
        """Test resolve with match below threshold."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher(fingerprint_threshold=0.95)

        matches = [
            Match(
                track_id="existing-123",
                source="notion",
                similarity_score=0.80,
                fingerprint_match=False,
                metadata_match=False
            )
        ]

        action, reason = matcher.resolve(matches)
        assert action == "keep"
        assert "below threshold" in reason


class TestNameSimilarity:
    """Test name similarity calculation."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_exact_match(self, mock_settings):
        """Test exact name match."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        score = matcher._calculate_name_similarity("Test Track", "Test Track")
        assert score == 1.0

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_case_insensitive_match(self, mock_settings):
        """Test case-insensitive name match."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        score = matcher._calculate_name_similarity("TEST TRACK", "test track")
        assert score == 1.0

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_containment_match(self, mock_settings):
        """Test containment produces high score."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        score = matcher._calculate_name_similarity("Test Track", "Test Track (Extended Mix)")
        assert score >= 0.8

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_empty_names(self, mock_settings):
        """Test empty names produce zero score."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        assert matcher._calculate_name_similarity("", "Test") == 0.0
        assert matcher._calculate_name_similarity("Test", "") == 0.0


class TestMetadataSimilarity:
    """Test metadata similarity calculation."""

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_spotify_id_exact_match(self, mock_settings):
        """Test Spotify ID exact match gives perfect score."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        track1 = TrackInfo(id="1", title="Track", spotify_id="spotify:track:123")
        track2 = TrackInfo(id="2", title="Track", spotify_id="spotify:track:123")

        score = matcher._calculate_metadata_similarity(track1, track2)
        assert score == 1.0

    @patch('music_workflow.deduplication.matcher.get_settings')
    def test_duration_similarity(self, mock_settings):
        """Test duration contributes to similarity."""
        mock_settings.return_value = MagicMock(
            deduplication=MagicMock(
                check_notion=True,
                check_eagle=False
            )
        )

        matcher = DuplicateMatcher()

        # Same duration (within 2 seconds)
        track1 = TrackInfo(id="1", title="Track", duration=180.0)
        track2 = TrackInfo(id="2", title="Track", duration=181.0)

        score = matcher._calculate_metadata_similarity(track1, track2)
        # Should include title (0.5) + duration (0.2)
        assert score >= 0.5


class TestCheckForDuplicates:
    """Test check_for_duplicates convenience function."""

    @patch('music_workflow.deduplication.matcher.DuplicateMatcher')
    def test_check_for_duplicates_not_duplicate(self, mock_matcher_class):
        """Test check_for_duplicates returns not duplicate."""
        mock_matcher = MagicMock()
        mock_matcher.check_duplicate.return_value = DeduplicationResult(
            is_duplicate=False,
            similarity_score=0.5
        )
        mock_matcher_class.return_value = mock_matcher

        track = TrackInfo(id="test-123", title="Test Track")
        result = check_for_duplicates(track)

        assert result.is_duplicate is False

    @patch('music_workflow.deduplication.matcher.DuplicateMatcher')
    def test_check_for_duplicates_raises_on_duplicate(self, mock_matcher_class):
        """Test check_for_duplicates raises when configured."""
        mock_matcher = MagicMock()
        mock_matcher.check_duplicate.return_value = DeduplicationResult(
            is_duplicate=True,
            matching_track_id="existing-123",
            matching_source="notion",
            similarity_score=0.98
        )
        mock_matcher_class.return_value = mock_matcher

        track = TrackInfo(id="test-123", title="Test Track")

        with pytest.raises(DuplicateFoundError):
            check_for_duplicates(track, raise_on_duplicate=True)

    @patch('music_workflow.deduplication.matcher.DuplicateMatcher')
    def test_check_for_duplicates_no_raise(self, mock_matcher_class):
        """Test check_for_duplicates doesn't raise by default."""
        mock_matcher = MagicMock()
        mock_matcher.check_duplicate.return_value = DeduplicationResult(
            is_duplicate=True,
            matching_track_id="existing-123",
            matching_source="notion",
            similarity_score=0.98
        )
        mock_matcher_class.return_value = mock_matcher

        track = TrackInfo(id="test-123", title="Test Track")

        # Should not raise
        result = check_for_duplicates(track, raise_on_duplicate=False)
        assert result.is_duplicate is True
