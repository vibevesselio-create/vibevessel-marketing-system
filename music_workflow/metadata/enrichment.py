"""
Metadata enrichment from external sources.

This module provides functions for enriching track metadata from
external services like Spotify, MusicBrainz, and other sources.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from music_workflow.utils.errors import IntegrationError
from music_workflow.config.settings import get_settings
from music_workflow.metadata.extraction import ExtractedMetadata


@dataclass
class EnrichmentResult:
    """Result of metadata enrichment."""
    success: bool = False
    source: Optional[str] = None
    confidence: float = 0.0
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_art_url: Optional[str] = None
    release_date: Optional[str] = None
    isrc: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    valence: Optional[float] = None
    genre: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    spotify_id: Optional[str] = None
    spotify_url: Optional[str] = None
    musicbrainz_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


class MetadataEnricher:
    """Enriches track metadata from external sources.

    Supports:
    - Spotify API (primary source for audio features)
    - Basic metadata matching
    """

    def __init__(self):
        self._settings = get_settings()
        self._spotify_client = None

    def _get_spotify_client(self):
        """Lazy load Spotify client."""
        if self._spotify_client is None:
            try:
                from music_workflow.integrations.spotify import get_spotify_client
                self._spotify_client = get_spotify_client()
            except Exception:
                self._spotify_client = False  # Mark as unavailable
        return self._spotify_client if self._spotify_client is not False else None

    def enrich(
        self,
        title: str,
        artist: str,
        existing_metadata: Optional[ExtractedMetadata] = None,
        sources: Optional[List[str]] = None,
    ) -> EnrichmentResult:
        """Enrich track metadata from external sources.

        Args:
            title: Track title
            artist: Artist name
            existing_metadata: Optional existing metadata to supplement
            sources: List of sources to query (default: ["spotify"])

        Returns:
            EnrichmentResult with enriched metadata
        """
        sources = sources or ["spotify"]
        result = EnrichmentResult()

        for source in sources:
            if source == "spotify":
                spotify_result = self._enrich_from_spotify(title, artist)
                if spotify_result.success:
                    return spotify_result
                result = spotify_result

        return result

    def enrich_from_spotify_id(self, spotify_id: str) -> EnrichmentResult:
        """Enrich metadata directly from a Spotify track ID.

        Args:
            spotify_id: Spotify track ID

        Returns:
            EnrichmentResult with enriched metadata
        """
        client = self._get_spotify_client()
        if not client:
            return EnrichmentResult(success=False, source="spotify")

        try:
            # Get track
            track = client.get_track(spotify_id)
            if not track:
                return EnrichmentResult(success=False, source="spotify")

            # Enrich with audio features
            track = client.enrich_track(track)

            return EnrichmentResult(
                success=True,
                source="spotify",
                confidence=1.0,
                title=track.name,
                artist=", ".join(track.artists),
                album=track.album,
                album_art_url=track.album_art_url,
                release_date=track.release_date,
                isrc=track.isrc,
                bpm=track.bpm,
                key=self._key_number_to_name(track.key) if track.key is not None else None,
                energy=track.energy,
                danceability=track.danceability,
                valence=track.valence,
                spotify_id=track.id,
                spotify_url=track.spotify_url,
            )

        except Exception as e:
            return EnrichmentResult(
                success=False,
                source="spotify",
                additional_data={"error": str(e)},
            )

    def _enrich_from_spotify(self, title: str, artist: str) -> EnrichmentResult:
        """Enrich metadata from Spotify search.

        Args:
            title: Track title
            artist: Artist name

        Returns:
            EnrichmentResult with Spotify data
        """
        client = self._get_spotify_client()
        if not client:
            return EnrichmentResult(
                success=False,
                source="spotify",
                additional_data={"error": "Spotify client not available"},
            )

        try:
            # Search for track
            tracks = client.search_track(title, artist, limit=5)
            if not tracks:
                return EnrichmentResult(
                    success=False,
                    source="spotify",
                    additional_data={"error": "No matches found"},
                )

            # Find best match
            best_match = None
            best_score = 0.0

            for track in tracks:
                score = self._calculate_match_score(
                    title, artist,
                    track.name, ", ".join(track.artists),
                )
                if score > best_score:
                    best_score = score
                    best_match = track

            if not best_match or best_score < 0.5:
                return EnrichmentResult(
                    success=False,
                    source="spotify",
                    confidence=best_score,
                    additional_data={"error": "No confident match found"},
                )

            # Enrich with audio features
            best_match = client.enrich_track(best_match)

            return EnrichmentResult(
                success=True,
                source="spotify",
                confidence=best_score,
                title=best_match.name,
                artist=", ".join(best_match.artists),
                album=best_match.album,
                album_art_url=best_match.album_art_url,
                release_date=best_match.release_date,
                isrc=best_match.isrc,
                bpm=best_match.bpm,
                key=self._key_number_to_name(best_match.key) if best_match.key is not None else None,
                energy=best_match.energy,
                danceability=best_match.danceability,
                valence=best_match.valence,
                spotify_id=best_match.id,
                spotify_url=best_match.spotify_url,
            )

        except Exception as e:
            return EnrichmentResult(
                success=False,
                source="spotify",
                additional_data={"error": str(e)},
            )

    def _calculate_match_score(
        self,
        search_title: str,
        search_artist: str,
        result_title: str,
        result_artist: str,
    ) -> float:
        """Calculate similarity score between search and result."""
        def normalize(s: str) -> str:
            return s.lower().strip()

        # Title similarity
        title_score = self._string_similarity(
            normalize(search_title),
            normalize(result_title),
        )

        # Artist similarity
        artist_score = self._string_similarity(
            normalize(search_artist),
            normalize(result_artist),
        )

        # Weighted average (title is more important)
        return (title_score * 0.6) + (artist_score * 0.4)

    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity."""
        if s1 == s2:
            return 1.0

        # Check containment
        if s1 in s2 or s2 in s1:
            return 0.9

        # Check word overlap
        words1 = set(s1.split())
        words2 = set(s2.split())
        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)
        return overlap / total if total > 0 else 0.0

    def _key_number_to_name(self, key: int) -> str:
        """Convert Spotify key number (0-11) to musical key name."""
        key_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        if 0 <= key < len(key_names):
            return key_names[key]
        return str(key)

    def merge_metadata(
        self,
        existing: ExtractedMetadata,
        enrichment: EnrichmentResult,
        overwrite: bool = False,
        djay_pro_is_source_of_truth: bool = True,
    ) -> ExtractedMetadata:
        """Merge enrichment result into existing metadata.

        Args:
            existing: Existing extracted metadata
            enrichment: Enrichment result to merge
            overwrite: Whether to overwrite existing values
            djay_pro_is_source_of_truth: If True, never overwrite bpm/key if they exist
                                          (djay Pro data takes precedence)

        Returns:
            Merged ExtractedMetadata
        """
        if not enrichment.success:
            return existing

        # Fields to potentially update
        field_mapping = {
            "title": "title",
            "artist": "artist",
            "album": "album",
            "genre": "genre",
            "bpm": "bpm",
            "key": "key",
            "isrc": "isrc",
        }

        # Fields where djay Pro is source of truth - never overwrite if they exist
        djay_pro_fields = {"bpm", "key"} if djay_pro_is_source_of_truth else set()

        for enrichment_field, metadata_field in field_mapping.items():
            enrichment_value = getattr(enrichment, enrichment_field, None)
            if enrichment_value is not None:
                existing_value = getattr(existing, metadata_field, None)
                # Skip BPM/Key if djay Pro is source of truth and value exists
                if metadata_field in djay_pro_fields and existing_value is not None:
                    continue  # djay Pro data takes precedence
                if overwrite or existing_value is None:
                    setattr(existing, metadata_field, enrichment_value)

        # Store additional enrichment data in custom_tags
        if enrichment.spotify_id:
            existing.custom_tags["spotify_id"] = enrichment.spotify_id
        if enrichment.spotify_url:
            existing.custom_tags["spotify_url"] = enrichment.spotify_url
        if enrichment.energy is not None:
            existing.custom_tags["energy"] = enrichment.energy
        if enrichment.danceability is not None:
            existing.custom_tags["danceability"] = enrichment.danceability
        if enrichment.valence is not None:
            existing.custom_tags["valence"] = enrichment.valence

        return existing


# Singleton instance
_enricher: Optional[MetadataEnricher] = None


def get_metadata_enricher() -> MetadataEnricher:
    """Get the global metadata enricher instance."""
    global _enricher
    if _enricher is None:
        _enricher = MetadataEnricher()
    return _enricher


def enrich_metadata(
    title: str,
    artist: str,
    existing_metadata: Optional[ExtractedMetadata] = None,
) -> EnrichmentResult:
    """Convenience function to enrich metadata."""
    return get_metadata_enricher().enrich(title, artist, existing_metadata)
