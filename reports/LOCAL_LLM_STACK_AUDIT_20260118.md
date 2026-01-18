# Local LLM Stack Audit Report — Mac mini M2 Pro 16GB

**Audit Date**: 2026-01-18
**Auditor**: Claude Code Agent (Opus 4.5)
**Project ID**: `local-llm-stack-m2pro16-v1`
**Priority**: High

---

## Executive Summary

| Category | Status | Summary |
|----------|--------|---------|
| **Notion Sync** | **BLOCKED** | JSON artifacts exist but NOT synced to Notion |
| **Technical Plan** | **GO with caveats** | Mostly executable; 3 critical gaps identified |
| **File System** | **GO** | Storage plan is sound; volumes verified |
| **Security** | **GO** | .gitignore properly excludes sensitive files |

**Overall Verdict**: **CONDITIONAL GO** — Proceed after addressing critical gaps below.

---

## A) Notion Compliance Audit

### Precondition Check

| Artifact | Status | Location |
|----------|--------|----------|
| Agent-Project JSON | **EXISTS** | `var/pending_notion_writes/agent_projects/20260118T173743Z__local_llm_stack_m2pro16_marketing_automation.json` |
| Agent-Tasks JSONs (12) | **ALL EXIST** | `var/pending_notion_writes/agent_tasks/20260118T173743Z__task[1-12]_*.json` |
| Notion Project Page | **NOT FOUND** | Search returned no results for "Local LLM Stack" |
| Notion Task Pages (12) | **NOT FOUND** | Search returned no results |

### Critical Finding: Notion Sync Incomplete

**The Local LLM Stack project and all 12 tasks exist as JSON files in the repo but have NOT been synced to Notion.**

The target database ID in the JSON files (`2e633d7a-491b-80ed-ba48-000bd4fe690e`) is **VALID** — it corresponds to the Tasks database (collection URL: `collection://2e633d7a-491b-80ed-ba48-000bd4fe690e`).

### Schema Compliance

The JSON files use correct property names matching the Tasks database schema:

| JSON Property | Schema Match | Notes |
|---------------|--------------|-------|
| Task Name | **VALID** | Title property |
| Description | **VALID** | Text property |
| Status | **VALID** | Select: "In Progress", "Not Started" |
| Priority | **VALID** | Select: "High", "Medium", "Low" |
| Owner | **PARTIAL** | Uses "Cursor GPT-5.2 Agent" — not in current Owner options |
| Tags | **VALID** | Text property |
| Category | **VALID** | Text property |
| External Docs Required | **VALID** | Checkbox |
| Preflight Status | **VALID** | Select: "Passed" |
| Preflight Notes | **VALID** | Text property |

### Owner Property Gap

The `Owner` select property currently has these options:
- Antonious Fayek
- Claude MM1 Agent
- Brian Hellemn

The JSON files specify `Cursor GPT-5.2 Agent` which does NOT exist in the schema. This will cause sync failure or property mismatch.

---

## B) Technical Plan Audit (Gap Analysis)

### Hardware Verification

| Spec | Expected | Verified | Status |
|------|----------|----------|--------|
| Chip | Apple M2 Pro | Apple M2 Pro | **MATCH** |
| CPU Cores | 10 (6P+4E) | 10 (6P+4E) | **MATCH** |
| Memory | 16GB unified | 16GB unified | **MATCH** |
| Internal SSD Free | ~100GB | 92GB available | **MATCH** |
| External SSD (SYSTEM_SSD) | Samsung T7 USB | Present at `/Volumes/SYSTEM_SSD` | **MATCH** |

### Model Availability Assessment

