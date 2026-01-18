# Modularized Implementation Design

**Date:** 2026-01-08
**Status:** IMPLEMENTATION COMPLETE - Phase 5 Pending
**Last Audit:** 2026-01-14 06:01:00
**Created By:** Plans Directory Audit Agent (Gap Reconciliation)

---

## Executive Summary

This document outlines the modular architecture design for the music workflow system, providing a clear path from the monolithic implementation (`soundcloud_download_prod_merge-2.py`) to a maintainable, testable, and extensible modular codebase.

---

## Current State

### Monolithic Implementation

**Primary Script:** `monolithic-scripts/soundcloud_download_prod_merge-2.py`
- **Size:** ~413KB, ~8,500+ lines
- **Responsibility:** Everything - download, process, dedupe, organize, integrate
- **Issues:**
  - Difficult to test individual components
  - High cognitive load for maintenance
  - Single point of failure
  - Complex dependency management

### Supporting Files

| File | Purpose | Size |
|------|---------|------|
| `music_workflow_common.py` | Shared utilities | 6,245 bytes |
| `spotify_integration_module.py` | Spotify API integration | 37,503 bytes |
| `execute_music_track_sync_workflow.py` | Workflow execution | 19,240 bytes |

---

## Target Architecture

### Module Structure

```
music_workflow/
├── __init__.py                    # Package initialization
├── config/
│   ├── __init__.py
│   ├── settings.py                # Configuration management
│   └── constants.py               # Shared constants
├── core/
│   ├── __init__.py
│   ├── downloader.py              # Download logic (multi-source)
│   ├── processor.py               # Audio processing (BPM, key, normalize)
│   ├── organizer.py               # File organization and path management
│   └── workflow.py                # Main workflow orchestration
├── integrations/
│   ├── __init__.py
│   ├── notion/
│   │   ├── __init__.py
│   │   ├── client.py              # Notion API client
│   │   ├── tracks_db.py           # Tracks database operations
│   │   └── playlists_db.py        # Playlists database operations
│   ├── eagle/
│   │   ├── __init__.py
│   │   ├── client.py              # Eagle API client
│   │   └── library.py             # Library management
│   ├── spotify/
│   │   ├── __init__.py
│   │   ├── client.py              # Spotify API client
│   │   └── metadata.py            # Metadata enrichment
│   └── soundcloud/
│       ├── __init__.py
│       └── client.py              # SoundCloud integration (via yt-dlp)
├── deduplication/
│   ├── __init__.py
│   ├── fingerprint.py             # Audio fingerprinting
│   ├── notion_dedup.py            # Notion database deduplication
│   ├── eagle_dedup.py             # Eagle library deduplication
│   └── matcher.py                 # Multi-source matching logic
├── metadata/
│   ├── __init__.py
│   ├── extraction.py              # Extract metadata from files
│   ├── enrichment.py              # Enrich metadata from external sources
│   └── embedding.py               # Embed metadata into files
├── cli/
│   ├── __init__.py
│   ├── main.py                    # CLI entry point
│   └── commands/
│       ├── __init__.py
│       ├── download.py            # Download command
│       ├── process.py             # Process command
│       ├── sync.py                # Sync command
│       └── batch.py               # Batch operations
├── utils/
│   ├── __init__.py
│   ├── logging.py                 # Structured logging
│   ├── errors.py                  # Custom error classes
│   ├── validators.py              # Input validation
│   └── file_ops.py                # File operations utilities
└── tests/
    ├── __init__.py
    ├── conftest.py                # Pytest fixtures
    ├── unit/
    │   ├── test_downloader.py
    │   ├── test_processor.py
    │   └── ...
    └── integration/
        ├── test_notion_integration.py
        ├── test_eagle_integration.py
        └── ...
```

---

## Module Specifications

### 1. Core Module (`music_workflow/core/`)

#### 1.1 downloader.py

**Responsibilities:**
- Download audio from multiple sources (YouTube, SoundCloud)
- Handle DRM content gracefully (YouTube search fallback for Spotify)
- Format selection and conversion
- Progress tracking

**Key Classes:**
```python
class Downloader:
    """Multi-source audio downloader."""

    def download(self, url: str, output_dir: Path, formats: List[str]) -> DownloadResult:
        """Download audio from URL."""

    def search_youtube(self, query: str) -> Optional[str]:
        """Search YouTube for a track."""

class DownloadResult:
    """Result of a download operation."""
    success: bool
    files: List[Path]
    metadata: Dict
    errors: List[str]
```

#### 1.2 processor.py

**Responsibilities:**
- Audio analysis (BPM, key detection)
- Audio normalization
- Format conversion (WAV, AIFF, M4A)
- Quality assessment

