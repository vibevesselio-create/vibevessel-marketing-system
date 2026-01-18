# Music Track Sync Workflow - Production Guide

**Version**: 1.0  
**Date**: 2026-01-08  
**Status**: Production Ready

## Overview

The Music Track Sync Workflow is a production-ready automation system that synchronizes music tracks from various sources (Spotify, SoundCloud, YouTube) into a centralized Notion database with comprehensive metadata processing, deduplication, and file management.

## Quick Start

### Basic Usage

```bash
# Execute with auto-detection fallback chain (no URL provided)
python3 scripts/music_track_sync_workflow_prod.py

# Execute with a specific URL
python3 scripts/music_track_sync_workflow_prod.py --url "https://soundcloud.com/artist/track"

# Execute in DEV mode (for testing)
python3 scripts/music_track_sync_workflow_prod.py --mode DEV
```

### Command Line Options

- `--url URL`: Optional URL to process directly (Spotify, SoundCloud, or YouTube)
- `--mode PROD|DEV`: Execution mode (default: PROD)

## Workflow Phases

### Pre-Execution Phase

The workflow performs intelligence gathering before execution:

1. **Production Script Verification**
   - Verifies `monolithic-scripts/soundcloud_download_prod_merge-2.py` exists and is accessible
   - Creates critical error task if script is missing

2. **Plans Directory Review**
   - Scans `plans/` directory for recent plan files
   - Extracts expected deliverables from plans
   - **Takes direct action** to complete missing deliverables:
     - Creates missing code files
     - Creates missing documentation files
     - Creates issues in Issues+Questions database for gaps that cannot be resolved

3. **Related Items Identification**
   - Searches for related documentation and project items
   - Identifies automation opportunities

### Execution Phase

The workflow executes based on whether a URL is provided:

#### With URL Provided

Direct URL processing mode:
- Calls production script with `--mode url --url {url}`
- Handles SoundCloud, YouTube, and Spotify URLs
- Processes track through full workflow (download, convert, tag, Eagle import)

#### Without URL (Auto-Detection Mode)

Executes sync-aware fallback chain:

1. **Priority 1: Spotify Current Track**
   - Checks if Spotify is currently playing
   - Queries Notion for sync status
   - Processes track if not fully synced

2. **Priority 2: SoundCloud Likes** (up to 5 tracks)
   - Fetches recent SoundCloud likes
   - Checks Notion sync status for each
   - Processes first unsynced track

3. **Priority 3: Spotify Liked Tracks** (up to 5 tracks)
   - Fetches recent Spotify liked tracks
   - Checks Notion sync status for each
   - Processes first unsynced track

4. **Final Fallback: Single Mode**
   - Executes production script with `--mode single`
   - Processes newest eligible track from Notion database

### Post-Execution Phase

After workflow execution:

1. **Execution Verification**
   - Verifies workflow completed successfully
   - Logs results and errors

2. **Automation Gap Identification**
   - Identifies manual steps that could be automated
   - Identifies missing webhook triggers
   - Identifies automation opportunities

3. **Notion Task Creation**
   - Creates Agent-Tasks for automation opportunities
   - Links tasks to related project items
   - Sets appropriate priority and status

4. **Documentation Updates**
   - Updates workflow documentation
   - Creates issues for failures

## Configuration

### Environment Variables

**Required:**
- `NOTION_TOKEN`: Notion API token
- `TRACKS_DB_ID`: Notion database ID for music tracks (default: `27ce7361-6c27-80fb-b40e-fefdd47d6640`)

**Optional:**
- `ARTISTS_DB_ID`: Notion database ID for artists (default: `20ee7361-6c27-816d-9817-d4348f6de07c`)
- `SOUNDCLOUD_PROFILE`: SoundCloud profile name (default: `vibe-vessel`)
- `AGENT_TASKS_DB_ID`: Notion database ID for agent tasks (default: `284e73616c278018872aeb14e82e0392`)
- `ISSUES_DB_ID`: Notion database ID for issues (default: `229e73616c27808ebf06c202b10b5166`)
- `CURSOR_MM1_AGENT_ID`: Cursor MM1 Agent ID (default: `249e7361-6c27-8100-8a74-de7eabb9fc8d`)

