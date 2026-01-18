#!/bin/bash
#
# Start Webhook Server with Google Workspace Events API Integration
# =================================================================
#
# This script starts the webhook server with Google Workspace Events API
# integration enabled for persistent background processing.
#
# Author: Seren Media Workflows
# Created: 2026-01-18
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Notion Webhook Server with Google Workspace Events API Integration"
echo "================================================================================"
echo ""

# Ensure a local venv exists (avoids PEP 668 / externally-managed pip issues)
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment (venv)..."
    python3 -m venv venv
fi

echo "📦 Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
echo "🔍 Checking dependencies..."
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "⚠️  FastAPI not found. Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Check Google Workspace Events dependencies (optional)
if ! python3 -c "from google.cloud import pubsub_v1" 2>/dev/null; then
    echo "⚠️  Google Cloud Pub/Sub not found. Workspace Events integration will be disabled."
    echo "   To enable, install: pip install google-cloud-pubsub"
fi

# Set environment variables if not already set
export WORKSPACE_EVENTS_POLLING_INTERVAL=${WORKSPACE_EVENTS_POLLING_INTERVAL:-10}
export WORKSPACE_EVENTS_MAX_MESSAGES=${WORKSPACE_EVENTS_MAX_MESSAGES:-10}
export WORKSPACE_EVENTS_AUTO_RENEWAL=${WORKSPACE_EVENTS_AUTO_RENEWAL:-true}

echo ""
echo "📋 Configuration:"
echo "   - Polling Interval: ${WORKSPACE_EVENTS_POLLING_INTERVAL}s"
echo "   - Max Messages: ${WORKSPACE_EVENTS_MAX_MESSAGES}"
echo "   - Auto Renewal: ${WORKSPACE_EVENTS_AUTO_RENEWAL}"
echo ""

# Start the server
echo "🌐 Starting webhook server..."
echo ""

python3 notion_event_subscription_webhook_server_v5_multi_node.py