**Key Classes:**
```python
class AudioProcessor:
    """Audio processing operations."""

    def analyze(self, file_path: Path) -> AudioAnalysis:
        """Analyze audio file for BPM, key, duration."""

    def convert(self, source: Path, target_format: str) -> Path:
        """Convert audio file to target format."""

    def normalize(self, file_path: Path, target_lufs: float = -14.0) -> Path:
        """Normalize audio to target loudness."""

class AudioAnalysis:
    """Result of audio analysis."""
    bpm: float
    key: str
    duration: float
    sample_rate: int
    channels: int
```

#### 1.3 organizer.py

**Responsibilities:**
- File path generation based on metadata
- Playlist-based directory organization
- Backup management
- File movement and verification

**Key Classes:**
```python
class FileOrganizer:
    """Organize files into structured directories."""

    def get_output_path(self, track: TrackInfo, format: str) -> Path:
        """Generate output path for track."""

    def organize(self, source: Path, track: TrackInfo) -> OrganizeResult:
        """Move file to appropriate location."""

    def create_backups(self, source: Path, backup_dirs: List[Path]) -> List[Path]:
        """Create backup copies in specified directories."""
```

### 2. Integrations Module (`music_workflow/integrations/`)

#### 2.1 notion/client.py

**Responsibilities:**
- API authentication and error handling
- Rate limiting and retry logic
- Query building and pagination

**Key Classes:**
```python
class NotionClient:
    """Wrapper around Notion API."""

    def query_database(self, database_id: str, filter: Dict) -> List[Page]:
        """Query a Notion database."""

    def update_page(self, page_id: str, properties: Dict) -> Page:
        """Update a Notion page."""

    def create_page(self, database_id: str, properties: Dict) -> Page:
        """Create a new page in database."""
```

#### 2.2 eagle/client.py

**Responsibilities:**
- Eagle library API integration
- Image/file import
- Tag and folder management

**Key Classes:**
```python
class EagleClient:
    """Wrapper around Eagle API."""

    def import_file(self, file_path: Path, metadata: Dict) -> str:
        """Import file to Eagle library."""

    def search(self, query: str) -> List[EagleItem]:
        """Search Eagle library."""

    def add_tags(self, item_id: str, tags: List[str]) -> bool:
        """Add tags to Eagle item."""
```

### 3. Deduplication Module (`music_workflow/deduplication/`)

#### 3.1 fingerprint.py

**Responsibilities:**
- Generate audio fingerprints
- Compare fingerprints for similarity
- Cache fingerprints for performance

**Key Classes:**
```python
class FingerprintGenerator:
    """Generate and compare audio fingerprints."""

    def generate(self, file_path: Path) -> AudioFingerprint:
        """Generate fingerprint for audio file."""

    def compare(self, fp1: AudioFingerprint, fp2: AudioFingerprint) -> float:
        """Compare two fingerprints, return similarity score (0-1)."""

class AudioFingerprint:
    """Representation of audio fingerprint."""
    hash: str
    duration: float
    signature: bytes
```

#### 3.2 matcher.py

**Responsibilities:**
- Multi-source duplicate detection
- Match scoring and ranking
- Conflict resolution

**Key Classes:**
```python
class DuplicateMatcher:
    """Match potential duplicates across sources."""

    def find_matches(self, track: TrackInfo) -> List[Match]:
        """Find potential matches for track."""

    def resolve(self, matches: List[Match]) -> Resolution:
        """Resolve which version to keep."""
```

### 4. Metadata Module (`music_workflow/metadata/`)

#### 4.1 enrichment.py

**Responsibilities:**
- Fetch metadata from Spotify API
- Fetch metadata from other sources
- Merge and prioritize metadata sources

**Key Classes:**
```python
class MetadataEnricher:
    """Enrich track metadata from external sources."""

    def enrich_from_spotify(self, track: TrackInfo) -> TrackInfo:
        """Enrich track with Spotify metadata."""

    def merge_metadata(self, sources: List[Dict]) -> Dict:
        """Merge metadata from multiple sources."""
```

---

## Interface Contracts

### TrackInfo

The central data structure passed between modules:

```python
@dataclass
class TrackInfo:
    """Represents a music track with all metadata."""
    # Identifiers
    id: str
    notion_page_id: Optional[str] = None
    spotify_id: Optional[str] = None
    soundcloud_url: Optional[str] = None

    # Basic metadata
    title: str
    artist: str
    album: Optional[str] = None
    duration: Optional[float] = None

    # Audio analysis
    bpm: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[float] = None

    # File information
    source_url: Optional[str] = None
    file_paths: Dict[str, Path] = field(default_factory=dict)

    # Organization
    playlist: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Status
    processed: bool = False
    eagle_id: Optional[str] = None
```

