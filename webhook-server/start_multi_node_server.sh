#!/usr/bin/env bash
#
# Start Multi-Node Webhook System (local/MM2)
# ==========================================
#
# Starts:
# - Notion webhook server + Workspace Events background consumer (v5)
# - Dashboard service v2 (multi-node endpoints)
#
# Notes:
# - Uses a local venv (./venv) to avoid PEP 668 restrictions.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$SCRIPT_DIR"

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "🚀 Starting multi-node services from: $SCRIPT_DIR"

if [ ! -d "venv" ]; then
  echo "📦 Creating venv..."
  python3 -m venv venv
fi

echo "📦 Activating venv..."
# shellcheck disable=SC1091
source venv/bin/activate

echo "🔧 Installing/updating dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

export WORKSPACE_EVENTS_NODE_ID="${WORKSPACE_EVENTS_NODE_ID:-local}"
export WEBHOOK_DASHBOARD_PORT="${WEBHOOK_DASHBOARD_PORT:-5003}"

echo "📋 Env:"
echo "   - WORKSPACE_EVENTS_NODE_ID=$WORKSPACE_EVENTS_NODE_ID"
echo "   - WEBHOOK_DASHBOARD_PORT=$WEBHOOK_DASHBOARD_PORT"

echo "🌐 Starting dashboard (v2)..."
python webhook_dashboard_service_v2.py &
DASH_PID=$!

echo "🌐 Starting webhook server (v5)..."
python notion_event_subscription_webhook_server_v5_multi_node.py &
WEBHOOK_PID=$!

cleanup() {
  echo "🛑 Shutting down..."
  kill "$WEBHOOK_PID" "$DASH_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait "$WEBHOOK_PID" "$DASH_PID"

