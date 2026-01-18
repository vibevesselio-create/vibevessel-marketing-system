#!/usr/bin/env python3
"""
Sync djay Pro Library Data to Notion Music Tracks Database.

This script synchronizes metadata from djay Pro exports to the Notion Music Tracks
database, including:
- BPM values
- Key and Camelot notation
- Beatport URLs
- SoundCloud URLs
- DJ activity data (play counts, session counts)
- djay Pro IDs

Usage:
    python scripts/sync_djay_pro_to_notion.py [--dry-run] [--limit N]

Version: 1.0
Date: 2026-01-16
"""

from __future__ import annotations

import os
import sys
import csv
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import Counter
from difflib import SequenceMatcher

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared_core.notion import get_notion_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("djay-notion-sync")

# Constants
TRACKS_DB_ID = os.environ.get("TRACKS_DB_ID", "27ce7361-6c27-80fb-b40e-fefdd47d6640")
EXPORT_DIR = Path(os.environ.get("DJAY_EXPORT_DIR", "djay_pro_export"))


@dataclass
class DjayTrack:
    """Represents a track from djay Pro export."""
    track_id: str
    title: str = ""
    artist: str = ""
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    source_type: str = "local"
    source_id: Optional[str] = None
    file_path: Optional[str] = None


@dataclass
class StreamingTrack:
    """Represents a streaming track from djay Pro export."""
    track_id: str
    source_type: str
    source_track_id: str
    source_url: Optional[str] = None
    title: str = ""
    artist: str = ""


@dataclass
class TrackActivity:
    """DJ activity data for a track."""
    track_id: str
    total_plays: int = 0
    session_count: int = 0
    last_played: Optional[datetime] = None
    title: str = ""
    artist: str = ""


@dataclass
class SyncResult:
    """Results from a sync operation."""
    total_processed: int = 0
    matches_found: int = 0
    updates_made: int = 0
    skipped: int = 0
    errors: int = 0
    details: List[str] = field(default_factory=list)


