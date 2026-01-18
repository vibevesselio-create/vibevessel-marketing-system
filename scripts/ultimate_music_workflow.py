#!/usr/bin/env python3
"""
Ultimate Music Workflow Orchestrator (production-ready wrapper).

Routes to playlist sync, single track sync, or download-only modes.
Designed to replace archived orchestrator stubs with a minimal, reliable entrypoint.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from unified_config import load_unified_env, setup_unified_logging
    load_unified_env()
    logger = setup_unified_logging(session_id="ultimate_music_workflow")
except Exception as exc:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger("ultimate_music_workflow")
    logger.warning("Unified config unavailable (%s); using basic logging.", exc)


def run_playlist(args: argparse.Namespace) -> int:
    import sync_soundcloud_playlist as playlist_sync

    results_path = Path(args.results_file) if args.results_file else None
    stats = playlist_sync.sync_and_download_playlist(
        playlist_url=args.playlist_url,
        playlist_name=args.playlist_name,
        max_tracks=args.max_tracks,
        dry_run=args.dry_run,
        auto_download=not args.no_download,
        checkpoint_path=Path(args.checkpoint_file) if args.checkpoint_file else None,
        resume=args.resume,
        use_checkpoint=not args.no_checkpoint,
        results_path=results_path,
    )
    return 0 if stats.get("success") else 1


def run_track(args: argparse.Namespace) -> int:
    import sync_soundcloud_track as track_sync

    stats = track_sync.sync_and_download_track(
        track_url=args.track_url,
        dry_run=args.dry_run,
        auto_download=not args.no_download,
    )
    if args.results_file:
        try:
            results_path = Path(args.results_file)
            results_path.parent.mkdir(parents=True, exist_ok=True)
            import json
            with results_path.open("w", encoding="utf-8") as handle:
                json.dump(stats, handle, indent=2, ensure_ascii=True)
        except Exception as exc:
            logger.warning("Failed to write results file %s: %s", args.results_file, exc)
    return 0 if stats.get("success") else 1


def run_download_mode(args: argparse.Namespace) -> int:
    script_path = PROJECT_ROOT / "monolithic-scripts" / "soundcloud_download_prod_merge-2.py"
    if not script_path.exists():
        logger.error("Download workflow not found: %s", script_path)
        return 1

    cmd = ["python3", str(script_path), "--mode", args.mode]
    if args.limit:
        cmd.extend(["--limit", str(args.limit)])
    if args.debug:
        cmd.append("--debug")

    logger.info("Running download workflow: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)
    return result.returncode


def build_volume_index(args: argparse.Namespace) -> int:
    script_path = SCRIPT_DIR / "build_music_volume_index.py"
    if not script_path.exists():
        logger.error("Volume index script not found: %s", script_path)
        return 1

    cmd = ["python3", str(script_path)]
    if args.with_hash:
        cmd.append("--with-hash")
    if args.fast_hash:
        cmd.append("--fast-hash")
    if args.validate_integrity:
        cmd.append("--validate-integrity")
    if args.output:
        cmd.extend(["--output", args.output])

    logger.info("Building volume index: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Ultimate music workflow orchestrator")
    parser.add_argument("--mode", choices=["playlist", "track", "batch", "single"], help="Workflow mode")
    parser.add_argument("--playlist-url", help="SoundCloud playlist URL")
    parser.add_argument("--track-url", help="SoundCloud track URL")
    parser.add_argument("--playlist-name", help="Optional playlist name override")
    parser.add_argument("--max-tracks", type=int, help="Max tracks for playlist sync")
    parser.add_argument("--limit", type=int, help="Max tracks for download batch mode")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run (playlist/track only)")
    parser.add_argument("--no-download", action="store_true", help="Do not trigger download workflow")
    parser.add_argument("--resume", action="store_true", help="Resume playlist sync from checkpoint")
    parser.add_argument("--checkpoint-file", help="Checkpoint file path for playlist sync")
    parser.add_argument("--no-checkpoint", action="store_true", help="Disable playlist checkpointing")
    parser.add_argument("--results-file", help="Write JSON results to this path")
    parser.add_argument("--debug", action="store_true", help="Enable debug output in download workflow")

    parser.add_argument("--build-volume-index", action="store_true", help="Build volume index and exit")
    parser.add_argument("--with-hash", action="store_true", help="Include file hashes in volume index")
    parser.add_argument("--fast-hash", action="store_true", help="Use fast hash mode for volume index")
    parser.add_argument("--validate-integrity", action="store_true", help="Validate audio integrity for volume index")
    parser.add_argument("--output", help="Output path for volume index")

    args = parser.parse_args()

    if args.build_volume_index:
        return build_volume_index(args)

    mode = args.mode
    if not mode:
        if args.playlist_url:
            mode = "playlist"
        elif args.track_url:
            mode = "track"
        else:
            parser.error("Provide --mode or a --playlist-url/--track-url")

    if mode == "playlist":
        if not args.playlist_url:
            parser.error("--playlist-url is required for playlist mode")
        return run_playlist(args)
    if mode == "track":
        if not args.track_url:
            parser.error("--track-url is required for track mode")
        return run_track(args)
    if mode in {"batch", "single"}:
        return run_download_mode(args)

    parser.error(f"Unsupported mode: {mode}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
