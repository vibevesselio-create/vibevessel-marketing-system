# Multi-Environment Image Synchronization Architecture

**Version:** 1.0
**Date:** 2026-01-18
**Author:** Claude Code Agent

---

## Executive Summary

This document outlines a technically optimized architecture for synchronizing and managing images across multiple environments:

1. **Adobe Lightroom Classic** (local catalog + cloud sync)
2. **Google Drive** (cloud storage + backup)
3. **Eagle Library** (local DAM with metadata)
4. **Notion Photo Library** (metadata database + workflow integration)

The core challenge is that each environment treats images differently:
- Lightroom: Master catalog with non-destructive edits, cloud sync
- Google Drive: File-based storage with sync
- Eagle: Asset management with tags and collections
- Notion: Metadata database with workflow properties

---

## Core Design Principles

### 1. Single Source of Truth (SSOT) for Identity

Every image needs a **Universal Image Identifier (UII)** that persists across all environments:

```
UII = SHA256(original_file_bytes)[:16]
```

This fingerprint-based ID:
- Survives file renames
- Works across environments
- Detects true duplicates
- Handles format conversions (original vs processed)

### 2. Master Location Hierarchy

Define a clear hierarchy for "master" status:

```
Priority 1: Local Original RAW/DNG file
Priority 2: Lightroom Cloud (if local not available)
Priority 3: Google Drive backup
Priority 4: Eagle Library copy
```

### 3. Metadata Aggregation, Not Duplication

Each environment excels at different metadata:
- **Lightroom**: Develop settings, ratings, color labels, GPS
- **Eagle**: Tags, projects, usage tracking
- **Google Drive**: Sharing, versions, comments
- **Notion**: Workflow status, client assignments, publication history

**Strategy**: Aggregate metadata INTO Notion as the unified view, but don't try to sync metadata BACK to source systems.

---

## Technical Architecture

### Central Sync Database Schema

```sql
-- Universal Image Registry
CREATE TABLE images (
    uii TEXT PRIMARY KEY,           -- Universal Image Identifier (SHA256 fingerprint)
    original_filename TEXT,
    original_extension TEXT,
    file_size_bytes INTEGER,
    capture_date TEXT,

    -- Location References (nullable - image may not exist in all environments)
    lightroom_id TEXT,              -- Lightroom id_global
    lightroom_catalog TEXT,         -- Which catalog
    eagle_id TEXT,                  -- Eagle image ID
    google_drive_id TEXT,           -- Drive file ID
    notion_page_id TEXT,            -- Notion page ID

    -- Master Location
    master_location TEXT,           -- 'local'|'lightroom_cloud'|'google_drive'|'eagle'
    master_path TEXT,               -- Full path to master file

    -- Sync Metadata
    last_sync_timestamp TEXT,
    sync_status TEXT,               -- 'synced'|'pending'|'conflict'|'orphaned'

    UNIQUE(lightroom_id),
    UNIQUE(eagle_id),
    UNIQUE(google_drive_id)
);

-- Environment-Specific Metadata
CREATE TABLE lightroom_metadata (
    uii TEXT PRIMARY KEY REFERENCES images(uii),
    rating INTEGER,
    color_label TEXT,
    pick_status INTEGER,
    develop_preset TEXT,
    collections TEXT,               -- JSON array
    keywords TEXT,                  -- JSON array
    gps_latitude REAL,
    gps_longitude REAL,
    camera_model TEXT,
    lens_model TEXT,
    aperture REAL,
    shutter_speed TEXT,
    iso INTEGER,
    focal_length REAL,
    last_updated TEXT
);

CREATE TABLE eagle_metadata (
    uii TEXT PRIMARY KEY REFERENCES images(uii),
    tags TEXT,                      -- JSON array
    folders TEXT,                   -- JSON array
    annotation TEXT,
    star_rating INTEGER,
    color TEXT,
    url TEXT,
    last_updated TEXT
);

CREATE TABLE google_drive_metadata (
    uii TEXT PRIMARY KEY REFERENCES images(uii),
    file_id TEXT,
    parent_folder_id TEXT,
    shared_with TEXT,               -- JSON array
    web_view_link TEXT,
    thumbnail_link TEXT,
    version INTEGER,
    last_updated TEXT
);

-- Notion Unified View (aggregated from all sources)
CREATE TABLE notion_sync_queue (
    uii TEXT PRIMARY KEY REFERENCES images(uii),
    pending_properties TEXT,        -- JSON of properties to update
    last_attempt TEXT,
    attempt_count INTEGER DEFAULT 0,
    status TEXT                     -- 'pending'|'synced'|'failed'
);

-- Conflict Resolution Log
CREATE TABLE sync_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uii TEXT REFERENCES images(uii),
    conflict_type TEXT,             -- 'duplicate'|'missing_master'|'metadata_mismatch'
    source_a TEXT,
    source_b TEXT,
    resolution TEXT,
    resolved_at TEXT,
    resolved_by TEXT
);
```

