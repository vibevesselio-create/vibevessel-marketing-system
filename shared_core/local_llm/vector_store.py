"""
Simple JSON-based Vector Store for MVP
======================================

A minimal vector store implementation for agent task deduplication.
Stores embeddings in a JSON file with cosine similarity search.

This is an MVP implementation - can be upgraded to a proper vector DB
(e.g., ChromaDB, Qdrant, Milvus) once the pattern is validated.

Author: Claude Cowork Agent
Created: 2026-01-19
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SimpleVectorStore:
    """
    JSON-based vector store for task embeddings.

    Features:
    - Cosine similarity search
    - Persistent storage to JSON file
    - Metadata support for each vector
    - Thread-safe file operations

    Usage:
        store = SimpleVectorStore()
        store.add("task_123", embedding, {"title": "My Task"})
        similar = store.search(query_embedding, threshold=0.85)
    """

    DEFAULT_PATH = "~/.local/share/agent-vectors/tasks.json"

    def __init__(self, path: Optional[str] = None):
        """
        Initialize the vector store.

        Args:
            path: Path to the JSON file. Defaults to ~/.local/share/agent-vectors/tasks.json
        """
        self.path = Path(path or self.DEFAULT_PATH).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vectors: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        """Load vectors from JSON file."""
        if self.path.exists():
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} vectors from {self.path}")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load vector store: {e}")
                return {}
        return {}

    def _save(self) -> None:
        """Save vectors to JSON file."""
        try:
            with open(self.path, 'w') as f:
                json.dump(self.vectors, f, indent=2)
            logger.debug(f"Saved {len(self.vectors)} vectors to {self.path}")
        except IOError as e:
            logger.error(f"Failed to save vector store: {e}")
            raise

    def add(
        self,
        task_id: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a vector to the store.

        Args:
            task_id: Unique identifier for the task
            embedding: Vector embedding as a list of floats
            metadata: Optional metadata dict (title, description, etc.)
        """
        self.vectors[task_id] = {
            'embedding': embedding,
            'metadata': metadata or {},
            'added_at': datetime.utcnow().isoformat()
        }
        self._save()
        logger.info(f"Added vector for task {task_id}")

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a vector by task ID.

        Args:
            task_id: The task identifier

        Returns:
            Dict with embedding and metadata, or None if not found
        """
        return self.vectors.get(task_id)

    def remove(self, task_id: str) -> bool:
        """
        Remove a vector from the store.

        Args:
            task_id: The task identifier

        Returns:
            True if removed, False if not found
        """
        if task_id in self.vectors:
            del self.vectors[task_id]
            self._save()
            logger.info(f"Removed vector for task {task_id}")
            return True
        return False

    def search(
        self,
        query_embedding: List[float],
        threshold: float = 0.85,
        top_k: int = 5,
        exclude_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors using cosine similarity.

        Args:
            query_embedding: The query vector
            threshold: Minimum similarity score (0-1)
            top_k: Maximum number of results
            exclude_ids: Task IDs to exclude from results

        Returns:
            List of dicts with task_id, similarity, and metadata
        """
        if not self.vectors:
            return []

        exclude_ids = exclude_ids or []
        query = np.array(query_embedding)
        query_norm = np.linalg.norm(query)

        if query_norm == 0:
            logger.warning("Query embedding has zero norm")
            return []

        results = []
        for task_id, data in self.vectors.items():
            if task_id in exclude_ids:
                continue

            stored = np.array(data['embedding'])
            stored_norm = np.linalg.norm(stored)

            if stored_norm == 0:
                continue

            # Cosine similarity
            similarity = float(np.dot(query, stored) / (query_norm * stored_norm))

            if similarity >= threshold:
                results.append({
                    'task_id': task_id,
                    'similarity': round(similarity, 4),
                    **data.get('metadata', {})
                })

        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]

    def count(self) -> int:
        """Return the number of vectors in the store."""
        return len(self.vectors)

    def clear(self) -> None:
        """Clear all vectors from the store."""
        self.vectors = {}
        self._save()
        logger.info("Cleared vector store")


# Convenience functions for module-level access
_default_store: Optional[SimpleVectorStore] = None


def get_store(path: Optional[str] = None) -> SimpleVectorStore:
    """
    Get or create the default vector store.

    Args:
        path: Optional path override

    Returns:
        SimpleVectorStore instance
    """
    global _default_store
    if _default_store is None or path is not None:
        _default_store = SimpleVectorStore(path)
    return _default_store


def check_duplicate_task(
    description: str,
    threshold: float = 0.85,
    exclude_task_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Check if a task description has duplicates in the store.

    This is the main entry point for task deduplication.

    Args:
        description: The task description to check
        threshold: Similarity threshold (default 0.85)
        exclude_task_id: Optional task ID to exclude (e.g., self)

    Returns:
        List of similar tasks with similarity scores

    Example:
        from shared_core.local_llm import embed
        from shared_core.local_llm.vector_store import check_duplicate_task

        embedding = embed(new_task_description)
        duplicates = check_duplicate_task(new_task_description, threshold=0.85)
        if duplicates:
            print(f"Warning: Found {len(duplicates)} similar tasks")
    """
    # Import here to avoid circular imports
    from . import embed

    try:
        embedding = embed(description)
        store = get_store()

        exclude_ids = [exclude_task_id] if exclude_task_id else None
        similar = store.search(embedding, threshold=threshold, exclude_ids=exclude_ids)

        if similar:
            logger.info(f"Found {len(similar)} similar tasks (threshold={threshold})")

        return similar
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return []


def add_task_embedding(
    task_id: str,
    description: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Add a task's embedding to the vector store.

    Call this when creating a new task to enable future duplicate detection.

    Args:
        task_id: Unique task identifier (e.g., Notion page ID)
        description: Task description text
        metadata: Optional metadata (title, priority, etc.)

    Example:
        add_task_embedding(
            task_id="abc123",
            description="Fix the bug in DriveSheetsSync",
            metadata={"title": "Bug Fix", "priority": "High"}
        )
    """
    from . import embed

    try:
        embedding = embed(description)
        store = get_store()
        store.add(task_id, embedding, metadata)
        logger.info(f"Added embedding for task {task_id}")
    except Exception as e:
        logger.error(f"Failed to add task embedding: {e}")
        raise
