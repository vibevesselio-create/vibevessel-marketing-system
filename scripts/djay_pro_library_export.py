#!/usr/bin/env python3
"""
djay Pro Library Complete Export Script
─────────────────────────────────────────────────────────────────────────────────────
• Extracts ALL data from djay Pro SQLite database (MediaLibrary.db)
• Exports to structured CSV and JSON formats
• Handles YapDatabase key-value structure
• Includes all collections: tracks, playlists, sessions, metadata, etc.
• System-aligned with workspace standards

Aligned with Seren Media Workspace Standards
Version: 2025-01-27
"""

from __future__ import annotations

import os
import sys
import json
import csv
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

# Import unified configuration and logging
try:
    from unified_config import load_unified_env, get_unified_config
except (TimeoutError, OSError, ModuleNotFoundError) as unified_err:
    import importlib
    import sys as _sys
    from pathlib import Path as _Path

    _script_dir = _Path(__file__).resolve().parent
    _fallback_search = [
        _script_dir,
        _script_dir.parent / "scripts",
    ]
    for _candidate in _fallback_search:
        if _candidate.is_dir():
            _candidate_str = str(_candidate)
            if _candidate_str not in _sys.path:
                _sys.path.append(_candidate_str)

    fallback_module = importlib.import_module("unified_config_fallback")
    _sys.modules.setdefault("unified_config", fallback_module)
    load_unified_env = fallback_module.load_unified_env
    get_unified_config = fallback_module.get_unified_config
    print(
        f"[djay_pro_library_export] unified_config unavailable "
        f"({unified_err}); using fallback module.",
        file=_sys.stderr,
    )

try:
    from shared_core.logging import setup_logging
except (TimeoutError, OSError, ModuleNotFoundError) as logging_err:
    import sys as _sys_logging
    import types as _types
    import logging as _logging
    from pathlib import Path as _PathLogging

    _script_dir_logging = _PathLogging(__file__).resolve().parent
    for _p in {
        _script_dir_logging,
        _script_dir_logging.parent,
        _script_dir_logging.parent / "shared_core",
        _script_dir_logging.parent / "scripts",
    }:
        try:
            if _p.is_dir():
                _ps = str(_p)
                if _ps not in _sys_logging.path:
                    _sys_logging.path.append(_ps)
        except Exception:
            pass

    import time as _time

    class _WorkspaceFallbackLogger:
        def __init__(self, name: str = "workspace"):
            self._logger = _logging.getLogger(name)
            if not self._logger.handlers:
                h = _logging.StreamHandler()
                fmt = _logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
                h.setFormatter(fmt)
                self._logger.addHandler(h)
            self._logger.propagate = False
            self._start_ts = _time.time()
            self._closed = False

        def debug(self, *a, **k): self._logger.debug(*a, **k)
        def info(self, *a, **k): self._logger.info(*a, **k)
        def warning(self, *a, **k): self._logger.warning(*a, **k)
        def error(self, *a, **k): self._logger.error(*a, **k)

        @property
        def logger(self): return self._logger
        def get_metrics(self): return {"total_runtime": _time.time() - self._start_ts}
        def close(self):
            if self._closed: return
            for h in list(self._logger.handlers):
                try: h.flush()
                except Exception: pass
            self._closed = True

    def setup_logging(session_id: str = "session", enable_notion: bool = False, log_level: str = "INFO"):
        lvl = getattr(_logging, str(log_level).upper(), _logging.INFO)
        _logging.basicConfig(level=lvl)
        lg = _WorkspaceFallbackLogger(name=f"{session_id}")
        lg.info("[fallback logging] shared_core.logging unavailable; using inline fallback")
        return lg

    if "shared_core" not in _sys_logging.modules:
        _sys_logging.modules["shared_core"] = _types.ModuleType("shared_core")
    _sys_logging.modules["shared_core.logging"] = _types.ModuleType("shared_core.logging")
    _sys_logging.modules["shared_core.logging"].setup_logging = setup_logging

# Load unified environment and configuration
load_unified_env()
unified_config = get_unified_config()

# Setup logging
workspace_logger = setup_logging(
    session_id="djay_pro_library_export",
    enable_notion=False,
    log_level=os.getenv("LOG_LEVEL", "INFO")
)

# Configuration
DEFAULT_DB_PATH = Path("/Users/brianhellemn/Music/djay/djay Media Library.djayMediaLibrary/MediaLibrary.db")
DB_PATH = Path(unified_config.get("djay_db_path") or os.getenv("DJAY_DB_PATH", str(DEFAULT_DB_PATH)))
OUTPUT_DIR = Path(unified_config.get("djay_export_dir") or os.getenv("DJAY_EXPORT_DIR", "./djay_pro_export"))

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Timestamp for file naming
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


