# How Fingerprints Are Applied to Eagle Metadata

## Quick Answer

Fingerprints are applied to Eagle metadata as **tags** using the format: `fingerprint:{sha256_hash}`

There are **5 methods** available:

---

## Method 1: Automatic During Import (Recommended for New Files)

**When to use:** Importing new files to Eagle

**How it works:**
- The enhanced `EagleClient.import_file()` method automatically extracts fingerprints from file metadata
- Fingerprint is added as a tag during import

**Code:**
```python
from music_workflow.integrations.eagle.client import get_eagle_client
from pathlib import Path

eagle_client = get_eagle_client()
item_id = eagle_client.import_file(
    file_path=Path("/path/to/audio.m4a"),
    auto_sync_fingerprint=True  # Default: True
)
```

---

## Method 2: Batch Fingerprint Embedding Script

**When to use:** Processing existing files that don't have fingerprints

**Command:**
```bash
python scripts/batch_fingerprint_embedding.py --execute --limit 100
```

**What it does:**
1. Computes fingerprints for files without them
2. Embeds fingerprints in file metadata
3. **Automatically syncs fingerprints to Eagle tags**

---

## Method 3: Standalone Sync Script (NEW)

**When to use:** Files already have fingerprints in metadata but missing Eagle tags

**Command:**
```bash
# Dry run first
python scripts/sync_fingerprints_to_eagle.py

# Execute sync
python scripts/sync_fingerprints_to_eagle.py --execute

# Limit to first 100 items
python scripts/sync_fingerprints_to_eagle.py --execute --limit 100
```

**What it does:**
1. Scans all Eagle items
2. Checks for existing fingerprint tags
3. Extracts fingerprints from file metadata for items without tags
4. Adds fingerprint tags to Eagle items

---

## Method 4: Manual Sync via Eagle Client

**When to use:** Syncing individual items programmatically

**Code:**
```python
from music_workflow.integrations.eagle.client import get_eagle_client

eagle_client = get_eagle_client()
success = eagle_client.sync_fingerprint_tag(
    item_id="eagle_item_id",
    fingerprint="6074e33c38dc9245...",
    force=False  # Set True to replace existing tag
)
```

---

## Method 5: Direct API Call

**When to use:** When Eagle client is not available

**Code:**
```python
from scripts.music_library_remediation import eagle_update_tags

success = eagle_update_tags(
    eagle_base="http://localhost:41595",
    eagle_token="your_token",
    item_id="item_id",
    tags=["fingerprint:6074e33c38dc9245..."]
)
```

---

## Fingerprint Tag Format

```
fingerprint:{sha256_hash}
```

**Example:**
```
fingerprint:6074e33c38dc9245b7628408925fe8d2a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6
```

**Important:**
- Tag is case-insensitive
- Only one fingerprint tag per item
- Hash is SHA-256 (64 hex characters)

---

## Recommended Workflow

### Scenario 1: New Files
→ **Use Method 1** (Automatic during import)

### Scenario 2: Existing Files Without Fingerprints
→ **Use Method 2** (Batch fingerprint embedding)

### Scenario 3: Existing Files With Fingerprints in Metadata
→ **Use Method 3** (Standalone sync script)

### Scenario 4: Individual Items
→ **Use Method 4** (Manual sync via client)

---

## Verification

Check if an item has a fingerprint tag:

```python
from music_workflow.integrations.eagle.client import get_eagle_client

eagle_client = get_eagle_client()
fp = eagle_client.get_fingerprint("item_id")
if fp:
    print(f"Fingerprint: {fp}")
```

Search items by fingerprint:

```python
matching_items = eagle_client.search_by_fingerprint("6074e33c38dc9245...")
print(f"Found {len(matching_items)} items")
```

---

## Summary

**Fingerprints are stored in Eagle as tags** in the format `fingerprint:{hash}`. Choose the method that fits your workflow:

- **New imports:** Method 1 (automatic)
- **Batch processing:** Method 2 (batch embedding)
- **Sync existing:** Method 3 (standalone sync)
- **Individual items:** Method 4 (manual sync)

All methods ensure consistent fingerprint storage for reliable duplicate detection.
