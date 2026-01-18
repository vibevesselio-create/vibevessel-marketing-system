"""
Webhook Dashboard Service

FastAPI-based dashboard backend providing WebSocket feed and REST API endpoints
for real-time status, Execution-Log statistics, and aggregated metrics.
"""

import asyncio
import json
import os
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.request import Request as UrlRequest, urlopen

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
import uvicorn

# Import notification system
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))
from shared_core.notifications.event_schema import NotificationEvent, EventSeverity, EventStatus

# Import Execution-Logs integration
try:
    from notion_client import Client
    from shared_core.notion.db_id_resolver import get_database_id
    import os
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    EXECUTION_LOGS_AVAILABLE = bool(NOTION_TOKEN)
    if EXECUTION_LOGS_AVAILABLE:
        notion_client = Client(auth=NOTION_TOKEN)
    else:
        notion_client = None
except ImportError:
    EXECUTION_LOGS_AVAILABLE = False
    notion_client = None
    print("⚠️ Execution-Logs integration not available")


class DashboardService:
    """
    Dashboard backend service providing real-time status and metrics.
    
    Features:
    - WebSocket feed for real-time updates
    - REST API endpoints for status/metrics
    - Execution-Logs aggregation
    - In-memory cache + SQLite persistence
    - run_id correlation enforcement
    """
    
    def __init__(
        self,
        port: int = 5003,
        cache_ttl: int = 300,  # 5 minutes
        db_path: Optional[Path] = None
    ):
        """
        Initialize dashboard service.
        
        Args:
            port: Port for FastAPI server
            cache_ttl: Cache TTL in seconds
            db_path: Path to SQLite database (default: ~/.webhook_dashboard/dashboard.db)
        """
        self.port = port
        self.cache_ttl = cache_ttl
        default_db_path = (
            Path(__file__).resolve().parents[1]
            / "var"
            / "state"
            / "webhook_dashboard"
            / "dashboard.db"
        )
        self.db_path = db_path or default_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # API key for event ingest
        self.api_key = os.getenv("WEBHOOK_DASHBOARD_API_KEY")
        self.api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
        if not self.api_key:
            print("⚠️ WEBHOOK_DASHBOARD_API_KEY not set; POST /dashboard/api/event will reject requests (503)")
        
        # In-memory cache
        self.cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        
        # WebSocket connections
        self.active_connections: List[WebSocket] = []
        
        # Event history (for recent events display)
        self.recent_events: deque = deque(maxlen=100)

        # Multi-node coordinator integration (optional)
        self.coordinator_nodes_url = os.getenv(
            "WEBHOOK_COORDINATOR_NODES_URL",
            "http://localhost:5001/coordinator/nodes",
        )
        
        # FastAPI app
        self.app = FastAPI(title="Webhook Dashboard Service")
        self._setup_routes()
        
        # Background tasks
        self.cleanup_task: Optional[asyncio.Task] = None
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        async def _require_api_key(x_api_key: Optional[str] = Depends(self.api_key_header)):
            """Require API key for POST ingest"""
            if not self.api_key:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="API key not configured (set WEBHOOK_DASHBOARD_API_KEY)"
                )
            if not x_api_key or x_api_key != self.api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing API key"
                )
            return True
        
        @self.app.get("/dashboard/api/status")
        async def get_status():
            """Get overall system status"""
            return await self._get_status_summary()
        
        @self.app.get("/dashboard/api/execution-logs")
        async def get_execution_logs(limit: int = 10, status: Optional[str] = None):
            """Get recent Execution-Log entries"""
            return await self._get_execution_logs(limit=limit, status=status)
        
        @self.app.get("/dashboard/api/metrics")
        async def get_metrics(timeframe: str = "1h"):
            """Get aggregated metrics"""
            return await self._get_metrics(timeframe=timeframe)
        
        @self.app.get("/dashboard/api/webhook-queue")
        async def get_webhook_queue():
            """Get webhook queue status"""
            return await self._get_webhook_queue_status()

        @self.app.get("/dashboard/api/nodes")
        async def get_nodes():
            """Get multi-node status (MM1/MM2/cloud)"""
            return await self._get_nodes_status()

        @self.app.get("/dashboard/api/performance")
        async def get_performance(timeframe: str = "1h"):
            """Get multi-node performance summary derived from ingested events"""
            return await self._get_performance(timeframe=timeframe)

        @self.app.get("/dashboard/api/errors")
        async def get_errors(limit: int = 50):
            """Get recent errors across nodes"""
            return await self._get_errors(limit=limit)
        
        @self.app.websocket("/dashboard/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await self._handle_websocket(websocket)
        
        @self.app.post("/dashboard/api/event")
        async def receive_event(event: dict, _: bool = Depends(_require_api_key)):
            """Receive event from webhook server"""
            await self._process_event(event)
            return {"status": "received"}
    
    async def _get_status_summary(self) -> Dict[str, Any]:
        """Get overall system status summary"""
        # Get cached status or compute
        cache_key = "status_summary"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        # Compute status
        execution_logs = await self._get_execution_logs(limit=100)
        
        # Calculate overall status
        if not execution_logs:
            overall_status = "unknown"
        else:
            # Determine status from recent logs
            recent_statuses = [log.get("status") for log in execution_logs[:10]]
            if any(s == "Error" for s in recent_statuses):
                overall_status = "unhealthy"
            elif any(s == "Partial" for s in recent_statuses):
                overall_status = "degraded"
            else:
                overall_status = "healthy"
        
        # Count active runs
        active_runs = sum(1 for log in execution_logs if log.get("status") == "Running")
        
        # Get last error
        last_error = next(
            (log for log in execution_logs if log.get("status") == "Error"),
            None
        )
        
        status_summary = {
            "overall_status": overall_status,
            "active_runs": active_runs,
            "last_error": last_error,
            "timestamp": datetime.utcnow().isoformat(),
            "recent_logs": [
                {
                    "script_name": event.get("script_name", "Unknown"),
                    "status": event.get("status", "unknown"),
                    "run_id": event.get("run_id", ""),
                    "timestamp": event.get("timestamp", datetime.utcnow().isoformat()),
                }
                for event in list(self.recent_events)[-10:]
            ],
        }
        
        # Cache result
        self.cache[cache_key] = status_summary
        self.cache_timestamps[cache_key] = datetime.utcnow()
        
        return status_summary
    
    async def _get_execution_logs(self, limit: int = 10, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent Execution-Log entries"""
        if not EXECUTION_LOGS_AVAILABLE or not notion_client:
            return []
        
        try:
            # Query Execution-Logs database
            db_id = get_database_id("Execution-Logs")
            
            # Build filter
            filter_dict = {}
            if status:
                filter_dict = {
                    "property": "Status",
                    "select": {"equals": status}
                }
            
            # Query Notion database
            response = notion_client.databases.query(
                database_id=db_id,
                filter=filter_dict if filter_dict else None,
                sorts=[{
                    "property": "Start Time",
                    "direction": "descending"
                }],
                page_size=limit
            )
            
            # Format for dashboard
            formatted_logs = []
            for page in response.get("results", []):
                props = page.get("properties", {})
                
                # Extract properties
                run_id = ""
                if "Run ID" in props:
                    rich_text = props["Run ID"].get("rich_text", [])
                    if rich_text:
                        run_id = rich_text[0].get("plain_text", "")
                
                script_name = ""
                if "Script" in props and props["Script"].get("relation"):
                    # Would need to fetch related page for name
                    script_name = "Unknown"
                
                status_value = ""
                if "Status" in props:
                    select = props["Status"].get("select")
                    if select:
                        status_value = select.get("name", "")
                
                start_time = None
                if "Start Time" in props:
                    date = props["Start Time"].get("date")
                    if date:
                        start_time = date.get("start")
                
                end_time = None
                if "End Time" in props:
                    date = props["End Time"].get("date")
                    if date:
                        end_time = date.get("start")
                
                summary = ""
                if "Plain-English Summary" in props:
                    rich_text = props["Plain-English Summary"].get("rich_text", [])
                    if rich_text:
                        summary = rich_text[0].get("plain_text", "")
                
                formatted_logs.append({
                    "id": page.get("id"),
                    "run_id": run_id,
                    "script_name": script_name,
                    "status": status_value,
                    "start_time": start_time,
                    "end_time": end_time,
                    "summary": summary,
                    "checklist_status": {}  # Would need to parse Performance Metrics JSON
                })
            
            return formatted_logs
            
        except Exception as e:
            print(f"⚠️ Failed to query Execution-Logs: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _get_metrics(self, timeframe: str = "1h") -> Dict[str, Any]:
        """Get aggregated metrics"""
        cache_key = f"metrics_{timeframe}"
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]
        
        # Parse timeframe
        hours = self._parse_timeframe(timeframe)
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Get execution logs for timeframe
        execution_logs = await self._get_execution_logs(limit=1000)
        filtered_logs = [
            log for log in execution_logs
            if log.get("start_time") and datetime.fromisoformat(log["start_time"]) >= start_time
        ]
        
        # Calculate metrics
        total = len(filtered_logs)
        success = sum(1 for log in filtered_logs if log.get("status") == "Success")
        failed = sum(1 for log in filtered_logs if log.get("status") == "Failed")
        partial = sum(1 for log in filtered_logs if log.get("status") == "Partial")
        
        success_rate = success / total if total > 0 else 0.0
        error_rate = failed / total if total > 0 else 0.0
        
        # Calculate average execution time
        execution_times = []
        for log in filtered_logs:
            if log.get("start_time") and log.get("end_time"):
                try:
                    start = datetime.fromisoformat(log["start_time"])
                    end = datetime.fromisoformat(log["end_time"])
                    duration = (end - start).total_seconds()
                    execution_times.append(duration)
                except:
                    pass
        
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
        
        metrics = {
            "timeframe": timeframe,
            "total_executions": total,
            "success_count": success,
            "failed_count": failed,
            "partial_count": partial,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "avg_execution_time_seconds": avg_execution_time,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Cache result
        self.cache[cache_key] = metrics
        self.cache_timestamps[cache_key] = datetime.utcnow()
        
        return metrics
    
    async def _get_webhook_queue_status(self) -> Dict[str, Any]:
        """Get webhook queue status"""
        # This would integrate with webhook server's queue
        # For now, return placeholder
        return {
            "queue_depth": 0,
            "processing": False,
            "last_processed": None
        }

    async def _fetch_json(self, url: str, timeout_s: int = 3) -> Optional[Dict[str, Any]]:
        def _do() -> Optional[Dict[str, Any]]:
            try:
                req = UrlRequest(url, headers={"Accept": "application/json"})
                with urlopen(req, timeout=timeout_s) as resp:  # nosec - operator-configured URL
                    body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body) if body else {}
            except Exception:
                return None

        return await asyncio.to_thread(_do)

    async def _get_nodes_status(self) -> Dict[str, Any]:
        """
        Prefer MM1 coordinator view; fall back to deriving from recent ingested events.
        """
        now = datetime.utcnow().isoformat()
        coord = await self._fetch_json(self.coordinator_nodes_url)
        if coord and coord.get("ok") and isinstance(coord.get("nodes"), list):
            return {"timestamp": now, "source": "coordinator", "nodes": coord.get("nodes")}

        # Fallback: derive from recent ingested events (node_id field)
        nodes: Dict[str, Dict[str, Any]] = {}
        for e in list(self.recent_events):
            node_id = (e.get("node_id") or e.get("__node_id") or "unknown").lower()
            nodes.setdefault(node_id, {"node_id": node_id, "last_seen": None, "status": "unknown", "recent_errors": 0})
            nodes[node_id]["last_seen"] = e.get("timestamp") or nodes[node_id]["last_seen"]
            if e.get("error"):
                nodes[node_id]["recent_errors"] += 1
                nodes[node_id]["status"] = "unhealthy"
            else:
                if nodes[node_id]["status"] != "unhealthy":
                    nodes[node_id]["status"] = e.get("status") or "healthy"

        return {"timestamp": now, "source": "events", "nodes": list(nodes.values())}

    async def _get_performance(self, timeframe: str = "1h") -> Dict[str, Any]:
        """
        Compute lightweight performance metrics from ingested events.
        """
        now = datetime.utcnow()
        seconds = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}.get(timeframe, 3600)
        cutoff = now - timedelta(seconds=seconds)

        per_node: Dict[str, Dict[str, Any]] = {}
        for e in list(self.recent_events):
            ts = e.get("timestamp")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except Exception:
                dt = None
            if dt and dt < cutoff:
                continue

            node_id = (e.get("node_id") or e.get("__node_id") or "unknown").lower()
            per_node.setdefault(
                node_id,
                {"node_id": node_id, "events": 0, "errors": 0, "avg_processing_ms": None, "_durations": []},
            )
            per_node[node_id]["events"] += 1
            if e.get("error"):
                per_node[node_id]["errors"] += 1
            dur = e.get("processing_time_ms") or e.get("duration_ms")
            if isinstance(dur, (int, float)):
                per_node[node_id]["_durations"].append(float(dur))

        for info in per_node.values():
            durs = info.pop("_durations", [])
            if durs:
                info["avg_processing_ms"] = sum(durs) / max(len(durs), 1)

        return {"timestamp": now.isoformat(), "timeframe": timeframe, "by_node": list(per_node.values())}

    async def _get_errors(self, limit: int = 50) -> Dict[str, Any]:
        errors = []
        for e in reversed(list(self.recent_events)):
            if e.get("error"):
                errors.append(e)
            if len(errors) >= limit:
                break
        return {"timestamp": datetime.utcnow().isoformat(), "errors": errors}
    
    async def _handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        
        try:
            # Send initial status
            status = await self._get_status_summary()
            await websocket.send_json({
                "type": "status_update",
                "data": status
            })
            
            # Keep connection alive and send updates
            while True:
                # Wait for client message or timeout
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
        except WebSocketDisconnect:
            self.active_connections.remove(websocket)
    
    async def _process_event(self, event: dict):
        """Process incoming event and broadcast to WebSocket clients"""
        try:
            # Validate event has run_id
            if "run_id" not in event:
                print("⚠️ Event missing run_id - skipping")
                return
            
            # Ensure timestamp present for evidence/logging
            event.setdefault("timestamp", datetime.utcnow().isoformat())
            print(f"↪️ Received event run_id={event.get('run_id')} status={event.get('status')} script={event.get('script_name')}")
            
            # Add to recent events
            self.recent_events.append(event)
            
            # Broadcast to WebSocket clients
            message = {
                "type": "event",
                "data": event,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to all connected clients
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
            
            # Remove disconnected clients
            for connection in disconnected:
                self.active_connections.remove(connection)
            
            # Invalidate cache
            self._invalidate_cache()
            
        except Exception as e:
            print(f"⚠️ Error processing event: {e}")
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cache entry is valid"""
        if key not in self.cache:
            return False
        
        if key not in self.cache_timestamps:
            return False
        
        age = datetime.utcnow() - self.cache_timestamps[key]
        return age.total_seconds() < self.cache_ttl
    
    def _invalidate_cache(self):
        """Invalidate all cache entries"""
        self.cache.clear()
        self.cache_timestamps.clear()
    
    def _parse_timeframe(self, timeframe: str) -> int:
        """Parse timeframe string to hours"""
        if timeframe.endswith("h"):
            return int(timeframe[:-1])
        elif timeframe.endswith("d"):
            return int(timeframe[:-1]) * 24
        else:
            return 1  # Default to 1 hour
    
    async def start(self):
        """Start the dashboard service"""
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Start FastAPI server
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while True:
            try:
                # Clean up old cache entries
                now = datetime.utcnow()
                expired_keys = [
                    key for key, timestamp in self.cache_timestamps.items()
                    if (now - timestamp).total_seconds() > self.cache_ttl * 2
                ]
                for key in expired_keys:
                    self.cache.pop(key, None)
                    self.cache_timestamps.pop(key, None)
                
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                print(f"⚠️ Cleanup loop error: {e}")
                await asyncio.sleep(60)


# Global instance
dashboard_service: Optional[DashboardService] = None


def get_dashboard_service() -> DashboardService:
    """Get or create dashboard service instance"""
    global dashboard_service
    if dashboard_service is None:
        dashboard_service = DashboardService()
    return dashboard_service


# Expose FastAPI app for ASGI runners (uvicorn/gunicorn)
app = get_dashboard_service().app


if __name__ == "__main__":
    service = get_dashboard_service()
    asyncio.run(service.start())
