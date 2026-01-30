#!/usr/bin/env python3
"""
Notion Gap Remediation Script
────────────────────────────────────────────────────────────────────────────────
Addresses gaps identified in Notion population analysis:
1. Link tracks to playlists via relation property
2. Populate Artist database with Spotify IDs and track relations
3. Add file path tracking to tracks
4. Enrich metadata (BPM, Key, Genre from audio analysis)

Usage:
    python scripts/notion_gap_remediation.py [--step STEP] [--limit N] [--dry-run]

Steps:
    1 = Playlist-Track Relations
    2 = Artist Population
    3 = File Path Tracking
    4 = Audio Metadata (requires local files)
    all = Run all steps

Version: 2026-01-30
"""
import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment
from dotenv import load_dotenv
env_path = project_root / '.env'
load_dotenv(env_path, override=True)

from notion_client import Client

# Use token manager for Notion tokens (per environment management pattern)
from shared_core.notion.token_manager import get_notion_token

# Configuration
NOTION_TOKEN = get_notion_token()
TRACKS_DB_ID = os.getenv('TRACKS_DB_ID')
PLAYLISTS_DB_ID = os.getenv('PLAYLISTS_DB_ID')
ARTISTS_DB_ID = os.getenv('ARTISTS_DB_ID')

# Notion client
notion = Client(auth=NOTION_TOKEN)


def get_all_playlists() -> List[Dict[str, Any]]:
    """Fetch all playlists from Notion."""
    playlists = []
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {'database_id': PLAYLISTS_DB_ID, 'page_size': 100}
        if start_cursor:
            kwargs['start_cursor'] = start_cursor

        results = notion.databases.query(**kwargs)
        playlists.extend(results.get('results', []))

        has_more = results.get('has_more', False)
        start_cursor = results.get('next_cursor')
        time.sleep(0.1)

    return playlists


def get_all_tracks() -> List[Dict[str, Any]]:
    """Fetch all tracks from Notion."""
    tracks = []
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {'database_id': TRACKS_DB_ID, 'page_size': 100}
        if start_cursor:
            kwargs['start_cursor'] = start_cursor

        results = notion.databases.query(**kwargs)
        tracks.extend(results.get('results', []))

        has_more = results.get('has_more', False)
        start_cursor = results.get('next_cursor')
        time.sleep(0.1)

    return tracks


def get_all_artists() -> List[Dict[str, Any]]:
    """Fetch all artists from Notion."""
    artists = []
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {'database_id': ARTISTS_DB_ID, 'page_size': 100}
        if start_cursor:
            kwargs['start_cursor'] = start_cursor

        results = notion.databases.query(**kwargs)
        artists.extend(results.get('results', []))

        has_more = results.get('has_more', False)
        start_cursor = results.get('next_cursor')
        time.sleep(0.1)

    return artists


