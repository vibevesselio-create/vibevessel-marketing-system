# HANDOFF: Audit + Gap Analysis — Local LLM Stack (M2 Pro 16GB) Marketing Automation

**Trigger Type**: Comprehensive Audit + Gap Analysis  
**Priority**: High  
**Created By**: Cursor GPT-5.2 Agent  
**Created Date**: 2026-01-18  

---

## Preconditions (MUST be true before auditing)

This audit should only begin **after Notion updates are complete** (Agent-Project + Agent-Tasks created and linked).

### Verify these repo artifacts exist (source-of-truth)

- Agent-Project JSON:
  - `var/pending_notion_writes/agent_projects/20260118T173743Z__local_llm_stack_m2pro16_marketing_automation.json`
- Agent-Tasks JSONs (12):
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task1_storage_layout_and_env_vars.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task2_install_llama_cpp_runtime.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task3_install_whisper_cpp_runtime.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task4_download_text_models_phi_and_gemma.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task5_download_vision_and_ocr_models_qwen_vl_and_florence2.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task6_download_whisper_models_and_transcription_pipeline.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task7_download_rag_models_bge_m3_and_reranker.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task8_download_safety_model_llama_guard.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task9_optional_audio_embedding_clap.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task10_local_llm_gateway_service.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task11_marketing_automation_workflow_adapters.json`
  - `var/pending_notion_writes/agent_tasks/20260118T173743Z__task12_performance_guardrails_and_runbook.json`

### Verify the Notion objects exist and are linked

In Notion:
- Confirm the Agent-Project exists with **Project ID**: `local-llm-stack-m2pro16-v1`
- Confirm the 12 Agent-Tasks exist, are linked to the project, and have correct statuses/priorities.
- If these Notion objects do NOT exist yet, stop the audit and produce a short note indicating Notion sync is incomplete.

---

## Context (what was proposed)

Target machine:
- Mac mini, Apple M2 Pro
- 10 CPU cores (6P+4E), 16 GPU cores, Metal 4
- 16GB unified memory

Proposed local model set (16GB-optimized, sequential “one-heavy-model-at-a-time”):
- Text controller/router: Phi-4-mini-instruct
- Copy/rewrite model: Gemma 2 9B
- Vision: Qwen2.5-VL 7B Instruct
- OCR/doc-vision: Florence-2
- Transcription: Whisper medium (whisper.cpp)
- RAG embeddings: BGE-M3
- RAG reranker: bge-reranker-v2-m3
- Safety gate: Llama Guard 3 1B
- Optional audio embeddings: CLAP

Proposed storage (performance-first):
- Hot: `/Users/brianhellemn/Library/Application Support/SerenLocalLLM/models` (internal SSD / Apple Fabric)
- Cold/archive: `/Volumes/SYSTEM_SSD/SerenLocalLLM/models-archive` (external Samsung T7 USB SSD)

Proposed repo integration points:
- `services/local_llm/` (gateway service)
- `shared_core/local_llm/` (client + templates + schemas)

---

## Audit Objectives

### A) Notion compliance audit
- Validate required properties exist and are populated correctly for the Agent-Project and all Agent-Tasks.
- Validate all tasks are linked to the project and have correct “Category/Tags/Status” semantics.
- Identify any schema gaps (missing relations, wrong database IDs, missing required properties).

### B) Technical plan audit (gap analysis)
Assess whether the plan is complete and executable on a **16GB unified memory** Mac:
- Are model choices realistic (memory + context constraints + format availability)?
- Are the runtime choices coherent (llama.cpp vs MLX vs Ollama) and do they integrate cleanly?
- Are download/installation steps explicit enough (exact model IDs, formats, checksums, licensing)?
- Are performance guardrails sufficient (single heavy model, context caps, unload strategy)?
- Are failure modes addressed (memory pressure, model load failures, timeouts)?

### C) File system placement audit
Confirm the proposed model storage location is technically optimal and safe:
- Internal SSD is fastest → hot models there is correct.
- External SSD is USB → archive only; do not default to archive for runtime hot path.
- Confirm ownership/perms implications (Application Support path) and backup strategy.

### D) Security audit (local secrets and supply chain)
- Confirm that no tokens/secrets are checked into git (watch for `.cache`/token artifacts, .env files, etc.).
- Confirm model downloads are pinned/verified (checksums recorded, license recorded, source URL recorded).

---

## Required Deliverables

1. **Audit report (Markdown)** saved to:
   - `reports/LOCAL_LLM_STACK_AUDIT_20260118.md`
2. **Gap list** with severity and remediation plan:
   - Missing tasks (create new Agent-Tasks)
   - Wrong assumptions (update project/task descriptions)
   - Implementation blockers (format availability, licensing constraints, memory limits)
3. **Concrete remediation actions**
   - Create any missing Agent-Tasks in Notion (and/or via repo JSON queue) for gaps you find.
   - Update task statuses if tasks are malformed or incomplete.

---

## Suggested Audit Checklist (high-signal)

- **Model format availability**:
  - Are GGUF variants available for each “llama.cpp-targeted” model?
  - For Florence-2 / BGE / reranker / CLAP: are Transformers-based installs acceptable on this host?
- **Exact model selection**:
  - Pin to specific model IDs and quantization levels suitable for 16GB.
  - Decide “default contexts” per workflow (e.g., 4K/8K) and document.
- **Gateway feasibility**:
  - Verify the proposed `/services/local_llm/` gateway approach matches existing repo conventions.
  - Verify logging + artifact storage patterns (e.g., `var/` usage) match system conventions.
- **Operational workflow**:
  - Confirm sequential pipeline (transcribe → summarize; OCR → vision QA; retrieve → rerank → generate).
  - Confirm “one heavy model at a time” is enforced.
- **Licensing**:
  - Verify each model’s license supports your use (commercial marketing automation).
  - Verify attribution obligations (e.g., Llama license requirements).

---

## Completion Criteria

- Audit report produced and saved to the repo.
- All gaps converted into concrete tasks (Notion tasks and/or queued JSON tasks).
- Clear “go/no-go” summary for deploying this stack on the 16GB Mac.

