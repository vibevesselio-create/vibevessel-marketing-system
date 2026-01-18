# Eagle API Review & Implementation Updates

**Date:** 2026-01-12  
**Review Type:** Comprehensive API Documentation Review  
**Status:** Critical Findings - Implementation Updates Required

---

## Executive Summary

After comprehensive review of Eagle App API documentation and testing, **critical issues** have been identified that prevent direct file path retrieval for fingerprint embedding. The Eagle REST API does **NOT** return file paths for items, and items are stored in Eagle's internal library structure, not as direct file references.

---

## Key Findings from API Documentation Review

### 1. `/api/item/list` Endpoint Limitations

**Finding:** The `/api/item/list` endpoint does NOT include `path` attribute in response.

**Verified Response Structure:**
```json
{
  "id": "MKBAC8F1BAVW2",
  "name": "The Maelstrom",
  "size": 105479786,
  "ext": "wav",
  "tags": [...],
  "url": "",
  // NO "path" field
}
```

**Impact:** Cannot get file paths directly from list endpoint.

### 2. `/api/item/info` Endpoint Limitations

**Finding:** The `/api/item/info` endpoint also does NOT return `path` attribute.

**Correct Endpoint Format:**
- ✅ **GET** `/api/item/info?id={item_id}` (NOT POST)
- ❌ **POST** `/api/item/info` returns HTTP 405 (Method Not Allowed)

**Verified Response Structure:**
```json
{
  "status": "success",
  "data": {
    "id": "MKBAC8F1BAVW2",
    "name": "The Maelstrom",
    "ext": "wav",
    "tags": [...],
    "url": "",
    // NO "path" field
  }
}
```

**Impact:** Even detailed item info doesn't include file paths.

### 3. Eagle Library File Storage Architecture

**Finding:** Eagle stores files in its internal library structure:
- Library path: `/Volumes/VIBES/Music Library-2.library`
- Files stored in: `{library_path}/images/` or similar structure
- Metadata in: `{library_path}/metadata.db` (SQLite database)

**Impact:** Files are copied into Eagle library, original paths may not be preserved.

---

## Implementation Updates Required

### Update 1: Fix `/api/item/info` Endpoint Method

**Current Implementation (WRONG):**
```python
response = self._request("item/info", method="POST", data={"id": item_id})
```

**Correct Implementation:**
```python
response = self._request("item/info", method="GET", data={"id": item_id})
```

**File to Update:** `music_workflow/integrations/eagle/client.py` (line 336)

**Reason:** Eagle API requires GET with query parameter, not POST with body.

### Update 2: Construct File Paths from Library Structure

**Approach:** Since API doesn't return paths, construct them from library structure.

**Implementation Strategy:**
1. Get Eagle library path from configuration
2. Construct file path: `{library_path}/images/{item_id}.{ext}`
3. Verify file exists before processing
4. Fallback: Access SQLite database for actual file locations

**Code Update Needed:**
```python
def get_eagle_item_file_path(item_id: str, ext: str, library_path: Path) -> Optional[Path]:
    """Construct file path from Eagle library structure."""
    # Try standard location
    file_path = library_path / "images" / f"{item_id}.{ext}"
    if file_path.exists():
        return file_path
    
    # Try alternative locations
    for alt_dir in ["files", "assets", "media"]:
        alt_path = library_path / alt_dir / f"{item_id}.{ext}"
        if alt_path.exists():
            return alt_path
    
    # Fallback: Query SQLite database
    return get_file_path_from_db(item_id, library_path)
```

### Update 3: Access Eagle SQLite Database Directly

**Approach:** Query `metadata.db` to get actual file locations.

**Implementation:**
```python
import sqlite3

def get_file_path_from_db(item_id: str, library_path: Path) -> Optional[Path]:
    """Get file path from Eagle SQLite database."""
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        return None
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        # Query depends on Eagle's schema - needs investigation
        cursor.execute("SELECT filePath FROM items WHERE id = ?", (item_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            return Path(result[0])
    except Exception as e:
        logger.warning(f"Failed to query Eagle database: {e}")
    
    return None
```

### Update 4: Handle URL-Based Items

**Finding:** Many Eagle items are URL-based (imported from web) and don't have local file paths.

**Implementation:**
```python
def can_process_item(item: dict) -> bool:
    """Check if item can be processed for fingerprinting."""
    # Skip URL-based items
    if item.get("url") and not item.get("path"):
        return False
    
    # Skip items without file extensions
    if not item.get("ext"):
        return False
    
    return True
```

