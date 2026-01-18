# Item-Types Database Integration Guide

## Overview

This guide explains how to use the item-types database as the centralized source of truth for all Notion synchronization workflows. The item-types database (ID: `26ce7361-6c27-8163-b29e-000be7d41128`) provides configuration for database routing, validation rules, and workflow parameters.

## Architecture

### Components

1. **Item-Types Manager** (`sync_config/item_types_manager.py`)
   - Queries and caches item-types database
   - Provides lookup functions for database IDs, validation rules, and related resources

2. **Unified Config Integration** (`unified_config.py`)
   - Extends unified config with item-types lookups
   - Provides `get_database_id()` with fallback hierarchy

3. **Sync Framework** (`sync_framework/`)
   - Modular deduplication, fingerprinting, and orchestration
   - Parameterized by item-type configuration

## Usage

### Basic Database Lookup

```python
from unified_config import get_database_id

# Get database ID for an item type
db_id = get_database_id("Music Track")
# Falls back to env vars or raises ConfigurationError if not found

# With fallback
db_id = get_database_id("Music Track", fallback_db_id="default-id")

# With source path for pattern matching
db_id = get_database_id("Music Track", source_path="/path/to/audio/file.mp3")
```

### Using Item-Type Configuration

```python
from unified_config import get_item_type_config, get_validation_rules

# Get full item-type configuration
config = get_item_type_config("Music Track")
print(config["default_sync_database_id"])
print(config["validation_rules"])

# Get validation rules only
rules = get_validation_rules("Music Track")
print(rules["population_requirements"])
print(rules["validation_rules"])
```

### Validating Items

```python
from unified_config import validate_item_properties

item = {
    "title": "My Track",
    "artist": "Artist Name"
}

is_valid, errors = validate_item_properties(item, "Music Track")
if not is_valid:
    print(f"Validation errors: {errors}")
```

### Using Sync Framework

```python
from sync_framework.core.sync_orchestrator import SyncOrchestrator
from sync_framework.adapters.filesystem_adapter import FilesystemAdapter
from sync_framework.adapters.notion_adapter import NotionAdapter

# Initialize adapters
source = FilesystemAdapter()
destination = NotionAdapter()

# Create orchestrator
orchestrator = SyncOrchestrator(
    item_type="Music Track",
    source_adapter=source,
    destination_adapter=destination
)

# Sync items
result = orchestrator.sync(source_path=Path("/path/to/music"))
print(f"Created: {result.items_created}, Updated: {result.items_updated}")
```

### Using Deduplication

```python
from sync_framework.core.deduplication import DeduplicationEngine
from sync_config.item_types_manager import get_item_types_manager

# Get item-type config
manager = get_item_types_manager()
config = manager.get_item_type_config("Music Track")
config_dict = {
    "validation_rules": config.validation_rules,
    "population_requirements": config.population_requirements
}

# Create deduplication engine
dedup = DeduplicationEngine("Music Track", config_dict)

# Find duplicates
item = {"title": "My Track", "artist": "Artist"}
existing_items = [...]  # List of existing items
matches = dedup.find_duplicates(item, existing_items, file_path=Path("track.mp3"))

# Check if duplicate
is_dup, match = dedup.is_duplicate(item, existing_items, file_path=Path("track.mp3"))
```

### Using Database Router

```python
from sync_framework.core.database_router import DatabaseRouter

router = DatabaseRouter()

# Route item to databases
item = {"title": "My Track"}
database_ids = router.route_item(
    item,
    item_type="Music Track",
    source_path="/path/to/track.mp3"
)

# Get primary database
primary_db = router.get_primary_database("Music Track", "/path/to/track.mp3")
```

## Migration Guide

### Step 1: Update Database ID Lookups

**Before:**
```python
TRACKS_DB_ID = "27ce7361-6c27-80fb-b40e-fefdd47d6640"
```

**After:**
```python
from unified_config import get_database_id
TRACKS_DB_ID = get_database_id("Music Track", fallback_db_id="27ce7361-6c27-80fb-b40e-fefdd47d6640")
```

### Step 2: Use Item-Type Configuration

Replace hardcoded validation logic with item-type-based validation:

```python
from unified_config import validate_item_properties

# Before: Manual validation
if not item.get("title"):
    raise ValueError("Title required")

# After: Item-type validation
is_valid, errors = validate_item_properties(item, "Music Track")
if not is_valid:
    raise ValueError(f"Validation failed: {errors}")
```

### Step 3: Migrate to Sync Framework (Optional)

For new workflows or major refactoring, use the sync framework:

```python
from sync_framework.core.sync_orchestrator import SyncOrchestrator
# ... (see usage examples above)
```

## Item-Types Database Schema

### Required Properties

- **Name**: Item type name (e.g., "Music Track", "PNG Format Image")
- **Default-Synchronization-Database**: Relation to target Notion database

### Configuration Properties

- **Variable-Namespace**: Namespace for configuration variables
- **Population-Requirements**: JSON with required fields and validation rules
- **Validation-Rules**: JSON with field-level validation rules
- **Template-Schema**: Schema template for items of this type
- **Default-Values**: Default property values

### Relations

- **DATABASES**: Related Notion databases
- **Functions**: Related functions
- **Scripts**: Related scripts
- **Prompts**: Related prompts
- **Tasks**: Related tasks
- **Workflows**: Related workflows

## Best Practices

1. **Always provide fallback database IDs** when using `get_database_id()` for backward compatibility
2. **Cache item-types lookups** - the manager automatically caches for 1 hour
3. **Use validation** - validate items before syncing to catch errors early
4. **Handle errors gracefully** - item-types lookups may fail, always have fallbacks
5. **Update item-types database** - ensure all item types have `Default-Synchronization-Database` set

## Troubleshooting

### Database ID Not Found

If `get_database_id()` raises `ConfigurationError`:
1. Check that the item type exists in the item-types database
2. Verify `Default-Synchronization-Database` is set for the item type
3. Provide a `fallback_db_id` parameter

### Item-Types Manager Not Available

If item-types manager fails to initialize:
1. Check Notion token is available
2. Verify item-types database ID is correct
3. Check network connectivity to Notion API
4. System will fall back to cached data or env vars

### Validation Failures

If validation fails:
1. Check `Population-Requirements` in item-types database
2. Verify required fields are present in item
3. Check `Validation-Rules` for field-specific requirements