### Error Classes

```python
class MusicWorkflowError(Exception):
    """Base exception for music workflow."""

class DownloadError(MusicWorkflowError):
    """Error during download."""

class ProcessingError(MusicWorkflowError):
    """Error during audio processing."""

class IntegrationError(MusicWorkflowError):
    """Error with external service integration."""

class DuplicateFoundError(MusicWorkflowError):
    """Track is a duplicate."""
    existing_track: TrackInfo
```

---

## Migration Strategy

### Phase 1: Extract Utilities (1-2 sessions)

1. Create `music_workflow/utils/` module
2. Extract logging utilities from monolithic script
3. Extract file operation utilities
4. Extract error classes
5. Create tests for utilities

### Phase 2: Extract Integrations (2-3 sessions)

1. Create `music_workflow/integrations/notion/` module
2. Create `music_workflow/integrations/eagle/` module
3. Create `music_workflow/integrations/spotify/` module
4. Add integration tests

### Phase 3: Extract Core Logic (3-4 sessions)

1. Create `music_workflow/core/downloader.py`
2. Create `music_workflow/core/processor.py`
3. Create `music_workflow/core/organizer.py`
4. Add comprehensive unit tests

### Phase 4: Extract Deduplication (1-2 sessions)

1. Create `music_workflow/deduplication/` module
2. Extract fingerprinting logic
3. Extract matching logic
4. Add deduplication tests

### Phase 5: Create Unified CLI (1-2 sessions)

1. Create `music_workflow/cli/main.py`
2. Implement all commands
3. Add feature flags for gradual migration
4. Documentation and help text

### Phase 6: Deprecate Monolithic (1 session)

1. Route all calls through modular implementation
2. Remove feature flags
3. Archive monolithic script
4. Update documentation

---

## Testing Strategy

### Unit Tests

- Each module has corresponding test file
- Mock external dependencies
- Cover edge cases and error conditions
- Target: 80%+ coverage

### Integration Tests

- Test module interactions
- Test with real (sandboxed) external services
- Verify data flow between modules

### End-to-End Tests

- Full workflow execution
- Compare results with monolithic implementation
- Performance benchmarks

---

## Configuration Management

### Environment Variables

```bash
# Core settings
MUSIC_WORKFLOW_USE_MODULAR=true
MUSIC_WORKFLOW_LOG_LEVEL=INFO

# Feature flags (gradual rollout)
MUSIC_WORKFLOW_MODULAR_DOWNLOAD=true
MUSIC_WORKFLOW_MODULAR_PROCESS=true
MUSIC_WORKFLOW_MODULAR_DEDUP=true
MUSIC_WORKFLOW_MODULAR_INTEGRATE=true

# Fallback settings
MUSIC_WORKFLOW_FALLBACK_TO_MONOLITHIC=true
```

### Configuration File (music_workflow.yaml)

```yaml
workflow:
  use_modular: true
  fallback_to_monolithic: true

modules:
  download:
    enabled: true
    default_formats: [m4a, aiff, wav]
    max_retries: 3

  process:
    enabled: true
    target_lufs: -14.0
    analyze_bpm: true
    analyze_key: true

  deduplication:
    enabled: true
    fingerprint_threshold: 0.95
    check_notion: true
    check_eagle: true

integrations:
  notion:
    timeout: 30
    max_retries: 3

  eagle:
    library_path: /Volumes/VIBES/Music-Library-2.library

  spotify:
    enrich_metadata: true
```

---

## Dependencies

### Required Libraries

```
# Core
click>=8.0
pydantic>=2.0
pyyaml>=6.0

# Audio
yt-dlp>=2023.0
librosa>=0.10.0
mutagen>=1.45.0
pydub>=0.25.0

# Integrations
notion-client>=2.0
spotipy>=2.0
httpx>=0.24.0

# Testing
pytest>=7.0
pytest-cov>=4.0
pytest-asyncio>=0.21.0
responses>=0.23.0
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Test Coverage | > 80% |
| Module Dependencies | < 5 per module |
| Average Function Length | < 30 lines |
| Cyclomatic Complexity | < 10 per function |
| Documentation Coverage | > 90% |
| Build Time | < 30 seconds |
| Full Workflow Time | < 60 seconds |

---

## Next Steps

1. [ ] Review and approve modularized design
2. [ ] Set up package structure and tooling
3. [ ] Begin Phase 1: Extract utilities
4. [ ] Create test fixtures and mocks
5. [ ] Document API interfaces

---

**Document Status:** DRAFT
**Requires:** Review and approval before implementation
**Created During:** Plans Directory Audit 2026-01-08
