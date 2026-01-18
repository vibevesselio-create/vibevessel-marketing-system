"""
Batch command for music workflow CLI.

Provides commands for batch operations including bulk processing,
directory scanning, and parallel execution.
"""

import click
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions
from music_workflow.core.processor import AudioProcessor
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("batch-cli")


@click.command("batch")
@click.argument("input_path", type=click.Path(exists=True))
@click.option(
    "--operation",
    type=click.Choice(["analyze", "convert", "organize", "full"]),
    default="full",
    help="Batch operation to perform"
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory"
)
@click.option(
    "--pattern",
    default="*.m4a,*.wav,*.aiff,*.mp3,*.flac",
    help="File pattern to match (comma-separated)"
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Search directories recursively"
)
@click.option(
    "--workers",
    type=int,
    default=4,
    help="Number of parallel workers"
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
def batch(
    input_path: str,
    operation: str,
    output_dir: Optional[str],
    pattern: str,
    recursive: bool,
    workers: int,
    dry_run: bool,
    verbose: bool,
):
    """Perform batch operations on audio files.

    Can process a directory of files or a file containing URLs.

    Example:
        music-workflow batch ./music --operation analyze
        music-workflow batch urls.txt --operation full
    """
    input_path = Path(input_path)

    # Determine if input is a file or directory
    if input_path.is_file():
        if input_path.suffix == ".txt":
            _batch_from_urls(input_path, operation, output_dir, workers, dry_run, verbose)
        else:
            click.secho("Single file provided, use 'process' command instead", fg="yellow")
            return
    elif input_path.is_dir():
        _batch_from_directory(
            input_path, operation, output_dir, pattern, recursive, workers, dry_run, verbose
        )
    else:
        click.secho(f"Invalid input path: {input_path}", fg="red")
        return


def _batch_from_urls(
    urls_file: Path,
    operation: str,
    output_dir: Optional[str],
    workers: int,
    dry_run: bool,
    verbose: bool,
):
    """Process batch from a file of URLs."""
    urls = [
        line.strip()
        for line in urls_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    if not urls:
        click.echo("No URLs found in file")
        return

    click.echo(f"Found {len(urls)} URLs")

    if dry_run:
        click.echo("[DRY RUN] Would process:")
        for url in urls[:10]:
            click.echo(f"  {url}")
        if len(urls) > 10:
            click.echo(f"  ... and {len(urls) - 10} more")
        return

    options = WorkflowOptions(
        download_formats=["m4a", "aiff", "wav"],
        analyze_audio=True,
        organize_files=True,
    )
    workflow = MusicWorkflow(options=options)
    output_path = Path(output_dir) if output_dir else None

    results = workflow.process_batch(urls, output_dir=output_path)

    # Summary
    successful = sum(1 for r in results.values() if r.success)
    failed = len(results) - successful

    click.echo(f"\nBatch complete: {successful} successful, {failed} failed")


def _batch_from_directory(
    directory: Path,
    operation: str,
    output_dir: Optional[str],
    pattern: str,
    recursive: bool,
    workers: int,
    dry_run: bool,
    verbose: bool,
):
    """Process batch from a directory of files."""
    # Find matching files
    patterns = [p.strip() for p in pattern.split(",")]
    files: List[Path] = []

    for p in patterns:
        if recursive:
            files.extend(directory.rglob(p))
        else:
            files.extend(directory.glob(p))

    files = sorted(set(files))  # Remove duplicates and sort

    if not files:
        click.echo(f"No files matching '{pattern}' found in {directory}")
        return

    click.echo(f"Found {len(files)} files")

    if dry_run:
        click.echo("[DRY RUN] Would process:")
        for f in files[:10]:
            click.echo(f"  {f}")
        if len(files) > 10:
            click.echo(f"  ... and {len(files) - 10} more")
        return

    output_path = Path(output_dir) if output_dir else None
    processor = AudioProcessor()

    successful = 0
    failed = 0

    if operation == "analyze":
        click.echo("Analyzing files...")
        for i, file in enumerate(files, 1):
            try:
                analysis = processor.analyze(file)
                if verbose:
                    click.echo(f"[{i}/{len(files)}] {file.name}: BPM={analysis.bpm}, Key={analysis.key}")
                successful += 1
            except Exception as e:
                if verbose:
                    click.secho(f"[{i}/{len(files)}] {file.name}: Error - {e}", fg="red")
                failed += 1

    elif operation == "convert":
        if not output_path:
            click.secho("Output directory required for convert operation", fg="red")
            return

        output_path.mkdir(parents=True, exist_ok=True)
        click.echo("Converting files...")

        for i, file in enumerate(files, 1):
            try:
                output_file = output_path / f"{file.stem}.wav"
                processor.convert(file, "wav", output_file)
                if verbose:
                    click.echo(f"[{i}/{len(files)}] {file.name} -> {output_file.name}")
                successful += 1
            except Exception as e:
                if verbose:
                    click.secho(f"[{i}/{len(files)}] {file.name}: Error - {e}", fg="red")
                failed += 1

    elif operation == "organize":
        click.echo("Organizing files...")
        # Organization would use the organizer module
        click.secho("Organize operation not yet implemented", fg="yellow")
        return

    elif operation == "full":
        click.echo("Full processing...")
        options = WorkflowOptions(
            download_formats=["m4a", "aiff", "wav"],
            analyze_audio=True,
            organize_files=True,
        )
        workflow = MusicWorkflow(options=options)

        for i, file in enumerate(files, 1):
            try:
                # For local files, we just process them
                analysis = processor.analyze(file)
                if verbose:
                    click.echo(f"[{i}/{len(files)}] {file.name}: BPM={analysis.bpm}, Key={analysis.key}")
                successful += 1
            except Exception as e:
                if verbose:
                    click.secho(f"[{i}/{len(files)}] {file.name}: Error - {e}", fg="red")
                failed += 1

    click.echo(f"\nBatch complete: {successful} successful, {failed} failed")


@click.command("scan")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "--pattern",
    default="*.m4a,*.wav,*.aiff,*.mp3,*.flac",
    help="File pattern to match"
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Search recursively"
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON"
)
def scan(directory: str, pattern: str, recursive: bool, output_json: bool):
    """Scan a directory for audio files.

    Lists all audio files matching the pattern.

    Example:
        music-workflow scan ./music
        music-workflow scan ./library --pattern "*.wav" --json
    """
    dir_path = Path(directory)
    patterns = [p.strip() for p in pattern.split(",")]
    files: List[Path] = []

    for p in patterns:
        if recursive:
            files.extend(dir_path.rglob(p))
        else:
            files.extend(dir_path.glob(p))

    files = sorted(set(files))

    if output_json:
        import json
        result = {
            "directory": str(dir_path),
            "pattern": pattern,
            "recursive": recursive,
            "count": len(files),
            "files": [str(f) for f in files],
        }
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"Directory: {dir_path}")
        click.echo(f"Pattern: {pattern}")
        click.echo(f"Found: {len(files)} files")
        click.echo("")

        for f in files:
            size_mb = f.stat().st_size / (1024 * 1024)
            click.echo(f"  {f.name} ({size_mb:.1f} MB)")


