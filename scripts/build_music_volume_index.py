#!/usr/bin/env python3
"""
Build a volume-wide index of music files for download dedupe.

Outputs a JSON file used by soundcloud_download_prod_merge-2.py when enabled.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("build_music_volume_index")

try:
    from unified_config import load_unified_env, get_unified_config
except (OSError, ModuleNotFoundError, TimeoutError):
    def load_unified_env() -> None:
        return None

    def get_unified_config() -> Dict[str, Any]:
        return {}

try:
    from shared_core.notion.token_manager import get_notion_client
except (ImportError, ModuleNotFoundError):
    get_notion_client = None

from music_library_remediation import load_music_directories, scan_directories


def build_index_records(records: list[Any]) -> list[dict]:
    output = []
    for record in records:
        output.append(
            {
                "path": record.path,
                "extension": record.extension,
                "size": record.size,
                "mtime": record.mtime,
                "title_cleaned": record.title_cleaned,
                "artist_cleaned": record.artist_cleaned,
                "file_hash": record.file_hash,
                "is_valid": record.is_valid,
            }
        )
    return output


def default_output_path() -> Path:
    out_dir = PROJECT_ROOT / "var"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "music_volume_index.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build music volume index JSON")
    parser.add_argument("--with-hash", action="store_true", help="Compute file hash for each file")
    parser.add_argument("--fast-hash", action="store_true", help="Use fast hash mode (sampled)")
    parser.add_argument("--validate-integrity", action="store_true", help="Validate audio file integrity")
    parser.add_argument("--output", help="Output JSON path (default: var/music_volume_index.json)")
    args = parser.parse_args()

    load_unified_env()
    config = get_unified_config()
    directories_db_id = (config.get("music_directories_db_id") or os.getenv("MUSIC_DIRECTORIES_DB_ID") or "").strip()

    notion_client = None
    if get_notion_client:
        try:
            notion_client = get_notion_client()
        except Exception as exc:
            logger.warning("Failed to initialize Notion client: %s", exc)

    scan_paths = load_music_directories(notion_client, directories_db_id)
    logger.info("Scanning %d directories", len(scan_paths))

    records, missing_paths = scan_directories(
        scan_paths,
        with_hash=args.with_hash,
        fast_hash=args.fast_hash,
        validate_integrity=args.validate_integrity,
    )

    output_path = Path(args.output) if args.output else default_output_path()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scan_paths": scan_paths,
        "missing_paths": missing_paths,
        "with_hash": bool(args.with_hash),
        "fast_hash": bool(args.fast_hash),
        "validate_integrity": bool(args.validate_integrity),
        "records": build_index_records(records),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)

    logger.info("Wrote %d records to %s", len(payload["records"]), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
