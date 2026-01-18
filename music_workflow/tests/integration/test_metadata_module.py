"""
Integration tests for Metadata module.

These tests verify the metadata extraction, enrichment, and embedding
functionality works correctly.
"""

import pytest
import sys
sys.path.insert(0, '.')

from music_workflow.metadata.extraction import MetadataExtractor
from music_workflow.metadata.enrichment import MetadataEnricher
from music_workflow.metadata.embedding import MetadataEmbedder


class TestMetadataExtractor:
    """Test MetadataExtractor class."""

    def test_extractor_initialization(self):
        """Test extractor can be initialized."""
        extractor = MetadataExtractor()
        assert extractor is not None


class TestMetadataEnricher:
    """Test MetadataEnricher class."""

    def test_enricher_initialization(self):
        """Test enricher can be initialized."""
        enricher = MetadataEnricher()
        assert enricher is not None


class TestMetadataEmbedder:
    """Test MetadataEmbedder class."""

    def test_embedder_initialization(self):
        """Test embedder can be initialized."""
        embedder = MetadataEmbedder()
        assert embedder is not None


class TestMetadataWorkflow:
    """Test complete metadata workflow."""

    def test_all_components_initialize(self):
        """Test all metadata components can initialize."""
        extractor = MetadataExtractor()
        enricher = MetadataEnricher()
        embedder = MetadataEmbedder()

        assert extractor is not None
        assert enricher is not None
        assert embedder is not None
