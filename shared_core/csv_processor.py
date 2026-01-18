"""
CSV Processor (Shared Core)
==========================

Shared CSV utilities used across multi-node webhook systems.

Design goals (aligned with DriveSheetsSync patterns):
- Durable append-only writes
- Optional "type row" support (DriveSheetsSync style: row 2 contains column types)
- Minimal dependencies (standard library only)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


class CsvProcessorError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvWriteOptions:
    include_header: bool = True
    include_type_row: bool = False
    type_row: Optional[Sequence[str]] = None


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(
    path: Path,
    *,
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    options: Optional[CsvWriteOptions] = None,
) -> None:
    opts = options or CsvWriteOptions()
    _ensure_parent_dir(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if opts.include_header:
            w.writerow(list(headers))
        if opts.include_type_row:
            if not opts.type_row:
                raise CsvProcessorError("include_type_row=True requires type_row")
            w.writerow(list(opts.type_row))
        for r in rows:
            w.writerow(list(r))


def append_csv_rows(
    path: Path,
    *,
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> None:
    """
    Append rows to a CSV file, writing the header if the file doesn't exist yet.
    """
    _ensure_parent_dir(path)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(list(headers))
        for r in rows:
            w.writerow(list(r))


def read_csv_as_dicts(path: Path, *, expect_type_row: bool = False) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return []
    headers = rows[0]
    start_idx = 2 if expect_type_row else 1
    out: List[Dict[str, str]] = []
    for row in rows[start_idx:]:
        if not row:
            continue
        d: Dict[str, str] = {}
        for i, h in enumerate(headers):
            d[h] = row[i] if i < len(row) else ""
        out.append(d)
    return out

