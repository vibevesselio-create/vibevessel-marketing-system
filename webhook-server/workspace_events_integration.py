#!/usr/bin/env python3
"""
Google Workspace Events API Integration for Webhook Server
==========================================================

Integrates Google Workspace Events API processing into the Notion webhook server
for persistent, resource-efficient background execution.

Author: Seren Media Workflows
Created: 2026-01-18
"""

import os
import sys
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Add workspace_events to path
# Try multiple possible paths
possible_paths = [
    Path(__file__).resolve().parents[1] / "seren-media-workflows" / "scripts" / "workspace_events",
    Path(__file__).resolve().parents[0] / ".." / "seren-media-workflows" / "scripts" / "workspace_events",
    Path("/Users/brianhellemn/Projects/github-production/seren-media-workflows/scripts/workspace_events"),
]

workspace_events_path = None
for path in possible_paths:
    resolved_path = path.resolve() if path.exists() else None
    if resolved_path and resolved_path.exists():
        workspace_events_path = resolved_path
        sys.path.insert(0, str(resolved_path.parent))
        sys.path.insert(0, str(resolved_path))
        break

try:
    # Try importing workspace events modules
    if workspace_events_path and workspace_events_path.exists():
        # Add parent directory to path for proper module imports
        parent_path = str(workspace_events_path.parent)
        if parent_path not in sys.path:
            sys.path.insert(0, parent_path)
        
        # Import using module path
        from workspace_events.core.event_handler import WorkspaceEventHandler
        
        # Subscription manager is optional - only needed for subscription management
        # For message processing, we only need event_handler and pubsub
        SubscriptionManager = None
        try:
            from workspace_events.subscription_manager import SubscriptionManager
        except Exception:
            # Subscription manager not available - that's OK, we can still process messages
            logging.debug("Subscription manager not available (optional)")
        
        try:
            from google.cloud import pubsub_v1
        except ImportError:
            # Try alternative import
            try:
                import google.cloud.pubsub_v1 as pubsub_v1
            except ImportError:
                raise ImportError("google-cloud-pubsub not installed")
        WORKSPACE_EVENTS_AVAILABLE = True
    else:
        WORKSPACE_EVENTS_AVAILABLE = False
        logging.warning("Workspace events path not found")
except ImportError as e:
    WORKSPACE_EVENTS_AVAILABLE = False
    logging.warning(f"Google Workspace Events API not available: {e}")
except Exception as e:
    WORKSPACE_EVENTS_AVAILABLE = False
    logging.warning(f"Google Workspace Events API initialization error: {e}")

logger = logging.getLogger(__name__)


