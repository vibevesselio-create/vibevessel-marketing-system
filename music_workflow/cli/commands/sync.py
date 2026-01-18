"""
Sync command for music workflow CLI.

Provides commands for syncing tracks with Notion database,
playlist synchronization, and cross-platform sync operations.
"""

import click
from pathlib import Path
from typing import Optional

from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions
from music_workflow.integrations.notion.client import NotionClient
from music_workflow.integrations.notion.tracks_db import TracksDatabase
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("sync-cli")


@click.command("sync")
@click.option(
    "--source",
    type=click.Choice(["notion", "spotify", "soundcloud"]),
    default="notion",
    help="Source to sync from"
)
@click.option(
    "--mode",
    type=click.Choice(["single", "batch", "all", "reprocess"]),
    default="single",
    help="Sync mode"
)
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of tracks to sync"
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for downloaded files"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output"
)
def sync(
    source: str,
    mode: str,
    limit: int,
    output_dir: Optional[str],
    dry_run: bool,
    verbose: bool,
):
    """Sync tracks from a data source.

    Connects to Notion/Spotify/SoundCloud to find and process tracks.

    Example:
        music-workflow sync --source notion --mode single
        music-workflow sync --source spotify --limit 5
    """
    if verbose:
        click.echo(f"Syncing from: {source}")
        click.echo(f"Mode: {mode}")
        click.echo(f"Limit: {limit}")

    if dry_run:
        click.echo("[DRY RUN] Would sync:")
        click.echo(f"  Source: {source}")
        click.echo(f"  Mode: {mode}")
        click.echo(f"  Limit: {limit}")
        return

    try:
        if source == "notion":
            _sync_from_notion(mode, limit, output_dir, verbose)
        elif source == "spotify":
            _sync_from_spotify(mode, limit, output_dir, verbose)
        elif source == "soundcloud":
            _sync_from_soundcloud(mode, limit, output_dir, verbose)

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()


def _sync_from_notion(mode: str, limit: int, output_dir: Optional[str], verbose: bool):
    """Sync tracks from Notion database."""
    click.echo("Connecting to Notion...")

    try:
        notion = NotionClient()
        tracks_db = TracksDatabase(notion)

        # Query for tracks based on mode
        if mode == "single":
            tracks = tracks_db.get_pending_tracks(limit=1)
        elif mode == "batch":
            tracks = tracks_db.get_pending_tracks(limit=limit)
        elif mode == "all":
            tracks = tracks_db.get_all_tracks()
        elif mode == "reprocess":
            tracks = tracks_db.get_tracks_for_reprocess()
        else:
            tracks = []

        if not tracks:
            click.echo("No tracks to sync")
            return

        click.echo(f"Found {len(tracks)} track(s) to sync")

        # Process each track
        options = WorkflowOptions(
            download_formats=["m4a", "aiff", "wav"],
            analyze_audio=True,
            organize_files=True,
        )
        workflow = MusicWorkflow(options=options)
        output_path = Path(output_dir) if output_dir else None

        for i, track in enumerate(tracks, 1):
            click.echo(f"\n[{i}/{len(tracks)}] Processing: {track.title or track.id}")

            if track.source_url:
                result = workflow.process_url(
                    track.source_url,
                    track=track,
                    output_dir=output_path
                )

                if result.success:
                    click.secho(f"  Success: {track.title}", fg="green")
                    # Update Notion with results
                    tracks_db.update_track(track)
                else:
                    click.secho(f"  Failed: {result.errors}", fg="red")
            else:
                click.secho(f"  No source URL for track", fg="yellow")

        click.secho(f"\nSync complete!", fg="green")

    except Exception as e:
        click.secho(f"Notion sync error: {e}", fg="red")
        raise


