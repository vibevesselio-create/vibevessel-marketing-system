# Migration Guide: Item-Types Database Integration

This guide helps you migrate existing synchronization workflows to use the item-types database as the centralized configuration source.

## Migration Checklist

- [ ] Update database ID lookups to use `get_database_id()`
- [ ] Replace hardcoded validation with `validate_item_properties()`
- [ ] Update workflows to use item-type configuration
- [ ] Test with fallback database IDs
- [ ] Update item-types database with required configurations
- [ ] Document any custom item types

## Step-by-Step Migration

### 1. Music Track Sync Workflow

**Before:**
```python
TRACKS_DB_ID = os.getenv("TRACKS_DB_ID") or "27ce7361-6c27-80fb-b40e-fefdd47d6640"
```

**After:**
```python
from unified_config import get_database_id

TRACKS_DB_ID = get_database_id(
    "Music Track",
    fallback_db_id=os.getenv("TRACKS_DB_ID") or "27ce7361-6c27-80fb-b40e-fefdd47d6640"
)
```

### 2. Eagle to Notion Photo Sync

**Before:**
```python
PHOTO_LIBRARY_DATABASE_ID = "223e7361-6c27-8157-840c-000ba533ca02"
```

**After:**
```python
from unified_config import get_database_id

PHOTO_LIBRARY_DATABASE_ID = get_database_id(
    "PNG Format Image",  # Or "JPEG Format Image" based on file type
    fallback_db_id="223e7361-6c27-8157-840c-000ba533ca02"
)
```

### 3. Script Sync

**Before:**
```python
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"
```

**After:**
```python
from unified_config import get_database_id

SCRIPTS_DB_ID = get_database_id(
    "Python Script",  # Or "Google Apps Script", "JavaScript" based on file type
    fallback_db_id="26ce7361-6c27-8178-bc77-f43aff00eddf"
)
```

### 4. DaVinci Resolve Sync

**Before:**
```python
PROJECT_DB_ID = "20fe73616c278141b8e0f7865be6537e"
```

**After:**
```python
from unified_config import get_database_id

PROJECT_DB_ID = get_database_id(
    "Project",  # Or "Timeline", "Video Clip" based on item type
    fallback_db_id="20fe73616c278141b8e0f7865be6537e"
)
```

## Advanced Migration: Using Sync Framework

For workflows that need deduplication, fingerprinting, or complex orchestration:

### Before (Monolithic)

```python
def sync_track(track_data, file_path):
    # Hardcoded database ID
    db_id = "27ce7361-6c27-80fb-b40e-fefdd47d6640"
    
    # Manual deduplication
    existing = notion_client.databases.query(db_id, ...)
    if is_duplicate(track_data, existing):
        return
    
    # Manual fingerprinting
    fingerprint = compute_audio_fingerprint(file_path)
    
    # Create in Notion
    notion_client.pages.create(...)
```

### After (Modular)

```python
from sync_framework.core.sync_orchestrator import SyncOrchestrator
from sync_framework.adapters.filesystem_adapter import FilesystemAdapter
from sync_framework.adapters.notion_adapter import NotionAdapter

def sync_track(track_data, file_path):
    source = FilesystemAdapter()
    destination = NotionAdapter()
    
    orchestrator = SyncOrchestrator(
        item_type="Music Track",
        source_adapter=source,
        destination_adapter=destination
    )
    
    result = orchestrator.sync(source_path=Path(file_path))
    return result
```

## Item-Types Database Setup

### Required Configuration

For each item type in the item-types database:

1. **Set Default-Synchronization-Database**
   - Add relation to target Notion database
   - This is the primary database for items of this type

2. **Configure Population-Requirements** (JSON)
   ```json
   {
     "required_fields": ["title", "artist"],
     "required_properties": ["Name", "Artist"]
   }
   ```

3. **Configure Validation-Rules** (JSON)
   ```json
   {
     "field_rules": {
       "title": {
         "type": "string",
         "required": true,
         "min_length": 1,
         "max_length": 200
       }
     },
     "fingerprint_threshold": 0.95,
     "fuzzy_threshold": 0.85
   }
   ```

4. **Set Default-Values** (JSON)
   ```json
   {
     "status": "Active",
     "source": "sync_framework"
   }
   ```

## Testing Migration

1. **Test with fallback IDs**
   - Ensure workflows work when item-types lookup fails
   - Verify fallback database IDs are used correctly

2. **Test item-type lookups**
   - Verify correct database IDs are retrieved
   - Check that caching works properly

3. **Test validation**
   - Verify items are validated against item-type rules
   - Check that validation errors are handled gracefully

4. **Test sync framework** (if used)
   - Verify deduplication works correctly
   - Check fingerprinting for different file types
   - Test end-to-end sync workflow

## Rollback Plan

If issues occur:

1. **Temporary rollback**: Use `fallback_db_id` parameter
2. **Full rollback**: Revert to hardcoded database IDs
3. **Partial rollback**: Keep item-types integration but disable validation

## Common Issues

### Issue: Database ID Not Found

**Solution**: Ensure item type exists in item-types database and has `Default-Synchronization-Database` set. Always provide `fallback_db_id`.

### Issue: Validation Fails

**Solution**: Check `Population-Requirements` and `Validation-Rules` in item-types database. Ensure item data matches requirements.

### Issue: Item-Types Manager Not Available

**Solution**: Check Notion token, network connectivity. System will fall back to env vars or cached data.

## Next Steps

After migration:

1. Update item-types database with all item types
2. Configure validation rules for each type
3. Link related resources (databases, functions, scripts)
4. Document custom item types
5. Establish change control process for item-types database
