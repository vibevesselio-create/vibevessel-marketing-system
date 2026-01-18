from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared_core.notion.token_manager import get_notion_client


def _safe_get(page: Dict[str, Any], prop_name: str) -> Optional[Dict[str, Any]]:
    props = page.get("properties") or {}
    prop = props.get(prop_name)
    return prop if isinstance(prop, dict) else None


def _get_select_name(prop: Optional[Dict[str, Any]]) -> Optional[str]:
    if not prop:
        return None
    t = prop.get("type")
    if t == "select":
        sel = prop.get("select") or {}
        return sel.get("name")
    if t == "status":
        sel = prop.get("status") or {}
        return sel.get("name")
    return None


def _get_date_start(prop: Optional[Dict[str, Any]]) -> Optional[str]:
    if not prop:
        return None
    if prop.get("type") != "date":
        return None
    date_obj = prop.get("date") or {}
    return date_obj.get("start")


@dataclass(frozen=True)
class PublishJobsSchema:
    execution_layer: str = os.getenv(
        "NOTION_MARKETING_PUBLISH_JOBS_PROP_EXECUTION_LAYER", "Execution Layer"
    )
    execution_status: str = os.getenv(
        "NOTION_MARKETING_PUBLISH_JOBS_PROP_EXECUTION_STATUS", "Execution Status"
    )
    scheduled_time_utc: str = os.getenv(
        "NOTION_MARKETING_PUBLISH_JOBS_PROP_SCHEDULED_TIME", "Scheduled Time (UTC)"
    )
    last_run_ts: str = os.getenv(
        "NOTION_MARKETING_PUBLISH_JOBS_PROP_LAST_RUN_TS", "Last Run Timestamp"
    )
    last_run_log: str = os.getenv(
        "NOTION_MARKETING_PUBLISH_JOBS_PROP_LAST_RUN_LOG", "Last Run Log"
    )
    log_page: str = os.getenv("NOTION_MARKETING_PUBLISH_JOBS_PROP_LOG_PAGE", "Log Page")


class NotionPublishJobsClient:
    def __init__(self, publish_jobs_db_id: str, schema: Optional[PublishJobsSchema] = None):
        self._notion = get_notion_client()
        self._db_id = publish_jobs_db_id
        self._schema = schema or PublishJobsSchema()

    def query_ready_jobs(self, *, now: Optional[datetime] = None, page_size: int = 10) -> List[Dict[str, Any]]:
        now_dt = now or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        # Default schema from the design doc:
        # - Execution Layer = Python
        # - Execution Status in {Not Started, Retry}
        # - Scheduled Time (UTC) <= now
        filter_obj: Dict[str, Any] = {
            "and": [
                {
                    "property": self._schema.execution_layer,
                    "select": {"equals": "Python"},
                },
                {
                    "or": [
                        {
                            "property": self._schema.execution_status,
                            "select": {"equals": "Not Started"},
                        },
                        {
                            "property": self._schema.execution_status,
                            "select": {"equals": "Retry"},
                        },
                    ],
                },
                {
                    "property": self._schema.scheduled_time_utc,
                    "date": {"on_or_before": now_iso},
                },
            ]
        }

        resp = self._notion.databases.query(
            database_id=self._db_id,
            filter=filter_obj,
            page_size=page_size,
        )
        return resp.get("results", []) or []

    def get_job_debug_summary(self, job_page: Dict[str, Any]) -> Dict[str, Any]:
        props = job_page.get("properties") or {}
        return {
            "page_id": job_page.get("id"),
            "execution_layer": _get_select_name(_safe_get(job_page, self._schema.execution_layer)),
            "execution_status": _get_select_name(_safe_get(job_page, self._schema.execution_status)),
            "scheduled_time_utc": _get_date_start(_safe_get(job_page, self._schema.scheduled_time_utc)),
            "properties_present": sorted(list(props.keys())),
        }

    def mark_job_status(
        self,
        *,
        job_page_id: str,
        execution_status: str,
        last_run_timestamp: Optional[datetime] = None,
        last_run_log: Optional[str] = None,
        log_page_id: Optional[str] = None,
    ) -> None:
        properties: Dict[str, Any] = {
            self._schema.execution_status: {"select": {"name": execution_status}},
        }

        if last_run_timestamp is not None:
            properties[self._schema.last_run_ts] = {
                "date": {"start": last_run_timestamp.isoformat()}
            }

        if last_run_log is not None:
            properties[self._schema.last_run_log] = {
                "rich_text": [{"text": {"content": last_run_log[:1999]}}]
            }

        if log_page_id is not None:
            properties[self._schema.log_page] = {"relation": [{"id": log_page_id}]}

        self._notion.pages.update(page_id=job_page_id, properties=properties)

