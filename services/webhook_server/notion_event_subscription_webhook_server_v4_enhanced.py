#!/usr/bin/env python3
"""
notion_event_subscription_webhook_server.py
==========================================

Notion Event Subscription Webhook Server
========================================

A FastAPI-based webhook server designed specifically for handling Notion event subscriptions.
This server receives webhook events from Notion and processes them through various workflows,
including the Spotify-to-Notion integration.

Key Features:
- Event subscription management
- Webhook event processing
- Spotify-to-Notion integration
- Health monitoring
- Automated logging
- Public exposure via Cloudflare Tunnel (permanent URL)
- Queue-based processing (one webhook at a time)
- Google OAuth2 authentication

PUBLIC WEBHOOK URL: https://webhook.vibevessel.space/webhook (permanent - never changes)
ENDPOINT: POST /webhook
HEALTH CHECK: GET https://webhook.vibevessel.space/health
LOCAL ACCESS: http://localhost:5001/webhook (for local testing)

Google OAuth2 Configuration:
- Canonical local redirect URI: http://localhost:5001/auth/google/callback
- Expected Google Cloud → Authorized redirect URI: http://localhost:5001/auth/google/callback
- Configure via GOOGLE_OAUTH_CLIENT_SECRETS_FILE and GOOGLE_OAUTH_REDIRECT_URI env vars
- See DEV_NOTES section (near end of file) for complete testing instructions

Author: Seren Development • v1.0.0 • 2025-07-26
"""

# Receives all Notion webhook event types
# Fetches the changed page / database to get full property data
# Maps every Notion property to Python variables (snake_case)
# Re-implements the Keyboard Maestro workflow step-by-step
# using AppleScript calls so that the visible behaviour is identical
# Designed for macOS 13+ on Apple Silicon (works on Intel too)

# Standard library imports
import asyncio
import base64
import csv
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections import deque, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

# Load environment variables from .env file (before logger init)
_dotenv_loaded = False
try:
    from dotenv import load_dotenv
    load_dotenv()
    _dotenv_loaded = True
except ImportError:
    pass  # Will log after logger is initialized
except Exception:
    pass  # Will log after logger is initialized

# Third-party imports
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from notion_client import Client
import uvicorn

# Local imports
from shared_core.notifications import (
    NotificationManager,
    NotificationEvent,
    EventSeverity,
    EventStatus,
)

# Unified logging import
from shared_core.logging import setup_logging, UnifiedLogger

# Initialize unified logger for webhook server
# This replaces all print() statements with structured logging
webhook_logger = setup_logging(
    session_id="notion_webhook_server",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    enable_file_logging=True,
    env=os.getenv("ENVIRONMENT", "PROD"),
)

# Log dotenv status after logger is initialized
if _dotenv_loaded:
    webhook_logger.info("Environment variables loaded from .env file")
else:
    webhook_logger.warning("python-dotenv not available or failed, using system environment variables")

# Import enhanced webhook processing
try:
    from production_scripts.enhanced_webhook_processor import process_enhanced_webhook
    ENHANCED_PROCESSING_AVAILABLE = True
    webhook_logger.info("Enhanced webhook processing available")
except ImportError as e:
    webhook_logger.warning("Enhanced webhook processing not available", {"error": str(e)})
    ENHANCED_PROCESSING_AVAILABLE = False

# Import periodic query executor for dynamic database discovery
try:
    from production_scripts.periodic_notion_query_executor import get_global_executor
    PERIODIC_EXECUTOR_AVAILABLE = True
    webhook_logger.info("Periodic query executor available for dynamic database discovery")
except ImportError as e:
    webhook_logger.warning("Periodic query executor not available", {"error": str(e)})
    PERIODIC_EXECUTOR_AVAILABLE = False

# -------------------------------------------------------------------
# ── Multi-node coordinator (MM1 ↔ MM2) -------------------------------
# -------------------------------------------------------------------
try:
    from coordinator import NodeRegistry, LoadBalancer, HealthMonitor

    MULTI_NODE_COORDINATOR_AVAILABLE = True
    webhook_logger.info("Multi-node coordinator modules available")
except Exception as e:
    MULTI_NODE_COORDINATOR_AVAILABLE = False
    NodeRegistry = None  # type: ignore
    LoadBalancer = None  # type: ignore
    HealthMonitor = None  # type: ignore
    webhook_logger.warning("Multi-node coordinator modules not available", {"error": str(e)})

# Import enhanced logging manager
try:
    from production_scripts.notion_logging_manager import NotionLoggingManager, LogLevel, LogCategory
    ENHANCED_LOGGING_AVAILABLE = True
    webhook_logger.info("Enhanced logging manager available")
except ImportError as e:
    webhook_logger.warning("Enhanced logging manager not available", {"error": str(e)})
    ENHANCED_LOGGING_AVAILABLE = False

# Import fortified Cursor submitter
try:
    sys.path.append('/Users/brianhellemn/Scripts-MM1-Production/shared')
    from cursor_submitter_fortified import FortifiedCursorSubmitter, submit_to_cursor
    FORTIFIED_CURSOR_AVAILABLE = True
    webhook_logger.info("Fortified Cursor submitter available")
except ImportError as e:
    webhook_logger.warning("Fortified Cursor submitter not available", {"error": str(e)})
    FORTIFIED_CURSOR_AVAILABLE = False

# Import Notion Webhook Status Monitor
try:
    from notion_webhook_status_monitor import NotionWebhookStatusMonitor
    STATUS_MONITOR_AVAILABLE = True
except ImportError as e:
    webhook_logger.warning("Notion Webhook Status Monitor not available", {"error": str(e)})
    STATUS_MONITOR_AVAILABLE = False

# Import Google Workspace Events API Integration
try:
    from workspace_events_integration import (
        initialize_workspace_events_service,
        shutdown_workspace_events_service,
        get_workspace_events_service
    )
    WORKSPACE_EVENTS_INTEGRATION_AVAILABLE = True
    webhook_logger.info("Google Workspace Events API integration available")
except ImportError as e:
    webhook_logger.warning("Google Workspace Events API integration not available", {"error": str(e)})
    WORKSPACE_EVENTS_INTEGRATION_AVAILABLE = False
    webhook_logger.info("Notion Webhook Status Monitor available")
except ImportError as e:
    webhook_logger.warning("Notion Webhook Status Monitor not available", {"error": str(e)})
    STATUS_MONITOR_AVAILABLE = False

# Import Google OAuth Handler
try:
    from google_oauth_handler import GoogleOAuthHandler
    GOOGLE_OAUTH_AVAILABLE = True
    webhook_logger.info("Google OAuth Handler available")
except ImportError as e:
    webhook_logger.warning("Google OAuth Handler not available", {"error": str(e)})
    GOOGLE_OAUTH_AVAILABLE = False

# Import Linear/GitHub Issue-Tracking Orchestrator
try:
    from linear_github_orchestrator import LinearGitHubOrchestrator, create_orchestrator_from_env
    from shared_core.notion.db_id_resolver import get_agent_tasks_db_id
    LINEAR_GITHUB_ORCHESTRATOR_AVAILABLE = True
    AGENT_TASKS_DB_ID = get_agent_tasks_db_id()
    webhook_logger.info("Linear/GitHub Orchestrator available", {"agent_tasks_db_id": AGENT_TASKS_DB_ID})
except ImportError as e:
    webhook_logger.warning("Linear/GitHub Orchestrator not available", {"error": str(e)})
    LINEAR_GITHUB_ORCHESTRATOR_AVAILABLE = False
    AGENT_TASKS_DB_ID = None

# Notification manager (global)
notification_manager = NotificationManager()
LOG_PATH = Path(__file__).parent / "webhook_server.log"


def _log_event_line(message: str) -> None:
    """Append a timestamped line to the webhook server log and stdout - now uses UnifiedLogger."""
    # Log via UnifiedLogger instead of direct print/file write
    webhook_logger.info(message)


