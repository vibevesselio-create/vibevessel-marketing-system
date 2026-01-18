#!/usr/bin/env python3
"""
Unified State Registry
======================

Provides centralized track state management with:
- File-based persistence (JSON)
- TTL-based cache expiration
- Thread-safe operations
- Notion integration for state sync
- Cross-module state sharing

This registry tracks the state of all tracks in the music workflow,
enabling efficient lookups without repeated Notion API calls.

State Structure per Track:
{
    "track_id": str,
    "notion_page_id": str,
    "track_name": str,
    "artist_name": str,
    "notion_downloaded": bool,
    "notion_file_paths": List[str],
    "notion_eagle_id": str,
    "fingerprint": str,
    "eagle_item_id": str,
    "last_updated": str (ISO timestamp),
    "expires_at": str (ISO timestamp)
}

Version: 1.0.0
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = Path("var/unified_track_state_registry.json")
DEFAULT_TTL_SECONDS = 300  # 5 minutes


class UnifiedStateRegistry:
    """
    Unified state registry for track state management.

    Provides a centralized, persistent, thread-safe cache for track state
    that can be shared across modules and workflows.
    """

    def __init__(
        self,
        notion_manager: Any = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        state_file: Optional[Path] = None,
        auto_persist: bool = True,
        persist_interval: int = 50  # Persist every N updates
    ):
        """
        Initialize the unified state registry.

        Args:
            notion_manager: Notion manager instance for syncing state
            ttl_seconds: Time-to-live for cached entries (default: 300s / 5min)
            state_file: Path to persistent state file
            auto_persist: Whether to auto-persist state changes
            persist_interval: How often to persist (every N updates)
        """
        self.notion_manager = notion_manager
        self.ttl_seconds = ttl_seconds
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.auto_persist = auto_persist
        self.persist_interval = persist_interval

        # Thread safety
        self.lock = threading.RLock()

        # Internal state
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._update_count = 0
        self._stats = {
            "hits": 0,
            "misses": 0,
            "updates": 0,
            "expirations": 0,
            "persists": 0
        }

        # Ensure state directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing state
        self._load_state()

        logger.info(f"UnifiedStateRegistry initialized (TTL: {ttl_seconds}s, file: {self.state_file})")

    def _load_state(self) -> None:
        """Load persisted state from file."""
        if not self.state_file.exists():
            logger.debug(f"No existing state file at {self.state_file}")
            return

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)

            # Load cache and clean expired entries
            loaded_cache = data.get("cache", {})
            now = datetime.now(timezone.utc)

            valid_entries = 0
            expired_entries = 0

            for track_id, entry in loaded_cache.items():
                expires_at_str = entry.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        if expires_at > now:
                            self._cache[track_id] = entry
                            valid_entries += 1
                        else:
                            expired_entries += 1
                    except (ValueError, TypeError):
                        # Invalid timestamp, skip entry
                        expired_entries += 1
                else:
                    # No expiration, keep entry
                    self._cache[track_id] = entry
                    valid_entries += 1

            # Load stats
            self._stats = data.get("stats", self._stats)

            logger.info(f"Loaded {valid_entries} valid entries ({expired_entries} expired) from {self.state_file}")

        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")

    def _save_state(self, force: bool = False) -> None:
        """
        Save state to file.

        Args:
            force: Force save even if not at persist interval
        """
        if not self.auto_persist and not force:
            return

        self._update_count += 1

        if not force and self._update_count % self.persist_interval != 0:
            return

        try:
            data = {
                "version": "1.0.0",
                "last_saved": datetime.now(timezone.utc).isoformat(),
                "cache": self._cache,
                "stats": self._stats,
                "entry_count": len(self._cache)
            }

            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            self._stats["persists"] += 1
            logger.debug(f"Persisted {len(self._cache)} entries to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _calculate_expiry(self) -> str:
        """Calculate expiry timestamp based on TTL."""
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        return expires.isoformat()

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if an entry is expired."""
        expires_at_str = entry.get("expires_at")
        if not expires_at_str:
            return False  # No expiry means never expires

        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > expires_at
        except (ValueError, TypeError):
            return True  # Invalid timestamp = expired

    # ─────────────────────────────────────────────────────────────
    # Core API Methods
    # ─────────────────────────────────────────────────────────────

    def get_track_state(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        Get track state from registry.

        Args:
            track_id: Track identifier (Notion page ID or custom ID)

        Returns:
            Track state dictionary, or None if not found/expired
        """
        with self.lock:
            entry = self._cache.get(track_id)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if self._is_expired(entry):
                self._stats["expirations"] += 1
                del self._cache[track_id]
                return None

            self._stats["hits"] += 1
            return entry.copy()

    def update_track_state(self, track_id: str, state: Dict[str, Any]) -> bool:
        """
        Update track state in registry.

        Args:
            track_id: Track identifier
            state: Track state dictionary

        Returns:
            True if update succeeded
        """
        with self.lock:
            try:
                # Merge with existing state (if any)
                existing = self._cache.get(track_id, {})

                # Update entry
                entry = {
                    **existing,
                    **state,
                    "track_id": track_id,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "expires_at": self._calculate_expiry()
                }

                self._cache[track_id] = entry
                self._stats["updates"] += 1

                # Auto-persist
                self._save_state()

                logger.debug(f"Updated track state: {track_id}")
                return True

            except Exception as e:
                logger.error(f"Failed to update track state for {track_id}: {e}")
                return False

    def invalidate(self, track_id: str) -> bool:
        """
        Invalidate (remove) a track from registry.

        Args:
            track_id: Track identifier

        Returns:
            True if entry was removed, False if not found
        """
        with self.lock:
            if track_id in self._cache:
                del self._cache[track_id]
                self._save_state()
                logger.debug(f"Invalidated track: {track_id}")
                return True
            return False

    def clear(self) -> bool:
        """
        Clear all entries from registry.

        Returns:
            True if cleared successfully
        """
        with self.lock:
            count = len(self._cache)
            self._cache.clear()
            self._save_state(force=True)
            logger.info(f"Cleared {count} entries from registry")
            return True

    # ─────────────────────────────────────────────────────────────
    # Bulk Operations
    # ─────────────────────────────────────────────────────────────

    def get_all_tracks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all non-expired tracks from registry.

        Returns:
            Dictionary of track_id -> track_state
        """
        with self.lock:
            result = {}
            expired_ids = []

            for track_id, entry in self._cache.items():
                if self._is_expired(entry):
                    expired_ids.append(track_id)
                else:
                    result[track_id] = entry.copy()

            # Clean up expired entries
            for track_id in expired_ids:
                del self._cache[track_id]
                self._stats["expirations"] += 1

            if expired_ids:
                self._save_state()

            return result

    def bulk_update(self, tracks: Dict[str, Dict[str, Any]]) -> int:
        """
        Bulk update multiple tracks.

        Args:
            tracks: Dictionary of track_id -> track_state

        Returns:
            Number of tracks updated
        """
        with self.lock:
            updated = 0
            for track_id, state in tracks.items():
                if self.update_track_state(track_id, state):
                    updated += 1

            self._save_state(force=True)
            logger.info(f"Bulk updated {updated} tracks")
            return updated

    def find_tracks(
        self,
        filter_fn: Optional[callable] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """
        Find tracks matching criteria.

        Args:
            filter_fn: Optional custom filter function
            **filters: Key-value filters (e.g., notion_downloaded=True)

        Returns:
            List of matching track states
        """
        with self.lock:
            results = []

            for track_id, entry in self._cache.items():
                if self._is_expired(entry):
                    continue

                # Apply custom filter
                if filter_fn and not filter_fn(entry):
                    continue

                # Apply key-value filters
                match = True
                for key, value in filters.items():
                    if entry.get(key) != value:
                        match = False
                        break

                if match:
                    results.append(entry.copy())

            return results

    # ─────────────────────────────────────────────────────────────
    # Track Lookup Helpers
    # ─────────────────────────────────────────────────────────────

    def get_by_notion_page_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Get track by Notion page ID."""
        # First try direct lookup (track_id might be page_id)
        result = self.get_track_state(page_id)
        if result:
            return result

        # Search by notion_page_id field
        with self.lock:
            for track_id, entry in self._cache.items():
                if entry.get("notion_page_id") == page_id:
                    if not self._is_expired(entry):
                        return entry.copy()
            return None

    def get_by_eagle_id(self, eagle_id: str) -> Optional[Dict[str, Any]]:
        """Get track by Eagle item ID."""
        with self.lock:
            for track_id, entry in self._cache.items():
                if entry.get("eagle_item_id") == eagle_id or entry.get("notion_eagle_id") == eagle_id:
                    if not self._is_expired(entry):
                        return entry.copy()
            return None

    def get_by_fingerprint(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """Get track by fingerprint."""
        with self.lock:
            for track_id, entry in self._cache.items():
                if entry.get("fingerprint") == fingerprint:
                    if not self._is_expired(entry):
                        return entry.copy()
            return None

    # ─────────────────────────────────────────────────────────────
    # Statistics & Diagnostics
    # ─────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with cache stats
        """
        with self.lock:
            return {
                **self._stats,
                "entry_count": len(self._cache),
                "ttl_seconds": self.ttl_seconds,
                "state_file": str(self.state_file),
                "hit_rate": (
                    self._stats["hits"] / (self._stats["hits"] + self._stats["misses"])
                    if (self._stats["hits"] + self._stats["misses"]) > 0
                    else 0.0
                )
            }

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on registry.

        Returns:
            Health check results
        """
        with self.lock:
            now = datetime.now(timezone.utc)

            # Count valid vs expired
            valid = 0
            expired = 0
            for entry in self._cache.values():
                if self._is_expired(entry):
                    expired += 1
                else:
                    valid += 1

            # Check state file
            state_file_exists = self.state_file.exists()
            state_file_size = self.state_file.stat().st_size if state_file_exists else 0

            return {
                "healthy": True,
                "timestamp": now.isoformat(),
                "entries": {
                    "total": len(self._cache),
                    "valid": valid,
                    "expired": expired
                },
                "persistence": {
                    "file_exists": state_file_exists,
                    "file_size_bytes": state_file_size,
                    "file_path": str(self.state_file)
                },
                "stats": self._stats,
                "config": {
                    "ttl_seconds": self.ttl_seconds,
                    "auto_persist": self.auto_persist,
                    "persist_interval": self.persist_interval
                }
            }

    def flush(self) -> bool:
        """
        Force flush all state to disk.

        Returns:
            True if flush succeeded
        """
        with self.lock:
            try:
                self._save_state(force=True)
                return True
            except Exception as e:
                logger.error(f"Flush failed: {e}")
                return False

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        with self.lock:
            expired_ids = [
                track_id for track_id, entry in self._cache.items()
                if self._is_expired(entry)
            ]

            for track_id in expired_ids:
                del self._cache[track_id]
                self._stats["expirations"] += 1

            if expired_ids:
                self._save_state(force=True)
                logger.info(f"Cleaned up {len(expired_ids)} expired entries")

            return len(expired_ids)


# ─────────────────────────────────────────────────────────────────
# Factory Function
# ─────────────────────────────────────────────────────────────────

# Singleton instance
_registry_instance: Optional[UnifiedStateRegistry] = None
_registry_lock = threading.Lock()


def get_registry(
    notion_manager: Any = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_new: bool = False
) -> UnifiedStateRegistry:
    """
    Get the unified state registry instance (singleton).

    Args:
        notion_manager: Notion manager instance for syncing state
        ttl_seconds: Time-to-live for cached entries
        force_new: Force creation of new instance (for testing)

    Returns:
        UnifiedStateRegistry instance
    """
    global _registry_instance

    with _registry_lock:
        if _registry_instance is None or force_new:
            _registry_instance = UnifiedStateRegistry(
                notion_manager=notion_manager,
                ttl_seconds=ttl_seconds
            )
            logger.info("Created new UnifiedStateRegistry instance")

        return _registry_instance


def reset_registry() -> None:
    """Reset the singleton registry instance (for testing)."""
    global _registry_instance

    with _registry_lock:
        if _registry_instance:
            _registry_instance.flush()
        _registry_instance = None
        logger.info("Reset UnifiedStateRegistry singleton")