| Model | GGUF Available | Q4 Memory | License | Runtime | Status |
|-------|----------------|-----------|---------|---------|--------|
| Phi-4-mini-instruct | **YES** | ~4.5 GB | MIT | llama.cpp | **GO** |
| Gemma 2 9B | **YES** | ~5.76 GB | Gemma License | llama.cpp | **GO** |
| Qwen2.5-VL 7B | **PARTIAL** | ~5-6 GB | Apache-2.0 | llama.cpp (fork) | **CAUTION** |
| Florence-2 | **NO** | ~1-2 GB | MIT | Transformers | **GO** |
| Whisper medium | **NO** (uses ggml) | ~0.5 GB | MIT | whisper.cpp | **GO** |
| BGE-M3 | **NO** | ~0.6 GB | MIT | Transformers | **GO** |
| bge-reranker-v2-m3 | **NO** | ~0.6 GB | Apache-2.0 | Transformers | **GO** |
| Llama Guard 3 1B | **YES** | ~1 GB | Llama License | llama.cpp | **GO** |
| CLAP (optional) | **NO** | ~1-2 GB | Apache-2.0 | Transformers | **GO** |

### Critical Technical Gaps

#### GAP-1: Vision Model Requires Specialized llama.cpp Fork (CRITICAL)

**Problem**: Qwen2.5-VL 7B Instruct requires a specialized fork of llama.cpp with vision/multimodal support. Standard llama.cpp release builds do NOT support vision inference.

**Impact**: Task 5 (Vision + OCR models) cannot be completed with standard llama.cpp.

**Remediation**:
1. Use llama.cpp with multimodal support (check `docs/multimodal.md`)
2. Download both the model file AND the separate vision projection file (mmproj)
3. Consider MLX as an alternative for vision models on Apple Silicon
4. Document the fork/branch requirement in Task 5

#### GAP-2: Missing Explicit Model IDs and Checksums (HIGH)

**Problem**: The task descriptions reference model families but do not pin to specific model IDs, quantization levels, or checksums.

**Current**: "Phi-4-mini-instruct" / "Gemma 2 9B"

**Required**:
```
Model: bartowski/microsoft_Phi-4-mini-instruct-GGUF
File: Phi-4-mini-instruct-Q4_K_M.gguf
SHA256: [checksum]
Size: 2.5 GB
```

**Remediation**: Create a model manifest with exact HuggingFace repo IDs, file names, and SHA256 checksums.

#### GAP-3: No Explicit Unload/Memory Management Strategy (HIGH)

**Problem**: Tasks mention "one heavy model at a time" but lack explicit memory management implementation details.

**Required**:
- How does the gateway unload models?
- What triggers unload (explicit API call? timeout? memory pressure)?
- How is memory pressure detected?
- What's the cooldown/warmup time between model swaps?

**Remediation**: Add explicit memory management section to Task 10 (Gateway Service) and Task 12 (Performance Guardrails).

### License Compliance Check

| Model | License | Commercial OK | Attribution Required | Restrictions |
|-------|---------|---------------|---------------------|--------------|
| Phi-4-mini-instruct | MIT | **YES** | No | None |
| Gemma 2 9B | Gemma License | **YES** | Terms apply | Content policy restrictions |
| Qwen2.5-VL 7B | Apache-2.0 | **YES** | Yes (notice) | None |
| Florence-2 | MIT | **YES** | No | None |
| Whisper | MIT | **YES** | No | None |
| BGE-M3 | MIT | **YES** | No | None |
| bge-reranker-v2-m3 | Apache-2.0 | **YES** | Yes (notice) | None |
| Llama Guard 3 1B | Llama 3.1 License | **YES** | Terms apply | Meta's acceptable use policy |
| CLAP | Apache-2.0 | **YES** | Yes (notice) | Training data restrictions |

**Note**: Gemma and Llama Guard have custom licenses with usage restrictions. Review before deployment.

### 16GB Memory Budget Analysis

**Worst-case concurrent load** (should NEVER happen):
- Gemma 2 9B Q4: 5.76 GB
- Qwen2.5-VL 7B Q4: 5.5 GB
- Total: 11.26 GB (would leave only 4.7 GB for system + context)

**Recommended sequential pipeline memory budget**:

