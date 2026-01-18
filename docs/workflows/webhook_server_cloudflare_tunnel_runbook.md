# Webhook Server Cloudflare Tunnel Runbook

## Purpose
Start and validate the Cloudflare tunnel for the Notion webhook server so that `https://webhook.vibevessel.space` routes to the local webhook server running on port 5001.

## Prerequisites
- Webhook server running locally on port 5001.
- Cloudflared installed (`/opt/homebrew/bin/cloudflared`).
- Tunnel credentials file present at `~/.cloudflared/8f70cf6f-551f-4fb7-b1f9-0349f2f688f3.json`.
- Config synced between `~/.cloudflared/config.yml` and `github-production/services/webhook_server/cloudflared/config.yml`.

## Quick Validation
```bash
lsof -iTCP:5001 -sTCP:LISTEN
cloudflared tunnel info 8f70cf6f-551f-4fb7-b1f9-0349f2f688f3
curl -I https://webhook.vibevessel.space/health
```

Expected:
- Port 5001 shows a listening process.
- Tunnel info shows an active connection.
- Health endpoint returns HTTP 200.

## Start Webhook Server (local)
Adjust the script path and Python env to match the current install.
```bash
# Example only; update paths to the active script and venv
python3 "/Users/brianhellemn/Projects/github-production/services/webhook_server/notion_event_subscription_webhook_server_v4_enhanced.py"
```

## Start Cloudflared (foreground)
```bash
/opt/homebrew/bin/cloudflared tunnel --config /Users/brianhellemn/.cloudflared/config.yml run 8f70cf6f-551f-4fb7-b1f9-0349f2f688f3
```

## Install LaunchAgent (persistent)
1) Copy the LaunchAgent template:
```bash
cp github-production/services/webhook_server/launchagents/com.seren.cloudflared-tunnel.plist ~/Library/LaunchAgents/
```

2) Load it:
```bash
launchctl unload ~/Library/LaunchAgents/com.seren.cloudflared-tunnel.plist || true
launchctl load ~/Library/LaunchAgents/com.seren.cloudflared-tunnel.plist
```

3) Confirm it is running:
```bash
launchctl list | rg -i cloudflared
```

## Ensure DNS is Routed to the Tunnel
```bash
cloudflared tunnel route dns --overwrite-dns 8f70cf6f-551f-4fb7-b1f9-0349f2f688f3 webhook.vibevessel.space
```

If you see an authentication error, re-run:
```bash
cloudflared tunnel login
```
and retry the route command.

## Troubleshooting
- HTTP 530 from Cloudflare usually means the tunnel is not connected or origin is down.
- If the tunnel is connected but still 530, confirm the webhook server is listening on port 5001.
- If DNS resolves but SSL fails, check Cloudflare SSL mode and certificate issuance.

## Notion Webhook Update
Once HTTPS is stable:
- Update Notion webhook subscription URL to `https://webhook.vibevessel.space/webhook`.
- Verify Notion challenge and event delivery in the webhook server logs.

## OAuth Callback URL (Google)
The webhook server includes a Google OAuth callback endpoint. Ensure the provider console includes:
- `https://webhook.vibevessel.space/auth/google/callback`
