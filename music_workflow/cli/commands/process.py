"""
Process command for music workflow CLI.

Provides commands for processing existing audio files,
including analysis, format conversion, and metadata embedding.
"""

import click
from pathlib import Path
from typing import Optional, List

from music_workflow.core.processor import AudioProcessor, ProcessingOptions
from music_workflow.metadata.extraction import MetadataExtractor
from music_workflow.metadata.embedding import MetadataEmbedder
from music_workflow.utils.logging import MusicWorkflowLogger


logger = MusicWorkflowLogger("process-cli")


@click.command("process")
@click.argument("file_path", type=click.Path(exists=True))
@click.option(
    "--analyze/--no-analyze",
    default=True,
    help="Perform audio analysis (BPM, key detection)"
)
@click.option(
    "--normalize/--no-normalize",
    default=False,
    help="Normalize audio to target loudness"
)
@click.option(
    "--target-lufs",
    type=float,
    default=-14.0,
    help="Target loudness in LUFS for normalization"
)
@click.option(
    "--embed-metadata",
    is_flag=True,
    help="Embed analysis results as file metadata"
)
@click.option(
    "--output-format", "-f",
    type=click.Choice(["m4a", "wav", "aiff", "mp3", "flac"]),
    default=None,
    help="Convert to specified format"
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for processed files"
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output"
)
def process(
    file_path: str,
    analyze: bool,
    normalize: bool,
    target_lufs: float,
    embed_metadata: bool,
    output_format: Optional[str],
    output_dir: Optional[str],
    verbose: bool,
):
    """Process an audio file.

    Performs analysis, normalization, and format conversion.

    Example:
        music-workflow process track.m4a --analyze
        music-workflow process track.wav --normalize --target-lufs -14.0
        music-workflow process track.m4a -f wav -o ./converted
    """
    source = Path(file_path)

    if verbose:
        click.echo(f"Processing: {source}")

    try:
        options = ProcessingOptions(
            target_lufs=target_lufs,
            analyze_bpm=analyze,
            analyze_key=analyze,
        )
        processor = AudioProcessor(options)

        # Analysis
        if analyze:
            click.echo("Analyzing audio...")
            analysis = processor.analyze(source)

            click.echo(f"  BPM: {analysis.bpm}")
            click.echo(f"  Key: {analysis.key}")
            click.echo(f"  Duration: {analysis.duration:.2f}s")
            click.echo(f"  Sample Rate: {analysis.sample_rate} Hz")
            click.echo(f"  Channels: {analysis.channels}")
            if analysis.loudness:
                click.echo(f"  Loudness: {analysis.loudness:.2f} LUFS")

        # Normalization
        if normalize:
            click.echo(f"Normalizing to {target_lufs} LUFS...")
            normalized_path = processor.normalize(source, target_lufs)
            click.echo(f"  Normalized: {normalized_path}")
            source = normalized_path

        # Format conversion
        if output_format:
            click.echo(f"Converting to {output_format}...")
            if output_dir:
                output_path = Path(output_dir) / f"{source.stem}.{output_format}"
            else:
                output_path = source.with_suffix(f".{output_format}")

            converted_path = processor.convert(source, output_format, output_path)
            click.echo(f"  Converted: {converted_path}")

        # Metadata embedding
        if embed_metadata and analyze:
            click.echo("Embedding metadata...")
            embedder = MetadataEmbedder()
            embedder.embed_analysis(source, analysis)
            click.echo("  Metadata embedded")

        click.secho("Processing complete!", fg="green")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()


@click.command("analyze")
@click.argument("file_path", type=click.Path(exists=True))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results as JSON"
)
def analyze(file_path: str, output_json: bool):
    """Analyze an audio file for BPM, key, and other properties.

    Example:
        music-workflow analyze track.m4a
        music-workflow analyze track.wav --json
    """
    source = Path(file_path)

    try:
        processor = AudioProcessor()
        analysis = processor.analyze(source)

        if output_json:
            import json
            result = {
                "file": str(source),
                "bpm": analysis.bpm,
                "key": analysis.key,
                "duration": analysis.duration,
                "sample_rate": analysis.sample_rate,
                "channels": analysis.channels,
                "loudness": analysis.loudness,
            }
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(f"File: {source.name}")
            click.echo(f"BPM: {analysis.bpm}")
            click.echo(f"Key: {analysis.key}")
            click.echo(f"Duration: {analysis.duration:.2f}s")
            click.echo(f"Sample Rate: {analysis.sample_rate} Hz")
            click.echo(f"Channels: {analysis.channels}")
            if analysis.loudness:
                click.echo(f"Loudness: {analysis.loudness:.2f} LUFS")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()


@click.command("convert")
@click.argument("source", type=click.Path(exists=True))
@click.argument("target_format", type=click.Choice(["m4a", "wav", "aiff", "mp3", "flac"]))
@click.option(
    "--output", "-o",
    type=click.Path(),
    default=None,
    help="Output file path"
)
def convert(source: str, target_format: str, output: Optional[str]):
    """Convert an audio file to another format.

    Example:
        music-workflow convert track.m4a wav
        music-workflow convert track.wav aiff -o output.aiff
    """
    source_path = Path(source)

    if output:
        output_path = Path(output)
    else:
        output_path = source_path.with_suffix(f".{target_format}")

    try:
        processor = AudioProcessor()
        result = processor.convert(source_path, target_format, output_path)
        click.secho(f"Converted: {result}", fg="green")

    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()
