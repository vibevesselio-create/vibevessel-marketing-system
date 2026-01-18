#!/usr/bin/env bash
set -euo pipefail

tunnel_id="8f70cf6f-551f-4fb7-b1f9-0349f2f688f3"
endpoint="https://webhook.vibevessel.space/health"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found in PATH" >&2
  exit 1
fi

echo "== Cloudflared tunnel status =="
cloudflared tunnel info "$tunnel_id" || true

echo ""
echo "== DNS resolution =="
dig webhook.vibevessel.space +short || true

if command -v curl >/dev/null 2>&1; then
  echo ""
  echo "== HTTPS health check =="
  curl -I --max-time 10 "$endpoint" || true
fi
