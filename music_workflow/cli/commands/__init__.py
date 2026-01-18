"""
CLI commands for music workflow.

This module exposes all CLI commands for the music workflow system.
Commands are implemented using Click for consistent interface.
"""

from music_workflow.cli.commands.download import download, download_batch
from music_workflow.cli.commands.process import process, analyze, convert
from music_workflow.cli.commands.sync import sync, sync_playlist
from music_workflow.cli.commands.batch import batch, scan, stats

__all__ = [
    "download",
    "download_batch",
    "process",
    "analyze",
    "convert",
    "sync",
    "sync_playlist",
    "batch",
    "scan",
    "stats",
]