| Phase | Primary Model | Utility Models | Peak RAM |
|-------|---------------|----------------|----------|
| Transcription | Whisper medium | — | ~2 GB |
| Text Gen (routing) | Phi-4-mini Q4 | BGE-M3 | ~5.5 GB |
| Text Gen (copy) | Gemma 2 9B Q4 | — | ~6.5 GB |
| Vision | Qwen2.5-VL 7B Q4 | — | ~6.5 GB |
| OCR | Florence-2 | — | ~3 GB |
| Safety | Llama Guard 3 1B Q4 | — | ~2 GB |

**Verdict**: Plan is memory-safe IF sequential execution is enforced.

---

## C) File System Placement Audit

### Storage Verification

| Location | Type | Speed | Status | Free Space |
|----------|------|-------|--------|------------|
| Internal SSD (`/System/Volumes/Data`) | Apple Fabric | **Fastest** | Verified | 92 GB |
| `/Volumes/SYSTEM_SSD` | Samsung T7 USB | Moderate | Verified | Present |

### Proposed Layout Assessment

| Path | Purpose | Recommendation |
|------|---------|----------------|
| `/Users/brianhellemn/Library/Application Support/SerenLocalLLM/models` | Hot models | **APPROVED** — Optimal for Apple Fabric speed |
| `/Volumes/SYSTEM_SSD/SerenLocalLLM/models-archive` | Cold archive | **APPROVED** — Good for capacity |

**Note**: A `seren` directory already exists at `/Users/brianhellemn/Library/Application Support/seren`. Consider naming consistency — use `SerenLocalLLM` or `seren-local-llm` to match existing patterns.

### Backup Strategy Gap

**Not addressed in the plan**: What happens if:
- Internal SSD fills up?
- Models need to be migrated?
- Hot models need version rollback?

**Recommendation**: Add model versioning and backup strategy to Task 1 or Task 12.

---

## D) Security Audit

### Git Security

| Check | Status | Notes |
|-------|--------|-------|
| `.env` files excluded | **PASS** | `.gitignore` includes `.env`, `.env.*`, `*.env` |
| OAuth credentials excluded | **PASS** | `credentials/google-oauth/*.json` excluded |
| State files excluded | **PASS** | `var/state/**/*.json`, `var/pending_notion_writes/**/*.json` excluded |
| Client secrets excluded | **PASS** | `clients/.env.*` excluded |

### Concerns

1. **HuggingFace Token**: If `HF_TOKEN` is needed for gated models (Llama Guard requires agreement), it must be stored securely and excluded from git.

2. **Model Registry Checksums**: The proposed `registry/models.json` should NOT contain tokens but should verify model integrity via checksums.

### Recommendation

Add to Task 1 (Storage Layout):
- Ensure `$SEREN_LLM_ROOT/registry/` is excluded from git if it contains any tokens
- Use environment variables for any authentication tokens

---

## E) Gap List with Severity

| ID | Severity | Category | Gap | Remediation |
|----|----------|----------|-----|-------------|
| GAP-NOTION-1 | **CRITICAL** | Notion | Project and tasks not synced to Notion | Run pending writes sync processor |
| GAP-NOTION-2 | **MEDIUM** | Notion | Owner "Cursor GPT-5.2 Agent" not in schema | Add option or use existing agent name |
| GAP-TECH-1 | **CRITICAL** | Technical | Vision model requires llama.cpp fork | Document fork requirement; add to Task 5 |
| GAP-TECH-2 | **HIGH** | Technical | No pinned model IDs/checksums | Create model manifest with exact specs |
| GAP-TECH-3 | **HIGH** | Technical | No explicit unload strategy | Add memory management details to Tasks 10/12 |
| GAP-TECH-4 | **MEDIUM** | Technical | License restrictions not documented | Add license compliance notes to project description |
| GAP-FS-1 | **LOW** | File System | No backup/versioning strategy | Add to Task 1 or Task 12 |
| GAP-FS-2 | **LOW** | File System | Naming inconsistency (seren vs SerenLocalLLM) | Standardize naming |
| GAP-SEC-1 | **LOW** | Security | HF_TOKEN handling not specified | Add to Task 1 env vars section |

---

## F) Concrete Remediation Actions

