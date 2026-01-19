#!/usr/bin/env python3
"""
Eagle Smart API with State Tracking and Query Caching
======================================================

This module provides enhanced Eagle API operations with:
- State tracking for resumable operations
- Query caching with configurable TTL
- Connection testing and auto-recovery
- Operation logging and metrics
- Thread-safe concurrent access

Integrates with the unified WorkflowStateManager for cross-module state sharing.

Usage:
    from scripts.eagle_api_smart import (
        eagle_request_smart as eagle_request,
        eagle_add_item_smart as eagle_add_item,
        eagle_import_to_library,
        eagle_switch_library_smart as eagle_switch_library,
        test_eagle_connection,
        state_manager,
        query_cache,
        NotionQueryCache,
        set_workspace_logger
    )

Version: 2026-01-19 - Initial implementation with full state tracking
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
from functools import wraps

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure module logger
logger = logging.getLogger(__name__)

# Workspace logger (can be overridden by set_workspace_logger)
_workspace_logger: Optional[logging.Logger] = None


def set_workspace_logger(ws_logger: logging.Logger) -> None:
    """Set the workspace logger for Eagle API operations."""
    global _workspace_logger
    _workspace_logger = ws_logger
    _log("info", "✅ Workspace logger configured for Eagle Smart API")


def _log(level: str, message: str, *args, **kwargs) -> None:
    """Log to workspace logger if available, otherwise module logger."""
    target_logger = _workspace_logger or logger
    getattr(target_logger, level)(message, *args, **kwargs)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment-based configuration with sensible defaults
EAGLE_API_BASE = os.getenv("EAGLE_API_BASE", "http://localhost:41595")
EAGLE_TOKEN = os.getenv("EAGLE_TOKEN", "")
EAGLE_LIBRARY_PATH = os.getenv("EAGLE_LIBRARY_PATH", "")
EAGLE_CACHE_TTL = float(os.getenv("EAGLE_CACHE_TTL", "300"))  # 5 minutes
EAGLE_RETRY_MAX = int(os.getenv("EAGLE_RETRY_MAX", "3"))
EAGLE_REQUEST_TIMEOUT = int(os.getenv("EAGLE_REQUEST_TIMEOUT", "30"))
EAGLE_CONNECTION_TIMEOUT = int(os.getenv("EAGLE_CONNECTION_TIMEOUT", "10"))

# State file location
STATE_FILE_PATH = Path(os.getenv(
    "EAGLE_STATE_FILE",
    "var/eagle_api_state.json"
))


# =============================================================================
# HTTP SESSION WITH RETRY LOGIC
# =============================================================================

def _build_http_session() -> requests.Session:
    """Build a robust HTTP session with connection pooling and retries."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=EAGLE_RETRY_MAX,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


_HTTP_SESSION: requests.Session = _build_http_session()


# =============================================================================
# QUERY CACHE WITH TTL
# =============================================================================

