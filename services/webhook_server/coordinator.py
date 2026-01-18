"""
Multi-node coordinator utilities (MM1 ↔ MM2)
============================================

Duplicate of `webhook-server/coordinator.py` to keep `from coordinator import ...`
imports working in this mirrored server directory.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.request import Request as UrlRequest, urlopen


@dataclass
class Node:
    node_id: str
    base_url: str
    role: str = "worker"
    meta: Dict[str, Any] = field(default_factory=dict)
    healthy: bool = False
    last_checked_at: Optional[str] = None
    last_ok_at: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "base_url": self.base_url,
            "role": self.role,
            "meta": self.meta,
            "healthy": self.healthy,
            "last_checked_at": self.last_checked_at,
            "last_ok_at": self.last_ok_at,
            "last_error": self.last_error,
        }


class NodeRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._nodes: Dict[str, Node] = {}

    def register_or_update(self, *, node_id: str, base_url: str, role: str = "worker", meta: Optional[Dict[str, Any]] = None) -> None:
        if not node_id:
            raise ValueError("node_id is required")
        if not base_url:
            raise ValueError("base_url is required")
        base_url = base_url.rstrip("/")
        with self._lock:
            n = self._nodes.get(node_id)
            if n:
                n.base_url = base_url
                n.role = role or n.role
                if isinstance(meta, dict):
                    n.meta.update(meta)
            else:
                self._nodes[node_id] = Node(node_id=node_id, base_url=base_url, role=role, meta=meta or {})

    def list_nodes(self) -> List[Node]:
        with self._lock:
            return list(self._nodes.values())

    def healthy_nodes(self, *, role: Optional[str] = None) -> List[Node]:
        with self._lock:
            nodes = [n for n in self._nodes.values() if n.healthy]
            if role:
                nodes = [n for n in nodes if n.role == role]
            return nodes

    def set_health(self, node_id: str, *, healthy: bool, checked_at: str, ok_at: Optional[str], error: Optional[str]) -> None:
        with self._lock:
            n = self._nodes.get(node_id)
            if not n:
                return
            n.healthy = healthy
            n.last_checked_at = checked_at
            n.last_ok_at = ok_at if healthy else n.last_ok_at
            n.last_error = error


class LoadBalancer:
    def __init__(self, strategy: str = "round_robin"):
        self.strategy = (strategy or "round_robin").strip().lower()
        self._lock = threading.Lock()
        self._rr_idx = 0

    def select_node(self, nodes: List[Node]) -> Optional[Node]:
        if not nodes:
            return None
        if self.strategy == "round_robin":
            with self._lock:
                idx = self._rr_idx % len(nodes)
                self._rr_idx += 1
                return nodes[idx]
        return nodes[0]


class HealthMonitor:
    def __init__(self, registry: NodeRegistry, *, interval_s: int = 30, timeout_s: int = 5):
        self.registry = registry
        self.interval_s = max(1, int(interval_s))
        self.timeout_s = max(1, int(timeout_s))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HealthMonitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _check_node(self, node: Node) -> None:
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        url = node.base_url.rstrip("/") + "/health"
        try:
            req = UrlRequest(url, headers={"Accept": "application/json"}, method="GET")
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {}
            ok = isinstance(parsed, dict) and parsed.get("status") == "healthy"
            self.registry.set_health(node.node_id, healthy=bool(ok), checked_at=checked_at, ok_at=checked_at if ok else None, error=None if ok else "unhealthy")
        except Exception as e:
            self.registry.set_health(node.node_id, healthy=False, checked_at=checked_at, ok_at=None, error=str(e))

    def _run(self) -> None:
        while not self._stop.is_set():
            nodes = self.registry.list_nodes()
            for n in nodes:
                self._check_node(n)
            self._stop.wait(self.interval_s)

