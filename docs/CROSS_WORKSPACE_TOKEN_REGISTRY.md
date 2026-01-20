# Cross-Workspace Token Registry

**Last Updated:** 2026-01-19
**Maintained By:** Cursor MM1 Agent

---

## Active Tokens

### 1. Primary Workspace (Seren Internal)

| Property | Value |
|----------|-------|
| Integration Name | Cursor MM1 Agent |
| Workspace | Seren Media Internal |
| Token Variable | `NOTION_TOKEN` |
| Status | **VALID** |
| Last Verified | 2026-01-19 |

### 2. VibeVessel Client Workspace

| Property | Value |
|----------|-------|
| Integration Name | Client-DriveSheetsSync |
| Workspace | VibeVessel Client Workspace |
| Token Variable | `NOTION_VIBEVESSELCLIENT_TOKEN` |
| Status | **VALID** |
| Last Verified | 2026-01-19 |
| Database Parent Page | `2cf33d7a-491b-806d-8ac7-f401ddde95f9` |

### 3. VibeVessel Automations Workspace

| Property | Value |
|----------|-------|
| Integration Name | VibeVessel-Automations-WS |
| Workspace | VibeVessel Automations Workspace |
| Token Variable | `NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN` |
| Status | **VALID** |
| Last Verified | 2026-01-19 |

### 4. VibeVessel Music Workspace (Admin's Space)

| Property | Value |
|----------|-------|
| Integration Name | VibeVessel-Music-WS |
| Workspace | VibeVessel Admin's Space |
| Token Variable | `NOTION_VIBEVESSEL_MUSIC_TOKEN` |
| Status | **PENDING ACCESS** |
| Last Verified | 2026-01-19 |
| Database Parent Page | `2ed9037e-a041-80c0-89c9-d8a23a44c072` |

**ACTION REQUIRED:** The integration needs a page shared with it before databases can be transferred.
1. In Notion, create a page named `database-parent-page` in the VibeVessel Music workspace
2. Click the "..." menu on the page > "Add connections" > Select "VibeVessel-Music-WS"
3. Copy the page ID and update `CLIENT_WORKSPACE_CONFIG` in `scripts/cross_workspace_sync.py`

---

## Token Storage Locations

### Local Files

1. **`.env`** - Environment variables for Python scripts
   ```
   NOTION_TOKEN=<token-from-notion-integration-page>
   NOTION_VIBEVESSELCLIENT_TOKEN=<client-workspace-token>
   NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN=<automations-workspace-token>
   NOTION_VIBEVESSEL_MUSIC_TOKEN=<music-workspace-token>
   ```

2. **`~/.notion_token_cache`** - Primary token cache (managed by token_manager)

3. **`~/.config/notion_script_runner/config.json`** - Config file (deprecated)

### Notion Databases

1. **system-environments** (`26ce7361-6c27-8195-8726-f6aeb5b9cd95`)
   - Property: `Primary-Token`
   - Contains tokens for each workspace environment

---

## Usage Pattern

```python
from shared_core.notion.token_manager import get_notion_token
import os

# Primary workspace
primary_token = get_notion_token()

# Client workspaces - use environment variables
client_token = os.getenv('NOTION_VIBEVESSELCLIENT_TOKEN')
automations_token = os.getenv('NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN')
music_token = os.getenv('NOTION_VIBEVESSEL_MUSIC_TOKEN')
```

---

## Security Notes

1. **NEVER commit actual tokens to git** - Use environment variables
2. **Tokens are stored in:**
   - `.env` file (gitignored)
   - `~/.notion_token_cache` (system-level)
   - Notion `system-environments` database
3. **Pre-commit hooks** validate no hardcoded tokens are committed
4. **GitHub Push Protection** blocks pushes containing API tokens

---

## Token Refresh Procedure

If a token becomes invalid:

1. Check the Notion integration settings at https://www.notion.so/my-integrations
2. Regenerate the secret if needed
3. Update ALL storage locations:
   - `.env` file
   - `~/.notion_token_cache`
   - `system-environments` database in Notion
4. Test with: `python -c "from shared_core.notion.token_manager import get_notion_token; print(get_notion_token()[-5:])"`