def _sync_from_spotify(mode: str, limit: int, output_dir: Optional[str], verbose: bool):
    """Sync tracks from Spotify."""
    click.echo("Connecting to Spotify...")

    try:
        from music_workflow.integrations.spotify.client import SpotifyClient

        spotify = SpotifyClient()

        if mode == "single":
            # Get currently playing track
            current = spotify.get_current_track()
            if current:
                click.echo(f"Currently playing: {current.title} by {current.artist}")
                # Process through workflow
                options = WorkflowOptions(
                    download_formats=["m4a", "aiff", "wav"],
                    analyze_audio=True,
                )
                workflow = MusicWorkflow(options=options)

                # Search YouTube for the track
                if current.source_url:
                    output_path = Path(output_dir) if output_dir else None
                    result = workflow.process_url(
                        current.source_url,
                        track=current,
                        output_dir=output_path
                    )

                    if result.success:
                        click.secho("Track downloaded successfully!", fg="green")
                    else:
                        click.secho(f"Download failed: {result.errors}", fg="red")
            else:
                click.echo("No track currently playing")
        else:
            click.echo(f"Spotify sync mode '{mode}' not yet implemented")

    except Exception as e:
        click.secho(f"Spotify sync error: {e}", fg="red")
        raise


def _sync_from_soundcloud(mode: str, limit: int, output_dir: Optional[str], verbose: bool):
    """Sync tracks from SoundCloud."""
    click.echo("Connecting to SoundCloud...")

    try:
        from music_workflow.integrations.soundcloud.client import SoundCloudClient

        sc = SoundCloudClient()

        if mode == "single":
            # Get recent likes
            likes = sc.get_likes(limit=1)
            if likes:
                track = likes[0]
                click.echo(f"Processing: {track.title} by {track.artist}")

                options = WorkflowOptions(
                    download_formats=["m4a", "aiff", "wav"],
                    analyze_audio=True,
                )
                workflow = MusicWorkflow(options=options)
                output_path = Path(output_dir) if output_dir else None

                result = workflow.process_url(
                    track.source_url,
                    track=track,
                    output_dir=output_path
                )

                if result.success:
                    click.secho("Track downloaded successfully!", fg="green")
                else:
                    click.secho(f"Download failed: {result.errors}", fg="red")
            else:
                click.echo("No recent likes found")
        else:
            click.echo(f"SoundCloud sync mode '{mode}' not yet implemented")

    except Exception as e:
        click.secho(f"SoundCloud sync error: {e}", fg="red")
        raise


@click.command("sync-playlist")
@click.argument("playlist_url")
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory"
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum tracks to sync"
)
@click.option(
    "--skip-existing",
    is_flag=True,
    default=True,
    help="Skip tracks already in Notion"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output"
)
def sync_playlist(
    playlist_url: str,
    output_dir: Optional[str],
    limit: int,
    skip_existing: bool,
    verbose: bool,
):
    """Sync an entire playlist.

    Supports SoundCloud and Spotify playlists.

    Example:
        music-workflow sync-playlist https://soundcloud.com/user/sets/playlist
    """
    click.echo(f"Syncing playlist: {playlist_url}")
    click.echo(f"Limit: {limit}")

    try:
        if "soundcloud" in playlist_url.lower():
            from music_workflow.integrations.soundcloud.client import SoundCloudClient
            sc = SoundCloudClient()
            tracks = sc.get_playlist_tracks(playlist_url, limit=limit)
        elif "spotify" in playlist_url.lower():
            from music_workflow.integrations.spotify.client import SpotifyClient
            spotify = SpotifyClient()
            tracks = spotify.get_playlist_tracks(playlist_url, limit=limit)
        else:
            click.secho("Unsupported playlist URL", fg="red")
            return

        click.echo(f"Found {len(tracks)} tracks")

        options = WorkflowOptions(
            download_formats=["m4a", "aiff", "wav"],
            analyze_audio=True,
            organize_files=True,
        )
        workflow = MusicWorkflow(options=options)
        output_path = Path(output_dir) if output_dir else None

        successful = 0
        failed = 0

        for i, track in enumerate(tracks, 1):
            click.echo(f"\n[{i}/{len(tracks)}] {track.title}")

            result = workflow.process_url(
                track.source_url,
                track=track,
                output_dir=output_path
            )

            if result.success:
                successful += 1
                if verbose:
                    click.secho(f"  Success", fg="green")
            else:
                failed += 1
                if verbose:
                    click.secho(f"  Failed: {result.errors}", fg="red")

        click.echo(f"\nPlaylist sync complete: {successful} successful, {failed} failed")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()
