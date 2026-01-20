# VibeVessel OAuth Credentials

This directory contains OAuth 2.0 client credentials for the VibeVessel workspace.

## Required File

**Filename:** `client_secret_2_797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com.json`

**Download From:** https://console.cloud.google.com/apis/credentials?project=797362328200

## Download Instructions

1. Open the Google Cloud Console URL above
2. Navigate to "OAuth 2.0 Client IDs"
3. Find client: `797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com`
4. Click the download button (JSON format)
5. Save to this directory with the exact filename above

## Verification

After downloading, verify the file contains valid JSON with the correct client_id:

```bash
cat client_secret_*.json | jq .client_id
# Expected: "797362328200-9cro3bms23fse7hgqh2es4sk35hl4jln.apps.googleusercontent.com"
```

## Related

- Cross-Workspace Sync Project (VV-7)
- GAP-003 in critical blockers resolution

---
*Created: 2026-01-19 by Cursor MM1 Agent*