### Fingerprint-Based Identity Resolution

```python
import hashlib
from pathlib import Path

def compute_image_fingerprint(file_path: Path, chunk_size: int = 8192) -> str:
    """
    Compute a stable fingerprint for an image file.
    Uses SHA256 of file contents, truncated to 16 chars for readability.
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()[:16]

def compute_perceptual_hash(file_path: Path) -> str:
    """
    Compute perceptual hash for finding visually similar images.
    Survives format conversions, minor edits, and resizing.
    """
    import imagehash
    from PIL import Image

    with Image.open(file_path) as img:
        return str(imagehash.average_hash(img))
```

### Sync Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHANGE DETECTION LAYER                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Lightroom   │  │    Eagle     │  │ Google Drive │  │   Notion    │ │
│  │   Watcher    │  │   Watcher    │  │   Watcher    │  │   Webhook   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                 │                 │         │
│         ▼                 ▼                 ▼                 ▼         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      EVENT QUEUE (Redis/SQLite)                  │  │
│  │   {source: "lightroom", type: "image_added", id: "...", ts: ...} │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                    │                                    │
└────────────────────────────────────┼────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        IDENTITY RESOLUTION LAYER                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Compute fingerprint (UII) for new/changed image                     │
│  2. Check if UII exists in central registry                             │
│  3. If new: Create registry entry, determine master location            │
│  4. If existing: Update environment reference, detect conflicts         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        METADATA AGGREGATION LAYER                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Extract metadata from source environment                            │
│  2. Merge with existing metadata (source-specific tables)               │
│  3. Apply aggregation rules to build unified Notion view                │
│  4. Queue Notion update if changed                                      │
│                                                                         │
│  Aggregation Rules:                                                     │
│  - Rating: MAX(lightroom.rating, eagle.star_rating)                     │
│  - Tags: UNION(lightroom.keywords, eagle.tags)                          │
│  - GPS: COALESCE(lightroom.gps, exif.gps)                              │
│  - Status: Notion-managed (not overwritten by sources)                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           NOTION SYNC LAYER                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. Process sync queue in batches (rate-limited)                        │
│  2. Find or create Notion page by UII                                   │
│  3. Update properties with aggregated metadata                          │
│  4. Preserve Notion-only properties (workflow status, assignments)      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Components

### 1. Environment Watchers

#### Lightroom Catalog Watcher
```python
class LightroomCatalogWatcher:
    """Monitor Lightroom catalog for changes."""

    def __init__(self, catalog_path: str, poll_interval: int = 300):
        self.catalog_path = catalog_path
        self.poll_interval = poll_interval
        self.last_check = None

    def get_changes_since(self, since_timestamp: str) -> List[Dict]:
        """Query catalog for images modified since timestamp."""
        conn = sqlite3.connect(f"file:{self.catalog_path}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Lightroom stores touchTime as epoch seconds
        cursor.execute("""
            SELECT id_local, id_global, touchTime
            FROM Adobe_images
            WHERE touchTime > ?
        """, (since_timestamp,))

        return [{'id': row[1], 'modified': row[2]} for row in cursor.fetchall()]
```

