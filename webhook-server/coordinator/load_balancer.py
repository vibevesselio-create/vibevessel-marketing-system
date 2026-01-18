"""
Load Balancer
=============

Selects a target node for a unit of work based on a strategy.
"""

from __future__ import annotations

from typing import List, Optional

from .node_registry import NodeInfo


class LoadBalancer:
    def __init__(self, strategy: str = "round_robin"):
        self.strategy = strategy
        self._rr_index = 0

    def select_node(self, nodes: List[NodeInfo]) -> Optional[NodeInfo]:
        if not nodes:
            return None

        if self.strategy == "least_loaded":
            # Prefer smallest known queue_depth; unknowns go last.
            def key(n: NodeInfo):
                return (n.queue_depth is None, n.queue_depth if n.queue_depth is not None else 10**9)

            return sorted(nodes, key=key)[0]

        # Default: round_robin across the passed-in list.
        idx = self._rr_index % len(nodes)
        self._rr_index += 1
        return nodes[idx]

