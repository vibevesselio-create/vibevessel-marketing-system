# DEPRECATED - Moved to Canonical Location

**Date:** 2026-01-18
**Moved By:** Claude Cowork Agent

## New Location

The webhook server has been relocated to the canonical services-based architecture path:

```
/Users/brianhellemn/Projects/github-production/services/webhook_server/
```

## Migration Details

- All files synced to new location
- LaunchAgent templates updated to use new paths
- Documentation updated with canonical references
- Runbook already references correct path

## Do Not Use This Directory

This directory is kept temporarily for reference only. All development and operations should use:

```
services/webhook_server/
```

## Files in New Location

- `notion_event_subscription_webhook_server_v4_enhanced.py` - Main server
- `google_oauth_handler.py` - OAuth handler
- `linear_github_orchestrator.py` - Linear/GitHub sync
- `notion_webhook_status_monitor.py` - Status monitor
- `webhook_dashboard_service.py` - Dashboard service
- `requirements.txt` - Python dependencies
- `cloudflared/config.yml` - Tunnel config template
- `launchagents/` - LaunchAgent templates
- `scripts/` - Utility scripts
- `IMPLEMENTATION_SUMMARY.md` - Full documentation

## Cleanup

This directory can be safely deleted once the human confirms the canonical location is operational.