### Script Paths

- Production script: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
- Auto-detection script: `scripts/music_track_sync_auto_detect.py`
- Plans directory: `plans/`

## Error Handling

### Critical Errors (Stop execution, create Agent-Task)

- **Notion API 401/403**: Authentication failure
- **Notion API 404**: Database not found
- **Production script not found**: Script missing or inaccessible
- **TRACKS_DB_ID validation failure**: Invalid database ID
- **Script execution timeout**: Execution exceeded 10 minute timeout

### High Errors (Retry with backoff, then create task)

- **yt-dlp rate limit**: Download rate limit exceeded
- **Spotify API rate limit**: Spotify API rate limit exceeded
- **Network timeouts**: Network connectivity issues

### Medium Errors (Log warning, continue)

- **Download failure**: Mark `Downloaded=false` in Notion, continue
- **External volume unmounted**: Skip volume, log warning
- **Eagle API connection failed**: Auto-launch Eagle, retry, then log warning

## Database IDs

### Verified Database IDs

| Database | ID | Source |
|----------|-----|--------|
| Music Tracks | `27ce7361-6c27-80fb-b40e-fefdd47d6640` | unified_config.py, codebase |
| Music Artists | `20ee7361-6c27-816d-9817-d4348f6de07c` | codebase |
| Agent-Tasks | `284e73616c278018872aeb14e82e0392` | execute script, codebase |
| Issues+Questions | `229e73616c27808ebf06c202b10b5166` | shared_core/notion/issues_questions.py |

## Integration Points

### Production Script

The workflow uses the production script (`soundcloud_download_prod_merge-2.py`) which provides:

- Comprehensive deduplication (Notion + Eagle)
- Advanced metadata maximization (BPM, Key, Fingerprint, Spotify enrichment)
- Complete file organization (M4A/ALAC, WAV, AIFF formats)
- Full system integration (Notion, Eagle, YouTube, SoundCloud, Spotify)
- Production-ready error handling and recovery

### Auto-Detection Script

The auto-detection script (`scripts/music_track_sync_auto_detect.py`) implements:

- Sync-aware fallback chain
- Notion sync status checking
- Track selection based on sync state
- Integration with production script

## Troubleshooting

### Common Issues

1. **Production script not found**
   - Verify script exists at: `monolithic-scripts/soundcloud_download_prod_merge-2.py`
   - Check file permissions (script must be readable)

2. **Notion API authentication failure**
   - Verify `NOTION_TOKEN` environment variable is set
   - Check token permissions and validity

3. **Database not found**
   - Verify `TRACKS_DB_ID` environment variable is set correctly
   - Check database ID format (UUID format)

4. **Auto-detection script not found**
   - Verify script exists at: `scripts/music_track_sync_auto_detect.py`
   - Check file permissions

5. **Workflow execution timeout**
   - Increase timeout in script (default: 600 seconds)
   - Check for long-running operations

### Debug Mode

Enable debug logging by setting environment variable:

```bash
export LOG_LEVEL=DEBUG
python3 scripts/music_track_sync_workflow_prod.py
```

## Success Criteria

A successful workflow execution should:

1. ✅ Verify production script exists and is accessible
2. ✅ Review plans directory and identify missing deliverables
3. ✅ Execute workflow (URL mode or auto-detection mode)
4. ✅ Complete at least one track sync
5. ✅ Create Notion tasks for automation opportunities
6. ✅ Update documentation

## Related Documentation

- `PRODUCTION_MUSIC_DOWNLOAD_WORKFLOW_COMPREHENSIVE_REPORT.md`: Comprehensive workflow documentation
- `MUSIC_WORKFLOW_IMPLEMENTATION_STATUS.md`: Implementation status tracking
- `plans/MUSIC_WORKFLOW_BIFURCATION_STRATEGY.md`: Future modularization strategy

## Support

For issues or questions:

1. Check error logs for detailed error messages
2. Review Notion Agent-Tasks database for error tasks
3. Review Issues+Questions database for documented issues
4. Check workflow documentation for common solutions

---

**Last Updated**: 2026-01-08  
**Maintained By**: Cursor MM1 Agent
