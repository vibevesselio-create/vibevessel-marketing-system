"""
Download command for music workflow CLI.

Provides commands for downloading tracks from various sources
including YouTube, SoundCloud, and Spotify (via YouTube fallback).
"""

import click
from pathlib import Path
from typing import Optional

from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions
from music_workflow.core.downloader import Downloader, DownloadOptions
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("download-cli")


@click.command("download")
@click.argument("url")
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for downloaded files"
)
@click.option(
    "--formats", "-f",
    multiple=True,
    default=["m4a", "aiff", "wav"],
    help="Output formats (can specify multiple)"
)
@click.option(
    "--analyze/--no-analyze",
    default=True,
    help="Perform audio analysis (BPM, key detection)"
)
@click.option(
    "--organize/--no-organize",
    default=True,
    help="Organize files into playlist folders"
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
def download(
    url: str,
    output_dir: Optional[str],
    formats: tuple,
    analyze: bool,
    organize: bool,
    dry_run: bool,
    verbose: bool,
):
    """Download a track from URL.

    Supports YouTube, SoundCloud, and other yt-dlp compatible sources.

    Example:
        music-workflow download https://youtube.com/watch?v=...
        music-workflow download https://soundcloud.com/artist/track
    """
    if verbose:
        click.echo(f"Downloading from: {url}")
        click.echo(f"Formats: {', '.join(formats)}")
        if output_dir:
            click.echo(f"Output directory: {output_dir}")

    if dry_run:
        click.echo("[DRY RUN] Would download:")
        click.echo(f"  URL: {url}")
        click.echo(f"  Formats: {', '.join(formats)}")
        click.echo(f"  Analyze: {analyze}")
        click.echo(f"  Organize: {organize}")
        return

    try:
        # Configure workflow
        options = WorkflowOptions(
            download_formats=list(formats),
            analyze_audio=analyze,
            organize_files=organize,
            dry_run=dry_run,
        )

        workflow = MusicWorkflow(options=options)

        # Set progress callback for verbose output
        if verbose:
            def progress_callback(track, message):
                click.echo(f"  [{track.id}] {message}")
            workflow.set_progress_callback(progress_callback)

        # Process URL
        output_path = Path(output_dir) if output_dir else None
        result = workflow.process_url(url, output_dir=output_path)

        # Report results
        if result.success:
            click.secho("Download complete!", fg="green")
            click.echo(f"Title: {result.track.title}")
            click.echo(f"Artist: {result.track.artist}")

            if result.track.bpm:
                click.echo(f"BPM: {result.track.bpm}")
            if result.track.key:
                click.echo(f"Key: {result.track.key}")

            if result.track.file_paths:
                click.echo("Files:")
                for fmt, path in result.track.file_paths.items():
                    click.echo(f"  {fmt}: {path}")
        else:
            click.secho("Download failed!", fg="red")
            for error in result.errors:
                click.echo(f"  Error: {error}")

        # Show warnings
        if result.warnings:
            click.secho("Warnings:", fg="yellow")
            for warning in result.warnings:
                click.echo(f"  {warning}")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()


@click.command("download-batch")
@click.argument("urls_file", type=click.Path(exists=True))
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for downloaded files"
)
@click.option(
    "--formats", "-f",
    multiple=True,
    default=["m4a"],
    help="Output formats"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output"
)
def download_batch(
    urls_file: str,
    output_dir: Optional[str],
    formats: tuple,
    verbose: bool,
):
    """Download multiple tracks from a file of URLs.

    The file should contain one URL per line.

    Example:
        music-workflow download-batch urls.txt -o ./downloads
    """
    # Read URLs from file
    urls_path = Path(urls_file)
    urls = [
        line.strip()
        for line in urls_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not urls:
        click.secho("No URLs found in file", fg="yellow")
        return

    click.echo(f"Processing {len(urls)} URLs...")

    options = WorkflowOptions(
        download_formats=list(formats),
        analyze_audio=True,
        organize_files=True,
    )

    workflow = MusicWorkflow(options=options)
    output_path = Path(output_dir) if output_dir else None

    results = workflow.process_batch(urls, output_dir=output_path)

    # Summary
    successful = sum(1 for r in results.values() if r.success)
    failed = len(results) - successful

    click.echo(f"\nResults: {successful} successful, {failed} failed")

    if failed > 0:
        click.secho("Failed downloads:", fg="red")
        for url, result in results.items():
            if not result.success:
                click.echo(f"  {url}")
                for error in result.errors:
                    click.echo(f"    - {error}")
