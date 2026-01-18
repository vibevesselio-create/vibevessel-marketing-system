#!/usr/bin/env python3
"""
Music Files Migration Script
============================

Migrates existing music files from the old 4-file output structure to the new 3-file structure.

OLD Structure (4 files):
1. AIFF -> OUT_DIR/{playlist}/{filename}.aiff (Eagle Auto-Import)
2. M4A -> OUT_DIR/{playlist}/{filename}.m4a (Eagle Auto-Import)
3. M4A Backup -> BACKUP_DIR/{filename}.m4a (Djay-Pro-Auto-Import)
4. WAV -> WAV_BACKUP_DIR/{filename}.wav (Apple-Music-Auto-Add)

NEW Structure (3 files):
1. WAV -> Eagle Library (organized in Playlists/{playlist}/ folder)
2. AIFF -> Eagle Library (organized in Playlists/{playlist}/ folder)
3. WAV copy -> /Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks/{playlist}/{filename}.wav

Migration Actions:
- Move WAV files to playlist subdirectories in PLAYLIST_TRACKS_DIR
- Import WAV and AIFF files to Eagle organized by playlist folder
- Delete M4A files (no longer needed)
- Update Notion database with new file paths

Usage:
    python migrate_music_files_to_new_structure.py --dry-run    # Preview changes
    python migrate_music_files_to_new_structure.py --execute    # Perform migration

Version: 2026-01-16
"""

import os
import sys
import json
import shutil
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from shared_core.logging import setup_logging
    logger = setup_logging(session_id="migrate_music_files", log_level="INFO")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger = logging.getLogger(__name__)

# Configuration
OLD_OUT_DIR = Path("/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2")
OLD_BACKUP_DIR = Path("/Volumes/VIBES/Djay-Pro-Auto-Import")
OLD_WAV_BACKUP_DIR = Path("/Volumes/VIBES/Apple-Music-Auto-Add")
NEW_PLAYLIST_TRACKS_DIR = Path("/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks")

EAGLE_API_BASE = "http://localhost:41595"