### Update 5: Batch Processing with Error Handling

**Implementation:**
```python
def process_eagle_items_with_paths(
    eagle_items: List[dict],
    library_path: Path,
    execute: bool = False
) -> Dict[str, Any]:
    """Process Eagle items, constructing paths from library structure."""
    stats = {
        "total": len(eagle_items),
        "with_paths": 0,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0
    }
    
    for item in eagle_items:
        item_id = item.get("id")
        ext = item.get("ext", "")
        
        if not item_id or not ext:
            stats["skipped"] += 1
            continue
        
        # Construct file path
        file_path = get_eagle_item_file_path(item_id, ext, library_path)
        
        if not file_path or not file_path.exists():
            stats["skipped"] += 1
            continue
        
        stats["with_paths"] += 1
        
        # Process file for fingerprinting
        if execute:
            try:
                # Embed fingerprint logic here
                stats["processed"] += 1
                stats["succeeded"] += 1
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Failed to process {item_id}: {e}")
    
    return stats
```

---

## Recommended Implementation Priority

### Priority 1: Fix API Method (Critical)
- **Update:** Change `item/info` from POST to GET
- **Impact:** Enables item detail retrieval
- **Effort:** 5 minutes
- **File:** `music_workflow/integrations/eagle/client.py`

### Priority 2: Construct File Paths (High)
- **Update:** Implement path construction from library structure
- **Impact:** Enables fingerprint embedding for library items
- **Effort:** 2-3 hours
- **Files:** `scripts/batch_fingerprint_embedding.py`, new utility function

### Priority 3: Database Access (Medium)
- **Update:** Query SQLite database for file paths
- **Impact:** Handles edge cases where standard paths don't work
- **Effort:** 4-6 hours
- **Files:** New utility module

### Priority 4: URL-Based Item Handling (Low)
- **Update:** Skip URL-based items gracefully
- **Impact:** Prevents errors, improves logging
- **Effort:** 1 hour
- **Files:** `scripts/batch_fingerprint_embedding.py`

---

## Alternative Approaches Considered

### Approach 1: Plugin API (Not Viable)
- **Method:** Use `eagle.item.get()` from Plugin API
- **Limitation:** Requires running inside Eagle app as plugin
- **Verdict:** ❌ Not suitable for external scripts

### Approach 2: Direct Database Access (Viable)
- **Method:** Query `metadata.db` SQLite database directly
- **Advantage:** Can get actual file paths
- **Risk:** Database schema may change
- **Verdict:** ✅ Recommended as fallback

### Approach 3: Library Structure Navigation (Viable)
- **Method:** Construct paths from library folder structure
- **Advantage:** No database dependency
- **Risk:** Structure may vary
- **Verdict:** ✅ Recommended as primary method

---

## Testing Recommendations

### Test 1: Verify API Method Fix
```python
# Test GET method works
client = get_eagle_client()
item = client.get_item("MKBAC8F1BAVW2")
assert item is not None
```

### Test 2: Verify Path Construction
```python
# Test path construction
library_path = Path("/Volumes/VIBES/Music Library-2.library")
file_path = get_eagle_item_file_path("MKBAC8F1BAVW2", "wav", library_path)
assert file_path.exists()
```

### Test 3: Verify Database Access
```python
# Test database query
file_path = get_file_path_from_db("MKBAC8F1BAVW2", library_path)
assert file_path is not None
```

---

## Implementation Checklist

- [ ] Fix `get_item()` method: POST → GET
- [ ] Implement path construction from library structure
- [ ] Add SQLite database access as fallback
- [ ] Update `batch_fingerprint_embedding.py` to use new path methods
- [ ] Add error handling for URL-based items
- [ ] Test with sample Eagle items
- [ ] Verify fingerprint embedding works with constructed paths
- [ ] Update documentation

---

## Conclusion

The Eagle REST API **does not provide file paths** for items. To enable fingerprint embedding, we must:

1. **Fix the API method** (POST → GET) for `item/info`
2. **Construct file paths** from Eagle library structure
3. **Use database access** as fallback for edge cases
4. **Handle URL-based items** gracefully

These updates will enable fingerprint embedding for Eagle library items, resolving the current limitation where 0 items have accessible file paths.

---

## References

- Eagle Plugin API: https://developer.eagle.cool/plugin-api/api/item
- Eagle Library Structure: Internal `.library` folder with `metadata.db` and `images/` directory
- API Testing: Verified `/api/item/info` requires GET method with query parameter