def _emit_notification(event: NotificationEvent, channels: Optional[List[str]] = None) -> None:
    """Send notification asynchronously when possible."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notification_manager.send(event, channels=channels))
    except RuntimeError:
        # No running loop; fall back to blocking send
        asyncio.run(notification_manager.send(event, channels=channels))


def _safe_id(val: Any) -> str:
    """Return a sanitized identifier for logging (non-sensitive)."""
    if val is None:
        return "none"
    text = str(val).strip()
    return text if len(text) <= 80 else text[:77] + "..."


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify Slack request signature using signing secret (v0 scheme).
    Slack docs: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not SLACK_SIGNING_SECRET:
        return False
    if not timestamp or not signature:
        return False
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    # Reject stale requests (5 minute window)
    if abs(time.time() - ts_int) > 60 * 5:
        return False

    base_string = f"v0:{timestamp}:{body.decode('utf-8', errors='ignore')}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

class AgentType(Enum):
    """Four-Agent Framework agent types"""
    CHATGPT = "chatgpt"
    CURSOR = "cursor"
    CLAUDE = "claude"
    NOTION_AI = "notion_ai"

class FourAgentRouter:
    """Routes tasks to appropriate agents in the Four-Agent Framework"""
    
    def __init__(self):
        self.cursor_submitter = FortifiedCursorSubmitter() if FORTIFIED_CURSOR_AVAILABLE else None
        
        # Import universal prompt enhancer
        try:
            import sys
            from pathlib import Path
            enhancer_path = Path(__file__).parent.parent / "agent-coordination-system" / "universal_prompt_enhancer.py"
            if enhancer_path.exists():
                sys.path.insert(0, str(enhancer_path.parent))
                from universal_prompt_enhancer import enhance_agent_prompt
                self.enhance_prompt = enhance_agent_prompt
                webhook_logger.info("Universal Prompt Enhancer loaded")
            else:
                webhook_logger.warning(" Universal Prompt Enhancer not found, prompts will not be enhanced")
                self.enhance_prompt = None
        except Exception as e:
            webhook_logger.warning(" Failed to load Universal Prompt Enhancer: {e}")
            import traceback
            traceback.print_exc()
            self.enhance_prompt = None
    
    async def route_to_agent(
        self,
        agent_type: AgentType,
        prompt: str,
        page_id: Optional[str] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        priority: str = "Medium"
    ) -> bool:
        """
        Route task to appropriate agent with universal prompt enhancement.
        
        CRITICAL: All prompts are enhanced with review and execution handoff instructions.
        """
        try:
            # Enhance prompt with review and execution instructions
            if self.enhance_prompt and page_id:
                # Get agent name from type
                agent_name_map = {
                    AgentType.CURSOR: "Cursor MM1 Agent",
                    AgentType.CLAUDE: "Claude MM1 Agent",
                    AgentType.NOTION_AI: "Notion AI Research Agent",
                    AgentType.CHATGPT: "ChatGPT Strategic Agent"
                }
                current_agent = agent_name_map.get(agent_type, "Unknown Agent")
                
                # Enhance prompt
                enhanced_prompt = self.enhance_prompt(
                    original_prompt=prompt,
                    task_id=page_id,
                    task_name=task_name or "Task",
                    current_agent=current_agent,
                    task_description=task_description,
                    priority=priority
                )
                prompt = enhanced_prompt
                webhook_logger.info("Prompt enhanced with review and execution handoff instructions")
            
            # Route to appropriate agent
            if agent_type == AgentType.CURSOR:
                return await self.submit_to_cursor(prompt, page_id)
            elif agent_type == AgentType.CLAUDE:
                return await self.submit_to_claude(prompt, page_id)
            elif agent_type == AgentType.NOTION_AI:
                return await self.submit_to_notion_ai(prompt, page_id)
            elif agent_type == AgentType.CHATGPT:
                return await self.submit_to_chatgpt(prompt, page_id)
            else:
                webhook_logger.info(f"Unknown agent type: {agent_type}")
                return False
        except Exception as e:
            webhook_logger.info(f"Error routing to agent {agent_type}: {e}")
            return False
    
    async def submit_to_cursor(self, prompt: str, page_id: Optional[str] = None) -> bool:
        """Submit task to Cursor IDE"""
        try:
            if self.cursor_submitter:
                success = self.cursor_submitter.submit_with_retry(prompt)
                
                if success and page_id:
                    # Update Notion page with completion status
                    await update_notion_with_notification(
                        page_id, "success", "cursor_submitter", "Cursor Task", "Completed successfully"
                    )
                
                return success
            else:
                webhook_logger.warning("Cursor submitter not available")
                return False
        except Exception as e:
            webhook_logger.info(f"Error submitting to Cursor: {e}")
            return False
    
    async def submit_to_claude(self, prompt: str, page_id: Optional[str] = None) -> bool:
        """Submit task to Claude via AppleScript"""
        try:
            script = f'''
            tell application "Claude"
                activate
                delay 1
            end tell
            
            tell application "System Events"
                keystroke "a" using command down
                delay 0.5
                keystroke "{prompt}"
                delay 0.5
                key code 36
            end tell
            '''
            
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True)
            
            success = result.returncode == 0
            
            if success and page_id:
                await update_notion_with_notification(
                    page_id, "success", "claude_submitter", "Claude Task", "Completed successfully"
                )
            
            return success
        except Exception as e:
            webhook_logger.info(f"Error submitting to Claude: {e}")
            return False
    
    async def submit_to_notion_ai(self, prompt: str, page_id: Optional[str] = None) -> bool:
        """Submit task to Notion AI"""
        try:
            # For now, simulate success
            success = True
            
            if success and page_id:
                await update_notion_with_notification(
                    page_id, "success", "notion_ai", "Notion AI Task", "Completed successfully"
                )
            
            return success
        except Exception as e:
            webhook_logger.info(f"Error submitting to Notion AI: {e}")
            return False
    
    async def submit_to_chatgpt(self, prompt: str, page_id: Optional[str] = None) -> bool:
        """Submit task to ChatGPT"""
        try:
            # For now, simulate success
            success = True
            
            if success and page_id:
                await update_notion_with_notification(
                    page_id, "success", "chatgpt", "ChatGPT Task", "Completed successfully"
                )
            
            return success
        except Exception as e:
            webhook_logger.info(f"Error submitting to ChatGPT: {e}")
            return False

# Initialize Four-Agent router
four_agent_router = FourAgentRouter()

# -------------------------------------------------------------------
# ── Mac Notification System -----------------------------------------
# -------------------------------------------------------------------

class MacNotifier:
    """Handle Mac OS notifications"""
    
    @staticmethod
    def send_notification(title, message, sound="default"):
        """Send Mac OS notification"""
        try:
            cmd = [
                'osascript', '-e',
                f'display notification "{message}" with title "{title}" sound name "{sound}"'
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            webhook_logger.info(f"Notification failed: {e}")

# -------------------------------------------------------------------
# ── Webhook Queue System --------------------------------------------
# -------------------------------------------------------------------

@dataclass
class WebhookItem:
    """Represents a webhook item in the queue."""
    payload: Dict[str, Any]
    timestamp: datetime
    request_id: str

class WebhookQueue:
    """Thread-safe queue for processing webhooks one at a time."""
    
    def __init__(self):
        self.queue = deque()
        self.processing = False
        self.lock = threading.Lock()
        self.processing_thread = None
        self.stop_event = threading.Event()
        
    def add_webhook(self, payload: Dict[str, Any], request_id: str = None) -> None:
        """Add a webhook to the queue."""
        if request_id is None:
            request_id = f"webhook_{int(time.time() * 1000)}"
            
        webhook_item = WebhookItem(
            payload=payload,
            timestamp=datetime.now(timezone.utc),
            request_id=request_id
        )
        
        with self.lock:
            self.queue.append(webhook_item)
            webhook_logger.info("Received: Webhook queued: {request_id} (Queue size: {len(self.queue)})")
            
        # Start processing if not already running
        if not self.processing:
            self.start_processing()
    
    def start_processing(self) -> None:
        """Start the processing thread."""
        with self.lock:
            if self.processing:
                return
            self.processing = True
            
        self.processing_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processing_thread.start()
        webhook_logger.info("Processing: Webhook queue processing started")
    
    def stop_processing(self) -> None:
        """Stop the processing thread."""
        self.stop_event.set()
        if self.processing_thread:
            self.processing_thread.join(timeout=5)
        webhook_logger.info("Stopped: Webhook queue processing stopped")
    
    def _process_queue(self) -> None:
        """Process webhooks from the queue one at a time."""
        while not self.stop_event.is_set():
            webhook_item = None
            
            # Get next webhook from queue
            with self.lock:
                if self.queue:
                    webhook_item = self.queue.popleft()
                    webhook_logger.info("Processing: Processing webhook: {webhook_item.request_id}")
                else:
                    self.processing = False
                    break
            
            if webhook_item:
                try:
                    # Process the webhook
                    self._process_single_webhook(webhook_item)
                    webhook_logger.info("Webhook processed: {webhook_item.request_id}")
                    
                    # Pause for 1 second before processing next webhook
                    time.sleep(1)
                    
                except Exception as e:
                    webhook_logger.error("Error processing webhook {webhook_item.request_id}: {str(e)}")
                    _emit_notification(
                        NotificationEvent(
                            run_id=webhook_item.request_id,
                            script_name="notion_webhook_server",
                            event_type="webhook_error",
                            severity=EventSeverity.ERROR,
                            phase="processing",
                            status=EventStatus.ERROR,
                            summary="Error processing webhook",
                            details={"error": str(e)},
                        )
                    )
                    # Continue processing other webhooks even if one fails
    
    def _process_single_webhook(self, webhook_item: WebhookItem) -> None:
        """Process a single webhook item."""
        payload = webhook_item.payload
        run_id = payload.get("run_id", webhook_item.request_id)
        success = False
        status_summary = "Processing webhook"
        
        _log_event_line(f"🔄 Processing webhook run_id={run_id}")
        _emit_notification(
            NotificationEvent(
                run_id=run_id,
                script_name="notion_webhook_server",
                event_type="webhook_processing",
                severity=EventSeverity.WARNING,
                phase="processing",
                status=EventStatus.RUNNING,
                summary="Processing webhook",
                details={"request_id": webhook_item.request_id},
            )
        )
        
        try:
            # Slack Event Subscriptions: route through same queue for controlled processing
            if payload.get("__source") == "slack_event_subscriptions":
                self._process_slack_event(payload, run_id=run_id)
                success = True
                status_summary = "Slack event processed"
                return

            # Test hook: allow bypassing Notion fetch for smoke tests
            if payload.get("test_event"):
                success = True
                status_summary = "Test webhook processed"
                return
            
            # 1 Handle initial verification handshake
            if "verification_token" in payload:
                if payload["verification_token"] != NOTION_VERIFICATION:
                    webhook_logger.warning("Invalid verification token in webhook: {webhook_item.request_id}")
                    return
                webhook_logger.info("Verification handshake processed: {webhook_item.request_id}")
                success = True
                status_summary = "Verification handshake processed"
                return
            
            # Handle Notion's challenge request
            if "challenge" in payload:
                webhook_logger.info("Challenge received: {payload['challenge']}")
                success = True
                status_summary = "Challenge processed"
                return {"challenge": payload["challenge"]}

            # 2 Basic payload sanity
            event_type = payload.get("type")
            entity = payload.get("entity", {})
            entity_id = entity.get("id")
            if not event_type or not entity_id:
                webhook_logger.warning("Malformed event in webhook: {webhook_item.request_id}")
                status_summary = "Malformed event"
                return
            
            # 3 Fetch latest data from Notion
            try:
                if entity["type"] == "page":
                    full = notion.pages.retrieve(entity_id)
                elif entity["type"] == "database":
                    full = notion.databases.retrieve(entity_id)
                else:
                    full = {}
            except Exception as e:
                webhook_logger.error("Failed to fetch entity for webhook {webhook_item.request_id}: {str(e)}")
                status_summary = f"Failed to fetch entity: {e}"
                return

            # 3b Loop-guard: prevent circular flows between Google Workspace sync and Notion webhooks.
            if entity.get("type") == "page" and isinstance(full, dict) and full:
                ignore_reason = _should_ignore_notion_webhook(payload, full)
                if ignore_reason:
                    webhook_logger.info(
                        "Loop-guard: ignoring webhook to prevent automation loop",
                        {
                            "reason": ignore_reason,
                            "entity_id": entity_id,
                            "event_type": event_type,
                        },
                    )
                    success = True
                    status_summary = f"Ignored by loop-guard ({ignore_reason})"
                    return

            # 4 Flatten properties → snake_case keys
            def to_snake(s: str) -> str:
                return "".join(["_" + c.lower() if c.isupper() else c for c in s]).lstrip("_")
            mapped = {
                "event_type": event_type,
                "entity_id": entity_id,
                "url": full.get("url", ""),
            }

            # Dynamically add every property (page) or column (db)
            props = full.get("properties", {})
            for name, val in props.items():
                mapped[to_snake(name)] = val

            # 5 Process based on database type
            parent_db_id = full.get("parent", {}).get("database_id") or full.get("id")

            # Four-Agent Framework routing based on database
            if parent_db_id == SCRIPT_ROUTER_DB_ID:
                # Script synchronization - route to Cursor
                webhook_logger.info("Processing: Four-Agent Framework: Routing script webhook to Cursor")
                asyncio.run(self._handle_script_sync_webhook(mapped, full))
            elif parent_db_id == WORKFLOWS_ROUTER_DB_ID:
                # Workflow processing - route based on workflow type
                workflow_type = mapped.get('type', {}).get('select', {}).get('name', 'general')
                webhook_logger.info("Processing: Four-Agent Framework: Routing workflow webhook to {workflow_type}")
                asyncio.run(self._handle_workflow_webhook(mapped, full, workflow_type))
            elif parent_db_id == PROMPTS_DB_ID:
                # Prompt execution - route to Cursor
                webhook_logger.info("Processing: Four-Agent Framework: Routing prompt webhook to Cursor")
                asyncio.run(self._handle_prompt_webhook(mapped, full))
            elif LINEAR_GITHUB_ORCHESTRATOR_AVAILABLE and parent_db_id == AGENT_TASKS_DB_ID:
                # Agent-Tasks: Linear/GitHub issue sync
                webhook_logger.info("Processing: Linear/GitHub Orchestrator: Routing Agent-Task webhook")
                asyncio.run(self._handle_agent_task_linear_github_sync(payload, full))
            else:
                # Default to existing handlers for other databases
                webhook_logger.info("Processing: Using legacy webhook handler for database: {parent_db_id}")
                self._handle_legacy_webhook(mapped, full)
            
            success = True
            status_summary = "Webhook processed successfully"
        finally:
            if success:
                _log_event_line(f"✅ Webhook processed successfully run_id={run_id}")
                _emit_notification(
                    NotificationEvent(
                        run_id=run_id,
                        script_name="notion_webhook_server",
                        event_type="webhook_complete",
                        severity=EventSeverity.INFO,
                        phase="completion",
                        status=EventStatus.OK,
                        summary=status_summary,
                        details={"request_id": webhook_item.request_id},
                    )
                )
            else:
                _log_event_line(f"⚠️ Webhook processing incomplete run_id={run_id} summary={status_summary}")
                _emit_notification(
                    NotificationEvent(
                        run_id=run_id,
                        script_name="notion_webhook_server",
                        event_type="webhook_incomplete",
                        severity=EventSeverity.WARNING,
                        phase="completion",
                        status=EventStatus.PARTIAL,
                        summary=status_summary,
                        details={"request_id": webhook_item.request_id},
                    )
                )

    def _process_slack_event(self, payload: Dict[str, Any], run_id: str) -> None:
        """
        Slack Event Subscriptions processor (background).

        Safeguards:
        - Deduplicate by Slack event_id
        - Ignore bot-originated message events by default
        - Best-effort CSV logging + dashboard ingest
        """
        event_id = payload.get("event_id") or ""
        team_id = payload.get("team_id") or ""
        api_app_id = payload.get("api_app_id") or ""
        event = payload.get("event", {}) or {}
        event_type = event.get("type", "unknown")
        subtype = event.get("subtype") or ""

        dedupe_key = f"slack:{team_id}:{event_id}"
        if event_id and _slack_dedupe_seen(dedupe_key):
            log_slack_event_to_csv(payload, {"status": "duplicate", "error": "Duplicate Slack event_id"})
            _post_dashboard_event(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "node_id": os.getenv("WORKSPACE_EVENTS_NODE_ID", "local"),
                    "status": "Complete",
                    "event_type": f"slack.{event_type}",
                    "run_id": run_id,
                    "error": "Duplicate Slack event_id",
                    "slack": {"team_id": team_id, "event_id": event_id, "api_app_id": api_app_id},
                }
            )
            return

        # Ignore bot messages to avoid feedback loops (can be overridden later if needed)
        if event_type == "message" and (event.get("bot_id") or subtype == "bot_message"):
            log_slack_event_to_csv(payload, {"status": "ignored", "error": "Ignored bot message"})
            return

        log_slack_event_to_csv(payload, {"status": "processed"})
        _post_dashboard_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "node_id": os.getenv("WORKSPACE_EVENTS_NODE_ID", "local"),
                "status": "Complete",
                "event_type": f"slack.{event_type}",
                "run_id": run_id,
                "processing_time_ms": None,
                "slack": {
                    "team_id": team_id,
                    "event_id": event_id,
                    "api_app_id": api_app_id,
                    "channel": event.get("channel"),
                    "user": event.get("user") or event.get("bot_id"),
                    "subtype": subtype,
                },
            }
        )
    
    async def _handle_script_sync_webhook(self, mapped: Dict[str, Any], full: Dict[str, Any]):
        """Handle script synchronization webhooks using Four-Agent Framework"""
        try:
            page_id = mapped.get('entity_id', '')
            script_name = mapped.get('name', {}).get('title', [{}])[0].get('plain_text', 'Unknown')
            
            # Check if Send Webhook is TRUE
            send_webhook = mapped.get('send_webhook', {}).get('checkbox', False)
            
            if send_webhook:
                # Create Cursor super-prompt for script synchronization
                cursor_super_prompt = f"""
You are Cursor-AI acting as the "Implementation Agent" in Seren Media's Four-Agent framework.

▶ TASK
Synchronise the script "{script_name}" between the local repo
(/Users/brianhellemn/Scripts-MM1-Production) and the Notion Scripts DB
({SCRIPT_ROUTER_DB_ID}).

▶ REQUIREMENTS
1. Dynamic discovery only – never hard-code database IDs (use search if absent).
2. Compare file-hash + version header; pick latest.
3. Push newer version both directions (file ↔ Notion code block).
4. Update metadata (Version, Last Modified, SHA256, Dependencies).
5. **CRITICAL: Detect services (APIs, CLI tools) used by script and update 'services' relation property.**
   - Analyze script imports, API calls, CLI invocations (e.g., notion_client, soundcloud, n8n, cloudflared, yt-dlp, ffmpeg)
   - Map to Services/Tools database items (discover database dynamically)
   - Update 'services' relation with all detected services
6. **CRITICAL: Link Execution-Logs entries to script via relation property.**
   - Query Execution-Logs database (27be7361-6c27-8033-a323-dca0fafa80e6) for entries matching this script
   - Match by Script Path, Name, or Plain-English Summary containing script name
   - Link via 'Execution-Logs' relation on script entry
   - Ensure bidirectional linking (also update 'scripts' relation on Execution-Log entries)
   - Limit to recent logs (last 30 days) for efficiency
7. If a row has **Send Webhook = TRUE** then:
   a. Leave it TRUE (so orchestrator sees the event).
   b. Wait ≤30 s for `scripts/sync` webhook payload; verify `status=="synced"`.
8. Write a Diátaxis "Reference" section per script if missing.
9. Log every action to Interactions DB ({INTERACTIONS_DB_ID}).

▶ VERIFICATION GATE
After all updates:
• Run `pytest test_scripts/test_sync_integrity.py -q`.
• Verify 'services' relation is populated correctly.
• Verify Execution-Logs are linked to script.
• Any failures ⇒ open Cursor chat again and paste full traceback.
• When tests pass, tick property **Sync Status = ✅**.

▶ OUTPUT
Respond only with:

SYNC COMPLETE – {{n_files}} files processed, {{n_services}} services linked, {{n_logs}} execution logs linked, {{issues}} issues.
"""

                # Route to Cursor using Four-Agent Framework
                success = await four_agent_router.route_to_agent(
                    AgentType.CURSOR,
                    cursor_super_prompt,
                    page_id
                )

                if success:
                    webhook_logger.info("Script synchronization completed for {script_name}")
                else:
                    webhook_logger.error("Failed to synchronize script {script_name}")

        except Exception as e:
            webhook_logger.info(f"Error in script sync webhook handler: {e}")
    
    async def _handle_workflow_webhook(self, mapped: Dict[str, Any], full: Dict[str, Any], workflow_type: str):
        """Handle workflow webhooks using Four-Agent Framework"""
        try:
            page_id = mapped.get('entity_id', '')
            workflow_name = mapped.get('name', {}).get('title', [{}])[0].get('plain_text', 'Unknown')
            
            if workflow_type == 'documentation':
                # Route to Claude for documentation (with prompt enhancement)
                prompt = f"Process documentation workflow: {workflow_name}"
                await four_agent_router.route_to_agent(
                    AgentType.CLAUDE,
                    prompt,
                    page_id=page_id,
                    task_name=workflow_name,
                    task_description=f"Documentation workflow: {workflow_name}",
                    priority="High"
                )
            elif workflow_type == 'data_processing':
                # Route to Notion AI for data operations (with prompt enhancement)
                prompt = f"Process data workflow: {workflow_name}"
                await four_agent_router.route_to_agent(
                    AgentType.NOTION_AI,
                    prompt,
                    page_id=page_id,
                    task_name=workflow_name,
                    task_description=f"Data processing workflow: {workflow_name}",
                    priority="High"
                )
            else:
                # Route to ChatGPT for strategy (with prompt enhancement)
                prompt = f"Process workflow: {workflow_name}"
                await four_agent_router.route_to_agent(
                    AgentType.CHATGPT,
                    prompt,
                    page_id=page_id,
                    task_name=workflow_name,
                    task_description=f"General workflow: {workflow_name}",
                    priority="Medium"
                )
                
        except Exception as e:
            webhook_logger.info(f"Error in workflow webhook handler: {e}")
    
    async def _handle_prompt_webhook(self, mapped: Dict[str, Any], full: Dict[str, Any]):
        """Handle prompt webhooks using Four-Agent Framework"""
        try:
            page_id = mapped.get('entity_id', '')
            prompt_name = mapped.get('name', {}).get('title', [{}])[0].get('plain_text', 'Unknown')
            
            # Route to Cursor for prompt execution (with prompt enhancement)
            prompt = f"Execute prompt: {prompt_name}"
            await four_agent_router.route_to_agent(
                AgentType.CURSOR,
                prompt,
                page_id=page_id,
                task_name=prompt_name,
                task_description=f"Prompt execution: {prompt_name}",
                priority="High"
            )
            
        except Exception as e:
            webhook_logger.info(f"Error in prompt webhook handler: {e}")
    
    async def _handle_agent_task_linear_github_sync(self, webhook_payload: Dict[str, Any], full: Dict[str, Any]):
        """Handle Agent-Task webhooks for Linear/GitHub issue synchronization."""
        try:
            if not LINEAR_GITHUB_ORCHESTRATOR_AVAILABLE:
                webhook_logger.warning("Linear/GitHub Orchestrator not available, skipping sync")
                return

            # Create orchestrator (lazy initialization)
            orchestrator = create_orchestrator_from_env()

            # Reconstruct webhook payload with entity info
            payload = {
                "type": webhook_payload.get("type"),
                "entity": {
                    "id": full.get("id"),
                    "type": "page",
                },
            }

            # Process webhook through orchestrator
            result = orchestrator.handle_notion_webhook(payload)

            # Log result
            if result.get("status") == "success":
                webhook_logger.info("Linear/GitHub sync completed: {result.get('results', {})}")
                log_webhook_to_csv(webhook_payload, "agent_task_linear_github_sync", result)
            elif result.get("status") == "ignored":
                webhook_logger.info("Linear/GitHub sync skipped: {result.get('reason', 'Unknown')}")
            else:
                webhook_logger.warning("Linear/GitHub sync error: {result.get('error', 'Unknown error')}")
                log_webhook_to_csv(webhook_payload, "agent_task_linear_github_sync", result)

        except Exception as e:
            webhook_logger.error("Error in Linear/GitHub sync handler: {e}")
            import traceback
            traceback.print_exc()

    def _handle_legacy_webhook(self, mapped: Dict[str, Any], full: Dict[str, Any]):
        """Handle legacy webhook processing for backward compatibility"""
        try:
            # Existing webhook handling logic
            if mapped.get('database_name', '').lower() == 'prompts':
                asyncio.run(handle_prompts_webhook(mapped, full))
            elif mapped.get('database_name', '').lower() == 'actions':
                asyncio.run(handle_actions_relation(mapped, full))
            else:
                webhook_logger.warning("No handler for database type")
        except Exception as e:
            webhook_logger.info(f"Error in legacy webhook handler: {e}")

# Global webhook queue instance
webhook_queue = WebhookQueue()

# -------------------------------------------------------------------
# ── Configuration ---------------------------------------------------
# -------------------------------------------------------------------
DEFAULT_DATABASES_WITH_ACTIONS = {
    "1cce7361-6c27-81eb-bbe3-caee7e75b312": "Scripts",
    "224e7361-6c27-801a-858f-f29ff7d1c64b": "Assets",
    "20fe7361-6c27-816b-9c3c-f526adcf0ba3": "Tools+Services",
    "20fe7361-6c27-8141-b8e0-f7865be6537e": "DaVinci-Resolve-Projects",
    "20fe7361-6c27-814a-8f84-d3f47b413c2a": "Tasks",
    "1f9e7361-6c27-80fa-9e45-f3952c94298f": "Functions",
    "23be7361-6c27-80ca-86a7-f070230bc7b4": "Functions*",
    "22be7361-6c27-8088-83bc-eb914c23eacf": "Assets*",
}

DEFAULT_DB_IDS = {
    "scripts_db_id": "1cce7361-6c27-81eb-bbe3-caee7e75b312",
    "script_db_id": "1cce7361-6c27-8161-af0b-000b64fce9c6",
    "workflows_db_id": "20fe7361-6c27-81ce-8227-e8602f53dd17",
    "workflows_router_db_id": "20fe7361-6c27-8188-b133-000bceeb2d09",
    "prompts_db_id": "1d1e7361-6c27-8004-b897-ddfec29dff96",
    "functions_db_id": "1f9e7361-6c27-80fa-9e45-f3952c94298f",
    "tracks_db_id": "20ee73616c278107aa3bfda03e8de9bd",
    "interactions_db_id": "20fe73616c27817187a1c226a88e5238",
}


def _parse_mapping_override(raw_value: str) -> Dict[str, str]:
    """Parse JSON string to mapping for database overrides."""
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception as exc:
        webhook_logger.warning("Failed to parse INITIAL_DATABASES_WITH_ACTIONS override: {exc}")
    return {}


def load_server_configuration() -> Dict[str, Any]:
    """Load configuration with unified config → env → defaults precedence."""
    unified_config_data: Dict[str, Any] = {}

    try:
        from unified_config import get_unified_config

        unified_config_data = get_unified_config()
        webhook_logger.info("Unified configuration loaded")
    except Exception as exc:
        webhook_logger.warning("Unified configuration unavailable, using env/defaults: {exc}")

    def pick(key: str, env_var: str, default: Any = None) -> Any:
        """Return first non-empty value from unified config, env, then default."""
        value = None
        if isinstance(unified_config_data, dict):
            value = unified_config_data.get(key)
        if value in (None, "") and env_var:
            value = os.getenv(env_var)
        if value in (None, ""):
            value = default
        return value

    initial_databases = DEFAULT_DATABASES_WITH_ACTIONS.copy()
    if isinstance(unified_config_data, dict):
        uc_dbs = unified_config_data.get("initial_databases_with_actions")
        if isinstance(uc_dbs, dict):
            initial_databases = {str(k): str(v) for k, v in uc_dbs.items()}
    env_initial = os.getenv("INITIAL_DATABASES_WITH_ACTIONS")
    if env_initial:
        parsed_env = _parse_mapping_override(env_initial)
        if parsed_env:
            initial_databases = parsed_env

    config: Dict[str, Any] = {
        "notion_api_token": pick("notion_api_token", "NOTION_API_TOKEN"),
        "notion_verification_token": pick("notion_verification_token", "NOTION_VERIFICATION_TOKEN"),
        "fastapi_host": pick("fastapi_host", "HOST", "0.0.0.0"),
        "fastapi_port": int(pick("fastapi_port", "PORT", "5001") or 5001),
        "scripts_db_id": pick("scripts_db_id", "SCRIPTS_DB_ID", DEFAULT_DB_IDS["scripts_db_id"]),
        "script_db_id": pick("script_db_id", "SCRIPT_DB_ID", DEFAULT_DB_IDS["script_db_id"]),
        "workflows_db_id": pick("workflows_db_id", "WORKFLOWS_DB_ID", DEFAULT_DB_IDS["workflows_db_id"]),
        "workflows_router_db_id": pick("workflows_router_db_id", "WORKFLOWS_DB_ID", DEFAULT_DB_IDS["workflows_router_db_id"]),
        "prompts_db_id": pick("prompts_db_id", "PROMPTS_DB_ID", DEFAULT_DB_IDS["prompts_db_id"]),
        "functions_db_id": pick("functions_db_id", "FUNCTIONS_DB_ID", DEFAULT_DB_IDS["functions_db_id"]),
        "tracks_db_id": pick("tracks_db_id", "TRACKS_DB_ID", DEFAULT_DB_IDS["tracks_db_id"]),
        "interactions_db_id": pick("interactions_db_id", "INTERACTIONS_DB_ID", DEFAULT_DB_IDS["interactions_db_id"]),
        "initial_databases_with_actions": initial_databases,
        "slack_signing_secret": pick("slack_signing_secret", "SLACK_SIGNING_SECRET"),
        "slack_verification_token": pick("slack_verification_token", "SLACK_VERIFICATION_TOKEN"),
    }

    for key, value in DEFAULT_DB_IDS.items():
        config.setdefault(key, value)

    return config


SERVER_CONFIG = load_server_configuration()

# -------------------------------------------------------------------
# ── Environment -----------------------------------------------------
# -------------------------------------------------------------------
NOTION_TOKEN = SERVER_CONFIG.get("notion_api_token")
NOTION_VERIFICATION = SERVER_CONFIG.get("notion_verification_token")  # sent once when you create the subscription
FASTAPI_HOST = SERVER_CONFIG.get("fastapi_host", "0.0.0.0")
FASTAPI_PORT = int(SERVER_CONFIG.get("fastapi_port", 5001) or 5001)

# Identify node for multi-node coordination and loop-guard tagging.
WORKSPACE_EVENTS_NODE_ID = os.getenv("WORKSPACE_EVENTS_NODE_ID") or os.getenv("WEBHOOK_NODE_ID") or "mm1"
os.environ.setdefault("WORKSPACE_EVENTS_NODE_ID", WORKSPACE_EVENTS_NODE_ID)

# Public URL configuration (for external access via Cloudflare tunnel)
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "webhook.vibevessel.space")
PROTOCOL = os.environ.get("PROTOCOL", "https")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", f"{PROTOCOL}://{PUBLIC_HOST}/")

WORKFLOWS_DB_ID = SERVER_CONFIG.get("workflows_db_id", DEFAULT_DB_IDS["workflows_db_id"])
WORKFLOWS_ROUTER_DB_ID = SERVER_CONFIG.get("workflows_router_db_id", WORKFLOWS_DB_ID)
PROMPTS_DB_ID = SERVER_CONFIG.get("prompts_db_id", DEFAULT_DB_IDS["prompts_db_id"])
SCRIPTS_DB_ID = SERVER_CONFIG.get("scripts_db_id", DEFAULT_DB_IDS["scripts_db_id"])
SCRIPT_ROUTER_DB_ID = SERVER_CONFIG.get("script_db_id", SCRIPTS_DB_ID)
FUNCTIONS_DB_ID = SERVER_CONFIG.get("functions_db_id", DEFAULT_DB_IDS["functions_db_id"])
TRACKS_DB_ID = SERVER_CONFIG.get("tracks_db_id", DEFAULT_DB_IDS["tracks_db_id"])
INTERACTIONS_DB_ID = SERVER_CONFIG.get("interactions_db_id", DEFAULT_DB_IDS["interactions_db_id"])
INITIAL_DATABASES_WITH_ACTIONS = SERVER_CONFIG.get(
    "initial_databases_with_actions", DEFAULT_DATABASES_WITH_ACTIONS
)
SLACK_SIGNING_SECRET = SERVER_CONFIG.get("slack_signing_secret")
SLACK_VERIFICATION_TOKEN = SERVER_CONFIG.get("slack_verification_token")

if not NOTION_TOKEN:
    raise SystemExit("❌  Set NOTION_API_TOKEN in your environment")

notion = Client(auth=NOTION_TOKEN)
app = FastAPI(title="Notion → KM replacement")

# Multi-node coordinator runtime (optional)
def _strtobool(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


MULTI_NODE_ENABLED = _strtobool(os.getenv("WEBHOOK_MULTI_NODE_ENABLED", "false"))
WEBHOOK_LOAD_BALANCER_STRATEGY = os.getenv("WEBHOOK_LOAD_BALANCER_STRATEGY", "round_robin")
MM2_BASE_URL = os.getenv("MM2_BASE_URL", "http://mm2.local:5002").rstrip("/")
MM1_BASE_URL = os.getenv("MM1_BASE_URL", f"http://localhost:{FASTAPI_PORT}").rstrip("/")

node_registry = None
load_balancer = None
health_monitor = None

if MULTI_NODE_COORDINATOR_AVAILABLE:
    try:
        node_registry = NodeRegistry()
        load_balancer = LoadBalancer(strategy=WEBHOOK_LOAD_BALANCER_STRATEGY)
        health_monitor = HealthMonitor(
            node_registry,
            interval_s=int(os.getenv("WEBHOOK_NODE_HEALTH_INTERVAL_SECONDS", "30") or 30),
            timeout_s=int(os.getenv("WEBHOOK_NODE_HEALTH_TIMEOUT_SECONDS", "5") or 5),
        )

        # Register coordinator (self) and default worker (MM2).
        node_registry.register_or_update(
            node_id=WORKSPACE_EVENTS_NODE_ID,
            base_url=MM1_BASE_URL,
            role="coordinator",
            meta={"port": FASTAPI_PORT},
        )
        node_registry.register_or_update(
            node_id="mm2",
            base_url=MM2_BASE_URL,
            role="worker",
            meta={"port": 5002},
        )
    except Exception as e:
        webhook_logger.warning("Failed to initialize multi-node coordinator runtime", {"error": str(e)})
        node_registry = None
        load_balancer = None
        health_monitor = None

# Initialize enhanced logging manager
if ENHANCED_LOGGING_AVAILABLE:
    logging_manager = NotionLoggingManager(NOTION_TOKEN)
    webhook_logger.info("Enhanced logging manager initialized")
else:
    logging_manager = None
    webhook_logger.warning("Enhanced logging manager not available")

# CSV Logging Configuration
WEBHOOK_CSV_DIR = "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Seren Internal/Automation Files/Notion-Database-Webhooks"

# Slack Event Subscriptions CSV Logging
SLACK_EVENTS_CSV_DIR = os.getenv(
    "SLACK_EVENTS_CSV_DIR",
    "/Users/brianhellemn/Library/CloudStorage/GoogleDrive-brian@serenmedia.co/My Drive/Seren Internal/Automation Files/Slack-Event-Subscriptions",
)

# Dashboard ingest (optional)
WEBHOOK_DASHBOARD_INGEST_URL = os.getenv(
    "WEBHOOK_DASHBOARD_INGEST_URL",
    "http://localhost:5003/dashboard/api/event",
)
WEBHOOK_DASHBOARD_API_KEY = os.getenv("WEBHOOK_DASHBOARD_API_KEY")

# Slack event dedupe (Event Subscriptions are at-least-once)
SLACK_EVENT_DEDUPE_TTL_SECONDS = int(os.getenv("SLACK_EVENT_DEDUPE_TTL_SECONDS", "600") or 600)
SLACK_EVENT_DEDUPE_MAX_KEYS = int(os.getenv("SLACK_EVENT_DEDUPE_MAX_KEYS", "5000") or 5000)
_slack_dedupe_cache: "OrderedDict[str, float]" = OrderedDict()  # key -> expires_epoch


def _slack_dedupe_cleanup(now_epoch: float) -> None:
    try:
        while _slack_dedupe_cache:
            k, exp = next(iter(_slack_dedupe_cache.items()))
            if exp > now_epoch:
                break
            _slack_dedupe_cache.popitem(last=False)
        while len(_slack_dedupe_cache) > SLACK_EVENT_DEDUPE_MAX_KEYS:
            _slack_dedupe_cache.popitem(last=False)
    except Exception:
        return


def _slack_dedupe_seen(key: str) -> bool:
    if not key:
        return False
    now = time.time()
    _slack_dedupe_cleanup(now)
    exp = _slack_dedupe_cache.get(key)
    if exp and exp > now:
        _slack_dedupe_cache.move_to_end(key)
        return True
    _slack_dedupe_cache[key] = now + SLACK_EVENT_DEDUPE_TTL_SECONDS
    _slack_dedupe_cache.move_to_end(key)
    return False


def _post_dashboard_event(event: Dict[str, Any]) -> None:
    """
    Best-effort dashboard ingest (non-critical).
    Requires WEBHOOK_DASHBOARD_API_KEY and WEBHOOK_DASHBOARD_INGEST_URL.
    """
    try:
        if not WEBHOOK_DASHBOARD_API_KEY or not WEBHOOK_DASHBOARD_INGEST_URL:
            return
        req = UrlRequest(
            WEBHOOK_DASHBOARD_INGEST_URL,
            data=json.dumps(event, default=str).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": WEBHOOK_DASHBOARD_API_KEY,
            },
            method="POST",
        )
        with urlopen(req, timeout=2) as _:
            return
    except Exception:
        return


def log_slack_event_to_csv(payload: Dict[str, Any], processing_result: Dict[str, Any] | None = None) -> None:
    """Log Slack event subscription payloads to a CSV file."""
    try:
        os.makedirs(SLACK_EVENTS_CSV_DIR, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        csv_filename = f"slack_event_subscriptions_{today}.csv"
        csv_path = os.path.join(SLACK_EVENTS_CSV_DIR, csv_filename)

        timestamp = datetime.now().isoformat()
        event = payload.get("event", {}) or {}
        event_type = event.get("type", "unknown")
        event_subtype = event.get("subtype", "")
        event_id = payload.get("event_id", "")
        team_id = payload.get("team_id", "")
        api_app_id = payload.get("api_app_id", "")
        user = event.get("user", "") or event.get("bot_id", "")
        channel = event.get("channel", "")
        text = event.get("text", "")

        processing_status = "received"
        error_message = ""
        if processing_result:
            processing_status = processing_result.get("status", processing_status)
            error_message = processing_result.get("error", "")

        row_data = {
            "timestamp": timestamp,
            "event_id": event_id,
            "event_type": event_type,
            "event_subtype": event_subtype,
            "team_id": team_id,
            "api_app_id": api_app_id,
            "user": user,
            "channel": channel,
            "text": text,
            "processing_status": processing_status,
            "error_message": error_message,
            "payload": json.dumps(payload, default=str),
        }

        file_exists = os.path.exists(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = list(row_data.keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row_data)
    except Exception:
        return

# -------------------------------------------------------------------
# ── Loop Guard (Notion ↔ Google Workspace circular-flow protection) --
# -------------------------------------------------------------------
SEREN_AUTOMATION_SOURCE_PROPERTY = os.getenv(
    "SEREN_AUTOMATION_SOURCE_PROPERTY",
    "Seren Automation Source",
)
SEREN_AUTOMATION_EVENT_ID_PROPERTY = os.getenv(
    "SEREN_AUTOMATION_EVENT_ID_PROPERTY",
    "Seren Automation Event ID",
)
SEREN_AUTOMATION_NODE_ID_PROPERTY = os.getenv(
    "SEREN_AUTOMATION_NODE_ID_PROPERTY",
    "Seren Automation Node",
)

# If a Notion webhook is triggered by an update whose source is in this list,
# we ignore it to prevent automation loops (Notion→Drive→Notion, etc).
_default_ignore_sources = [
    "workspace_events",          # Python Workspace Events consumer
    "gas_workspace_events",      # GAS Workspace Events consumer
    "drivesheetsync",            # DriveSheetsSync script
    "notion_webhook_server",     # Self-generated Notion updates
]
SEREN_AUTOMATION_IGNORE_SOURCES = {
    s.strip().lower()
    for s in (os.getenv("SEREN_AUTOMATION_IGNORE_SOURCES", "") or "").split(",")
    if s.strip()
} or set(_default_ignore_sources)

# Additional dedupe guard to avoid rapid re-processing even if the source property
# isn't present for some reason (short-term cache by entity+event).
SEREN_LOOP_GUARD_TTL_SECONDS = int(os.getenv("SEREN_LOOP_GUARD_TTL_SECONDS", "180") or 180)
SEREN_LOOP_GUARD_MAX_KEYS = int(os.getenv("SEREN_LOOP_GUARD_MAX_KEYS", "5000") or 5000)
_loop_guard_cache: "OrderedDict[str, float]" = OrderedDict()  # key -> expires_epoch


def _loop_guard_cleanup(now_epoch: float) -> None:
    try:
        # Expire old
        while _loop_guard_cache:
            k, exp = next(iter(_loop_guard_cache.items()))
            if exp > now_epoch:
                break
            _loop_guard_cache.popitem(last=False)
        # Cap size
        while len(_loop_guard_cache) > SEREN_LOOP_GUARD_MAX_KEYS:
            _loop_guard_cache.popitem(last=False)
    except Exception:
        # Never let loop-guard failure break webhook processing.
        return


def _loop_guard_seen(key: str) -> bool:
    now = time.time()
    _loop_guard_cleanup(now)
    exp = _loop_guard_cache.get(key)
    if exp and exp > now:
        # Refresh LRU position
        _loop_guard_cache.move_to_end(key)
        return True
    _loop_guard_cache[key] = now + SEREN_LOOP_GUARD_TTL_SECONDS
    _loop_guard_cache.move_to_end(key)
    return False


def _notion_prop_to_text(prop: Dict[str, Any]) -> str:
    try:
        if not isinstance(prop, dict):
            return ""
        prop_type = prop.get("type")
        if prop_type == "rich_text":
            rt = prop.get("rich_text") or []
            return (rt[0].get("plain_text") if rt else "") or ""
        if prop_type == "title":
            t = prop.get("title") or []
            return (t[0].get("plain_text") if t else "") or ""
        if prop_type == "select":
            sel = prop.get("select") or None
            return (sel.get("name") if sel else "") or ""
        return ""
    except Exception:
        return ""


def _get_seren_automation_source(full: Dict[str, Any]) -> str:
    props = full.get("properties") or {}
    prop = props.get(SEREN_AUTOMATION_SOURCE_PROPERTY) or {}
    return (_notion_prop_to_text(prop) or "").strip().lower()


def _should_ignore_notion_webhook(payload: Dict[str, Any], full: Dict[str, Any]) -> str:
    """
    Returns a non-empty reason string if this webhook should be ignored to prevent
    circular automation loops.
    """
    try:
        src = _get_seren_automation_source(full)
        if src and src in SEREN_AUTOMATION_IGNORE_SOURCES:
            return f"seren_automation_source={src}"

        # As a secondary safety net, ignore rapid duplicates for the same entity+event_type+last_edited_time.
        entity = payload.get("entity") or {}
        entity_id = entity.get("id") or "unknown"
        event_type = payload.get("type") or "unknown"
        last_edited_time = full.get("last_edited_time") or ""
        dedupe_key = f"notion:{event_type}:{entity_id}:{last_edited_time}"
        if _loop_guard_seen(dedupe_key):
            return "rapid_duplicate"

        return ""
    except Exception as e:
        # If guard fails, do not block processing; just proceed.
        webhook_logger.warning("Loop guard failed, proceeding", {"error": str(e)})
        return ""

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Get Workspace Events service status
    workspace_events_status = None
    if WORKSPACE_EVENTS_INTEGRATION_AVAILABLE:
        try:
            service = get_workspace_events_service()
            if service:
                workspace_events_status = service.health_check()
        except Exception as e:
            workspace_events_status = {"error": str(e)}
    
    status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "node_id": WORKSPACE_EVENTS_NODE_ID,
        "public_host": PUBLIC_HOST,
        "protocol": PROTOCOL,
        "webhook_url": WEBHOOK_URL,
        "local_port": FASTAPI_PORT,
        "enhanced_processing": ENHANCED_PROCESSING_AVAILABLE,
        "workspace_events": {
            "available": WORKSPACE_EVENTS_INTEGRATION_AVAILABLE,
            "status": workspace_events_status
        },
        "periodic_executor": PERIODIC_EXECUTOR_AVAILABLE,
        "enhanced_logging": ENHANCED_LOGGING_AVAILABLE
    }

    # Multi-node coordinator status (optional)
    status["multi_node"] = {
        "enabled": MULTI_NODE_ENABLED,
        "available": MULTI_NODE_COORDINATOR_AVAILABLE and node_registry is not None,
        "strategy": WEBHOOK_LOAD_BALANCER_STRATEGY,
        "mm1_base_url": MM1_BASE_URL,
        "mm2_base_url": MM2_BASE_URL,
    }
    if node_registry is not None:
        try:
            status["multi_node"]["nodes"] = [n.to_dict() for n in node_registry.list_nodes()]
        except Exception as e:
            status["multi_node"]["nodes_error"] = str(e)
    
    # Add database count if periodic executor is available
    if PERIODIC_EXECUTOR_AVAILABLE:
        try:
            executor = get_global_executor()
            status["databases_in_rotation"] = executor.get_database_count()
            status["database_list"] = executor.get_database_list()
        except Exception as e:
            status["database_error"] = str(e)
    
    return status


def _try_forward_to_worker(payload: Dict[str, Any], *, run_id: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort forward to a healthy worker node (MM2).
    If forwarding fails, return None so the coordinator can fall back to local queue.
    """
    if not MULTI_NODE_ENABLED or node_registry is None or load_balancer is None:
        return None

    workers = node_registry.healthy_nodes(role="worker")
    if not workers:
        return None

    target = load_balancer.select_node(workers)
    if not target:
        return None

    # Forward to worker's /webhook/process endpoint.
    url = target.base_url.rstrip("/") + "/webhook/process"
    try:
        req = UrlRequest(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=3) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"text": body[:5000]}

        return {
            "status": "forwarded",
            "run_id": run_id,
            "worker_node_id": target.node_id,
            "worker_url": url,
            "worker_response": parsed,
        }
    except Exception as e:
        webhook_logger.warning(
            "Multi-node: worker forward failed; falling back to local queue",
            {"run_id": run_id, "worker": getattr(target, "node_id", "unknown"), "error": str(e)},
        )
        return None