#### Eagle Library Watcher
```python
class EagleLibraryWatcher:
    """Monitor Eagle library for changes via SQLite."""

    def get_changes_since(self, since_timestamp: str) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, modificationTime
            FROM images
            WHERE modificationTime > ?
        """, (since_timestamp,))

        return [{'id': row[0], 'modified': row[1]} for row in cursor.fetchall()]
```

#### Google Drive Watcher
```python
class GoogleDriveWatcher:
    """Monitor Google Drive folder for changes via API."""

    def get_changes_since(self, start_page_token: str) -> List[Dict]:
        changes = []
        page_token = start_page_token

        while page_token:
            response = self.drive_service.changes().list(
                pageToken=page_token,
                spaces='drive',
                fields='nextPageToken, newStartPageToken, changes(fileId, file(name, mimeType, modifiedTime))'
            ).execute()

            for change in response.get('changes', []):
                if self._is_image(change.get('file', {}).get('mimeType', '')):
                    changes.append({
                        'id': change['fileId'],
                        'file': change.get('file')
                    })

            page_token = response.get('nextPageToken')

        return changes
```

### 2. Identity Resolution Service

```python
class ImageIdentityResolver:
    """Resolve image identity across environments."""

    def __init__(self, registry_db: str):
        self.conn = sqlite3.connect(registry_db)

    def register_image(self,
                       file_path: str,
                       source: str,
                       source_id: str) -> str:
        """
        Register an image from any source environment.
        Returns the Universal Image Identifier (UII).
        """
        # Compute fingerprint
        uii = compute_image_fingerprint(Path(file_path))

        # Check if already registered
        cursor = self.conn.cursor()
        cursor.execute("SELECT uii FROM images WHERE uii = ?", (uii,))
        existing = cursor.fetchone()

        if existing:
            # Update source reference
            self._update_source_reference(uii, source, source_id)
            return uii

        # New image - create registry entry
        cursor.execute("""
            INSERT INTO images (uii, original_filename, original_extension,
                                master_location, master_path, last_sync_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            uii,
            Path(file_path).stem,
            Path(file_path).suffix,
            source,
            file_path,
            datetime.now().isoformat()
        ))

        self._update_source_reference(uii, source, source_id)
        self.conn.commit()

        return uii

    def find_by_source(self, source: str, source_id: str) -> Optional[str]:
        """Find UII by source environment ID."""
        column = f"{source}_id"
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT uii FROM images WHERE {column} = ?", (source_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    def detect_duplicates(self, uii: str) -> List[Dict]:
        """Detect copies of an image across environments."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT lightroom_id, eagle_id, google_drive_id, notion_page_id
            FROM images WHERE uii = ?
        """, (uii,))

        row = cursor.fetchone()
        if not row:
            return []

        locations = []
        if row[0]: locations.append({'source': 'lightroom', 'id': row[0]})
        if row[1]: locations.append({'source': 'eagle', 'id': row[1]})
        if row[2]: locations.append({'source': 'google_drive', 'id': row[2]})
        if row[3]: locations.append({'source': 'notion', 'id': row[3]})

        return locations
```

### 3. Metadata Aggregation Service

