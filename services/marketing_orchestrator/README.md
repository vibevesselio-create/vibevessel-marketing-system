## Marketing Orchestrator (Notion-driven)

Minimal local orchestrator for the Notion-centric marketing system described in `Marketing-tool-search.md`.

### What this does (Phase 1 skeleton)

- Polls a Notion `Publish Jobs` database for jobs that are:
  - `Execution Layer = Python`
  - `Execution Status ∈ {Not Started, Retry}`
  - `Scheduled Time (UTC) <= now`
- Marks the job `In Progress`
- Creates an Execution-Logs entry
- Marks the job `Succeeded` (no external posting yet)

### Environment variables

- **Notion**
  - `NOTION_TOKEN` (or `NOTION_API_TOKEN` / `VV_AUTOMATIONS_WS_TOKEN`)
  - `NOTION_MARKETING_PUBLISH_JOBS_DB_ID` (required)

- **Optional (property name overrides)**
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_EXECUTION_LAYER` (default: `Execution Layer`)
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_EXECUTION_STATUS` (default: `Execution Status`)
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_SCHEDULED_TIME` (default: `Scheduled Time (UTC)`)
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_LAST_RUN_TS` (default: `Last Run Timestamp`)
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_LAST_RUN_LOG` (default: `Last Run Log`)
  - `NOTION_MARKETING_PUBLISH_JOBS_PROP_LOG_PAGE` (default: `Log Page`)

- **Runtime**
  - `MARKETING_ORCH_DRY_RUN=1` to avoid any Notion writes
  - `MARKETING_ORCH_PAGE_SIZE=10` to cap jobs per run

### Run

From repo root:

```bash
python3 scripts/run_marketing_orchestrator.py
```