class WorkspaceEventsService:
    """
    Background service for processing Google Workspace Events API messages.
    
    Features:
    - Pulls messages from Pub/Sub subscription
    - Processes events through WorkspaceEventHandler
    - Resource-efficient with configurable polling intervals
    - Automatic error recovery
    - Health monitoring
    """
    
    def __init__(
        self,
        polling_interval: int = 10,
        max_messages: int = 10,
        enable_auto_renewal: bool = True,
        renewal_check_interval: int = 3600  # 1 hour
    ):
        """
        Initialize Workspace Events service.
        
        Args:
            polling_interval: Seconds between Pub/Sub polls (default: 10)
            max_messages: Max messages to pull per poll (default: 10)
            enable_auto_renewal: Enable automatic subscription renewal (default: True)
            renewal_check_interval: Seconds between renewal checks (default: 3600)
        """
        if not WORKSPACE_EVENTS_AVAILABLE:
            raise RuntimeError("Google Workspace Events API modules not available")
        
        self.polling_interval = polling_interval
        self.max_messages = max_messages
        self.enable_auto_renewal = enable_auto_renewal
        self.renewal_check_interval = renewal_check_interval
        
        # Initialize components
        self.event_handler = None
        self.subscription_manager = None
        self.subscriber = None
        self.subscription_path = None
        
        # Background thread control
        self.running = False
        self.processing_thread = None
        self.renewal_thread = None
        self.stop_event = threading.Event()
        
        # Statistics
        self.stats = {
            'messages_processed': 0,
            'messages_failed': 0,
            'last_poll_time': None,
            'last_renewal_check': None,
            'subscriptions_renewed': 0,
            'errors': []
        }
        
        self._initialize()
    
    def _initialize(self):
        """Initialize Google API clients and handlers."""
        try:
            # Initialize event handler
            self.event_handler = WorkspaceEventHandler()
            logger.info("✅ WorkspaceEventHandler initialized")
            
            # Initialize subscription manager (optional - only needed for subscription management)
            if SubscriptionManager:
                try:
                    self.subscription_manager = SubscriptionManager()
                    logger.info("✅ SubscriptionManager initialized")
                except Exception as e:
                    logger.warning(f"⚠️ SubscriptionManager initialization failed (optional): {e}")
                    self.subscription_manager = None
            else:
                logger.info("ℹ️ SubscriptionManager not available (optional)")
                self.subscription_manager = None
            
            # Initialize Pub/Sub subscriber
            from config import WORKSPACE_EVENTS_CONFIG, get_pubsub_subscription_path
            self.subscription_path = get_pubsub_subscription_path()
            
            # Get credentials
            from google.auth import default
            credentials, project = default()
            
            self.subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
            logger.info(f"✅ Pub/Sub subscriber initialized (subscription: {self.subscription_path})")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Workspace Events service: {e}")
            raise
    
    def start(self):
        """Start the background processing service."""
        if self.running:
            logger.warning("Workspace Events service already running")
            return
        
        self.running = True
        self.stop_event.clear()
        
        # Start message processing thread
        self.processing_thread = threading.Thread(
            target=self._process_messages_loop,
            daemon=True,
            name="WorkspaceEventsProcessor"
        )
        self.processing_thread.start()
        logger.info("✅ Started Workspace Events message processing thread")
        
        # Start subscription renewal thread
        if self.enable_auto_renewal:
            self.renewal_thread = threading.Thread(
                target=self._renewal_check_loop,
                daemon=True,
                name="WorkspaceEventsRenewal"
            )
            self.renewal_thread.start()
            logger.info("✅ Started Workspace Events subscription renewal thread")
        
        logger.info("🚀 Workspace Events service started")
    
    def stop(self, timeout: float = 10.0):
        """Stop the background processing service."""
        if not self.running:
            return
        
        logger.info("Stopping Workspace Events service...")
        self.running = False
        self.stop_event.set()
        
        # Wait for threads to finish
        if self.processing_thread:
            self.processing_thread.join(timeout=timeout)
        
        if self.renewal_thread:
            self.renewal_thread.join(timeout=timeout)
        
        logger.info("✅ Workspace Events service stopped")
    
    def _process_messages_loop(self):
        """Main loop for processing Pub/Sub messages."""
        logger.info("📥 Starting Pub/Sub message processing loop")
        
        while self.running and not self.stop_event.is_set():
            try:
                # Pull messages from Pub/Sub
                response = self.subscriber.pull(
                    request={
                        "subscription": self.subscription_path,
                        "max_messages": self.max_messages,
                    }
                )
                
                received_messages = response.received_messages if hasattr(response, 'received_messages') else []
                
                if received_messages:
                    logger.info(f"📨 Received {len(received_messages)} messages")
                    
                    # Collect ack_ids for batch acknowledgment
                    ack_ids_to_ack = []
                    ack_ids_to_nack = []
                    
                    for received_message in received_messages:
                        try:
                            # Extract message data from ReceivedMessage structure
                            # ReceivedMessage has: .ack_id, .message (PubsubMessage), .delivery_attempt
                            # PubsubMessage has: .data (bytes), .attributes (dict), .message_id (str)
                            if hasattr(received_message, 'message'):
                                message_obj = received_message.message
                                message_data = message_obj.data if hasattr(message_obj, 'data') else b''
                                message_attributes = dict(message_obj.attributes) if hasattr(message_obj, 'attributes') else {}
                                message_id = message_obj.message_id if hasattr(message_obj, 'message_id') else received_message.ack_id
                            else:
                                # Fallback for different API versions
                                message_data = getattr(received_message, 'data', b'')
                                message_attributes = dict(getattr(received_message, 'attributes', {}))
                                message_id = getattr(received_message, 'message_id', getattr(received_message, 'ack_id', 'unknown'))
                            
                            ack_id = received_message.ack_id

                            # SAFEGUARD: Ack ONLY after successful processing.
                            # We bypass the handler's queue-based pubsub wrapper here and process synchronously
                            # to preserve at-least-once semantics and prevent message loss.
                            event = self.event_handler.parse_cloudevent(message_data, message_attributes or {})
                            if not event:
                                ack_ids_to_nack.append(ack_id)
                                self.stats['messages_failed'] += 1
                                logger.warning("⚠️ Failed to parse CloudEvent; scheduling retry")
                                continue

                            processed_event = self.event_handler.process_event(event, request_id=message_id or ack_id)
                            if processed_event and processed_event.processed:
                                ack_ids_to_ack.append(ack_id)
                                self.stats['messages_processed'] += 1
                                logger.info(f"✅ Processed event: {processed_event.event_id}")
                            else:
                                ack_ids_to_nack.append(ack_id)
                                self.stats['messages_failed'] += 1
                                error_msg = processed_event.error if processed_event and processed_event.error else "Unknown error"
                                logger.warning(f"⚠️ Failed to process event; scheduling retry: {error_msg}")
                        
                        except Exception as e:
                            logger.error(f"❌ Error processing message: {e}", exc_info=True)
                            # Nack failed messages for retry
                            if hasattr(received_message, 'ack_id'):
                                ack_ids_to_nack.append(received_message.ack_id)
                            self.stats['messages_failed'] += 1
                            self.stats['errors'].append({
                                'time': datetime.now(timezone.utc).isoformat(),
                                'error': str(e)
                            })
                            # Keep only last 100 errors
                            if len(self.stats['errors']) > 100:
                                self.stats['errors'] = self.stats['errors'][-100:]
                    
                    # Batch acknowledge successful messages
                    if ack_ids_to_ack:
                        try:
                            self.subscriber.acknowledge(
                                request={
                                    "subscription": self.subscription_path,
                                    "ack_ids": ack_ids_to_ack,
                                }
                            )
                            logger.debug(f"✅ Acknowledged {len(ack_ids_to_ack)} messages")
                        except Exception as e:
                            logger.error(f"❌ Error acknowledging messages: {e}")
                    
                    # Batch nack failed messages for retry
                    if ack_ids_to_nack:
                        try:
                            self.subscriber.modify_ack_deadline(
                                request={
                                    "subscription": self.subscription_path,
                                    "ack_ids": ack_ids_to_nack,
                                    "ack_deadline_seconds": 60,  # Retry in 60 seconds
                                }
                            )
                            logger.debug(f"⚠️ Nacked {len(ack_ids_to_nack)} messages for retry")
                        except Exception as e:
                            logger.error(f"❌ Error nacking messages: {e}")
                
                self.stats['last_poll_time'] = datetime.now(timezone.utc).isoformat()
                
                # Sleep before next poll
                time.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in message processing loop: {e}", exc_info=True)
                self.stats['errors'].append({
                    'time': datetime.now(timezone.utc).isoformat(),
                    'error': str(e)
                })
                # Wait before retrying
                time.sleep(self.polling_interval)
    
    def _renewal_check_loop(self):
        """Background loop for checking and renewing subscriptions."""
        logger.info("🔄 Starting subscription renewal check loop")
        
        while self.running and not self.stop_event.is_set():
            try:
                # Check subscription health
                health = self.subscription_manager.check_subscription_health()
                
                # Auto-renew expiring subscriptions
                renewed = self.subscription_manager.auto_renew_expiring_subscriptions()
                
                if renewed:
                    self.stats['subscriptions_renewed'] += len(renewed)
                    logger.info(f"✅ Renewed {len(renewed)} subscriptions")
                
                self.stats['last_renewal_check'] = datetime.now(timezone.utc).isoformat()
                
                # Sleep until next check
                time.sleep(self.renewal_check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in renewal check loop: {e}", exc_info=True)
                # Wait before retrying
                time.sleep(300)  # Retry in 5 minutes
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status and statistics."""
        return {
            'running': self.running,
            'polling_interval': self.polling_interval,
            'max_messages': self.max_messages,
            'auto_renewal_enabled': self.enable_auto_renewal,
            'stats': self.stats.copy(),
            'subscription_path': self.subscription_path
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        health = {
            'status': 'healthy' if self.running else 'stopped',
            'initialized': self.event_handler is not None,  # Subscription manager is optional
            'subscription_accessible': False,
            'last_poll': self.stats.get('last_poll_time'),
            'messages_processed': self.stats['messages_processed'],
            'messages_failed': self.stats['messages_failed']
        }
        
        # Check subscription accessibility
        try:
            if self.subscription_manager:
                sub_health = self.subscription_manager.check_subscription_health()
                health['subscription_accessible'] = True
                health['subscription_health'] = sub_health
        except Exception as e:
            health['subscription_error'] = str(e)
        
        return health


# Global service instance
_workspace_events_service: Optional[WorkspaceEventsService] = None


def get_workspace_events_service() -> Optional[WorkspaceEventsService]:
    """Get global Workspace Events service instance."""
    return _workspace_events_service


def initialize_workspace_events_service(
    polling_interval: int = 10,
    max_messages: int = 10,
    enable_auto_renewal: bool = True
) -> Optional[WorkspaceEventsService]:
    """
    Initialize and start the Workspace Events service.
    
    Args:
        polling_interval: Seconds between Pub/Sub polls
        max_messages: Max messages per poll
        enable_auto_renewal: Enable subscription auto-renewal
        
    Returns:
        WorkspaceEventsService instance or None if unavailable
    """
    global _workspace_events_service
    
    if not WORKSPACE_EVENTS_AVAILABLE:
        logger.warning("⚠️ Google Workspace Events API not available, skipping initialization")
        return None
    
    try:
        _workspace_events_service = WorkspaceEventsService(
            polling_interval=polling_interval,
            max_messages=max_messages,
            enable_auto_renewal=enable_auto_renewal
        )
        _workspace_events_service.start()
        logger.info("✅ Workspace Events service initialized and started")
        return _workspace_events_service
    except Exception as e:
        logger.error(f"❌ Failed to initialize Workspace Events service: {e}")
        return None


def shutdown_workspace_events_service():
    """Shutdown the Workspace Events service."""
    global _workspace_events_service
    
    if _workspace_events_service:
        _workspace_events_service.stop()
        _workspace_events_service = None
        logger.info("✅ Workspace Events service shut down")