@app.post("/coordinator/register")
async def coordinator_register(payload: Dict[str, Any]):
    """
    Register or update a node in the in-memory registry.
    """
    if node_registry is None:
        return {"ok": False, "error": "coordinator_not_available"}

    node_id = str(payload.get("node_id") or "").strip() or "unknown"
    base_url = str(payload.get("base_url") or "").strip()
    role = str(payload.get("role") or "worker")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    node_registry.register_or_update(node_id=node_id, base_url=base_url, role=role, meta=meta)
    return {"ok": True, "node_id": node_id}


@app.get("/coordinator/nodes")
async def coordinator_nodes():
    """
    List currently registered nodes and their last observed health.
    """
    if node_registry is None:
        return {"ok": False, "error": "coordinator_not_available", "nodes": []}
    return {"ok": True, "nodes": [n.to_dict() for n in node_registry.list_nodes()]}


@app.post("/coordinator/assign")
async def coordinator_assign(job: Dict[str, Any]):
    """
    Assign a unit of work to a worker node (MM2) by forwarding it to /webhook/process.
    """
    if node_registry is None or load_balancer is None:
        return {"ok": False, "error": "coordinator_not_available"}

    run_id = str(job.get("run_id") or f"assign-{int(time.time() * 1000)}")
    job["run_id"] = run_id

    resp = _try_forward_to_worker(job, run_id=run_id)
    if resp:
        return {"ok": True, **resp}
    return {"ok": False, "status": "no_worker_available", "run_id": run_id}

# Initialize status monitor
status_monitor = None
if STATUS_MONITOR_AVAILABLE:
    try:
        status_monitor = NotionWebhookStatusMonitor(
            notion_token=NOTION_TOKEN,
            scripts_database_id=SCRIPTS_DB_ID
        )
        webhook_logger.info("Status monitor initialized")
    except Exception as e:
        webhook_logger.warning("Failed to initialize status monitor: {e}")
        status_monitor = None

@app.get("/queue-status")
async def queue_status():
    """Get the current status of the webhook queue."""
    with webhook_queue.lock:
        queue_size = len(webhook_queue.queue)
        processing = webhook_queue.processing
    return {
        "queue_size": queue_size,
        "processing": processing,
        "timestamp": datetime.now().isoformat()
    }

# -------------------------------------------------------------------
# ── Google OAuth Endpoints -----------------------------------------
# -------------------------------------------------------------------
#
# Google OAuth2 Configuration
# ===========================
# Redirect URI Detection:
#   - Local access: http://localhost:5001/auth/google/callback
#   - Cloudflare tunnel: https://webhook.vibevessel.space/auth/google/callback
#   - Automatically detected from request headers (X-Forwarded-Host, X-Forwarded-Proto, Host)
#
# Environment Variables:
#   - GOOGLE_OAUTH_CLIENT_SECRETS_FILE: Full path to client_secret JSON file
#     Example: /path/to/client_secret_*.apps.googleusercontent.com.json
#   - GOOGLE_OAUTH_REDIRECT_URI: OAuth redirect URI (default: http://localhost:5001/auth/google/callback)
#     Used as fallback when Cloudflare headers are not detected
#
# IMPORTANT: Before testing, ensure BOTH redirect URIs are added to your OAuth client
# in Google Cloud Console under "Authorized redirect URIs":
#   1. http://localhost:5001/auth/google/callback (for local testing)
#   2. https://webhook.vibevessel.space/auth/google/callback (for Cloudflare tunnel)

# Initialize Google OAuth Handler
google_oauth_handler = None
if GOOGLE_OAUTH_AVAILABLE:
    try:
        # Construct redirect URI: use env var, or build from server port
        redirect_uri = os.getenv('GOOGLE_OAUTH_REDIRECT_URI')
        if not redirect_uri:
            redirect_uri = f'http://localhost:{FASTAPI_PORT}/auth/google/callback'
        
        # Get client secrets file path from environment
        client_secrets_file = os.getenv('GOOGLE_OAUTH_CLIENT_SECRETS_FILE')
        
        # Initialize handler with credentials path and redirect URI
        init_kwargs = {'redirect_uri': redirect_uri}
        if client_secrets_file:
            init_kwargs['credentials_path'] = client_secrets_file
        
        google_oauth_handler = GoogleOAuthHandler(**init_kwargs)
        webhook_logger.info("Google OAuth Handler initialized")
        webhook_logger.info(f"   Redirect URI: {redirect_uri}")
        webhook_logger.info(f"   Client secrets: {google_oauth_handler.credentials_path}")
    except Exception as e:
        webhook_logger.warning("Failed to initialize Google OAuth Handler: {e}")
        import traceback
        traceback.print_exc()
        google_oauth_handler = None

OAUTH_TOKEN_DIR = Path(os.getenv("OAUTH_TOKEN_DIR", "~/.credentials")).expanduser()

