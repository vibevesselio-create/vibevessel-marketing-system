"""
Webhook Dashboard Service (v2)
==============================

Extends `webhook_dashboard_service.py` with multi-node-aware endpoints:
- /dashboard/api/events
- /dashboard/api/csv-stats

This service is designed to aggregate:
- Ingested runtime events from multiple nodes (local/cloud/gas)
- Execution-Logs summaries (when Notion is available)
- CSV output visibility for operational verification
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn

from webhook_dashboard_service import DashboardService as DashboardServiceV1


class DashboardServiceV2(DashboardServiceV1):
    def _setup_routes(self):
        super()._setup_routes()

        @self.app.get("/dashboard/api/events")
        async def get_events(limit: int = 50):
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "events": list(self.recent_events)[-limit:],
            }

        @self.app.get("/dashboard/api/csv-stats")
        async def get_csv_stats():
            return await self._get_csv_stats()

    async def _get_nodes_status(self) -> Dict[str, Any]:
        """
        Derive a multi-node status view from recent ingested events.
        Expected ingest payload fields:
          - node_id (local|cloud|gas)
          - status (optional)
          - error (optional)
          - timestamp (optional)
        """
        now = datetime.now(timezone.utc)
        nodes: Dict[str, Dict[str, Any]] = {}

        # Initialize known nodes for predictability
        for node_id in ["local", "cloud", "gas"]:
            nodes[node_id] = {
                "node_id": node_id,
                "last_seen": None,
                "status": "unknown",
                "recent_errors": 0,
            }

        for e in list(self.recent_events):
            node_id = (e.get("node_id") or "unknown").lower()
            if node_id not in nodes:
                nodes[node_id] = {"node_id": node_id, "last_seen": None, "status": "unknown", "recent_errors": 0}
            ts = e.get("timestamp")
            if ts:
                nodes[node_id]["last_seen"] = ts
            if e.get("error"):
                nodes[node_id]["recent_errors"] += 1
                nodes[node_id]["status"] = "unhealthy"
            else:
                if nodes[node_id]["status"] != "unhealthy":
                    nodes[node_id]["status"] = e.get("status") or "healthy"

        # Add simple staleness detection (no events in last 15 minutes)
        for node_id, info in nodes.items():
            last_seen = info.get("last_seen")
            if last_seen:
                try:
                    dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    if (now - dt).total_seconds() > 15 * 60:
                        info["status"] = "stale"
                except Exception:
                    pass

        return {"timestamp": now.isoformat(), "nodes": list(nodes.values())}

    async def _get_csv_stats(self) -> Dict[str, Any]:
        """
        Summarize local CSV artifacts for operator verification.
        This is intentionally filesystem-only; Drive visibility should be handled by Drive-backed dashboards.
        """
        now = datetime.now(timezone.utc).isoformat()
        base_dir = Path(os.getenv("WORKSPACE_EVENTS_CSV_DIR", "")).expanduser()
        if not str(base_dir):
            base_dir = Path(__file__).resolve().parents[1] / "var" / "workspace_events_csv"

        stats: Dict[str, Any] = {
            "timestamp": now,
            "base_dir": str(base_dir),
            "files": [],
            "by_node": {},
        }

        if not base_dir.exists():
            return stats

        files = sorted(base_dir.glob("webhook_events_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:200]:
            name = p.name
            node_id = "unknown"
            parts = name.split("_")
            if len(parts) >= 3:
                node_id = parts[2]
            info = {
                "name": name,
                "path": str(p),
                "bytes": p.stat().st_size,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                "node_id": node_id,
            }
            stats["files"].append(info)
            by = stats["by_node"].setdefault(node_id, {"count": 0, "total_bytes": 0, "latest_mtime": None})
            by["count"] += 1
            by["total_bytes"] += info["bytes"]
            if by["latest_mtime"] is None or info["mtime"] > by["latest_mtime"]:
                by["latest_mtime"] = info["mtime"]

        return stats

    async def _get_performance(self, timeframe: str = "1h") -> Dict[str, Any]:
        """
        Compute basic performance metrics from ingested events if they include processing_time_ms.
        """
        now = datetime.now(timezone.utc)
        window_seconds = 3600
        if timeframe.endswith("m"):
            window_seconds = int(timeframe[:-1]) * 60
        elif timeframe.endswith("h"):
            window_seconds = int(timeframe[:-1]) * 3600

        cutoff = now.timestamp() - window_seconds
        samples: List[float] = []

        for e in list(self.recent_events):
            ts = e.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.timestamp() < cutoff:
                    continue
            except Exception:
                continue

            pt = e.get("processing_time_ms")
            if pt is None:
                continue
            try:
                samples.append(float(pt))
            except Exception:
                continue

        if not samples:
            return {"timestamp": now.isoformat(), "timeframe": timeframe, "count": 0}

        samples.sort()
        return {
            "timestamp": now.isoformat(),
            "timeframe": timeframe,
            "count": len(samples),
            "p50_ms": samples[int(len(samples) * 0.50)],
            "p95_ms": samples[int(len(samples) * 0.95) - 1],
            "max_ms": max(samples),
            "min_ms": min(samples),
        }

    async def _get_errors(self, limit: int = 50) -> Dict[str, Any]:
        errs = []
        for e in reversed(list(self.recent_events)):
            if e.get("error"):
                errs.append(e)
            if len(errs) >= limit:
                break
        return {"timestamp": datetime.now(timezone.utc).isoformat(), "errors": errs}


def main():
    port = int(os.getenv("WEBHOOK_DASHBOARD_PORT", "5003"))
    svc = DashboardServiceV2(port=port)
    uvicorn.run(svc.app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()