@dataclass
class CacheEntry:
    """A single cache entry with metadata."""
    data: Any
    created_at: float
    ttl: float
    hits: int = 0
    
    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class QueryCache:
    """
    Thread-safe query cache with TTL support.
    
    Features:
    - Configurable TTL per cache entry
    - Automatic expiration
    - Hit/miss statistics
    - Memory-efficient with size limits
    - Thread-safe operations
    """
    
    def __init__(
        self,
        default_ttl: float = EAGLE_CACHE_TTL,
        max_entries: int = 1000,
        name: str = "eagle_cache"
    ):
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self.name = name
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0
        }
        
        # Pre-built indexes for fast lookups
        self._name_index: Dict[str, List[Dict]] = {}
        self._path_index: Dict[str, Dict] = {}
        self._fingerprint_index: Dict[str, List[Dict]] = {}
        self._id_index: Dict[str, Dict] = {}
    
    def _make_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate a unique cache key for the request."""
        key_data = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if not expired."""
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            if entry.is_expired:
                del self._cache[key]
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None
            
            entry.hits += 1
            self._stats["hits"] += 1
            return entry.data
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None
    ) -> None:
        """Set a value in cache with optional TTL override."""
        with self._lock:
            # Evict oldest entries if at capacity
            while len(self._cache) >= self.max_entries:
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k].created_at
                )
                del self._cache[oldest_key]
                self._stats["evictions"] += 1
            
            self._cache[key] = CacheEntry(
                data=value,
                created_at=time.time(),
                ttl=ttl or self.default_ttl
            )
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate a specific key or the entire cache."""
        with self._lock:
            if key is None:
                self._cache.clear()
                self._name_index.clear()
                self._path_index.clear()
                self._fingerprint_index.clear()
                self._id_index.clear()
                _log("debug", f"🔄 {self.name}: Cache fully invalidated")
            elif key in self._cache:
                del self._cache[key]
                _log("debug", f"🔄 {self.name}: Key {key[:8]}... invalidated")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0
            
            return {
                **self._stats,
                "size": len(self._cache),
                "hit_rate": hit_rate,
                "max_entries": self.max_entries,
                "default_ttl": self.default_ttl
            }
    
    def build_indexes(self, items: List[Dict]) -> None:
        """Build pre-indexed lookups for O(1) access."""
        with self._lock:
            self._name_index.clear()
            self._path_index.clear()
            self._fingerprint_index.clear()
            self._id_index.clear()
            
            for item in items:
                # Index by ID
                item_id = item.get("id")
                if item_id:
                    self._id_index[item_id] = item
                
                # Index by lowercase name
                name = item.get("name", "").lower()
                if name:
                    self._name_index.setdefault(name, []).append(item)
                
                # Index by path
                path = item.get("path", "")
                if path:
                    self._path_index[path] = item
                
                # Index by fingerprint tag
                for tag in item.get("tags", []):
                    if isinstance(tag, str) and tag.lower().startswith("fingerprint:"):
                        fp_value = tag.split(":", 1)[1].strip().lower()
                        if fp_value:
                            self._fingerprint_index.setdefault(fp_value, []).append(item)
            
            _log("debug", f"✅ {self.name}: Indexed {len(items)} items "
                 f"(names: {len(self._name_index)}, paths: {len(self._path_index)}, "
                 f"fingerprints: {len(self._fingerprint_index)})")
    
    def get_by_id(self, item_id: str) -> Optional[Dict]:
        """O(1) lookup by Eagle item ID."""
        with self._lock:
            return self._id_index.get(item_id)
    
    def get_by_name(self, name: str) -> List[Dict]:
        """O(1) lookup by item name."""
        with self._lock:
            return self._name_index.get(name.lower(), [])
    
    def get_by_path(self, path: str) -> Optional[Dict]:
        """O(1) lookup by file path."""
        with self._lock:
            return self._path_index.get(path)
    
    def get_by_fingerprint(self, fingerprint: str) -> List[Dict]:
        """O(1) lookup by fingerprint tag."""
        with self._lock:
            return self._fingerprint_index.get(fingerprint.lower(), [])


class NotionQueryCache(QueryCache):
    """
    Extended cache specifically for Notion queries.
    
    Adds Notion-specific indexing by page ID, database ID, and title.
    """
    
    def __init__(
        self,
        default_ttl: float = 600,  # 10 minutes for Notion
        max_entries: int = 5000,
        name: str = "notion_cache"
    ):
        super().__init__(default_ttl, max_entries, name)
        self._page_index: Dict[str, Dict] = {}
        self._database_results: Dict[str, List[Dict]] = {}
    
    def cache_database_results(
        self,
        database_id: str,
        results: List[Dict],
        ttl: Optional[float] = None
    ) -> None:
        """Cache results from a Notion database query."""
        with self._lock:
            self._database_results[database_id] = results
            
            # Index individual pages
            for page in results:
                page_id = page.get("id")
                if page_id:
                    self._page_index[page_id] = page
            
            # Also store in main cache
            key = self._make_key(f"database:{database_id}", None)
            self.set(key, results, ttl)
    
    def get_database_results(self, database_id: str) -> Optional[List[Dict]]:
        """Get cached database results."""
        key = self._make_key(f"database:{database_id}", None)
        return self.get(key)
    
    def get_page(self, page_id: str) -> Optional[Dict]:
        """O(1) lookup by Notion page ID."""
        with self._lock:
            return self._page_index.get(page_id)
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """Override to also clear Notion-specific indexes."""
        with self._lock:
            super().invalidate(key)
            if key is None:
                self._page_index.clear()
                self._database_results.clear()


# Global cache instances
query_cache = QueryCache(name="eagle_items_cache")
notion_query_cache = NotionQueryCache(name="notion_tracks_cache")


# =============================================================================
# STATE MANAGER FOR EAGLE OPERATIONS
# =============================================================================

@dataclass
class OperationState:
    """State of an individual Eagle operation."""
    operation_id: str
    operation_type: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "in_progress"  # in_progress, completed, failed
    result: Optional[Dict] = None
    error: Optional[str] = None
    retries: int = 0
    metadata: Dict = field(default_factory=dict)


class EagleStateManager:
    """
    State manager for Eagle API operations.
    
    Provides:
    - Operation tracking with unique IDs
    - Checkpoint/resume capability
    - Operation history with stats
    - Thread-safe state persistence
    
    Integrates with unified WorkflowStateManager when available.
    """
    
    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or STATE_FILE_PATH
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._operations: Dict[str, OperationState] = {}
        self._session_stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "total_retries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "session_started_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Try to load existing state
        self._load_state()
        
        # Try to integrate with unified WorkflowStateManager
        self._workflow_state_manager = None
        try:
            from shared_core.workflows.workflow_state_manager import WorkflowStateManager
            self._workflow_state_manager = WorkflowStateManager()
            _log("debug", "✅ Integrated with unified WorkflowStateManager")
        except ImportError:
            _log("debug", "ℹ️  WorkflowStateManager not available - using standalone state")
    
    def _load_state(self) -> None:
        """Load persisted state from file."""
        if not self.state_file.exists():
            return
        
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            
            # Restore operations
            for op_id, op_data in data.get("operations", {}).items():
                self._operations[op_id] = OperationState(**op_data)
            
            # Restore session stats (partial - some stats are session-specific)
            saved_stats = data.get("session_stats", {})
            self._session_stats["total_operations"] = saved_stats.get("total_operations", 0)
            
            _log("debug", f"✅ Loaded {len(self._operations)} operations from state file")
        except Exception as e:
            _log("warning", f"⚠️  Could not load state file: {e}")
    
    def _save_state(self) -> None:
        """Persist state to file."""
        try:
            data = {
                "operations": {
                    op_id: {
                        "operation_id": op.operation_id,
                        "operation_type": op.operation_type,
                        "started_at": op.started_at,
                        "completed_at": op.completed_at,
                        "status": op.status,
                        "result": op.result,
                        "error": op.error,
                        "retries": op.retries,
                        "metadata": op.metadata
                    }
                    for op_id, op in self._operations.items()
                },
                "session_stats": self._session_stats,
                "last_saved": datetime.now(timezone.utc).isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            _log("warning", f"⚠️  Could not save state file: {e}")
    
    def start_operation(
        self,
        operation_type: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """Start tracking a new operation. Returns operation ID."""
        with self._lock:
            op_id = f"{operation_type}_{int(time.time() * 1000)}"
            
            self._operations[op_id] = OperationState(
                operation_id=op_id,
                operation_type=operation_type,
                started_at=datetime.now(timezone.utc).isoformat(),
                metadata=metadata or {}
            )
            
            self._session_stats["total_operations"] += 1
            self._save_state()
            
            return op_id
    
    def complete_operation(
        self,
        operation_id: str,
        result: Optional[Dict] = None
    ) -> None:
        """Mark an operation as completed."""
        with self._lock:
            if operation_id not in self._operations:
                return
            
            op = self._operations[operation_id]
            op.status = "completed"
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.result = result
            
            self._session_stats["successful_operations"] += 1
            self._save_state()
    
    def fail_operation(
        self,
        operation_id: str,
        error: str,
        partial_result: Optional[Dict] = None
    ) -> None:
        """Mark an operation as failed."""
        with self._lock:
            if operation_id not in self._operations:
                return
            
            op = self._operations[operation_id]
            op.status = "failed"
            op.completed_at = datetime.now(timezone.utc).isoformat()
            op.error = error
            op.result = partial_result
            
            self._session_stats["failed_operations"] += 1
            self._save_state()
    
    def record_retry(self, operation_id: str) -> None:
        """Record a retry attempt for an operation."""
        with self._lock:
            if operation_id in self._operations:
                self._operations[operation_id].retries += 1
                self._session_stats["total_retries"] += 1
    
    def record_api_call(self) -> None:
        """Record an API call."""
        with self._lock:
            self._session_stats["api_calls"] += 1
    
    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        with self._lock:
            self._session_stats["cache_hits"] += 1
    
    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        with self._lock:
            self._session_stats["cache_misses"] += 1
    
    def get_operation(self, operation_id: str) -> Optional[OperationState]:
        """Get the state of a specific operation."""
        with self._lock:
            return self._operations.get(operation_id)
    
    def get_pending_operations(self, operation_type: Optional[str] = None) -> List[OperationState]:
        """Get all in-progress operations, optionally filtered by type."""
        with self._lock:
            ops = [
                op for op in self._operations.values()
                if op.status == "in_progress"
            ]
            
            if operation_type:
                ops = [op for op in ops if op.operation_type == operation_type]
            
            return ops
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics."""
        with self._lock:
            stats = dict(self._session_stats)
            stats["cache_stats"] = query_cache.get_stats()
            stats["pending_operations"] = len(self.get_pending_operations())
            return stats
    
    def clear_completed_operations(self, older_than_hours: int = 24) -> int:
        """Clear completed/failed operations older than specified hours."""
        with self._lock:
            cutoff = time.time() - (older_than_hours * 3600)
            to_remove = []
            
            for op_id, op in self._operations.items():
                if op.status in ("completed", "failed"):
                    if op.completed_at:
                        completed_ts = datetime.fromisoformat(
                            op.completed_at.replace('Z', '+00:00')
                        ).timestamp()
                        if completed_ts < cutoff:
                            to_remove.append(op_id)
            
            for op_id in to_remove:
                del self._operations[op_id]
            
            if to_remove:
                self._save_state()
                _log("debug", f"🗑️  Cleared {len(to_remove)} old operations")
            
            return len(to_remove)