@click.command("stats")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "--pattern",
    default="*.m4a,*.wav,*.aiff,*.mp3,*.flac",
    help="File pattern to match"
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Search recursively"
)
def stats(directory: str, pattern: str, recursive: bool):
    """Show statistics for audio files in a directory.

    Example:
        music-workflow stats ./music
    """
    dir_path = Path(directory)
    patterns = [p.strip() for p in pattern.split(",")]
    files: List[Path] = []

    for p in patterns:
        if recursive:
            files.extend(dir_path.rglob(p))
        else:
            files.extend(dir_path.glob(p))

    files = sorted(set(files))

    if not files:
        click.echo("No files found")
        return

    # Calculate statistics
    total_size = sum(f.stat().st_size for f in files)
    by_format = {}

    for f in files:
        ext = f.suffix.lower()
        if ext not in by_format:
            by_format[ext] = {"count": 0, "size": 0}
        by_format[ext]["count"] += 1
        by_format[ext]["size"] += f.stat().st_size

    click.echo(f"Directory: {dir_path}")
    click.echo(f"Total files: {len(files)}")
    click.echo(f"Total size: {total_size / (1024*1024*1024):.2f} GB")
    click.echo("")
    click.echo("By format:")

    for ext, data in sorted(by_format.items()):
        size_gb = data["size"] / (1024*1024*1024)
        click.echo(f"  {ext}: {data['count']} files ({size_gb:.2f} GB)")