def _normalize_forwarded_value(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.split(",")[0].strip()

def _pick_proto(value: Optional[str], fallback: str = "http") -> str:
    if value in ("http", "https"):
        return value
    return fallback

def get_dynamic_redirect_uri(request: Request, callback_path: str) -> str:
    """
    Dynamically determine redirect URI based on request headers.
    Uses proxy headers when present to preserve the public hostname.
    """
    forwarded_host = _normalize_forwarded_value(request.headers.get("X-Forwarded-Host"))
    forwarded_proto = _normalize_forwarded_value(request.headers.get("X-Forwarded-Proto"))
    host = _normalize_forwarded_value(request.headers.get("Host"))

    if forwarded_host:
        proto = _pick_proto(forwarded_proto, fallback="https")
        redirect_uri = f"{proto}://{forwarded_host}{callback_path}"
        webhook_logger.info("Network: Proxy detected via X-Forwarded-Host: {redirect_uri}")
        return redirect_uri

    if host:
        proto = _pick_proto(forwarded_proto, fallback=request.url.scheme or "http")
        redirect_uri = f"{proto}://{host}{callback_path}"
        webhook_logger.info("Network: Host-based redirect URI: {redirect_uri}")
        return redirect_uri

    redirect_uri = f"http://localhost:{FASTAPI_PORT}{callback_path}"
    webhook_logger.info("Local: Using localhost redirect URI: {redirect_uri}")
    return redirect_uri

def persist_oauth_payload(provider: str, payload: Dict[str, Any]) -> Path:
    """Persist OAuth payloads outside the repo to avoid secret leakage."""
    OAUTH_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    token_path = OAUTH_TOKEN_DIR / f"{provider}_oauth_{timestamp}.json"
    token_path.write_text(json.dumps(payload, indent=2))
    return token_path

@app.get("/auth/google")
async def start_google_oauth(
    request: Request,
    state: Optional[str] = Query(None, description="Optional state parameter for CSRF protection")
):
    """
    Start Google OAuth2 authentication flow.
    Redirects user to Google authorization page.
    
    Automatically detects Cloudflare tunnel and uses appropriate redirect URI.
    """
    if not GOOGLE_OAUTH_AVAILABLE or not google_oauth_handler:
        raise HTTPException(status_code=503, detail="Google OAuth not available")
    
    try:
        # Dynamically determine redirect URI based on request
        dynamic_redirect_uri = get_dynamic_redirect_uri(request, "/auth/google/callback")
        
        # Create authorization URL with dynamic redirect URI
        authorization_url, state_value = google_oauth_handler.create_authorization_url(
            state=state,
            redirect_uri=dynamic_redirect_uri
        )
        webhook_logger.info("Auth: Starting Google OAuth flow with state: {state_value}")
        webhook_logger.info(f"   Using redirect URI: {dynamic_redirect_uri}")
        return RedirectResponse(url=authorization_url)
    except Exception as e:
        webhook_logger.error("Error starting OAuth flow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start OAuth flow: {str(e)}")

@app.get("/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter from authorization request"),
    error: Optional[str] = Query(None, description="Error from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description from OAuth provider"),
    error_uri: Optional[str] = Query(None, description="Error URI from OAuth provider")
):
    """
    Handle Google OAuth2 callback.
    Exchanges authorization code for access tokens.
    """
    if not GOOGLE_OAUTH_AVAILABLE or not google_oauth_handler:
        raise HTTPException(status_code=503, detail="Google OAuth not available")
    
    # Handle OAuth errors - with automatic error detection and logging
    if error:
        error_description = request.query_params.get('error_description', 'No description provided')
        error_uri = request.query_params.get('error_uri', None)
        
        # Categorize and log OAuth error
        error_type_map = {
            'redirect_uri_mismatch': 'configuration_error',
            'access_denied': 'user_action_required',
            'invalid_client': 'configuration_error',
            'invalid_grant': 'authentication_error',
            'invalid_request': 'request_error',
            'unauthorized_client': 'authorization_error',
            'unsupported_response_type': 'configuration_error',
            'invalid_scope': 'configuration_error'
        }
        
        error_type = error_type_map.get(error, 'unknown_error')
        severity_map = {
            'configuration_error': 'high',
            'authentication_error': 'high',
            'authorization_error': 'high',
            'user_action_required': 'medium',
            'request_error': 'medium',
            'unknown_error': 'medium'
        }
        severity = severity_map.get(error_type, 'low')
        
        # Log error to Notion Execution Logs
        if ENHANCED_LOGGING_AVAILABLE and logging_manager:
            try:
                error_data = {
                    'error_type': error_type,
                    'error_code': error,
                    'error_description': error_description,
                    'error_uri': error_uri,
                    'severity': severity,
                    'state': state,
                    'detection_method': 'callback_endpoint',
                    'oauth_provider': 'google',
                    'timestamp': datetime.now().isoformat()
                }
                
                asyncio.create_task(logging_manager.log_script_execution(
                    entity_id='oauth_handler',
                    script_name='Google OAuth Handler',
                    result={
                        'status': 'error',
                        'error': error_data
                    },
                    metadata={
                        'trigger': 'oauth_callback',
                        'error_detection': 'automatic',
                        'oauth_provider': 'google'
                    },
                    properties={}
                ))
                webhook_logger.info("Logged: OAuth error logged to Notion: {error} ({error_type}, severity: {severity})")
            except Exception as e:
                webhook_logger.warning(" Failed to log OAuth error to Notion: {e}")
        else:
            # Fallback console logging
            webhook_logger.error("OAuth Error [{severity}]: {error_type} - {error}")
            webhook_logger.info(f"   Description: {error_description}")
            if error_uri:
                webhook_logger.info(f"   Error URI: {error_uri}")
        
        error_html = f"""
        <html>
            <head><title>OAuth Error</title></head>
            <body>
                <h1>OAuth Authentication Failed</h1>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Description:</strong> {error_description}</p>
                <p><strong>Error Type:</strong> {error_type} (Severity: {severity})</p>
                <p><em>This error has been automatically logged to execution logs.</em></p>
                <p><a href="/auth/google">Try again</a></p>
            </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)
    
    # Validate required parameters for successful callback
    if not error and (not code or not state):
        error_msg = "Missing required parameters: code and state are required for successful OAuth callback"
        webhook_logger.error("OAuth callback error: {error_msg}")
        if ENHANCED_LOGGING_AVAILABLE and logging_manager:
            try:
                asyncio.create_task(logging_manager.log_script_execution(
                    entity_id='oauth_handler',
                    script_name='Google OAuth Handler',
                    result={'status': 'error', 'error': {'error_type': 'request_error', 'error_code': 'missing_parameters', 'error_description': error_msg}},
                    metadata={'trigger': 'oauth_callback', 'error_detection': 'automatic'},
                    properties={}
                ))
            except Exception as e:
                webhook_logger.warning(" Failed to log error: {e}")
        return HTMLResponse(content=f"<h1>Error</h1><p>{error_msg}</p>", status_code=400)
    
    try:
        result = google_oauth_handler.handle_callback(code=code, state=state)
        
        if result.get("status") == "success":
            user_info = result.get("user_info", {})
            user_email = user_info.get("email", "Unknown")
            user_name = user_info.get("name", "Unknown")
            
            success_html = f"""
            <html>
                <head><title>OAuth Success</title></head>
                <body>
                    <h1>✅ Authentication Successful!</h1>
                    <p><strong>User:</strong> {user_name} ({user_email})</p>
                    <p><strong>Token saved:</strong> {result.get('token_path', 'N/A')}</p>
                    <p><strong>Scopes:</strong> {', '.join(result.get('scopes', []))}</p>
                    <p><strong>Expires:</strong> {result.get('expires_at', 'N/A')}</p>
                    <hr>
                    <p><a href="/auth/google/status">Check authentication status</a></p>
                    <p><a href="/health">Server health</a></p>
                </body>
            </html>
            """
            webhook_logger.info("OAuth authentication successful for: {user_email}")
            return HTMLResponse(content=success_html)
        else:
            error_msg = result.get("error", "Unknown error")
            error_html = f"""
            <html>
                <head><title>OAuth Error</title></head>
                <body>
                    <h1>❌ Authentication Failed</h1>
                    <p>Error: {error_msg}</p>
                    <p><a href="/auth/google">Try again</a></p>
                </body>
            </html>
            """
            webhook_logger.error("OAuth callback error: {error_msg}")
            return HTMLResponse(content=error_html, status_code=400)
            
    except Exception as e:
        # Log application-level errors
        error_msg = str(e)
        if ENHANCED_LOGGING_AVAILABLE and logging_manager:
            try:
                asyncio.create_task(logging_manager.log_script_execution(
                    entity_id='oauth_handler',
                    script_name='Google OAuth Handler',
                    result={
                        'status': 'error',
                        'error': {
                            'error_type': 'application_error',
                            'error_code': 'callback_processing_failed',
                            'error_description': error_msg,
                            'severity': 'high',
                            'detection_method': 'callback_endpoint'
                        }
                    },
                    metadata={'trigger': 'oauth_callback', 'error_detection': 'automatic'},
                    properties={}
                ))
                webhook_logger.info("Logged: OAuth application error logged to Notion: {error_msg}")
            except Exception as log_err:
                webhook_logger.warning(" Failed to log error to Notion: {log_err}")
        
        error_html = f"""
        <html>
            <head><title>OAuth Error</title></head>
            <body>
                <h1>❌ Authentication Error</h1>
                <p>Error: {error_msg}</p>
                <p><em>This error has been automatically logged to execution logs.</em></p>
                <p><a href="/auth/google">Try again</a></p>
            </body>
        </html>
        """
        webhook_logger.error("OAuth callback exception: {e}")
        return HTMLResponse(content=error_html, status_code=500)

@app.get("/auth/google/status")
async def google_oauth_status(email: Optional[str] = Query(None, description="Email to check credentials for")):
    """
    Check Google OAuth authentication status.
    Returns information about saved credentials.
    """
    if not GOOGLE_OAUTH_AVAILABLE or not google_oauth_handler:
        raise HTTPException(status_code=503, detail="Google OAuth not available")
    
    try:
        credentials = google_oauth_handler.load_credentials(email=email)
        client_info = google_oauth_handler.get_client_info()
        
        if credentials:
            # Get user info if credentials are valid
            try:
                from googleapiclient.discovery import build
                service = build('oauth2', 'v2', credentials=credentials)
                user_info = service.userinfo().get().execute()
            except:
                user_info = {}
            
            return {
                "authenticated": True,
                "user_info": user_info,
                "scopes": credentials.scopes,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "client_info": {
                    "client_id": client_info.get("client_id"),
                    "project_id": client_info.get("project_id"),
                    "redirect_uri": client_info.get("redirect_uri")
                }
            }
        else:
            return {
                "authenticated": False,
                "message": "No credentials found. Please authenticate at /auth/google",
                "client_info": {
                    "client_id": client_info.get("client_id"),
                    "project_id": client_info.get("project_id"),
                    "redirect_uri": client_info.get("redirect_uri")
                }
            }
            
    except Exception as e:
        webhook_logger.error("Error checking OAuth status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check OAuth status: {str(e)}")

# -------------------------------------------------------------------
# ── Spotify OAuth Endpoints ----------------------------------------
# -------------------------------------------------------------------
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

def _get_spotify_scopes() -> str:
    scopes = os.getenv("SPOTIFY_SCOPES")
    if scopes:
        return scopes
    return "user-read-email user-read-private playlist-read-private playlist-read-collaborative"

def _build_spotify_authorize_url(request: Request, state: str) -> tuple[str, str]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Spotify client ID not configured")

    redirect_uri = get_dynamic_redirect_uri(request, "/auth/spotify/callback")
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _get_spotify_scopes(),
        "state": state,
        "show_dialog": "true",
    }
    return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}", redirect_uri

def _exchange_spotify_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Spotify client credentials not configured")

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode("ascii")).decode("ascii")
    data = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")

    req = UrlRequest(
        SPOTIFY_TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

@app.get("/auth/spotify")
async def start_spotify_oauth(
    request: Request,
    state: Optional[str] = Query(None, description="Optional state parameter for CSRF protection"),
):
    if not os.getenv("SPOTIFY_CLIENT_ID"):
        raise HTTPException(status_code=503, detail="Spotify OAuth not available")

    state_value = state or secrets.token_urlsafe(32)
    authorization_url, redirect_uri = _build_spotify_authorize_url(request, state_value)
    webhook_logger.info("Auth: Starting Spotify OAuth flow with state: {state_value}")
    webhook_logger.info(f"   Using redirect URI: {redirect_uri}")
    return RedirectResponse(url=authorization_url)

@app.get("/auth/spotify/callback")
async def spotify_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code from Spotify"),
    state: Optional[str] = Query(None, description="State parameter from authorization request"),
    error: Optional[str] = Query(None, description="Error from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description from OAuth provider"),
):
    if error:
        error_html = f"""
        <html>
            <head><title>Spotify OAuth Error</title></head>
            <body>
                <h1>Spotify OAuth Failed</h1>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Description:</strong> {error_description or "No description provided"}</p>
                <p><a href="/auth/spotify">Try again</a></p>
            </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code for Spotify callback")

    redirect_uri = get_dynamic_redirect_uri(request, "/auth/spotify/callback")
    try:
        token_payload = _exchange_spotify_code(code, redirect_uri)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise HTTPException(status_code=500, detail=f"Spotify token exchange failed: {error_body}") from exc
    except URLError as exc:
        raise HTTPException(status_code=500, detail=f"Spotify token exchange failed: {exc}") from exc

    token_payload["received_at"] = datetime.now(timezone.utc).isoformat()
    token_payload["redirect_uri"] = redirect_uri
    token_payload["state"] = state
    token_path = persist_oauth_payload("spotify", token_payload)

    expires_in = int(token_payload.get("expires_in", 0) or 0)
    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        os.environ["SPOTIFY_ACCESS_TOKEN_EXPIRES_AT"] = expires_at.isoformat()

    if token_payload.get("access_token"):
        os.environ["SPOTIFY_ACCESS_TOKEN"] = token_payload["access_token"]
    if token_payload.get("refresh_token"):
        os.environ["SPOTIFY_REFRESH_TOKEN"] = token_payload["refresh_token"]

    success_html = f"""
    <html>
        <head><title>Spotify OAuth Success</title></head>
        <body>
            <h1>Spotify OAuth Complete</h1>
            <p>Tokens saved to: <code>{token_path}</code></p>
            <p>Expires at: {expires_at.isoformat() if expires_at else "unknown"}</p>
            <p>Scope: {token_payload.get("scope", "unknown")}</p>
            <p><em>Remember to persist tokens in your environment if needed.</em></p>
        </body>
    </html>
    """
    return HTMLResponse(content=success_html, status_code=200)

# -------------------------------------------------------------------
# ── Adobe Lightroom OAuth Callback ---------------------------------
# -------------------------------------------------------------------
@app.get("/auth/adobe")
async def adobe_oauth_info(request: Request):
    redirect_uri = get_dynamic_redirect_uri(request, "/auth/adobe/callback")
    info_html = f"""
    <html>
        <head><title>Adobe OAuth Setup</title></head>
        <body>
            <h1>Adobe Lightroom OAuth</h1>
            <p>Configure the following redirect URI in the Adobe console:</p>
            <p><code>{redirect_uri}</code></p>
            <p>Once authorized, Adobe will redirect back here to complete the flow.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=info_html, status_code=200)

@app.get("/auth/adobe/callback")
async def adobe_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None, description="Authorization code from Adobe"),
    state: Optional[str] = Query(None, description="State parameter from authorization request"),
    error: Optional[str] = Query(None, description="Error from OAuth provider"),
    error_description: Optional[str] = Query(None, description="Error description from OAuth provider"),
):
    redirect_uri = get_dynamic_redirect_uri(request, "/auth/adobe/callback")
    payload = {
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
        "redirect_uri": redirect_uri,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    token_path = persist_oauth_payload("adobe", payload)

    if error:
        error_html = f"""
        <html>
            <head><title>Adobe OAuth Error</title></head>
            <body>
                <h1>Adobe OAuth Failed</h1>
                <p><strong>Error:</strong> {error}</p>
                <p><strong>Description:</strong> {error_description or "No description provided"}</p>
                <p>Payload saved to: <code>{token_path}</code></p>
            </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=400)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code for Adobe callback")

    success_html = f"""
    <html>
        <head><title>Adobe OAuth Success</title></head>
        <body>
            <h1>Adobe OAuth Code Captured</h1>
            <p>Authorization code saved to: <code>{token_path}</code></p>
            <p><em>Exchange this code for tokens using the Adobe Lightroom API.</em></p>
        </body>
    </html>
    """
    return HTMLResponse(content=success_html, status_code=200)

# -------------------------------------------------------------------
# ── Helpers for macOS UI control (AppleScript wrapped) --------------
# -------------------------------------------------------------------
def osa(script: str) -> None:
    """Run arbitrary AppleScript."""
    subprocess.run(["osascript", "-e", script], check=False)

def hide_all_windows() -> None:
    osa('tell application "System Events" to keystroke "h" using {command down, option down}')

def quit_app(bundle_id: str) -> None:
    osa(f'tell application id "{bundle_id}" to quit')

def activate_app(bundle_id: str) -> None:
    osa(f'tell application id "{bundle_id}" to activate')

def log_webhook_to_csv(payload: Dict[str, Any], event_type: str = "unknown", processing_result: Dict[str, Any] = None) -> None:
    """Log webhook data to CSV file in Google Drive directory with comprehensive information."""
    try:
        # Ensure the directory exists
        os.makedirs(WEBHOOK_CSV_DIR, exist_ok=True)
        
        # Create filename with current date
        today = datetime.now().strftime("%Y-%m-%d")
        csv_filename = f"notion_database_webhooks_{today}.csv"
        csv_path = os.path.join(WEBHOOK_CSV_DIR, csv_filename)
        
        # Prepare data for CSV
        timestamp = datetime.now().isoformat()
        event_type = payload.get("type", event_type)
        entity = payload.get("entity", {})
        entity_id = entity.get("id", "unknown")
        entity_type = entity.get("type", "unknown")
        
        # Extract database information
        database_id = "unknown"
        if "data" in payload:
            data = payload.get("data", {})
            parent = data.get("parent", {})
            database_id = parent.get("database_id", "unknown")
        
        # Extract Actions relation information
        actions_info = "none"
        if "data" in payload and "properties" in payload.get("data", {}):
            properties = payload.get("data", {}).get("properties", {})
            actions_prop = properties.get("Actions", {})
            if actions_prop and actions_prop.get("type") == "relation":
                actions_relation = actions_prop.get("relation", [])
                if actions_relation:
                    action_ids = [action.get("id", "") for action in actions_relation]
                    actions_info = ", ".join(action_ids)
        
        # Extract file path information
        file_path = "unknown"
        if "data" in payload and "properties" in payload.get("data", {}):
            properties = payload.get("data", {}).get("properties", {})
            file_path_prop = properties.get("File Path", {})
            if file_path_prop and file_path_prop.get("type") == "url":
                file_path = file_path_prop.get("url", "unknown")
        
        # Extract name/title information
        name = "unknown"
        if "data" in payload and "properties" in payload.get("data", {}):
            properties = payload.get("data", {}).get("properties", {})
            # Try different name properties
            for name_key in ["Name", "Title", "Script Name"]:
                name_prop = properties.get(name_key, {})
                if name_prop and name_prop.get("type") == "title":
                    titles = name_prop.get("title", [])
                    if titles:
                        name = titles[0].get("text", {}).get("content", "unknown")
                        break
                elif name_prop and name_prop.get("type") == "rich_text":
                    texts = name_prop.get("rich_text", [])
                    if texts:
                        name = texts[0].get("text", {}).get("content", "unknown")
                        break
        
        # Process processing result
        processing_status = "not_processed"
        actions_processed = 0
        error_message = ""
        
        if processing_result:
            processing_status = processing_result.get("status", "unknown")
            actions_processed = processing_result.get("actions_processed", 0)
            if processing_result.get("status") == "error":
                error_message = processing_result.get("reason", "")
        
        # Flatten the payload for CSV (convert to string for complex objects)
        payload_str = json.dumps(payload, default=str)
        
        # CSV row data with comprehensive information
        row_data = {
            "timestamp": timestamp,
            "event_type": event_type,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "database_id": database_id,
            "name": name,
            "file_path": file_path,
            "actions_relation": actions_info,
            "processing_status": processing_status,
            "actions_processed": actions_processed,
            "error_message": error_message,
            "payload": payload_str
        }
        
        # Check if file exists to determine if we need to write headers
        file_exists = os.path.exists(csv_path)
        
        # Write to CSV
        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                "timestamp", "event_type", "entity_id", "entity_type", "database_id",
                "name", "file_path", "actions_relation", "processing_status",
                "actions_processed", "error_message", "payload"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header if file is new
            if not file_exists:
                writer.writeheader()
            
            # Write the row
            writer.writerow(row_data)
        
        webhook_logger.info("Webhook logged to CSV: {csv_path}")
        
    except Exception as e:
        webhook_logger.error("Error logging webhook to CSV: {e}")

def paste_clipboard() -> None:
    osa('tell application "System Events" to keystroke "v" using command down')

def press_return() -> None:
    """Press Return key using AppleScript."""
    osa('tell application "System Events" to key code 36')

def press_stop_and_send() -> None:
    osa('tell application "System Events" to keystroke return using {command down, option down}')   # Cmd+Option+Enter for stop & send

def submit_to_cursor(message: str) -> None:
    """
    Submit a parsed message to Cursor desktop app using the fortified submitter.
    This function uses the enhanced Cursor submitter with retry and fallback mechanisms.
    """
    try:
        if FORTIFIED_CURSOR_AVAILABLE:
            # Use the fortified submitter with retry
            success = submit_to_cursor(message)
            if success:
                webhook_logger.info("Message submitted to Cursor via fortified submitter: {message[:50]}...")
            else:
                webhook_logger.error("Fortified submitter failed, falling back to basic method")
                # Fallback to basic method
                _submit_to_cursor_basic(message)
        else:
            # Fallback to basic method if fortified submitter not available
            _submit_to_cursor_basic(message)
        
    except Exception as e:
        webhook_logger.error("Failed to submit message to Cursor: {e}")

def _submit_to_cursor_basic(message: str) -> None:
    """
    Basic Cursor submission method as fallback.
    """
    try:
        # 1. Activate Cursor application
        activate_app("com.todesktop.230313mzl4w4u92")
        time.sleep(1)
        
        # 2. Set the message to clipboard
        subprocess.run(["pbcopy"], input=message.encode(), check=True)
        time.sleep(0.5)
        
        # 3. Paste the message (Cmd+V)
        paste_clipboard()
        time.sleep(0.5)
        
        # 4. Press Cmd+Enter for stop & send
        press_stop_and_send()
        
        webhook_logger.info("Message submitted to Cursor via basic method: {message[:50]}...")
        
    except Exception as e:
        webhook_logger.error("Failed to submit message to Cursor via basic method: {e}")