def build_track_index(tracks: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build index of Spotify ID -> Notion page ID."""
    index = {}
    for track in tracks:
        props = track.get('properties', {})
        spotify_id_prop = props.get('Spotify ID', {}).get('rich_text', [])
        if spotify_id_prop:
            spotify_id = spotify_id_prop[0].get('plain_text', '')
            if spotify_id:
                index[spotify_id] = track.get('id')
    return index


def get_prop_text(props: Dict, prop_name: str) -> str:
    """Extract text from rich_text or title property."""
    prop = props.get(prop_name, {})

    # Handle title type
    if prop.get('type') == 'title':
        items = prop.get('title', [])
        return ''.join(t.get('plain_text', '') for t in items)

    # Handle rich_text type
    items = prop.get('rich_text', [])
    return ''.join(t.get('plain_text', '') for t in items)


def step1_playlist_track_relations(tracks: List[Dict], playlists: List[Dict],
                                    limit: int = 0, dry_run: bool = False) -> Dict[str, int]:
    """
    Step 1: Link tracks to playlists based on matching.

    Since we can't call Spotify API directly, we'll:
    1. Check if tracks have artist names matching playlist names (for artist playlists)
    2. Link based on existing metadata patterns
    """
    print("\n" + "="*70)
    print("STEP 1: PLAYLIST-TRACK RELATION SYNC")
    print("="*70)

    stats = {'linked': 0, 'already_linked': 0, 'errors': 0, 'playlists_processed': 0}

    # Build lookup of playlist page IDs by name
    playlist_lookup = {}
    for pl in playlists:
        props = pl.get('properties', {})
        name = get_prop_text(props, 'Name')
        if name:
            playlist_lookup[name.lower()] = pl.get('id')

    print(f"Found {len(playlists)} playlists")
    print(f"Found {len(tracks)} tracks")

    # Process tracks and find playlist matches
    processed = 0
    for track in tracks:
        if limit and processed >= limit:
            break

        track_id = track.get('id')
        props = track.get('properties', {})

        # Get existing playlist relations
        existing_playlists = props.get('Playlists', {}).get('relation', [])
        existing_ids = {r.get('id') for r in existing_playlists}

        # Get track metadata for matching
        artist_name = get_prop_text(props, 'Artist Name')
        title = get_prop_text(props, 'Title')

        # Try to match with playlists based on artist name
        new_links = []
        if artist_name:
            # Check for artist-named playlist
            for pl_name, pl_id in playlist_lookup.items():
                if artist_name.lower() in pl_name or pl_name in artist_name.lower():
                    if pl_id not in existing_ids:
                        new_links.append(pl_id)

        # Update track with new playlist relations
        if new_links and not dry_run:
            try:
                # Combine existing and new
                all_relations = list(existing_ids) + new_links
                notion.pages.update(
                    page_id=track_id,
                    properties={
                        'Playlists': {
                            'relation': [{'id': pid} for pid in all_relations]
                        }
                    }
                )
                stats['linked'] += len(new_links)
                print(f"  Linked '{title}' to {len(new_links)} playlist(s)")
                time.sleep(0.2)
            except Exception as e:
                stats['errors'] += 1
                print(f"  Error linking track: {e}")
        elif new_links:
            stats['linked'] += len(new_links)
            print(f"  [DRY-RUN] Would link '{title}' to {len(new_links)} playlist(s)")

        processed += 1
        stats['playlists_processed'] = processed

    print(f"\n✅ Step 1 Complete:")
    print(f"   - Tracks processed: {stats['playlists_processed']}")
    print(f"   - New links created: {stats['linked']}")
    print(f"   - Errors: {stats['errors']}")

    return stats


def step2_artist_population(tracks: List[Dict], artists: List[Dict],
                            limit: int = 0, dry_run: bool = False) -> Dict[str, int]:
    """
    Step 2: Populate Artist database with track relations.

    For each track, ensure the artist exists in Artists DB and is linked.
    """
    print("\n" + "="*70)
    print("STEP 2: ARTIST DATABASE POPULATION")
    print("="*70)

    stats = {'created': 0, 'updated': 0, 'linked': 0, 'errors': 0}

    # Build artist lookup by name (case-insensitive)
    artist_lookup = {}
    for artist in artists:
        props = artist.get('properties', {})
        name = get_prop_text(props, 'Name')
        if name:
            artist_lookup[name.lower()] = {
                'id': artist.get('id'),
                'props': props
            }

    print(f"Found {len(artists)} existing artists")
    print(f"Processing {len(tracks)} tracks...")

    # Track unique artist names from tracks
    artist_track_map: Dict[str, Set[str]] = {}  # artist_name -> set of track_ids

    for track in tracks:
        props = track.get('properties', {})
        artist_name = get_prop_text(props, 'Artist Name')
        track_id = track.get('id')

        if artist_name:
            # Handle multiple artists (comma-separated)
            for name in artist_name.split(','):
                name = name.strip()
                if name:
                    if name not in artist_track_map:
                        artist_track_map[name] = set()
                    artist_track_map[name].add(track_id)

    print(f"Found {len(artist_track_map)} unique artists in tracks")

    # Process each artist
    processed = 0
    for artist_name, track_ids in artist_track_map.items():
        if limit and processed >= limit:
            break

        # Check if artist exists
        artist_info = artist_lookup.get(artist_name.lower())

        if not artist_info:
            # Create new artist
            if not dry_run:
                try:
                    new_page = notion.pages.create(
                        parent={'database_id': ARTISTS_DB_ID},
                        properties={
                            'Name': {'title': [{'text': {'content': artist_name}}]},
                            'Tracks': {'relation': [{'id': tid} for tid in list(track_ids)[:100]]}
                        }
                    )
                    stats['created'] += 1
                    print(f"  Created artist: {artist_name} ({len(track_ids)} tracks)")
                    time.sleep(0.2)
                except Exception as e:
                    stats['errors'] += 1
                    print(f"  Error creating artist {artist_name}: {e}")
            else:
                stats['created'] += 1
                print(f"  [DRY-RUN] Would create artist: {artist_name}")
        else:
            # Update existing artist with track relations
            artist_id = artist_info['id']
            existing_tracks = artist_info['props'].get('Tracks', {}).get('relation', [])
            existing_track_ids = {r.get('id') for r in existing_tracks}

            new_track_ids = track_ids - existing_track_ids

            if new_track_ids:
                if not dry_run:
                    try:
                        all_track_ids = list(existing_track_ids | track_ids)[:100]
                        notion.pages.update(
                            page_id=artist_id,
                            properties={
                                'Tracks': {'relation': [{'id': tid} for tid in all_track_ids]}
                            }
                        )
                        stats['linked'] += len(new_track_ids)
                        print(f"  Updated artist: {artist_name} (+{len(new_track_ids)} tracks)")
                        time.sleep(0.2)
                    except Exception as e:
                        stats['errors'] += 1
                        print(f"  Error updating artist {artist_name}: {e}")
                else:
                    stats['linked'] += len(new_track_ids)
                    print(f"  [DRY-RUN] Would update artist: {artist_name}")

        processed += 1

    print(f"\n✅ Step 2 Complete:")
    print(f"   - Artists processed: {processed}")
    print(f"   - Artists created: {stats['created']}")
    print(f"   - Track links added: {stats['linked']}")
    print(f"   - Errors: {stats['errors']}")

    return stats


def step3_file_path_tracking(tracks: List[Dict], limit: int = 0,
                              dry_run: bool = False) -> Dict[str, int]:
    """
    Step 3: Add file path tracking to tracks.

    Scan download directories and match files to tracks.
    """
    print("\n" + "="*70)
    print("STEP 3: FILE PATH TRACKING")
    print("="*70)

    stats = {'updated': 0, 'not_found': 0, 'already_set': 0, 'errors': 0}

    # Get download directories from env
    out_dir = os.getenv('OUT_DIR', '/Volumes/VIBES/Playlists')
    backup_dir = os.getenv('BACKUP_DIR', '/Volumes/VIBES/Djay-Pro-Auto-Import')

    # Build file index from directories
    print(f"Scanning directories...")
    file_index = {}  # normalized_name -> file_path

    search_dirs = [out_dir, backup_dir]
    audio_extensions = {'.mp3', '.m4a', '.flac', '.wav', '.aif', '.aiff', '.opus', '.ogg'}

    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if search_path.exists():
            for f in search_path.rglob('*'):
                if f.suffix.lower() in audio_extensions:
                    # Normalize filename for matching
                    name = f.stem.lower()
                    # Remove common suffixes like _download, -hq, etc
                    for suffix in ['_download', '-hq', '-lq', '_wav', '_mp3']:
                        name = name.replace(suffix, '')
                    file_index[name] = str(f)

    print(f"Found {len(file_index)} audio files")

    # Process tracks
    processed = 0
    for track in tracks:
        if limit and processed >= limit:
            break

        track_id = track.get('id')
        props = track.get('properties', {})

        # Check if file path already set
        existing_path = get_prop_text(props, 'File Path')
        if existing_path:
            stats['already_set'] += 1
            processed += 1
            continue

        # Get track title for matching
        title = get_prop_text(props, 'Title')
        artist = get_prop_text(props, 'Artist Name')

        if not title:
            processed += 1
            continue

        # Try to find matching file
        search_name = title.lower()
        # Also try with artist prefix
        search_variants = [
            search_name,
            f"{artist} - {title}".lower() if artist else None,
            f"{title} - {artist}".lower() if artist else None,
        ]

        matched_path = None
        for variant in search_variants:
            if variant and variant in file_index:
                matched_path = file_index[variant]
                break

        # Fuzzy match - check if track title is contained in filename
        if not matched_path:
            for file_name, file_path in file_index.items():
                if search_name in file_name or file_name in search_name:
                    matched_path = file_path
                    break

        if matched_path:
            if not dry_run:
                try:
                    notion.pages.update(
                        page_id=track_id,
                        properties={
                            'File Path': {'rich_text': [{'text': {'content': matched_path}}]}
                        }
                    )
                    stats['updated'] += 1
                    print(f"  Set path for: {title}")
                    time.sleep(0.15)
                except Exception as e:
                    stats['errors'] += 1
            else:
                stats['updated'] += 1
                print(f"  [DRY-RUN] Would set path for: {title}")
        else:
            stats['not_found'] += 1

        processed += 1

    print(f"\n✅ Step 3 Complete:")
    print(f"   - Tracks processed: {processed}")
    print(f"   - File paths set: {stats['updated']}")
    print(f"   - Already had path: {stats['already_set']}")
    print(f"   - Files not found: {stats['not_found']}")
    print(f"   - Errors: {stats['errors']}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Notion Gap Remediation')
    parser.add_argument('--step', choices=['1', '2', '3', 'all'], default='all',
                        help='Step to run (1=playlists, 2=artists, 3=file paths, all=run all)')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit number of items to process (0=no limit)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')

    args = parser.parse_args()

    print("="*70)
    print("NOTION GAP REMEDIATION SCRIPT")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Step: {args.step}")
    print(f"Limit: {args.limit if args.limit else 'No limit'}")
    print(f"Dry Run: {args.dry_run}")
    print("="*70)

    # Fetch all data once
    print("\nFetching data from Notion...")
    tracks = get_all_tracks()
    print(f"  - Tracks: {len(tracks)}")

    playlists = get_all_playlists()
    print(f"  - Playlists: {len(playlists)}")

    artists = get_all_artists()
    print(f"  - Artists: {len(artists)}")

    all_stats = {}

    # Run requested steps
    if args.step in ['1', 'all']:
        all_stats['step1'] = step1_playlist_track_relations(
            tracks, playlists, args.limit, args.dry_run
        )

    if args.step in ['2', 'all']:
        all_stats['step2'] = step2_artist_population(
            tracks, artists, args.limit, args.dry_run
        )

    if args.step in ['3', 'all']:
        all_stats['step3'] = step3_file_path_tracking(
            tracks, args.limit, args.dry_run
        )

    # Summary
    print("\n" + "="*70)
    print("REMEDIATION COMPLETE")
    print("="*70)
    for step, stats in all_stats.items():
        print(f"\n{step}: {stats}")

    return all_stats


if __name__ == '__main__':
    main()