class DjayProNotionSync:
    """Synchronize djay Pro data to Notion Music Tracks database."""

    def __init__(self, dry_run: bool = False, limit: Optional[int] = None):
        self.client = get_notion_client()
        self.dry_run = dry_run
        self.limit = limit
        self.tracks: Dict[str, DjayTrack] = {}
        self.streaming: Dict[str, StreamingTrack] = {}
        self.activity: Dict[str, TrackActivity] = {}
        self._notion_cache: Dict[str, dict] = {}

    def load_exports(self) -> None:
        """Load all djay Pro export CSV files."""
        logger.info(f"Loading djay Pro exports from {EXPORT_DIR}")

        # Find latest export files
        tracks_file = self._find_latest_file("djay_library_tracks_*.csv")
        streaming_file = self._find_latest_file("djay_library_streaming_*.csv")
        session_tracks_file = self._find_latest_file("djay_session_tracks_*.csv")

        if tracks_file:
            self._load_tracks(tracks_file)
        if streaming_file:
            self._load_streaming(streaming_file)
        if session_tracks_file:
            self._load_activity(session_tracks_file)

        logger.info(f"Loaded: {len(self.tracks)} tracks, {len(self.streaming)} streaming, {len(self.activity)} with activity")

    def _find_latest_file(self, pattern: str) -> Optional[Path]:
        """Find the most recent file matching pattern."""
        files = sorted(EXPORT_DIR.glob(pattern))
        return files[-1] if files else None

    def _load_tracks(self, file_path: Path) -> None:
        """Load tracks from CSV."""
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                track_id = row.get('track_id', '')
                if not track_id:
                    continue

                bpm = None
                if row.get('bpm') and row['bpm'] not in ('', '0.0', '0'):
                    try:
                        bpm = float(row['bpm'])
                    except ValueError:
                        pass

                self.tracks[track_id] = DjayTrack(
                    track_id=track_id,
                    title=row.get('title', ''),
                    artist=row.get('artist', ''),
                    bpm=bpm,
                    key=row.get('key') or None,
                    key_camelot=row.get('key_camelot') or None,
                    source_type=row.get('source_type', 'local'),
                    source_id=row.get('source_id') or None,
                    file_path=row.get('file_path') or None,
                )

    def _load_streaming(self, file_path: Path) -> None:
        """Load streaming tracks from CSV."""
        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                track_id = row.get('track_id', '')
                if not track_id:
                    continue

                self.streaming[track_id] = StreamingTrack(
                    track_id=track_id,
                    source_type=row.get('source_type', ''),
                    source_track_id=row.get('source_track_id', ''),
                    source_url=row.get('source_url') or None,
                    title=row.get('title', ''),
                    artist=row.get('artist', ''),
                )

    def _load_activity(self, file_path: Path) -> None:
        """Load and aggregate activity from session tracks."""
        play_counts: Counter = Counter()
        session_sets: Dict[str, set] = {}
        last_played: Dict[str, datetime] = {}
        track_info: Dict[str, Tuple[str, str]] = {}

        with open(file_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                track_id = row.get('track_id', '')
                session_id = row.get('session_id', '')
                if not track_id:
                    continue

                play_counts[track_id] += 1

                if track_id not in session_sets:
                    session_sets[track_id] = set()
                if session_id:
                    session_sets[track_id].add(session_id)

                # Store title/artist from session track
                if track_id not in track_info:
                    track_info[track_id] = (
                        row.get('title', ''),
                        row.get('artist', '')
                    )

        for track_id, plays in play_counts.items():
            title, artist = track_info.get(track_id, ('', ''))
            self.activity[track_id] = TrackActivity(
                track_id=track_id,
                total_plays=plays,
                session_count=len(session_sets.get(track_id, set())),
                title=title,
                artist=artist,
            )

    def sync_all(self) -> Dict[str, SyncResult]:
        """Run all sync operations."""
        results = {}

        logger.info("=" * 60)
        logger.info("DJAY PRO → NOTION SYNC")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

        # Load exports
        self.load_exports()

        # Run sync operations
        results['bpm'] = self.sync_bpm()
        results['key'] = self.sync_key()
        results['beatport'] = self.sync_beatport_urls()
        results['soundcloud'] = self.sync_soundcloud_urls()
        results['activity'] = self.sync_activity()
        results['djay_id'] = self.sync_djay_ids()

        # Print summary
        self._print_summary(results)

        return results

    def sync_bpm(self) -> SyncResult:
        """Sync BPM values from djay Pro to Notion."""
        logger.info("\n--- Syncing BPM ---")
        result = SyncResult()

        tracks_with_bpm = [t for t in self.tracks.values() if t.bpm and t.bpm > 0]
        logger.info(f"djay Pro tracks with BPM: {len(tracks_with_bpm)}")

        if self.limit:
            tracks_with_bpm = tracks_with_bpm[:self.limit]

        for track in tracks_with_bpm:
            result.total_processed += 1
            match = self._find_notion_match(track)

            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']
            props = match['properties']

            # Check if BPM already set
            current_bpm = props.get('Tempo', {}).get('number')
            if current_bpm and current_bpm > 0:
                result.skipped += 1
                continue

            # Update BPM
            if not self.dry_run:
                try:
                    self.client.pages.update(
                        page_id=page_id,
                        properties={
                            "Tempo": {"number": track.bpm},
                        }
                    )
                    result.updates_made += 1
                    result.details.append(f"BPM {track.bpm} → {track.title[:30]}")
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating BPM for {track.title}: {e}")
            else:
                result.updates_made += 1

        logger.info(f"BPM sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def sync_key(self) -> SyncResult:
        """Sync Key and Camelot notation from djay Pro to Notion."""
        logger.info("\n--- Syncing Key + Camelot ---")
        result = SyncResult()

        tracks_with_key = [t for t in self.tracks.values() if t.key]
        logger.info(f"djay Pro tracks with Key: {len(tracks_with_key)}")

        if self.limit:
            tracks_with_key = tracks_with_key[:self.limit]

        for track in tracks_with_key:
            result.total_processed += 1
            match = self._find_notion_match(track)

            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']
            props = match['properties']

            # Check if Key already set
            key_texts = props.get('Key ', {}).get('rich_text', [])
            current_key = key_texts[0].get('text', {}).get('content', '') if key_texts else ''
            if current_key:
                result.skipped += 1
                continue

            # Prepare key value with Camelot
            key_value = track.key
            if track.key_camelot:
                key_value = f"{track.key} ({track.key_camelot})"

            # Update Key
            if not self.dry_run:
                try:
                    self.client.pages.update(
                        page_id=page_id,
                        properties={
                            "Key ": {"rich_text": [{"text": {"content": key_value}}]},
                        }
                    )
                    result.updates_made += 1
                    result.details.append(f"Key {key_value} → {track.title[:30]}")
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating Key for {track.title}: {e}")
            else:
                result.updates_made += 1

        logger.info(f"Key sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def sync_beatport_urls(self) -> SyncResult:
        """Sync Beatport URLs from djay Pro streaming tracks to Notion."""
        logger.info("\n--- Syncing Beatport URLs ---")
        result = SyncResult()

        beatport_tracks = [s for s in self.streaming.values() if s.source_type == 'beatport' and s.source_url]
        logger.info(f"djay Pro Beatport tracks: {len(beatport_tracks)}")

        if self.limit:
            beatport_tracks = beatport_tracks[:self.limit]

        for streaming in beatport_tracks:
            result.total_processed += 1

            # Get the corresponding track
            track = self.tracks.get(streaming.track_id)
            if not track:
                result.skipped += 1
                continue

            match = self._find_notion_match(track)
            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']
            props = match['properties']

            # Check if Beatport URL already set
            current_url = props.get('Beatport URL', {}).get('url')
            if current_url:
                result.skipped += 1
                continue

            # Update Beatport URL
            if not self.dry_run:
                try:
                    self.client.pages.update(
                        page_id=page_id,
                        properties={
                            "Beatport URL": {"url": streaming.source_url},
                        }
                    )
                    result.updates_made += 1
                    result.details.append(f"Beatport → {track.title[:30]}")
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating Beatport URL for {track.title}: {e}")
            else:
                result.updates_made += 1

        logger.info(f"Beatport sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def sync_soundcloud_urls(self) -> SyncResult:
        """Sync SoundCloud URLs from djay Pro streaming tracks to Notion."""
        logger.info("\n--- Syncing SoundCloud URLs ---")
        result = SyncResult()

        soundcloud_tracks = [s for s in self.streaming.values() if s.source_type == 'soundcloud' and s.source_url]
        logger.info(f"djay Pro SoundCloud tracks: {len(soundcloud_tracks)}")

        if self.limit:
            soundcloud_tracks = soundcloud_tracks[:self.limit]

        for streaming in soundcloud_tracks:
            result.total_processed += 1

            track = self.tracks.get(streaming.track_id)
            if not track:
                result.skipped += 1
                continue

            match = self._find_notion_match(track)
            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']
            props = match['properties']

            # Check if SoundCloud URL already set
            current_url = props.get('SoundCloud URL', {}).get('url')
            if current_url:
                result.skipped += 1
                continue

            # Update SoundCloud URL
            if not self.dry_run:
                try:
                    self.client.pages.update(
                        page_id=page_id,
                        properties={
                            "SoundCloud URL": {"url": streaming.source_url},
                        }
                    )
                    result.updates_made += 1
                    result.details.append(f"SoundCloud → {track.title[:30]}")
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating SoundCloud URL for {track.title}: {e}")
            else:
                result.updates_made += 1

        logger.info(f"SoundCloud sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def sync_activity(self) -> SyncResult:
        """Sync DJ activity data (play counts, session counts) to Notion."""
        logger.info("\n--- Syncing DJ Activity ---")
        result = SyncResult()

        activity_tracks = [a for a in self.activity.values() if a.total_plays > 0]
        logger.info(f"Tracks with DJ activity: {len(activity_tracks)}")

        if self.limit:
            activity_tracks = activity_tracks[:self.limit]

        for activity in activity_tracks:
            result.total_processed += 1

            # Try to find track in tracks dict or match by title/artist
            track = self.tracks.get(activity.track_id)
            if track:
                match = self._find_notion_match(track)
            else:
                # Fallback: try to match by title/artist from activity
                match = self._find_notion_match_by_metadata(activity.title, activity.artist)

            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']

            # Update activity fields
            if not self.dry_run:
                try:
                    update_props = {
                        "Play Count (DJ)": {"number": activity.total_plays},
                        "Session Count": {"number": activity.session_count},
                    }

                    # Add djay Pro ID if we have it
                    if activity.track_id:
                        update_props["djay Pro ID"] = {"rich_text": [{"text": {"content": activity.track_id}}]}

                    self.client.pages.update(page_id=page_id, properties=update_props)
                    result.updates_made += 1
                    title = track.title if track else activity.title
                    result.details.append(f"Activity ({activity.total_plays} plays) → {title[:30]}")
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating activity: {e}")
            else:
                result.updates_made += 1

        logger.info(f"Activity sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def sync_djay_ids(self) -> SyncResult:
        """Sync djay Pro IDs to Notion tracks (for tracks not covered by activity sync)."""
        logger.info("\n--- Syncing djay Pro IDs ---")
        result = SyncResult()

        # Process tracks that weren't covered by activity sync
        tracks_without_activity = [t for t in self.tracks.values() if t.track_id not in self.activity]
        logger.info(f"Tracks without activity (need ID sync): {len(tracks_without_activity)}")

        if self.limit:
            tracks_without_activity = tracks_without_activity[:self.limit]

        for track in tracks_without_activity:
            result.total_processed += 1
            match = self._find_notion_match(track)

            if not match:
                result.skipped += 1
                continue

            result.matches_found += 1
            page_id = match['id']
            props = match['properties']

            # Check if djay Pro ID already set
            djay_texts = props.get('djay Pro ID', {}).get('rich_text', [])
            current_id = djay_texts[0].get('text', {}).get('content', '') if djay_texts else ''
            if current_id:
                result.skipped += 1
                continue

            # Update djay Pro ID
            if not self.dry_run:
                try:
                    self.client.pages.update(
                        page_id=page_id,
                        properties={
                            "djay Pro ID": {"rich_text": [{"text": {"content": track.track_id}}]},
                        }
                    )
                    result.updates_made += 1
                except Exception as e:
                    result.errors += 1
                    logger.error(f"Error updating djay Pro ID for {track.title}: {e}")
            else:
                result.updates_made += 1

        logger.info(f"djay ID sync: {result.updates_made} updates, {result.skipped} skipped, {result.errors} errors")
        return result

    def _find_notion_match(self, track: DjayTrack) -> Optional[dict]:
        """Find matching Notion page for a djay Pro track."""
        # Try cache first
        cache_key = track.track_id
        if cache_key in self._notion_cache:
            return self._notion_cache[cache_key]

        # Try by djay Pro ID
        if track.track_id:
            pages = self._query_by_rich_text("djay Pro ID", track.track_id)
            if pages:
                self._notion_cache[cache_key] = pages[0]
                return pages[0]

        # Try by file path (for local tracks)
        if track.file_path and track.source_type == 'local':
            # Try matching by filename in various file path fields
            filename = Path(track.file_path).stem
            pages = self._query_by_title_contains(filename[:40])
            if pages:
                # Verify match by similarity
                for page in pages:
                    if self._is_good_match(track, page):
                        self._notion_cache[cache_key] = page
                        return page

        # Try by title + artist fuzzy match
        return self._find_notion_match_by_metadata(track.title, track.artist)

    def _find_notion_match_by_metadata(self, title: str, artist: str) -> Optional[dict]:
        """Find Notion match by title and artist."""
        if not title:
            return None

        pages = self._query_by_title_contains(title[:40])
        best_match = None
        best_score = 0.0

        for page in pages:
            score = self._calculate_similarity(title, artist, page)
            if score > best_score and score >= 0.7:
                best_score = score
                best_match = page

        return best_match

    def _query_by_rich_text(self, prop: str, value: str) -> List[dict]:
        """Query Notion by rich text property."""
        try:
            return self.client.databases.query(
                database_id=TRACKS_DB_ID,
                filter={"property": prop, "rich_text": {"equals": value}},
                page_size=5
            )['results']
        except Exception:
            return []

    def _query_by_title_contains(self, value: str) -> List[dict]:
        """Query Notion by title contains."""
        try:
            return self.client.databases.query(
                database_id=TRACKS_DB_ID,
                filter={"property": "Title", "title": {"contains": value}},
                page_size=20
            )['results']
        except Exception:
            return []

    def _is_good_match(self, track: DjayTrack, page: dict) -> bool:
        """Check if page is a good match for track."""
        score = self._calculate_similarity(track.title, track.artist, page)
        return score >= 0.7

    def _calculate_similarity(self, title: str, artist: str, page: dict) -> float:
        """Calculate similarity score between djay track and Notion page."""
        props = page.get('properties', {})

        # Get Notion title
        title_prop = props.get('Title', {}).get('title', [])
        notion_title = title_prop[0].get('text', {}).get('content', '') if title_prop else ''

        # Get Notion artist
        artist_prop = props.get('Artist Name', {}).get('rich_text', [])
        notion_artist = artist_prop[0].get('text', {}).get('content', '') if artist_prop else ''

        # Calculate similarity
        title_sim = self._string_similarity(title, notion_title)
        artist_sim = self._string_similarity(artist, notion_artist) if artist and notion_artist else 0.5

        return (title_sim * 0.6) + (artist_sim * 0.4)

    def _string_similarity(self, a: str, b: str) -> float:
        """Calculate string similarity."""
        if not a or not b:
            return 0.0
        a_norm = ''.join(c for c in a.lower() if c.isalnum() or c.isspace()).strip()
        b_norm = ''.join(c for c in b.lower() if c.isalnum() or c.isspace()).strip()
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    def _print_summary(self, results: Dict[str, SyncResult]) -> None:
        """Print sync summary."""
        logger.info("\n" + "=" * 60)
        logger.info("SYNC SUMMARY")
        logger.info("=" * 60)

        total_updates = 0
        total_errors = 0

        for name, result in results.items():
            logger.info(f"\n{name.upper()}:")
            logger.info(f"  Processed: {result.total_processed}")
            logger.info(f"  Matches:   {result.matches_found}")
            logger.info(f"  Updates:   {result.updates_made}")
            logger.info(f"  Skipped:   {result.skipped}")
            logger.info(f"  Errors:    {result.errors}")
            total_updates += result.updates_made
            total_errors += result.errors

        logger.info("\n" + "-" * 60)
        logger.info(f"TOTAL UPDATES: {total_updates}")
        logger.info(f"TOTAL ERRORS:  {total_errors}")
        if self.dry_run:
            logger.info("(DRY RUN - No actual changes made)")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Sync djay Pro data to Notion")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without making them")
    parser.add_argument("--limit", type=int, help="Limit number of tracks to process per category")
    args = parser.parse_args()

    sync = DjayProNotionSync(dry_run=args.dry_run, limit=args.limit)
    sync.sync_all()


if __name__ == "__main__":
    main()
