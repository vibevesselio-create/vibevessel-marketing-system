"""
Multi-node Configuration
=======================

Central configuration for coordinating MM1 (coordinator) and MM2 (worker) as well
as optional cloud workers (GitHub Actions).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


def _strtobool(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class NodeConfig:
    node_id: str
    base_url: str
    role: str = "worker"  # worker|coordinator|cloud|gas


@dataclass(frozen=True)
class MultiNodeConfig:
    enabled: bool
    node_id: str
    strategy: str
    health_interval_s: int
    health_timeout_s: int
    mm1_base_url: str
    mm2_base_url: str
    workers: List[NodeConfig]

    @classmethod
    def from_env(cls) -> "MultiNodeConfig":
        node_id = os.getenv("WORKSPACE_EVENTS_NODE_ID") or os.getenv("WEBHOOK_NODE_ID") or "mm1"
        enabled = _strtobool(os.getenv("WEBHOOK_MULTI_NODE_ENABLED", "false"))
        strategy = os.getenv("WEBHOOK_LOAD_BALANCER_STRATEGY", "round_robin")

        mm1_base_url = os.getenv("MM1_BASE_URL", "").rstrip("/") or "http://localhost:5001"
        mm2_base_url = os.getenv("MM2_BASE_URL", "").rstrip("/") or "http://mm2.local:5002"

        health_interval_s = int(os.getenv("WEBHOOK_NODE_HEALTH_INTERVAL_SECONDS", "30") or 30)
        health_timeout_s = int(os.getenv("WEBHOOK_NODE_HEALTH_TIMEOUT_SECONDS", "5") or 5)

        # Additional worker nodes: comma-separated URLs (optional)
        worker_urls = [
            u.strip().rstrip("/")
            for u in (os.getenv("WEBHOOK_WORKER_NODE_URLS", "") or "").split(",")
            if u.strip()
        ]
        workers: List[NodeConfig] = [NodeConfig(node_id="mm2", base_url=mm2_base_url, role="worker")]
        for i, u in enumerate(worker_urls, start=1):
            workers.append(NodeConfig(node_id=f"worker{i}", base_url=u, role="worker"))

        return cls(
            enabled=enabled,
            node_id=node_id,
            strategy=strategy,
            health_interval_s=health_interval_s,
            health_timeout_s=health_timeout_s,
            mm1_base_url=mm1_base_url,
            mm2_base_url=mm2_base_url,
            workers=workers,
        )

