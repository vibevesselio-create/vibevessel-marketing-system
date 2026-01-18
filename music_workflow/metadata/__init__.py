"""Metadata extraction, enrichment, and embedding.

This module provides comprehensive metadata handling for the music workflow:
- Extraction: Read metadata from audio files
- Enrichment: Fetch additional metadata from external sources (Spotify)
- Embedding: Write metadata back to audio files

Usage:
    from music_workflow.metadata import (
        extract_metadata,
        enrich_metadata,
        embed_metadata,
        ExtractedMetadata,
        EnrichmentResult,
        EmbedResult,
    )

    # Extract metadata from file
    metadata = extract_metadata(Path("song.mp3"))

    # Enrich with Spotify data
    enrichment = enrich_metadata(metadata.title, metadata.artist)

    # Embed updated metadata
    result = embed_metadata(Path("song.mp3"), metadata)
"""

from music_workflow.metadata.extraction import (
    MetadataExtractor,
    ExtractedMetadata,
    extract_metadata,
    get_metadata_extractor,
)

from music_workflow.metadata.enrichment import (
    MetadataEnricher,
    EnrichmentResult,
    enrich_metadata,
    get_metadata_enricher,
)

from music_workflow.metadata.embedding import (
    MetadataEmbedder,
    EmbedResult,
    embed_metadata,
    get_metadata_embedder,
)

__all__ = [
    # Extraction
    "MetadataExtractor",
    "ExtractedMetadata",
    "extract_metadata",
    "get_metadata_extractor",
    # Enrichment
    "MetadataEnricher",
    "EnrichmentResult",
    "enrich_metadata",
    "get_metadata_enricher",
    # Embedding
    "MetadataEmbedder",
    "EmbedResult",
    "embed_metadata",
    "get_metadata_embedder",
]
