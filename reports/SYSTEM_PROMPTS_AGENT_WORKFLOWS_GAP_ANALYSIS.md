# System Prompts → Agent Workflows & Functions Integration — Gap Analysis

**Generated:** 2026-01-18  
**Project (Notion):** `https://www.notion.so/System-Prompts-Agent-Workflows-Functions-Integration-2e2e73616c27816b997ae1b6f73978ff`  

## Scope

Inventory the **system prompts directory**, identify whether corresponding **Agent-Workflows** / **Agent-Functions** exist in Notion, and create the **Agent-Tasks** needed to close the gaps.

## System Prompts Inventory (source-of-truth)

Directory: `/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/MM1-MM2-Sync/system-prompts/`

- **`Music Track Synchronization Prompt.rtf`**: Production single-track sync workflow (auto-detect mode chain), anchored on `monolithic-scripts/soundcloud_download_prod_merge-2.py`.
- **`Music Playlist Synchronization Prompt.rtf`**: Production playlist sync workflow, anchored on `scripts/sync_soundcloud_playlist.py` + track processing via `monolithic-scripts/soundcloud_download_prod_merge-2.py`.
- **`Eagle Library Deduplication Prompt.rtf`**: Production Eagle library deduplication workflow (scan/detect/report/optional cleanup), anchored on `monolithic-scripts/soundcloud_download_prod_merge-2.py`.
- **`Eagle Music Library Deduplication - System Compliant Prompt.rtf`**: Same as above, but with explicit **Notion compliance gating** (music directories + Eagle libraries documented before running).
- **`Workflow Implementation Audit.rtf`**: Notion-first runtime health + handoff orchestrator prompt (foundational stack compliance focus).
- **`Plans Directory Audit and Completion Review Prompt.rtf`**: Audit Cursor plans directory and reconcile planned vs executed work.
- **`Plans Directory Audit - P2 Prompt.rtf`**: **File appears corrupted / not parseable as text** (needs repair/replacement).
- **`Cursor-MM1-Work-Audit-and-Validation-Prompt.md`**: Audit Cursor-MM1 agent work sessions using evidence-based verification.
- **`In-Progress Issue + Project Continuation Prompt.txt`**: General “continue in-progress work” execution directive.
- **`In-Progress Issue + Project Continuation Prompt-notion-ai-data-operations.txt`**: Notion-only “Data Ops” variant of the above.
- **`python scripts:run_fingerprint_dedup_production-log.rtf`**: A captured production run log; should be converted into a canonical, reusable workflow prompt (not a log-as-prompt).

## Existing Notion Coverage (high-level finding)

Using targeted Notion keyword scans of **Agent-Workflows** and **Agent-Functions** (report artifact: `reports/system_prompts_gap_analysis_notionscan_20260118.json`), there are **no clear, prompt-named dedicated workflow/function items** for most of the above prompts (notably: Music Track/Playlist, Plans Audit, Cursor-MM1 audit, In-Progress continuation variants).

This indicates a **modeling gap**: system prompts exist, but the Notion control plane (workflows/functions) is not consistently created/linked for them.

## Remediation: Agent-Tasks Created in Notion (linked to project)

All tasks below are linked to project `2e2e7361-6c27-816b-997a-e1b6f73978ff` via the `🤖 Agent-Projects` relation and are created as **Status = Ready**.

- **Music Track workflow+functions**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Functions-Music-Track-Sync-Workflow-Production-2ece73616c278174ab70e203e1a7e868`
- **Music Playlist workflow+functions**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Functions-Music-Playlist-Sync-Workflow-Production-2ece73616c2781e686faf3302ccc759b`
- **Eagle Dedup (Production) workflow+functions**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Functions-Eagle-Library-Deduplication-Workflow-Production-2ece73616c2781a9b4a3c2869030cbbc`
- **Eagle Dedup (System Compliant) workflow+functions**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Functions-Eagle-Deduplication-Workflow-System-Compliant-2ece73616c2781608e67fb6d9792d2b6`
- **Workflow Implementation Audit / Notion-first orchestrator workflow**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Workflow-Implementation-Audit-Notion-First-Runtime-Health-O-2ece73616c2781118c11ce4f2e0b100b`
- **Plans Directory Audit workflow**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Plans-Directory-Audit-and-Completion-Review-2ece73616c278184a8c8e974c0bd4b23`
- **Repair/replace corrupted P2 prompt + map to workflow**: `https://www.notion.so/System-Prompts-Repair-Replace-Prompt-Plans-Directory-Audit-P2-Prompt-corrupt-RTF-map-to-work-2ece73616c2781e6abf8f86951ba0da8`
- **Cursor MM1 Work Audit workflow**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-Cursor-MM1-Agent-Work-Audit-and-Validation-2ece73616c2781c8864aefa6c0bee82d`
- **In-Progress Issue + Project Continuation workflow**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-In-Progress-Issue-Project-Continuation-2ece73616c278141bcafdbc924208b41`
- **In-Progress continuation (Notion AI DataOps) workflow**: `https://www.notion.so/System-Prompts-Create-Agent-Workflow-In-Progress-Issue-Project-Continuation-Notion-AI-DataOps-2ece73616c2781edb62bc38ca18a8882`
- **Convert run log prompt to canonical workflow**: `https://www.notion.so/System-Prompts-Convert-Run-Log-Prompt-to-Canonical-Workflow-run_fingerprint_dedup_production-Prod-2ece73616c2781a4ae34efe566136c91`

## Recommended Execution Order (for next agent)

1. **Plans Directory Audit (and P2 prompt repair)** — unblocks systematic backlog cleanups.
2. **Workflow Implementation Audit / Notion-first orchestrator** — establishes canonical workflow modeling patterns.
3. **Music Track + Playlist workflows** — production-critical, high reuse.
4. **Eagle Dedup workflows (production + system-compliant)** — production-critical, risk-sensitive.
5. **Cursor MM1 Work Audit workflow** — governance/compliance.
6. **In-Progress continuation workflows (general + DataOps)** — operational hygiene.
7. **Convert fingerprint dedup “log prompt” to canonical workflow** — reduce future drift.