class DjayProLibraryExporter:
    """Extract and export all data from djay Pro SQLite database."""
    
    def __init__(self, db_path: Path, output_dir: Path, logger):
        self.db_path = db_path
        self.output_dir = output_dir
        self.logger = logger
        self.conn: Optional[sqlite3.Connection] = None
        self.all_data: Dict[str, Any] = {
            "export_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "database_path": str(db_path),
                "export_version": "1.0.0"
            },
            "collections": {}
        }
        
    def connect(self) -> bool:
        """Connect to SQLite database in read-only mode."""
        if not self.db_path.exists():
            self.logger.error(f"❌ Database file not found: {self.db_path}")
            return False
            
        try:
            # Open in read-only mode to avoid locking issues
            uri = f"file:{self.db_path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True)
            self.conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
            self.logger.info(f"✅ Connected to database: {self.db_path}")
            return True
        except sqlite3.Error as e:
            self.logger.error(f"❌ Failed to connect to database: {e}")
            return False
    
    def get_all_tables(self) -> List[str]:
        """Get all table names from the database."""
        try:
            cursor = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            self.logger.info(f"📊 Found {len(tables)} tables")
            return tables
        except sqlite3.Error as e:
            self.logger.error(f"❌ Error getting tables: {e}")
            return []
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, str]]:
        """Get schema information for a table."""
        try:
            cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
            schema = []
            for row in cursor.fetchall():
                schema.append({
                    "cid": row[0],
                    "name": row[1],
                    "type": row[2],
                    "notnull": row[3],
                    "dflt_value": row[4],
                    "pk": row[5]
                })
            return schema
        except sqlite3.Error as e:
            self.logger.warning(f"⚠️  Error getting schema for {table_name}: {e}")
            return []
    
    def extract_table_data(self, table_name: str) -> List[Dict[str, Any]]:
        """Extract all data from a table."""
        try:
            cursor = self.conn.execute(f"SELECT * FROM {table_name}")
            rows = []
            for row in cursor.fetchall():
                # Convert Row to dict, handling various data types
                row_dict = {}
                for key in row.keys():
                    value = row[key]
                    # Handle binary data, dates, and other special types
                    if isinstance(value, bytes):
                        # Try to decode as string, or store as base64
                        try:
                            value = value.decode('utf-8')
                        except UnicodeDecodeError:
                            value = f"<binary_data_{len(value)}_bytes>"
                    elif value is None:
                        value = None
                    row_dict[key] = value
                rows.append(row_dict)
            return rows
        except sqlite3.Error as e:
            self.logger.warning(f"⚠️  Error extracting data from {table_name}: {e}")
            return []
    
    def extract_all_collections(self):
        """Extract data from all YapDatabase collections."""
        self.logger.info("🔍 Extracting all collections from database...")
        
        tables = self.get_all_tables()
        
        for table in tables:
            self.logger.info(f"📦 Processing table: {table}")
            
            # Get schema
            schema = self.get_table_schema(table)
            
            # Extract data
            data = self.extract_table_data(table)
            
            # Store in collections
            self.all_data["collections"][table] = {
                "schema": schema,
                "row_count": len(data),
                "data": data
            }
            
            self.logger.info(f"   ✓ Extracted {len(data)} rows from {table}")
    
    def extract_media_items(self) -> List[Dict[str, Any]]:
        """Extract media items (tracks) with all metadata."""
        media_items = []
        
        # Look for tables that might contain media items
        # Common YapDatabase patterns: mediaItem, MediaItem, media_items, etc.
        potential_tables = [t for t in self.all_data["collections"].keys() 
                          if "media" in t.lower() or "item" in t.lower()]
        
        for table_name in potential_tables:
            data = self.all_data["collections"][table_name]["data"]
            for row in data:
                # Try to extract track information
                item = {
                    "table_source": table_name,
                    "raw_data": row
                }
                
                # Common field mappings
                field_mappings = {
                    "title": ["title", "name", "track_title", "Title"],
                    "artist": ["artist", "artist_name", "Artist"],
                    "album": ["album", "album_name", "Album"],
                    "bpm": ["bpm", "BPM", "tempo"],
                    "key": ["key", "Key", "musical_key"],
                    "duration": ["duration", "Duration", "length", "time"],
                    "file_path": ["file_path", "path", "filePath", "file_url"],
                    "genre": ["genre", "Genre"],
                    "year": ["year", "Year", "release_year"],
                    "bitrate": ["bitrate", "Bitrate"],
                    "sample_rate": ["sample_rate", "sampleRate", "SampleRate"],
                    "play_count": ["play_count", "playCount", "times_played"],
                    "rating": ["rating", "Rating", "stars"],
                    "date_added": ["date_added", "dateAdded", "created", "added_date"],
                    "last_played": ["last_played", "lastPlayed", "last_modified"],
                }
                
                for standard_field, possible_keys in field_mappings.items():
                    for key in possible_keys:
                        if key in row and row[key] is not None:
                            item[standard_field] = row[key]
                            break
                
                media_items.append(item)
        
        # Also check all tables for any row that looks like a track
        if not media_items:
            self.logger.warning("⚠️  No media items found in expected tables, scanning all tables...")
            for table_name, collection in self.all_data["collections"].items():
                for row in collection["data"]:
                    # Check if row has track-like fields
                    if any(key.lower() in ["title", "artist", "bpm", "duration"] for key in row.keys()):
                        item = {
                            "table_source": table_name,
                            "raw_data": row
                        }
                        # Extract all fields
                        for key, value in row.items():
                            item[key] = value
                        media_items.append(item)
        
        self.logger.info(f"🎵 Extracted {len(media_items)} media items")
        return media_items
    
    def extract_playlists(self) -> List[Dict[str, Any]]:
        """Extract playlist data."""
        playlists = []
        
        playlist_tables = [t for t in self.all_data["collections"].keys() 
                          if "playlist" in t.lower()]
        
        for table_name in playlist_tables:
            data = self.all_data["collections"][table_name]["data"]
            for row in data:
                playlist = {
                    "table_source": table_name,
                    "raw_data": row
                }
                # Extract all fields
                for key, value in row.items():
                    playlist[key] = value
                playlists.append(playlist)
        
        self.logger.info(f"📋 Extracted {len(playlists)} playlists")
        return playlists
    
    def extract_sessions(self) -> List[Dict[str, Any]]:
        """Extract DJ session data."""
        sessions = []
        
        session_tables = [t for t in self.all_data["collections"].keys() 
                         if "session" in t.lower() or "history" in t.lower()]
        
        for table_name in session_tables:
            data = self.all_data["collections"][table_name]["data"]
            for row in data:
                session = {
                    "table_source": table_name,
                    "raw_data": row
                }
                for key, value in row.items():
                    session[key] = value
                sessions.append(session)
        
        self.logger.info(f"🎧 Extracted {len(sessions)} sessions")
        return sessions
    
    def export_to_json(self) -> Path:
        """Export all data to JSON file."""
        json_path = self.output_dir / f"djay_pro_library_export_{TIMESTAMP}.json"
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.all_data, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"✅ Exported JSON: {json_path}")
            return json_path
        except Exception as e:
            self.logger.error(f"❌ Error exporting JSON: {e}")
            raise
    
    def export_to_csv(self) -> List[Path]:
        """Export collections to separate CSV files."""
        csv_files = []
        
        for table_name, collection in self.all_data["collections"].items():
            if collection["row_count"] == 0:
                continue
            
            # Sanitize table name for filename
            safe_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in table_name)
            csv_path = self.output_dir / f"djay_pro_{safe_name}_{TIMESTAMP}.csv"
            
            try:
                data = collection["data"]
                if not data:
                    continue
                
                # Get all unique keys from all rows
                all_keys = set()
                for row in data:
                    all_keys.update(row.keys())
                
                # Write CSV
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=sorted(all_keys), extrasaction='ignore')
                    writer.writeheader()
                    for row in data:
                        # Convert non-serializable values to strings
                        clean_row = {}
                        for key, value in row.items():
                            if value is None:
                                clean_row[key] = ""
                            elif isinstance(value, (dict, list)):
                                clean_row[key] = json.dumps(value)
                            else:
                                clean_row[key] = str(value)
                        writer.writerow(clean_row)
                
                self.logger.info(f"✅ Exported CSV: {csv_path} ({collection['row_count']} rows)")
                csv_files.append(csv_path)
            except Exception as e:
                self.logger.error(f"❌ Error exporting CSV for {table_name}: {e}")
        
        return csv_files
    
    def export_media_items_csv(self, media_items: List[Dict[str, Any]]) -> Optional[Path]:
        """Export media items to a consolidated CSV file."""
        if not media_items:
            self.logger.warning("⚠️  No media items to export")
            return None
        
        csv_path = self.output_dir / f"djay_pro_media_items_{TIMESTAMP}.csv"
        
        try:
            # Get all unique keys
            all_keys = set()
            for item in media_items:
                all_keys.update(item.keys())
            
            # Remove internal fields
            all_keys.discard("raw_data")
            all_keys.discard("table_source")
            
            # Write CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=sorted(all_keys), extrasaction='ignore')
                writer.writeheader()
                for item in media_items:
                    clean_item = {}
                    for key, value in item.items():
                        if key in ["raw_data", "table_source"]:
                            continue
                        if value is None:
                            clean_item[key] = ""
                        elif isinstance(value, (dict, list)):
                            clean_item[key] = json.dumps(value)
                        else:
                            clean_item[key] = str(value)
                    writer.writerow(clean_item)
            
            self.logger.info(f"✅ Exported media items CSV: {csv_path} ({len(media_items)} items)")
            return csv_path
        except Exception as e:
            self.logger.error(f"❌ Error exporting media items CSV: {e}")
            return None
    
    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate a summary report of the export."""
        summary = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "database_path": str(self.db_path),
            "total_collections": len(self.all_data["collections"]),
            "collections": {}
        }
        
        total_rows = 0
        for table_name, collection in self.all_data["collections"].items():
            row_count = collection["row_count"]
            total_rows += row_count
            summary["collections"][table_name] = {
                "row_count": row_count,
                "columns": len(collection["schema"])
            }
        
        summary["total_rows"] = total_rows
        
        # Add extracted summaries
        media_items = self.extract_media_items()
        playlists = self.extract_playlists()
        sessions = self.extract_sessions()
        
        summary["extracted"] = {
            "media_items": len(media_items),
            "playlists": len(playlists),
            "sessions": len(sessions)
        }
        
        return summary
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.logger.info("🔒 Database connection closed")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Export all data from djay Pro library to CSV and JSON"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DB_PATH),
        help=f"Path to djay Pro MediaLibrary.db (default: {DB_PATH})"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help=f"Output directory for exported files (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Export only JSON file (skip CSV exports)"
    )
    parser.add_argument(
        "--csv-only",
        action="store_true",
        help="Export only CSV files (skip JSON export)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        workspace_logger.logger.setLevel("DEBUG")
    
    workspace_logger.info("=" * 80)
    workspace_logger.info("djay Pro Library Complete Export")
    workspace_logger.info("=" * 80)
    workspace_logger.info(f"Database: {args.db_path}")
    workspace_logger.info(f"Output: {args.output_dir}")
    workspace_logger.info("")
    
    # Initialize exporter
    exporter = DjayProLibraryExporter(
        db_path=Path(args.db_path),
        output_dir=Path(args.output_dir),
        logger=workspace_logger
    )
    
    try:
        # Connect to database
        if not exporter.connect():
            workspace_logger.error("❌ Failed to connect to database. Exiting.")
            sys.exit(1)
        
        # Extract all collections
        exporter.extract_all_collections()
        
        # Export to JSON
        if not args.csv_only:
            json_path = exporter.export_to_json()
            workspace_logger.info(f"📄 JSON export: {json_path}")
        
        # Export to CSV
        if not args.json_only:
            csv_files = exporter.export_to_csv()
            workspace_logger.info(f"📊 CSV exports: {len(csv_files)} files")
            
            # Export consolidated media items
            media_items = exporter.extract_media_items()
            media_csv = exporter.export_media_items_csv(media_items)
            if media_csv:
                workspace_logger.info(f"🎵 Media items CSV: {media_csv}")
        
        # Generate summary
        summary = exporter.generate_summary_report()
        summary_path = exporter.output_dir / f"djay_pro_export_summary_{TIMESTAMP}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        workspace_logger.info("")
        workspace_logger.info("=" * 80)
        workspace_logger.info("EXPORT COMPLETE")
        workspace_logger.info("=" * 80)
        workspace_logger.info(f"Total collections: {summary['total_collections']}")
        workspace_logger.info(f"Total rows: {summary['total_rows']}")
        workspace_logger.info(f"Media items: {summary['extracted']['media_items']}")
        workspace_logger.info(f"Playlists: {summary['extracted']['playlists']}")
        workspace_logger.info(f"Sessions: {summary['extracted']['sessions']}")
        workspace_logger.info(f"Summary: {summary_path}")
        workspace_logger.info("=" * 80)
        
    except KeyboardInterrupt:
        workspace_logger.warning("\n⚠️  Export interrupted by user")
        sys.exit(1)
    except Exception as e:
        workspace_logger.error(f"❌ Export failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        exporter.close()
        workspace_logger.close()


if __name__ == "__main__":
    main()