```python
class MetadataAggregator:
    """Aggregate metadata from all sources into unified view."""

    AGGREGATION_RULES = {
        'rating': 'max',           # Take highest rating
        'tags': 'union',           # Combine all tags
        'gps': 'first_non_null',   # Take first available
        'camera_model': 'first_non_null',
        'capture_date': 'first_non_null',
    }

    def aggregate_for_notion(self, uii: str) -> Dict[str, Any]:
        """Build unified Notion properties from all sources."""

        lr_meta = self._get_lightroom_metadata(uii)
        eagle_meta = self._get_eagle_metadata(uii)
        drive_meta = self._get_drive_metadata(uii)

        properties = {}

        # Rating (max of all sources)
        ratings = [lr_meta.get('rating'), eagle_meta.get('star_rating')]
        ratings = [r for r in ratings if r is not None]
        if ratings:
            properties['Rating'] = {'number': max(ratings)}

        # Tags (union of all sources)
        all_tags = set()
        if lr_meta.get('keywords'):
            all_tags.update(lr_meta['keywords'])
        if eagle_meta.get('tags'):
            all_tags.update(eagle_meta['tags'])
        if all_tags:
            properties['Tags'] = {
                'multi_select': [{'name': tag} for tag in list(all_tags)[:100]]
            }

        # GPS (prefer Lightroom, fallback to EXIF)
        if lr_meta.get('gps_latitude') and lr_meta.get('gps_longitude'):
            properties['GPS'] = {
                'rich_text': [{
                    'text': {'content': f"{lr_meta['gps_latitude']}, {lr_meta['gps_longitude']}"}
                }]
            }

        # Camera info
        if lr_meta.get('camera_model'):
            properties['Camera Model'] = {
                'rich_text': [{'text': {'content': lr_meta['camera_model']}}]
            }

        # Collections (from Lightroom)
        if lr_meta.get('collections'):
            properties['Collections'] = {
                'multi_select': [{'name': c} for c in lr_meta['collections'][:100]]
            }

        # Source locations for reference
        properties['Lightroom ID'] = {
            'rich_text': [{'text': {'content': lr_meta.get('id', '') or ''}}]
        }
        properties['Eagle ID'] = {
            'rich_text': [{'text': {'content': eagle_meta.get('id', '') or ''}}]
        }
        properties['Google Drive ID'] = {
            'rich_text': [{'text': {'content': drive_meta.get('file_id', '') or ''}}]
        }

        return properties
```

---

## Conflict Resolution

### Conflict Types

1. **Duplicate Detection**: Same image exists in multiple locations
   - Resolution: Register all locations, designate master based on hierarchy

2. **Metadata Mismatch**: Different ratings/tags in different environments
   - Resolution: Use aggregation rules (max rating, union tags)

3. **Missing Master**: Image referenced but master file not found
   - Resolution: Search other locations, update master_location

4. **Orphaned Reference**: Environment reference exists but image deleted
   - Resolution: Mark as orphaned, queue for cleanup review

### Conflict Resolution Flow

```python
class ConflictResolver:
    """Handle sync conflicts between environments."""

    def resolve_duplicate(self, uii: str, locations: List[Dict]) -> Dict:
        """
        Resolve duplicate by selecting master based on hierarchy.
        """
        priority = ['local', 'lightroom_cloud', 'google_drive', 'eagle']

        for p in priority:
            for loc in locations:
                if loc['source'] == p:
                    return {
                        'resolution': 'master_selected',
                        'master': loc,
                        'copies': [l for l in locations if l != loc]
                    }

        return {'resolution': 'no_master', 'locations': locations}

    def resolve_metadata_mismatch(self, uii: str,
                                   lr_meta: Dict,
                                   eagle_meta: Dict) -> Dict:
        """
        Resolve metadata conflicts using aggregation rules.
        """
        # Metadata aggregation is non-destructive - we just take the "best" value
        # for display in Notion, but don't modify source environments
        return {
            'resolution': 'aggregated',
            'aggregated_rating': max(
                lr_meta.get('rating', 0) or 0,
                eagle_meta.get('star_rating', 0) or 0
            ),
            'aggregated_tags': list(set(
                (lr_meta.get('keywords') or []) +
                (eagle_meta.get('tags') or [])
            ))
        }
```

---

## Implementation Phases

### Phase 1: Central Registry (Week 1-2)
1. Create sync database with schema
2. Implement fingerprint computation
3. Build Lightroom catalog reader
4. Initial bulk import of Lightroom catalog

### Phase 2: Environment Watchers (Week 3-4)
1. Lightroom catalog watcher (polling)
2. Eagle library watcher (polling)
3. Google Drive watcher (API-based)
4. Event queue implementation

### Phase 3: Metadata Aggregation (Week 5-6)
1. Lightroom metadata extraction
2. Eagle metadata extraction
3. Aggregation rules engine
4. Notion property mapping

