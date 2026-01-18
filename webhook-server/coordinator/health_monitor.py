"""
Health Monitor
==============

Periodically polls registered nodes and updates the in-memory registry.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .node_registry import NodeRegistry


def _get_json(url: str, timeout_s: int = 5) -> Optional[Dict[str, Any]]:
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout_s) as resp:  # nosec - internal-only URLs
            body = resp.read().decode("utf-8", errors="replace")
        return json.loads(body)
    except Exception:
        return None


class HealthMonitor:
    def __init__(
        self,
        registry: NodeRegistry,
        *,
        interval_s: int = 30,
        timeout_s: int = 5,
    ):
        self.registry = registry
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="NodeHealthMonitor")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            nodes = self.registry.list_nodes()
            for n in nodes:
                # Prefer /status, fall back to /health
                status_url = n.base_url.rstrip("/") + "/status"
                health_url = n.base_url.rstrip("/") + "/health"

                payload = _get_json(status_url, timeout_s=self.timeout_s)
                ok = bool(payload)
                if not payload:
                    payload = _get_json(health_url, timeout_s=self.timeout_s)
                    ok = bool(payload)

                self.registry.update_health(node_id=n.node_id, ok=ok, status_payload=payload or {})

            time.sleep(self.interval_s)

