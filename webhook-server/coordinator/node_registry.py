"""
Node Registry
=============

In-memory registry tracking the status/capacity of webhook processing nodes.

Nodes include:
- mm1 (coordinator)
- mm2 (worker)
- cloud (GitHub Actions workers, represented logically)
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NodeInfo:
    node_id: str
    base_url: str
    role: str = "worker"  # worker|coordinator|cloud|gas
    status: str = "unknown"  # healthy|unhealthy|stale|unknown
    last_seen: Optional[str] = None
    queue_depth: Optional[int] = None
    queue_processing: Optional[bool] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NodeRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._nodes: Dict[str, NodeInfo] = {}

    def register_or_update(
        self,
        *,
        node_id: str,
        base_url: str,
        role: str = "worker",
        meta: Optional[Dict[str, Any]] = None,
    ) -> NodeInfo:
        with self._lock:
            info = self._nodes.get(node_id)
            if info is None:
                info = NodeInfo(node_id=node_id, base_url=base_url, role=role)
                self._nodes[node_id] = info
            else:
                info.base_url = base_url or info.base_url
                info.role = role or info.role

            if meta:
                info.meta.update(meta)
            info.last_seen = _utc_iso()
            if info.status in {"unknown", "stale"}:
                info.status = "healthy"
            return info

    def update_health(
        self,
        *,
        node_id: str,
        ok: bool,
        status_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            info = self._nodes.get(node_id)
            if not info:
                return
            info.last_seen = _utc_iso()
            info.status = "healthy" if ok else "unhealthy"
            if status_payload:
                # Common fields
                if "queue_depth" in status_payload:
                    try:
                        info.queue_depth = int(status_payload["queue_depth"])
                    except Exception:
                        pass
                if "queue_processing" in status_payload:
                    info.queue_processing = bool(status_payload["queue_processing"])
                info.meta.update({k: v for k, v in status_payload.items() if k not in {"queue_depth", "queue_processing"}})

    def mark_stale(self, node_id: str) -> None:
        with self._lock:
            info = self._nodes.get(node_id)
            if info:
                info.status = "stale"

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        with self._lock:
            info = self._nodes.get(node_id)
            return NodeInfo(**info.to_dict()) if info else None

    def list_nodes(self, *, role: Optional[str] = None) -> List[NodeInfo]:
        with self._lock:
            nodes = list(self._nodes.values())
            if role:
                nodes = [n for n in nodes if n.role == role]
            return [NodeInfo(**n.to_dict()) for n in nodes]

    def healthy_nodes(self, *, role: Optional[str] = None) -> List[NodeInfo]:
        nodes = self.list_nodes(role=role)
        return [n for n in nodes if n.status == "healthy"]

