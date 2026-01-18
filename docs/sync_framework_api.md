# Sync Framework API Documentation

## Overview

The sync framework provides modular, reusable components for synchronizing data to Notion. All components are parameterized by item-type configuration from the item-types database.

## Core Modules

### Fingerprinting (`sync_framework/core/fingerprinting.py`)

#### `FingerprintEngine`

Generic fingerprint computation for all file types.

```python
from sync_framework.core.fingerprinting import get_fingerprint_engine

engine = get_fingerprint_engine()
fingerprint = engine.compute_fingerprint(file_path, item_type)
similarity = engine.compare_fingerprints(fp1, fp2)
```

**Methods:**
- `compute_fingerprint(file_path, item_type, use_cache=True) -> FileFingerprint`
- `compute_content_hash(content: bytes) -> str`
- `compare_fingerprints(fp1, fp2) -> float`

### Deduplication (`sync_framework/core/deduplication.py`)

#### `DeduplicationEngine`

Parameterized deduplication engine.

```python
from sync_framework.core.deduplication import DeduplicationEngine

engine = DeduplicationEngine(item_type, item_type_config)
matches = engine.find_duplicates(item, existing_items, file_path)
is_dup, match = engine.is_duplicate(item, existing_items, file_path)
merged = engine.merge_duplicates([item1, item2])
```

**Methods:**
- `find_duplicates(item, existing_items, file_path=None) -> List[DuplicateMatch]`
- `is_duplicate(item, existing_items, file_path=None) -> Tuple[bool, Optional[DuplicateMatch]]`
- `merge_duplicates(items) -> Dict[str, Any]`

### Database Router (`sync_framework/core/database_router.py`)

#### `DatabaseRouter`

Routes items to appropriate Notion databases.

```python
from sync_framework.core.database_router import DatabaseRouter

router = DatabaseRouter()
database_ids = router.route_item(item, item_type, source_path, category)
primary_db = router.get_primary_database(item_type, source_path)
```

**Methods:**
- `route_item(item, item_type, source_path=None, category=None) -> List[str]`
- `get_primary_database(item_type, source_path=None) -> Optional[str]`

### Schema Validator (`sync_framework/core/schema_validator.py`)

#### `SchemaValidator`

Validates schemas and items against item-type requirements.

```python
from sync_framework.core.schema_validator import SchemaValidator

validator = SchemaValidator()
is_valid = validator.validate_and_repair(database_id, item_type, notion_client)
is_valid, errors = validator.validate_item(item, item_type)
required = validator.get_required_properties(item_type)
defaults = validator.get_default_values(item_type)
```

**Methods:**
- `validate_and_repair(database_id, item_type, notion_client=None) -> bool`
- `validate_item(item, item_type) -> Tuple[bool, List[str]]`
- `get_required_properties(item_type) -> List[str]`
- `get_default_values(item_type) -> Dict[str, Any]`

### Sync Orchestrator (`sync_framework/core/sync_orchestrator.py`)

#### `SyncOrchestrator`

Full sync workflow orchestrator.

```python
from sync_framework.core.sync_orchestrator import SyncOrchestrator

orchestrator = SyncOrchestrator(item_type, source_adapter, destination_adapter)
result = orchestrator.sync(items=None, source_path=None)
```

**Methods:**
- `sync(items=None, source_path=None) -> SyncResult`

**SyncResult:**
- `success: bool`
- `items_processed: int`
- `items_created: int`
- `items_updated: int`
- `items_skipped: int`
- `items_failed: int`
- `errors: List[str]`

## Adapters

### Notion Adapter (`sync_framework/adapters/notion_adapter.py`)

```python
from sync_framework.adapters.notion_adapter import NotionAdapter

adapter = NotionAdapter(notion_token, rate_limit_delay=0.1)
result = adapter.create_or_update_item(item, database_id, item_type)
existing = adapter.get_existing_items(item_type)
```

### Filesystem Adapter (`sync_framework/adapters/filesystem_adapter.py`)

```python
from sync_framework.adapters.filesystem_adapter import FilesystemAdapter

adapter = FilesystemAdapter(supported_extensions=[".mp3", ".m4a"])
items = adapter.discover_items(source_path, item_type)
```

### Eagle Adapter (`sync_framework/adapters/eagle_adapter.py`)

```python
from sync_framework.adapters.eagle_adapter import EagleAdapter

adapter = EagleAdapter(eagle_api_url="http://localhost:41595")
items = adapter.discover_items(source_path, item_type)
```

## Item-Types Manager

### `ItemTypesManager`

```python
from sync_config.item_types_manager import get_item_types_manager

manager = get_item_types_manager()
db_id = manager.get_database_for_item_type("Music Track")
config = manager.get_item_type_config("Music Track")
rules = manager.get_validation_rules("Music Track")
related_dbs = manager.get_related_databases("Music Track")
```

**Methods:**
- `get_database_for_item_type(item_type_name) -> Optional[str]`
- `get_item_type_config(item_type_name) -> Optional[ItemTypeConfig]`
- `get_validation_rules(item_type_name) -> Dict[str, Any]`
- `get_related_databases(item_type_name) -> List[str]`
- `get_related_functions(item_type_name) -> List[str]`
- `get_related_scripts(item_type_name) -> List[str]`
- `list_all_item_types() -> List[str]`
- `get_item_types_by_category(category) -> List[str]`
- `refresh_cache() -> None`

## Unified Config Functions

### `get_database_id()`

```python
from unified_config import get_database_id

db_id = get_database_id(
    item_type,
    source_path=None,
    category=None,
    fallback_db_id=None
)
```

### `get_item_type_config()`

```python
from unified_config import get_item_type_config

config = get_item_type_config(item_type)
```

### `get_validation_rules()`

```python
from unified_config import get_validation_rules

rules = get_validation_rules(item_type)
```

### `validate_item_properties()`

```python
from unified_config import validate_item_properties

is_valid, errors = validate_item_properties(item, item_type)
```

### `refresh_item_types_cache()`

```python
from unified_config import refresh_item_types_cache

refresh_item_types_cache()
```

## Error Handling

### `ConfigurationError`

Raised when database ID cannot be resolved.

```python
from unified_config import ConfigurationError, get_database_id

try:
    db_id = get_database_id("Unknown Type")
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Use fallback
    db_id = "fallback-id"
```

## Examples

See `docs/item_types_integration_guide.md` for complete usage examples.