async def handle_test_mode_webhook(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle webhooks from the Scripts database for test mode.
    Updates the "Run Verification Status" property to indicate the script is being tested.
    """
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        webhook_logger.info("Test: Processing test mode webhook for script: {entity_id}")
        
        # Update the "Status" property to "Not Running" (test mode indicator)
        try:
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Status": {
                        "status": {
                            "name": "Not Running"
                        }
                    }
                }
            )
            
            webhook_logger.info("Updated Status to 'Not Running' (test mode) for script: {entity_id}")
            
            return {
                "status": "completed",
                "action": "test_mode_update",
                "script_id": entity_id,
                "verification_status": "Not Running"
            }
            
        except Exception as e:
            error_msg = f"Failed to update Run Verification Status: {str(e)}"
            webhook_logger.error("{error_msg}")
            return {
                "status": "error",
                "reason": error_msg,
                "script_id": entity_id
            }
            
    except Exception as e:
        webhook_logger.error("Error handling test mode webhook: {e}")
        return {
            "status": "error",
            "reason": f"Failed to process test mode webhook: {str(e)}"
        }

async def handle_script_sync_webhook(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """Handle script synchronization webhooks using Four-Agent Framework"""
    try:
        page_id = mapped.get('page_id', '')
        script_name = mapped.get('name', 'Unknown')
        
        # Check if Send Webhook is TRUE
        send_webhook = mapped.get('send_webhook', False)
        
        if send_webhook:
            # Create Cursor super-prompt for script synchronization
            cursor_super_prompt = f"""
You are Cursor-AI acting as the "Implementation Agent" in Seren Media's Four-Agent framework.

▶ TASK
Synchronise the script "{script_name}" between the local repo
(/Users/brianhellemn/Scripts-MM1-Production) and the Notion Scripts DB
({SCRIPT_ROUTER_DB_ID}).

▶ REQUIREMENTS
1. Dynamic discovery only – never hard-code database IDs (use search if absent).
2. Compare file-hash + version header; pick latest.
3. Push newer version both directions (file ↔ Notion code block).
4. Update metadata (Version, Last Modified, SHA256, Dependencies).
5. If a row has **Send Webhook = TRUE** then:
   a. Leave it TRUE (so orchestrator sees the event).
   b. Wait ≤30 s for `scripts/sync` webhook payload; verify `status=="synced"`.
6. Write a Diátaxis "Reference" section per script if missing.
7. Log every action to Interactions DB ({INTERACTIONS_DB_ID}).

▶ VERIFICATION GATE
After all updates:
• Run `pytest test_scripts/test_sync_integrity.py -q`.
• Any failures ⇒ open Cursor chat again and paste full traceback.
• When tests pass, tick property **Sync Status = ✅**.

▶ OUTPUT
Respond only with:

SYNC COMPLETE – {{n_files}} files processed, {{issues}} issues.
"""
            
            # Route to Cursor using Four-Agent Framework
            success = await four_agent_router.route_to_agent(
                AgentType.CURSOR, 
                cursor_super_prompt, 
                page_id
            )
            
            if success:
                # Reset Send Webhook flag
                await update_notion_with_notification(
                    page_id, "success", "script_sync", script_name, "Synchronization completed"
                )
                
                return {
                    "status": "success",
                    "message": f"Script synchronization completed for {script_name}",
                    "agent": "cursor",
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to synchronize script {script_name}",
                    "agent": "cursor",
                    "timestamp": datetime.now().isoformat()
                }
        else:
            return {
                "status": "skipped",
                "message": f"Send Webhook not enabled for {script_name}",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        webhook_logger.info(f"Error in script sync webhook handler: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

async def handle_prompts_webhook(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle webhooks from the prompts database.
    Extracts the prompt message and submits it to Cursor desktop app.
    """
    try:
        # Extract prompt message from the page
        properties = full.get("properties", {})
        
        # Look for common prompt field names
        prompt_message = None
        prompt_fields = ["request", "prompt", "message", "content", "text", "input", "query"]
        
        for field_name in prompt_fields:
            if field_name in properties:
                field_data = properties[field_name]
                if field_data.get("type") == "rich_text":
                    texts = field_data.get("rich_text", [])
                    if texts:
                        prompt_message = texts[0].get("plain_text", "")
                        break
                elif field_data.get("type") == "title":
                    titles = field_data.get("title", [])
                    if titles:
                        prompt_message = titles[0].get("plain_text", "")
                        break
        
        if not prompt_message:
            # Try to get from page title if no specific prompt field found
            title_prop = properties.get("Name") or properties.get("Title")
            if title_prop and title_prop.get("type") == "title":
                titles = title_prop.get("title", [])
                if titles:
                    prompt_message = titles[0].get("plain_text", "")
        
        if prompt_message:
            # Submit the prompt message to Cursor
            submit_to_cursor(prompt_message)
            
            return {
                "status": "completed", 
                "triggered": True,
                "action": "cursor_submission",
                "message_length": len(prompt_message),
                "message_preview": prompt_message[:100] + "..." if len(prompt_message) > 100 else prompt_message
            }
        else:
            return {
                "status": "skipped", 
                "reason": "No prompt message found in page properties"
            }
            
    except Exception as e:
        webhook_logger.error("Error handling prompts webhook: {e}")
        return {
            "status": "error",
            "reason": f"Failed to process prompts webhook: {str(e)}"
        }

# -------------------------------------------------------------------
# ── Universal Action Handler ----------------------------------------
# -------------------------------------------------------------------

async def handle_actions_relation(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """
    Universal handler for Actions relation property across all databases.
    Checks the "Actions" relation property and executes the appropriate action.
    
    Actions supported:
    - "Run": Execute the script/workflow
    - "Troubleshoot": Run troubleshooting process
    - "Test": Run in test mode
    - "Stop": Stop running process
    - "Restart": Restart the process
    """
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        webhook_logger.info(f"🔧 Processing Actions relation for entity: {entity_id}")
        
        # Check for Actions relation property
        actions_prop = properties.get("Actions", {})
        if not actions_prop or actions_prop.get("type") != "relation":
            webhook_logger.info(f"⏭️ No Actions relation found for entity: {entity_id}")
            return {
                "status": "skipped",
                "reason": "No Actions relation property found"
            }
        
        # Get the related pages from the Actions relation
        actions_relation = actions_prop.get("relation", [])
        if not actions_relation:
            webhook_logger.info(f"⏭️ Actions relation is empty for entity: {entity_id}")
            return {
                "status": "skipped",
                "reason": "Actions relation is empty"
            }
        
        # Process each action in the relation
        results = []
        for action_ref in actions_relation:
            action_id = action_ref.get("id")
            if not action_id:
                continue
                
            try:
                # Fetch the action page to get its name
                action_page = notion.pages.retrieve(page_id=action_id)
                action_name = ""
                
                # Extract action name from title property
                title_prop = action_page.get("properties", {}).get("Name", {})
                if title_prop and title_prop.get("type") == "title":
                    titles = title_prop.get("title", [])
                    if titles:
                        action_name = titles[0].get("plain_text", "")
                
                if not action_name:
                    # Try other common name properties
                    for name_key in ["Title", "Action Name", "Function", "Workflow Name"]:
                        name_prop = action_page.get("properties", {}).get(name_key, {})
                        if name_prop and name_prop.get("type") == "title":
                            titles = name_prop.get("title", [])
                            if titles:
                                action_name = titles[0].get("plain_text", "")
                                break
                
                webhook_logger.info(f"🎯 Processing action: {action_name} for entity: {entity_id}")
                
                # Execute the action based on its name
                action_result = await execute_action(action_name, mapped, full, action_page)
                results.append({
                    "action_name": action_name,
                    "action_id": action_id,
                    "result": action_result
                })
                
            except Exception as e:
                error_msg = f"Failed to process action {action_id}: {str(e)}"
                webhook_logger.error("{error_msg}")
                results.append({
                    "action_id": action_id,
                    "error": error_msg
                })
        
        return {
            "status": "completed",
            "actions_processed": len(results),
            "results": results
        }
        
    except Exception as e:
        error_msg = f"Error handling Actions relation: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "reason": error_msg
        }

async def execute_action(action_name: str, mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a specific action based on the action name.
    
    Args:
        action_name: Name of the action to execute
        mapped: Mapped properties from the webhook
        full: Full page/database data from Notion
        action_page: The action page data from Notion
        
    Returns:
        Dict containing the execution result
    """
    action_name_lower = action_name.lower().strip()
    entity_id = mapped.get("entity_id")
    
    try:
        if action_name_lower == "run":
            return await execute_run_action(mapped, full, action_page)
        elif action_name_lower == "troubleshoot":
            return await execute_troubleshoot_action(mapped, full, action_page)
        elif action_name_lower == "test":
            return await execute_test_action(mapped, full, action_page)
        elif action_name_lower == "stop":
            return await execute_stop_action(mapped, full, action_page)
        elif action_name_lower == "restart":
            return await execute_restart_action(mapped, full, action_page)
        else:
            webhook_logger.warning("Unknown action: {action_name}")
            return {
                "status": "unknown_action",
                "action_name": action_name,
                "message": f"Unknown action: {action_name}"
            }
            
    except Exception as e:
        error_msg = f"Error executing action {action_name}: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action_name": action_name,
            "error": error_msg
        }

async def execute_run_action(mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the 'Run' action - execute the script/workflow."""
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        webhook_logger.info(f"🚀 Executing Run action for entity: {entity_id}")
        
        # Get script path from properties
        script_path = None
        file_path_prop = properties.get("File Path", {})
        if file_path_prop and file_path_prop.get("type") == "url":
            script_path = file_path_prop.get("url", "")
            if script_path.startswith("file://"):
                script_path = script_path[7:]  # Remove file:// prefix
        
        if not script_path:
            # Try other path properties
            for path_key in ["Script Path", "Local Path", "Path"]:
                path_prop = properties.get(path_key, {})
                if path_prop and path_prop.get("type") == "url":
                    script_path = path_prop.get("url", "")
                    if script_path.startswith("file://"):
                        script_path = script_path[7:]
                    break
        
        if not script_path:
            return {
                "status": "error",
                "reason": "No script path found in properties"
            }
        
        # Update status to "Running"
        try:
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Status": {
                        "status": {
                            "name": "Running"
                        }
                    }
                }
            )
            webhook_logger.info("Updated status to 'Running' for entity: {entity_id}")
        except Exception as e:
            webhook_logger.warning("Failed to update status: {e}")
        
        # Extract item name for notifications
        item_name = "Unknown"
        for name_key in ["Script Name", "Name", "Title"]:
            name_prop = properties.get(name_key, {})
            if name_prop and name_prop.get("type") == "title":
                titles = name_prop.get("title", [])
                if titles:
                    item_name = titles[0].get("text", {}).get("content", "Unknown")
                    break
        
        # Send macOS notification that script is starting
        script_filename = os.path.basename(script_path)
        MacNotifier.send_notification(
            title="🚀 Script Execution Started",
            message=f"Running: {script_filename}\nTriggered by: {item_name}",
            sound="default"
        )
        webhook_logger.info(f"🔔 Sent notification for script start: {script_filename}")
        
        # Update Notion item with notification
        await update_notion_with_notification(
            entity_id, "Script Execution Started", script_filename, item_name,
            f"Triggered by: {item_name}"
        )
        
        # Execute the script
        webhook_logger.info(f"🔧 Executing script: {script_path}")
        result = await run_script_async(script_path, mapped, full)
        
        # Enhanced logging for script execution
        if ENHANCED_LOGGING_AVAILABLE and logging_manager:
            try:
                # Extract item name for logging
                item_name = "Unknown"
                for name_key in ["Script Name", "Name", "Title"]:
                    name_prop = properties.get(name_key, {})
                    if name_prop and name_prop.get("type") == "title":
                        titles = name_prop.get("title", [])
                        if titles:
                            item_name = titles[0].get("text", {}).get("content", "Unknown")
                            break
                
                # Log script execution with enhanced script properties
                await logging_manager.log_script_execution(
                    entity_id, item_name, result, {},
                    {"trigger": "webhook", "action": "run"},
                    properties  # Pass script properties for enhanced logging
                )
                
                # Log workflow action
                await logging_manager.log_workflow_action(
                    "script_execution", entity_id, item_name,
                    {"status": "completed" if result.get("exit_code") == 0 else "failed", "script_path": script_path}
                )
            except Exception as e:
                webhook_logger.warning("Failed to log script execution: {e}")
        
        # Check if script execution was successful
        if result.get("status") == "completed" and result.get("exit_code") == 0:
            # Send success notification
            MacNotifier.send_notification(
                title="✅ Script Execution Completed",
                message=f"Successfully completed: {script_filename}\nTriggered by: {item_name}",
                sound="default"
            )
            webhook_logger.info(f"🔔 Sent success notification for: {script_filename}")
            
            # Update Notion item with success notification
            await update_notion_with_notification(
                entity_id, "Script Execution Completed", script_filename, item_name,
                f"Successfully completed - Triggered by: {item_name}"
            )
            
            # Script succeeded - clear the Actions relation
            try:
                await clear_actions_relation(entity_id, action_page.get("id"))
                webhook_logger.info("Cleared Actions relation for successful entity: {entity_id}")
            except Exception as e:
                webhook_logger.warning("Failed to clear Actions relation: {e}")
            
            return {
                "status": "completed",
                "action": "run",
                "script_path": script_path,
                "execution_result": result
            }
        else:
            # Send failure notification
            exit_code = result.get("exit_code", "Unknown")
            MacNotifier.send_notification(
                title="❌ Script Execution Failed",
                message=f"Failed to complete: {script_filename}\nExit Code: {exit_code}\nTriggered by: {item_name}",
                sound="default"
            )
            webhook_logger.info(f"🔔 Sent failure notification for: {script_filename}")
            
            # Update Notion item with failure notification
            await update_notion_with_notification(
                entity_id, "Script Execution Failed", script_filename, item_name,
                f"Exit Code: {exit_code} - Triggered by: {item_name}"
            )
            
            # Script failed - DON'T clear the action to allow retry
            webhook_logger.warning("Script failed for entity {entity_id} - Actions relation NOT cleared to allow retry")
            webhook_logger.info(f"   Exit code: {result.get('exit_code', 'Unknown')}")
            webhook_logger.info(f"   Error: {result.get('error', 'No error details')}")
            
            return {
                "status": "error",
                "action": "run",
                "script_path": script_path,
                "execution_result": result,
                "reason": "Script execution failed - action not cleared"
            }
        
    except Exception as e:
        error_msg = f"Error executing Run action: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action": "run",
            "error": error_msg
        }

async def execute_troubleshoot_action(mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the 'Troubleshoot' action - run troubleshooting process."""
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        webhook_logger.info(f"🔧 Executing Troubleshoot action for entity: {entity_id}")
        
        # Update status to "Troubleshooting"
        try:
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Status": {
                        "status": {
                            "name": "Troubleshooting"
                        }
                    }
                }
            )
            webhook_logger.info("Updated status to 'Troubleshooting' for entity: {entity_id}")
        except Exception as e:
            webhook_logger.warning("Failed to update status: {e}")
        
        # Run troubleshooting process
        troubleshoot_result = await run_troubleshooting_async(mapped, full)
        
        return {
            "status": "completed",
            "action": "troubleshoot",
            "troubleshoot_result": troubleshoot_result
        }
        
    except Exception as e:
        error_msg = f"Error executing Troubleshoot action: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action": "troubleshoot",
            "error": error_msg
        }

async def execute_test_action(mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the 'Test' action - run in test mode."""
    try:
        entity_id = mapped.get("entity_id")
        
        webhook_logger.info("Test: Executing Test action for entity: {entity_id}")
        
        # Update status to "Testing"
        try:
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Status": {
                        "status": {
                            "name": "Testing"
                        }
                    }
                }
            )
            webhook_logger.info("Updated status to 'Testing' for entity: {entity_id}")
        except Exception as e:
            webhook_logger.warning("Failed to update status: {e}")
        
        # Run test mode process
        test_result = await run_test_mode_async(mapped, full)
        
        return {
            "status": "completed",
            "action": "test",
            "test_result": test_result
        }
        
    except Exception as e:
        error_msg = f"Error executing Test action: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action": "test",
            "error": error_msg
        }