# Global state manager instance
state_manager = EagleStateManager()


# =============================================================================
# CONNECTION TESTING
# =============================================================================

def test_eagle_connection(
    timeout: int = EAGLE_CONNECTION_TIMEOUT,
    auto_launch: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Test connection to Eagle application.
    
    Args:
        timeout: Connection timeout in seconds
        auto_launch: If True, attempt to launch Eagle if not running
    
    Returns:
        Tuple of (is_connected, error_message or None)
    """
    try:
        url = f"{EAGLE_API_BASE}/api/application/info"
        if EAGLE_TOKEN:
            url = f"{url}?token={EAGLE_TOKEN}"
        
        response = _HTTP_SESSION.get(url, timeout=timeout)
        
        if response.status_code == 200:
            data = response.json()
            version = data.get("data", {}).get("version", "unknown")
            _log("info", f"✅ Eagle connection OK (version: {version})")
            return True, None
        else:
            error = f"Eagle returned status {response.status_code}"
            _log("warning", f"⚠️  {error}")
            return False, error
            
    except requests.exceptions.ConnectionError:
        if auto_launch:
            _log("info", "🦅 Eagle not running - attempting to launch...")
            if _launch_eagle_app():
                time.sleep(3)  # Wait for Eagle to start
                return test_eagle_connection(timeout=timeout, auto_launch=False)
        
        error = "Eagle application not running"
        _log("warning", f"⚠️  {error}")
        return False, error
        
    except Exception as e:
        error = f"Connection test failed: {e}"
        _log("error", f"❌ {error}")
        return False, error


def _launch_eagle_app() -> bool:
    """Attempt to launch Eagle application."""
    try:
        subprocess.Popen(
            ["open", "-a", "Eagle"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _log("info", "🦅 Eagle launch command sent")
        return True
    except Exception as e:
        _log("warning", f"⚠️  Could not launch Eagle: {e}")
        return False


# =============================================================================
# CORE API FUNCTIONS
# =============================================================================

def eagle_request_smart(
    method: str,
    endpoint: str,
    payload: Optional[Dict] = None,
    retry: int = EAGLE_RETRY_MAX,
    use_cache: bool = True,
    cache_ttl: Optional[float] = None
) -> Any:
    """
    Smart Eagle API request with caching and state tracking.
    
    Features:
    - Automatic caching for GET requests
    - State tracking for all operations
    - Automatic retry with exponential backoff
    - Connection testing and auto-recovery
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint (e.g., "/api/item/list")
        payload: Request payload for POST/PUT
        retry: Maximum retry attempts
        use_cache: Whether to use cache for GET requests
        cache_ttl: Optional cache TTL override
    
    Returns:
        API response data
    """
    # Check cache for GET requests
    cache_key = None
    if method.upper() == "GET" and use_cache:
        cache_key = query_cache._make_key(endpoint, payload)
        cached = query_cache.get(cache_key)
        if cached is not None:
            state_manager.record_cache_hit()
            _log("debug", f"🔄 Cache hit for {endpoint}")
            return cached
        state_manager.record_cache_miss()
    
    # Start operation tracking
    op_id = state_manager.start_operation(
        f"eagle_request_{method.lower()}",
        {"endpoint": endpoint, "has_payload": payload is not None}
    )
    
    # Build URL with token
    url = f"{EAGLE_API_BASE}{endpoint}"
    if EAGLE_TOKEN:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}token={EAGLE_TOKEN}"
    
    headers = {"Content-Type": "application/json"}
    
    for attempt in range(1, retry + 1):
        try:
            state_manager.record_api_call()
            
            response = _HTTP_SESSION.request(
                method.upper(),
                url,
                json=payload,
                headers=headers,
                timeout=EAGLE_REQUEST_TIMEOUT
            )
            
            # Handle specific error codes
            if response.status_code in (404, 405):
                if "item" in endpoint and (method.lower() == "delete" or "delete" in endpoint):
                    result = {"ok": False, "status": "unsupported", "reason": "endpoint_not_supported"}
                    state_manager.complete_operation(op_id, result)
                    return result
            
            if 200 <= response.status_code < 300:
                try:
                    data = response.json()
                except ValueError:
                    data = response.text
                
                # Cache successful GET responses
                if cache_key is not None:
                    query_cache.set(cache_key, data, cache_ttl)
                    
                    # Build indexes for item list responses
                    if endpoint == "/api/item/list" and isinstance(data, dict):
                        items = data.get("data", [])
                        if items:
                            query_cache.build_indexes(items)
                
                state_manager.complete_operation(op_id, {"status_code": response.status_code})
                _log("debug", f"✅ {method} {endpoint} succeeded")
                return data
            
            # Server error - retry
            if response.status_code >= 500:
                state_manager.record_retry(op_id)
                _log("warning", f"⚠️  Server error {response.status_code} (attempt {attempt}/{retry})")
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
            
            # Client error - don't retry
            error = f"Eagle API error {response.status_code}: {response.text[:200]}"
            state_manager.fail_operation(op_id, error)
            raise RuntimeError(error)
            
        except requests.exceptions.ConnectionError as e:
            state_manager.record_retry(op_id)
            _log("warning", f"⚠️  Connection error (attempt {attempt}/{retry}): {e}")
            
            # Try to launch Eagle
            connected, _ = test_eagle_connection(auto_launch=True)
            
            if attempt < retry:
                time.sleep(2 ** attempt)
                continue
            
            error = f"Connection failed after {retry} attempts"
            state_manager.fail_operation(op_id, error)
            raise RuntimeError(error)
            
        except requests.exceptions.Timeout as e:
            state_manager.record_retry(op_id)
            _log("warning", f"⏰ Timeout (attempt {attempt}/{retry}): {e}")
            
            if attempt < retry:
                time.sleep(2 ** attempt)
                continue
            
            error = f"Timeout after {retry} attempts"
            state_manager.fail_operation(op_id, error)
            raise RuntimeError(error)
            
        except Exception as e:
            if attempt < retry:
                state_manager.record_retry(op_id)
                _log("warning", f"⚠️  Error (attempt {attempt}/{retry}): {e}")
                time.sleep(2 ** attempt)
                continue
            
            error = str(e)
            state_manager.fail_operation(op_id, error)
            raise


def eagle_switch_library_smart(library_path: str = EAGLE_LIBRARY_PATH) -> bool:
    """
    Switch Eagle to the specified library with validation.
    
    Args:
        library_path: Path to Eagle library (.library folder)
    
    Returns:
        True if switch successful, False otherwise
    """
    if not library_path:
        _log("info", "🦅 No library path specified - using current library")
        return True
    
    lib_path = Path(library_path)
    
    # Validate library path
    if not lib_path.exists():
        _log("warning", f"🦅 Library path does not exist: {library_path}")
        return False
    
    if not lib_path.is_dir() or not (lib_path / "library.json").exists():
        _log("warning", f"🦅 Invalid Eagle library (missing library.json): {library_path}")
        return False
    
    try:
        result = eagle_request_smart(
            "POST",
            "/api/library/switch",
            {"libraryPath": str(lib_path)},
            use_cache=False
        )
        
        if isinstance(result, dict) and result.get("status") == "success":
            # Invalidate cache on library switch
            query_cache.invalidate()
            _log("info", f"✅ Switched to Eagle library: {lib_path.name}")
            return True
        else:
            _log("warning", f"⚠️  Library switch returned: {result}")
            return False
            
    except Exception as e:
        _log("warning", f"⚠️  Could not switch library: {e}")
        return False


def eagle_add_item_smart(
    path: str,
    name: str,
    website: str = "",
    tags: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    existing_eagle_id: Optional[str] = None
) -> Optional[str]:
    """
    Add an item to Eagle with smart handling.
    
    Features:
    - Pre-validates file existence
    - Handles existing items gracefully
    - Updates cache after successful add
    - Tracks operation state
    
    Args:
        path: Path to the file
        name: Display name for the item
        website: Optional source URL
        tags: List of tags to apply
        folder_id: Optional folder ID to add to
        existing_eagle_id: If updating an existing item
    
    Returns:
        Eagle item ID if successful, None otherwise
    """
    file_path = Path(path)
    
    # Validate file exists
    if not file_path.exists():
        _log("error", f"❌ File not found: {path}")
        return None
    
    # Use absolute path
    abs_path = str(file_path.resolve())
    
    # Build payload
    payload = {
        "path": abs_path,
        "name": name,
        "tags": tags or [],
        "folderId": folder_id or "root"
    }
    
    if website:
        payload["website"] = website
    
    _log("debug", f"🦅 Adding item: {name}")
    _log("debug", f"   Path: {abs_path}")
    _log("debug", f"   Tags: {tags}")
    
    try:
        result = eagle_request_smart(
            "POST",
            "/api/item/addFromPath",
            payload,
            use_cache=False
        )
        
        if isinstance(result, dict) and result.get("status") == "success":
            eagle_id = result.get("data")
            if isinstance(eagle_id, dict):
                eagle_id = eagle_id.get("id")
            
            # Invalidate cache after adding new item
            query_cache.invalidate()
            
            _log("info", f"✅ Added item to Eagle: {name} -> {eagle_id}")
            return eagle_id
        else:
            _log("warning", f"⚠️  Eagle add failed: {result}")
            return None
            
    except Exception as e:
        _log("error", f"❌ Failed to add item: {e}")
        return None


# =============================================================================
# SAFE DELETION FUNCTIONS
# =============================================================================
# CRITICAL: These functions ensure files are NEVER deleted from filesystem
# without first being properly removed from Eagle via the API.
# This prevents "orphaned" Eagle items where metadata exists but files are gone.

def eagle_move_to_trash_smart(item_ids: List[str]) -> Tuple[bool, List[str], List[str]]:
    """
    Move Eagle items to trash using the official API endpoint.
    
    This is the ONLY supported delete operation in Eagle. It moves items
    to Eagle's trash, which can be emptied from the Eagle UI.
    
    IMPORTANT: Always use this BEFORE deleting files from filesystem!
    
    Args:
        item_ids: List of Eagle item IDs to move to trash
    
    Returns:
        Tuple of (success, successfully_trashed_ids, failed_ids)
    """
    if not item_ids:
        return True, [], []
    
    op_id = state_manager.start_operation(
        "eagle_move_to_trash",
        {"item_count": len(item_ids)}
    )
    
    try:
        result = eagle_request_smart(
            "POST",
            "/api/item/moveToTrash",
            {"itemIds": item_ids},
            use_cache=False
        )
        
        if isinstance(result, dict) and result.get("status") == "success":
            query_cache.invalidate()
            state_manager.complete_operation(op_id, {"trashed": len(item_ids)})
            _log("info", f"🗑️  Moved {len(item_ids)} Eagle item(s) to trash")
            return True, item_ids, []
        else:
            _log("warning", f"⚠️  Failed to move items to trash: {result}")
            state_manager.fail_operation(op_id, f"API returned: {result}")
            return False, [], item_ids
            
    except Exception as e:
        _log("error", f"❌ Exception moving items to trash: {e}")
        state_manager.fail_operation(op_id, str(e))
        return False, [], item_ids


def safe_delete_file_with_eagle_sync(
    file_path: Union[str, Path],
    eagle_item_id: Optional[str] = None,
    require_eagle_success: bool = True
) -> Dict[str, Any]:
    """
    SAFELY delete a file, ensuring Eagle is updated FIRST.
    
    This function prevents the "orphaned Eagle items" problem by:
    1. Finding/verifying the Eagle item for this file
    2. Moving the Eagle item to trash via API
    3. Only THEN deleting the file from filesystem
    
    If Eagle deletion fails and require_eagle_success=True, the file
    is NOT deleted from the filesystem.
    
    Args:
        file_path: Path to the file to delete
        eagle_item_id: Optional known Eagle item ID (if None, will search)
        require_eagle_success: If True, abort file deletion if Eagle fails
    
    Returns:
        Dict with operation results:
        {
            "success": bool,
            "file_deleted": bool,
            "eagle_deleted": bool,
            "eagle_item_id": str or None,
            "error": str or None,
            "warnings": list
        }
    """
    file_path = Path(file_path)
    result = {
        "success": False,
        "file_deleted": False,
        "eagle_deleted": False,
        "eagle_item_id": eagle_item_id,
        "error": None,
        "warnings": []
    }
    
    # Step 1: Check if file exists
    if not file_path.exists():
        result["warnings"].append(f"File does not exist: {file_path}")
        # File already gone - still try to clean up Eagle if we have an ID
        if eagle_item_id:
            success, trashed, failed = eagle_move_to_trash_smart([eagle_item_id])
            result["eagle_deleted"] = success
        result["success"] = True  # Nothing to delete
        return result
    
    # Step 2: Find Eagle item if not provided
    if not eagle_item_id:
        eagle_item = find_eagle_items_by_path(str(file_path))
        if eagle_item:
            eagle_item_id = eagle_item.get("id")
            result["eagle_item_id"] = eagle_item_id
            _log("debug", f"Found Eagle item for {file_path.name}: {eagle_item_id}")
        else:
            # Also try by filename
            items_by_name = find_eagle_items_by_name(file_path.stem)
            if items_by_name:
                # Match by extension too
                for item in items_by_name:
                    if item.get("ext", "").lower() == file_path.suffix.lstrip(".").lower():
                        eagle_item_id = item.get("id")
                        result["eagle_item_id"] = eagle_item_id
                        _log("debug", f"Found Eagle item by name: {eagle_item_id}")
                        break
    
    # Step 3: Delete from Eagle FIRST
    if eagle_item_id:
        success, trashed, failed = eagle_move_to_trash_smart([eagle_item_id])
        result["eagle_deleted"] = success
        
        if not success and require_eagle_success:
            result["error"] = f"Eagle deletion failed for {eagle_item_id} - file NOT deleted to prevent orphan"
            _log("warning", f"⚠️  {result['error']}")
            return result
    else:
        result["warnings"].append(f"No Eagle item found for {file_path} - proceeding with file deletion")
        _log("debug", f"No Eagle item found for {file_path}")
    
    # Step 4: Now safe to delete the file
    try:
        file_path.unlink()
        result["file_deleted"] = True
        result["success"] = True
        _log("info", f"🗑️  Safely deleted: {file_path.name} (Eagle: {eagle_item_id or 'N/A'})")
    except Exception as e:
        result["error"] = f"Failed to delete file: {e}"
        _log("error", f"❌ {result['error']}")
    
    return result


def safe_cleanup_track_files(
    file_paths: List[Union[str, Path]],
    eagle_item_ids: Optional[List[str]] = None,
    require_all_eagle_success: bool = False
) -> Dict[str, Any]:
    """
    Safely clean up multiple files for a track, syncing with Eagle first.
    
    Args:
        file_paths: List of file paths to delete
        eagle_item_ids: Optional list of known Eagle IDs (parallel to file_paths)
        require_all_eagle_success: If True, abort all if any Eagle deletion fails
    
    Returns:
        Summary dict with stats and details
    """
    op_id = state_manager.start_operation(
        "safe_cleanup_track_files",
        {"file_count": len(file_paths)}
    )
    
    results = {
        "success": True,
        "files_deleted": 0,
        "eagle_items_deleted": 0,
        "files_failed": 0,
        "eagle_items_failed": 0,
        "details": [],
        "errors": [],
        "warnings": []
    }
    
    # Normalize inputs
    file_paths = [Path(p) for p in file_paths if p]
    if eagle_item_ids is None:
        eagle_item_ids = [None] * len(file_paths)
    
    # Process each file
    for i, file_path in enumerate(file_paths):
        eagle_id = eagle_item_ids[i] if i < len(eagle_item_ids) else None
        
        delete_result = safe_delete_file_with_eagle_sync(
            file_path,
            eagle_item_id=eagle_id,
            require_eagle_success=require_all_eagle_success
        )
        
        results["details"].append({
            "path": str(file_path),
            **delete_result
        })
        
        if delete_result["file_deleted"]:
            results["files_deleted"] += 1
        elif delete_result.get("error"):
            results["files_failed"] += 1
            results["errors"].append(delete_result["error"])
        
        if delete_result["eagle_deleted"]:
            results["eagle_items_deleted"] += 1
        elif delete_result["eagle_item_id"] and not delete_result["eagle_deleted"]:
            results["eagle_items_failed"] += 1
        
        results["warnings"].extend(delete_result.get("warnings", []))
    
    results["success"] = results["files_failed"] == 0
    
    state_manager.complete_operation(op_id, {
        "files_deleted": results["files_deleted"],
        "eagle_deleted": results["eagle_items_deleted"]
    })
    
    _log("info", f"🧹 Cleanup complete: {results['files_deleted']}/{len(file_paths)} files, "
         f"{results['eagle_items_deleted']} Eagle items deleted")
    
    return results


def verify_eagle_file_integrity(
    item_id: Optional[str] = None,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    Verify file integrity for Eagle items - find orphaned items.
    
    An orphaned item is one where Eagle has metadata but the file
    is missing from the filesystem.
    
    Args:
        item_id: Optional specific item ID to check
        limit: Max items to check (for performance)
    
    Returns:
        Dict with integrity report
    """
    try:
        from scripts.eagle_path_resolution import (
            resolve_eagle_item_path,
            get_eagle_library_path
        )
    except ImportError:
        _log("warning", "eagle_path_resolution not available - cannot verify integrity")
        return {"error": "eagle_path_resolution module not available"}
    
    library_path = get_eagle_library_path()
    if not library_path:
        return {"error": "Could not determine Eagle library path"}
    
    items = get_eagle_items()
    if item_id:
        items = [i for i in items if i.get("id") == item_id]
    
    if limit:
        items = items[:limit]
    
    report = {
        "total_checked": len(items),
        "valid": 0,
        "orphaned": [],  # Eagle has metadata but file missing
        "path_errors": [],  # Could not resolve path
    }
    
    for item in items:
        iid = item.get("id")
        try:
            resolved_path = resolve_eagle_item_path(item, library_path)
            
            if resolved_path is None:
                report["path_errors"].append({
                    "id": iid,
                    "name": item.get("name"),
                    "error": "Could not resolve path"
                })
            elif not resolved_path.exists():
                report["orphaned"].append({
                    "id": iid,
                    "name": item.get("name"),
                    "expected_path": str(resolved_path)
                })
            else:
                report["valid"] += 1
                
        except Exception as e:
            report["path_errors"].append({
                "id": iid,
                "name": item.get("name"),
                "error": str(e)
            })
    
    report["orphan_count"] = len(report["orphaned"])
    report["health_percentage"] = (
        report["valid"] / report["total_checked"] * 100
        if report["total_checked"] > 0 else 0
    )
    
    _log("info", f"🔍 Eagle integrity check: {report['valid']}/{report['total_checked']} valid, "
         f"{report['orphan_count']} orphaned")
    
    return report


def cleanup_orphaned_eagle_items(
    dry_run: bool = True,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Find and clean up orphaned Eagle items (items without files).
    
    Args:
        dry_run: If True, only report what would be cleaned (default: True)
        limit: Max items to process
    
    Returns:
        Dict with cleanup results
    """
    integrity = verify_eagle_file_integrity(limit=limit)
    
    if "error" in integrity:
        return integrity
    
    orphaned = integrity.get("orphaned", [])
    
    result = {
        "orphaned_found": len(orphaned),
        "cleaned": 0,
        "failed": 0,
        "dry_run": dry_run,
        "items": []
    }
    
    if not orphaned:
        _log("info", "✅ No orphaned Eagle items found")
        return result
    
    _log("info", f"Found {len(orphaned)} orphaned Eagle items")
    
    if dry_run:
        _log("info", "🔍 DRY RUN - would clean the following orphaned items:")
        for item in orphaned[:10]:
            _log("info", f"   - {item['name']} ({item['id'][:8]}...)")
        if len(orphaned) > 10:
            _log("info", f"   ... and {len(orphaned) - 10} more")
        result["items"] = orphaned
        return result
    
    # Actually clean up
    item_ids = [item["id"] for item in orphaned]
    success, trashed, failed = eagle_move_to_trash_smart(item_ids)
    
    result["cleaned"] = len(trashed)
    result["failed"] = len(failed)
    result["items"] = orphaned
    
    _log("info", f"🧹 Cleaned {result['cleaned']} orphaned items, {result['failed']} failed")
    
    return result


def eagle_import_to_library(
    items: List[Dict[str, Any]],
    folder_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Batch import multiple items to Eagle.
    
    Args:
        items: List of item dicts with 'path', 'name', 'tags', etc.
        folder_id: Optional folder to add all items to
    
    Returns:
        Dict with 'succeeded', 'failed', and 'errors' lists
    """
    op_id = state_manager.start_operation(
        "eagle_batch_import",
        {"item_count": len(items), "folder_id": folder_id}
    )
    
    results = {
        "succeeded": [],
        "failed": [],
        "errors": []
    }
    
    for item in items:
        try:
            eagle_id = eagle_add_item_smart(
                path=item.get("path", ""),
                name=item.get("name", ""),
                website=item.get("website", ""),
                tags=item.get("tags", []),
                folder_id=folder_id or item.get("folder_id")
            )
            
            if eagle_id:
                results["succeeded"].append({
                    "path": item.get("path"),
                    "eagle_id": eagle_id
                })
            else:
                results["failed"].append(item.get("path"))
                
        except Exception as e:
            results["failed"].append(item.get("path"))
            results["errors"].append({
                "path": item.get("path"),
                "error": str(e)
            })
    
    state_manager.complete_operation(op_id, {
        "succeeded": len(results["succeeded"]),
        "failed": len(results["failed"])
    })
    
    _log("info", f"📦 Batch import: {len(results['succeeded'])} succeeded, "
         f"{len(results['failed'])} failed")
    
    return results


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_eagle_items(force_refresh: bool = False) -> List[Dict]:
    """
    Get all Eagle items with caching.
    
    Args:
        force_refresh: Force cache refresh
    
    Returns:
        List of Eagle item dictionaries
    """
    if force_refresh:
        query_cache.invalidate()
    
    result = eagle_request_smart("GET", "/api/item/list", use_cache=not force_refresh)
    
    if isinstance(result, dict):
        return result.get("data", [])
    return []


def get_eagle_library_info() -> Optional[Dict]:
    """Get information about the current Eagle library."""
    try:
        result = eagle_request_smart("GET", "/api/library/info", use_cache=False)
        if result and isinstance(result, dict) and result.get("status") == "success":
            lib_data = result.get("data", {})
            return {
                "name": lib_data.get("library", {}).get("name", "Unknown"),
                "path": lib_data.get("library", {}).get("path", "Unknown"),
                "itemCount": lib_data.get("library", {}).get("itemCount", 0),
                "folders": lib_data.get("folders", [])
            }
    except Exception as e:
        _log("debug", f"Could not get library info: {e}")
    return None


def find_eagle_items_by_name(name: str) -> List[Dict]:
    """Find Eagle items by name using cached index."""
    # Ensure cache is populated
    if not query_cache._name_index:
        get_eagle_items()
    
    return query_cache.get_by_name(name)


def find_eagle_items_by_path(path: str) -> Optional[Dict]:
    """Find Eagle item by path using cached index."""
    # Ensure cache is populated
    if not query_cache._path_index:
        get_eagle_items()
    
    return query_cache.get_by_path(path)


def find_eagle_items_by_fingerprint(fingerprint: str) -> List[Dict]:
    """Find Eagle items by fingerprint tag using cached index."""
    # Ensure cache is populated
    if not query_cache._fingerprint_index:
        get_eagle_items()
    
    return query_cache.get_by_fingerprint(fingerprint)


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """CLI for testing Eagle Smart API."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Eagle Smart API CLI")
    parser.add_argument("--test", action="store_true", help="Test Eagle connection")
    parser.add_argument("--info", action="store_true", help="Show library info")
    parser.add_argument("--stats", action="store_true", help="Show session stats")
    parser.add_argument("--list", action="store_true", help="List Eagle items")
    parser.add_argument("--limit", type=int, default=10, help="Limit items shown")
    parser.add_argument("--search", type=str, help="Search by name")
    parser.add_argument("--refresh", action="store_true", help="Force cache refresh")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    if args.test:
        connected, error = test_eagle_connection()
        if connected:
            print("✅ Eagle connection successful")
        else:
            print(f"❌ Connection failed: {error}")
        return
    
    if args.info:
        info = get_eagle_library_info()
        if info:
            print(f"📚 Library: {info['name']}")
            print(f"📁 Path: {info['path']}")
            print(f"📦 Items: {info['itemCount']:,}")
        else:
            print("❌ Could not get library info")
        return
    
    if args.stats:
        stats = state_manager.get_session_stats()
        print("📊 Session Statistics:")
        print(f"   Total operations: {stats['total_operations']}")
        print(f"   Successful: {stats['successful_operations']}")
        print(f"   Failed: {stats['failed_operations']}")
        print(f"   API calls: {stats['api_calls']}")
        print(f"   Cache hits: {stats['cache_hits']}")
        print(f"   Cache misses: {stats['cache_misses']}")
        
        cache_stats = stats.get('cache_stats', {})
        print(f"\n📦 Cache Statistics:")
        print(f"   Size: {cache_stats.get('size', 0)} entries")
        print(f"   Hit rate: {cache_stats.get('hit_rate', 0):.1%}")
        return
    
    if args.search:
        items = find_eagle_items_by_name(args.search)
        print(f"🔍 Found {len(items)} items matching '{args.search}':")
        for item in items[:args.limit]:
            print(f"   - {item.get('name')} ({item.get('id', 'no-id')[:8]}...)")
        return
    
    if args.list:
        items = get_eagle_items(force_refresh=args.refresh)
        print(f"📦 Eagle items ({len(items)} total, showing {min(args.limit, len(items))}):")
        for item in items[:args.limit]:
            print(f"   - {item.get('name')} ({item.get('id', 'no-id')[:8]}...)")
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