### Immediate Actions (Before Proceeding)

1. **Sync Notion writes** — The pending writes processor must run to create the Notion pages.

2. **Create missing Agent-Tasks** for identified gaps:

#### New Task: Model Manifest and Checksum Registry
```json
{
  "Task Name": "[TASK 13] Model Manifest — Pinned Model IDs, Checksums, and Licenses",
  "Description": "Create authoritative model manifest with:\n- Exact HuggingFace repo IDs\n- Specific file names and quantization levels\n- SHA256 checksums for verification\n- License type and attribution requirements\n- Download URLs\n\nStore under $SEREN_LLM_ROOT/registry/models.json",
  "Status": "Not Started",
  "Priority": "High",
  "Category": "Documentation"
}
```

#### New Task: Memory Management Implementation
```json
{
  "Task Name": "[TASK 14] Memory Management — Explicit Unload Strategy for 16GB",
  "Description": "Implement and document:\n- Model unload API endpoint in gateway\n- Memory pressure detection (using psutil or similar)\n- Automatic unload on memory threshold\n- Cooldown/warmup timing between swaps\n- Graceful degradation on OOM\n\nIntegrate with Task 10 gateway service.",
  "Status": "Not Started",
  "Priority": "High",
  "Category": "Code Implementation"
}
```

### Task Updates Required

**Task 5 Update**: Add note about llama.cpp multimodal fork requirement:
> "CRITICAL: Qwen2.5-VL 7B requires llama.cpp built with multimodal/vision support. Standard releases do NOT work. See https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md. Must download both model GGUF and mmproj vision projection file."

**Task 8 Update**: Add Llama license note:
> "Llama Guard 3 1B uses Meta's Llama 3.1 Community License. Commercial use is permitted but subject to Meta's Acceptable Use Policy. Ensure compliance before production deployment."

---

## G) Go/No-Go Summary

| Criterion | Status | Blocker? |
|-----------|--------|----------|
| Hardware verified | **PASS** | No |
| Models available | **PASS with caveats** | Vision model needs fork |
| Memory budget feasible | **PASS** | No (if sequential) |
| Storage plan sound | **PASS** | No |
| Licenses commercial-OK | **PASS** | No (review Gemma/Llama terms) |
| Notion sync complete | **FAIL** | Yes — must sync before tracking |
| Technical plan complete | **PARTIAL** | Yes — add model manifest, memory mgmt |

### Final Verdict

**CONDITIONAL GO**

The technical plan is fundamentally sound and executable on 16GB Mac mini M2 Pro. However:

1. **Must sync Notion writes** before proceeding
2. **Must add model manifest task** with pinned IDs and checksums
3. **Must document llama.cpp fork requirement** for vision models
4. **Should add memory management task** for robustness

Once these gaps are addressed, the project can proceed to Task 1 (Storage Layout).

---

## Appendix: Model Download Sources

| Model | Recommended Source | Quantization |
|-------|-------------------|--------------|
| Phi-4-mini-instruct | `bartowski/microsoft_Phi-4-mini-instruct-GGUF` | Q4_K_M |
| Gemma 2 9B | `bartowski/gemma-2-9b-it-GGUF` | Q4_K_M |
| Qwen2.5-VL 7B | `bartowski/Qwen_Qwen2.5-VL-7B-Instruct-GGUF` | Q4_K_L |
| Florence-2 | `microsoft/Florence-2-large` | fp16 (Transformers) |
| Whisper medium | `ggml-org/whisper.cpp` models | Q5_0 (ggml format) |
| BGE-M3 | `BAAI/bge-m3` | fp16 (Transformers) |
| bge-reranker-v2-m3 | `BAAI/bge-reranker-v2-m3` | fp16 (Transformers) |
| Llama Guard 3 1B | `QuantFactory/Llama-Guard-3-1B-GGUF` | Q4_K_M |
| CLAP | `laion/larger_clap_general` | fp16 (Transformers) |

---

*Report generated by Claude Code Agent (Opus 4.5) — 2026-01-18*
