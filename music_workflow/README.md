# Music Workflow Module

**Version:** 1.0.0
**Status:** Production Ready (Feature-Flagged)
**Last Updated:** 2026-01-13

A modular music workflow system for downloading, processing, and organizing music tracks with integration to Notion, Eagle, Spotify, and SoundCloud.

## Overview

This module provides a modular alternative to the monolithic `soundcloud_download_prod_merge-2.py` script. It follows a bifurcation strategy that allows gradual migration while maintaining backward compatibility.

## Module Structure

```
music_workflow/
├── __init__.py              # Package initialization
├── dispatcher.py            # Feature flag routing between modular/monolithic
├── config/                  # Configuration management
│   ├── settings.py          # Centralized settings with env var support
│   └── constants.py         # Shared constants
├── core/                    # Core workflow logic
│   ├── downloader.py        # Multi-source download (YouTube, SoundCloud)
│   ├── processor.py         # Audio processing (BPM, key, normalization)
│   ├── organizer.py         # File organization and path management
│   ├── workflow.py          # Main workflow orchestration
│   └── models.py            # Data models (TrackInfo, etc.)
├── integrations/            # External service integrations
│   ├── notion/              # Notion API integration
│   │   ├── client.py        # Notion API wrapper
│   │   ├── tracks_db.py     # Tracks database operations
│   │   └── playlists_db.py  # Playlists database operations
│   ├── eagle/               # Eagle library integration
│   │   └── client.py        # Eagle API wrapper
│   ├── spotify/             # Spotify API integration
│   │   └── client.py        # Spotify API wrapper
│   └── soundcloud/          # SoundCloud integration
│       ├── client.py        # SoundCloud download via yt-dlp
│       └── compat.py        # Compatibility layer
├── deduplication/           # Duplicate detection
│   ├── fingerprint.py       # Audio fingerprinting
│   ├── matcher.py           # Multi-source matching
│   ├── notion_dedup.py      # Notion database deduplication
│   └── eagle_dedup.py       # Eagle library deduplication
├── metadata/                # Metadata handling
│   ├── extraction.py        # Extract metadata from files
│   ├── enrichment.py        # Enrich from external sources
│   └── embedding.py         # Embed metadata into files
├── cli/                     # Command-line interface
│   ├── main.py              # CLI entry point
│   └── commands/            # CLI commands
│       ├── download.py      # Download command
│       ├── process.py       # Process command
│       ├── sync.py          # Sync command
│       └── batch.py         # Batch operations
├── utils/                   # Shared utilities
│   ├── logging.py           # Structured logging
│   ├── errors.py            # Custom error classes
│   ├── validators.py        # Input validation
│   └── file_ops.py          # File operations
└── tests/                   # Test suite
    ├── conftest.py          # Pytest fixtures
    ├── unit/                # Unit tests
    └── integration/         # Integration tests
```

## Installation

The music_workflow module is part of the github-production repository. No separate installation required.

### Dependencies

```bash
# Install dependencies
pip install -r requirements.txt

# Or install specific packages
pip install yt-dlp click pyyaml notion-client spotipy
```

## Configuration

### Environment Variables

```bash
# Feature flags
MUSIC_WORKFLOW_USE_MODULAR=false     # Enable modular implementation
MUSIC_WORKFLOW_YOUTUBE_FALLBACK=true # YouTube search for Spotify
MUSIC_WORKFLOW_DEDUP_ENABLED=true    # Enable deduplication
MUSIC_WORKFLOW_LOG_LEVEL=INFO        # Log level

# Directories
MUSIC_WORKFLOW_OUTPUT_DIR=~/Music/Downloads
MUSIC_WORKFLOW_TEMP_DIR=/tmp/music_workflow

# Notion configuration
TRACKS_DB_ID=<your_tracks_db_id>
PLAYLISTS_DB_ID=<your_playlists_db_id>
EXECUTION_LOGS_DB_ID=<your_execution_logs_db_id>
ISSUES_DB_ID=229e73616c27808ebf06c202b10b5166

# Eagle configuration
EAGLE_LIBRARY_PATH=/Volumes/VIBES/Music-Library-2.library

# Spotify configuration
SPOTIFY_CLIENT_ID=<your_client_id>
SPOTIFY_CLIENT_SECRET=<your_client_secret>
```

### Configuration File

See `music_workflow.yaml` in project root for YAML-based configuration.

## Usage

### Using the Dispatcher (Recommended)

The dispatcher automatically routes to modular or monolithic based on feature flags:

```python
from music_workflow.dispatcher import dispatch_workflow

result = dispatch_workflow(
    url="https://soundcloud.com/artist/track",
    formats=["m4a", "wav"],
    analyze=True,
    organize=True
)
```

### Direct Modular Usage

```python
from music_workflow.core.workflow import MusicWorkflow, WorkflowOptions

options = WorkflowOptions(
    download_formats=["m4a"],
    analyze_audio=True,
    organize_files=True,
)

workflow = MusicWorkflow(options=options)
result = workflow.process_url("https://soundcloud.com/artist/track")
```

### CLI Usage

```bash
# Download a track
python -m music_workflow.cli.main download "https://soundcloud.com/artist/track"

# Process existing files
python -m music_workflow.cli.main process /path/to/audio.m4a

# Sync with Notion
python -m music_workflow.cli.main sync --playlist "My Playlist"

# Batch operations
python -m music_workflow.cli.main batch --input urls.txt
```

## Feature Flags

The module supports gradual migration via feature flags:

| Flag | Default | Description |
|------|---------|-------------|
| `MUSIC_WORKFLOW_USE_MODULAR` | `false` | Use modular implementation |
| `MUSIC_WORKFLOW_YOUTUBE_FALLBACK` | `true` | YouTube search for DRM content |
| `MUSIC_WORKFLOW_DEDUP_ENABLED` | `true` | Enable deduplication checks |

## Error Handling

The module provides standardized error classes:

- `MusicWorkflowError` - Base exception
- `DownloadError` - Download failures
- `DRMProtectionError` - DRM-protected content (triggers YouTube fallback)
- `ProcessingError` - Audio processing failures
- `IntegrationError` - External service errors
- `DuplicateFoundError` - Duplicate track detected
- `ConfigurationError` - Invalid configuration
- `ValidationError` - Input validation failures

## Testing

```bash
# Run all tests
pytest music_workflow/tests/

# Run unit tests only
pytest music_workflow/tests/unit/

# Run integration tests only
pytest music_workflow/tests/integration/

# Run with coverage
pytest music_workflow/tests/ --cov=music_workflow --cov-report=html
```

## Migration from Monolithic

See `plans/MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md` for the full migration strategy.

### Quick Migration Guide

1. Set `MUSIC_WORKFLOW_USE_MODULAR=true`
2. Monitor logs for any issues
3. Set `MUSIC_WORKFLOW_FALLBACK_TO_MONOLITHIC=false` once stable
4. Remove monolithic script from production

## Related Documentation

- `plans/MODULARIZED_IMPLEMENTATION_DESIGN.md` - Architecture design
- `plans/MONOLITHIC_MAINTENANCE_PLAN.md` - Maintenance plan
- `plans/MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md` - Migration strategy
- `music_workflow.yaml` - Configuration file

## Changelog

### Version 1.0.0 (2026-01-12)

- Initial modular implementation
- Feature flag support for gradual migration
- Full test suite with unit and integration tests
- Dispatcher for routing between implementations
- DRM protection error handling with YouTube fallback
- Comprehensive error classes
- CLI implementation with download, process, sync, batch commands

---

**Created by:** Plans Directory Audit Agent
**Part of:** VibeVessel Marketing System
