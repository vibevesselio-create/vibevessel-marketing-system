from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared_core.notion.execution_logs import create_execution_log, update_execution_log

from .notion_publish_jobs import NotionPublishJobsClient


@dataclass(frozen=True)
class MarketingOrchestratorConfig:
    publish_jobs_db_id: str
    dry_run: bool = os.getenv("MARKETING_ORCH_DRY_RUN", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    page_size: int = int(os.getenv("MARKETING_ORCH_PAGE_SIZE", "10"))


class MarketingOrchestrator:
    """
    Phase-1 skeleton orchestrator:
    - polls Notion Publish Jobs
    - updates job status
    - writes Execution-Logs

    External posting providers (Mixpost/Postiz/Late/Ayrshare/CLI/Meta) are intentionally
    out of scope for this first slice.
    """

    def __init__(self, cfg: MarketingOrchestratorConfig):
        self._cfg = cfg
        self._jobs = NotionPublishJobsClient(cfg.publish_jobs_db_id)

    def run_once(self) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        start = datetime.now(timezone.utc)

        exec_log_id = create_execution_log(
            name=f"Marketing Orchestrator Run {run_id}",
            start_time=start,
            status="Running",
            run_id=run_id,
            environment="local",
            plain_english_summary="Poll Notion Publish Jobs and advance runnable jobs (Phase-1 skeleton).",
            metrics={"component": "marketing_orchestrator", "phase": 1},
        )

        jobs = self._jobs.query_ready_jobs(now=start, page_size=self._cfg.page_size)

        processed: List[str] = []
        errors: List[Dict[str, Any]] = []

        for job in jobs:
            job_page_id = job.get("id")
            if not job_page_id:
                continue

            try:
                if not self._cfg.dry_run:
                    self._jobs.mark_job_status(
                        job_page_id=job_page_id,
                        execution_status="In Progress",
                        last_run_timestamp=datetime.now(timezone.utc),
                        last_run_log=f"[{run_id}] Picked up by Marketing Orchestrator (Phase-1 skeleton).",
                        log_page_id=exec_log_id,
                    )

                # Phase-1: no external execution; mark succeeded immediately.
                if not self._cfg.dry_run:
                    self._jobs.mark_job_status(
                        job_page_id=job_page_id,
                        execution_status="Succeeded",
                        last_run_timestamp=datetime.now(timezone.utc),
                        last_run_log=f"[{run_id}] Marked succeeded (Phase-1 skeleton; no provider execution).",
                        log_page_id=exec_log_id,
                    )

                processed.append(job_page_id)
            except Exception as e:
                errors.append(
                    {
                        "job_page_id": job_page_id,
                        "error": str(e),
                        "job_debug": self._jobs.get_job_debug_summary(job),
                    }
                )

        end = datetime.now(timezone.utc)
        duration_s = (end - start).total_seconds()

        status = "Success" if not errors else ("Partial" if processed else "Failed")
        if exec_log_id:
            update_execution_log(
                page_id=exec_log_id,
                status=status,
                end_time=end,
                duration=duration_s,
                error_count=len(errors),
                metrics={
                    "run_id": run_id,
                    "jobs_found": len(jobs),
                    "jobs_processed": len(processed),
                    "errors": errors[:10],
                    "dry_run": self._cfg.dry_run,
                },
            )

        return {
            "run_id": run_id,
            "dry_run": self._cfg.dry_run,
            "jobs_found": len(jobs),
            "jobs_processed": len(processed),
            "errors": errors,
            "execution_log_id": exec_log_id,
        }