### Phase 4: Notion Integration (Week 7-8)
1. Notion sync queue processor
2. Batch update optimization
3. Conflict resolution UI
4. Status dashboard

### Phase 5: Production Hardening (Week 9-10)
1. Error handling and retry logic
2. Performance optimization
3. Monitoring and alerting
4. Documentation and runbooks

---

## Configuration

```yaml
# config/image_sync.yaml

# Environment sources
sources:
  lightroom:
    enabled: true
    catalog_path: /Volumes/SYSTEM_SSD/master-lightroom-2/Master_Lightroom.lrcat
    poll_interval_seconds: 300

  eagle:
    enabled: true
    library_path: /Users/brianhellemn/Pictures/SEREN_Assets_Library.library
    poll_interval_seconds: 300

  google_drive:
    enabled: true
    folder_id: "root"
    credentials_path: ~/.credentials/google-drive.json
    watch_folders:
      - "VibeVessel/Photos"
      - "OF Content"

  notion:
    enabled: true
    database_id: "223e7361-6c27-8157-840c-000ba533ca02"
    token_env: "NOTION_ARCHIVE_TOKEN"

# Sync settings
sync:
  batch_size: 50
  rate_limit_per_second: 3
  retry_max_attempts: 3
  retry_backoff_seconds: 5

# Master location priority
master_priority:
  - local_raw
  - lightroom_cloud
  - google_drive
  - eagle

# Aggregation rules
aggregation:
  rating: max
  tags: union
  gps: first_non_null
  camera: first_non_null

# Notion property mapping
notion_properties:
  title: "Name"
  rating: "Rating"
  tags: "Tags"
  gps: "GPS Location"
  camera: "Camera Model"
  lens: "Lens"
  aperture: "Aperture"
  iso: "ISO"
  shutter: "Shutter Speed"
  collections: "Collections"
  lightroom_id: "Lightroom ID"
  eagle_id: "Eagle ID"
  drive_id: "Google Drive ID"
  fingerprint: "Image Fingerprint"
  master_location: "Master Location"
```

---

## Key Technical Decisions

### 1. Why SHA256 Fingerprint for Identity?
- **Survives renames**: File name changes don't break identity
- **Cross-platform**: Works regardless of source environment
- **Duplicate detection**: Automatically identifies exact copies
- **Efficient**: Can be computed incrementally for large files

### 2. Why Notion as Aggregation Target (Not Source)?
- **Single source of truth for workflow**: Notion manages assignments, status, publication
- **Non-destructive**: Source environments keep their native metadata
- **Flexible**: Easy to change aggregation rules without affecting sources
- **Queryable**: Notion provides powerful filtering and views

### 3. Why Polling Instead of Webhooks for Local Sources?
- **Lightroom**: No webhook support, SQLite is local
- **Eagle**: No webhook support, SQLite is local
- **Google Drive**: Uses Change API (event-driven where possible)
- **Polling interval**: 5 minutes balances freshness vs resource usage

### 4. Why Not Bi-Directional Sync?
- **Complexity**: Bi-directional sync creates race conditions and conflicts
- **Data loss risk**: Overwriting source metadata is dangerous
- **Purpose mismatch**: Each environment has different purposes
- **Solution**: Aggregation is read-only from sources, write-only to Notion

---

## Appendix: Database IDs

| Environment | Database/Location | ID |
|-------------|------------------|-----|
| Notion Photo Library | VibeVessel-Automation | `223e7361-6c27-8157-840c-000ba533ca02` |
| Lightroom Master | SYSTEM_SSD | `/Volumes/SYSTEM_SSD/master-lightroom-2/Master_Lightroom.lrcat` |
| Eagle Library | Pictures | `/Users/brianhellemn/Pictures/SEREN_Assets_Library.library` |
| Google Drive | VibeVessel | `vibe.vessel.io@gmail.com` |
| Central Sync DB | Google Drive | `Google Drive/VibeVessel/Databases/image_sync_registry.db` |

---

*Document generated by Claude Code Agent - 2026-01-18*
