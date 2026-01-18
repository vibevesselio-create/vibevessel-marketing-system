#!/usr/bin/env bash
#
# MM2 Deploy Script (Mac Mini M1 Pro worker)
# =========================================
#
# Installs dependencies and sets up a persistent launchd service for the MM2
# worker webhook server (`mm2_webhook_server.py`).
#
# This script is intended to be run ON the MM2 machine.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$SCRIPT_DIR"

echo "📦 MM2 deploy starting in: $SCRIPT_DIR"
echo "📁 Repo root: $REPO_ROOT"

# Use local venv (keeps macOS Python environments clean).
if [ ! -d ".venv" ]; then
  echo "🐍 Creating venv..."
  python3 -m venv .venv
fi

echo "🐍 Activating venv..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "📦 Installing dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Dependencies installed."

# Runtime env defaults for MM2
export WORKSPACE_EVENTS_NODE_ID="${WORKSPACE_EVENTS_NODE_ID:-mm2}"
export PORT="${PORT:-5002}"

echo "📋 Env:"
echo "   - WORKSPACE_EVENTS_NODE_ID=$WORKSPACE_EVENTS_NODE_ID"
echo "   - PORT=$PORT"

# Create LaunchAgent
PLIST_PATH="$HOME/Library/LaunchAgents/com.seren.webhook-server-mm2.plist"
LOG_DIR="$HOME/Library/Logs"
STDOUT_LOG="$LOG_DIR/webhook-server-mm2-stdout.log"
STDERR_LOG="$LOG_DIR/webhook-server-mm2-stderr.log"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

echo "🧩 Writing launchd plist: $PLIST_PATH"
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.seren.webhook-server-mm2</string>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${SCRIPT_DIR}/.venv/bin/python</string>
    <string>${SCRIPT_DIR}/mm2_webhook_server.py</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>WORKSPACE_EVENTS_NODE_ID</key>
    <string>${WORKSPACE_EVENTS_NODE_ID}</string>
    <key>PORT</key>
    <string>${PORT}</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
EOF

echo "🚀 Loading launchd service..."
launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"

echo "✅ MM2 worker service installed and started."
echo "🔎 Logs:"
echo "   - $STDOUT_LOG"
echo "   - $STDERR_LOG"
echo
echo "Health check (from MM2):"
echo "  curl http://localhost:${PORT}/health"
echo "  curl http://localhost:${PORT}/status"

