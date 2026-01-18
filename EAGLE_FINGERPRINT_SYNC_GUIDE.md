# How to Apply Fingerprints to Eagle Metadata

This guide explains how fingerprints are applied to Eagle metadata (tags) for each file.

---

## Overview

Fingerprints are stored in Eagle as **tags** in the format: `fingerprint:{sha256_hash}`

There are multiple ways to sync fingerprints to Eagle tags:

1. **During file import** - Automatic fingerprint extraction and tagging
2. **During batch embedding** - Syncs fingerprints after embedding in file metadata
3. **Standalone sync** - Sync existing fingerprints from file metadata to Eagle tags

---

## Method 1: Automatic During Import

When importing files to Eagle using the enhanced `EagleClient.import_file()` method, fingerprints are automatically extracted from file metadata and added as tags.

### Example:
```python
from music_workflow.integrations.eagle.client import get_eagle_client
from pathlib import Path

eagle_client = get_eagle_client()

# Import file - fingerprint will be automatically extracted and tagged
item_id = eagle_client.import_file(
    file_path=Path("/path/to/audio.m4a"),
    name="My Track",
    tags=["genre:electronic"],
    auto_sync_fingerprint=True  # Default: True
)

# Or explicitly provide fingerprint
item_id = eagle_client.import_file(
    file_path=Path("/path/to/audio.m4a"),
    fingerprint="6074e33c38dc9245b7628408925fe8d2...",
    auto_sync_fingerprint=False
)
```

---

## Method 2: Batch Fingerprint Embedding Script

The `batch_fingerprint_embedding.py` script embeds fingerprints in file metadata AND syncs them to Eagle tags in one operation.

### Usage:
```bash
# Dry run - see what would be processed
python scripts/batch_fingerprint_embedding.py --limit 10

# Execute - embed fingerprints and sync to Eagle tags
python scripts/batch_fingerprint_embedding.py --execute --limit 10

# Process all files (use with caution)
python scripts/batch_fingerprint_embedding.py --execute
```

### What it does:
1. Scans directories for audio files
2. Computes fingerprints for files without them
3. Embeds fingerprints in file metadata
4. **Automatically syncs fingerprints to Eagle tags** (if Eagle integration enabled)

---

## Method 3: Standalone Sync Script

The `sync_fingerprints_to_eagle.py` script syncs fingerprints from file metadata to Eagle tags for files that already have fingerprints embedded but missing Eagle tags.

### Usage:
```bash
# Dry run - see what would be synced
python scripts/sync_fingerprints_to_eagle.py

# Execute sync for all items
python scripts/sync_fingerprints_to_eagle.py --execute

# Sync first 100 items
python scripts/sync_fingerprints_to_eagle.py --execute --limit 100
```

### What it does:
1. Fetches all Eagle items
2. Checks each item for existing fingerprint tag
3. If no tag, extracts fingerprint from file metadata
4. Adds fingerprint tag to Eagle item

---

## Method 4: Manual Sync via Eagle Client

Use the `sync_fingerprint_tag()` method directly:

### Example:
```python
from music_workflow.integrations.eagle.client import get_eagle_client

eagle_client = get_eagle_client()

# Sync fingerprint tag for a specific item
success = eagle_client.sync_fingerprint_tag(
    item_id="eagle_item_id_here",
    fingerprint="6074e33c38dc9245b7628408925fe8d2...",
    force=False  # Set to True to replace existing tag
)
```

---

## Method 5: Direct API Call

Use the direct Eagle API if client is not available:

### Example:
```python
from scripts.music_library_remediation import eagle_update_tags

# Update tags for an Eagle item
success = eagle_update_tags(
    eagle_base="http://localhost:41595",
    eagle_token="your_token",
    item_id="eagle_item_id",
    tags=["existing_tag1", "existing_tag2", "fingerprint:6074e33c38dc9245..."]
)
```

---

## Fingerprint Tag Format

Fingerprints are stored in Eagle tags using this format:

```
fingerprint:{sha256_hash}
```

**Example:**
```
fingerprint:6074e33c38dc9245b7628408925fe8d2a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
```

**Important:**
- Tag is case-insensitive (lowercase hash recommended)
- Only one fingerprint tag per item (old tags are replaced if `force=True`)
- Hash is SHA-256 (64 hex characters)

---

## Workflow Recommendations

### For New Files:
1. **Use Method 1** - Import files with `auto_sync_fingerprint=True` (default)
   - Fingerprints are automatically extracted and tagged during import

### For Existing Files Without Fingerprints:
1. **Use Method 2** - Run `batch_fingerprint_embedding.py`
   - Computes fingerprints, embeds in metadata, and syncs to Eagle tags

### For Existing Files With Fingerprints in Metadata:
1. **Use Method 3** - Run `sync_fingerprints_to_eagle.py`
   - Syncs fingerprints from file metadata to Eagle tags

### For Individual Items:
1. **Use Method 4** - Use `sync_fingerprint_tag()` method
   - Quick sync for specific items

---

## Verification

### Check if an item has a fingerprint tag:
```python
from music_workflow.integrations.eagle.client import get_eagle_client

eagle_client = get_eagle_client()
item = eagle_client.get_item("item_id")

# Check for fingerprint tag
fp = eagle_client.get_fingerprint("item_id")
if fp:
    print(f"Fingerprint: {fp}")
else:
    print("No fingerprint tag found")
```

### Search items by fingerprint:
```python
from music_workflow.integrations.eagle.client import get_eagle_client

eagle_client = get_eagle_client()
fingerprint = "6074e33c38dc9245..."

# Find all items with this fingerprint
matching_items = eagle_client.search_by_fingerprint(fingerprint)
print(f"Found {len(matching_items)} items with fingerprint")
```

---

## Troubleshooting

### Issue: Fingerprint not syncing to Eagle
**Solutions:**
1. Check Eagle API is accessible: `eagle_client.is_available()`
2. Verify file path matches Eagle item path
3. Check file has fingerprint in metadata: `extract_fingerprint_from_metadata(file_path)`
4. Verify Eagle token/permissions

### Issue: Multiple fingerprint tags
**Solution:**
- Use `sync_fingerprint_tag()` with `force=True` to replace existing tags

### Issue: File not found in Eagle
**Solution:**
- Ensure file is imported to Eagle first
- Check file path matches exactly (case-sensitive on some systems)

---

## Best Practices

1. **Always verify** fingerprints are embedded in file metadata first
2. **Use dry-run mode** before executing large syncs
3. **Process in batches** for large libraries (100-1000 items at a time)
4. **Monitor errors** and review failed items
5. **Backup Eagle library** before large sync operations

---

## Summary

Fingerprints are applied to Eagle metadata as **tags** using the format `fingerprint:{hash}`. The recommended approach depends on your situation:

- **New imports:** Automatic via `import_file()` with `auto_sync_fingerprint=True`
- **Batch processing:** Use `batch_fingerprint_embedding.py`
- **Existing files:** Use `sync_fingerprints_to_eagle.py`
- **Individual items:** Use `sync_fingerprint_tag()` method

All methods ensure fingerprints are stored consistently in Eagle tags for reliable duplicate detection and library management.