class EagleAPI:
    """Simple Eagle API client for migration."""

    def __init__(self, base_url: str = EAGLE_API_BASE):
        self.base_url = base_url

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make a request to the Eagle API."""
        # Ensure endpoint has /api prefix
        if not endpoint.startswith("/api"):
            endpoint = f"/api{endpoint}"
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "POST" and data:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(data).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            else:
                req = urllib.request.Request(url, method=method.upper())

            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            logger.error(f"Eagle API error: {e}")
            return {"status": "error", "message": str(e)}

    def is_available(self) -> bool:
        """Check if Eagle is running."""
        try:
            result = self._request("GET", "/application/info")
            return result.get("status") == "success"
        except Exception:
            return False

    def get_folders(self) -> List[Dict]:
        """Get all folders."""
        result = self._request("GET", "/folder/list")
        return result.get("data", [])

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Create a folder and return its ID."""
        data = {"folderName": name}
        if parent_id:
            data["parent"] = parent_id
        result = self._request("POST", "/folder/create", data)
        if result.get("status") == "success":
            folder_data = result.get("data", {})
            return folder_data.get("id") if isinstance(folder_data, dict) else folder_data
        return ""

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Get or create a folder by name."""
        folders = self.get_folders()

        def find_recursive(folder_list, target_name, target_parent=None):
            for f in folder_list:
                if f.get("name") == target_name:
                    if target_parent is None or f.get("parent") == target_parent:
                        return f["id"]
                children = f.get("children", [])
                if children:
                    result = find_recursive(children, target_name, target_parent)
                    if result:
                        return result
            return None

        folder_id = find_recursive(folders, name, parent_id)
        if folder_id:
            return folder_id

        return self.create_folder(name, parent_id)

    def get_playlist_folder(self, playlist_name: str) -> str:
        """Get or create a playlist folder under 'Playlists' parent."""
        playlists_folder_id = self.get_or_create_folder("Playlists")
        return self.get_or_create_folder(playlist_name, playlists_folder_id)

    def import_file(self, file_path: str, name: str, tags: List[str], folder_id: Optional[str] = None) -> Optional[str]:
        """Import a file to Eagle."""
        data = {
            "path": str(Path(file_path).resolve()),
            "name": name,
            "tags": tags,
        }
        if folder_id:
            data["folderId"] = folder_id

        result = self._request("POST", "/item/addFromPath", data)
        if result.get("status") == "success":
            item_data = result.get("data", {})
            return item_data.get("id") if isinstance(item_data, dict) else item_data
        return None


def discover_existing_files() -> Dict[str, Dict]:
    """Discover existing music files and their playlist associations."""
    logger.info("Discovering existing music files...")
    files_by_playlist: Dict[str, Dict] = {}

    # Scan OLD_OUT_DIR for playlist subdirectories
    if OLD_OUT_DIR.exists():
        for item in OLD_OUT_DIR.iterdir():
            if item.is_dir():
                playlist_name = item.name
                files_by_playlist[playlist_name] = {
                    "aiff": [],
                    "m4a": [],
                    "wav": [],
                }

                for f in item.iterdir():
                    if f.is_file():
                        ext = f.suffix.lower()
                        if ext == ".aiff":
                            files_by_playlist[playlist_name]["aiff"].append(f)
                        elif ext == ".m4a":
                            files_by_playlist[playlist_name]["m4a"].append(f)
                        elif ext == ".wav":
                            files_by_playlist[playlist_name]["wav"].append(f)

    # Also check OLD_WAV_BACKUP_DIR for WAV files
    if OLD_WAV_BACKUP_DIR.exists():
        for f in OLD_WAV_BACKUP_DIR.iterdir():
            if f.is_file() and f.suffix.lower() == ".wav":
                # Try to match to a playlist based on filename
                matched = False
                for playlist_name, files in files_by_playlist.items():
                    # Check if there's a matching AIFF or M4A
                    for aiff_file in files["aiff"]:
                        if aiff_file.stem == f.stem:
                            files["wav"].append(f)
                            matched = True
                            break
                    if matched:
                        break

                if not matched:
                    # Add to "Uncategorized" playlist
                    if "Uncategorized" not in files_by_playlist:
                        files_by_playlist["Uncategorized"] = {"aiff": [], "m4a": [], "wav": []}
                    files_by_playlist["Uncategorized"]["wav"].append(f)

    return files_by_playlist


def generate_migration_plan(files_by_playlist: Dict[str, Dict]) -> List[Dict]:
    """Generate a migration plan based on discovered files."""
    migration_actions = []

    for playlist_name, files in files_by_playlist.items():
        playlist_wav_dir = NEW_PLAYLIST_TRACKS_DIR / playlist_name

        # For each AIFF file, create migration actions
        for aiff_file in files["aiff"]:
            base_name = aiff_file.stem

            # Find matching WAV file
            wav_file = None
            for w in files["wav"]:
                if w.stem == base_name:
                    wav_file = w
                    break

            # Find matching M4A file
            m4a_file = None
            for m in files["m4a"]:
                if m.stem == base_name:
                    m4a_file = m
                    break

            action = {
                "track_name": base_name,
                "playlist": playlist_name,
                "aiff_source": aiff_file,
                "wav_source": wav_file,
                "m4a_source": m4a_file,
                "wav_destination": playlist_wav_dir / f"{base_name}.wav",
                "actions": [],
            }

            # Plan actions
            if wav_file and wav_file.exists():
                action["actions"].append(f"COPY WAV: {wav_file} -> {action['wav_destination']}")
            elif aiff_file.exists():
                # Convert AIFF to WAV if no WAV exists
                action["actions"].append(f"CONVERT AIFF->WAV: {aiff_file} -> {action['wav_destination']}")

            # Import to Eagle
            if aiff_file.exists():
                action["actions"].append(f"EAGLE IMPORT AIFF: {aiff_file} -> Playlists/{playlist_name}/")
            if wav_file and wav_file.exists():
                action["actions"].append(f"EAGLE IMPORT WAV: {wav_file} -> Playlists/{playlist_name}/")

            # Delete M4A files
            if m4a_file and m4a_file.exists():
                action["actions"].append(f"DELETE M4A: {m4a_file}")

            migration_actions.append(action)

    return migration_actions


def execute_migration(migration_actions: List[Dict], dry_run: bool = True) -> Dict:
    """Execute the migration plan."""
    stats = {
        "wav_copied": 0,
        "aiff_converted": 0,
        "eagle_imports": 0,
        "m4a_deleted": 0,
        "errors": [],
    }

    eagle = EagleAPI()
    eagle_available = eagle.is_available()

    if not eagle_available:
        logger.warning("Eagle is not running. Eagle imports will be skipped.")

    for action in migration_actions:
        logger.info(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {action['track_name']}")
        logger.info(f"  Playlist: {action['playlist']}")

        # Create destination directory
        dest_dir = action["wav_destination"].parent
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy or convert WAV
        wav_source = action.get("wav_source")
        aiff_source = action.get("aiff_source")
        wav_dest = action["wav_destination"]

        if wav_source and wav_source.exists():
            logger.info(f"  Copying WAV: {wav_source.name} -> {wav_dest}")
            if not dry_run:
                try:
                    shutil.copy2(wav_source, wav_dest)
                    stats["wav_copied"] += 1
                except Exception as e:
                    logger.error(f"  ERROR copying WAV: {e}")
                    stats["errors"].append(f"Copy WAV {wav_source}: {e}")
        elif aiff_source and aiff_source.exists():
            logger.info(f"  Converting AIFF to WAV: {aiff_source.name} -> {wav_dest}")
            if not dry_run:
                try:
                    import subprocess
                    subprocess.run([
                        "ffmpeg", "-loglevel", "error", "-y",
                        "-i", str(aiff_source),
                        "-c:a", "pcm_s24le", "-ar", "48000",
                        str(wav_dest)
                    ], check=True)
                    stats["aiff_converted"] += 1
                except Exception as e:
                    logger.error(f"  ERROR converting AIFF: {e}")
                    stats["errors"].append(f"Convert AIFF {aiff_source}: {e}")

        # Import to Eagle
        if eagle_available:
            playlist_folder_id = None
            if not dry_run:
                try:
                    playlist_folder_id = eagle.get_playlist_folder(action["playlist"])
                except Exception as e:
                    logger.error(f"  ERROR getting Eagle folder: {e}")

            # Import AIFF
            if aiff_source and aiff_source.exists():
                logger.info(f"  Importing AIFF to Eagle: Playlists/{action['playlist']}/")
                if not dry_run and playlist_folder_id:
                    try:
                        eagle_id = eagle.import_file(
                            str(aiff_source),
                            f"{action['track_name']} (AIFF)",
                            ["audio", "aiff", f"playlist:{action['playlist']}"],
                            playlist_folder_id
                        )
                        if eagle_id:
                            stats["eagle_imports"] += 1
                    except Exception as e:
                        logger.error(f"  ERROR importing AIFF to Eagle: {e}")
                        stats["errors"].append(f"Eagle AIFF {aiff_source}: {e}")

            # Import WAV (from destination after copy/convert)
            if wav_dest.exists() or dry_run:
                logger.info(f"  Importing WAV to Eagle: Playlists/{action['playlist']}/")
                if not dry_run and playlist_folder_id and wav_dest.exists():
                    try:
                        eagle_id = eagle.import_file(
                            str(wav_dest),
                            action['track_name'],
                            ["audio", "wav", f"playlist:{action['playlist']}"],
                            playlist_folder_id
                        )
                        if eagle_id:
                            stats["eagle_imports"] += 1
                    except Exception as e:
                        logger.error(f"  ERROR importing WAV to Eagle: {e}")
                        stats["errors"].append(f"Eagle WAV {wav_dest}: {e}")

        # Delete M4A
        m4a_source = action.get("m4a_source")
        if m4a_source and m4a_source.exists():
            logger.info(f"  Deleting M4A: {m4a_source}")
            if not dry_run:
                try:
                    m4a_source.unlink()
                    stats["m4a_deleted"] += 1
                except Exception as e:
                    logger.error(f"  ERROR deleting M4A: {e}")
                    stats["errors"].append(f"Delete M4A {m4a_source}: {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate music files to new 3-file structure")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute the migration")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        print("\nUsage:")
        print("  python migrate_music_files_to_new_structure.py --dry-run    # Preview changes")
        print("  python migrate_music_files_to_new_structure.py --execute    # Perform migration")
        sys.exit(1)

    dry_run = args.dry_run

    logger.info("=" * 80)
    logger.info("MUSIC FILES MIGRATION SCRIPT")
    logger.info(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (making changes)'}")
    logger.info("=" * 80)

    # Verify directories
    logger.info("\nChecking directories...")
    logger.info(f"  OLD_OUT_DIR: {OLD_OUT_DIR} {'(exists)' if OLD_OUT_DIR.exists() else '(NOT FOUND)'}")
    logger.info(f"  OLD_WAV_BACKUP_DIR: {OLD_WAV_BACKUP_DIR} {'(exists)' if OLD_WAV_BACKUP_DIR.exists() else '(NOT FOUND)'}")
    logger.info(f"  NEW_PLAYLIST_TRACKS_DIR: {NEW_PLAYLIST_TRACKS_DIR}")

    if not OLD_OUT_DIR.exists():
        logger.error("Source directory not found. Nothing to migrate.")
        sys.exit(1)

    # Discover files
    files_by_playlist = discover_existing_files()

    total_aiff = sum(len(f["aiff"]) for f in files_by_playlist.values())
    total_m4a = sum(len(f["m4a"]) for f in files_by_playlist.values())
    total_wav = sum(len(f["wav"]) for f in files_by_playlist.values())

    logger.info(f"\nDiscovered {len(files_by_playlist)} playlists:")
    logger.info(f"  Total AIFF files: {total_aiff}")
    logger.info(f"  Total M4A files: {total_m4a}")
    logger.info(f"  Total WAV files: {total_wav}")

    for playlist_name, files in files_by_playlist.items():
        logger.info(f"  - {playlist_name}: {len(files['aiff'])} AIFF, {len(files['m4a'])} M4A, {len(files['wav'])} WAV")

    # Generate migration plan
    migration_actions = generate_migration_plan(files_by_playlist)
    logger.info(f"\nGenerated {len(migration_actions)} migration actions")

    # Execute migration
    stats = execute_migration(migration_actions, dry_run=dry_run)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"WAV files copied: {stats['wav_copied']}")
    logger.info(f"AIFF files converted to WAV: {stats['aiff_converted']}")
    logger.info(f"Eagle imports: {stats['eagle_imports']}")
    logger.info(f"M4A files deleted: {stats['m4a_deleted']}")

    if stats["errors"]:
        logger.warning(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"]:
            logger.warning(f"  - {err}")

    if dry_run:
        logger.info("\nThis was a DRY RUN. No changes were made.")
        logger.info("Run with --execute to perform the migration.")


if __name__ == "__main__":
    main()
