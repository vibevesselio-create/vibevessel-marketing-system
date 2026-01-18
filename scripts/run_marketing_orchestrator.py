#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    publish_jobs_db_id = os.getenv("NOTION_MARKETING_PUBLISH_JOBS_DB_ID")
    if not publish_jobs_db_id:
        print("ERROR: NOTION_MARKETING_PUBLISH_JOBS_DB_ID is required")
        return 2

    from services.marketing_orchestrator import MarketingOrchestrator, MarketingOrchestratorConfig

    cfg = MarketingOrchestratorConfig(publish_jobs_db_id=publish_jobs_db_id)
    orch = MarketingOrchestrator(cfg)
    result = orch.run_once()

    # Print full result (no truncation; user rule: don't use head)
    print(result)
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())