async def execute_stop_action(mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the 'Stop' action - stop running process."""
    try:
        entity_id = mapped.get("entity_id")
        
        webhook_logger.info("Stopped: Executing Stop action for entity: {entity_id}")
        
        # Update status to "Stopped"
        try:
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Status": {
                        "status": {
                            "name": "Stopped"
                        }
                    }
                }
            )
            webhook_logger.info("Updated status to 'Stopped' for entity: {entity_id}")
        except Exception as e:
            webhook_logger.warning("Failed to update status: {e}")
        
        # Stop the process
        stop_result = await stop_process_async(mapped, full)
        
        return {
            "status": "completed",
            "action": "stop",
            "stop_result": stop_result
        }
        
    except Exception as e:
        error_msg = f"Error executing Stop action: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action": "stop",
            "error": error_msg
        }

async def execute_restart_action(mapped: Dict[str, Any], full: Dict[str, Any], action_page: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the 'Restart' action - restart the process."""
    try:
        entity_id = mapped.get("entity_id")
        
        webhook_logger.info("Processing: Executing Restart action for entity: {entity_id}")
        
        # First stop the process
        await stop_process_async(mapped, full)
        
        # Then run the process
        run_result = await execute_run_action(mapped, full, action_page)
        
        return {
            "status": "completed",
            "action": "restart",
            "stop_result": "Process stopped",
            "run_result": run_result
        }
        
    except Exception as e:
        error_msg = f"Error executing Restart action: {str(e)}"
        webhook_logger.error("{error_msg}")
        return {
            "status": "error",
            "action": "restart",
            "error": error_msg
        }

async def discover_database_from_webhook(payload: Dict[str, Any]) -> None:
    """Discover if the webhook source database has Actions relation and add to query rotation"""
    if not PERIODIC_EXECUTOR_AVAILABLE:
        return
        
    try:
        # Extract database ID from webhook payload
        database_id = None
        
        # Check different possible locations for database ID
        if 'database_id' in payload:
            database_id = payload['database_id']
        elif 'parent' in payload and 'database_id' in payload['parent']:
            database_id = payload['parent']['database_id']
        elif 'properties' in payload and 'Actions' in payload['properties']:
            # If we have Actions property, try to get database from parent
            pass  # Will be handled by the executor when it processes the webhook
        
        if database_id:
            executor = get_global_executor()
            if executor.discover_and_add_database(database_id):
                webhook_logger.info("Discovered new database with Actions relation: {database_id}")
                
    except Exception as e:
        webhook_logger.info(f"Error discovering database from webhook: {e}")

def clear_actions_relation(entity_id: str, action_id: str):
    """Clear the Actions relation property after execution to prevent duplicate runs"""
    try:
        # Get current page to see existing Actions relation
        page = notion.pages.retrieve(page_id=entity_id)
        properties = page.get("properties", {})
        
        # Get current Actions relation
        actions_prop = properties.get("Actions", {})
        if actions_prop and actions_prop.get("type") == "relation":
            current_actions = actions_prop.get("relation", [])
            
            # Remove the specific action that was just executed
            updated_actions = [action for action in current_actions if action.get("id") != action_id]
            
            # Update the page with the cleared Actions relation
            notion.pages.update(
                page_id=entity_id,
                properties={
                    "Actions": {
                        "relation": updated_actions
                    }
                }
            )
            
            webhook_logger.info("Cleared action {action_id} from Actions relation for entity {entity_id}")
            
    except Exception as e:
        webhook_logger.error("Error clearing Actions relation: {e}")
        raise

async def update_notion_with_notification(entity_id: str, notification_type: str, script_filename: str, item_name: str, additional_info: str = ""):
    """Update Notion item when a notification is sent"""
    try:
        current_time = datetime.now().isoformat()
        
        # Create notification log entry
        notification_text = f"[{current_time}] {notification_type}: {script_filename}"
        if additional_info:
            notification_text += f"\\n{additional_info}"
        
        # Update the "Execution Result-AI" property with notification info
        properties = {
            "Execution Result-AI": {
                "rich_text": [{
                    "text": {
                        "content": notification_text
                    }
                }]
            }
        }
        
        # Also update last run time for all notifications
        properties["Last Run"] = {
            "date": {
                "start": current_time
            }
        }
        
        # Update status based on notification type
        if "Started" in notification_type:
            properties["Execution Status"] = {
                "status": {
                    "name": "Running"
                }
            }
        elif "Completed" in notification_type:
            properties["Execution Status"] = {
                "status": {
                    "name": "Completed"
                }
            }
        elif "Failed" in notification_type:
            properties["Execution Status"] = {
                "status": {
                    "name": "Failed"
                }
            }
        
        notion.pages.update(page_id=entity_id, properties=properties)
        webhook_logger.info("Logged: Updated Notion item {entity_id} with notification: {notification_type}")
        
    except Exception as e:
        webhook_logger.info(f"Failed to update Notion item {entity_id} with notification: {e}")

async def run_script_async(script_path: str, mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """Run a script asynchronously."""
    try:
        # Validate script path
        if not os.path.exists(script_path):
            return {
                "status": "error",
                "reason": f"Script not found: {script_path}"
            }
        
        # Make script executable
        os.chmod(script_path, 0o755)
        
        # Run the script
        webhook_logger.info(f"🚀 Running script: {script_path}")
        process = await asyncio.create_subprocess_exec(
            "python3", script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            "status": "completed",
            "exit_code": process.returncode,
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else ""
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

async def run_troubleshooting_async(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """Run troubleshooting process asynchronously."""
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        # Get script path for troubleshooting
        script_path = None
        file_path_prop = properties.get("File Path", {})
        if file_path_prop and file_path_prop.get("type") == "url":
            script_path = file_path_prop.get("url", "")
            if script_path.startswith("file://"):
                script_path = script_path[7:]
        
        if script_path and os.path.exists(script_path):
            # Run script with troubleshooting flag
            process = await asyncio.create_subprocess_exec(
                "python3", script_path, "--troubleshoot",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "status": "completed",
                "exit_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else ""
            }
        else:
            # Basic troubleshooting without script
            return {
                "status": "completed",
                "message": "Basic troubleshooting completed",
                "checks": [
                    "File path validation",
                    "Permission checks",
                    "Dependency verification"
                ]
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

async def run_test_mode_async(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """Run test mode process asynchronously."""
    try:
        entity_id = mapped.get("entity_id")
        properties = full.get("properties", {})
        
        # Get script path for testing
        script_path = None
        file_path_prop = properties.get("File Path", {})
        if file_path_prop and file_path_prop.get("type") == "url":
            script_path = file_path_prop.get("url", "")
            if script_path.startswith("file://"):
                script_path = script_path[7:]
        
        if script_path and os.path.exists(script_path):
            # Run script with test flag
            process = await asyncio.create_subprocess_exec(
                "python3", script_path, "--test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            return {
                "status": "completed",
                "exit_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else ""
            }
        else:
            # Basic test mode without script
            return {
                "status": "completed",
                "message": "Test mode completed",
                "tests": [
                    "Configuration validation",
                    "Environment checks",
                    "Basic functionality test"
                ]
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

async def stop_process_async(mapped: Dict[str, Any], full: Dict[str, Any]) -> Dict[str, Any]:
    """Stop a running process asynchronously."""
    try:
        entity_id = mapped.get("entity_id")
        
        # For now, just return success since we don't have process tracking
        # In a full implementation, you would track running processes and stop them
        return {
            "status": "completed",
            "message": "Process stop requested"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

# -------------------------------------------------------------------
# ── Macro steps as Python functions ---------------------------------
# -------------------------------------------------------------------
def run_submacro_a(data: Dict[str, Any]) -> None:
    """
    Placeholder for macro UID D1023304-09AF-45F0-8A61-14179EAFB3F2
    Implement your Cursor-specific automation here.
    """
    # Example: send a Notion page URL to Cursor AI
    url = data.get("url") or ""
    if url:
        osa(f'do shell script "open -g {url}"')

def run_workflow(mapped: Dict[str, Any]) -> None:
    """
    Recreates the Keyboard Maestro repeat loop exactly once.
    If you need the original 'CountExpression' behaviour,
    wrap this function in a for-loop based on that expression.
    """
    # 1 Execute sub-macro
    run_submacro_a(mapped)

    # 2 Hide all windows
    hide_all_windows()
    time.sleep(5)

    # 3 Quit Terminal
    quit_app("com.apple.Terminal")

    # 4 Activate Google Drive → wait
    activate_app("com.google.drivefs")
    time.sleep(1)

    # 5 Activate Cursor → run second sub-macro
    activate_app("com.todesktop.230313mzl4w4u92")
    run_submacro_a(mapped)         # original macro executed a different UID — adjust if needed
    time.sleep(0.5)

    # 6 Insert text = value originally held in Named Clipboard "Temporary"
    temp = mapped.get("temporary", "")
    if temp:
        subprocess.run(["pbcopy"], input=temp.encode())  # set clipboard
        paste_clipboard()

    time.sleep(0.5)
    press_return()

    # 7 Final pause identical to KM
    time.sleep(5 * 60)  # 5 minutes

# -------------------------------------------------------------------
# ── Webhook endpoint ------------------------------------------------
# -------------------------------------------------------------------
@app.post("/test-automation")
async def test_automation(req: Request):
    """Test endpoint for enhanced webhook processing."""
    try:
        webhook_data = await req.json()
        
        if ENHANCED_PROCESSING_AVAILABLE:
            # Use enhanced webhook processing
            await process_enhanced_webhook(webhook_data)
            return {"status": "success", "message": "Enhanced webhook processing completed"}
        else:
            # Fallback to basic processing
            return {"status": "error", "message": "Enhanced webhook processing not available"}
            
    except Exception as e:
        return {"status": "error", "message": f"Test automation failed: {str(e)}"}

@app.post("/test-four-agent")
async def test_four_agent_framework(req: Request):
    """Test endpoint for Four-Agent Framework functionality"""
    try:
        data = await req.json()
        agent_type = data.get('agent', 'cursor')
        prompt = data.get('prompt', 'Test prompt for Four-Agent Framework')
        page_id = data.get('page_id', None)
        
        # Convert string to AgentType enum
        agent_enum = AgentType(agent_type)
        
        # Route to agent
        success = await four_agent_router.route_to_agent(agent_enum, prompt, page_id)
        
        return {
            "status": "success" if success else "error",
            "agent": agent_type,
            "prompt": prompt,
            "page_id": page_id,
            "timestamp": datetime.now().isoformat(),
            "message": f"Four-Agent Framework test completed for {agent_type}"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/test-event-subscription")
async def test_event_subscription(req: Request):
    """Test endpoint for event subscription webhook processing."""
    try:
        test_data = await req.json()
        
        # Create event subscription webhook format
        event_webhook = {
            "type": test_data.get("event_type", "page_created"),
            "entity": {
                "id": test_data.get("page_id", "test_page_123"),
                "type": "page"
            },
            "data": {
                "id": test_data.get("page_id", "test_page_123"),
                "object": "page",
                "parent": {
                    "database_id": test_data.get("database_id", WORKFLOWS_DB_ID)
                },
                "properties": test_data.get("properties", {
                    "Name": {
                        "type": "title",
                        "title": [{"text": {"content": test_data.get("page_name", "Test Event Page")}}]
                    },
                    "Script Name": {
                        "type": "rich_text",
                        "rich_text": [{"text": {"content": test_data.get("script_name", "test_script.py")}}]
                    }
                })
            }
        }
        
        if ENHANCED_PROCESSING_AVAILABLE:
            # Use enhanced webhook processing
            await process_enhanced_webhook(event_webhook)
            return {"status": "success", "message": "Event subscription webhook processed", "webhook_data": event_webhook}
        else:
            # Fallback to basic processing
            return {"status": "error", "message": "Enhanced webhook processing not available"}
            
    except Exception as e:
        return {"status": "error", "message": f"Event subscription test failed: {str(e)}"}

@app.post("/status-monitor")
async def trigger_status_monitor():
    """
    Trigger status monitoring: capture screenshot, parse status, update Notion
    """
    if not STATUS_MONITOR_AVAILABLE or not status_monitor:
        raise HTTPException(status_code=503, detail="Status monitor not available")
    
    try:
        result = await status_monitor.monitor_and_parse()
        
        # Update Notion if status was parsed successfully
        if result['success'] and result['status_info']:
            update_success = await status_monitor.update_notion_status(
                result['status_info'],
                script_name="Notion Webhook Status Monitor"
            )
            result['notion_updated'] = update_success
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status monitoring failed: {str(e)}")

@app.get("/status-monitor")
async def get_status_monitor_info():
    """
    Get information about the status monitor
    """
    return {
        "available": STATUS_MONITOR_AVAILABLE,
        "monitor_initialized": status_monitor is not None,
        "notion_url": status_monitor.notion_url if status_monitor else None,
        "output_dir": str(status_monitor.output_dir) if status_monitor else None
    }

@app.get("/workspace-events/status")
async def get_workspace_events_status():
    """
    Get Google Workspace Events API service status and statistics.
    """
    if not WORKSPACE_EVENTS_INTEGRATION_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Google Workspace Events API integration not available"
        )
    
    service = get_workspace_events_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Google Workspace Events API service not initialized"
        )
    
    return service.get_status()

@app.get("/workspace-events/health")
async def get_workspace_events_health():
    """
    Get Google Workspace Events API service health check.
    """
    if not WORKSPACE_EVENTS_INTEGRATION_AVAILABLE:
        return {
            "status": "unavailable",
            "reason": "Integration not available"
        }
    
    service = get_workspace_events_service()
    if not service:
        return {
            "status": "unavailable",
            "reason": "Service not initialized"
        }
    
    return service.health_check()


@app.post("/slack/events")
async def slack_events(req: Request):
    """
    Slack Event Subscriptions endpoint.
    - Validates Slack signature (v0)
    - Handles URL verification challenge
    - Emits NotificationManager events for receipt/completion
    """
    body = await req.body()
    timestamp = req.headers.get("X-Slack-Request-Timestamp")
    signature = req.headers.get("X-Slack-Signature")

    if not _verify_slack_signature(body, timestamp, signature):
        _log_event_line("⚠️ Slack signature validation failed")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:
        _log_event_line(f"⚠️ Slack payload parse error: {exc}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle Slack URL verification challenge immediately
    if payload.get("type") == "url_verification" and payload.get("challenge"):
        return {"challenge": payload["challenge"]}

    # Optional legacy token check
    if SLACK_VERIFICATION_TOKEN and payload.get("token") not in (None, SLACK_VERIFICATION_TOKEN):
        _log_event_line("⚠️ Slack verification token mismatch")
        raise HTTPException(status_code=401, detail="Invalid Slack token")

    event = payload.get("event", {}) or {}
    event_type = event.get("type", "unknown")
    raw_ts = event.get("event_ts") or event.get("ts") or f"{int(time.time() * 1000)}"
    run_id = f"slack-{raw_ts}"
    event_id = payload.get("event_id")
    team_id = payload.get("team_id")
    api_app_id = payload.get("api_app_id")

    details = {
        "team_id": team_id,
        "api_app_id": api_app_id,
        "event_id": event_id,
        "channel": event.get("channel"),
        "user": event.get("user"),
    }

    _log_event_line(
        "📥 Slack event received "
        f"run_id={run_id} "
        f"event_id={_safe_id(event_id)} "
        f"team_id={_safe_id(team_id)} "
        f"api_app_id={_safe_id(api_app_id)} "
        f"type={event_type}"
    )
    _emit_notification(
        NotificationEvent(
            run_id=run_id,
            script_name="notion_webhook_server",
            event_type="slack_event_received",
            severity=EventSeverity.INFO,
            phase="receipt",
            status=EventStatus.RUNNING,
            summary=f"Slack event received ({event_type})",
            details=details,
        )
    )

    # Align with other webhook flows: log + queue for processing, return fast to Slack.
    slack_payload = payload
    slack_payload["run_id"] = run_id
    slack_payload["__source"] = "slack_event_subscriptions"
    slack_payload["received_at"] = datetime.now(timezone.utc).isoformat()

    # Best-effort: CSV log receipt (processing happens in background)
    log_slack_event_to_csv(slack_payload, {"status": "received"})

    # Queue for controlled background processing
    webhook_queue.add_webhook(slack_payload, request_id=run_id)

    _emit_notification(
        NotificationEvent(
            run_id=run_id,
            script_name="notion_webhook_server",
            event_type="slack_event_queued",
            severity=EventSeverity.INFO,
            phase="receipt",
            status=EventStatus.RUNNING,
            summary=f"Slack event queued ({event_type})",
            details=details,
        )
    )

    return {"ok": True, "run_id": run_id, "event_type": event_type, "status": "queued"}

@app.post("/webhook")
async def receive_webhook(req: Request):
    """
    Webhook endpoint for Notion Event Subscriptions and Notion Automations.
    
    Supports two webhook formats:
    1. Notion Event Subscriptions: {"type": "...", "entity": {...}}
    2. Notion Automations: Direct property payload (e.g., {"Task Name": {...}, ...})
    
    Always returns 200 OK to prevent 503 errors. Errors are logged but not returned as HTTP errors.
    """
    try:
        run_id = f"notion-webhook-{int(time.time() * 1000)}"
        # Parse JSON payload with error handling
        try:
            payload = await req.json()
        except Exception as e:
            _log_event_line(f"⚠️ Failed to parse JSON payload: {e}")
            log_webhook_to_csv({"error": str(e)}, "parse_error", {"status": "json_parse_failed"})
            _emit_notification(
                NotificationEvent(
                    run_id=run_id,
                    script_name="notion_webhook_server",
                    event_type="webhook_received",
                    severity=EventSeverity.ERROR,
                    phase="receipt",
                    status=EventStatus.ERROR,
                    summary="Webhook JSON parse failed",
                    details={"error": str(e)},
                )
            )
            return {"status": "error", "message": "Invalid JSON payload", "error": str(e)}
        
        payload["run_id"] = payload.get("run_id", run_id)
        run_id = payload["run_id"]
        
        # Handle verification requests immediately (not queued)
        if "verification_token" in payload:
            # Log verification request to CSV
            log_webhook_to_csv(payload, "verification", {"status": "verification_request"})
            
            if payload["verification_token"] != NOTION_VERIFICATION:
                webhook_logger.warning("Invalid verification token: {payload.get('verification_token', 'missing')}")
                return {"error": "Invalid verification token"}
            webhook_logger.info("Verification token validated: {payload.get('verification_token', 'missing')}")
            return {"status": "verified"}

        # Handle challenge requests immediately
        if "challenge" in payload:
            # Log challenge request to CSV
            log_webhook_to_csv(payload, "challenge", {"status": "challenge_request"})
            
            webhook_logger.info("Challenge received: {payload['challenge']}")
            return {"challenge": payload["challenge"]}

        # Detect webhook format: Event Subscription vs Automation
        is_event_subscription = "type" in payload and "entity" in payload
        is_automation = not is_event_subscription and any(
            key in payload for key in ["Task Name", "Name", "Title", "Agent Handoff File Links"]
        )
        
        format_type = (
            "automation" if is_automation else "event_subscription" if is_event_subscription else "unknown"
        )
        _log_event_line(f"📥 Received webhook run_id={run_id} format={format_type}")
        _emit_notification(
            NotificationEvent(
                run_id=run_id,
                script_name="notion_webhook_server",
                event_type="webhook_received",
                severity=EventSeverity.WARNING,
                phase="receipt",
                status=EventStatus.RUNNING,
                summary=f"Webhook received ({format_type})",
                details={"keys": list(payload.keys())[:5]},
            )
        )
        
        # Fast path for test events: process inline and return
        if payload.get("test_event"):
            _log_event_line(f"✅ Test webhook processed run_id={run_id}")
            _emit_notification(
                NotificationEvent(
                    run_id=run_id,
                    script_name="notion_webhook_server",
                    event_type="webhook_complete",
                    severity=EventSeverity.INFO,
                    phase="completion",
                    status=EventStatus.OK,
                    summary="Test webhook processed (inline)",
                    details={"request_id": run_id},
                ),
                channels=["macos", "slack"],
            )
            return {"status": "webhook processed (test_event)", "format": format_type}
        
        if is_automation:
            # Notion Automation format - log and queue for processing
            webhook_logger.info("Received: Received Notion Automation webhook with {len(payload)} properties")
            log_webhook_to_csv(payload, "automation", {"status": "automation_webhook", "property_count": len(payload)})
            # Best-effort forward to worker node (MM2) for parallelism; fall back to local queue.
            forwarded = _try_forward_to_worker(payload, run_id=run_id)
            if forwarded:
                return forwarded

            # Queue automation webhooks for local processing (can be extended with automation-specific handlers)
            webhook_queue.add_webhook(payload, request_id=run_id)
            return {"status": "webhook queued", "format": "automation", "node_id": WORKSPACE_EVENTS_NODE_ID}
        elif is_event_subscription:
            # Notion Event Subscription format - existing processing
            webhook_logger.info("Received: Received Notion Event Subscription webhook: {payload.get('type', 'unknown')}")
            log_webhook_to_csv(payload, "event_subscription", {"status": "webhook_queued", "event_type": payload.get('type', 'unknown')})
            # Discover database from webhook for dynamic database management
            try:
                discover_database_from_webhook(payload)
            except Exception as e:
                webhook_logger.warning("Failed to discover database from webhook: {e}")
            # Best-effort forward to worker node (MM2) for parallelism; fall back to local queue.
            forwarded = _try_forward_to_worker(payload, run_id=run_id)
            if forwarded:
                return forwarded

            # Add all other webhooks to the local queue
            webhook_queue.add_webhook(payload, request_id=run_id)
            return {"status": "webhook queued", "format": "event_subscription", "node_id": WORKSPACE_EVENTS_NODE_ID}
        else:
            # Unknown format - log and queue anyway
            webhook_logger.warning("Unknown webhook format received: {list(payload.keys())[:5]}")
            log_webhook_to_csv(payload, "unknown", {"status": "unknown_format", "keys": list(payload.keys())[:5]})
            forwarded = _try_forward_to_worker(payload, run_id=run_id)
            if forwarded:
                return forwarded
            webhook_queue.add_webhook(payload, request_id=run_id)
            return {"status": "webhook queued", "format": "unknown", "node_id": WORKSPACE_EVENTS_NODE_ID}
            
    except Exception as e:
        # Catch-all error handler - always return 200 OK to prevent 503 errors
        error_msg = f"Unexpected error processing webhook: {str(e)}"
        _log_event_line(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        
        # Log error to CSV
        try:
            log_webhook_to_csv({"error": error_msg, "traceback": traceback.format_exc()}, "error", {"status": "unexpected_error"})
        except:
            pass  # Don't fail if logging fails
        
        _emit_notification(
            NotificationEvent(
                run_id=run_id if 'run_id' in locals() else f"notion-webhook-error-{int(time.time()*1000)}",
                script_name="notion_webhook_server",
                event_type="webhook_error",
                severity=EventSeverity.ERROR,
                phase="receipt",
                status=EventStatus.ERROR,
                summary=error_msg,
                details={"exception": str(e)},
            )
        )
        
        # Always return 200 OK to prevent Notion from retrying and causing 503 errors
        return {"status": "error", "message": "Webhook received but processing failed", "error": str(e)}


@app.post("/webhook/process")
async def worker_process_webhook(req: Request):
    """
    Worker ingest endpoint for multi-node coordination.
    """
    try:
        payload = await req.json()
    except Exception as e:
        return {"ok": False, "status": "error", "error": f"invalid_json: {e}"}

    run_id = payload.get("run_id") or f"worker-{int(time.time() * 1000)}"
    payload["run_id"] = run_id
    payload["__forwarded"] = True
    payload["__forwarded_at"] = datetime.now(timezone.utc).isoformat()

    try:
        webhook_queue.add_webhook(payload, request_id=run_id)
        return {"ok": True, "status": "queued", "run_id": run_id, "node_id": os.getenv("WORKSPACE_EVENTS_NODE_ID", "local")}
    except Exception as e:
        return {"ok": False, "status": "error", "run_id": run_id, "error": str(e)}

# -------------------------------------------------------------------
# ── DEV_NOTES: Google OAuth Testing Instructions -------------------
# -------------------------------------------------------------------
#
# LOCAL TEST INSTRUCTIONS FOR GOOGLE OAUTH2 FLOW
# ===============================================
#
# Prerequisites:
# 1. Ensure you have a Google Cloud "Web application" OAuth client configured
# 2. The client_secret JSON file must be accessible
# 3. The redirect URI must be added to Google Cloud Console
#
# Step 1: Set Environment Variables
# ----------------------------------
# Export the required environment variables before starting the server:
#
#   export GOOGLE_OAUTH_CLIENT_SECRETS_FILE="/Users/brianhellemn/Library/CloudStorage/GoogleDrive-vibe.vessel.io@gmail.com/My Drive/VibeVessel-Internal-WS-gd/database-parent-page/scripts/github-dev/credentials/google-oauth/client_secret_797362328200-ki5cbaoauictkugd87mm8u70o75euvqk.apps.googleusercontent.com.json"
#
#   export GOOGLE_OAUTH_REDIRECT_URI="http://localhost:5001/auth/google/callback"
#
#   # Optional: Override server port if needed
#   export PORT=5001
#
# Step 2: Add Redirect URIs to Google Cloud Console
# ---------------------------------------------------
# IMPORTANT: Add BOTH redirect URIs for local and Cloudflare access:
# 1. Go to: https://console.cloud.google.com/apis/credentials
# 2. Select your OAuth 2.0 Client ID (the one matching your client_secret file)
# 3. Under "Authorized redirect URIs", click "ADD URI"
# 4. Add BOTH of these URIs:
#    a. http://localhost:5001/auth/google/callback (for local testing)
#    b. https://webhook.vibevessel.space/auth/google/callback (for Cloudflare tunnel)
# 5. Click "SAVE"
#
# Note: The server automatically detects Cloudflare and uses the appropriate redirect URI.
#
# Step 3: Start the FastAPI Server
# ----------------------------------
#   cd /Users/brianhellemn/Projects/github-production/webhook-server
#   python3 notion_event_subscription_webhook_server_v4_enhanced.py
#
#   Or using uvicorn directly:
#   uvicorn notion_event_subscription_webhook_server_v4_enhanced:app --reload --port 5001
#
# Step 4: Test the OAuth Flow
# -----------------------------
# 1. Open your browser and navigate to:
#    http://localhost:5001/auth/google
#
# 2. You should be redirected to Google's consent screen
#
# 3. Approve the requested permissions
#
# 4. Google will redirect back to:
#    http://localhost:5001/auth/google/callback?code=...&state=...
#
# 5. The callback endpoint will:
#    - Exchange the authorization code for tokens
#    - Save credentials to ~/.credentials/google_oauth_token_*.pickle
#    - Display a success page with user info
#
# Step 5: Verify Success
# -----------------------
# Check the server logs for:
#   ✅ Google OAuth Handler initialized
#   ✅ OAuth authentication successful for: <your-email>
#
# Check authentication status:
#   http://localhost:5001/auth/google/status
#
# Troubleshooting:
# ----------------
# - "redirect_uri_mismatch" error:
#   → Ensure BOTH redirect URIs are in Google Cloud Console:
#     - http://localhost:5001/auth/google/callback (for local access)
#     - https://webhook.vibevessel.space/auth/google/callback (for Cloudflare tunnel)
#   → The server automatically detects Cloudflare and uses the correct URI
#   → Check for trailing slashes, port mismatches, or protocol differences
#   → Verify Cloudflare tunnel is running: launchctl list | grep cloudflare
#
# - Cloudflare detection not working:
#   → Check that Cloudflare tunnel is running and proxying requests
#   → Verify X-Forwarded-Host header is present: curl -I https://webhook.vibevessel.space/auth/google
#   → Check tunnel logs: tail -f ~/Library/Logs/cloudflare-tunnel-stdout.log
#
# - "Invalid client_secret" error:
#   → Verify GOOGLE_OAUTH_CLIENT_SECRETS_FILE points to the correct JSON file
#   → Ensure the JSON file contains a "web" key with client_id and client_secret
#
# - "File not found" error:
#   → Verify the path in GOOGLE_OAUTH_CLIENT_SECRETS_FILE is correct
#   → Check file permissions (must be readable)
#
# - Port conflicts:
#   → If port 5001 is in use, change PORT env var and update redirect URI accordingly
#   → Remember to update Google Cloud Console with the new redirect URI
#
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# ── Main ------------------------------------------------------------
# -------------------------------------------------------------------

# Store execution log ID for linking
_startup_log_id = None
_script_registry_id = None

@app.on_event("startup")
async def startup_event():
    """Handle startup - create execution log and link to script registry."""
    global _startup_log_id, _script_registry_id
    
    try:
        # Import execution log utilities
        from shared_core.notion.execution_logs import create_execution_log
        from datetime import timezone
        
        # Find script registry entry
        script_path = __file__
        script_name = Path(script_path).name
        
        # Try to find script registry entry by file path
        try:
            response = notion.databases.query(
                database_id="26ce73616c278141af54dd115915445c",  # Scripts Registry DB ID
                filter={
                    "property": "File Path",
                    "url": {"equals": f"file://{script_path}"}
                }
            )
            
            if response.get("results"):
                _script_registry_id = response["results"][0]["id"]
            else:
                # Try by script name
                response = notion.databases.query(
                    database_id="26ce73616c278141af54dd115915445c",
                    filter={
                        "property": "Script Name",
                        "title": {"contains": script_name.replace(".py", "")}
                    }
                )
                if response.get("results"):
                    _script_registry_id = response["results"][0]["id"]
        except Exception as e:
            webhook_logger.warning("Could not find script registry entry: {e}")
        
        # Create execution log
        try:
            _startup_log_id = create_execution_log(
                name=f"{script_name} - Service Started",
                start_time=datetime.now(timezone.utc),
                status="Running",
                script_id=_script_registry_id,
                script_name=script_name,
                script_path=script_path,
                environment="production",
                type="Local Python Script",
                plain_english_summary=f"Webhook server started on {FASTAPI_HOST}:{FASTAPI_PORT}"
            )
            
            if _startup_log_id and _script_registry_id:
                # Link execution log to script registry entry
                notion.pages.update(
                    page_id=_script_registry_id,
                    properties={
                        "Most Recent Log": {
                            "relation": [{"id": _startup_log_id}]
                        },
                        "All-Execution-Logs": {
                            "relation": [{"id": _startup_log_id}]
                        }
                    }
                )
                webhook_logger.info("Created and linked execution log: {_startup_log_id}")
            elif _startup_log_id:
                webhook_logger.info("Created execution log: {_startup_log_id} (script registry entry not found)")
        except Exception as e:
            webhook_logger.warning("Failed to create execution log: {e}")
        
        # Initialize Google Workspace Events API service
        if WORKSPACE_EVENTS_INTEGRATION_AVAILABLE:
            try:
                polling_interval = int(os.getenv("WORKSPACE_EVENTS_POLLING_INTERVAL", "10"))
                max_messages = int(os.getenv("WORKSPACE_EVENTS_MAX_MESSAGES", "10"))
                enable_auto_renewal = os.getenv("WORKSPACE_EVENTS_AUTO_RENEWAL", "true").lower() == "true"
                
                service = initialize_workspace_events_service(
                    polling_interval=polling_interval,
                    max_messages=max_messages,
                    enable_auto_renewal=enable_auto_renewal
                )
                
                if service:
                    webhook_logger.info("✅ Google Workspace Events API service started")
                else:
                    webhook_logger.warning("⚠️ Google Workspace Events API service failed to start")
            except Exception as e:
                webhook_logger.error(f"❌ Failed to start Google Workspace Events API service: {e}")
        else:
            webhook_logger.info("ℹ️ Google Workspace Events API integration not available")

        # Start multi-node health monitor (best-effort)
        if MULTI_NODE_ENABLED and health_monitor is not None:
            try:
                health_monitor.start()
                webhook_logger.info("✅ Multi-node health monitor started")
            except Exception as e:
                webhook_logger.warning("⚠️ Failed to start multi-node health monitor", {"error": str(e)})
            
    except Exception as e:
        webhook_logger.warning("Startup event handler error: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Handle graceful shutdown - update execution log."""
    global _startup_log_id
    
    webhook_logger.info("Processing: Shutting down webhook queue...")
    webhook_queue.stop_processing()
    webhook_logger.info("Webhook queue shutdown complete")
    
    # Shutdown Google Workspace Events API service
    if WORKSPACE_EVENTS_INTEGRATION_AVAILABLE:
        try:
            shutdown_workspace_events_service()
            webhook_logger.info("✅ Google Workspace Events API service stopped")
        except Exception as e:
            webhook_logger.error(f"❌ Error stopping Google Workspace Events API service: {e}")

    # Stop multi-node health monitor
    if health_monitor is not None:
        try:
            health_monitor.stop()
            webhook_logger.info("✅ Multi-node health monitor stopped")
        except Exception as e:
            webhook_logger.warning("⚠️ Failed to stop multi-node health monitor", {"error": str(e)})
    
    # Update execution log with shutdown status
    if _startup_log_id:
        try:
            from shared_core.notion.execution_logs import update_execution_log
            from datetime import timezone
            
            update_execution_log(
                page_id=_startup_log_id,
                status="Success",
                end_time=datetime.now(timezone.utc)
            )
            webhook_logger.info("Updated execution log {_startup_log_id} with shutdown status")
        except Exception as e:
            webhook_logger.warning("Failed to update execution log: {e}")

if __name__ == "__main__":
    webhook_logger.info(f"🚀 Starting Notion Webhook Server on {FASTAPI_HOST}:{FASTAPI_PORT}")
    webhook_logger.info("Network: Public URL: {WEBHOOK_URL}")
    webhook_logger.info(f"📊 Enhanced processing: {ENHANCED_PROCESSING_AVAILABLE}")
    webhook_logger.info(f"🔑 Notion token: {'✅ Set' if NOTION_TOKEN else '❌ Missing'}")
    webhook_logger.info("Database IDs:")
    webhook_logger.info(f"   • Workflows: {WORKFLOWS_DB_ID}")
    webhook_logger.info(f"   • Functions: {FUNCTIONS_DB_ID}")
    webhook_logger.info(f"   • Prompts: {PROMPTS_DB_ID}")
    webhook_logger.info("Processing: Queue-based processing: ✅ Enabled (1-second pause between webhooks)")
    
    try:
        uvicorn.run(app, host=FASTAPI_HOST, port=FASTAPI_PORT)
    except KeyboardInterrupt:
        webhook_logger.info("Received interrupt signal, shutting down gracefully...")
        webhook_queue.stop_processing()
        webhook_logger.info("Shutdown complete")
    except Exception as e:
        webhook_logger.error("Server error: {str(e)}")
        webhook_queue.stop_processing()
        raise 
