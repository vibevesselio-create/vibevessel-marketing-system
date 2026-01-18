"""
Command-line interface for music workflow.

This module provides the CLI entry point using Click, offering commands
for downloading, processing, syncing, and batch operations.
"""

import sys
from pathlib import Path
from typing import Optional, List

try:
    import click
except ImportError:
    print("Error: click is required for CLI. Install with: pip install click")
    sys.exit(1)

from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions, WorkflowResult
from music_workflow.core.models import TrackInfo, TrackStatus
from music_workflow.utils.logging import MusicWorkflowLogger
from music_workflow.config.settings import Settings


# Initialize logger
logger = MusicWorkflowLogger("music-cli")


def _print_result(result: WorkflowResult, verbose: bool = False) -> None:
    """Print workflow result in a readable format."""
    track = result.track
    status = "SUCCESS" if result.success else "FAILED"

    click.echo(f"\n[{status}] {track.title or track.id}")

    if track.artist:
        click.echo(f"  Artist: {track.artist}")

    if track.bpm:
        click.echo(f"  BPM: {track.bpm:.1f}")

    if track.key:
        click.echo(f"  Key: {track.key}")

    if track.duration:
        minutes = int(track.duration // 60)
        seconds = int(track.duration % 60)
        click.echo(f"  Duration: {minutes}:{seconds:02d}")

    if result.errors:
        click.echo(f"  Errors: {', '.join(result.errors)}")

    if verbose and result.warnings:
        click.echo(f"  Warnings: {', '.join(result.warnings)}")

    if verbose and track.file_paths:
        click.echo("  Files:")
        for fmt, path in track.file_paths.items():
            click.echo(f"    - {fmt}: {path}")

    click.echo(f"  Execution time: {result.execution_time_seconds:.2f}s")


@click.group()
@click.version_option(version="0.1.0", prog_name="music-workflow")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--dry-run", is_flag=True, help="Show what would be done without doing it")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, dry_run: bool) -> None:
    """Music Workflow CLI - Download, process, and organize music tracks."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["dry_run"] = dry_run

    if verbose:
        click.echo("Verbose mode enabled")
    if dry_run:
        click.echo("Dry run mode - no changes will be made")


@cli.command()
@click.argument("url")
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--format", "-f", multiple=True, default=["m4a"],
              help="Output format(s): m4a, aiff, wav, mp3")
@click.option("--skip-analyze", is_flag=True, help="Skip audio analysis")
@click.option("--skip-organize", is_flag=True, help="Skip file organization")
@click.pass_context
def download(
    ctx: click.Context,
    url: str,
    output: Optional[str],
    format: tuple,
    skip_analyze: bool,
    skip_organize: bool,
) -> None:
    """Download a track from URL.

    Supports YouTube, SoundCloud, and other sources via yt-dlp.

    Examples:

        music-workflow download https://soundcloud.com/artist/track

        music-workflow download -f wav -f aiff https://youtube.com/watch?v=xxx
    """
    verbose = ctx.obj.get("verbose", False)
    dry_run = ctx.obj.get("dry_run", False)

    click.echo(f"Downloading: {url}")

    if dry_run:
        click.echo("Would download with options:")
        click.echo(f"  Formats: {', '.join(format)}")
        click.echo(f"  Output: {output or 'default'}")
        click.echo(f"  Analyze: {not skip_analyze}")
        click.echo(f"  Organize: {not skip_organize}")
        return

    options = WorkflowOptions(
        download_formats=list(format),
        analyze_audio=not skip_analyze,
        organize_files=not skip_organize,
        dry_run=dry_run,
    )

    workflow = MusicWorkflow(options=options)

    # Add progress callback for verbose mode
    if verbose:
        def progress_callback(track: TrackInfo, message: str):
            click.echo(f"  [{track.status.value}] {message}")
        workflow.set_progress_callback(progress_callback)

    output_dir = Path(output) if output else None
    result = workflow.process_url(url, output_dir=output_dir)

    _print_result(result, verbose)

    if not result.success:
        sys.exit(1)


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--bpm", is_flag=True, help="Analyze BPM")
@click.option("--key", is_flag=True, help="Analyze musical key")
@click.option("--all", "analyze_all", is_flag=True, help="Perform full analysis")
@click.pass_context
def analyze(
    ctx: click.Context,
    files: tuple,
    bpm: bool,
    key: bool,
    analyze_all: bool,
) -> None:
    """Analyze audio files for BPM, key, and other metadata.

    Examples:

        music-workflow analyze track.m4a

        music-workflow analyze --bpm --key *.wav
    """
    from music_workflow.core.processor import AudioProcessor

    verbose = ctx.obj.get("verbose", False)

    if not files:
        click.echo("No files specified")
        sys.exit(1)

    processor = AudioProcessor()

    for file_path in files:
        path = Path(file_path)
        click.echo(f"\nAnalyzing: {path.name}")

        try:
            analysis = processor.analyze(path)

            if bpm or analyze_all:
                click.echo(f"  BPM: {analysis.bpm:.1f}" if analysis.bpm else "  BPM: Unknown")

            if key or analyze_all:
                click.echo(f"  Key: {analysis.key}" if analysis.key else "  Key: Unknown")

            if analyze_all:
                minutes = int(analysis.duration // 60)
                seconds = int(analysis.duration % 60)
                click.echo(f"  Duration: {minutes}:{seconds:02d}")
                click.echo(f"  Sample Rate: {analysis.sample_rate} Hz")
                click.echo(f"  Channels: {analysis.channels}")
                if analysis.loudness:
                    click.echo(f"  Loudness: {analysis.loudness:.1f} LUFS")

        except Exception as e:
            click.echo(f"  Error: {e}")


@cli.command()
@click.argument("urls", nargs=-1)
@click.option("--file", "-f", type=click.Path(exists=True),
              help="File containing URLs (one per line)")
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--format", multiple=True, default=["m4a"],
              help="Output format(s)")
@click.option("--max-concurrent", type=int, default=1,
              help="Maximum concurrent downloads")
@click.pass_context
def batch(
    ctx: click.Context,
    urls: tuple,
    file: Optional[str],
    output: Optional[str],
    format: tuple,
    max_concurrent: int,
) -> None:
    """Process multiple tracks in batch.

    URLs can be provided as arguments or from a file (one URL per line).

    Examples:

        music-workflow batch url1 url2 url3

        music-workflow batch -f urls.txt
    """
    verbose = ctx.obj.get("verbose", False)
    dry_run = ctx.obj.get("dry_run", False)

    url_list = list(urls)

    # Load URLs from file if specified
    if file:
        with open(file, "r") as f:
            url_list.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not url_list:
        click.echo("No URLs specified")
        sys.exit(1)

    click.echo(f"Processing {len(url_list)} tracks...")

    if dry_run:
        for url in url_list:
            click.echo(f"  Would process: {url}")
        return

    options = WorkflowOptions(
        download_formats=list(format),
        dry_run=dry_run,
    )

    workflow = MusicWorkflow(options=options)
    output_dir = Path(output) if output else None

    results = workflow.process_batch(url_list, output_dir=output_dir)

    # Print summary
    successful = sum(1 for r in results.values() if r.success)
    click.echo(f"\nBatch complete: {successful}/{len(results)} successful")

    if verbose:
        for url, result in results.items():
            status = "OK" if result.success else "FAIL"
            click.echo(f"  [{status}] {url}")


@cli.command()
@click.option("--playlist", "-p", help="Sync specific playlist")
@click.option("--source", type=click.Choice(["notion", "spotify", "soundcloud"]),
              default="notion", help="Source to sync from")
@click.option("--limit", type=int, help="Maximum tracks to sync")
@click.pass_context
def sync(
    ctx: click.Context,
    playlist: Optional[str],
    source: str,
    limit: Optional[int],
) -> None:
    """Sync tracks from Notion, Spotify, or SoundCloud.

    Syncs unprocessed tracks from the specified source.

    Examples:

        music-workflow sync --source notion

        music-workflow sync --source spotify --playlist "My Playlist"
    """
    verbose = ctx.obj.get("verbose", False)
    dry_run = ctx.obj.get("dry_run", False)

    click.echo(f"Syncing from {source}...")

    if playlist:
        click.echo(f"  Playlist: {playlist}")

    if limit:
        click.echo(f"  Limit: {limit} tracks")

    if dry_run:
        click.echo("Dry run - would sync tracks from source")
        return

    if source == "notion":
        _sync_from_notion(playlist, limit, verbose)
    elif source == "spotify":
        _sync_from_spotify(playlist, limit, verbose)
    elif source == "soundcloud":
        _sync_from_soundcloud(playlist, limit, verbose)


def _sync_from_notion(
    playlist: Optional[str],
    limit: Optional[int],
    verbose: bool,
) -> None:
    """Sync unprocessed tracks from Notion."""
    try:
        from music_workflow.integrations.notion import NotionClient, TracksDatabase

        notion = NotionClient()
        tracks_db = TracksDatabase(notion)

        # Get unprocessed tracks
        tracks = tracks_db.get_unprocessed_tracks(
            playlist=playlist,
            limit=limit,
        )

        click.echo(f"Found {len(tracks)} unprocessed tracks")

        if not tracks:
            return

        options = WorkflowOptions()
        workflow = MusicWorkflow(options=options)

        for track in tracks:
            click.echo(f"\nProcessing: {track.title or track.id}")
            result = workflow.process_track(track)
            _print_result(result, verbose)

            # Update Notion
            if result.success:
                tracks_db.update_track(track)

    except Exception as e:
        click.echo(f"Error syncing from Notion: {e}")
        sys.exit(1)


def _sync_from_spotify(
    playlist: Optional[str],
    limit: Optional[int],
    verbose: bool,
) -> None:
    """Sync tracks from Spotify playlist."""
    try:
        from music_workflow.integrations.spotify import SpotifyClient

        client = SpotifyClient()

        if not playlist:
            click.echo("Please specify a playlist with --playlist")
            sys.exit(1)

        tracks = client.get_playlist(playlist, limit=limit)
        click.echo(f"Found {len(tracks)} tracks in playlist")

        # TODO: Implement Spotify sync workflow
        click.echo("Spotify sync not yet fully implemented")

    except Exception as e:
        click.echo(f"Error syncing from Spotify: {e}")
        sys.exit(1)


def _sync_from_soundcloud(
    playlist: Optional[str],
    limit: Optional[int],
    verbose: bool,
) -> None:
    """Sync tracks from SoundCloud."""
    try:
        from music_workflow.integrations.soundcloud import SoundCloudClient

        client = SoundCloudClient()

        if playlist:
            # Get playlist tracks
            tracks = client.get_playlist(playlist)
            click.echo(f"Found {len(tracks)} tracks in playlist")
        else:
            click.echo("Please specify a playlist URL with --playlist")
            sys.exit(1)

        # TODO: Implement SoundCloud sync workflow
        click.echo("SoundCloud sync not yet fully implemented")

    except Exception as e:
        click.echo(f"Error syncing from SoundCloud: {e}")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current workflow status and statistics."""
    click.echo("Music Workflow Status")
    click.echo("=" * 40)

    settings = Settings()

    click.echo(f"\nConfiguration:")
    click.echo(f"  Output Directory: {settings.output_dir}")
    click.echo(f"  Temp Directory: {settings.temp_dir}")
    click.echo(f"  Log Level: {settings.log_level}")

    # Check integrations
    click.echo(f"\nIntegrations:")

    # Notion
    try:
        from music_workflow.integrations.notion import NotionClient
        client = NotionClient()
        click.echo("  Notion: Connected")
    except Exception as e:
        click.echo(f"  Notion: Not configured ({e})")

    # Spotify
    try:
        from music_workflow.integrations.spotify import SpotifyClient
        client = SpotifyClient()
        click.echo("  Spotify: Configured")
    except Exception as e:
        click.echo(f"  Spotify: Not configured ({e})")

    # Eagle
    try:
        from music_workflow.integrations.eagle import EagleClient
        client = EagleClient()
        if client.is_available():
            click.echo("  Eagle: Available")
        else:
            click.echo("  Eagle: Not running")
    except Exception as e:
        click.echo(f"  Eagle: Not available ({e})")


def main() -> None:
    """Entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
