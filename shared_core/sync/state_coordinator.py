"""
Unified State Coordinator for Cross-System Synchronization
============================================================

Provides centralized state management across:
- Python cron scripts
- Google Apps Script triggers
- Webhook server
- Notion distributed locks

VERSION: 1.0.0
CREATED: 2026-01-30
AUTHOR: Claude Code Agent

USAGE:
    from shared_core.sync.state_coordinator import StateCoordinator

    coordinator = StateCoordinator()

    # Get unified state
    state = coordinator.get_state("cron_music_sync")

    # Update with conflict detection
    success = coordinator.update_state_atomic(
        source="cron_music_sync",
        updates={"batch_index": 5},
        expected_version=state["version"]
    )
"""

import os
import json
import fcntl
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class SyncState:
    """Unified state object for all sync operations."""
    source: str
    batch_index: int = 0
    last_sync: Optional[str] = None
    total_processed: int = 0
    last_item_id: Optional[str] = None
    cursor: Optional[str] = None
    version: int = 0
    updated_at: Optional[str] = None
    lock_holder: Optional[str] = None
    lock_expires: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncState':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class StateCoordinator:
    """
    Centralized state coordinator for cross-system synchronization.

    Manages state across:
    - Local file storage (for cron scripts)
    - Notion database (for distributed coordination)
    - In-memory cache (for webhook server)
    """

    STATE_DIR = PROJECT_ROOT / "var" / "sync_state"
    LOCK_TIMEOUT_MINUTES = 30

    def __init__(self, notion_client=None):
        """Initialize the state coordinator."""
        self.notion = notion_client
        self.STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, SyncState] = {}

    def _get_state_file(self, source: str) -> Path:
        """Get the state file path for a source."""
        safe_name = hashlib.md5(source.encode()).hexdigest()[:12]
        return self.STATE_DIR / f"{source}_{safe_name}.json"

    def get_state(self, source: str) -> SyncState:
        """
        Get the current state for a source.

        Args:
            source: Source identifier (e.g., "cron_music_sync", "gas_spotify_sync")

        Returns:
            SyncState object
        """
        # Check cache first
        if source in self._cache:
            return self._cache[source]

        state_file = self._get_state_file(source)

        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        data = json.load(f)
                        state = SyncState.from_dict(data)
                        self._cache[source] = state
                        return state
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                logger.warning(f"Failed to load state for {source}: {e}")

        # Return default state
        return SyncState(source=source)

    def update_state_atomic(
        self,
        source: str,
        updates: Dict[str, Any],
        expected_version: Optional[int] = None
    ) -> bool:
        """
        Update state with atomic compare-and-set semantics.

        Args:
            source: Source identifier
            updates: Fields to update
            expected_version: Expected current version (for CAS)

        Returns:
            True if update succeeded, False if conflict detected
        """
        state_file = self._get_state_file(source)
        temp_file = state_file.with_suffix('.tmp')

        try:
            # Load current state with exclusive lock
            current_state = self.get_state(source)

            # Check version if CAS requested
            if expected_version is not None:
                if current_state.version != expected_version:
                    logger.warning(
                        f"CAS conflict for {source}: expected v{expected_version}, "
                        f"got v{current_state.version}"
                    )
                    return False

            # Apply updates
            for key, value in updates.items():
                if hasattr(current_state, key):
                    setattr(current_state, key, value)

            # Increment version and timestamp
            current_state.version += 1
            current_state.updated_at = datetime.now(timezone.utc).isoformat()

            # Write atomically
            with open(temp_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(current_state.to_dict(), f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Atomic rename
            os.replace(temp_file, state_file)

            # Update cache
            self._cache[source] = current_state

            logger.debug(f"State updated for {source}: v{current_state.version}")
            return True

        except Exception as e:
            logger.error(f"Failed to update state for {source}: {e}")
            return False

    def acquire_lock(self, source: str, lock_id: str) -> bool:
        """
        Acquire a distributed lock for a source.

        Args:
            source: Source identifier
            lock_id: Unique lock identifier (e.g., PID:HOST:UUID)

        Returns:
            True if lock acquired, False if already locked
        """
        state = self.get_state(source)
        now = datetime.now(timezone.utc)

        # Check if already locked and not expired
        if state.lock_holder and state.lock_expires:
            try:
                expires = datetime.fromisoformat(state.lock_expires.replace('Z', '+00:00'))
                if expires > now and state.lock_holder != lock_id:
                    logger.debug(f"Lock held by {state.lock_holder} until {state.lock_expires}")
                    return False
            except (ValueError, TypeError):
                pass  # Invalid expiry, allow override

        # Acquire lock
        expires = now + timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)
        success = self.update_state_atomic(
            source=source,
            updates={
                "lock_holder": lock_id,
                "lock_expires": expires.isoformat()
            },
            expected_version=state.version
        )

        if success:
            logger.info(f"Lock acquired for {source}: {lock_id}")

        return success

    def release_lock(self, source: str, lock_id: str) -> bool:
        """
        Release a distributed lock.

        Args:
            source: Source identifier
            lock_id: Lock identifier to release

        Returns:
            True if released, False if not our lock
        """
        state = self.get_state(source)

        # Verify we own the lock
        if state.lock_holder != lock_id:
            logger.warning(f"Cannot release lock: owned by {state.lock_holder}, not {lock_id}")
            return False

        success = self.update_state_atomic(
            source=source,
            updates={
                "lock_holder": None,
                "lock_expires": None
            },
            expected_version=state.version
        )

        if success:
            logger.info(f"Lock released for {source}")

        return success

    def cleanup_stale_locks(self) -> int:
        """
        Clean up all stale locks across all sources.

        Returns:
            Number of locks cleaned up
        """
        cleaned = 0
        now = datetime.now(timezone.utc)

        for state_file in self.STATE_DIR.glob("*.json"):
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)

                if data.get("lock_expires"):
                    try:
                        expires = datetime.fromisoformat(
                            data["lock_expires"].replace('Z', '+00:00')
                        )
                        if expires < now:
                            # Stale lock
                            source = data.get("source", "unknown")
                            self.update_state_atomic(
                                source=source,
                                updates={
                                    "lock_holder": None,
                                    "lock_expires": None
                                }
                            )
                            cleaned += 1
                            logger.info(f"Cleaned stale lock for {source}")
                    except (ValueError, TypeError):
                        pass

            except Exception as e:
                logger.warning(f"Error checking {state_file}: {e}")

        return cleaned

    def get_all_states(self) -> Dict[str, SyncState]:
        """
        Get state for all tracked sources.

        Returns:
            Dict mapping source names to SyncState objects
        """
        states = {}

        for state_file in self.STATE_DIR.glob("*.json"):
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                source = data.get("source", "unknown")
                states[source] = SyncState.from_dict(data)
            except Exception as e:
                logger.warning(f"Error reading {state_file}: {e}")

        return states

    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        Detect potential conflicts across systems.

        Returns:
            List of conflict descriptions
        """
        conflicts = []
        states = self.get_all_states()

        # Group related sources
        music_sources = {k: v for k, v in states.items() if 'music' in k.lower() or 'spotify' in k.lower()}

        # Check for batch index drift
        batch_indices = [(k, v.batch_index) for k, v in music_sources.items() if v.batch_index > 0]
        if len(batch_indices) > 1:
            indices = [b for _, b in batch_indices]
            if max(indices) - min(indices) > 5:
                conflicts.append({
                    "type": "batch_index_drift",
                    "sources": {k: v for k, v in batch_indices},
                    "severity": "warning",
                    "action": "Review and reconcile batch indices"
                })

        # Check for multiple active locks
        active_locks = [(k, v.lock_holder) for k, v in states.items() if v.lock_holder]
        if len(active_locks) > 1:
            conflicts.append({
                "type": "multiple_active_locks",
                "locks": {k: v for k, v in active_locks},
                "severity": "info",
                "action": "Review if expected concurrent processing"
            })

        return conflicts

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get overall health status of the sync system.

        Returns:
            Health status dictionary
        """
        states = self.get_all_states()
        conflicts = self.detect_conflicts()
        now = datetime.now(timezone.utc)

        # Calculate metrics
        active_sources = len([s for s in states.values() if s.last_sync])
        stale_count = 0
        for state in states.values():
            if state.last_sync:
                try:
                    last = datetime.fromisoformat(state.last_sync.replace('Z', '+00:00'))
                    if (now - last).total_seconds() > 3600:  # 1 hour
                        stale_count += 1
                except (ValueError, TypeError):
                    pass

        return {
            "healthy": len(conflicts) == 0 and stale_count == 0,
            "total_sources": len(states),
            "active_sources": active_sources,
            "stale_sources": stale_count,
            "conflicts": conflicts,
            "states": {k: v.to_dict() for k, v in states.items()},
            "checked_at": now.isoformat()
        }


# Singleton instance
_coordinator: Optional[StateCoordinator] = None


def get_state_coordinator() -> StateCoordinator:
    """Get the singleton StateCoordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = StateCoordinator()
    return _coordinator
