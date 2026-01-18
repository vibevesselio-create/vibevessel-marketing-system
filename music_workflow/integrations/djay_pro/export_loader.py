"""Loader utilities for djay Pro export CSV files."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from music_workflow.integrations.djay_pro.models import (
    DjayExport,
    DjayTrack,
    DjayStreamingTrack,
    DjaySession,
    DjaySessionTrack,
    DjayPlaylistEntry,
)


_TIMESTAMP_FORMATS = ("%Y%m%d_%H%M%S", "%Y%m%d%H%M%S")


def _parse_timestamp(path: Path, stem: str) -> Optional[datetime]:
    name = path.stem
    prefix = f"{stem}_"
    if not name.startswith(prefix):
        return None
    suffix = name[len(prefix):]
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(suffix, fmt)
        except ValueError:
            continue
    return None


def find_latest_export_file(export_dir: Path, stem: str) -> Optional[Path]:
    """Find the newest export file for a given stem."""
    export_dir = Path(export_dir)
    candidates = list(export_dir.glob(f"{stem}_*.csv"))
    direct_path = export_dir / f"{stem}.csv"
    if direct_path.exists():
        candidates.append(direct_path)

    if not candidates:
        return None

    def sort_key(path: Path) -> datetime:
        parsed = _parse_timestamp(path, stem)
        if parsed:
            return parsed
        return datetime.fromtimestamp(path.stat().st_mtime)

    return max(candidates, key=sort_key)


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    value = value.strip().lower()
    return value in ("1", "true", "yes", "y")


def _load_tracks(path: Path) -> list[DjayTrack]:
    tracks = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tracks.append(
                DjayTrack(
                    track_id=(row.get("track_id") or "").strip(),
                    title=(row.get("title") or "").strip(),
                    artist=(row.get("artist") or "").strip(),
                    album=(row.get("album") or "").strip(),
                    genre=(row.get("genre") or "").strip(),
                    duration_sec=_parse_float(row.get("duration_sec")),
                    bpm=_parse_float(row.get("bpm")),
                    key=(row.get("key") or "").strip() or None,
                    key_camelot=(row.get("key_camelot") or "").strip() or None,
                    source_type=(row.get("source_type") or "local").strip() or "local",
                    source_id=(row.get("source_id") or "").strip() or None,
                    file_path=(row.get("file_path") or "").strip() or None,
                    added_date=(row.get("added_date") or "").strip() or None,
                    last_played=(row.get("last_played") or "").strip() or None,
                    play_count=_parse_int(row.get("play_count")),
                )
            )
    return tracks


def _load_streaming(path: Path) -> list[DjayStreamingTrack]:
    tracks = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            tracks.append(
                DjayStreamingTrack(
                    track_id=(row.get("track_id") or "").strip(),
                    source_type=(row.get("source_type") or "").strip(),
                    source_track_id=(row.get("source_track_id") or "").strip(),
                    source_url=(row.get("source_url") or "").strip() or None,
                    artist=(row.get("artist") or "").strip(),
                    title=(row.get("title") or "").strip(),
                    duration_sec=_parse_float(row.get("duration_sec")),
                    is_available=_parse_bool(row.get("is_available")),
                )
            )
    return tracks


def _load_sessions(path: Path) -> list[DjaySession]:
    sessions = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sessions.append(
                DjaySession(
                    session_id=(row.get("session_id") or "").strip(),
                    device_name=(row.get("device_name") or "").strip(),
                    device_type=(row.get("device_type") or "").strip(),
                    start_time=(row.get("start_time") or "").strip() or None,
                    end_time=(row.get("end_time") or "").strip() or None,
                    duration_min=_parse_float(row.get("duration_min")),
                    track_count=_parse_int(row.get("track_count")),
                )
            )
    return sessions


def _load_session_tracks(path: Path) -> list[DjaySessionTrack]:
    session_tracks = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            session_tracks.append(
                DjaySessionTrack(
                    play_id=(row.get("play_id") or "").strip(),
                    session_id=(row.get("session_id") or "").strip(),
                    track_id=(row.get("track_id") or "").strip(),
                    deck_number=_parse_int(row.get("deck_number")),
                    play_start=(row.get("play_start") or "").strip() or None,
                    title=(row.get("title") or "").strip(),
                    artist=(row.get("artist") or "").strip(),
                    bpm=_parse_float(row.get("bpm")),
                )
            )
    return session_tracks


def _load_playlists(path: Path) -> list[DjayPlaylistEntry]:
    entries = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            entries.append(
                DjayPlaylistEntry(
                    playlist_id=(row.get("playlist_id") or "").strip(),
                    playlist_name=(row.get("playlist_name") or "").strip(),
                    track_id=(row.get("track_id") or "").strip(),
                    position=_parse_int(row.get("position")),
                    added_date=(row.get("added_date") or "").strip() or None,
                )
            )
    return entries


def load_djay_export(export_dir: Path, require_tracks: bool = True) -> DjayExport:
    """Load the latest djay Pro export from a directory."""
    export_dir = Path(export_dir)

    tracks_path = find_latest_export_file(export_dir, "djay_library_tracks")
    streaming_path = find_latest_export_file(export_dir, "djay_library_streaming")
    sessions_path = find_latest_export_file(export_dir, "djay_session_history")
    session_tracks_path = find_latest_export_file(export_dir, "djay_session_tracks")
    playlists_path = find_latest_export_file(export_dir, "djay_playlists")

    if require_tracks and not tracks_path:
        raise FileNotFoundError(
            f"No djay library tracks export found in {export_dir}"
        )

    export = DjayExport()
    if tracks_path:
        export.tracks = _load_tracks(tracks_path)
    if streaming_path:
        export.streaming_tracks = _load_streaming(streaming_path)
    if sessions_path:
        export.sessions = _load_sessions(sessions_path)
    if session_tracks_path:
        export.session_tracks = _load_session_tracks(session_tracks_path)
    if playlists_path:
        export.playlists = _load_playlists(playlists_path)

    return export
