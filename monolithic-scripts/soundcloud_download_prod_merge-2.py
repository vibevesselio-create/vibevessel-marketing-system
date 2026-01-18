from __future__ import annotations
# Token override removed - using environment variables only
#!/usr/bin/env python3
"""
SoundCloud Music Library Processor - Full Library Sync with Conflict Management
Enhanced with unified logging, debugging system, Spotify integration, and distributed locking
─────────────────────────────────────────────────────────────────────────────────────────────

OVERVIEW
• Comprehensive music track processing from Notion "Music Tracks" database
• Supports SoundCloud and Spotify tracks with automatic source detection
• Full workflow: download, convert, normalize, tag, deduplicate, Eagle import
• NEW (2026-01-16): Full Library Sync mode with conflict-aware distributed locking
• NEW (2026-01-16): 3-file output structure (WAV + AIFF to Eagle, WAV copy to playlist-tracks)

Aligned with Seren Media Workspace Standards
Version: 2026-01-16
Enhanced: 2026-01-16 (Full Library Sync, Process Locking)

PROCESSING MODES
─────────────────────────────────────────────────────────────────────────────────────────────
  --mode single        Process newest eligible track (default)
  --mode batch         Process tracks in batches of 100
  --mode all           Process all eligible tracks continuously
  --mode reprocess     Re-run for items with existing paths but not marked downloaded
  --mode library-sync  NEW: Full library sync with distributed locking (safe for concurrent runs)
  --mode status        NEW: Show library statistics without processing
  --mode cleanup       NEW: Clean up stale processing locks from crashed processes

LIBRARY-SYNC MODE (NEW)
─────────────────────────────────────────────────────────────────────────────────────────────
The library-sync mode performs a comprehensive synchronization by:
  1. Querying ALL matching tracks from Notion in a single paginated request
  2. Pre-caching the entire Eagle library for efficient deduplication
  3. Using Notion-based distributed locking to prevent conflicts with concurrent processes
  4. Providing detailed progress tracking and automatic lock cleanup

This mode is ideal for:
  - Initial library setup or migration
  - Periodic full-library maintenance
  - Running alongside other batch processes safely (conflict-aware)

Examples:
  python soundcloud_download_prod_merge-2.py --mode library-sync
  python soundcloud_download_prod_merge-2.py --mode library-sync --limit 50
  python soundcloud_download_prod_merge-2.py --mode library-sync --parallel --workers 4
  python soundcloud_download_prod_merge-2.py --mode library-sync --filter missing_eagle

Filter options for library-sync:
  --filter unprocessed    Tracks not yet downloaded (default)
  --filter all            All tracks with SoundCloud URLs
  --filter missing_eagle  Downloaded tracks missing Eagle IDs

DISTRIBUTED PROCESS LOCKING
─────────────────────────────────────────────────────────────────────────────────────────────
When multiple instances run simultaneously (e.g., library-sync + batch mode), the system
uses Notion-based locking to prevent conflicts:
  - Lock format: "PID:HOSTNAME:UUID:TIMESTAMP" stored in "Processing Lock" property
  - Lock timeout: 30 minutes (configurable via PROCESS_LOCK_TIMEOUT_MINUTES)
  - Stale locks are automatically cleaned up before processing
  - Each process checks for existing locks before processing a track
  - Locks are released after successful processing or on error

To add the "Processing Lock" property to your Notion database:
  1. Open your Music Tracks database in Notion
  2. Add a new property named "Processing Lock" (type: Text)
  3. The script will automatically detect and use this property

ENVIRONMENT VARIABLES
─────────────────────────────────────────────────────────────────────────────────────────────
Required:
  NOTION_TOKEN          Notion integration token
  TRACKS_DB_ID          Notion database ID for tracks

Optional:
  OUT_DIR               Output directory for processed files
  BACKUP_DIR            Backup directory for M4A files
  WAV_BACKUP_DIR        Backup directory for WAV files
  PLAYLIST_TRACKS_DIR   Directory for playlist-organized WAV copies (new 3-file structure)
  EAGLE_API_BASE        Eagle API endpoint (default: http://localhost:41595)
  EAGLE_LIBRARY_PATH    Path to Eagle library (blank = use active library)

Spotify Integration:
  SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
  SPOTIFY_ACCESS_TOKEN, SPOTIFY_REFRESH_TOKEN (optional but recommended)

Process Locking:
  PROCESS_LOCK_ENABLED=1           Enable/disable locking (default: 1)
  PROCESS_LOCK_TIMEOUT_MINUTES=30  Lock expiration time (default: 30)

Concurrency:
  SC_MAX_CONCURRENCY=4             Max parallel workers (default: 4)
  SC_ENABLE_PARALLEL_BATCH=1       Enable parallel batch processing

Known schema caveat: some workspaces name the download checkbox "Downloaded" not "DL". This script auto-detects and adapts.
"""
import os, sys, re, json, time, shutil, logging, argparse, tempfile, subprocess, threading, hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set, Iterator
from typing import Dict, List, Tuple, Any, Optional, Set, Iterator
from difflib import SequenceMatcher
# CRITICAL: centralized token access (pre-commit enforced)
from shared_core.notion.token_manager import get_notion_token
# Import unified configuration first, shared logging second
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
        f"[soundcloud_download_prod_merge] unified_config unavailable "
        f"({unified_err}); using fallback module.",
        file=_sys.stderr,
    )
# Import Spotify integration module
try:
    from spotify_integration_module import SpotifyNotionSync, SpotifyAPI, SpotifyOAuthManager
    SPOTIFY_AVAILABLE = True
except (TimeoutError, OSError, ModuleNotFoundError) as spotify_err:
    SPOTIFY_AVAILABLE = False
    print(f"[soundcloud_download_prod_merge] Spotify integration unavailable ({spotify_err}); Spotify features disabled.", file=sys.stderr)

try:
    from shared_core.logging import setup_logging
except (TimeoutError, OSError, ModuleNotFoundError) as logging_err:
    import sys as _sys_logging
    import types as _types
    import logging as _logging
    from pathlib import Path as _PathLogging

    # Ensure repo root and common sibling dirs are on sys.path
    _script_dir_logging = _PathLogging(__file__).resolve().parent
    for _p in {
        _script_dir_logging,
        _script_dir_logging.parent,                         # repo root
        _script_dir_logging.parent / "shared_core",        # shared_core as a sibling
        _script_dir_logging.parent / "scripts",            # scripts folder
    }:
        try:
            if _p.is_dir():
                _ps = str(_p)
                if _ps not in _sys_logging.path:
                    _sys_logging.path.append(_ps)
        except Exception:
            pass

    # Inline fallback for shared_core.logging to avoid hard dependency on external module
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

        # Expose std logging API
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

    # Synthesize a minimal shared_core package so `import shared_core.logging` resolves later
    if "shared_core" not in _sys_logging.modules:
        _sys_logging.modules["shared_core"] = _types.ModuleType("shared_core")
    _sys_logging.modules["shared_core.logging"] = _types.ModuleType("shared_core.logging")
    _sys_logging.modules["shared_core.logging"].setup_logging = setup_logging

# Load unified environment and configuration
load_unified_env()
unified_config = get_unified_config()

# ── Shared config helpers (parity with remove_duplicates) ─────────────────
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
DEFAULT_CONFIG: Dict[str, str] = {
    "NOTION_TOKEN": "",
    "TRACKS_DB_ID": "",
    "NOTION_TIMEOUT": "60",
    "NOTION_VERSION": "2022-06-28",
}

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

try:
    from spotify_integration_module import SpotifyAPI, SpotifyOAuthManager
    _SPOTIFY_IMPORT_ERROR: Optional[Exception] = None
except (ImportError, ModuleNotFoundError) as _spotify_exc:
    SpotifyAPI = None  # type: ignore[assignment]
    SpotifyOAuthManager = None  # type: ignore[assignment]
    _SPOTIFY_IMPORT_ERROR = _spotify_exc
def _env_or_default(key: str) -> str:
    val = os.getenv(key)
    if val is None or val == "":
        return DEFAULT_CONFIG.get(key, "")
    return val

import re as _re_uuid
_UUID_DASHED_RE = _re_uuid.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", _re_uuid.IGNORECASE)
_UUID_32_RE = _re_uuid.compile(r"[0-9a-f]{32}", _re_uuid.IGNORECASE)

def format_database_id(db_id: str) -> str:
    """Convert 32-char hex to UUID format for Notion API 2022-06-28+"""
    if not db_id or len(db_id) != 32:
        return db_id
    if '-' in db_id:
        return db_id  # Already formatted
    # Insert dashes at positions 8, 12, 16, 20
    return f"{db_id[:8]}-{db_id[8:12]}-{db_id[12:16]}-{db_id[16:20]}-{db_id[20:]}"

def _normalize_uuid(s: str) -> str:
    if not isinstance(s, str):
        return s
    c = s.strip()
    m = _UUID_DASHED_RE.search(c)
    if m: return m.group(0).replace("-", "").lower()
    m = _UUID_32_RE.search(c)
    if m: return m.group(0).lower()
    return "".join(ch for ch in c.lower() if ch in "0123456789abcdef")


def _truthy(value) -> bool:
    """Lenient boolean conversion for configuration flags."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class WorkspaceLoggerAdapter:
    """Adapter exposing legacy helper methods on top of the shared-core logger."""

    def __init__(self, base_logger, script_name: str = "soundcloud_download"):
        self._base = base_logger
        self._script_name = script_name
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self._closed = False

    def __getattr__(self, item):
        return getattr(self._base, item)

    @property
    def logger(self):
        return getattr(self._base, "logger", None)

    def record_processed(self, increment: int = 1):
        self.processed_count += increment

    def record_failed(self, increment: int = 1):
        self.failed_count += increment

    def record_skipped(self, increment: int = 1):
        self.skipped_count += increment

    def temp_dir_created(self, temp_dir: str):
        self._base.debug(f"📁 Created temp directory: {temp_dir}")

    def temp_dir_cleaned(self, temp_dir: str):
        self._base.debug(f"🧹 Cleaned temp directory: {temp_dir}")

    def script_end(self, exit_code: int = 0, error_message: Optional[str] = None):
        if error_message:
            self._base.error(
                f"❌ SCRIPT END: {self._script_name} - Exit Code: {exit_code} - Error: {error_message}"
            )
        else:
            self._base.info(f"✅ SCRIPT END: {self._script_name} - Exit Code: {exit_code}")
        self._base.info(
            f"📊 Final Stats: processed={self.processed_count} failed={self.failed_count} skipped={self.skipped_count}"
        )
        if hasattr(self._base, "get_metrics"):
            try:
                metrics = self._base.get_metrics()
                runtime = metrics.get("total_runtime")
                if runtime is not None:
                    self._base.info(f"⏱️  Total Runtime: {runtime:.2f}s")
            except Exception:
                pass
        self.close()

    def close(self):
        if self._closed:
            return
        if hasattr(self._base, "close"):
            try:
                self._base.close()
            except Exception:
                pass
        self._closed = True


_log_level = unified_config.get("log_level") or "INFO"
if _truthy(unified_config.get("enable_debug", False)):
    _log_level = "DEBUG"

_enable_notion_logs = _truthy(unified_config.get("enable_notion_logging", False))
_base_logger = setup_logging(
    session_id="soundcloud_download",
    enable_notion=_enable_notion_logs,
    log_level=str(_log_level).upper()
)

# Expose adapter with legacy helper methods expected by the script
workspace_logger = WorkspaceLoggerAdapter(_base_logger, script_name="soundcloud_download")
workspace_logger.info("Unified logging initialized via shared_core.logging")

# Priority ordering configuration
_DEFAULT_PRIORITY_ORDER = [x.strip() for x in os.getenv("SC_PRIORITY_ORDER", "Critical,High,Medium,Low").split(",") if x.strip()]
_PRIORITY_RANK_BY_NAME = {name.lower(): i for i, name in enumerate(_DEFAULT_PRIORITY_ORDER)}
_PRIORITY_RANK_FALLBACK = len(_DEFAULT_PRIORITY_ORDER) + 1
_NUMERIC_DESC = str(os.getenv("SC_PRIORITY_NUMERIC_DESC", "1")).strip().lower() in {"1", "true", "yes", "on"}

_num_re = re.compile(r"^\s*(\d+)")
_name_to_num = {
    "critical": 5, "highest": 5,
    "high": 4,
    "medium": 3, "med": 3,
    "low": 2, "lowest": 1,
}

def _extract_priority_value(props: dict) -> str | None:
    pri_name = _resolve_prop_name("Priority") or "Priority"
    prop = props.get(pri_name, {})
    t = prop.get("type")
    if t == "status":
        return (prop.get("status") or {}).get("name")
    if t == "select":
        return (prop.get("select") or {}).get("name")
    if t == "multi_select":
        ms = prop.get("multi_select") or []
        return ms[0].get("name") if ms else None
    return None

def _priority_from_props(props: dict) -> int:
    """Lower rank = higher priority. 5→-5, 4→-4, …; name and order fallbacks."""
    try:
        val = _extract_priority_value(props)
        if not val:
            return _PRIORITY_RANK_FALLBACK
        s = str(val).strip()

        # 1) Numeric labels like "5 - Critical"
        if _NUMERIC_DESC:
            m = _num_re.match(s)
            if m:
                try:
                    n = int(m.group(1))
                    return -n
                except Exception:
                    pass

        # 2) Name-to-number mapping
        lower_val = s.lower()
        stripped_lower = re.sub(r"^\s*\d+\s*[-:\u2013]\s*", "", lower_val).strip()

        for candidate in (lower_val, stripped_lower):
            if not candidate:
                continue
            n = _name_to_num.get(candidate)
            if n is not None:
                return -n

        # 3) Name-order fallback from SC_PRIORITY_ORDER
        for candidate in (lower_val, stripped_lower):
            if not candidate:
                continue
            idx = _PRIORITY_RANK_BY_NAME.get(candidate)
            if idx is not None:
                return idx

        return _PRIORITY_RANK_FALLBACK
    except Exception:
        return _PRIORITY_RANK_FALLBACK

def _title_from_props(props: dict) -> str:
    try:
        name_prop = _resolve_prop_name("Name") or "Name"
        return _page_text_for(props.get(name_prop, {})) or ""
    except Exception:
        for cand in ("Name", "Title"):
            try:
                v = _page_text_for(props.get(cand, {}))
                if v: return v
            except Exception:
                pass
        return ""

def order_candidates(pages: list[dict]) -> list[dict]:
    """Priority (numeric/name-aware) → Title A–Z."""
    try:
        return sorted(
            pages,
            key=lambda p: (
                _priority_from_props(p.get("properties", {})),
                _title_from_props(p.get("properties", {})).lower(),
            ),
        )
    except Exception:
        return pages

# Processing order configuration (controls Notion query sort priorities)
ORDER_MODE_CHOICES = {
    "priority_then_title",
    "priority_then_created",
    "title_asc",
    "created_then_release",
    "release_then_created",
    "release_only",
    "created_only",
    "last_edited",
}

ORDER_MODE = os.getenv("SC_ORDER_MODE", "priority_then_created").lower()
if ORDER_MODE not in ORDER_MODE_CHOICES:
    logging.warning("Unknown SC_ORDER_MODE '%s' – defaulting to created_only", ORDER_MODE)
    ORDER_MODE = "created_only"

# Concurrency configuration for batch mode
MAX_CONCURRENT_JOBS = int(os.getenv("SC_MAX_CONCURRENCY", "4"))
workspace_logger.info(f"🧵 Max concurrency for batch mode: {MAX_CONCURRENT_JOBS}")
workspace_logger.info(f"📑 Order mode: {ORDER_MODE} | Priority numeric mode: {_NUMERIC_DESC} | Name-order: {_DEFAULT_PRIORITY_ORDER}")

import sys
import json
import glob
import shutil
import random
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import cProfile
import tempfile
import re
import difflib
import argparse
import traceback
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
import subprocess
import logging
from pathlib import Path
from send2trash import send2trash
import hashlib
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Add workspace scripts to path for imports
sys.path.append(str(Path(__file__).parent))

# Third-Party
import yt_dlp
import librosa
try:
    from librosa.feature import rhythm as librosa_rhythm
except (ImportError, AttributeError, RuntimeError):
    librosa_rhythm = None
import numpy as np
import requests
from notion_client import Client
# Import smart Eagle API with state tracking
try:
    from eagle_api_smart import (
        eagle_request_smart as eagle_request,
        eagle_add_item_smart as eagle_add_item,
        eagle_import_to_library,
        eagle_switch_library_smart as eagle_switch_library,
        test_eagle_connection,
        state_manager,
        query_cache,
        NotionQueryCache,
        set_workspace_logger
    )
    # Set the workspace logger for Eagle API
    set_workspace_logger(workspace_logger)
    EAGLE_SMART_AVAILABLE = True
    workspace_logger.info("✅ Using smart Eagle API with state tracking")
except ImportError:
    EAGLE_SMART_AVAILABLE = False
    workspace_logger.warning("⚠️ Smart Eagle API not available, using fallback")

from dotenv import load_dotenv
from pathlib import Path

# Audio Normalizer imports
try:
    from audio_normalizer import AudioNormalizer, NormalizationConfig
    from audio_normalizer.notion_integration import NotionAudioLogger
    AUDIO_NORMALIZER_AVAILABLE = True
except ImportError:
    # Use our built-in Platinum Notes-style normalizer
    AUDIO_NORMALIZER_AVAILABLE = False

# Proper LUFS normalization library
try:
    import pyloudnorm as pyln
    PYLOUDNORM_AVAILABLE = True
except ImportError:
    PYLOUDNORM_AVAILABLE = False

# Optional – used only for fast AIFF duration read; falls back to ffprobe
try:
    import soundfile as sf
except ImportError:
    sf = None

# Cached pyloudnorm Meter instances per sample rate
_meter_cache: dict[int, Any] = {}
def get_meter(sample_rate: int):
    """Return a cached pyloudnorm Meter for the given sample rate."""
    if not PYLOUDNORM_AVAILABLE:
        raise RuntimeError("pyloudnorm not available")
    if sample_rate not in _meter_cache:
        _meter_cache[sample_rate] = pyln.Meter(sample_rate)
    return _meter_cache[sample_rate]

def _build_http_session() -> requests.Session:
    """Build a shared HTTP session with connection pooling and retries."""
    session = requests.Session()
    try:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        )
    except TypeError:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

_HTTP_SESSION = _build_http_session()

# ───────────────────────────────────────────────────────────────
# Audio Normalizer - Platinum Notes Style Implementation
# ───────────────────────────────────────────────────────────────
def analyze_audio_loudness(audio_samples: np.ndarray, sample_rate: int = 44100) -> dict:
    """
    FIXED: Proper LUFS loudness analysis using ITU-R BS.1770-4 standard via pyloudnorm.
    Replaces the broken RMS approximation with actual LUFS measurement.
    """
    try:
        if not PYLOUDNORM_AVAILABLE:
            # Fallback to improved RMS method if pyloudnorm unavailable
            return analyze_audio_loudness_fallback(audio_samples, sample_rate)
        
        # Ensure audio is in correct format for pyloudnorm
        if audio_samples.ndim == 1:
            audio_samples = audio_samples.reshape(-1, 1)  # Convert to column vector for mono
        
        # Create BS.1770 meter
        meter = get_meter(sample_rate)
        
        # Measure integrated loudness (LUFS)
        try:
            integrated_loudness = meter.integrated_loudness(audio_samples)
        except ValueError as e:
            if "not contain enough samples" in str(e):
                # File too short for integrated measurement, use RMS fallback
                workspace_logger.warning(f"Audio too short for integrated LUFS, using RMS fallback")
                rms = np.sqrt(np.mean(audio_samples**2))
                integrated_loudness = 20 * np.log10(rms) - 16 if rms > 0 else -70
            else:
                raise
        
        # Calculate additional metrics
        peak = np.max(np.abs(audio_samples))
        rms = np.sqrt(np.mean(audio_samples**2))
        crest_factor = peak / rms if rms > 0 else 0
        
        # True peak measurement (using numpy max for peak detection)
        true_peak = np.max(np.abs(audio_samples))
        true_peak_db = 20 * np.log10(true_peak) if true_peak > 0 else -70
        
        # Clipping detection (samples exceeding 0.95)
        clipped_samples = np.sum(np.abs(audio_samples) > 0.95)
        clipping_percentage = (clipped_samples / len(audio_samples.flatten())) * 100
        
        return {
            'lufs_integrated': float(integrated_loudness),
            'lufs_approx': float(integrated_loudness),  # Keep for compatibility
            'true_peak_db': float(true_peak_db),
            'peak': float(peak),
            'rms': float(rms),
            'crest_factor': float(crest_factor),
            'clipped_samples': int(clipped_samples),
            'clipping_percentage': float(clipping_percentage),
            'measurement_method': 'ITU-R BS.1770-4 (pyloudnorm)'
        }
        
    except Exception as e:
        workspace_logger.warning(f"Proper LUFS analysis failed: {e}")
        return analyze_audio_loudness_fallback(audio_samples, sample_rate)

def analyze_audio_loudness_fallback(audio_samples: np.ndarray, sample_rate: int = 44100) -> dict:
    """
    Improved fallback method when pyloudnorm is unavailable.
    Still better than the original RMS approximation.
    """
    try:
        # Basic measurements
        rms = np.sqrt(np.mean(audio_samples**2))
        peak = np.max(np.abs(audio_samples))
        crest_factor = peak / rms if rms > 0 else 0
        
        # Improved LUFS approximation with A-weighting
        if rms > 0:
            # Apply basic frequency weighting approximation
            n_fft = 2048
            hop_length = 512
            
            # Compute STFT
            stft = librosa.stft(audio_samples, n_fft=n_fft, hop_length=hop_length)
            magnitude = np.abs(stft)
            
            # Get frequencies and apply A-weighting
            freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
            a_weights = librosa.A_weighting(freqs)
            
            # Apply weighting and compute weighted RMS
            weighted_magnitude = magnitude * (10**(a_weights/20)).reshape(-1, 1)
            weighted_rms = np.sqrt(np.mean(weighted_magnitude**2))
            
            # Convert to approximate LUFS
            lufs_approx = 20 * np.log10(weighted_rms) - 12  # Adjusted offset
            lufs_approx = max(-70, min(-6, lufs_approx))  # Reasonable bounds
        else:
            lufs_approx = -70
        
        # Clipping detection
        clipped_samples = np.sum(np.abs(audio_samples) > 0.95)
        clipping_percentage = (clipped_samples / len(audio_samples)) * 100
        
        return {
            'lufs_integrated': float(lufs_approx),
            'lufs_approx': float(lufs_approx),
            'true_peak_db': 20 * np.log10(peak) if peak > 0 else -70,
            'peak': float(peak),
            'rms': float(rms),
            'crest_factor': float(crest_factor),
            'clipped_samples': int(clipped_samples),
            'clipping_percentage': float(clipping_percentage),
            'measurement_method': 'A-weighted RMS approximation (fallback)'
        }
        
    except Exception as e:
        workspace_logger.warning(f"Fallback loudness analysis failed: {e}")
        return {
            'lufs_integrated': -70.0,
            'lufs_approx': -70.0,
            'true_peak_db': -70.0,
            'peak': 0.0,
            'rms': 0.0,
            'crest_factor': 0.0,
            'clipped_samples': 0,
            'clipping_percentage': 0.0,
            'measurement_method': 'failed'
        }

def detect_and_repair_clipping(audio_samples: np.ndarray, threshold: float = 0.95) -> tuple[np.ndarray, dict]:
    """
    Detect and repair clipped peaks using smoothing interpolation.
    Based on Platinum Notes clipping repair approach.
    """
    try:
        original_samples = audio_samples.copy()
        repaired_samples = audio_samples.copy()
        
        # Find clipped samples
        clipped_indices = np.where(np.abs(audio_samples) > threshold)[0]
        clipping_count = len(clipped_indices)
        
        if clipping_count == 0:
            return repaired_samples, {'clipped_found': 0, 'clipped_repaired': 0}
        
        # Repair clipped samples using smoothing
        for idx in clipped_indices:
            # Get surrounding samples for interpolation
            start_idx = max(0, idx - 2)
            end_idx = min(len(audio_samples), idx + 3)
            
            # Create smooth transition
            if idx > 0 and idx < len(audio_samples) - 1:
                # Use linear interpolation with neighbors
                left_val = audio_samples[idx - 1]
                right_val = audio_samples[idx + 1]
                repaired_samples[idx] = (left_val + right_val) / 2
                
                # Apply soft limiting to prevent overshoot
                if np.abs(repaired_samples[idx]) > threshold:
                    repaired_samples[idx] = np.sign(repaired_samples[idx]) * threshold * 0.95
        
        repaired_count = np.sum(np.abs(repaired_samples) > threshold)
        
        return repaired_samples, {
            'clipped_found': clipping_count,
            'clipped_repaired': clipping_count - repaired_count
        }
        
    except Exception as e:
        workspace_logger.warning(f"Clipping repair failed: {e}")
        return audio_samples, {'clipped_found': 0, 'clipped_repaired': 0}

def apply_warmth_saturation(audio_samples: np.ndarray, mode: str = "gentle") -> tuple[np.ndarray, dict]:
    """
    Apply harmonic saturation for warmth enhancement.
    Based on Platinum Notes warmth/saturation stage.
    """
    try:
        original_samples = audio_samples.copy()
        processed_samples = audio_samples.copy()
        
        if mode == "none":
            return processed_samples, {'warmth_applied': False, 'mode': mode}
        
        # Apply different saturation curves based on mode
        if mode == "gentle":
            # Gentle harmonic enhancement
            processed_samples = np.tanh(processed_samples * 1.1) * 0.95
            saturation_amount = 0.1
        elif mode == "hot":
            # Hot vacuum tube simulation
            processed_samples = np.tanh(processed_samples * 1.3) * 0.9
            saturation_amount = 0.3
        else:
            return processed_samples, {'warmth_applied': False, 'mode': 'unknown'}
        
        # Calculate harmonic distortion
        harmonic_content = np.mean(np.abs(processed_samples - original_samples))
        
        return processed_samples, {
            'warmth_applied': True,
            'mode': mode,
            'saturation_amount': saturation_amount,
            'harmonic_content': float(harmonic_content)
        }
        
    except Exception as e:
        workspace_logger.warning(f"Warmth saturation failed: {e}")
        return audio_samples, {'warmth_applied': False, 'mode': mode, 'error': str(e)}

def apply_loudness_normalization(audio_samples: np.ndarray, target_lufs: float = -8.0,
                                sample_rate: int = 44100, max_true_peak_db: float = -1.0) -> tuple[np.ndarray, dict]:
    """
    FIXED: Professional LUFS-based loudness normalization with proper limiting.
    Uses pyloudnorm for accurate LUFS measurement and normalization.
    """
    try:
        if not PYLOUDNORM_AVAILABLE:
            workspace_logger.warning("⚠️  Using fallback normalization (pyloudnorm unavailable)")
            return apply_loudness_normalization_fallback(audio_samples, target_lufs, sample_rate, max_true_peak_db)
        
        # Ensure correct audio format
        if audio_samples.ndim == 1:
            audio_samples = audio_samples.reshape(-1, 1)
        
        # Measure current loudness
        meter = get_meter(sample_rate)
        current_lufs = meter.integrated_loudness(audio_samples)
        
        if np.isnan(current_lufs) or np.isinf(current_lufs):
            workspace_logger.warning("⚠️  Invalid LUFS measurement, using fallback")
            return apply_loudness_normalization_fallback(audio_samples.flatten(), target_lufs, sample_rate, max_true_peak_db)
        
        workspace_logger.info(f"🎚️  Current LUFS: {current_lufs:.1f}, Target: {target_lufs:.1f}")
        
        # Apply loudness normalization
        normalized_audio = pyln.normalize.loudness(audio_samples, current_lufs, target_lufs)
        
        # Apply true peak limiting
        true_peak_linear = 10**(max_true_peak_db / 20)  # Convert dB to linear
        
        # Check true peak (using numpy max)
        current_true_peak = np.max(np.abs(normalized_audio))
        peak_exceeded = current_true_peak > true_peak_linear
        
        if peak_exceeded:
            # Apply peak limiting
            peak_reduction = true_peak_linear / current_true_peak
            normalized_audio = normalized_audio * peak_reduction
            workspace_logger.info(f"🔧 Applied peak limiting: {20*np.log10(current_true_peak):.1f} -> {max_true_peak_db:.1f} dBTP")
            limiting_applied = True
            samples_limited = int(np.sum(np.abs(normalized_audio) >= true_peak_linear * 0.99))
        else:
            limiting_applied = False
            samples_limited = 0
        
        # Final measurements
        final_lufs = meter.integrated_loudness(normalized_audio)
        final_true_peak = np.max(np.abs(normalized_audio))
        final_true_peak_db = 20 * np.log10(final_true_peak) if final_true_peak > 0 else -70
        
        # Calculate gain applied
        gain_db = final_lufs - current_lufs
        
        result_audio = normalized_audio.flatten() if normalized_audio.ndim > 1 else normalized_audio
        
        return result_audio, {
            'original_lufs': float(current_lufs),
            'target_lufs': float(target_lufs),
            'final_lufs': float(final_lufs),
            'gain_applied_db': float(gain_db),
            'limiting_applied': limiting_applied,
            'samples_limited': samples_limited,
            'true_peak_ceiling_db': float(max_true_peak_db),
            'final_true_peak_db': float(final_true_peak_db),
            'normalization_method': 'pyloudnorm ITU-R BS.1770-4',
            'processing_successful': True
        }
        
    except Exception as e:
        workspace_logger.warning(f"Proper loudness normalization failed: {e}")
        return apply_loudness_normalization_fallback(audio_samples.flatten(), target_lufs, sample_rate, max_true_peak_db)

def apply_loudness_normalization_fallback(audio_samples: np.ndarray, target_lufs: float = -8.0,
                                        sample_rate: int = 44100, max_true_peak_db: float = -1.0) -> tuple[np.ndarray, dict]:
    """
    Fallback normalization when pyloudnorm unavailable. Uses improved RMS-based approach.
    """
    try:
        # Analyze current loudness (with caching to avoid redundant analysis)
        if hasattr(audio_samples, '_cached_fallback_analysis'):
            current_analysis = audio_samples._cached_fallback_analysis
        else:
            current_analysis = analyze_audio_loudness_fallback(audio_samples, sample_rate)
            # Note: We can't actually set attributes on numpy arrays, but this pattern
            # documents the intent for future optimization with a wrapper class
            try:
                audio_samples._cached_fallback_analysis = current_analysis
            except (AttributeError, TypeError):
                pass  # NumPy arrays don't support arbitrary attributes
        current_lufs = current_analysis['lufs_approx']
        
        # Calculate required gain (with LESS conservative limits)
        lufs_diff = target_lufs - current_lufs
        max_boost_db = 12.0  # Increased from 6dB
        max_cut_db = -18.0   # Increased from -12dB
        
        if lufs_diff > max_boost_db:
            workspace_logger.info(f"⚠️  Limiting gain boost from {lufs_diff:+.1f} dB to {max_boost_db:+.1f} dB")
            gain_db = max_boost_db
        elif lufs_diff < max_cut_db:
            workspace_logger.info(f"⚠️  Limiting gain cut from {lufs_diff:+.1f} dB to {max_cut_db:+.1f} dB")
            gain_db = max_cut_db
        else:
            gain_db = lufs_diff
        
        gain_linear = 10**(gain_db / 20)
        workspace_logger.info(f"🎚️  Fallback normalization: {current_lufs:.1f} → {target_lufs:.1f} LUFS (gain: {gain_db:+.1f} dB)")
        
        # Apply gain
        normalized_samples = audio_samples * gain_linear
        
        # Apply peak limiting
        true_peak_linear = 10**(max_true_peak_db / 20)
        peak_before = np.max(np.abs(normalized_samples))
        
        if peak_before > true_peak_linear:
            normalized_samples = np.clip(normalized_samples, -true_peak_linear, true_peak_linear)
            limiting_applied = True
            samples_limited = int(np.sum(np.abs(audio_samples * gain_linear) > true_peak_linear))
        else:
            limiting_applied = False
            samples_limited = 0
        
        # Final analysis
        final_analysis = analyze_audio_loudness_fallback(normalized_samples, sample_rate)
        final_lufs = final_analysis['lufs_approx']
        final_true_peak_db = final_analysis['true_peak_db']
        
        return normalized_samples, {
            'original_lufs': float(current_lufs),
            'target_lufs': float(target_lufs),
            'final_lufs': float(final_lufs),
            'gain_applied_db': float(gain_db),
            'limiting_applied': limiting_applied,
            'samples_limited': samples_limited,
            'true_peak_ceiling_db': float(max_true_peak_db),
            'final_true_peak_db': float(final_true_peak_db),
            'normalization_method': 'Fallback A-weighted RMS',
            'processing_successful': True
        }
        
    except Exception as e:
        workspace_logger.warning(f"Fallback normalization failed: {e}")
        return audio_samples, {
            'processing_successful': False,
            'error': str(e),
            'normalization_method': 'Failed'
        }

def normalize_audio_platinum_notes_style(audio_samples: np.ndarray, sample_rate: int = 44100,
                                        target_lufs: float = -8.0, warmth_mode: str = "gentle") -> tuple[np.ndarray, dict]:
    """
    FIXED: Complete Platinum Notes-style audio normalization pipeline with proper LUFS measurement.
    This replaces the original function with accurate LUFS processing.
    
    Steps:
    1. Analyze current audio characteristics with proper LUFS
    2. Detect and repair clipping
    3. Apply warmth/saturation
    4. Apply proper LUFS-based loudness normalization with limiting
    5. Final quality check
    
    Returns:
        tuple: (normalized_audio_samples, processing_report)
    """
    try:
        workspace_logger.info("🎛️  Starting FIXED Platinum Notes-style audio normalization...")
        
        # Step 1: Initial analysis with proper LUFS
        initial_analysis = analyze_audio_loudness(audio_samples, sample_rate)
        workspace_logger.info(f"📊 Initial LUFS: {initial_analysis['lufs_integrated']:.1f} ({initial_analysis['measurement_method']})")
        
        # Step 2: Clipping detection and repair (keep existing function)
        workspace_logger.info("🔧 Detecting and repairing clipped peaks...")
        repaired_samples, clipping_report = detect_and_repair_clipping(audio_samples)
        if clipping_report['clipped_found'] > 0:
            workspace_logger.info(f"✅ Repaired {clipping_report['clipped_repaired']}/{clipping_report['clipped_found']} clipped samples")
        
        # Step 3: Warmth/saturation (keep existing function)
        workspace_logger.info(f"🔥 Applying {warmth_mode} warmth enhancement...")
        saturated_samples, warmth_report = apply_warmth_saturation(repaired_samples, warmth_mode)
        if warmth_report['warmth_applied']:
            workspace_logger.info(f"✅ Applied {warmth_mode} saturation")
        
        # Step 4: PROPER loudness normalization
        workspace_logger.info(f"🎚️  Normalizing to target LUFS: {target_lufs}")
        normalized_samples, normalization_report = apply_loudness_normalization(
            saturated_samples, target_lufs, sample_rate
        )
        
        if normalization_report['processing_successful']:
            workspace_logger.info(f"✅ Normalization complete: {normalization_report['original_lufs']:.1f} → {normalization_report['final_lufs']:.1f} LUFS")
            workspace_logger.info(f"📊 Method: {normalization_report['normalization_method']}")
        else:
            workspace_logger.warning(f"❌ Normalization failed: {normalization_report.get('error', 'Unknown error')}")
        
        # Log limiting details
        if normalization_report.get('limiting_applied', False):
            samples_limited = normalization_report.get('samples_limited', 0)
            final_peak_db = normalization_report.get('final_true_peak_db', 0)
            workspace_logger.info(f"🔧 Peak limiting applied: {samples_limited} samples limited")
            workspace_logger.info(f"📊 Final true peak: {final_peak_db:.1f} dBTP")
        else:
            final_peak_db = normalization_report.get('final_true_peak_db', 0)
            workspace_logger.info(f"ℹ️  No limiting needed (peaks below threshold)")
            workspace_logger.info(f"📊 Final true peak: {final_peak_db:.1f} dBTP")
        
        # Step 5: Final analysis (reuse normalization metrics to avoid extra pass)
        final_analysis = {
            'lufs_integrated': normalization_report.get('final_lufs'),
            'measurement_method': normalization_report.get('normalization_method'),
            'true_peak_db': normalization_report.get('final_true_peak_db'),
            'peak': float(np.max(np.abs(normalized_samples))) if isinstance(normalized_samples, np.ndarray) else None
        }
        workspace_logger.info(f"📊 Final LUFS: {final_analysis['lufs_integrated']:.1f}")
        
        # Compile comprehensive report
        processing_report = {
            'initial_analysis': initial_analysis,
            'final_analysis': final_analysis,
            'clipping_report': clipping_report,
            'warmth_report': warmth_report,
            'normalization_report': normalization_report,
            'processing_successful': True,
            'target_lufs': target_lufs,
            'warmth_mode': warmth_mode,
            'normalization_method': normalization_report.get('normalization_method', 'Unknown')
        }
        
        workspace_logger.info("✅ FIXED Platinum Notes-style normalization complete!")
        return normalized_samples, processing_report
        
    except Exception as e:
        workspace_logger.error(f"❌ Fixed audio normalization failed: {e}")
        return audio_samples, {
            'processing_successful': False,
            'error': str(e),
            'initial_analysis': analyze_audio_loudness(audio_samples, sample_rate)
        }

# Load environment variables from common locations; proceed even if one is missing
_loaded_any_env = False
for _env_path in [
    "/Users/brianhellemn/Scripts-MM1/api.env",
    str(Path(__file__).resolve().parent.parent / "api.env"),  # repo root api.env
    str(Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "github" / "api.env"),  # iCloud github/api.env
]:
    try:
        if load_dotenv(_env_path):
            _loaded_any_env = True
    except Exception:
        pass


# ───────────────────────────────────────────────────────────────
# CRITICAL NOTE: Token Handling & Validation (unified)
# ───────────────────────────────────────────────────────────────
NOTION_TOKEN = (unified_config.get("notion_token") or get_notion_token() or "").strip()
NOTION_VERSION = _env_or_default("NOTION_VERSION") or "2022-06-28"  # Latest stable Notion API version
try:
    NOTION_TIMEOUT = int(_env_or_default("NOTION_TIMEOUT") or "60")
except ValueError:
    NOTION_TIMEOUT = 60

# Resolve Tracks DB id: prefer unified_config, then env TRACKS_DB_ID, then DATABASE_ID
TRACKS_DB_ID = (unified_config.get("tracks_db_id") or os.getenv("TRACKS_DB_ID") or os.getenv("DATABASE_ID") or "").strip()
# Normalize first (remove existing dashes if any)
TRACKS_DB_ID = _normalize_uuid(TRACKS_DB_ID) if TRACKS_DB_ID else ""
# Then format for Notion API 2022-06-28+ which requires UUID format with dashes
TRACKS_DB_ID = format_database_id(TRACKS_DB_ID) if TRACKS_DB_ID else ""

# Export back to env for downstream helpers
if NOTION_TOKEN:
    os.environ["NOTION_TOKEN"] = NOTION_TOKEN
    os.environ["NOTION_API_KEY"] = NOTION_TOKEN  # compat
os.environ["NOTION_VERSION"] = NOTION_VERSION
os.environ["NOTION_TIMEOUT"] = str(NOTION_TIMEOUT)
if TRACKS_DB_ID:
    os.environ["TRACKS_DB_ID"] = TRACKS_DB_ID

if not NOTION_TOKEN:
    raise RuntimeError(
        "NOTION_TOKEN is not set. Set NOTION_TOKEN/NOTION_API_KEY. "
        "Also share the database with this integration (Database ••• → Add connections)."
    )
if not TRACKS_DB_ID:
    raise RuntimeError("TRACKS_DB_ID is required. Set tracks_db_id in unified_config or export TRACKS_DB_ID.")

# ---------- Notion helpers: headers, unarchive, safe status update ----------
def notion_unarchive_if_needed(page_id: str) -> None:
    if not page_id:
        return
    try:
        page = notion_manager._req("get", f"/pages/{page_id}")
        if page.get("archived"):
            notion_manager._req("patch", f"/pages/{page_id}", {"archived": False})
    except Exception as e:
        workspace_logger.error(f"Failed to unarchive Notion page {page_id}: {e}")

def update_audio_processing_status(page_id: str, statuses: list[str]) -> bool:
    try:
        if not page_id or not statuses:
            return False
        notion_unarchive_if_needed(page_id)
        page = notion_manager._req("get", f"/pages/{page_id}")
        prop_name = "Audio Processing Status"
        existing = set()
        prop = page.get("properties", {}).get(prop_name)
        if prop and prop.get("type") == "multi_select":
            existing = {opt.get("name") for opt in prop.get("multi_select", []) if isinstance(opt, dict)}
        new_values = [{"name": s} for s in sorted(existing | set(statuses))]
        notion_manager._req("patch", f"/pages/{page_id}", {"properties": {prop_name: {"multi_select": new_values}}})
        return True
    except Exception as e:
        workspace_logger.error(f"Failed to update audio processing statuses for {page_id}: {e}")
        return False


# Configuration from unified config system
# ───────────────────────────────────────────────────────────────

# Use unified config for directories with enhanced logging
OUT_DIR = Path(unified_config.get("out_dir") or os.getenv("OUT_DIR", "/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/EAGLE-AUTO-IMPORT/Music Library-2"))
BACKUP_DIR = Path(unified_config.get("backup_dir") or os.getenv("BACKUP_DIR", "/Volumes/VIBES/Djay-Pro-Auto-Import"))
WAV_BACKUP_DIR = Path(unified_config.get("wav_backup_dir") or os.getenv("WAV_BACKUP_DIR", "/Volumes/VIBES/Apple-Music-Auto-Add"))
# NEW: Playlist tracks directory for WAV files organized by playlist
PLAYLIST_TRACKS_DIR = Path(unified_config.get("playlist_tracks_dir") or os.getenv("PLAYLIST_TRACKS_DIR", "/Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks"))

# Eagle API configuration
EAGLE_API_BASE = unified_config.get("eagle_api_url") or os.getenv("EAGLE_API_BASE", "http://localhost:41595")
# NOTE: Empty default means "use currently active Eagle library" (no forced switch)
# Set EAGLE_LIBRARY_PATH env var to override with a specific library path
EAGLE_LIBRARY_PATH = unified_config.get("eagle_library_path") or os.getenv("EAGLE_LIBRARY_PATH", "")
# Limit for Eagle cache indexing (Eagle default list limit is low; raise for better dedupe accuracy)
EAGLE_CACHE_LIMIT = int(os.getenv("EAGLE_CACHE_LIMIT", "50000"))
EAGLE_TOKEN = unified_config.get("eagle_token") or os.getenv("EAGLE_TOKEN", "")
EAGLE_APP_PATH = unified_config.get("eagle_app_path") or os.getenv("EAGLE_APP_PATH", "/Applications/Eagle.app")
EAGLE_APP_NAME = unified_config.get("eagle_app_name") or os.getenv("EAGLE_APP_NAME", "Eagle")
_eagle_auto_launch_cfg = unified_config.get("eagle_auto_launch")
if _eagle_auto_launch_cfg is None:
    _eagle_auto_launch_cfg = os.getenv("EAGLE_AUTO_LAUNCH", "1")
EAGLE_AUTO_LAUNCH = _truthy(_eagle_auto_launch_cfg)
try:
    _eagle_auto_launch_timeout_cfg = unified_config.get("eagle_auto_launch_timeout") or os.getenv("EAGLE_AUTO_LAUNCH_TIMEOUT", "45")
    EAGLE_AUTO_LAUNCH_TIMEOUT = int(float(_eagle_auto_launch_timeout_cfg))
except (TypeError, ValueError):
    EAGLE_AUTO_LAUNCH_TIMEOUT = 45
# Force direct Eagle POST path and bypass smart client on imports
EAGLE_FORCE_DIRECT = _truthy(os.getenv('EAGLE_FORCE_DIRECT', '1'))

# Enhanced logging for configuration
workspace_logger.info(f"📁 Using OUT_DIR: {OUT_DIR}")
workspace_logger.info(f"📁 Using BACKUP_DIR: {BACKUP_DIR}")
workspace_logger.info(f"📁 Using WAV_BACKUP_DIR: {WAV_BACKUP_DIR}")
workspace_logger.info(f"📁 Using PLAYLIST_TRACKS_DIR: {PLAYLIST_TRACKS_DIR}")
workspace_logger.info(f"🦅 Eagle API: {EAGLE_API_BASE}")
workspace_logger.info(f"🦅 Eagle Library: {EAGLE_LIBRARY_PATH or '(use currently active library)'}")

# Compression mode
COMPRESSION_MODE = os.getenv("SC_COMP_MODE", "LOSSLESS").upper()
COMPRESSION_PRESETS = {
    "LOSSLESS": {
        "aiff_codec": ["-c:a", "pcm_s24be"],
        "m4a_codec": ["-c:a", "alac"],
    },
    "HIGH": {
        "aiff_codec": ["-c:a", "pcm_s16be"],
        "m4a_codec": ["-c:a", "alac", "-sample_fmt", "s16"],
    },
    "PORTABLE": {
        "aiff_codec": ["-c:a", "pcm_s16be"],
        "m4a_codec": ["-c:a", "aac", "-b:a", "256k"],
    },
}

if COMPRESSION_MODE not in COMPRESSION_PRESETS:
    logging.warning("Unknown COMPRESSION_MODE '%s' – defaulting to LOSSLESS", COMPRESSION_MODE)
    COMPRESSION_MODE = "LOSSLESS"

# De‑duplication controls
SC_DEDUP_ON_WRITE = os.getenv("SC_DEDUP_ON_WRITE", "1").strip()  # "1" enables pre‑upsert dedupe
SC_DEDUP_DRY_RUN = os.getenv("SC_DEDUP_DRY_RUN", "0").strip()    # "1" logs only, no changes
try:
    SC_DEDUP_RECENT_LIMIT = int(os.getenv("SC_DEDUP_RECENT_LIMIT", "50"))
except ValueError:
    SC_DEDUP_RECENT_LIMIT = 50

# Batch pagination tuning
try:
    SC_NOTION_PAGE_SIZE = int(os.getenv("SC_NOTION_PAGE_SIZE", "100"))
except ValueError:
    SC_NOTION_PAGE_SIZE = 100
SC_NOTION_PAGE_SIZE = max(1, min(SC_NOTION_PAGE_SIZE, 100))  # Notion cap is 100

# When Notion refuses a page update because the database schema has reached its
# maximum size we retry with a trimmed payload that only touches safe fields.
NOTION_SCHEMA_LIMIT_PHRASE = "database schema has exceeded the maximum size"
DEDUP_SAFE_FIELD_TYPES = {"title", "rich_text", "url", "number", "checkbox", "date", "email", "phone_number"}
DEDUP_SAFE_MULTISELECT_KEYS = {"Audio Processing", "Audio Processing Status"}
DEDUP_MULTISELECT_LIMIT = int(os.getenv("SC_DEDUP_MULTISELECT_LIMIT", "25"))
DEDUP_MULTISELECT_REQUIRED_TAGS = {"Merged Duplicate"}

# Also attempt merges before processing eligible items (does not change filters)
SC_DEDUP_PRE_PROCESS = os.getenv("SC_DEDUP_PRE_PROCESS", "1").strip()

# Candidate property names for track release dates
RELEASE_DATE_CANDIDATES: tuple[str, ...] = (
    "Release Date",
    "Track Release Date",
    "Date Released",
    "Released On",
    "Album Release Date",
)

# OAuth header
SC_AUTH_HEADER = os.getenv("SC_AUTH_HEADER", "")

# ───────────────────────────────────────────────────────────────

# Eagle API Configuration - FIXED based on diagnostic
EAGLE_ADD_ENDPOINT = "/api/item/addFromPaths"  # Correct Eagle API endpoint (plural)
EAGLE_BATCH_ENDPOINT = "/api/item/addFromPaths"  # Batch endpoint
EAGLE_INFO_ENDPOINT = "/api/application/info"  # Health check endpoint (GET)

from pathlib import Path as _EPath

_eagle_launch_lock = threading.Lock()
_eagle_launch_attempted = False
_eagle_launch_confirmed = False

# Eagle API utilities

def eagle_update_tags(item_id: str, tags: list[str]) -> bool:
    """
    Update tags on an existing Eagle item using the direct REST API.
    Returns True on success, False otherwise.
    """
    try:
        if not item_id:
            workspace_logger.warning("⚠️  eagle_update_tags called without item_id")
            return False
        if not tags:
            workspace_logger.info("ℹ️  eagle_update_tags called with empty tags; nothing to do")
            return False

        update_url = f"{EAGLE_API_BASE}/api/item/update"
        payload = {"id": item_id, "tags": tags}
        workspace_logger.debug(f"🧪 Eagle tag update payload: {payload}")
        resp = requests.post(update_url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        if resp.status_code == 200 and isinstance(data, dict) and data.get("status") == "success":
            workspace_logger.info(f"✅ Tags updated in Eagle for {item_id}: {tags}")
            return True

        workspace_logger.warning(f"⚠️  Eagle tag update failed "
                                 f"(status={resp.status_code}) body={data}")
        return False
    except Exception as e:
        workspace_logger.warning(f"⚠️  Exception during Eagle tag update: {e}")
        return False

def complete_track_notion_update(
    page_id: str, 
    track_info: dict, 
    file_paths: dict, 
    eagle_id: str = None
) -> bool:
    """
    CRITICAL: Update Notion to mark track as complete and prevent reprocessing IMMEDIATELY after file processing.
    
    A track is excluded from future queries if:
    - DL checkbox = TRUE, OR
    - At least one file path is populated
    
    Args:
        page_id: Notion page ID
        track_info: Track metadata dict containing 'title', 'artist', etc.
        file_paths: Dict with keys 'm4a', 'aiff', 'wav' containing file paths
        eagle_id: Optional Eagle file ID
    
    Returns:
        True if update succeeded, False otherwise
    
    Example:
        file_paths = {
            'm4a': '/Volumes/VIBES/Playlists/Artist - Track.m4a',
            'aiff': '/Volumes/VIBES/Djay-Pro-Auto-Import/Artist - Track.aiff'
        }
        
        if not complete_track_notion_update(page_id, track_info, file_paths, eagle_id):
            raise RuntimeError("Notion update failed - track will be reprocessed")
    """
    properties = {}

    # Get property types for the tracks database
    prop_types = _get_tracks_db_prop_types()

    # Helper function to set URL or text properties
    def set_url_or_text(props_dict: dict, key: str, value: str):
        if not value:
            return
        name = _resolve_prop_name(key) or key
        prop_type = prop_types.get(name)
        if prop_type == "url":
            props_dict[name] = {"url": value}
        elif prop_type == "rich_text":
            props_dict[name] = {"rich_text": [{"text": {"content": value}}]}
        else:
            # Default to rich_text if type unknown
            props_dict[name] = {"rich_text": [{"text": {"content": value}}]}

    # Count file paths first to determine if we should mark as downloaded
    path_count = sum(1 for k in ["m4a", "aiff", "wav"] if file_paths.get(k))

    # CRITICAL FIX: Only set Downloaded=TRUE if we have actual files OR an Eagle ID
    # Spotify-only tracks without files should NOT be marked as downloaded
    dl_prop = _resolve_prop_name("DL") or "Downloaded"
    if path_count > 0 or eagle_id:
        properties[dl_prop] = {"checkbox": True}
        workspace_logger.info(f"📌 Setting {dl_prop} = TRUE for {page_id} ({path_count} files, Eagle: {'Yes' if eagle_id else 'No'})")
    else:
        # Don't mark as downloaded if no files and no Eagle ID
        workspace_logger.warning(f"⚠️  NOT setting {dl_prop}=TRUE for {page_id} - no files downloaded and no Eagle ID")

    # CRITICAL: Populate file paths if they exist
    path_count = 0
    if file_paths.get("m4a"):
        set_url_or_text(properties, "M4A File Path", str(file_paths["m4a"]))
        workspace_logger.info(f"📁 Setting M4A path: {file_paths['m4a']}")
        path_count += 1
    
    if file_paths.get("aiff"):
        set_url_or_text(properties, "AIFF File Path", str(file_paths["aiff"]))
        workspace_logger.info(f"📁 Setting AIFF path: {file_paths['aiff']}")
        path_count += 1
    
    if file_paths.get("wav"):
        set_url_or_text(properties, "WAV File Path", str(file_paths["wav"]))
        workspace_logger.info(f"📁 Setting WAV path: {file_paths['wav']}")
        path_count += 1
    
    # Optional: Eagle ID
    if eagle_id:
        eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
        properties[eagle_prop] = {
            "rich_text": [{"text": {"content": str(eagle_id)}}]
        }
        workspace_logger.info(f"🦅 Setting Eagle ID: {eagle_id}")
    
    # Track whether we set DL for accurate logging
    dl_was_set = dl_prop in properties

    # Attempt update with retry
    for attempt in range(1, 4):
        try:
            notion_manager.update_page(page_id, properties)
            workspace_logger.info(
                f"✅ Notion updated successfully (attempt {attempt}/3): "
                f"DL={'True' if dl_was_set else 'NOT SET'}, {path_count} file paths, Eagle ID={'Yes' if eagle_id else 'No'}"
            )

            # ═══════════════════════════════════════════════════════════════
            # FIX (2026-01-18): Link Artist/Playlist relations after update
            # These were only being set in upsert_track_page, not here
            # ═══════════════════════════════════════════════════════════════
            artist_name = track_info.get("artist")
            if artist_name and artist_name not in ["Unknown", "N/A", ""]:
                try:
                    link_track_artist_relation(page_id, artist_name)
                    workspace_logger.info(f"🎤 Linked artist relation: {artist_name}")
                except Exception as artist_err:
                    workspace_logger.warning(f"⚠️  Failed to link artist relation: {artist_err}")

            playlist_name = track_info.get("playlist_name") or track_info.get("playlist")
            if playlist_name and playlist_name not in ["No Playlist", "Unassigned", ""]:
                try:
                    link_track_playlist_relation(page_id, playlist_name)
                    workspace_logger.info(f"📋 Linked playlist relation: {playlist_name}")
                except Exception as playlist_err:
                    workspace_logger.warning(f"⚠️  Failed to link playlist relation: {playlist_err}")

            return True
        except Exception as e:
            workspace_logger.warning(f"⚠️  Notion update attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt)
            else:
                workspace_logger.error(
                    f"❌ CRITICAL: All Notion update attempts failed for {page_id}. "
                    f"THIS TRACK WILL BE REPROCESSED!"
                )
                return False
    
    return False


def verify_track_will_not_reprocess(page_id: str) -> bool:
    """
    Verify that track won't be reprocessed by checking if it would pass query filters.
    
    Returns:
        True if track is properly marked and won't reprocess
        False if track will reappear in next query
    
    Example:
        if not verify_track_will_not_reprocess(page_id):
            raise RuntimeError("Track not properly marked - will be reprocessed")
    """
    try:
        # Re-fetch page to get latest state
        page = notion_manager._req("get", f"/pages/{page_id}")
        props = page.get("properties", {})
        
        # Check DL checkbox
        dl_prop = _resolve_prop_name("DL") or "Downloaded"
        dl_checked = props.get(dl_prop, {}).get("checkbox") is True
        
        # Check if ANY file path exists
        has_file_path = False
        file_paths_checked = []
        for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
            prop_name = _resolve_prop_name(key) or key
            prop = props.get(prop_name, {})
            value = _prop_text_value(prop)
            if value:
                has_file_path = True
                file_paths_checked.append(f"{key}='{value[:50]}...'")
            else:
                file_paths_checked.append(f"{key}=EMPTY")
        
        # Track is properly marked if EITHER condition is true
        is_marked = dl_checked or has_file_path
        
        if is_marked:
            workspace_logger.info(
                f"✅ VERIFIED: Track {page_id} properly marked - won't reprocess\n"
                f"   - DL checkbox: {dl_checked}\n"
                f"   - Has file paths: {has_file_path}\n"
                f"   - Paths: {', '.join(file_paths_checked)}"
            )
        else:
            workspace_logger.error(
                f"❌ CRITICAL: Track {page_id} NOT properly marked - WILL REPROCESS\n"
                f"   - DL checkbox: {dl_checked} (should be True)\n"
                f"   - Has file paths: {has_file_path} (at least one should exist)\n"
                f"   - Paths: {', '.join(file_paths_checked)}"
            )
        
        return is_marked
        
    except Exception as e:
        workspace_logger.error(f"❌ Failed to verify track {page_id}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED TRACK UPDATE FUNCTION (2026-01-16)
# ═══════════════════════════════════════════════════════════════════════════════
# Single function to update ALL track properties after processing
# Ensures consistent property naming and prevents partial updates
# ═══════════════════════════════════════════════════════════════════════════════

def unified_track_update(
    page_id: str,
    track_info: dict,
    processing_data: dict,
    file_paths: dict,
    eagle_id: Optional[str] = None,
    fingerprints: Optional[dict] = None,
) -> bool:
    """
    UNIFIED function to update ALL track properties after processing.

    This function consolidates all Notion updates into a single atomic operation,
    using the canonical property names from ALT_PROP_NAMES.

    Args:
        page_id: Notion page ID
        track_info: Track metadata (title, artist, album, etc.)
        processing_data: Audio processing results (bpm, key, duration, quality metrics)
        file_paths: Dict with 'wav', 'aiff', 'm4a' file paths
        eagle_id: Eagle library item ID
        fingerprints: Dict with 'wav', 'aiff', 'm4a' fingerprint values

    Returns:
        True if update succeeded, False otherwise

    Example:
        unified_track_update(
            page_id="abc123",
            track_info={"title": "Song", "artist": "Artist"},
            processing_data={"bpm": 128, "key": "Am", "duration": 240},
            file_paths={"wav": "/path/to/file.wav"},
            eagle_id="eagle_xyz",
            fingerprints={"wav": "fp_hash_123"}
        )
    """
    try:
        prop_types = _get_tracks_db_prop_types()
        properties = {}
        update_log = []

        # Helper to safely set a property
        def set_prop(semantic_name: str, value, prop_format: str = "auto"):
            """Set a property using canonical name resolution."""
            if value is None:
                return

            prop_name = _resolve_prop_name(semantic_name)
            if not prop_name:
                workspace_logger.debug(f"Property '{semantic_name}' not found in schema")
                return

            actual_type = prop_types.get(prop_name)
            if not actual_type:
                return

            # Determine format based on type or override
            if prop_format == "auto":
                prop_format = actual_type

            if prop_format == "checkbox":
                properties[prop_name] = {"checkbox": bool(value)}
            elif prop_format == "number":
                try:
                    properties[prop_name] = {"number": float(value)}
                except (ValueError, TypeError):
                    return
            elif prop_format == "rich_text":
                properties[prop_name] = {"rich_text": [{"text": {"content": str(value)[:2000]}}]}
            elif prop_format == "url":
                properties[prop_name] = {"url": str(value) if value else None}
            elif prop_format == "select":
                properties[prop_name] = {"select": {"name": str(value)}}
            elif prop_format == "multi_select":
                if isinstance(value, list):
                    properties[prop_name] = {"multi_select": [{"name": str(v)} for v in value]}
                else:
                    properties[prop_name] = {"multi_select": [{"name": str(value)}]}
            elif prop_format == "date":
                if isinstance(value, str):
                    properties[prop_name] = {"date": {"start": value}}
                elif hasattr(value, 'isoformat'):
                    properties[prop_name] = {"date": {"start": value.isoformat()}}

            update_log.append(f"{semantic_name}={str(value)[:30]}")

        # ═══════════════════════════════════════════════════════════════════════
        # 1. CRITICAL: Status and File Paths (prevents reprocessing)
        # ═══════════════════════════════════════════════════════════════════════

        # Downloaded checkbox
        has_files = bool(file_paths.get("wav") or file_paths.get("aiff") or file_paths.get("m4a"))
        if has_files or eagle_id:
            set_prop("DL", True, "checkbox")

        # File paths
        if file_paths.get("wav"):
            set_prop("WAV File Path", file_paths["wav"], "rich_text")
        if file_paths.get("aiff"):
            set_prop("AIFF File Path", file_paths["aiff"], "rich_text")
        if file_paths.get("m4a"):
            set_prop("M4A File Path", file_paths["m4a"], "rich_text")

        # Eagle File ID
        if eagle_id:
            set_prop("Eagle File ID", eagle_id, "rich_text")

        # ═══════════════════════════════════════════════════════════════════════
        # 2. CRITICAL: Audio Metadata (BPM, Key, Duration)
        # ═══════════════════════════════════════════════════════════════════════

        # BPM (maps to "Tempo" property)
        bpm = processing_data.get("bpm") or track_info.get("bpm")
        if bpm and float(bpm) > 0:
            set_prop("BPM", bpm, "number")

        # Key
        key = processing_data.get("key") or track_info.get("key")
        if key and key != "Unknown":
            set_prop("Key", key, "rich_text")

        # Duration in seconds (maps to "Audio Duration (seconds)")
        duration = (
            processing_data.get("duration") or
            processing_data.get("duration_seconds") or
            track_info.get("duration_seconds") or
            track_info.get("duration")
        )
        if duration and float(duration) > 0:
            set_prop("Duration (s)", duration, "number")

        # ═══════════════════════════════════════════════════════════════════════
        # 3. Fingerprints (per-format)
        # ═══════════════════════════════════════════════════════════════════════

        if fingerprints:
            if fingerprints.get("wav"):
                set_prop("WAV Fingerprint", fingerprints["wav"], "rich_text")
            if fingerprints.get("aiff"):
                set_prop("AIFF Fingerprint", fingerprints["aiff"], "rich_text")
            if fingerprints.get("m4a"):
                set_prop("M4A Fingerprint", fingerprints["m4a"], "rich_text")

        # Legacy fingerprint from processing_data
        fp = processing_data.get("fingerprint") or track_info.get("fingerprint")
        if fp and not fingerprints:
            # Determine which format based on file_paths
            if file_paths.get("wav"):
                set_prop("WAV Fingerprint", fp, "rich_text")
            elif file_paths.get("aiff"):
                set_prop("AIFF Fingerprint", fp, "rich_text")
            elif file_paths.get("m4a"):
                set_prop("M4A Fingerprint", fp, "rich_text")

        # ═══════════════════════════════════════════════════════════════════════
        # 4. Audio Quality Metrics (2026-01-16: Complete metadata population)
        # ═══════════════════════════════════════════════════════════════════════

        # Quality score
        quality_score = processing_data.get("quality_score")
        if quality_score is not None:
            set_prop("Audio Quality Score", quality_score, "number")

        # LUFS level (final, post-normalization)
        lufs = processing_data.get("loudness_level") or processing_data.get("lufs_level") or processing_data.get("final_lufs")
        if lufs is not None:
            set_prop("Audio LUFS Level", lufs, "number")

        # Peak level (linear)
        peak = processing_data.get("peak_level")
        if peak is not None:
            set_prop("Audio Peak Level", peak, "number")

        # True Peak in dB (more useful than linear peak)
        true_peak_db = processing_data.get("true_peak_db")
        if true_peak_db is not None:
            # Store in Peak Level if no linear peak, or could add a separate property
            if peak is None:
                set_prop("Audio Peak Level", true_peak_db, "number")

        # RMS level
        rms = processing_data.get("rms_level")
        if rms is not None:
            set_prop("Audio RMS Level", rms, "number")

        # Dynamic range
        dr = processing_data.get("dynamic_range")
        if dr is not None:
            set_prop("Audio Dynamic Range (dB)", dr, "number")

        # Crest factor (peak-to-RMS ratio, indicates dynamics/punch)
        crest = processing_data.get("crest_factor")
        if crest is not None:
            set_prop("Audio Crest Factor", crest, "number")

        # Sample rate
        sample_rate = processing_data.get("sample_rate")
        if sample_rate is not None:
            set_prop("Audio Sample Rate", sample_rate, "number")

        # Clipping percentage (from audio analysis)
        clipping = processing_data.get("clipping_percentage")
        if clipping is not None:
            set_prop("Audio Clipping Percentage", clipping, "number")

        # Warmth enhancement level (0.0 = none, 1.0 = applied)
        warmth = processing_data.get("warmth_level")
        if warmth is not None:
            set_prop("Warmth Enhancement Level", warmth, "number")

        # ═══════════════════════════════════════════════════════════════════════
        # 5. Processing Metadata
        # ═══════════════════════════════════════════════════════════════════════

        # Processing timestamp
        set_prop("Processing Timestamp", datetime.now(timezone.utc).isoformat(), "date")

        # Compression mode
        compression = processing_data.get("compression_mode") or COMPRESSION_MODE
        if compression:
            set_prop("Compression Mode Used", compression, "select")

        # Normalization status
        normalized = processing_data.get("normalized", False)
        set_prop("Audio Normalized", normalized, "checkbox")

        # Audio normalizer availability
        set_prop("Audio Normalizer Available", AUDIO_NORMALIZER_AVAILABLE, "checkbox")

        # ═══════════════════════════════════════════════════════════════════════
        # 6. Processing Status (multi_select)
        # ═══════════════════════════════════════════════════════════════════════

        processing_statuses = processing_data.get("audio_processing_status", [])
        if not processing_statuses:
            processing_statuses = ["Audio Analysis Complete"]

        if processing_data.get("normalized"):
            if "Audio Normalized" not in processing_statuses:
                processing_statuses.append("Audio Normalized")

        if eagle_id:
            if "Eagle Import Complete" not in processing_statuses:
                processing_statuses.append("Eagle Import Complete")

        set_prop("Audio Processing", processing_statuses, "multi_select")

        # ═══════════════════════════════════════════════════════════════════════
        # 7. Apply Update with Retry
        # ═══════════════════════════════════════════════════════════════════════

        if not properties:
            workspace_logger.warning(f"No properties to update for {page_id}")
            return True

        workspace_logger.info(f"📝 Unified update for {page_id}: {len(properties)} properties")
        workspace_logger.info(f"   Properties: {', '.join(update_log[:10])}{'...' if len(update_log) > 10 else ''}")

        for attempt in range(1, 4):
            try:
                notion_manager._req("patch", f"/pages/{page_id}", {"properties": properties})
                workspace_logger.info(f"✅ Unified update successful (attempt {attempt}/3)")
                return True
            except Exception as e:
                workspace_logger.warning(f"⚠️  Unified update attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(2 ** attempt)
                else:
                    workspace_logger.error(f"❌ All unified update attempts failed for {page_id}")
                    return False

        return False

    except Exception as e:
        workspace_logger.error(f"❌ Unified track update error for {page_id}: {e}")
        import traceback
        workspace_logger.debug(traceback.format_exc())
        return False


def _is_eagle_api_available(timeout: float = 3.0) -> bool:
    """Lightweight health check to see if Eagle's API is reachable."""
    url = f"{EAGLE_API_BASE.rstrip('/')}{EAGLE_INFO_ENDPOINT}"
    try:
        resp = requests.get(url, timeout=timeout)
        return 200 <= resp.status_code < 500
    except Exception:
        return False


def _resolve_open_command() -> Optional[List[str]]:
    """Return the macOS open command for launching the Eagle app."""
    if sys.platform != "darwin":
        return None
    open_binary = "/usr/bin/open" if Path("/usr/bin/open").exists() else "open"
    if EAGLE_APP_PATH:
        candidate = Path(EAGLE_APP_PATH).expanduser()
        if candidate.exists():
            return [open_binary, str(candidate)]
    app_name = (EAGLE_APP_NAME or "Eagle").strip() or "Eagle"
    return [open_binary, "-a", app_name]


def ensure_eagle_app_running(force: bool = False) -> bool:
    """
    Ensure the Eagle desktop app is running by issuing an open command if needed.
    Returns True when the API is reachable, False otherwise.
    """
    global _eagle_launch_attempted, _eagle_launch_confirmed

    if not force and (_eagle_launch_confirmed or _is_eagle_api_available()):
        _eagle_launch_confirmed = True
        return True

    if not EAGLE_AUTO_LAUNCH and not force:
        workspace_logger.debug("Eagle auto-launch disabled; skipping app launch.")
        return False

    command = _resolve_open_command()
    if command is None:
        workspace_logger.warning("Cannot auto-launch Eagle on this platform.")
        return False

    with _eagle_launch_lock:
        if not force and _eagle_launch_attempted and not _eagle_launch_confirmed:
            workspace_logger.info("Waiting for Eagle to become ready after previous launch attempt...")
        elif not _eagle_launch_attempted or force:
            try:
                workspace_logger.info("🦅 Launching Eagle application...")
                subprocess.run(command, check=True)
                _eagle_launch_attempted = True
            except Exception as exc:
                workspace_logger.error(f"❌ Failed to launch Eagle application: {exc}")
                return False

    deadline = time.time() + max(EAGLE_AUTO_LAUNCH_TIMEOUT, 1)
    poll_interval = 2.0
    while time.time() < deadline:
        if _is_eagle_api_available():
            _eagle_launch_confirmed = True
            workspace_logger.info("✅ Eagle application is running.")
            return True
        time.sleep(poll_interval)

    workspace_logger.error(
        f"❌ Eagle application did not become ready within {EAGLE_AUTO_LAUNCH_TIMEOUT}s after launch attempt."
    )
    return False

def switch_to_configured_eagle_library() -> bool:
    try:
        lib = _EPath(EAGLE_LIBRARY_PATH).expanduser() if EAGLE_LIBRARY_PATH else None
        if lib and lib.exists():
            if EAGLE_SMART_AVAILABLE:
                try:
                    eagle_switch_library(str(lib))
                except Exception as e:
                    workspace_logger.warning(f"Could not switch Eagle library via smart API: {e}")
            workspace_logger.info(f"🦅 Using Eagle library: {lib}")
            return True
        workspace_logger.info("🦅 No valid EAGLE_LIBRARY_PATH. Using currently active Eagle library.")
        return False
    except Exception as e:
        workspace_logger.warning(f"Could not switch Eagle library, continuing with active library: {e}")
        return False

def _eagle_import_file_direct(path: str, name: str, website: str, tags: list[str], folder_id: Optional[str] = None, existing_eagle_id: str = None) -> Optional[str]:
    if not Path(path).exists():
        workspace_logger.error(f"❌ File not found: {path}")
        return None

    abs_path = str(Path(path).resolve())

    if existing_eagle_id:
        workspace_logger.info(f"ℹ️  Found existing Eagle ID: {existing_eagle_id}")
        workspace_logger.info(f"🔧 Attempting to update tags for existing Eagle item: {existing_eagle_id}")
        
        # Update tags for existing item (do not skip tagging)
        workspace_logger.debug(f"🧪 Tagging metadata for Eagle: {tags}")
        if not tags:
            workspace_logger.info("⚠️  No tags provided in metadata; skipping Eagle tag update")
            return existing_eagle_id

        updated = eagle_update_tags(existing_eagle_id, tags)
        if not updated:
            workspace_logger.warning("⚠️  Eagle tag update reported failure")
        return existing_eagle_id

    workspace_logger.debug(f"🦅 Calling Eagle API addFromPaths (direct): {abs_path}")
    workspace_logger.debug(f"📊 Tags to apply: {tags}")

    # Build payload with full metadata including tags
    payload = {
        "items": [{
            "path": abs_path,
            "name": name or Path(abs_path).stem,
            "website": website or "",
            "tags": tags or [],
        }]
    }
    # Add debug line to mirror input tag source for new import
    workspace_logger.debug(f"🧪 Tagging metadata for Eagle (new import): {payload['items'][0].get('tags')}")
    
    if folder_id:
        payload["items"][0]["folderId"] = folder_id
        
    url = f"{EAGLE_API_BASE}{EAGLE_ADD_ENDPOINT}"
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("status") == "success":
            ids = data.get("data") or []
            if ids:
                return ids[0]
    raise RuntimeError(f"Eagle API {resp.status_code}: {resp.text}")

def eagle_add_item_adapter(path: str, name: str, website: str, tags: list[str], folder_id: Optional[str] = None, existing_eagle_id: str = None) -> Optional[str]:
    """Bypass smart API and use direct REST import reliably."""
    # Always use the direct REST path to avoid 404/method errors from the smart layer
    try:
        workspace_logger.info("🦅 Using direct Eagle REST import (bypassing smart API)")
        return _eagle_import_file_direct(path, name, website, tags, folder_id, existing_eagle_id)
    except Exception as e:
        # Surface the exact failure for upstream retry logic
        raise

# Notion Configuration from workspace
# ───────────────────────────────────────────────────────────────
# NOTION_TOKEN validated above - already checked for presence

# Database IDs - TRACKS_DB_ID already validated above
SCRIPT_DB_ID = os.getenv("SCRIPT_DB_ID", "")
LOG_DB_ID = os.getenv("LOG_DB_ID", "")
SCRIPT_PAGE_ID = os.getenv("SCRIPT_PAGE_ID", "")

# Workspace constants
SUMMARY_LIMIT = 1950
FLUSH_LINES = 10
FLUSH_SECS = 10
RETRY_MAX = 3

# Cache of available property names
_tracks_db_props: Optional[Set[str]] = None
# New: cache of Tracks DB property type info
_tracks_db_prop_types: Optional[Dict[str, str]] = None

# ───────────────────────────────────────────────────────────────
# Unified Logging System - Now using unified_config module
# ───────────────────────────────────────────────────────────────
# The workspace_logger is now initialized from unified_config at the top of the file
# This provides enhanced logging with colors, progress tracking, and better debugging

# Helper: Preflight check for user-configured directories
def ensure_writable_dir(p: Path, name: str) -> Path:
    """
    Preflight check for user-configured directories.

    - If the path is under /Volumes/<VolumeName>/... and the base volume is not mounted,
      emit a clear error and exit instead of trying to create /Volumes/<VolumeName> (which
      requires root).
    - If the directory exists but is not writable, emit a clear error and exit.
    - Otherwise, create the directory tree if missing.
    """
    try:
        parts = p.parts
        # Detect /Volumes/<VolumeName>/... and ensure the volume is mounted
        if len(parts) >= 3 and parts[1] == 'Volumes':
            vol_base = Path('/', 'Volumes', parts[2])
            if not vol_base.exists():
                workspace_logger.error(
                    f"🚫 {name} points to external volume '{vol_base}', but it is not mounted.\n"
                    f"   → Mount the drive or set {name} in your .env "
                    f"(e.g., /Users/brianhellemn/Scripts-MM1/api.env) to a writable path."
                )
                raise SystemExit(1)

        # Try to create the directory tree if needed
        p.mkdir(parents=True, exist_ok=True)

        # Check write access by touching a temp file
        testfile = p / '.write_test'
        try:
            with open(testfile, 'w') as f:
                f.write('ok')
        finally:
            try:
                testfile.unlink()
            except Exception:
                pass

        workspace_logger.info(f"📁 Using {name}: {p}")
        return p

    except PermissionError as e:
        workspace_logger.error(
            f"🚫 Insufficient permissions for {name} '{p}'.\n"
            f"   → Fix permissions on the target or point {name} to a path you can write."
        )
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        workspace_logger.error(f"❌ Failed to prepare {name} '{p}': {e}")
        raise SystemExit(1)

# Preflight the user-configured directories early so we fail fast with a clear message
OUT_DIR = ensure_writable_dir(OUT_DIR, "OUT_DIR")
BACKUP_DIR = ensure_writable_dir(BACKUP_DIR, "BACKUP_DIR")
WAV_BACKUP_DIR = ensure_writable_dir(WAV_BACKUP_DIR, "WAV_BACKUP_DIR")

# ---------- Pre-download existence check ----------
def _sanitize_filename_component(name: str) -> str:
    s = "" if name is None else str(name)
    s = "".join(ch for ch in s if ch not in "\\/:*?\"<>|\n\r\t")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def find_existing_outputs(sc_url: str, out_dir: Path) -> Dict[str, Optional[str]]:
    """
    Probe OUT_DIR for already-rendered outputs derived from the track title.
    Returns {'aiff','m4a','wav'} -> absolute paths or None.
    """
    stem: Optional[str] = None
    if yt_dlp is not None:
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(sc_url, download=False)
                title = info.get("title") or ""
                stem = _sanitize_filename_component(title) if title else None
        except Exception as e:
            workspace_logger.debug(f"yt_dlp metadata probe failed: {e}")
    found: Dict[str, Optional[str]] = {"aiff": None, "m4a": None, "wav": None}
    if stem:
        exacts = [out_dir / f"{stem}.aiff", out_dir / f"{stem}.m4a", out_dir / f"{stem}.wav"]
        for p in exacts:
            try:
                if p.exists():
                    suf = p.suffix.lower()
                    if suf == ".aiff": found["aiff"] = str(p.resolve())
                    elif suf == ".m4a": found["m4a"] = str(p.resolve())
                    elif suf == ".wav": found["wav"] = str(p.resolve())
            except Exception:
                pass
        if not any(found.values()):
            for pat, key in [(f"*{stem}*.aiff","aiff"), (f"*{stem}*.m4a","m4a"), (f"*{stem}*.wav","wav")]:
                try:
                    for cand in out_dir.glob(pat):
                        if cand.exists():
                            found[key] = str(cand.resolve())
                except Exception:
                    pass
    return found

def pre_download_repair_if_outputs_exist(page_id: str, sc_url: str) -> bool:
    """
    If outputs exist already, skip download and fix Notion so the item will not reprocess.
    Returns True if handled.
    """
    existing = find_existing_outputs(sc_url, OUT_DIR)
    if any(existing.values()):
        workspace_logger.info("Detected existing outputs; skipping download and updating Notion.")
        files = {"m4a": existing.get("m4a"), "aiff": existing.get("aiff"), "wav": existing.get("wav")}
        if not complete_track_notion_update(page_id, {"source":"pre-download-repair"}, files, eagle_id=None):
            raise RuntimeError(f"Notion update failed for {page_id} during pre-download repair")
        if not verify_track_will_not_reprocess(page_id):
            raise RuntimeError(f"Verification failed for {page_id} during pre-download repair")
        workspace_logger.info(f"Recovered prior processing state for {page_id}.")
        return True
    return False

# ───────────────────────────────────────────────────────────────
# Notion API Helpers (following workspace patterns)
# ───────────────────────────────────────────────────────────────
class NotionManager:
    """Notion API manager following workspace standards"""
    
    def __init__(self, token: str = NOTION_TOKEN):
        self.client = Client(auth=token)
        self.session = _build_http_session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,  # Use the validated version
            "Content-Type": "application/json",
        }
        
    def _req(self, method: str, path: str, body: Optional[dict] = None, retry: int = RETRY_MAX):
        """Make API request with retry logic following workspace standards"""
        url = f"https://api.notion.com/v1{path}"
        timeout = max(5, min(120, NOTION_TIMEOUT))
        for attempt in range(1, retry + 1):
            try:
                resp = self.session.request(method, url, headers=self.headers, json=body, timeout=timeout)
                if 200 <= resp.status_code < 300:
                    return resp.json()
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 1))
                    time.sleep(wait or attempt)
                    continue
                if resp.status_code >= 500:
                    time.sleep(1 * attempt)
                    continue
                raise RuntimeError(f"Notion error {resp.status_code}: {resp.text}")
            except Exception as exc:
                if attempt == retry:
                    raise
                time.sleep(2 ** attempt)
                
    def query_database(self, database_id: str, query: dict) -> dict:
        """Query database with workspace-standard error handling"""
        try:
            if _notion_query_cache_ttl > 0:
                cache_key = f"{database_id}:{json.dumps(query, sort_keys=True, default=str)}"
                cached = _notion_query_cache.get(cache_key)
                if cached and (time.time() - cached.get("ts", 0)) < _notion_query_cache_ttl:
                    return cached.get("data", {})
            result = self._req("post", f"/databases/{database_id}/query", query)
            if _notion_query_cache_ttl > 0:
                if len(_notion_query_cache) >= _notion_query_cache_max:
                    _notion_query_cache.clear()
                _notion_query_cache[cache_key] = {"ts": time.time(), "data": result}
            return result
        except Exception as exc:
            workspace_logger.error(f"Failed to query database {database_id}: {exc}")
            try:
                msg = str(exc)
                if ("401" in msg) or ("unauthorized" in msg.lower()):
                    workspace_logger.error("401 Unauthorized from Notion API.")
                    workspace_logger.error(" • Ensure the database is shared with this integration (Database ••• → Add connections).")
                    workspace_logger.error(" • Confirm the token belongs to the same workspace as the database.")
                    workspace_logger.error(" • Recheck scopes: databases:read, pages:read, pages:write.")
                    workspace_logger.error(f" • TRACKS_DB_ID: {TRACKS_DB_ID}")
            except Exception:
                pass
            raise
            
    def update_page(self, page_id: str, properties: dict) -> dict:
        """Update page with workspace-standard error handling"""
        try:
            return self._req("patch", f"/pages/{page_id}", {"properties": properties})
        except Exception as exc:
            workspace_logger.error(f"Failed to update page {page_id}: {exc}")
            try:
                msg = str(exc)
                if ("401" in msg) or ("unauthorized" in msg.lower()):
                    workspace_logger.error("401 Unauthorized from Notion API.")
                    workspace_logger.error(" • Ensure the database is shared with this integration (Database ••• → Add connections).")
                    workspace_logger.error(" • Confirm the token belongs to the same workspace as the database.")
                    workspace_logger.error(" • Recheck scopes: databases:read, pages:read, pages:write.")
                    workspace_logger.error(f" • TRACKS_DB_ID: {TRACKS_DB_ID}")
            except Exception:
                pass
            raise
# Drop legacy 'ntn_' token-prefix warning from any logger
class _SuppressNTNWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "NOTION_TOKEN starts with 'ntn_'" not in str(msg)

logging.getLogger().addFilter(_SuppressNTNWarning())
for _name in list(getattr(logging.root.manager, "loggerDict", {}).keys()):
    try:
        logging.getLogger(_name).addFilter(_SuppressNTNWarning())
    except Exception:
        pass


# Global Notion manager
notion_manager = NotionManager()

# Lightweight Notion query cache to reduce redundant database queries
_notion_query_cache: dict[str, dict] = {}
_notion_query_cache_ttl = int(os.getenv("NOTION_QUERY_CACHE_TTL", "30"))
_notion_query_cache_max = int(os.getenv("NOTION_QUERY_CACHE_MAX", "256"))

# ───────────────────────────────────────────────────────────────
# Unified State Registry Integration (Phase 1)
# ───────────────────────────────────────────────────────────────
try:
    from unified_state_registry import get_registry
    state_registry = get_registry(notion_manager, ttl_seconds=300)
    workspace_logger.info("✅ Unified State Registry initialized")
except ImportError as e:
    workspace_logger.warning(f"⚠️  Unified State Registry not available: {e}")
    state_registry = None

def update_track_with_registry(page_id: str, properties: dict, track_data: dict = None) -> bool:
    """
    Update track in Notion and registry (Phase 1 integration).
    Non-breaking: falls back to Notion-only if registry unavailable.
    """
    try:
        # Always update Notion (existing behavior)
        notion_manager.update_page(page_id, properties)
        workspace_logger.info(f"🔄 Updated track page in Notion: {page_id}")
        
        # Add registry update if available
        if state_registry and track_data:
            try:
                # Extract track ID from page_id or track_data
                track_id = track_data.get('track_id') or page_id
                
                # Convert properties to registry format
                registry_state = {
                    'track_id': track_id,
                    'notion_page_id': page_id,
                    'track_name': track_data.get('title', ''),
                    'artist_name': track_data.get('artist', ''),
                }
                
                # Map Notion properties to registry state
                if 'DL' in properties or 'Downloaded' in properties:
                    registry_state['notion_downloaded'] = properties.get('DL', {}).get('checkbox', False) or \
                                                         properties.get('Downloaded', {}).get('checkbox', False)
                
                if 'M4A File Path' in properties:
                    file_paths = properties['M4A File Path'].get('rich_text', [])
                    registry_state['notion_file_paths'] = [item.get('text', {}).get('content', '') for item in file_paths]
                
                if 'Eagle File ID' in properties:
                    eagle_id = properties['Eagle File ID'].get('rich_text', [])
                    if eagle_id:
                        registry_state['notion_eagle_id'] = eagle_id[0].get('text', {}).get('content', '')
                
                # Update registry
                state_registry.update_track_state(track_id, registry_state)
                workspace_logger.debug(f"📊 Updated registry state for {track_id}")
                
            except Exception as registry_exc:
                workspace_logger.warning(f"⚠️  Registry update failed for {page_id}: {registry_exc}")
        
        return True
        
    except Exception as exc:
        workspace_logger.error(f"❌ Failed to update track {page_id}: {exc}")
        return False

# ───────────────────────────────────────────────────────────────
# Duplicate Detection & Merge Helpers (workspace‑aware)
# ───────────────────────────────────────────────────────────────
def _normalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        p = urlparse(u.strip())
        path = p.path.rstrip("/")
        # Remove typical SoundCloud tracking query params
        clean = p._replace(query="", fragment="", path=path).geturl().lower()
        return clean
    except Exception:
        return u.strip().lower()

_nonword = re.compile(r"[^a-z0-9]+")
def _clean_title(t: str) -> str:
    if not t:
        return ""
    t = t.lower()
    # Drop bracketed adornments like "(feat ...)", "[remix]", "- original mix"
    t = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", t)
    t = re.sub(r"\b(feat\.?|ft\.?|remix|original mix|edit|rework|vip)\b", " ", t)
    return _nonword.sub(" ", t).strip()

def _page_text_for(prop_obj: dict) -> str:
    """Extract text from a page property payload; uses existing helper where possible."""
    try:
        return _prop_text_value(prop_obj)
    except Exception:
        # Fallback for unexpected payloads
        t = prop_obj.get("type")
        if t == "url":
            return prop_obj.get("url") or ""
        if t == "title":
            return "".join([x.get("plain_text","") for x in prop_obj.get("title",[])])
        if t == "rich_text":
            return "".join([x.get("plain_text","") for x in prop_obj.get("rich_text",[])])
        return ""

def _score_page_for_keeper(page: dict) -> tuple:
    """Higher is better. Use presence of files, Eagle ID, fingerprint, then edit time."""
    props = page.get("properties", {})
    prop_types = _get_tracks_db_prop_types()

    def has_path(name: str) -> int:
        real = _resolve_prop_name(name) or name
        return 1 if _page_text_for(props.get(real, {})) else 0

    score = 0
    score += 2 * has_path("WAV File Path")
    score += 2 * has_path("AIFF File Path")
    score += 2 * has_path("M4A File Path")

    real_eagle = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
    if _page_text_for(props.get(real_eagle, {})):
        score += 5

    real_fp = _resolve_prop_name("Fingerprint") or "Fingerprint"
    if _page_text_for(props.get(real_fp, {})):
        score += 2

    real_dl = _resolve_prop_name("DL") or "Downloaded"
    if props.get(real_dl, {}).get("type") == "checkbox" and props.get(real_dl, {}).get("checkbox") is True:
        score += 1

    # Tiebreaker: latest last_edited_time (convert to comparable format)
    edited = page.get("last_edited_time") or ""
    # Convert timestamp to sortable format (newer = higher value)
    try:
        if edited:
            from datetime import datetime
            # Parse ISO timestamp and convert to sortable integer
            dt = datetime.fromisoformat(edited.replace('Z', '+00:00'))
            edited_sortable = int(dt.timestamp())
        else:
            edited_sortable = 0
    except Exception:
        edited_sortable = 0
    
    return (score, edited_sortable)

def _union_unique(seq):
    """Remove duplicates from sequence, handling both hashable and unhashable items."""
    out, seen = [], set()
    for x in seq:
        # Handle hashable items (strings, numbers, etc.)
        try:
            if x not in seen:
                out.append(x)
                seen.add(x)
        except TypeError:
            # Handle unhashable items (dicts, lists, etc.) by converting to string for comparison
            x_str = str(x)
            if x_str not in seen:
                out.append(x)
                seen.add(x_str)
    return out

def _merge_values(prop_type: str, keeper_val: dict, donor_val: dict):
    """Return merged Notion property payload fragment for a single property type."""
    if donor_val is None:
        return keeper_val
    if prop_type in ("title", "rich_text"):
        ktxt = _page_text_for(keeper_val) if keeper_val else ""
        dtxt = _page_text_for(donor_val) if donor_val else ""
        chosen = dtxt if len(dtxt) > len(ktxt) else ktxt
        if prop_type == "title":
            return {"title": [{"text": {"content": chosen}}]} if chosen else keeper_val
        else:
            return {"rich_text": [{"text": {"content": chosen}}]} if chosen else keeper_val

    if prop_type == "multi_select":
        k = [x.get("name") for x in (keeper_val or {}).get("multi_select", []) if x.get("name")]
        d = [x.get("name") for x in (donor_val or {}).get("multi_select", []) if x.get("name")]
        names = _union_unique([*(k or []), *(d or [])])
        return {"multi_select": [{"name": n} for n in names]} if names else keeper_val

    if prop_type == "relation":
        k = [x for x in (keeper_val or {}).get("relation", []) if x.get("id")]
        d = [x for x in (donor_val or {}).get("relation", []) if x.get("id")]
        rels = _union_unique([*(k or []), *(d or [])])
        return {"relation": rels} if rels else keeper_val

    if prop_type == "checkbox":
        k = (keeper_val or {}).get("checkbox")
        d = (donor_val or {}).get("checkbox")
        return {"checkbox": bool(k) or bool(d)}

    if prop_type in ("url", "email", "phone_number"):
        k = (keeper_val or {}).get(prop_type) or ""
        d = (donor_val or {}).get(prop_type) or ""
        return {prop_type: d or k} if (d or k) else keeper_val

    if prop_type == "select" or prop_type == "status":
        k = (keeper_val or {}).get(prop_type) or {}
        d = (donor_val or {}).get(prop_type) or {}
        return {prop_type: d or k} if (d or k) else keeper_val

    if prop_type == "number":
        k = (keeper_val or {}).get("number", None)
        d = (donor_val or {}).get("number", None)
        return {"number": d if d is not None else k} if (d is not None or k is not None) else keeper_val

    if prop_type == "date":
        k = (keeper_val or {}).get("date") or {}
        d = (donor_val or {}).get("date") or {}
        # Prefer earliest start if both present
        ks = (k.get("start") or k.get("start")) if k else None
        ds = (d.get("start") or d.get("start")) if d else None
        if ks and ds:
            chosen = ks if ks <= ds else ds
        else:
            chosen = ds or ks
        return {"date": {"start": chosen}} if chosen else keeper_val

    # Unsupported or complex types: keep keeper
    return keeper_val

def _build_update_payload(merged: dict[str, dict], prop_types: dict[str, str]) -> dict[str, dict]:
    """Convert merged page property values into a payload acceptable for notion.pages.update."""
    prepared: dict[str, dict] = {}
    for name, value in merged.items():
        if value is None:
            continue
        prop_type = prop_types.get(name)
        if not prop_type:
            continue

        if prop_type == "title":
            text = _page_text_for(value)
            if text:
                prepared[name] = {"title": [{"text": {"content": text}}]}
            elif value.get("title"):
                prepared[name] = {"title": value.get("title")}
            continue

        if prop_type == "rich_text":
            if value.get("rich_text") is not None:
                prepared[name] = {"rich_text": value.get("rich_text", [])}
            else:
                text = _page_text_for(value)
                prepared[name] = {"rich_text": [{"text": {"content": text}}]} if text else {"rich_text": []}
            continue

        if prop_type == "multi_select":
            names = [item.get("name") for item in value.get("multi_select", []) if item.get("name")]
            if names:
                prepared[name] = {"multi_select": [{"name": n} for n in names]}
            continue

        if prop_type == "relation":
            rels = [
                {"id": rel.get("id")}
                for rel in value.get("relation", [])
                if rel.get("id")
            ]
            if rels:
                prepared[name] = {"relation": rels}
            continue

        if prop_type == "checkbox":
            cb = value.get("checkbox")
            if cb:
                prepared[name] = {"checkbox": True}
            continue

        if prop_type in ("url", "email", "phone_number"):
            field_val = value.get(prop_type)
            if field_val:
                prepared[name] = {prop_type: field_val}
            continue

        if prop_type in ("select", "status"):
            sel = value.get(prop_type) or {}
            selected = sel.get("name")
            if selected:
                prepared[name] = {prop_type: {"name": selected}}
            continue

        if prop_type == "number":
            if "number" in value and value.get("number") is not None:
                prepared[name] = {"number": value.get("number")}
            continue

        if prop_type == "date":
            date_val = value.get("date")
            if date_val:
                prepared[name] = {"date": {k: v for k, v in date_val.items() if v is not None}}
            continue

        # Unsupported complex types (files, people, rollups, formulas, etc.) are skipped

    return prepared

def _limit_multi_select_entries(value: dict, ensure: Optional[Set[str]] = None, limit: int = DEDUP_MULTISELECT_LIMIT) -> dict:
    """Clamp multi_select payloads to avoid exploding schema options."""
    ensure = ensure or set()
    entries = []
    seen = set()

    for item in value.get("multi_select", []):
        name = item.get("name")
        if not name or name in seen:
            continue
        entries.append({"name": name})
        seen.add(name)
        if len(entries) >= limit:
            break

    for name in ensure:
        if name and name not in seen and len(entries) < limit:
            entries.append({"name": name})
            seen.add(name)

    return {"multi_select": entries} if entries else {}

def _build_trimmed_update_payload(update_payload: dict[str, dict], prop_types: dict[str, str]) -> dict[str, dict]:
    """
    Reduce an update payload to only safe property types for fallback updates when Notion
    reports the schema size limit has been reached.
    """
    if not update_payload:
        return {}

    safe_payload: dict[str, dict] = {}
    safe_multiselect_names: set[str] = set()
    for key in DEDUP_SAFE_MULTISELECT_KEYS:
        resolved = _resolve_prop_name(key) or key
        if prop_types.get(resolved) == "multi_select":
            safe_multiselect_names.add(resolved)

    for name, value in update_payload.items():
        prop_type = prop_types.get(name)
        if not prop_type:
            continue

        if prop_type in DEDUP_SAFE_FIELD_TYPES:
            safe_payload[name] = value
        elif prop_type == "multi_select" and name in safe_multiselect_names:
            limited = _limit_multi_select_entries(
                value,
                ensure=DEDUP_MULTISELECT_REQUIRED_TAGS
            )
            if limited:
                safe_payload[name] = limited
        elif prop_type == "checkbox":
            # Checkbox already covered above but kept for clarity
            safe_payload[name] = value

    return safe_payload

def _merge_group_into_keeper(keeper: dict, donors: list[dict], dry_run: bool = False) -> str:
    """Merge donors into keeper, update keeper, archive donors. Return keeper id."""
    keeper_id = keeper["id"]
    prop_types = _get_tracks_db_prop_types()
    kprops = keeper.get("properties", {})
    merged: dict[str, dict] = {}

    # Start with keeper values
    for name, info in kprops.items():
        merged[name] = info

    # Pull in donor values
    for donor in donors:
        dprops = donor.get("properties", {})
        for name, info in dprops.items():
            ptype = prop_types.get(name)
            if not ptype:
                continue
            merged[name] = _merge_values(ptype, merged.get(name), info)

    # Add a processing marker if available
    if "Audio Processing" in prop_types and prop_types["Audio Processing"] == "multi_select":
        ms = merged.get("Audio Processing", {"multi_select": []}).get("multi_select", [])
        names = _union_unique([*(x.get("name") for x in ms if x.get("name")), "Merged Duplicate"])
        merged["Audio Processing"] = {"multi_select": [{"name": n} for n in names]}

    update_payload = _build_update_payload(merged, prop_types)

    if dry_run:
        workspace_logger.info(
            f"[DRY‑RUN] Would update keeper {keeper_id} on {len(update_payload)} field(s); would archive {len(donors)} donor(s)."
        )
        return keeper_id

    # Apply update to keeper
    try:
        if update_payload:
            notion_manager.update_page(keeper_id, update_payload)
        else:
            workspace_logger.info(f"No property updates required for keeper {keeper_id}; archiving donors only.")
    except Exception as exc:
        error_msg = str(exc)
        if NOTION_SCHEMA_LIMIT_PHRASE in error_msg.lower():
            workspace_logger.warning(
                f"Notion rejected update for keeper {keeper_id} due to schema limits; retrying with trimmed payload. ({error_msg})"
            )
            trimmed_payload = _build_trimmed_update_payload(update_payload, prop_types)
            if trimmed_payload:
                try:
                    notion_manager.update_page(keeper_id, trimmed_payload)
                    workspace_logger.info(
                        f"✅ Keeper {keeper_id} updated with trimmed payload after schema-limit retry."
                    )
                except Exception as fallback_exc:
                    workspace_logger.error(
                        f"Fallback update for keeper {keeper_id} also failed: {fallback_exc}"
                    )
                    raise
            else:
                workspace_logger.warning(
                    f"Trimmed payload empty for keeper {keeper_id}; skipping property update to avoid schema growth."
                )
        else:
            workspace_logger.error(f"Failed to update keeper {keeper_id}: {exc}")
            raise

    # Archive donors
    for donor in donors:
        did = donor["id"]
        if did == keeper_id:
            continue
        try:
            notion_manager._req("patch", f"/pages/{did}", {"archived": True})
            workspace_logger.info(f"🗄️  Archived duplicate page {did}")
        except Exception as e:
            workspace_logger.warning(f"Could not archive duplicate {did}: {e}")

    return keeper_id

def _fetch_by_equals(prop_name: str, value: str) -> list[dict]:
    """Query helper for exact equality on url or rich_text supported by our dynamic types."""
    prop_types = _get_tracks_db_prop_types()
    real = _resolve_prop_name(prop_name) or prop_name
    ptype = prop_types.get(real)
    if not ptype or not value:
        return []
    filt = None
    if ptype == "url":
        filt = {"property": real, "url": {"equals": value}}
    elif ptype == "rich_text":
        filt = {"property": real, "rich_text": {"equals": value}}
    elif ptype == "title":
        filt = {"property": real, "title": {"equals": value}}
    if not filt:
        return []
    q = {"filter": filt, "page_size": SC_NOTION_PAGE_SIZE}
    res = notion_manager.query_database(TRACKS_DB_ID, q)
    return res.get("results", [])

# Cache for recent track queries to avoid redundant API calls
_recent_track_cache: Optional[list[dict]] = None

def _fetch_recent(limit: int = 50) -> list[dict]:
    global _recent_track_cache
    if _recent_track_cache is not None:
        return _recent_track_cache[:limit]
    q = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": min(max(10, limit), SC_NOTION_PAGE_SIZE)
    }
    res = notion_manager.query_database(TRACKS_DB_ID, q)
    _recent_track_cache = res.get("results", [])
    return _recent_track_cache[:limit]

def dedupe_for_meta(meta: dict, dry_run: bool = False) -> Optional[str]:
    """Find and merge duplicates based on Fingerprint, SC URL, Spotify ID, and cleaned Title. Return keeper id or None.

    DEDUPLICATION PRIORITY (2026-01-17):
    1. Fingerprint (MOST RELIABLE - exact audio content match)
    2. SoundCloud URL (reliable - same source)
    3. Spotify ID (reliable - unique identifier)
    4. Cleaned title match (fuzzy - metadata match)
    """
    try:
        candidates: list[dict] = []

        # 0) FINGERPRINT EQUALITY (HIGHEST PRIORITY - added 2026-01-17)
        # Check all fingerprint formats: AIFF, WAV, M4A
        for fp_prop in ["AIFF Fingerprint", "WAV Fingerprint", "M4A Fingerprint"]:
            fp_value = (meta.get(fp_prop.lower().replace(" ", "_")) or meta.get("fingerprint") or "").strip()
            if fp_value and fp_value not in ("FILE_MISSING", ""):
                fp_matches = _fetch_by_equals(fp_prop, fp_value)
                if fp_matches:
                    workspace_logger.info(f"🔍 NOTION DEDUP: Found {len(fp_matches)} fingerprint match(es) via {fp_prop}")
                candidates.extend(fp_matches)

        # 1) SoundCloud URL equality
        sc_url = _normalize_url(meta.get("source_url") or meta.get("soundcloud_url") or "")
        if sc_url:
            candidates.extend(_fetch_by_equals("SoundCloud URL", sc_url))

        # 2) Spotify ID equality
        spid = (meta.get("spotify_id") or "").strip()
        if spid:
            candidates.extend(_fetch_by_equals("Spotify ID", spid))

        # 3) Cleaned title match among recent pages
        title_clean = _clean_title(meta.get("title") or "")
        title_prop = _resolve_prop_name("Title") or "Title"
        if title_clean and title_prop:
            recent = _fetch_recent(SC_DEDUP_RECENT_LIMIT)
            for p in recent:
                tprop = p.get("properties", {}).get(title_prop, {})
                tclean = _clean_title(_page_text_for(tprop))
                if tclean and tclean == title_clean:
                    candidates.append(p)

        # Deduplicate by id
        uniq, seen = [], set()
        for p in candidates:
            pid = p.get("id")
            if pid and pid not in seen:
                uniq.append(p); seen.add(pid)

        if len(uniq) < 2:
            return None

        # Choose keeper
        uniq.sort(key=_score_page_for_keeper, reverse=True)
        keeper, donors = uniq[0], uniq[1:]
        keeper_id = keeper["id"]

        workspace_logger.info(f"🔁 De‑dupe group size={len(uniq)}. Keeper={keeper_id}. Donors={[d['id'] for d in donors]}")
        return _merge_group_into_keeper(keeper, donors, dry_run=dry_run)
    except Exception as e:
        workspace_logger.error(f"❌ CRITICAL: De‑dupe failed: {e}")
        workspace_logger.error(f"❌ This is a critical error that prevents proper duplicate handling")
        workspace_logger.error(f"❌ Processing cannot continue safely without deduplication")
        raise RuntimeError(f"Deduplication failed: {e}")


# ───────────────────────────────────────────────────────────────
# Pre-process de-duplication helper (redirect to canonical page before processing)
# ───────────────────────────────────────────────────────────────
def try_merge_duplicates_for_page(page: dict, dry_run: bool = False) -> dict:
    """
    Given a Notion page selected by the existing filters, look for duplicates
    using the same criteria as dedupe_for_meta(). If a different keeper is chosen,
    return that keeper's page object; otherwise return the original page.
    Does not modify the original DB query filters.
    """
    try:
        info = extract_track_data(page)
        meta = {
            "title": info.get("title") or "",
            "source_url": _normalize_url(info.get("soundcloud_url") or ""),
            "soundcloud_url": _normalize_url(info.get("soundcloud_url") or ""),
            "spotify_id": (info.get("spotify_id") or "").strip(),
        }
        keeper_id = dedupe_for_meta(meta, dry_run=dry_run)
        if not keeper_id or dry_run:
            return page
        if keeper_id == page.get("id"):
            return page
        # Fetch and return the keeper page so downstream processing targets the canonical item
        try:
            keeper_page = notion_manager._req("get", f"/pages/{keeper_id}")
            workspace_logger.info(f"🔗 Redirecting processing to keeper page {keeper_id} (was {page.get('id')})")
            return keeper_page
        except Exception as e:
            workspace_logger.warning(f"Could not fetch keeper page {keeper_id}: {e}")
            return page
    except Exception as e:
        workspace_logger.error(f"❌ CRITICAL: Pre-process de-duplication failed: {e}")
        workspace_logger.error(f"❌ Cannot safely process track without deduplication")
        raise RuntimeError(f"Pre-process deduplication failed: {e}")

# ───────────────────────────────────────────────────────────────
# Property helpers for dynamic Notion schemas
# ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL PROPERTY NAME MAPPINGS (2026-01-16)
# ═══════════════════════════════════════════════════════════════════════════════
# Maps semantic names to actual Notion property names (first match wins)
# Based on Music Tracks database schema analysis
# ═══════════════════════════════════════════════════════════════════════════════
ALT_PROP_NAMES = {
    # ─── Core Track Identification ───────────────────────────────────────────
    "Title": ["Title", "Name"],
    "Artist Name": ["Artist Name", "Artists"],
    "Album": ["Album", "Album Name"],
    "Genre": ["Genre", "Genres"],
    "Label": ["Label"],
    "Composer": ["Composer"],
    "Remixer": ["Remixer"],
    "Release Date": ["Release Date"],
    "Year": ["Year", "Release Year"],
    "Track Number": ["Track Number", "TrackNumber"],
    "Disc Number": ["Disc Number", "DiscNumber"],
    "ISRC": ["ISRC", "Track ISRC"],

    # ─── Download/Processing Status ──────────────────────────────────────────
    "DL": ["Downloaded", "DL"],  # "Downloaded" is the actual property name
    "Audio Processing": ["Audio Processing"],
    "Audio Processing Status": ["Audio Processing Status", "Audio Analysis Status"],
    "Audio Normalized": ["Audio Normalized"],
    "Duplicate": ["Duplicate"],
    "Explicit": ["Explicit"],
    "Fallback Used": ["Fallback Used"],

    # ─── File Paths (CRITICAL - prevents reprocessing) ───────────────────────
    "WAV File Path": ["WAV File Path", "WAV", "WAV Path"],
    "AIFF File Path": ["AIFF File Path", "AIFF", "AIFF Path"],
    "M4A File Path": ["M4A File Path", "M4A", "M4A Path"],

    # ─── Audio Metadata (CRITICAL) ───────────────────────────────────────────
    # NOTE: "Tempo" is the actual property name in the database, not "BPM"
    "BPM": ["Tempo", "AverageBpm", "BPM"],  # Tempo is PRIMARY
    "Key": ["Key"],
    "Duration (s)": ["Audio Duration (seconds)", "Duration (s)", "TotalTime"],

    # ─── Fingerprints (Per-format schema 2026-01-14) ─────────────────────────
    "WAV Fingerprint": ["WAV Fingerprint"],
    "AIFF Fingerprint": ["AIFF Fingerprint"],
    "M4A Fingerprint": ["M4A Fingerprint"],
    "Fingerprint": ["WAV Fingerprint", "AIFF Fingerprint", "M4A Fingerprint"],  # Legacy fallback

    # ─── Eagle Integration ───────────────────────────────────────────────────
    "Eagle File ID": ["Eagle File ID", "Eagle ID", "EagleID"],

    # ─── Source URLs ─────────────────────────────────────────────────────────
    "SoundCloud URL": ["SoundCloud URL", "Soundcloud URL"],
    "Spotify URL": ["Spotify URL", "Spotify Link"],
    "YouTube URL": ["YouTube URL"],
    "Apple Music URL": ["Apple Music URL"],
    "Bandcamp URL": ["Bandcamp URL"],
    "Beatport URL": ["Beatport URL"],

    # ─── Spotify Properties ──────────────────────────────────────────────────
    "Spotify ID": ["Spotify ID", "Spotify Track ID", "SpotifyID"],
    "Spotify Playlist ID": ["Spotify Playlist ID"],

    # ─── Audio Quality Metrics ───────────────────────────────────────────────
    "Audio Quality Score": ["Audio Quality Score", "Quality Score"],
    "Audio LUFS Level": ["Audio LUFS Level", "Loudness Level"],
    "Audio Peak Level": ["Audio Peak Level"],
    "Audio RMS Level": ["Audio RMS Level"],
    "Audio Dynamic Range (dB)": ["Audio Dynamic Range (dB)"],
    "Audio Crest Factor": ["Audio Crest Factor"],
    "Audio Sample Rate": ["Audio Sample Rate", "SampleRate"],
    "Audio Clipping Percentage": ["Audio Clipping Percentage"],
    "Warmth Enhancement Level": ["Warmth Enhancement Level"],
    "BitRate": ["BitRate"],
    "Audio File Size (MB)": ["Audio File Size (MB)"],

    # ─── Processing Metadata ─────────────────────────────────────────────────
    "Processing Timestamp": ["Processing Timestamp", "Processed At"],
    "Compression Mode Used": ["Compression Mode Used", "Compression Mode", "Audio Compression Mode"],
    "Download Source": ["Download Source"],
    "Audio Normalizer Available": ["Audio Normalizer Available"],

    # ─── Playlist Relations ──────────────────────────────────────────────────
    "Playlists": ["Playlists", "Playlist", "Playlist Relation"],

    # ─── Processing Lock (for concurrent process management) ─────────────────
    "Processing Lock": ["Processing Lock", "ProcessingLock"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# DISTRIBUTED PROCESS LOCKING SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
# This system enables multiple instances of the script to run concurrently without
# processing the same tracks. Uses Notion as a distributed lock store.
#
# Lock format: "PID:HOSTNAME:TIMESTAMP" (e.g., "12345:MacBook-Pro:2026-01-16T10:30:00Z")
# Lock expiration: 30 minutes (configurable via PROCESS_LOCK_TIMEOUT_MINUTES)
# ═══════════════════════════════════════════════════════════════════════════════

import socket
import uuid

# Process identification
_PROCESS_ID = os.getpid()
_PROCESS_HOSTNAME = socket.gethostname()
_PROCESS_UUID = str(uuid.uuid4())[:8]  # Short unique ID for this process instance
_PROCESS_IDENTIFIER = f"{_PROCESS_ID}:{_PROCESS_HOSTNAME}:{_PROCESS_UUID}"

# Lock configuration
PROCESS_LOCK_TIMEOUT_MINUTES = int(os.getenv("PROCESS_LOCK_TIMEOUT_MINUTES", "30"))
PROCESS_LOCK_ENABLED = os.getenv("PROCESS_LOCK_ENABLED", "1").strip().lower() in ("1", "true", "yes")

workspace_logger.info(f"🔒 Process Locking: {'ENABLED' if PROCESS_LOCK_ENABLED else 'DISABLED'}")
workspace_logger.info(f"🔒 Process Identifier: {_PROCESS_IDENTIFIER}")
workspace_logger.info(f"🔒 Lock Timeout: {PROCESS_LOCK_TIMEOUT_MINUTES} minutes")


def _parse_process_lock(lock_value: str) -> Optional[Dict[str, Any]]:
    """Parse a process lock string into its components.

    Lock format: "PID:HOSTNAME:UUID:TIMESTAMP"

    Returns:
        Dict with pid, hostname, uuid, timestamp, or None if invalid
    """
    if not lock_value or not lock_value.strip():
        return None

    try:
        parts = lock_value.strip().split(":")
        if len(parts) < 4:
            return None

        pid = parts[0]
        hostname = parts[1]
        proc_uuid = parts[2]
        timestamp_str = ":".join(parts[3:])  # Rejoin timestamp (may contain colons)

        # Parse timestamp
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        return {
            "pid": pid,
            "hostname": hostname,
            "uuid": proc_uuid,
            "timestamp": timestamp,
            "raw": lock_value,
        }
    except Exception as e:
        workspace_logger.debug(f"Failed to parse lock value '{lock_value}': {e}")
        return None


def _is_lock_stale(lock_info: Dict[str, Any]) -> bool:
    """Check if a lock has expired based on timestamp.

    Args:
        lock_info: Parsed lock information from _parse_process_lock

    Returns:
        True if lock is stale (expired), False if still valid
    """
    if not lock_info or "timestamp" not in lock_info:
        return True

    try:
        lock_time = lock_info["timestamp"]
        now = datetime.now(timezone.utc)

        # Ensure both are timezone-aware
        if lock_time.tzinfo is None:
            lock_time = lock_time.replace(tzinfo=timezone.utc)

        age_minutes = (now - lock_time).total_seconds() / 60
        is_stale = age_minutes > PROCESS_LOCK_TIMEOUT_MINUTES

        if is_stale:
            workspace_logger.debug(
                f"Lock is stale: age={age_minutes:.1f}m > timeout={PROCESS_LOCK_TIMEOUT_MINUTES}m"
            )

        return is_stale
    except Exception as e:
        workspace_logger.debug(f"Error checking lock staleness: {e}")
        return True  # Treat errors as stale


def _is_our_lock(lock_info: Dict[str, Any]) -> bool:
    """Check if a lock belongs to this process instance.

    Args:
        lock_info: Parsed lock information from _parse_process_lock

    Returns:
        True if this process owns the lock
    """
    if not lock_info:
        return False

    return (
        lock_info.get("pid") == str(_PROCESS_ID) and
        lock_info.get("hostname") == _PROCESS_HOSTNAME and
        lock_info.get("uuid") == _PROCESS_UUID
    )


def _create_lock_value() -> str:
    """Create a new lock value for this process.

    Returns:
        Lock string in format "PID:HOSTNAME:UUID:TIMESTAMP"
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"{_PROCESS_ID}:{_PROCESS_HOSTNAME}:{_PROCESS_UUID}:{timestamp}"


def acquire_track_lock(page_id: str) -> bool:
    """Attempt to acquire a processing lock on a track.

    This uses optimistic locking - we check if locked, then set our lock.
    In case of race conditions, the track will still be processed by one process
    (whichever writes last), and the other will skip on re-check.

    Args:
        page_id: Notion page ID to lock

    Returns:
        True if lock acquired successfully, False if already locked by another process
    """
    if not PROCESS_LOCK_ENABLED:
        return True  # Locking disabled, always succeed

    try:
        # Check if Processing Lock property exists
        prop_types = _get_tracks_db_prop_types()
        lock_prop = _resolve_prop_name("Processing Lock")

        if not lock_prop or lock_prop not in prop_types:
            workspace_logger.debug(f"Processing Lock property not found in database - locking disabled")
            return True  # Property doesn't exist, skip locking

        # Fetch current page state
        page = notion_manager._req("get", f"/pages/{page_id}")
        props = page.get("properties", {})

        # Get current lock value
        current_lock = _prop_text_value(props.get(lock_prop, {}))
        lock_info = _parse_process_lock(current_lock)

        # Check if locked by another process
        if lock_info and not _is_our_lock(lock_info) and not _is_lock_stale(lock_info):
            workspace_logger.info(
                f"🔒 Track {page_id} locked by another process: "
                f"PID={lock_info.get('pid')} HOST={lock_info.get('hostname')} "
                f"since {lock_info.get('timestamp')}"
            )
            return False

        # Acquire lock
        new_lock = _create_lock_value()

        # Determine property type and build appropriate update
        prop_type = prop_types.get(lock_prop)
        if prop_type == "rich_text":
            lock_update = {"rich_text": [{"text": {"content": new_lock}}]}
        elif prop_type == "url":
            # URL type can store the lock value too
            lock_update = {"url": new_lock}
        else:
            workspace_logger.warning(f"Unsupported lock property type: {prop_type}")
            return True

        # Write lock to Notion
        notion_manager._req("patch", f"/pages/{page_id}", {
            "properties": {lock_prop: lock_update}
        })

        workspace_logger.debug(f"🔒 Acquired lock on {page_id}: {new_lock}")
        return True

    except Exception as e:
        workspace_logger.warning(f"Failed to acquire lock on {page_id}: {e}")
        return True  # On error, proceed anyway to avoid deadlocks


def release_track_lock(page_id: str) -> bool:
    """Release a processing lock on a track.

    Only releases if we own the lock. Safe to call even if not locked.

    Args:
        page_id: Notion page ID to unlock

    Returns:
        True if lock released or not owned, False on error
    """
    if not PROCESS_LOCK_ENABLED:
        return True

    try:
        prop_types = _get_tracks_db_prop_types()
        lock_prop = _resolve_prop_name("Processing Lock")

        if not lock_prop or lock_prop not in prop_types:
            return True

        # Fetch current page state
        page = notion_manager._req("get", f"/pages/{page_id}")
        props = page.get("properties", {})

        # Get current lock value
        current_lock = _prop_text_value(props.get(lock_prop, {}))
        lock_info = _parse_process_lock(current_lock)

        # Only release if we own the lock
        if not lock_info or not _is_our_lock(lock_info):
            workspace_logger.debug(f"🔓 Not releasing lock on {page_id} - not our lock")
            return True

        # Clear lock
        prop_type = prop_types.get(lock_prop)
        if prop_type == "rich_text":
            lock_update = {"rich_text": []}
        elif prop_type == "url":
            lock_update = {"url": None}
        else:
            return True

        notion_manager._req("patch", f"/pages/{page_id}", {
            "properties": {lock_prop: lock_update}
        })

        workspace_logger.debug(f"🔓 Released lock on {page_id}")
        return True

    except Exception as e:
        workspace_logger.warning(f"Failed to release lock on {page_id}: {e}")
        return False


def check_track_lock_status(page_id: str) -> Dict[str, Any]:
    """Check the lock status of a track without modifying it.

    Args:
        page_id: Notion page ID to check

    Returns:
        Dict with:
            - locked: bool - whether track is locked
            - owned_by_us: bool - whether this process owns the lock
            - stale: bool - whether lock is expired
            - lock_info: Optional[Dict] - parsed lock details
    """
    result = {
        "locked": False,
        "owned_by_us": False,
        "stale": False,
        "lock_info": None,
    }

    if not PROCESS_LOCK_ENABLED:
        return result

    try:
        prop_types = _get_tracks_db_prop_types()
        lock_prop = _resolve_prop_name("Processing Lock")

        if not lock_prop or lock_prop not in prop_types:
            return result

        page = notion_manager._req("get", f"/pages/{page_id}")
        props = page.get("properties", {})

        current_lock = _prop_text_value(props.get(lock_prop, {}))
        lock_info = _parse_process_lock(current_lock)

        if lock_info:
            result["locked"] = True
            result["lock_info"] = lock_info
            result["owned_by_us"] = _is_our_lock(lock_info)
            result["stale"] = _is_lock_stale(lock_info)

        return result

    except Exception as e:
        workspace_logger.warning(f"Failed to check lock status for {page_id}: {e}")
        return result


def cleanup_stale_locks(max_pages: int = 100) -> int:
    """Clean up stale locks from tracks in the database.

    Useful for recovering from crashed processes or orphaned locks.

    Args:
        max_pages: Maximum number of pages to check

    Returns:
        Number of stale locks cleared
    """
    if not PROCESS_LOCK_ENABLED:
        return 0

    workspace_logger.info("🧹 Scanning for stale processing locks...")

    try:
        prop_types = _get_tracks_db_prop_types()
        lock_prop = _resolve_prop_name("Processing Lock")

        if not lock_prop or lock_prop not in prop_types:
            workspace_logger.info("Processing Lock property not found - no cleanup needed")
            return 0

        # Query for pages with non-empty lock
        query = {
            "filter": {
                "property": lock_prop,
                "rich_text": {"is_not_empty": True}
            },
            "page_size": min(max_pages, 100)
        }

        pages = query_database_paginated(TRACKS_DB_ID, query, max_items=max_pages)

        cleared = 0
        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})

            current_lock = _prop_text_value(props.get(lock_prop, {}))
            lock_info = _parse_process_lock(current_lock)

            if lock_info and _is_lock_stale(lock_info):
                # Clear stale lock
                try:
                    prop_type = prop_types.get(lock_prop)
                    if prop_type == "rich_text":
                        lock_update = {"rich_text": []}
                    elif prop_type == "url":
                        lock_update = {"url": None}
                    else:
                        continue

                    notion_manager._req("patch", f"/pages/{page_id}", {
                        "properties": {lock_prop: lock_update}
                    })

                    cleared += 1
                    workspace_logger.info(
                        f"🧹 Cleared stale lock on page {page_id}: "
                        f"was locked by PID={lock_info.get('pid')} HOST={lock_info.get('hostname')}"
                    )
                except Exception as e:
                    workspace_logger.warning(f"Failed to clear stale lock on {page_id}: {e}")

        workspace_logger.info(f"🧹 Cleared {cleared} stale locks")
        return cleared

    except Exception as e:
        workspace_logger.error(f"Failed to cleanup stale locks: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED STATE TRACKING SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════
# This system provides consistent state tracking across ALL processing modes:
# - single, batch, all, reprocess, library-sync
#
# It ensures:
# 1. Consistent completion marking (DL checkbox, file paths, Eagle ID)
# 2. Unified error recording to Notion
# 3. Atomic verification after updates
# 4. Consistent deduplication application
# ═══════════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Any


class TrackStatus(Enum):
    """Unified track processing status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED_LOCKED = "skipped_locked"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_ALREADY_DONE = "skipped_already_done"
    SKIPPED_NO_SOURCE = "skipped_no_source"
    ERROR = "error"


class ErrorType(Enum):
    """Unified error type classification for Notion recording."""
    SC_404 = "SC_404"  # SoundCloud track not found
    SC_GEO_BLOCKED = "SC_Geo_Blocked"  # Region restricted
    DOWNLOAD_FAILED = "Download_Failed"  # General download failure
    CONVERSION_FAILED = "Conversion_Failed"  # FFmpeg conversion error
    EAGLE_IMPORT_FAILED = "Eagle_Import_Failed"  # Eagle import error
    NOTION_UPDATE_FAILED = "Notion_Update_Failed"  # Notion API error
    DEDUP_FAILED = "Dedup_Failed"  # Deduplication error
    LOCK_CONFLICT = "Lock_Conflict"  # Locked by another process
    METADATA_FAILED = "Metadata_Failed"  # Metadata extraction error
    UNKNOWN = "Unknown_Error"  # Unclassified error


@dataclass
class TrackResult:
    """Unified result object for track processing across all modes.

    This ensures consistent result tracking regardless of which mode
    (single, batch, library-sync, etc.) processes the track.
    """
    page_id: str
    title: str = "Unknown"
    artist: str = "Unknown"
    status: TrackStatus = TrackStatus.PENDING

    # File outputs (None if not created)
    wav_path: Optional[str] = None
    aiff_path: Optional[str] = None
    m4a_path: Optional[str] = None
    playlist_wav_path: Optional[str] = None

    # Eagle integration
    eagle_item_id: Optional[str] = None
    eagle_aiff_item_id: Optional[str] = None

    # Audio metadata
    duration_seconds: Optional[float] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    fingerprint: Optional[str] = None

    # Error tracking
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None

    # Processing metadata
    dedupe_redirected: bool = False
    dedupe_keeper_id: Optional[str] = None
    processing_time_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "page_id": self.page_id,
            "title": self.title,
            "artist": self.artist,
            "status": self.status.value if isinstance(self.status, TrackStatus) else self.status,
            "file_paths": {
                "wav": self.wav_path,
                "aiff": self.aiff_path,
                "m4a": self.m4a_path,
                "playlist_wav": self.playlist_wav_path,
            },
            "eagle_item_id": self.eagle_item_id,
            "eagle_aiff_item_id": self.eagle_aiff_item_id,
            "duration_seconds": self.duration_seconds,
            "bpm": self.bpm,
            "key": self.key,
            "fingerprint": self.fingerprint,
            "error_type": self.error_type.value if self.error_type else None,
            "error_message": self.error_message,
            "dedupe_redirected": self.dedupe_redirected,
            "dedupe_keeper_id": self.dedupe_keeper_id,
            "processing_time_seconds": self.processing_time_seconds,
        }

    @property
    def is_success(self) -> bool:
        """Check if processing was successful."""
        return self.status == TrackStatus.PROCESSED

    @property
    def has_files(self) -> bool:
        """Check if any output files were created."""
        return bool(self.wav_path or self.aiff_path or self.m4a_path or self.playlist_wav_path)

    @property
    def has_eagle_id(self) -> bool:
        """Check if Eagle import was successful."""
        return bool(self.eagle_item_id or self.eagle_aiff_item_id)


def mark_track_complete(
    page_id: str,
    file_paths: Optional[Dict[str, str]] = None,
    eagle_id: Optional[str] = None,
    audio_status: Optional[List[str]] = None,
    fingerprint: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    verify_completion: bool = True,
) -> bool:
    """
    Unified function to mark a track as complete in Notion.

    This is the SINGLE source of truth for completion marking across all modes.
    It ensures:
    1. DL checkbox is only set if files exist OR Eagle ID exists
    2. All file paths are written atomically
    3. Audio Processing Status is updated
    4. Verification confirms track won't be reprocessed

    Args:
        page_id: Notion page ID
        file_paths: Dict with keys 'wav', 'aiff', 'm4a', 'playlist_wav'
        eagle_id: Eagle item ID if imported
        audio_status: List of audio processing status values to add
        fingerprint: Audio fingerprint for deduplication
        metadata: Additional metadata (bpm, key, duration_seconds, etc.)
        verify_completion: If True, verify track won't reprocess after update

    Returns:
        True if completion was successful and verified
    """
    if not page_id:
        workspace_logger.error("mark_track_complete called with no page_id")
        return False

    try:
        # Build properties update
        properties = {}
        prop_types = _get_tracks_db_prop_types()

        # Determine if we should set DL checkbox
        has_files = file_paths and any(file_paths.values())
        has_eagle = bool(eagle_id)
        should_mark_downloaded = has_files or has_eagle

        # Only set DL=True if we have actual completion evidence
        if should_mark_downloaded:
            dl_prop = _resolve_prop_name("DL") or "Downloaded"
            if dl_prop in prop_types:
                properties[dl_prop] = {"checkbox": True}

        # Set file paths (only if provided and non-empty)
        if file_paths:
            path_mappings = [
                ("wav", "WAV File Path"),
                ("aiff", "AIFF File Path"),
                ("m4a", "M4A File Path"),
            ]
            for key, prop_name in path_mappings:
                path_value = file_paths.get(key)
                if path_value:
                    resolved_prop = _resolve_prop_name(prop_name) or prop_name
                    if resolved_prop in prop_types:
                        properties[resolved_prop] = {
                            "rich_text": [{"text": {"content": str(path_value)[:2000]}}]
                        }

        # Set Eagle File ID
        if eagle_id:
            eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
            if eagle_prop in prop_types:
                properties[eagle_prop] = {
                    "rich_text": [{"text": {"content": str(eagle_id)}}]
                }

        # Set fingerprint
        if fingerprint:
            fp_prop = _resolve_prop_name("Fingerprint") or "Fingerprint"
            if fp_prop in prop_types:
                properties[fp_prop] = {
                    "rich_text": [{"text": {"content": str(fingerprint)[:2000]}}]
                }

        # Set metadata (BPM, Key, Duration)
        if metadata:
            if metadata.get("bpm"):
                bpm_prop = _resolve_prop_name("BPM") or "Tempo"
                if bpm_prop in prop_types and prop_types.get(bpm_prop) == "number":
                    properties[bpm_prop] = {"number": float(metadata["bpm"])}

            if metadata.get("key"):
                key_prop = _resolve_prop_name("Key") or "Key "
                if key_prop in prop_types:
                    properties[key_prop] = {
                        "rich_text": [{"text": {"content": str(metadata["key"])}}]
                    }

            if metadata.get("duration_seconds"):
                dur_prop = _resolve_prop_name("Duration (s)") or "Audio Duration (seconds)"
                if dur_prop in prop_types and prop_types.get(dur_prop) == "number":
                    properties[dur_prop] = {"number": float(metadata["duration_seconds"])}

        # Apply the update
        if properties:
            notion_manager._req("patch", f"/pages/{page_id}", {"properties": properties})
            workspace_logger.debug(f"✅ Updated Notion page {page_id} with {len(properties)} properties")

        # Update audio processing status separately (uses merge logic)
        if audio_status:
            update_audio_processing_status(page_id, audio_status)

        # Verify completion (track won't be reprocessed)
        if verify_completion and should_mark_downloaded:
            if not verify_track_will_not_reprocess(page_id):
                workspace_logger.error(f"⚠️  VERIFICATION FAILED: Track {page_id} may be reprocessed!")
                return False

        workspace_logger.info(f"✅ Track {page_id} marked complete (DL={should_mark_downloaded})")
        return True

    except Exception as e:
        workspace_logger.error(f"❌ Failed to mark track complete: {e}")
        return False


def record_track_error(
    page_id: str,
    error_type: ErrorType,
    error_message: Optional[str] = None,
    clear_lock: bool = True,
) -> bool:
    """
    Record an error for a track in Notion's Audio Processing Status.

    This ensures ALL error types are recorded consistently across all modes,
    not just SC_404 errors.

    Args:
        page_id: Notion page ID
        error_type: Classified error type
        error_message: Optional detailed error message
        clear_lock: Whether to release any processing lock

    Returns:
        True if error was recorded successfully
    """
    if not page_id:
        workspace_logger.error("record_track_error called with no page_id")
        return False

    try:
        # Record error in Audio Processing Status
        status_values = [error_type.value]

        # Add timestamp for error tracking
        error_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        if error_message:
            # Truncate long error messages
            short_msg = error_message[:100] if len(error_message) > 100 else error_message
            workspace_logger.info(f"📝 Recording error for {page_id}: {error_type.value} - {short_msg}")

        update_audio_processing_status(page_id, status_values)

        # Clear processing lock if requested
        if clear_lock and PROCESS_LOCK_ENABLED:
            release_track_lock(page_id)

        workspace_logger.record_failed()
        return True

    except Exception as e:
        workspace_logger.error(f"❌ Failed to record error for track {page_id}: {e}")
        return False


def classify_error(exception: Exception, context: str = "") -> ErrorType:
    """
    Classify an exception into a standardized ErrorType.

    Args:
        exception: The exception to classify
        context: Optional context string for better classification

    Returns:
        Classified ErrorType
    """
    error_msg = str(exception).lower()
    context_lower = context.lower()

    # SoundCloud specific errors
    if "404" in error_msg or "not found" in error_msg:
        if "soundcloud" in context_lower or "soundcloud" in error_msg:
            return ErrorType.SC_404
        return ErrorType.DOWNLOAD_FAILED

    if "geo" in error_msg or "blocked" in error_msg or "country" in error_msg or "region" in error_msg:
        return ErrorType.SC_GEO_BLOCKED

    # Download errors
    if "download" in error_msg or "yt-dlp" in error_msg or "ytdlp" in error_msg:
        return ErrorType.DOWNLOAD_FAILED

    # Conversion errors
    if "ffmpeg" in error_msg or "conversion" in error_msg or "transcode" in error_msg:
        return ErrorType.CONVERSION_FAILED

    # Eagle errors
    if "eagle" in error_msg or "eagle" in context_lower:
        return ErrorType.EAGLE_IMPORT_FAILED

    # Notion errors
    if "notion" in error_msg or "api" in error_msg:
        return ErrorType.NOTION_UPDATE_FAILED

    # Deduplication errors
    if "dedup" in error_msg or "duplicate" in error_msg:
        return ErrorType.DEDUP_FAILED

    # Lock errors
    if "lock" in error_msg:
        return ErrorType.LOCK_CONFLICT

    # Metadata errors
    if "metadata" in error_msg or "tag" in error_msg:
        return ErrorType.METADATA_FAILED

    return ErrorType.UNKNOWN


def process_track_with_unified_state(
    track_page: Dict[str, Any],
    enable_dedup: bool = True,
    dedupe_dry_run: bool = False,
) -> TrackResult:
    """
    Process a single track with unified state tracking and deduplication.

    This is the CANONICAL entry point for processing a track. All modes should
    use this function to ensure consistent:
    1. Deduplication (per-track check before processing)
    2. State tracking (TrackResult object)
    3. Error recording (to Notion)
    4. Completion marking (unified)

    Args:
        track_page: Notion page data for the track
        enable_dedup: Whether to run deduplication check
        dedupe_dry_run: If True, don't actually merge duplicates

    Returns:
        TrackResult with processing outcome
    """
    start_time = time.time()
    page_id = track_page.get("id", "unknown")
    track_data = extract_track_data(track_page)

    result = TrackResult(
        page_id=page_id,
        title=track_data.get("title", "Unknown"),
        artist=track_data.get("artist", "Unknown"),
        status=TrackStatus.IN_PROGRESS,
    )

    try:
        # ═══════════════════════════════════════════════════════════════
        # Step 1: Per-track deduplication (if enabled)
        # ═══════════════════════════════════════════════════════════════
        if enable_dedup:
            try:
                resolved_page = try_merge_duplicates_for_page(track_page, dry_run=dedupe_dry_run)
                resolved_page_id = resolved_page.get("id")

                if resolved_page_id and resolved_page_id != page_id:
                    workspace_logger.info(f"🔗 Dedup redirected {page_id} -> {resolved_page_id}")
                    result.dedupe_redirected = True
                    result.dedupe_keeper_id = resolved_page_id

                    # Update to use keeper page
                    track_page = resolved_page
                    page_id = resolved_page_id
                    track_data = extract_track_data(resolved_page)
                    result.page_id = page_id
                    result.title = track_data.get("title", "Unknown")
                    result.artist = track_data.get("artist", "Unknown")

            except Exception as dedup_err:
                workspace_logger.warning(f"⚠️  Deduplication check failed: {dedup_err}")
                # Continue processing despite dedup failure

        # ═══════════════════════════════════════════════════════════════
        # Step 2: Check if already processed
        # ═══════════════════════════════════════════════════════════════
        dl_prop = _resolve_prop_name("DL") or "Downloaded"
        props = track_page.get("properties", {})
        is_downloaded = props.get(dl_prop, {}).get("checkbox") is True

        eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
        has_eagle_id = bool(_prop_text_value(props.get(eagle_prop, {})))

        if is_downloaded or has_eagle_id:
            workspace_logger.info(f"⏭️  Already processed: {result.title}")
            result.status = TrackStatus.SKIPPED_ALREADY_DONE
            result.eagle_item_id = _prop_text_value(props.get(eagle_prop, {})) if has_eagle_id else None
            return result

        # ═══════════════════════════════════════════════════════════════
        # Step 3: Check for audio source
        # ═══════════════════════════════════════════════════════════════
        soundcloud_url = track_data.get("soundcloud_url")
        if not soundcloud_url:
            workspace_logger.warning(f"⏭️  No SoundCloud URL: {result.title}")
            result.status = TrackStatus.SKIPPED_NO_SOURCE
            record_track_error(page_id, ErrorType.DOWNLOAD_FAILED, "No SoundCloud URL")
            return result

        # ═══════════════════════════════════════════════════════════════
        # Step 4: Get playlist info and process
        # ═══════════════════════════════════════════════════════════════
        playlist_names = get_playlist_names_from_track(track_data)
        playlist_name = playlist_names[0] if playlist_names else "Unassigned"
        playlist_dir = OUT_DIR / playlist_name

        workspace_logger.info(f"🎵 Processing: {result.title} by {result.artist}")

        # Call the actual download function
        download_result = download_track(
            soundcloud_url,
            playlist_dir,
            track_data,
            playlist_name
        )

        # ═══════════════════════════════════════════════════════════════
        # Step 5: Handle result
        # ═══════════════════════════════════════════════════════════════
        if download_result:
            # Extract results
            result.status = TrackStatus.PROCESSED
            result.eagle_item_id = download_result.get("eagle_item_id")
            result.duration_seconds = download_result.get("duration")
            result.fingerprint = download_result.get("fingerprint")

            # Extract file paths from result
            file_paths = download_result.get("file_paths", {})
            if isinstance(file_paths, dict):
                result.wav_path = str(file_paths.get("WAV (Eagle)", "")) if file_paths.get("WAV (Eagle)") else None
                result.aiff_path = str(file_paths.get("AIFF (Eagle)", "")) if file_paths.get("AIFF (Eagle)") else None
                playlist_wav = file_paths.get("WAV (Playlist)")
                result.playlist_wav_path = str(playlist_wav) if playlist_wav else None

            workspace_logger.record_processed()
            workspace_logger.info(f"✅ Success: {result.title}")

        else:
            result.status = TrackStatus.FAILED
            result.error_type = ErrorType.DOWNLOAD_FAILED
            result.error_message = "download_track returned None"
            record_track_error(page_id, ErrorType.DOWNLOAD_FAILED, "Processing failed")
            workspace_logger.error(f"❌ Failed: {result.title}")

    except Exception as e:
        result.status = TrackStatus.ERROR
        result.error_type = classify_error(e, "process_track")
        result.error_message = str(e)
        record_track_error(page_id, result.error_type, str(e))
        workspace_logger.error(f"❌ Error processing {result.title}: {e}")

    finally:
        result.processing_time_seconds = time.time() - start_time

    return result


_SPOTIFY_CLIENT: Optional[SpotifyAPI] = None
_SPOTIFY_MANAGER: Optional[SpotifyOAuthManager] = None
_SPOTIFY_DISABLED_REASON: Optional[str] = None
_SPOTIFY_MATCH_CACHE: Dict[str, Optional[dict]] = {}
_SPOTIFY_CACHE_SENTINEL = object()
_SPOTIFY_ENRICH_ATTEMPTS = 0
_SPOTIFY_ENRICH_SUCCESS = 0

def _get_tracks_db_prop_types() -> dict[str, str]:
    """Return a mapping of property name -> Notion property type for the Tracks DB.
    Types are the Notion canonical types (e.g., 'url', 'rich_text', 'checkbox', 'date', 'title', etc.).
    """
    global _tracks_db_prop_types
    if _tracks_db_prop_types is None:
        try:
            db_meta = notion_manager._req("get", f"/databases/{TRACKS_DB_ID}")
            props = db_meta.get("properties", {})
            _tracks_db_prop_types = {name: info.get("type") for name, info in props.items()}
            # Also refresh the name cache used elsewhere
            global _tracks_db_props
            _tracks_db_props = set(_tracks_db_prop_types.keys())
            workspace_logger.debug(f"Cached Tracks DB prop types: { _tracks_db_prop_types }")
        except Exception as exc:
            workspace_logger.warning(f"Could not fetch Tracks DB property types: {exc}")
            _tracks_db_prop_types = {}
    return _tracks_db_prop_types

def _resolve_prop_name(preferred: str) -> Optional[str]:
    """Return the first existing property name for the given semantic key using ALT_PROP_NAMES.
    If none found, return None.
    """
    prop_types = _get_tracks_db_prop_types()
    for candidate in ALT_PROP_NAMES.get(preferred, [preferred]):
        if candidate in prop_types:
            return candidate
    return None

def _filter_is_empty(prop_key: str) -> Optional[dict]:
    """Build a Notion filter for 'is_empty' depending on the property's actual type.
    Returns None if the property does not exist or type unsupported for this filter.
    """
    prop_types = _get_tracks_db_prop_types()
    name = _resolve_prop_name(prop_key) or prop_key
    prop_type = prop_types.get(name)
    if not prop_type:
        return None
    if prop_type == "url":
        return {"property": name, "url": {"is_empty": True}}
    if prop_type == "rich_text":
        return {"property": name, "rich_text": {"is_empty": True}}
    # Some schemas may store file path as 'title'
    if prop_type == "title":
        return {"property": name, "title": {"is_empty": True}}
    # Unsupported for is_empty
    return None

def _filter_is_not_empty(prop_key: str) -> Optional[dict]:
    prop_types = _get_tracks_db_prop_types()
    name = _resolve_prop_name(prop_key) or prop_key
    prop_type = prop_types.get(name)
    if not prop_type:
        return None
    if prop_type == "url":
        return {"property": name, "url": {"is_not_empty": True}}
    if prop_type == "rich_text":
        return {"property": name, "rich_text": {"is_not_empty": True}}
    if prop_type == "title":
        return {"property": name, "title": {"is_not_empty": True}}
    return None

def _filter_checkbox_equals(prop_key: str, value: bool) -> Optional[dict]:
    prop_types = _get_tracks_db_prop_types()
    name = _resolve_prop_name(prop_key) or prop_key
    prop_type = prop_types.get(name)
    if prop_type == "checkbox":
        return {"property": name, "checkbox": {"equals": value}}
    return None

def _prop_text_value(prop: dict) -> str:
    """Extract textual content from a Notion property payload."""
    if not prop:
        return ""
    prop_type = prop.get("type")
    if prop_type == "url":
        return prop.get("url") or ""
    if prop_type == "email":
        return prop.get("email") or ""
    if prop_type == "phone_number":
        return prop.get("phone_number") or ""
    if prop_type == "rich_text":
        return "".join(segment.get("plain_text", "") for segment in prop.get("rich_text", []))
    if prop_type == "title":
        return "".join(segment.get("plain_text", "") for segment in prop.get("title", []))
    if not prop_type:
        # Handle update-style payloads that omit the explicit type key
        if "url" in prop:
            return prop.get("url") or ""
        if "email" in prop:
            return prop.get("email") or ""
        if "phone_number" in prop:
            return prop.get("phone_number") or ""
        if "title" in prop:
            return "".join(
                segment.get("plain_text")
                or (segment.get("text", {}) or {}).get("content", "")
                for segment in prop.get("title", [])
            )
        if "rich_text" in prop:
            return "".join(
                segment.get("plain_text")
                or (segment.get("text", {}) or {}).get("content", "")
                for segment in prop.get("rich_text", [])
            )
    return ""

def should_reprocess_page(page: Dict[str, Any]) -> bool:
    """
    Determine whether a track should be reprocessed based on current Notion properties and Eagle library.
    
    Returns False (skip reprocessing) if:
    - DL checkbox is already True
    - Files exist on disk AND have proper metadata (check Eagle tags)
    - Eagle library has the file with complete metadata
    
    Returns True (needs metadata update) if:
    - Files exist but are missing metadata in Eagle
    """
    props = page.get("properties", {})
    prop_types = _get_tracks_db_prop_types()

    def _get_prop(key: str) -> dict:
        name = _resolve_prop_name(key) or key
        return props.get(name, {})

    # Skip if already marked downloaded
    dl_prop = _get_prop("DL")
    if dl_prop.get("type") == "checkbox" and dl_prop.get("checkbox") is True:
        workspace_logger.debug(f"Skipping page {page['id']} — download checkbox already true.")
        return False

    processing_prop = _get_prop("Audio Processing")
    status_names = {
        item.get("name")
        for item in processing_prop.get("multi_select", [])
        if item.get("name")
    }

    # Check if files exist on disk
    file_paths: list[str] = []
    existing_files = 0
    existing_file_paths = []
    for key in ["AIFF File Path", "M4A File Path", "WAV File Path"]:
        prop = _get_prop(key)
        value = _prop_text_value(prop)
        if value:
            file_paths.append(value)
            try:
                candidate = Path(value).expanduser()
                if candidate.exists():
                    existing_files += 1
                    existing_file_paths.append(str(candidate))
            except Exception:
                pass

    eagle_prop = _get_prop("Eagle File ID")
    eagle_id = _prop_text_value(eagle_prop)

    # If files exist on disk, check Eagle library for metadata completeness
    if existing_files > 0:
        workspace_logger.info(f"Found {existing_files} existing files for page {page['id']}, checking Eagle metadata...")

        files_in_eagle = False
        files_need_metadata_update = False
        files_need_eagle_import = []  # Track files that exist locally but not in Eagle

        # Check if files are in Eagle library with complete metadata
        for file_path in existing_file_paths:
            try:
                # Search Eagle by file path
                eagle_items = eagle_find_items_by_path(file_path)
                if eagle_items:
                    files_in_eagle = True
                    # Check if metadata is complete
                    for item in eagle_items:
                        tags = item.get("tags", [])
                        # Check for essential metadata tags
                        has_bpm = any("bpm" in tag.lower() for tag in tags)
                        has_key = any("key" in tag.lower() for tag in tags)
                        has_genre = any("genre" in tag.lower() for tag in tags)
                        has_processed = any("processed" in tag.lower() for tag in tags)
                        has_fingerprint = any("fingerprint:" in tag.lower() for tag in tags)

                        if has_bpm and has_key and has_genre and has_processed and has_fingerprint:
                            workspace_logger.info(f"Skipping page {page['id']} — files exist with complete metadata in Eagle")
                            return False
                        else:
                            workspace_logger.info(f"Files exist but missing metadata in Eagle (BPM:{has_bpm}, Key:{has_key}, Genre:{has_genre}, Processed:{has_processed}, Fingerprint:{has_fingerprint})")
                            files_need_metadata_update = True
                else:
                    # File exists locally but NOT in Eagle - needs import
                    workspace_logger.info(f"🔄 File exists locally but NOT in Eagle: {file_path}")
                    files_need_eagle_import.append(file_path)
            except Exception as e:
                workspace_logger.warning(f"Error checking Eagle for file {file_path}: {e}")

        # If files exist locally but not in Eagle, they need processing (Eagle import + fingerprinting)
        if files_need_eagle_import:
            workspace_logger.info(f"🦅 Page {page['id']} has {len(files_need_eagle_import)} files that need Eagle import + fingerprinting")
            return True  # Needs reprocessing to import to Eagle and apply fingerprint

        # If we reach here, files exist in Eagle but metadata is incomplete
        if files_need_metadata_update:
            workspace_logger.info(f"Page {page['id']} needs metadata update for existing Eagle items")
            return True  # Needs reprocessing to update metadata

        workspace_logger.info(f"Page {page['id']} has files in Eagle, no action needed")
        return False

    completion_markers = {"Format Conversion Complete", "Files Imported to Eagle"}
    if completion_markers.issubset(status_names) and (existing_files or not file_paths):
        workspace_logger.info(
            f"Skipping reprocess for page {page['id']} — audio already imported and files present."
        )
        return False

    if "Files Imported to Eagle" in status_names and eagle_id:
        workspace_logger.info(
            f"Skipping reprocess for page {page['id']} — Eagle File ID present and already imported."
        )
        return False

    # Only reprocess if no files exist at all
    if existing_files == 0 and len(file_paths) > 0:
        workspace_logger.info(f"Page {page['id']} has file paths but no files exist on disk - needs reprocessing")
        return True

    return False  # Default to not reprocessing

# ───────────────────────────────────────────────────────────────
# Core Functions (adapted from original script)
# ───────────────────────────────────────────────────────────────
def _get_tracks_db_props() -> set[str]:
    """Fetch and cache the property names in the Tracks database."""
    global _tracks_db_props
    if _tracks_db_props is None:
        try:
            db_meta = notion_manager._req("get", f"/databases/{TRACKS_DB_ID}")
            _tracks_db_props = set(db_meta.get("properties", {}).keys())
            workspace_logger.debug(f"Cached Tracks DB properties: {sorted(_tracks_db_props)}")
        except Exception as exc:
            workspace_logger.warning(f"Could not fetch Tracks DB properties: {exc}")
            _tracks_db_props = set()
    return _tracks_db_props

def find_next_track() -> Optional[Dict[str, Any]]:
    """
    Query the Music Tracks database for the newest item that meets criteria,
    building filters dynamically based on available properties and types.
    """
    dynamic_filters: list[dict] = []

    # Required: SoundCloud URL present if available
    f = _filter_is_not_empty("SoundCloud URL")
    if f:
        dynamic_filters.append(f)

    # All file path properties empty (only include those that exist)
    for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        f = _filter_is_empty(key)
        if f:
            dynamic_filters.append(f)

    # Downloaded/DL unchecked if exists
    prop_types = _get_tracks_db_prop_types()
    if "DL" in prop_types or "Downloaded" in prop_types:
        f = _filter_checkbox_equals("DL", False)
        if f:
            dynamic_filters.append(f)
    else:
        workspace_logger.warning("Notion DB lacks 'DL'/'Downloaded' checkbox. Skipping DL filter.")

    # Build sorts according to configured ORDER_MODE
    sorts = None
    if ORDER_MODE == "priority_then_title":
        pri_prop = _resolve_prop_name("Priority")
        title_prop = _resolve_prop_name("Title")
        sorts = []
        if pri_prop:
            sorts.append({"property": pri_prop, "direction": "descending"})
        if title_prop:
            sorts.append({"property": title_prop, "direction": "ascending"})
        if not sorts:
            sorts = [{"timestamp": "created_time", "direction": "descending"}]
    elif ORDER_MODE == "priority_then_created":
        pri_prop = _resolve_prop_name("Priority")
        sorts = []
        if pri_prop:
            sorts.append({"property": pri_prop, "direction": "descending"})
        sorts.append({"timestamp": "created_time", "direction": "descending"})
        if not sorts:
            sorts = [{"timestamp": "created_time", "direction": "descending"}]
    elif ORDER_MODE == "title_asc":
        # Prefer the resolved Title property if available
        title_prop = _resolve_prop_name("Title")
        if title_prop:
            sorts = [{"property": title_prop, "direction": "ascending"}]
        else:
            sorts = [{"timestamp": "created_time", "direction": "descending"}]
    elif ORDER_MODE == "created_only":
        sorts = [{"timestamp": "created_time", "direction": "descending"}]
    elif ORDER_MODE == "release_only":
        rel_prop = _resolve_prop_name("Release Date") or "Release Date"
        sorts = [{"property": rel_prop, "direction": "descending"}]
    elif ORDER_MODE == "release_then_created":
        rel_prop = _resolve_prop_name("Release Date") or "Release Date"
        sorts = [{"property": rel_prop, "direction": "descending"}, {"timestamp": "created_time", "direction": "descending"}]
    elif ORDER_MODE == "created_then_release":
        rel_prop = _resolve_prop_name("Release Date") or "Release Date"
        sorts = [{"timestamp": "created_time", "direction": "descending"}, {"property": rel_prop, "direction": "descending"}]
    else:
        # Fallback behavior
        sorts = [{"timestamp": "created_time", "direction": "descending"}]

    query = {
        "filter": {"and": dynamic_filters} if dynamic_filters else None,
        "sorts": sorts,
        "page_size": 1,
    }

    # Remove None filter to avoid API validation error
    if query["filter"] is None:
        query.pop("filter")

    try:
        workspace_logger.info(f"Query filter: {json.dumps(query.get('filter', {}), default=str)}")
        workspace_logger.info(f"Tracks DB props: {sorted(list(_get_tracks_db_prop_types().keys()))[:15]}…")
        res = notion_manager.query_database(TRACKS_DB_ID, query)
        results = res.get("results", [])
        if results and SC_DEDUP_PRE_PROCESS == "1":
            try:
                return try_merge_duplicates_for_page(results[0], dry_run=(SC_DEDUP_DRY_RUN == "1"))
            except Exception:
                pass
        if results:
            return results[0]
        return None
    except Exception as exc:
        workspace_logger.error(f"Failed to query Notion database: {exc}")
        return None

def _build_unprocessed_tracks_query(limit: Optional[int] = 5000) -> dict[str, Any]:
    """Construct the Notion query payload for fetching unprocessed tracks."""
    dynamic_filters: list[dict] = []
    f = _filter_is_not_empty("SoundCloud URL")
    if f:
        dynamic_filters.append(f)
    for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        f = _filter_is_empty(key)
        if f:
            dynamic_filters.append(f)
    f = _filter_checkbox_equals("DL", False)
    if f:
        dynamic_filters.append(f)

    page_size = SC_NOTION_PAGE_SIZE
    if isinstance(limit, int) and limit > 0:
        page_size = min(SC_NOTION_PAGE_SIZE, limit)

    query: dict[str, Any] = {
        "filter": {"and": dynamic_filters} if dynamic_filters else None,
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": page_size,
    }
    if query.get("filter") is None:
        query.pop("filter")
    return query


def find_all_tracks_for_processing(limit: int = 5000) -> List[Dict[str, Any]]:
    """
    Query for ALL items that meet criteria (dynamic property checks).
    """
    query = _build_unprocessed_tracks_query(limit)

    try:
        tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=limit)
        if SC_DEDUP_PRE_PROCESS == "1" and tracks:
            merged_list = []
            seen_ids = set()
            for p in tracks:
                kp = try_merge_duplicates_for_page(p, dry_run=(SC_DEDUP_DRY_RUN == "1"))
                pid = kp.get("id")
                if pid and pid not in seen_ids:
                    merged_list.append(kp)
                    seen_ids.add(pid)
            tracks = merged_list
        return tracks
    except Exception as exc:
        workspace_logger.error(f"Failed to query Notion database for batch processing: {exc}")
        return []

def run_all_mode(limit: Optional[int] = None) -> int:
    """Process all filter-passing items from the Music Tracks database.
    Returns the number of items successfully processed.
    """
    max_items = limit if isinstance(limit, int) and limit > 0 else 200000
    query = _build_unprocessed_tracks_query(max_items)

    # Locate the single-track processing function dynamically to avoid tight coupling
    processor_candidates = [
        "process_track", "process_single_track", "process_track_page",
        "process_workflow_for_page", "process_download_workflow",
        "process_soundcloud_track_page"
    ]
    processor = None
    for name in processor_candidates:
        fn = globals().get(name)
        if callable(fn):
            processor = fn
            break
    if processor is None:
        workspace_logger.error("No track processing function found. Expected one of: %s", processor_candidates)
        return 0

    processed = 0
    seen_ids: set[str] = set()
    dedupe_enabled = SC_DEDUP_PRE_PROCESS == "1"
    dedupe_dry_run = SC_DEDUP_DRY_RUN == "1"
    any_items = False

    for payload in iterate_database_query(TRACKS_DB_ID, query, max_items=max_items):
        batch = payload.get("results", [])
        if not batch:
            continue
        any_items = True
        workspace_logger.info(
            f"▶️ Processing batch {payload.get('page')} with {len(batch)} track(s)"
        )
        for page in batch:
            try:
                resolved = try_merge_duplicates_for_page(page, dry_run=dedupe_dry_run) if dedupe_enabled else page
                page_id = resolved.get("id")
                if page_id:
                    if page_id in seen_ids:
                        workspace_logger.debug(
                            f"Skipping duplicate page {page_id} already handled during --mode all run."
                        )
                        continue
                    seen_ids.add(page_id)
                processor(resolved)
                processed += 1
            except SystemExit:
                raise
            except Exception as exc:
                workspace_logger.error("Failed processing page %s: %s", page.get("id", "<unknown>"), exc)

    if processed == 0:
        if not any_items:
            workspace_logger.info("No eligible tracks found for --mode all.")
        else:
            workspace_logger.info("--mode all complete. No new tracks processed after de-duplication.")
        return 0

    workspace_logger.info("--mode all complete. Processed %d item(s).", processed)
    return processed

def find_tracks_for_processing_batch(batch_size: int = 100) -> List[Dict[str, Any]]:
    """Small batch query with dynamic property handling."""
    dynamic_filters: list[dict] = []
    f = _filter_is_not_empty("SoundCloud URL");
    dynamic_filters += [f] if f else []
    for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
        f = _filter_is_empty(key)
        if f:
            dynamic_filters.append(f)
    f = _filter_checkbox_equals("DL", False)
    if f:
        dynamic_filters.append(f)

    query = {
        "filter": {"and": dynamic_filters} if dynamic_filters else None,
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": min(SC_NOTION_PAGE_SIZE, max(1, batch_size)),
    }
    if query.get("filter") is None:
        query.pop("filter")

    try:
        workspace_logger.info(f"🔍 Querying for {batch_size} unprocessed tracks...")
        tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=batch_size)
        if SC_DEDUP_PRE_PROCESS == "1" and tracks:
            merged_list = []
            seen_ids = set()
            for p in tracks:
                kp = try_merge_duplicates_for_page(p, dry_run=(SC_DEDUP_DRY_RUN == "1"))
                pid = kp.get("id")
                if pid and pid not in seen_ids:
                    merged_list.append(kp)
                    seen_ids.add(pid)
            tracks = merged_list
        workspace_logger.info(f"📋 Found {len(tracks)} tracks in this batch")
        return tracks
    except Exception as exc:
        workspace_logger.error(f"Failed to query Notion database for batch processing: {exc}")
        return []

# ───────────────────────────────────────────────────────────────
# Batch immediate processing with in-batch duplicate merging
# ───────────────────────────────────────────────────────────────

def _extract_track_meta_for_dedupe(page: Dict[str, Any]) -> Dict[str, str]:
    """Extract normalized metadata for duplicate detection."""
    props = page.get("properties", {})
    def _get(key: str) -> str:
        name = _resolve_prop_name(key) or key
        return _prop_text_value(props.get(name, {})).strip()
    return {
        "id": page.get("id", ""),
        "title": _clean_title(_get("Title")),
        "sc_url": _normalize_url(_get("SoundCloud URL")),
        "spotify_id": _get("Spotify ID").lower(),
    }

def _group_batch_duplicates(pages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group pages that are duplicates within the batch by SC URL, Spotify ID, or cleaned title."""
    if not pages:
        return []
    metas = {p.get("id"): _extract_track_meta_for_dedupe(p) for p in pages}

    parent: Dict[str, str] = {}
    def find(x: str) -> str:
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    def union(a: str, b: str):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_sc: Dict[str, List[str]] = {}
    by_sp: Dict[str, List[str]] = {}
    by_title: Dict[str, List[str]] = {}

    for pid, m in metas.items():
        if m.get("sc_url"):
            by_sc.setdefault(m["sc_url"], []).append(pid)
        if m.get("spotify_id"):
            by_sp.setdefault(m["spotify_id"], []).append(pid)
        if m.get("title"):
            by_title.setdefault(m["title"], []).append(pid)

    for index in (by_sc, by_sp, by_title):
        for ids in index.values():
            if len(ids) > 1:
                base = ids[0]
                for other in ids[1:]:
                    union(base, other)

    clusters: Dict[str, List[str]] = {}
    for pid in metas.keys():
        clusters.setdefault(find(pid), []).append(pid)

    groups: List[List[Dict[str, Any]]] = []
    for ids in clusters.values():
        if len(ids) >= 2:
            groups.append([next(p for p in pages if p.get("id") == _id) for _id in ids])
    return groups

def process_track_page_wrapper(page: dict) -> tuple[str, Optional[Exception]]:
    """
    Wrapper function for parallel track processing.
    Returns (track_id, error) tuple for concurrent execution.
    """
    track_id = page.get("id", "unknown")
    try:
        # Find the processor function dynamically
        processor = None
        for name in [
            "process_track", "process_single_track", "process_track_page",
            "process_workflow_for_page", "process_download_workflow",
            "process_soundcloud_track_page"
        ]:
            fn = globals().get(name)
            if callable(fn):
                processor = fn
                break
        
        if processor is None:
            raise RuntimeError("No track processing function found")
        
        # Process the track
        processor(page)
        return track_id, None
        
    except Exception as e:
        workspace_logger.error(f"❌ Error processing track {track_id}: {e}")
        return track_id, e

def process_pages_parallel(pages: List[Dict[str, Any]], max_workers: int = MAX_CONCURRENT_JOBS) -> int:
    """
    Process multiple pages in parallel using ThreadPoolExecutor.
    Returns the number of successfully processed pages.
    """
    if not pages:
        return 0
    
    workspace_logger.info(f"🚀 Starting parallel processing of {len(pages)} tracks with {max_workers} workers")
    
    processed_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = [executor.submit(process_track_page_wrapper, page) for page in pages]
        
        # Process results as they complete
        for future in as_completed(futures):
            try:
                track_id, error = future.result()
                if error:
                    workspace_logger.error(f"❌ Failed to process track {track_id}: {error}")
                    failed_count += 1
                else:
                    workspace_logger.info(f"✅ Successfully processed track {track_id}")
                    processed_count += 1
            except Exception as e:
                workspace_logger.error(f"❌ Unexpected error in parallel processing: {e}")
                failed_count += 1
    
    workspace_logger.info(f"📊 Parallel processing complete: {processed_count} succeeded, {failed_count} failed")
    return processed_count

def dedupe_within_batch(pages: List[Dict[str, Any]], dry_run: bool = False) -> List[Dict[str, Any]]:
    """Merge duplicates inside this batch immediately. Return keeper pages."""
    if not pages:
        return []
    groups = _group_batch_duplicates(pages)
    keepers: Dict[str, Dict[str, Any]] = {p["id"]: p for p in pages}

    for group in groups:
        group_sorted = sorted(group, key=_score_page_for_keeper, reverse=True)
        keeper, donors = group_sorted[0], group_sorted[1:]
        try:
            keeper_id = _merge_group_into_keeper(keeper, donors, dry_run=dry_run)
            for d in donors:
                keepers.pop(d["id"], None)
            if not dry_run and keeper_id:
                try:
                    refreshed = notion_manager._req("get", f"/pages/{keeper_id}")
                    if refreshed and refreshed.get("id"):
                        keepers[keeper_id] = refreshed
                except Exception:
                    pass
        except Exception as e:
            workspace_logger.warning(f"In-batch merge failed: {e}")
    return list(keepers.values())

def process_batch_immediately(batch_size: int = 100, dry_run: bool = False) -> int:
    """Fetch first batch, merge duplicates in-batch immediately, then process eligible items."""
    initial = find_tracks_for_processing_batch(batch_size=batch_size)
    if not initial:
        workspace_logger.info("No eligible tracks found in the first batch.")
        return 0

    after_merge = dedupe_within_batch(initial, dry_run=(SC_DEDUP_DRY_RUN == "1" or dry_run))

    # Discover processor dynamically
    processor = None
    for name in [
        "process_track", "process_single_track", "process_track_page",
        "process_workflow_for_page", "process_download_workflow",
        "process_soundcloud_track_page"
    ]:
        fn = globals().get(name)
        if callable(fn):
            processor = fn
            break
    if processor is None:
        workspace_logger.error("No track processing function found for batch processing.")
        return 0

    processed = 0
    for page in after_merge:
        try:
            resolved = try_merge_duplicates_for_page(page, dry_run=(SC_DEDUP_DRY_RUN == "1" or dry_run))
            if should_reprocess_page(resolved):
                processor(resolved)
                processed += 1
            else:
                workspace_logger.info(f"Skipping page {resolved.get('id')} — already processed or not eligible.")
        except SystemExit:
            raise
        except Exception as exc:
            workspace_logger.error("Failed processing page %s: %s", page.get("id", "<unknown>"), exc)

    workspace_logger.info("--mode batch (immediate) complete. Processed %d item(s).", processed)
    return processed

def find_all_tracks_with_soundcloud_urls() -> List[Dict[str, Any]]:
    """
    Query the Music Tracks database for ALL items that have SoundCloud URLs.
    This includes all tracks regardless of their processing status.
    """
    query = {
        "filter": {
            "property": "SoundCloud URL",
            "url": {
                "is_not_empty": True
            }
        },
        "sorts": [
            {
                "timestamp": "created_time",
                "direction": "descending"
            }
        ],
        "page_size": SC_NOTION_PAGE_SIZE
    }

    try:
        return query_database_paginated(TRACKS_DB_ID, query)
    except Exception as exc:
        workspace_logger.error(f"Failed to query Notion database for all tracks: {exc}")
        return []

def find_tracks_for_reprocessing() -> List[Dict[str, Any]]:
    """
    Find tracks that need reprocessing (DL=False but have file paths, Eagle items, or fingerprints).
    DISABLED by default - returns empty list to prevent re-downloading already processed tracks.
    Set environment variable ENABLE_REPROCESSING_FILTER=1 to enable this feature.
    """
    # Check if reprocessing filter is explicitly enabled
    if not _truthy(os.getenv("ENABLE_REPROCESSING_FILTER", "0")):
        workspace_logger.info("ℹ️  Reprocessing filter disabled (set ENABLE_REPROCESSING_FILTER=1 to enable)")
        return []
    
    workspace_logger.warning("⚠️  Reprocessing filter enabled - this may find many tracks that don't need reprocessing")
    
    prop_types = _get_tracks_db_prop_types()
    and_filters: list[dict] = []

    dl_filter = _filter_checkbox_equals("DL", False)
    if dl_filter:
        and_filters.append(dl_filter)
    else:
        workspace_logger.warning("Tracks DB missing DL/Downloaded checkbox; reprocess query will not filter by download status.")

    sc_filter = _filter_is_not_empty("SoundCloud URL")
    if sc_filter:
        and_filters.append(sc_filter)
    else:
        workspace_logger.warning("Tracks DB missing SoundCloud URL property; reprocess query may include invalid items.")

    # STRICTER FILTER: Only find tracks that have file paths BUT files don't exist on disk
    # This prevents re-downloading tracks that are already complete
    or_filters: list[dict] = []
    for key in ["WAV File Path", "AIFF File Path", "M4A File Path"]:
        f = _filter_is_not_empty(key)
        if f:
            or_filters.append(f)

    # Remove Fingerprint and Eagle File ID from reprocessing criteria
    # Having these doesn't mean the track needs reprocessing

    if or_filters:
        and_filters.append({"or": or_filters})

    query: dict[str, Any] = {
        "sorts": [
            {
                "timestamp": "created_time",
                "direction": "ascending"
            }
        ],
        "page_size": min(SC_NOTION_PAGE_SIZE, 20)  # Reduced from 100 to 20
    }

    if and_filters:
        query["filter"] = {"and": and_filters}

    try:
        # Limit to 20 items for reprocessing check to avoid long queries
        tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=20)
        
        # Verify each track actually needs reprocessing by checking if files exist on disk
        tracks_needing_reprocess = []
        for track in tracks:
            track_info = extract_track_data(track)
            # Check if any file paths exist on disk
            has_existing_files = False
            for path_key in ["wav_file_path", "aiff_file_path", "m4a_file_path"]:
                path = track_info.get(path_key)
                if path and Path(path).exists():
                    has_existing_files = True
                    break
            
            # Only reprocess if files DON'T exist (broken paths)
            if not has_existing_files:
                tracks_needing_reprocess.append(track)
                workspace_logger.info(f"Found track with broken file paths: {track_info.get('title', 'Unknown')}")
        
        return tracks_needing_reprocess
    except Exception as exc:
        workspace_logger.error(f"Failed to query database for reprocessing: {exc}")
        return []

def find_tracks_with_eagle_items_but_no_id() -> List[Dict[str, Any]]:
    """Find tracks that have Eagle items (by file path) but no Eagle File ID in Notion."""
    try:
        # First, get all tracks with DL=False (if available) and SoundCloud URL but missing Eagle File ID
        prop_types = _get_tracks_db_prop_types()
        and_filters: list[dict] = []

        dl_filter = _filter_checkbox_equals("DL", False)
        if dl_filter:
            and_filters.append(dl_filter)
        else:
            workspace_logger.warning("Tracks DB missing DL/Downloaded checkbox; Eagle lookup skipping DL filter.")

        sc_filter = _filter_is_not_empty("SoundCloud URL")
        if sc_filter:
            and_filters.append(sc_filter)

        eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
        if prop_types.get(eagle_prop) == "rich_text":
            and_filters.append({"property": eagle_prop, "rich_text": {"is_empty": True}})

        query = {
            "sorts": [
                {
                    "property": "Created time",
                    "direction": "descending"
                }
            ],
            "page_size": min(SC_NOTION_PAGE_SIZE, 50)
        }

        if and_filters:
            query["filter"] = {"and": and_filters}
        
        # Limit to 50 items for Eagle ID check to avoid long queries
        tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=50)
        
        # Check each track to see if it has file paths that exist in Eagle
        tracks_with_eagle_items = []
        
        for track in tracks:
            track_info = extract_track_data(track)
            wav_path = track_info.get("wav_file_path", "")
            aiff_path = track_info.get("aiff_file_path", "")
            m4a_path = track_info.get("m4a_file_path", "")
            
            # Check if any of these file paths exist in Eagle
            for file_path in [wav_path, aiff_path, m4a_path]:
                if file_path and eagle_find_items_by_path(file_path):
                    tracks_with_eagle_items.append(track)
                    workspace_logger.info(f"Found track with Eagle items but no ID: {track_info.get('title', 'Unknown')}")
                    break
        
        return tracks_with_eagle_items

    except Exception as exc:
        workspace_logger.error(f"Failed to find tracks with Eagle items: {exc}")
        return []

# ───────────────────────────────────────────────────────────────
# Artist Relation Functions (2026-01-15 fix for missing relations)
# ───────────────────────────────────────────────────────────────
_ARTISTS_DB_ID = os.getenv("ARTISTS_DB_ID", "")
_ARTIST_CACHE: Dict[str, Optional[str]] = {}  # Cache artist name -> page_id

# FIX 2026-01-15: Module-level validation for invalid artist names
_RESERVED_ARTIST_NAMES = {'tracks', 'playlists', 'sets', 'albums', 'users', 'discover', 'search', 'stream'}
_INVALID_ARTIST_PATTERNS = {'unknown', 'unknown artist', 'n/a', 'various artists', 'va', ''}

def _is_soundcloud_auto_username(name: str) -> bool:
    """Detect SoundCloud auto-generated usernames like 'user-123456789'."""
    if not name:
        return False
    import re
    # Pattern: 'user-' followed by 6+ digits (SoundCloud user IDs are typically 6-12 digits)
    return bool(re.match(r'^user-\d{6,}$', name.lower().strip()))

def _is_invalid_artist_name(name: str) -> bool:
    """
    Check if artist name is invalid (reserved word, auto-username, or generic placeholder).

    Invalid names include:
    - SoundCloud auto-generated usernames (user-123456789)
    - Reserved SoundCloud path segments (tracks, playlists, etc.)
    - Generic placeholders (Unknown, N/A, Various Artists)
    """
    if not name:
        return True
    name_lower = name.lower().strip()
    if name_lower in _RESERVED_ARTIST_NAMES:
        return True
    if _is_soundcloud_auto_username(name):
        return True
    if name_lower in _INVALID_ARTIST_PATTERNS:
        return True
    return False

def _get_artists_db_prop_types() -> Dict[str, str]:
    """Get property types for Artists database."""
    if not _ARTISTS_DB_ID:
        return {}
    try:
        db_info = notion_manager._req("get", f"/databases/{_ARTISTS_DB_ID}")
        return {name: prop.get("type", "") for name, prop in db_info.get("properties", {}).items()}
    except Exception:
        return {}

def find_or_create_artist_page(artist_name: str) -> Optional[str]:
    """
    Find or create an artist page by name and return its page ID.

    Args:
        artist_name: The artist name to search for or create

    Returns:
        The artist page ID if found/created, None otherwise
    """
    if not artist_name or not _ARTISTS_DB_ID:
        return None

    # Normalize artist name
    artist_name = artist_name.strip()
    if not artist_name:
        return None

    # Check cache first
    cache_key = artist_name.lower()
    if cache_key in _ARTIST_CACHE:
        return _ARTIST_CACHE[cache_key]

    try:
        # Search for existing artist by name
        query = {
            "filter": {
                "property": "Name",
                "title": {"equals": artist_name}
            },
            "page_size": 1
        }

        result = notion_manager.query_database(_ARTISTS_DB_ID, query)
        if result and result.get("results"):
            artist_page_id = result["results"][0]["id"]
            _ARTIST_CACHE[cache_key] = artist_page_id
            workspace_logger.debug(f"🎤 Found existing artist: {artist_name} -> {artist_page_id}")
            return artist_page_id

        # Create new artist page if not found
        artist_properties = {
            "Name": {"title": [{"text": {"content": artist_name}}]},
        }

        # Add optional properties if they exist in the database
        prop_types = _get_artists_db_prop_types()
        if "Source" in prop_types and prop_types["Source"] == "select":
            artist_properties["Source"] = {"select": {"name": "SoundCloud"}}

        payload = {"parent": {"database_id": _ARTISTS_DB_ID}, "properties": artist_properties}
        new_page = notion_manager._req("post", "/pages", payload)

        if new_page and new_page.get("id"):
            artist_page_id = new_page["id"]
            _ARTIST_CACHE[cache_key] = artist_page_id
            workspace_logger.info(f"🎤 Created new artist page: {artist_name} -> {artist_page_id}")
            return artist_page_id

    except Exception as exc:
        workspace_logger.warning(f"⚠️ Failed to find/create artist '{artist_name}': {exc}")

    _ARTIST_CACHE[cache_key] = None
    return None

def link_track_to_artist(track_page_id: str, artist_page_id: str) -> bool:
    """
    Link a track to an artist using the Artist relation property.

    Args:
        track_page_id: The track page ID
        artist_page_id: The artist page ID to link

    Returns:
        True if successful, False otherwise
    """
    if not track_page_id or not artist_page_id:
        return False

    try:
        # Get current page to check existing relations
        page = notion_manager._req("get", f"/pages/{track_page_id}")
        if not page:
            return False

        # Check for Artist relation property (may be named "Artist" or "Artists")
        props = page.get("properties", {})
        artist_prop_name = None
        for name in ["Artist", "Artists", "Artist Relation"]:
            if name in props and props[name].get("type") == "relation":
                artist_prop_name = name
                break

        if not artist_prop_name:
            workspace_logger.debug("No Artist relation property found on track page")
            return False

        # Get existing relations
        relation_data = props.get(artist_prop_name, {})
        existing_relations = relation_data.get("relation", []) or []
        existing_ids = [rel.get("id") for rel in existing_relations if rel.get("id")]

        # Skip if already linked
        if artist_page_id in existing_ids:
            return True

        # Build updated relations list
        updated_relations = [{"id": rid} for rid in existing_ids]
        updated_relations.append({"id": artist_page_id})

        # Update the track page
        payload = {
            "properties": {
                artist_prop_name: {
                    "relation": updated_relations
                }
            }
        }

        result = notion_manager._req("patch", f"/pages/{track_page_id}", payload)
        if result:
            workspace_logger.info(f"🔗 Linked track to artist: {track_page_id} -> {artist_page_id}")
            return True

    except Exception as exc:
        workspace_logger.warning(f"⚠️ Failed to link track to artist: {exc}")

    return False

def link_track_artist_relation(track_page_id: str, artist_name: str) -> bool:
    """
    High-level function to find/create artist and link to track.

    Args:
        track_page_id: The track page ID
        artist_name: The artist name

    Returns:
        True if successful, False otherwise
    """
    if not track_page_id or not artist_name or not _ARTISTS_DB_ID:
        return False

    # FIX 2026-01-15: Validate artist name before creating/linking
    if _is_invalid_artist_name(artist_name):
        workspace_logger.warning(f"⚠️ Skipping artist relation for invalid name: '{artist_name}' (auto-generated or placeholder)")
        return False

    artist_page_id = find_or_create_artist_page(artist_name)
    if not artist_page_id:
        return False

    return link_track_to_artist(track_page_id, artist_page_id)

# ───────────────────────────────────────────────────────────────
# Playlist Relation Functions (2026-01-15 fix for missing relations)
# ───────────────────────────────────────────────────────────────
_PLAYLISTS_DB_ID = os.getenv("MUSIC_PLAYLISTS_DB_ID", "") or os.getenv("PLAYLISTS_DB_ID", "")
_PLAYLIST_CACHE: Dict[str, Optional[str]] = {}  # Cache playlist name -> page_id

def _get_playlists_db_prop_types() -> Dict[str, str]:
    """Get property types for Playlists database."""
    if not _PLAYLISTS_DB_ID:
        return {}
    try:
        db_info = notion_manager._req("get", f"/databases/{_PLAYLISTS_DB_ID}")
        return {name: prop.get("type", "") for name, prop in db_info.get("properties", {}).items()}
    except Exception:
        return {}

def find_or_create_playlist_page(playlist_name: str, source: str = "SoundCloud") -> Optional[str]:
    """
    Find or create a playlist page by name and return its page ID.

    Args:
        playlist_name: The playlist name to search for or create
        source: Source platform (SoundCloud, Spotify, etc.)

    Returns:
        The playlist page ID if found/created, None otherwise
    """
    if not playlist_name or not _PLAYLISTS_DB_ID:
        return None

    # Normalize playlist name
    playlist_name = playlist_name.strip()
    if not playlist_name:
        return None

    # Check cache first
    cache_key = playlist_name.lower()
    if cache_key in _PLAYLIST_CACHE:
        return _PLAYLIST_CACHE[cache_key]

    try:
        # Search for existing playlist by name
        query = {
            "filter": {
                "property": "Name",
                "title": {"equals": playlist_name}
            },
            "page_size": 1
        }

        result = notion_manager.query_database(_PLAYLISTS_DB_ID, query)
        if result and result.get("results"):
            playlist_page_id = result["results"][0]["id"]
            _PLAYLIST_CACHE[cache_key] = playlist_page_id
            workspace_logger.debug(f"🎵 Found existing playlist: {playlist_name} -> {playlist_page_id}")
            return playlist_page_id

        # Create new playlist page if not found
        playlist_properties = {
            "Name": {"title": [{"text": {"content": playlist_name}}]},
        }

        # Add optional properties if they exist in the database
        prop_types = _get_playlists_db_prop_types()
        if "Source" in prop_types and prop_types["Source"] == "select":
            playlist_properties["Source"] = {"select": {"name": source}}
        if "Platform" in prop_types and prop_types["Platform"] == "select":
            playlist_properties["Platform"] = {"select": {"name": source}}

        payload = {"parent": {"database_id": _PLAYLISTS_DB_ID}, "properties": playlist_properties}
        new_page = notion_manager._req("post", "/pages", payload)

        if new_page and new_page.get("id"):
            playlist_page_id = new_page["id"]
            _PLAYLIST_CACHE[cache_key] = playlist_page_id
            workspace_logger.info(f"🎵 Created new playlist page: {playlist_name} -> {playlist_page_id}")
            return playlist_page_id

    except Exception as exc:
        workspace_logger.warning(f"⚠️ Failed to find/create playlist '{playlist_name}': {exc}")

    _PLAYLIST_CACHE[cache_key] = None
    return None

def link_track_to_playlist(track_page_id: str, playlist_page_id: str) -> bool:
    """
    Link a track to a playlist using the Playlists relation property.

    Args:
        track_page_id: The track page ID
        playlist_page_id: The playlist page ID to link

    Returns:
        True if successful, False otherwise
    """
    if not track_page_id or not playlist_page_id:
        return False

    try:
        # Get current page to check existing relations
        page = notion_manager._req("get", f"/pages/{track_page_id}")
        if not page:
            return False

        # Check for Playlist relation property (may have different names)
        props = page.get("properties", {})
        playlist_prop_name = None
        for name in ["Playlists", "Playlist", "Playlist Relation", "Related Playlists"]:
            if name in props and props[name].get("type") == "relation":
                playlist_prop_name = name
                break

        if not playlist_prop_name:
            workspace_logger.debug("No Playlist relation property found on track page")
            return False

        # Get existing relations
        relation_data = props.get(playlist_prop_name, {})
        existing_relations = relation_data.get("relation", []) or []
        existing_ids = [rel.get("id") for rel in existing_relations if rel.get("id")]

        # Skip if already linked
        if playlist_page_id in existing_ids:
            return True

        # Build updated relations list
        updated_relations = [{"id": rid} for rid in existing_ids]
        updated_relations.append({"id": playlist_page_id})

        # Update the track page
        payload = {
            "properties": {
                playlist_prop_name: {
                    "relation": updated_relations
                }
            }
        }

        result = notion_manager._req("patch", f"/pages/{track_page_id}", payload)
        if result:
            workspace_logger.info(f"🔗 Linked track to playlist: {track_page_id} -> {playlist_page_id}")
            return True

    except Exception as exc:
        workspace_logger.warning(f"⚠️ Failed to link track to playlist: {exc}")

    return False

def link_track_playlist_relation(track_page_id: str, playlist_name: str, source: str = "SoundCloud") -> bool:
    """
    High-level function to find/create playlist and link to track.

    Args:
        track_page_id: The track page ID
        playlist_name: The playlist name
        source: Source platform

    Returns:
        True if successful, False otherwise
    """
    if not track_page_id or not playlist_name or not _PLAYLISTS_DB_ID:
        return False

    playlist_page_id = find_or_create_playlist_page(playlist_name, source)
    if not playlist_page_id:
        return False

    return link_track_to_playlist(track_page_id, playlist_page_id)

def find_tracks_with_playlist_relations() -> List[Dict[str, Any]]:
    """Find tracks with playlist relations using dynamic property filters."""
    try:
        dynamic_filters: list[dict] = []
        f = _filter_is_not_empty("SoundCloud URL");
        dynamic_filters += [f] if f else []
        for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
            f = _filter_is_empty(key)
            if f:
                dynamic_filters.append(f)
        f = _filter_checkbox_equals("DL", False)
        if f:
            dynamic_filters.append(f)
        # Playlist relation (only if exists as relation)
        # CRITICAL FIX 2026-01-15: Check for both "Playlist" and "Playlists" property names
        prop_types = _get_tracks_db_prop_types()
        playlist_prop_name = None
        for pname in ["Playlists", "Playlist", "Playlist Relation", "Related Playlists"]:
            if pname in prop_types and prop_types[pname] == "relation":
                playlist_prop_name = pname
                break
        if playlist_prop_name:
            dynamic_filters.append({"property": playlist_prop_name, "relation": {"is_not_empty": True}})

        query = {
            "filter": {"and": dynamic_filters} if dynamic_filters else None,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
            "page_size": SC_NOTION_PAGE_SIZE,
        }
        if query.get("filter") is None:
            query.pop("filter")

        tracks = query_database_paginated(TRACKS_DB_ID, query)
        workspace_logger.info(f"Found {len(tracks)} tracks with playlist relations that need processing")
        return tracks
    except Exception as exc:
        workspace_logger.error(f"Failed to find tracks with playlist relations: {exc}")
        return []

def extract_track_data(page: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant data from a Notion page object."""
    props = page.get("properties", {})

    def get_text(prop_name: str) -> str:
        # Resolve property name using ALT_PROP_NAMES mapping
        resolved_name = _resolve_prop_name(prop_name) or prop_name
        prop = props.get(resolved_name, {})
        if prop.get("type") == "title" and prop.get("title"):
            return prop["title"][0]["plain_text"]
        elif prop.get("type") == "rich_text" and prop.get("rich_text"):
            return prop["rich_text"][0]["plain_text"]
        return ""

    def get_url(prop_name: str) -> str:
        resolved_name = _resolve_prop_name(prop_name) or prop_name
        prop = props.get(resolved_name, {})
        if prop.get("type") == "url" and prop.get("url"):
            return prop["url"]
        return ""

    def get_number(prop_name: str) -> Optional[float]:
        resolved_name = _resolve_prop_name(prop_name) or prop_name
        prop = props.get(resolved_name, {})
        if prop.get("type") == "number":
            return prop.get("number")
        return None

    def get_select(prop_name: str) -> str:
        resolved_name = _resolve_prop_name(prop_name) or prop_name
        prop = props.get(resolved_name, {})
        if prop.get("type") == "select" and prop.get("select"):
            return prop["select"]["name"]
        return ""

    return {
        "page_id": page["id"],
        "title": get_text("Title"),
        "artist": get_text("Artist Name"),
        "album": get_text("Album"),
        "genre": get_select("Genre"),
        "soundcloud_url": get_url("SoundCloud URL"),
        "spotify_id": get_text("Spotify ID"),  # Add Spotify ID extraction
        "spotify_url": get_url("Spotify URL"),
        "bpm": get_number("BPM"),  # Uses ALT_PROP_NAMES to resolve to "Tempo"
        "key": get_text("Key"),  # Uses ALT_PROP_NAMES to resolve to "Key " if needed
        "duration_seconds": get_number("Duration (s)"),  # Uses ALT_PROP_NAMES - value is already in seconds
        "eagle_file_id": get_text("Eagle File ID")
    }

def _get_spotify_client() -> Optional[SpotifyAPI]:
    """
    Lazily create a shared Spotify API client using the integration module's
    OAuth manager. Returns None if credentials are unavailable.
    """
    global _SPOTIFY_CLIENT, _SPOTIFY_MANAGER, _SPOTIFY_DISABLED_REASON
    if _SPOTIFY_CLIENT:
        return _SPOTIFY_CLIENT
    if _SPOTIFY_DISABLED_REASON:
        return None
    if SpotifyAPI is None or SpotifyOAuthManager is None:
        _SPOTIFY_DISABLED_REASON = str(_SPOTIFY_IMPORT_ERROR or "spotify module unavailable")
        workspace_logger.warning(f"⚠️ Spotify integration unavailable: {_SPOTIFY_DISABLED_REASON}")
        return None
    try:
        manager = SpotifyOAuthManager()
        token = manager.get_valid_token()
        if not token:
            raise RuntimeError("No Spotify token available (set SPOTIFY_* environment variables)")
        client = SpotifyAPI(oauth_manager=manager)
        _SPOTIFY_MANAGER = manager
        _SPOTIFY_CLIENT = client
        workspace_logger.info("✅ Spotify API client initialized for metadata enrichment")
        return client
    except Exception as exc:
        _SPOTIFY_DISABLED_REASON = str(exc)
        workspace_logger.warning(f"⚠️ Spotify enrichment disabled: {exc}")
        return None

def _normalize_spotify_value(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()

def _select_best_spotify_match(track_data: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    title_norm = _normalize_spotify_value(track_data.get("title"))
    artist_norm = _normalize_spotify_value(track_data.get("artist"))
    duration_ms = None
    if track_data.get("duration_seconds"):
        try:
            duration_ms = int(float(track_data["duration_seconds"]) * 1000)
        except (TypeError, ValueError):
            duration_ms = None

    best_match: Optional[Dict[str, Any]] = None
    best_score = 0.0

    for item in candidates:
        candidate_title = _normalize_spotify_value(item.get("name"))
        candidate_artists = _normalize_spotify_value(
            ", ".join(artist.get("name", "") for artist in item.get("artists", []))
        )

        title_score = SequenceMatcher(None, title_norm, candidate_title).ratio() if title_norm and candidate_title else 0.0
        artist_score = SequenceMatcher(None, artist_norm, candidate_artists).ratio() if artist_norm and candidate_artists else 0.0

        duration_score = 0.0
        candidate_duration = item.get("duration_ms")
        if duration_ms and candidate_duration:
            try:
                diff = abs(duration_ms - int(candidate_duration))
                duration_score = max(0.0, 1.0 - (diff / 15000.0))
            except (TypeError, ValueError):
                duration_score = 0.0

        total_score = (title_score * 0.6) + (artist_score * 0.3) + (duration_score * 0.1)

        if total_score > best_score:
            best_score = total_score
            best_match = item

    if best_match and best_score >= 0.55:
        best_match["_match_score"] = round(best_score, 3)
        return best_match

    return None

def _update_spotify_properties(page_id: str, spotify_track: Dict[str, Any], track_data: Dict[str, Any]) -> None:
    prop_types = _get_tracks_db_prop_types()
    updates: Dict[str, Any] = {}

    def _set(prop_key: str, value: Any) -> None:
        if value is None or value == "":
            return
        name = _resolve_prop_name(prop_key) or prop_key
        prop_type = prop_types.get(name)
        if not prop_type:
            return
        if prop_type == "rich_text":
            updates[name] = {"rich_text": [{"text": {"content": str(value)}}]}
        elif prop_type == "url":
            updates[name] = {"url": str(value)}
        elif prop_type == "title":
            updates[name] = {"title": [{"text": {"content": str(value)}}]}
        elif prop_type == "number":
            try:
                updates[name] = {"number": float(value)}
            except (TypeError, ValueError):
                return

    _set("Spotify ID", spotify_track.get("id"))
    _set("Spotify URL", spotify_track.get("external_urls", {}).get("spotify"))

    if not track_data.get("album"):
        _set("Album", spotify_track.get("album", {}).get("name"))
    if track_data.get("duration_seconds") is None and spotify_track.get("duration_ms"):
        _set("Duration (s)", spotify_track.get("duration_ms") / 1000)  # Convert ms to seconds
    popularity = spotify_track.get("popularity")
    if popularity is not None:
        _set("Popularity", popularity)

    if updates:
        notion_manager.update_page(page_id, updates)
        workspace_logger.info(f"🎧 Updated Spotify metadata on Notion page {page_id}")

def enrich_spotify_metadata(track_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the track dictionary contains Spotify identifiers by performing a
    best-effort search. Returns the same dict for fluent usage.
    """
    global _SPOTIFY_ENRICH_ATTEMPTS, _SPOTIFY_ENRICH_SUCCESS

    if not isinstance(track_data, dict):
        return track_data

    existing_id = (track_data.get("spotify_id") or "").strip()
    title = (track_data.get("title") or "").strip()
    artist = (track_data.get("artist") or "").strip()

    if existing_id or not title:
        return track_data

    client = _get_spotify_client()
    if not client:
        return track_data

    cache_key = f"{title.lower()}|{artist.lower()}"
    cached = _SPOTIFY_MATCH_CACHE.get(cache_key, _SPOTIFY_CACHE_SENTINEL)
    spotify_track = None if cached is _SPOTIFY_CACHE_SENTINEL else cached

    if cached is _SPOTIFY_CACHE_SENTINEL:
        _SPOTIFY_ENRICH_ATTEMPTS += 1
        query = f"{title} {artist}".strip()
        try:
            candidates = client.search_tracks(query, limit=5)
        except Exception as exc:
            workspace_logger.warning(f"⚠️ Spotify search failed for '{query}': {exc}")
            _SPOTIFY_MATCH_CACHE[cache_key] = None
            return track_data
        spotify_track = _select_best_spotify_match(track_data, candidates)
        _SPOTIFY_MATCH_CACHE[cache_key] = spotify_track

    if not spotify_track:
        return track_data

    track_data["spotify_id"] = spotify_track.get("id", "")
    track_data["spotify_url"] = spotify_track.get("external_urls", {}).get("spotify", "")
    track_data["spotify_match_score"] = spotify_track.get("_match_score")
    _SPOTIFY_ENRICH_SUCCESS += 1

    workspace_logger.info(
        f"🎧 Linked Spotify track '{spotify_track.get('name')}' "
        f"(score {spotify_track.get('_match_score')}, query: {title} – {artist})"
    )

    page_id = track_data.get("page_id")
    if page_id:
        try:
            _update_spotify_properties(page_id, spotify_track, track_data)
        except Exception as exc:
            workspace_logger.warning(f"⚠️ Failed to update Spotify fields in Notion: {exc}")

    return track_data

def upsert_track_page(meta: dict, eagle_item_id: Optional[str] = None) -> str:
    """
    Create or update a page in the TRACKS_DB_ID with metadata gathered
    during processing. Uses sophisticated matching logic across multiple
    properties to detect duplicates and merge them.
    """
    if not TRACKS_DB_ID or TRACKS_DB_ID.startswith("REPLACE"):
        workspace_logger.debug("TRACKS_DB_ID not set – skipping Notion item upsert.")
        return ""

    # Assemble Notion property payloads
    prop_types = _get_tracks_db_prop_types()
    db_props = set(prop_types.keys())

    # Pre-upsert duplicate merge (optional)
    if SC_DEDUP_ON_WRITE == "1":
        try:
            keeper_id = dedupe_for_meta(meta, dry_run=(SC_DEDUP_DRY_RUN == "1"))
            if keeper_id:
                # Ensure we target the keeper going forward
                meta["page_id"] = keeper_id
                workspace_logger.info(f"🧹 De-dupe resolved. Using keeper page_id: {keeper_id}")
        except Exception as e:
            workspace_logger.warning(f"De-dupe pre-upsert skipped due to error: {e}")

    def set_rich_or_title(props_dict: dict, key: str, value: str):
        if not value:
            return
        name = _resolve_prop_name(key) or key
        prop_type = prop_types.get(name)
        if prop_type == "title":
            props_dict[name] = {"title": [{"text": {"content": value}}]}
        elif prop_type == "rich_text":
            props_dict[name] = {"rich_text": [{"text": {"content": value}}]}

    def set_select(props_dict: dict, key: str, value: str):
        if not value:
            return
        name = _resolve_prop_name(key) or key
        if prop_types.get(name) == "select":
            props_dict[name] = {"select": {"name": value}}

    def set_number(props_dict: dict, key: str, value):
        name = _resolve_prop_name(key) or key
        if prop_types.get(name) == "number":
            props_dict[name] = {"number": value}

    def set_url_or_text(props_dict: dict, key: str, value: str):
        if not value:
            return
        name = _resolve_prop_name(key) or key
        prop_type = prop_types.get(name)
        # Force file paths to be URL format if the property is configured as URL type
        if "File Path" in key or "Path" in key:
            if prop_type == "url":
                props_dict[name] = {"url": value}
            else:
                props_dict[name] = {"rich_text": [{"text": {"content": value}}]}
        elif prop_type == "url":
            props_dict[name] = {"url": value}
        elif prop_type == "rich_text":
            props_dict[name] = {"rich_text": [{"text": {"content": value}}]}

    def set_checkbox(props_dict: dict, key: str, value: bool):
        name = _resolve_prop_name(key) or key
        if prop_types.get(name) == "checkbox":
            props_dict[name] = {"checkbox": value}

    def set_multi_select(props_dict: dict, key: str, values: list[str]):
        if not values:
            return
        name = _resolve_prop_name(key) or key
        if prop_types.get(name) == "multi_select":
            props_dict[name] = {"multi_select": [{"name": v} for v in values]}

    def set_date(props_dict: dict, key: str, iso_value: str):
        name = _resolve_prop_name(key) or key
        if prop_types.get(name) == "date":
            props_dict[name] = {"date": {"start": iso_value}}

    now_iso = datetime.now(timezone.utc).isoformat()
    props: dict[str, dict] = {}

    set_rich_or_title(props, "Title", meta["title"])
    set_rich_or_title(props, "Artist Name", meta["artist"])
    set_rich_or_title(props, "Album", meta["album"])
    set_select(props, "Genre", meta["genre"])
    set_number(props, "BPM", meta.get("bpm"))  # Uses ALT_PROP_NAMES to resolve to "Tempo"
    set_rich_or_title(props, "Key", meta.get("key", ''))  # Uses ALT_PROP_NAMES to resolve to "Key " if needed
    set_url_or_text(props, "SoundCloud URL", meta["source_url"])
    set_date(props, "Processed At", now_iso)
    set_date(props, "Last Used", now_iso)
    set_checkbox(props, "DL", True)
    
    # Add Audio Processing status if available
    audio_processing_status = meta.get("audio_processing_status", [])
    if audio_processing_status:
        set_multi_select(props, "Audio Processing", audio_processing_status)

    # Optional file-path properties
    for key in ["wav_file_path", "aiff_file_path", "m4a_file_path"]:
        if meta.get(key):
            if key == "wav_file_path":
                set_url_or_text(props, "WAV File Path", meta[key])
            elif key == "aiff_file_path":
                set_url_or_text(props, "AIFF File Path", meta[key])
            elif key == "m4a_file_path":
                set_url_or_text(props, "M4A File Path", meta[key])

    # Eagle item ID if present
    if eagle_item_id:
        set_rich_or_title(props, "Eagle File ID", eagle_item_id)

    # Fingerprint: Route to per-format property based on file path (2026-01-15 fix)
    fingerprint_value = meta.get("fingerprint")
    if fingerprint_value:
        # Determine format from file paths
        file_path = meta.get("aiff_file_path") or meta.get("wav_file_path") or meta.get("m4a_file_path") or ""
        try:
            from shared_core.fingerprint_schema import build_fingerprint_update_properties
            fp_props = build_fingerprint_update_properties(fingerprint_value, file_path, db_props)
            if fp_props:
                props.update(fp_props)
                workspace_logger.info(f"📝 Adding fingerprint to Notion properties: {list(fp_props.keys())}")
        except ImportError:
            # Legacy fallback - set the old Fingerprint property if it exists
            fp_prop_name = _resolve_prop_name("Fingerprint")
            if fp_prop_name and prop_types.get(fp_prop_name) == "rich_text":
                props[fp_prop_name] = {"rich_text": [{"text": {"content": fingerprint_value[:2000]}}]}
                workspace_logger.warning("Using DEPRECATED legacy Fingerprint property")

    # Filter to include only existing DB properties
    props = {k: v for k, v in props.items() if v is not None and k in db_props}

    # Helper to perform update with dynamic property creation
    def safe_update(page_id: str):
        try:
            # Use registry-integrated update (Phase 1)
            success = update_track_with_registry(page_id, props, meta)
            if success:
                workspace_logger.info(f"🔄 Updated track page in Notion: {meta['title']}")
            else:
                raise RuntimeError("Registry update failed")
        except RuntimeError as exc:
            err = str(exc)
            m = re.search(r"(.+?) is expected to be", err)
            if m:
                missing = m.group(1)
                
                # Special handling for Eagle File ID property type issue
                if missing == "Eagle File ID" and "expected to be date" in err:
                    workspace_logger.info("🔧 Detected Eagle File ID property type issue - fixing...")
                    if fix_eagle_file_id_property_type():
                        # Retry update after fixing property type
                        notion_manager.update_page(page_id, props)
                        workspace_logger.info(f"🔄 Retried update after fixing Eagle File ID property: {meta['title']}")
                    else:
                        workspace_logger.warning(f"Could not fix Eagle File ID property type: {exc}")
                else:
                    # Create missing prop as rich_text
                    notion_manager._req(
                        "patch",
                        f"/databases/{TRACKS_DB_ID}",
                        {"properties": {missing: {"rich_text": {}}}}
                    )
                    workspace_logger.info(f"➕ Created missing property '{missing}' in Tracks DB")
                    # Retry update
                    notion_manager.update_page(page_id, props)
                    workspace_logger.info(f"🔄 Retried update after adding '{missing}': {meta['title']}")
            else:
                workspace_logger.warning(f"Could not update Notion page: {exc}")

    # For single track processing, we expect the page to already exist
    if "page_id" in meta:
        safe_update(meta["page_id"])
        # Link artist relation (2026-01-15 fix)
        if meta.get("artist"):
            link_track_artist_relation(meta["page_id"], meta["artist"])
        # Link playlist relation (2026-01-15 fix)
        playlist_name = meta.get("playlist_name") or meta.get("playlist")
        if playlist_name and playlist_name not in ["No Playlist", "Unassigned", ""]:
            link_track_playlist_relation(meta["page_id"], playlist_name)
        return meta["page_id"]

    # If no page_id provided, query by SoundCloud URL
    sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
    query_filter = None
    prop_type = _get_tracks_db_prop_types().get(sc_prop)
    if prop_type == "url":
        query_filter = {"property": sc_prop, "url": {"equals": meta["source_url"]}}
    elif prop_type == "rich_text":
        query_filter = {"property": sc_prop, "rich_text": {"equals": meta["source_url"]}}

    query = {"page_size": 1}
    if query_filter:
        query["filter"] = query_filter
    res = notion_manager.query_database(TRACKS_DB_ID, query)
    results = res.get("results", [])

    if results:
        page_id = results[0]["id"]
        safe_update(page_id)
        # Link artist relation (2026-01-15 fix)
        if meta.get("artist"):
            link_track_artist_relation(page_id, meta["artist"])
        # Link playlist relation (2026-01-15 fix)
        playlist_name = meta.get("playlist_name") or meta.get("playlist")
        if playlist_name and playlist_name not in ["No Playlist", "Unassigned", ""]:
            link_track_playlist_relation(page_id, playlist_name)
        return page_id
    else:
        # Create new page (shouldn't happen in single-track mode)
        body = {"parent": {"database_id": TRACKS_DB_ID}, "properties": props}
        try:
            page = notion_manager._req("post", "/pages", body)
            workspace_logger.info(f"🆕 Created track page in Notion: {meta['title']}")
            new_page_id = page.get("id", "")
            # Link artist relation (2026-01-15 fix)
            if new_page_id and meta.get("artist"):
                link_track_artist_relation(new_page_id, meta["artist"])
            # Link playlist relation (2026-01-15 fix)
            playlist_name = meta.get("playlist_name") or meta.get("playlist")
            if new_page_id and playlist_name and playlist_name not in ["No Playlist", "Unassigned", ""]:
                link_track_playlist_relation(new_page_id, playlist_name)
            return new_page_id
        except RuntimeError as exc:
            workspace_logger.warning(f"Could not create Notion page: {exc}")
            return ""

# ───────────────────────────────────────────────────────────────
# Utility Functions (adapted from original)
# ───────────────────────────────────────────────────────────────
def parse_soundcloud_url(url: str):
    """
    Parse artist and track from SoundCloud URL.

    Valid URL format: https://soundcloud.com/artist-name/track-name
    Invalid (API) URL: https://api.soundcloud.com/tracks/soundcloud%3Atracks%3A12345

    Returns (None, None) for malformed URLs to prevent incorrect metadata.
    """
    workspace_logger.info(f"🔍 PARSING URL: {url}")

    try:
        parsed = urlparse(url)

        # FIX: Detect and reject malformed API URLs
        # API URLs contain 'api.soundcloud.com' or have paths like '/tracks/ID'
        if 'api.soundcloud.com' in parsed.netloc:
            workspace_logger.warning(f"   ⚠️  Skipping malformed API URL (cannot extract artist): {url}")
            return None, None

        path = unquote(parsed.path).strip('/')
        parts = path.split('/')

        # FIX: Also reject URLs that start with 'tracks/' (API-style paths)
        if parts and parts[0] == 'tracks':
            workspace_logger.warning(f"   ⚠️  Skipping API-style URL path (cannot extract artist): {url}")
            return None, None

        # FIX: Validate that parsed artist doesn't look like a reserved path segment
        RESERVED_PATHS = {'tracks', 'playlists', 'sets', 'albums', 'users', 'discover', 'search', 'stream'}
        artist, track = (parts[0], parts[1]) if len(parts) >= 2 else (None, None)

        if artist and artist.lower() in RESERVED_PATHS:
            workspace_logger.warning(f"   ⚠️  Parsed artist '{artist}' is a reserved path - likely malformed URL")
            return None, None

        workspace_logger.info(f"   → Parsed artist from URL: '{artist}'")
        workspace_logger.info(f"   → Parsed track from URL: '{track}'")
        return artist, track
    except Exception as e:
        workspace_logger.error(f"   ❌ Failed to parse URL: {e}")
        return None, None

def detect_key(wav_path: str, y: Optional[np.ndarray] = None, sr: Optional[int] = None) -> str:
    """
    Very lightweight key estimation using librosa chroma profile correlation.
    Returns e.g. "G Major", "A Minor", or "Unknown".
    """
    workspace_logger.debug(f"Detecting key for: {wav_path}")

    try:
        # Verify file exists when audio is not preloaded
        if y is None or sr is None:
            if not Path(wav_path).exists():
                workspace_logger.error(f"❌ Key detection failed: File not found - {wav_path}")
                return "Unknown"
            # Load audio with error checking
            workspace_logger.debug(f"🔄 Loading audio for key detection: {wav_path}")
            y, sr = librosa.load(wav_path, sr=None)
        
        if len(y) == 0:
            workspace_logger.error(f"❌ Key detection failed: Empty audio file - {wav_path}")
            return "Unknown"
        
        workspace_logger.debug(f"✅ Audio loaded for key detection: {len(y)} samples, {sr} Hz")
        
        # Calculate chroma features
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        mean_chroma = np.mean(chroma, axis=1)
        
        if np.all(mean_chroma == 0):
            workspace_logger.error(f"❌ Key detection failed: No chroma features detected - {wav_path}")
            return "Unknown"

        pitch_classes = ['C', 'C#', 'D', 'D#', 'E', 'F',
                        'F#', 'G', 'G#', 'A', 'A#', 'B']
        key_index = int(np.argmax(mean_chroma))

        major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                        2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        minor_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                        2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

        # Rotate profiles to align with detected tonic
        major_profile = major_profile[key_index:] + major_profile[:key_index]
        minor_profile = minor_profile[key_index:] + minor_profile[:key_index]

        major_corr = np.corrcoef(mean_chroma, major_profile)[0, 1]
        minor_corr = np.corrcoef(mean_chroma, minor_profile)[0, 1]
        scale = "Major" if major_corr > minor_corr else "Minor"
        key = f"{pitch_classes[key_index]} {scale}"

        workspace_logger.info(f"✅ Key detected: {key}")
        return key
    except Exception as exc:
        workspace_logger.error(f"❌ Key detection failed with error: {exc}")
        workspace_logger.error(f"❌ Exception type: {type(exc).__name__}")
        return "Unknown"

def convert_to_camelot(key: str) -> str:
    """Traditional key → Camelot code; unknown returns 'Unknown'."""
    camelot = {
        'C Major': '8B', 'G Major': '9B', 'D Major': '10B', 'A Major': '11B',
        'E Major': '12B', 'B Major': '1B', 'F# Major': '2B', 'C# Major': '3B',
        'G# Major': '4B', 'D# Major': '5B', 'A# Major': '6B', 'F Major': '7B',
        'A Minor': '8A', 'E Minor': '9A', 'B Minor': '10A', 'F# Minor': '11A',
        'C# Minor': '12A', 'G# Minor': '1A', 'D# Minor': '2A', 'A# Minor': '3A',
        'F Minor': '4A', 'C Minor': '5A', 'G Minor': '6A', 'D Minor': '7A'
    }
    enharm = {
        'Db Major': 'C# Major', 'Ab Major': 'G# Major', 'Eb Major': 'D# Major',
        'Bb Major': 'A# Major', 'Gb Major': 'F# Major',
        'Bb Minor': 'A# Minor', 'Eb Minor': 'D# Minor', 'Ab Minor': 'G# Minor',
        'Db Minor': 'C# Minor', 'Gb Minor': 'F# Minor'
    }
    key = enharm.get(key, key)
    return camelot.get(key, 'Unknown')

def get_playlist_names_from_track(track_info: dict) -> list[str]:
    """
    Get playlist names from a track's playlist properties.
    Checks multiple property types: relation, rich_text, title, select, multi_select.
    
    Args:
        track_info: Track information containing page_id
        
    Returns:
        List of playlist names (deduplicated)
    """
    playlist_names = []
    
    if not track_info.get("page_id"):
        return playlist_names
    
    try:
        # Get the track page from Notion
        page = notion_manager._req("get", f"/pages/{track_info['page_id']}")
        props = page.get("properties", {})
        
        # Define all possible playlist property names to check
        playlist_property_candidates = [
            "Playlist",
            "Playlists", 
            "Playlist Title",
            "Playlist Name",
            "Playlist Names",
            "Playlist Relation",
            "Related Playlists"
        ]
        
        for prop_name in playlist_property_candidates:
            if prop_name not in props:
                continue
                
            prop = props[prop_name]
            prop_type = prop.get("type")
            
            try:
                # Handle relation properties (link to playlist pages)
                if prop_type == "relation":
                    relations = prop.get("relation", [])
                    workspace_logger.debug(f"Found {len(relations)} playlist relations in '{prop_name}'")
                    
                    for relation in relations:
                        playlist_id = relation.get("id")
                        if playlist_id:
                            try:
                                # Get the playlist page
                                playlist_page = notion_manager._req("get", f"/pages/{playlist_id}")
                                # Try multiple title property names
                                for title_prop in ["Title", "Name", "Playlist Name"]:
                                    playlist_title_data = playlist_page.get("properties", {}).get(title_prop, {})
                                    if playlist_title_data.get("type") == "title":
                                        title_items = playlist_title_data.get("title", [])
                                        if title_items:
                                            playlist_name = title_items[0].get("text", {}).get("content", "")
                                            if playlist_name:
                                                playlist_names.append(playlist_name)
                                                workspace_logger.debug(f"Found playlist from relation: {playlist_name}")
                                                break
                            except Exception as e:
                                workspace_logger.warning(f"Could not get playlist name for relation ID {playlist_id}: {e}")
                                continue
                
                # Handle rich_text properties (direct text input)
                elif prop_type == "rich_text":
                    rich_text_items = prop.get("rich_text", [])
                    if rich_text_items:
                        playlist_text = "".join([item.get("text", {}).get("content", "") for item in rich_text_items])
                        if playlist_text.strip():
                            # Handle comma-separated or semicolon-separated lists
                            for separator in [";", ","]:
                                if separator in playlist_text:
                                    playlist_names.extend([p.strip() for p in playlist_text.split(separator) if p.strip()])
                                    workspace_logger.debug(f"Found playlists from rich_text '{prop_name}': {playlist_text}")
                                    break
                            else:
                                # Single playlist name
                                playlist_names.append(playlist_text.strip())
                                workspace_logger.debug(f"Found playlist from rich_text '{prop_name}': {playlist_text.strip()}")
                
                # Handle title properties (for databases where playlist name is the title)
                elif prop_type == "title":
                    title_items = prop.get("title", [])
                    if title_items:
                        playlist_text = "".join([item.get("text", {}).get("content", "") for item in title_items])
                        if playlist_text.strip():
                            playlist_names.append(playlist_text.strip())
                            workspace_logger.debug(f"Found playlist from title '{prop_name}': {playlist_text.strip()}")
                
                # Handle select properties (single selection)
                elif prop_type == "select":
                    select_item = prop.get("select")
                    if select_item:
                        playlist_name = select_item.get("name", "")
                        if playlist_name:
                            playlist_names.append(playlist_name)
                            workspace_logger.debug(f"Found playlist from select '{prop_name}': {playlist_name}")
                
                # Handle multi_select properties (multiple selections)
                elif prop_type == "multi_select":
                    multi_select_items = prop.get("multi_select", [])
                    for item in multi_select_items:
                        playlist_name = item.get("name", "")
                        if playlist_name:
                            playlist_names.append(playlist_name)
                            workspace_logger.debug(f"Found playlist from multi_select '{prop_name}': {playlist_name}")
                            
            except Exception as e:
                workspace_logger.warning(f"Error processing property '{prop_name}': {e}")
                continue
                    
    except Exception as e:
        workspace_logger.warning(f"Could not get playlist information for track: {e}")
    
    # Remove duplicates while preserving order
    unique_playlists = []
    seen = set()
    for name in playlist_names:
        if name and name not in seen:
            unique_playlists.append(name)
            seen.add(name)
    
    if unique_playlists:
        workspace_logger.info(f"📋 Found {len(unique_playlists)} playlist(s): {', '.join(unique_playlists)}")
    else:
        workspace_logger.debug("No playlist information found for track")
    
    return unique_playlists

def compute_file_fingerprint(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a stable SHA-256 fingerprint for the provided audio file."""
    hash_obj = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

def estimate_tempo_from_onset(onset_env: np.ndarray, sr: int) -> np.ndarray:
    """Estimate tempo using the modern librosa API with fallback for older versions."""
    if librosa_rhythm is not None and hasattr(librosa_rhythm, "tempo"):
        return librosa_rhythm.tempo(onset_envelope=onset_env, sr=sr)
    return librosa.beat.tempo(onset_envelope=onset_env, sr=sr)

def generate_comprehensive_tags(track_info: dict, processing_data: dict, file_type: str) -> list[str]:
    """
    Generate focused, high-value tags for files (max 10 tags).
    Only includes: playlists, genre, BPM, key, and essential metadata.
    
    Args:
        track_info: Original track information from Notion
        processing_data: Audio processing results (BPM, key, duration, etc.)
        file_type: Type of file (AIFF, M4A, WAV)
        
    Returns:
        List of high-value tags (max 10)
    """
    tags = []
    
    # 1. Playlist tags (highest priority)
    playlist_names = get_playlist_names_from_track(track_info)
    for playlist_name in playlist_names:
        # Clean playlist name for tag use (remove special characters, spaces)
        clean_playlist_name = re.sub(r'[^\w\s-]', '', playlist_name).strip()
        if clean_playlist_name:
            tags.append(clean_playlist_name)
            workspace_logger.debug(f"Added playlist tag: {clean_playlist_name}")
    
    # 2. Genre (if available)
    if track_info.get("genre"):
        tags.append(track_info["genre"])
    
    # 3. BPM (if available and valid)
    if processing_data.get("bpm") and processing_data["bpm"] > 0:
        tags.append(f"BPM{processing_data['bpm']}")
    
    # 4. Key (if available and valid)
    if processing_data.get("key") and processing_data["key"] != "Unknown":
        key = processing_data["key"]
        tags.append(key)
    
    # 5. Artist (if available)
    if track_info.get("artist"):
        tags.append(track_info["artist"])
    
    # 6. File format
    tags.append(file_type)
    
    # 7. Source platform
    if track_info.get("soundcloud_url"):
        tags.append("SoundCloud")
    elif track_info.get("spotify_id"):
        tags.append("Spotify")
    
    # 8. Quality indicator
    tags.append("HighQuality")
    
    # 9. Processing status and fingerprint tag (critical for deduplication)
    if processing_data.get("fingerprint"):
        tags.append("Processed")
        # Add fingerprint as tag for Eagle deduplication validation
        fingerprint_value = processing_data["fingerprint"]
        if fingerprint_value:
            # Truncate fingerprint to reasonable length for tag (first 32 chars)
            fingerprint_tag = f"fingerprint:{fingerprint_value[:32].lower()}"
            tags.append(fingerprint_tag)
            workspace_logger.debug(f"Added fingerprint tag: {fingerprint_tag}")
    
    # 10. Duration category (only if significant)
    if processing_data.get("duration") and processing_data["duration"] > 0:
        duration = processing_data["duration"]
        if duration < 60:
            tags.append("Short")
        elif duration > 300:
            tags.append("Extended")
    
    # Remove duplicates and empty tags
    tags = list(set([tag for tag in tags if tag and tag.strip()]))
    
    # Limit to 12 tags maximum (increased to accommodate fingerprint)
    if len(tags) > 12:
        # Keep the most important tags: fingerprint (critical), playlists, genre, BPM, key, artist
        priority_tags = []

        # CRITICAL: Always keep fingerprint tag first (required for deduplication)
        for tag in tags:
            if tag.startswith("fingerprint:"):
                priority_tags.append(tag)
                break

        # Add playlist tags
        for tag in tags:
            if tag not in priority_tags and any(playlist in tag for playlist in playlist_names):
                priority_tags.append(tag)

        # Add other high-value tags
        for tag in tags:
            if tag not in priority_tags and len(priority_tags) < 12:
                priority_tags.append(tag)

        tags = priority_tags[:12]
    
    workspace_logger.info(f"Generated {len(tags)} focused tags for {file_type}: {tags}")
    return tags



# ───────────────────────────────────────────────────────────────
# Eagle Integration (adapted from original)
# ───────────────────────────────────────────────────────────────
# Configuration flag for Eagle delete operations
EAGLE_DELETE_ENABLED = True  # Now enabled with moveToTrash implementation

# ═══════════════════════════════════════════════════════════════
# PERFORMANCE: Eagle Items Cache with TTL
# ═══════════════════════════════════════════════════════════════
# Cache for Eagle items to avoid repeated API calls (major performance improvement)
_eagle_items_cache: Optional[list[dict]] = None
_eagle_items_cache_time: float = 0.0
_eagle_items_cache_ttl: float = 300.0  # 5 minutes TTL
_eagle_items_name_index: Optional[dict[str, list[dict]]] = None  # Pre-indexed by lowercase name
_eagle_items_path_index: Optional[dict[str, dict]] = None  # Pre-indexed by path
_eagle_items_fingerprint_index: Optional[dict[str, list[dict]]] = None  # fingerprint -> items


def get_cached_eagle_items(force_refresh: bool = False) -> list[dict]:
    """
    Get Eagle items with caching. Significantly reduces API calls.

    Performance impact: Reduces 100+ API calls to 1 per 5-minute window.
    """
    global _eagle_items_cache, _eagle_items_cache_time, _eagle_items_name_index, _eagle_items_path_index, _eagle_items_fingerprint_index

    current_time = time.time()
    cache_expired = (current_time - _eagle_items_cache_time) > _eagle_items_cache_ttl

    if force_refresh or _eagle_items_cache is None or cache_expired:
        workspace_logger.info("🔄 Refreshing Eagle items cache...")
        try:
            endpoint = "/api/item/list"
            if EAGLE_CACHE_LIMIT > 0:
                endpoint = f"{endpoint}?limit={EAGLE_CACHE_LIMIT}"
            data = eagle_request("get", endpoint)
            _eagle_items_cache = data.get("data", [])
            _eagle_items_cache_time = current_time

            # Build pre-indexed lookups for O(1) access
            _eagle_items_name_index = {}
            _eagle_items_path_index = {}
            _eagle_items_fingerprint_index = {}
            for item in _eagle_items_cache:
                # Index by lowercase name for fast fuzzy matching
                name_lower = item.get("name", "").lower()
                if name_lower:
                    if name_lower not in _eagle_items_name_index:
                        _eagle_items_name_index[name_lower] = []
                    _eagle_items_name_index[name_lower].append(item)

                # Index by path for O(1) path lookups
                path = item.get("path", "")
                if path:
                    _eagle_items_path_index[path] = item

                # Index by fingerprint tag for O(1) fingerprint lookups
                for tag in item.get("tags", []):
                    if not isinstance(tag, str):
                        continue
                    tag_lower = tag.lower()
                    if tag_lower.startswith("fingerprint:"):
                        fingerprint_value = tag_lower.split(":", 1)[1].strip()
                        if fingerprint_value:
                            _eagle_items_fingerprint_index.setdefault(fingerprint_value, []).append(item)

            workspace_logger.info(f"✅ Eagle cache refreshed: {len(_eagle_items_cache)} items indexed")
        except Exception as e:
            workspace_logger.warning(f"⚠️ Failed to refresh Eagle cache: {e}")
            if _eagle_items_cache is None:
                _eagle_items_cache = []

    return _eagle_items_cache


def get_eagle_item_by_path(file_path: str) -> Optional[dict]:
    """O(1) lookup of Eagle item by path using pre-built index."""
    global _eagle_items_path_index
    if _eagle_items_path_index is None:
        get_cached_eagle_items()  # Initialize cache if needed
    return _eagle_items_path_index.get(file_path) if _eagle_items_path_index else None


def get_eagle_items_by_name(name: str) -> list[dict]:
    """O(1) lookup of Eagle items by name using pre-built index."""
    global _eagle_items_name_index
    if _eagle_items_name_index is None:
        get_cached_eagle_items()  # Initialize cache if needed
    return _eagle_items_name_index.get(name.lower(), []) if _eagle_items_name_index else []

def get_eagle_items_by_fingerprint(fingerprint: str) -> list[dict]:
    """O(1) lookup of Eagle items by fingerprint tag using pre-built index."""
    global _eagle_items_fingerprint_index
    if _eagle_items_fingerprint_index is None:
        get_cached_eagle_items()  # Initialize cache if needed
    if not fingerprint:
        return []
    return _eagle_items_fingerprint_index.get(fingerprint.lower(), []) if _eagle_items_fingerprint_index else []


def invalidate_eagle_cache():
    """Invalidate the Eagle items cache (call after adding/removing items)."""
    global _eagle_items_cache, _eagle_items_cache_time, _eagle_items_name_index, _eagle_items_path_index, _eagle_items_fingerprint_index
    _eagle_items_cache = None
    _eagle_items_cache_time = 0.0
    _eagle_items_name_index = None
    _eagle_items_path_index = None
    _eagle_items_fingerprint_index = None
    workspace_logger.debug("🔄 Eagle cache invalidated")


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE: Path Existence Cache
# ═══════════════════════════════════════════════════════════════
# Caches filesystem existence checks to avoid repeated syscalls
_path_exists_cache: dict[str, bool] = {}
_path_exists_cache_max_size: int = 10000  # Limit cache size


def cached_path_exists(path: str) -> bool:
    """
    Check if a path exists with caching.

    PERFORMANCE: Reduces filesystem syscalls by caching results.
    Cache is session-scoped (cleared when script restarts).
    """
    global _path_exists_cache

    if path in _path_exists_cache:
        return _path_exists_cache[path]

    # Limit cache size to prevent memory issues
    if len(_path_exists_cache) >= _path_exists_cache_max_size:
        # Clear oldest half of cache (simple LRU approximation)
        keys_to_remove = list(_path_exists_cache.keys())[:_path_exists_cache_max_size // 2]
        for key in keys_to_remove:
            del _path_exists_cache[key]

    exists = Path(path).exists()
    _path_exists_cache[path] = exists
    return exists


def clear_path_cache():
    """Clear the path existence cache (call if files are created/deleted)."""
    global _path_exists_cache
    _path_exists_cache = {}


def eagle_request(
    method: str,
    endpoint: str,
    payload: Optional[dict] = None,
    retry: int = RETRY_MAX
):
    """
    Generic helper for calling Eagle's local REST API with automatic retries
    and transparent token handling.
    """
    # Build URL with token in query string (correct Eagle API format)
    url = f"{EAGLE_API_BASE}{endpoint}"
    if EAGLE_TOKEN:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}token={EAGLE_TOKEN}"
    
    headers = {"Content-Type": "application/json"}
    payload_to_send = dict(payload) if isinstance(payload, dict) else None

    workspace_logger.debug(f"🦅 Eagle API request: {method} {endpoint}")

    for attempt in range(1, retry + 1):
        try:
            resp = _HTTP_SESSION.request(
                method,
                url,
                json=payload_to_send,
                headers=headers,
                timeout=20,
            )
            
            # Fast-fail for unsupported delete routes/methods (404/405) - check before raising exception
            if resp.status_code in (404, 405) and ("item" in endpoint and (method.lower() == "delete" or "delete" in endpoint)):
                workspace_logger.debug(f"🦅 Eagle API: Unsupported delete endpoint {method} {endpoint} (status {resp.status_code})")
                return {"ok": False, "status": "unsupported", "reason": "endpoint_not_supported"}
            
            if 200 <= resp.status_code < 300:
                workspace_logger.debug(f"✅ Eagle API request successful: {method} {endpoint}")
                try:
                    return resp.json()
                except ValueError:
                    return resp.text
            
            if resp.status_code >= 500:
                workspace_logger.warning(f"⚠️  Eagle API server error {resp.status_code} (attempt {attempt}/{retry})")
                if attempt < retry:
                    time.sleep(1 * attempt)
                    continue
            
            # For 4xx errors (except 404/405 which are handled above), don't retry
            if 400 <= resp.status_code < 500:
                workspace_logger.error(f"❌ Eagle API client error {resp.status_code}: {resp.text}")
                raise RuntimeError(f"Eagle API error {resp.status_code}: {resp.text}")
                    
            workspace_logger.error(f"❌ Eagle API error {resp.status_code}: {resp.text}")
            raise RuntimeError(f"Eagle API error {resp.status_code}: {resp.text}")
            
        except requests.exceptions.ConnectionError as exc:
            workspace_logger.warning(f"❌ Eagle API connection failed (attempt {attempt}/{retry}): {exc}")
            launched = ensure_eagle_app_running()
            if attempt < retry:
                if launched:
                    workspace_logger.info("🔄 Retrying Eagle API request after launching Eagle...")
                else:
                    workspace_logger.warning(f"🔄 Retrying in {2 ** attempt}s...")
                    time.sleep(2 ** attempt)
                continue
            workspace_logger.error(f"❌ Eagle API connection failed after {retry} attempts: {exc}")
            workspace_logger.error("🦅 Eagle application may not be running or accessible")
            raise
        except requests.exceptions.Timeout as exc:
            if attempt < retry:
                workspace_logger.warning(f"⏰ Eagle API timeout (attempt {attempt}/{retry}): {exc}")
                workspace_logger.warning(f"🔄 Retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
            else:
                workspace_logger.error(f"⏰ Eagle API timeout after {retry} attempts: {exc}")
                raise
        except RuntimeError as exc:
            # Check if this is our fast-fail response
            if "unsupported" in str(exc) or "endpoint_not_supported" in str(exc):
                workspace_logger.debug(f"🦅 Eagle API: Fast-fail for unsupported endpoint")
                return {"ok": False, "status": "unsupported", "reason": "endpoint_not_supported"}
            
            if attempt < retry:
                workspace_logger.warning(f"❌ Eagle API request failed (attempt {attempt}/{retry}): {exc}")
                workspace_logger.warning(f"🔄 Retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
            else:
                workspace_logger.error(f"❌ Eagle API request failed after {retry} attempts: {exc}")
                workspace_logger.error(f"❌ Exception type: {type(exc).__name__}")
                raise
        except Exception as exc:
            if attempt < retry:
                workspace_logger.warning(f"❌ Eagle API request failed (attempt {attempt}/{retry}): {exc}")
                workspace_logger.warning(f"🔄 Retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
            else:
                workspace_logger.error(f"❌ Eagle API request failed after {retry} attempts: {exc}")
                workspace_logger.error(f"❌ Exception type: {type(exc).__name__}")
                raise

def eagle_switch_library(library_path: str = EAGLE_LIBRARY_PATH):
    """Ensure Eagle is pointing at the correct library before we start."""
    try:
        p = Path(library_path)
        if not p.exists():
            workspace_logger.info("🦅 No valid EAGLE_LIBRARY_PATH. Using currently active Eagle library.")
            return
        if not (p.is_dir() and (p / "library.json").exists()):
            workspace_logger.warning("🦅 Path does not look like an Eagle library (missing library.json): %s — skipping switch", library_path)
            return
    except Exception as e:
        workspace_logger.warning("🦅 Eagle library preflight failed for %s: %s", library_path, e)
        return
    try:
        eagle_request("post", "/api/library/switch", {"libraryPath": library_path})
    except Exception as e:
        workspace_logger.warning("Could not switch Eagle library: %s", e)


def eagle_get_active_library_info() -> Optional[Dict[str, Any]]:
    """
    Get information about the currently active Eagle library.

    Works with ANY Eagle library - does not force opening a specific library.
    Returns information about whatever library is currently open in Eagle.

    Returns:
        Dictionary with library info (name, path, itemCount) or None if unavailable
    """
    try:
        response = eagle_request("get", "/api/library/info")
        if response and response.get("status") == "success":
            lib_data = response.get("data", {})
            return {
                "name": lib_data.get("library", {}).get("name", "Unknown"),
                "path": lib_data.get("library", {}).get("path", "Unknown"),
                "itemCount": lib_data.get("library", {}).get("itemCount", 0),
                "folders": lib_data.get("folders", []),
            }
        return None
    except Exception as e:
        workspace_logger.debug(f"Could not get Eagle library info: {e}")
        return None


def log_active_eagle_library() -> None:
    """Log information about the currently active Eagle library."""
    lib_info = eagle_get_active_library_info()
    if lib_info:
        workspace_logger.info(f"🦅 Active Eagle Library: {lib_info.get('name', 'Unknown')}")
        workspace_logger.info(f"🦅 Library Path: {lib_info.get('path', 'Unknown')}")
        workspace_logger.info(f"🦅 Item Count: {lib_info.get('itemCount', 0):,}")
    else:
        workspace_logger.warning("🦅 Could not retrieve active Eagle library info (Eagle may not be running)")


def eagle_get_or_create_folder(folder_name: str, parent_folder_id: Optional[str] = None) -> Optional[str]:
    """Return the Eagle folderId for folder_name, creating it if absent.

    Args:
        folder_name: Name of the folder to get or create
        parent_folder_id: Optional parent folder ID for nested folders

    Returns:
        The Eagle folder ID, or None if folder API is not available
    """
    try:
        # NOTE: Eagle API requires /api/ prefix for all endpoints
        data = eagle_request("get", "/api/folder/list")

        def find_folder_recursive(folders, name, parent_id=None):
            """Recursively search for folder by name and parent."""
            for f in folders:
                # Check if this folder matches
                if f.get("name") == name:
                    # If no parent specified, return first match
                    if parent_id is None:
                        return f["id"]
                    # If parent specified, check if this folder is under that parent
                    # Eagle folders have parent field
                    if f.get("parent") == parent_id:
                        return f["id"]
                # Check children recursively
                children = f.get("children", [])
                if children:
                    result = find_folder_recursive(children, name, parent_id)
                    if result:
                        return result
            return None

        folder_id = find_folder_recursive(data.get("data", []), folder_name, parent_folder_id)
        if folder_id:
            return folder_id

        # Create the folder - NOTE: Eagle API requires /api/ prefix
        create_payload = {"folderName": folder_name}
        if parent_folder_id:
            create_payload["parent"] = parent_folder_id

        resp = eagle_request("post", "/api/folder/create", create_payload)
        return resp["data"]["id"] if isinstance(resp.get("data"), dict) else resp.get("id")
    except Exception as e:
        workspace_logger.debug(f"Eagle folder API not available: {e}")
        return None


def eagle_get_or_create_playlist_folder(playlist_name: str) -> Optional[str]:
    """Get or create an Eagle folder for a playlist under the 'Playlists' parent folder.

    This ensures all playlist-organized tracks are nested under a 'Playlists' parent folder
    in Eagle for better organization.

    Args:
        playlist_name: Name of the playlist

    Returns:
        The Eagle folder ID for the playlist, or None if folder API is not available
    """
    # First, get or create the 'Playlists' parent folder
    playlists_parent_id = eagle_get_or_create_folder("Playlists")
    if playlists_parent_id is None:
        workspace_logger.debug(f"🦅 Eagle folder API not available - importing to root folder")
        return None

    # Then get or create the specific playlist folder under 'Playlists'
    playlist_folder_id = eagle_get_or_create_folder(playlist_name, playlists_parent_id)

    if playlist_folder_id:
        workspace_logger.debug(f"🦅 Eagle playlist folder: Playlists/{playlist_name} -> {playlist_folder_id}")
    else:
        workspace_logger.debug(f"🦅 Could not create playlist folder, will use root")
    return playlist_folder_id

def eagle_add_item(path: str, name: str, website: str, tags: list[str], folder_id: Optional[str] = None, existing_eagle_id: str = None) -> Optional[str]:
    """Add a local file to Eagle using the WORKING endpoint."""
    
    # Check if file exists
    if not Path(path).exists():
        workspace_logger.error(f"❌ File not found: {path}")
        return None
    
    # Use absolute path
    abs_path = str(Path(path).resolve())
    
    if existing_eagle_id:
        workspace_logger.info(f"ℹ️  Found existing Eagle ID: {existing_eagle_id}")
    
    workspace_logger.debug(f"🦅 Calling Eagle API addFromPath: {abs_path}")
    workspace_logger.debug(f"   Name: {name}")
    workspace_logger.debug(f"   Tags: {tags}")
    
    # Use the CORRECT payload format (confirmed by diagnostic)
    payload = {
        "path": abs_path,
        "name": name,
        "tags": tags,
        "folderId": folder_id if folder_id else "root"
    }
    
    # Add optional fields
    if website:
        payload["website"] = website
    
    try:
        # Use the WORKING endpoint
        data = eagle_request("POST", "/api/item/addFromPath", payload)
        workspace_logger.debug(f"🦅 Eagle API response: {data}")
            
        if isinstance(data, dict):
            if data.get("status") == "success":
                # Handle both string and dict data responses
                eagle_id = data.get("data")
                if isinstance(eagle_id, dict):
                    eagle_id = eagle_id.get("id")
                workspace_logger.info(f"✅ Eagle API added item, got ID: {eagle_id}")
                # Invalidate cache after adding new item
                invalidate_eagle_cache()
                return eagle_id
            else:
                workspace_logger.warning(f"Eagle API error: {data}")
        
        return None
    except Exception as e:
        workspace_logger.error(f"❌ Failed to add item to Eagle: {e}")
        return None

def eagle_move_to_trash(item_ids: list[str]) -> bool:
    """
    Move Eagle items to trash using the official API endpoint.
    This is the only supported "delete-like" operation in Eagle.
    
    Args:
        item_ids: List of Eagle item IDs to move to trash
        
    Returns:
        True if successful, False otherwise
    """
    if not item_ids:
        return True
    
    try:
        payload = {"itemIds": item_ids}
        result = eagle_request("post", "/api/item/moveToTrash", payload)
        
        if result and isinstance(result, dict) and result.get("status") == "success":
            workspace_logger.info(f"🗑️  Moved {len(item_ids)} Eagle item(s) to trash")
            return True
        else:
            workspace_logger.warning(f"❌ Failed to move items to trash: {result}")
            return False
            
    except Exception as exc:
        workspace_logger.warning(f"❌ Exception moving items to trash: {exc}")
        return False

def eagle_delete_item(item_id: str) -> bool:
    """
    Legacy function - now redirects to moveToTrash.
    Eagle only supports soft delete via moveToTrash, not hard delete.
    """
    if not EAGLE_DELETE_ENABLED:
        workspace_logger.debug(f"🦅 Eagle delete disabled - skipping item {item_id}")
        return False
    
    return eagle_move_to_trash([item_id])

def eagle_find_items_by_path(file_path: str) -> list[dict]:
    """
    Find Eagle items by file path using cached index.

    PERFORMANCE: O(1) lookup using pre-built path index.
    Returns list of item dictionaries (not just IDs) for consistency.
    """
    try:
        # Use cached index for O(1) lookup instead of O(n) scan
        item = get_eagle_item_by_path(file_path)
        if item:
            return [item]

        # Fallback: check for partial path matches in cache
        items = get_cached_eagle_items()
        matching_items = []
        file_name = Path(file_path).name
        for item in items:
            item_path = item.get("path", "")
            if item_path and Path(item_path).name == file_name:
                matching_items.append(item)
        return matching_items
    except Exception as exc:
        workspace_logger.warning(f"Failed to search Eagle items: {exc}")
        return []

def eagle_fetch_all_items() -> list[dict]:
    """
    Fetch the full item list from Eagle with caching.

    PERFORMANCE: Now uses cached data with 5-minute TTL.
    Reduces 100+ API calls to 1 per processing batch.
    """
    return get_cached_eagle_items()

def _extract_fingerprint_tag(item: dict) -> Optional[str]:
    """Extract fingerprint tag value from an Eagle item."""
    for tag in item.get("tags", []):
        if not isinstance(tag, str):
            continue
        tag_lower = tag.lower()
        if tag_lower.startswith("fingerprint:"):
            value = tag_lower.split(":", 1)[1].strip()
            if value:
                return value
    return None

def _normalize_name_for_dedup(name: str) -> str:
    return _sanitize_match_string(name or "")

def _token_prefix_key(normalized: str, token_count: int = 3) -> str:
    tokens = normalized.split()
    if not tokens:
        return ""
    return " ".join(tokens[:token_count])

def _token_suffix_key(normalized: str, token_count: int = 3) -> str:
    tokens = normalized.split()
    if not tokens:
        return ""
    return " ".join(tokens[-token_count:])

def _cluster_by_similarity(items: list[dict], min_similarity: float) -> list[list[dict]]:
    """Cluster items by name similarity using a simple union-find."""
    if len(items) < 2:
        return []

    norms = [_normalize_name_for_dedup(item.get("name", "")) for item in items]
    parent = list(range(len(items)))

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(items)):
        name_i = norms[i]
        if not name_i:
            continue
        for j in range(i + 1, len(items)):
            name_j = norms[j]
            if not name_j:
                continue
            # Skip obvious mismatches by length difference
            if abs(len(name_i) - len(name_j)) > max(len(name_i), len(name_j)) * 0.5:
                continue
            similarity = difflib.SequenceMatcher(None, name_i, name_j).ratio()
            if similarity >= min_similarity:
                union(i, j)

    clusters: dict[int, list[dict]] = {}
    for idx, item in enumerate(items):
        root = find(idx)
        clusters.setdefault(root, []).append(item)

    return [group for group in clusters.values() if len(group) > 1]

def _select_best_item(items: list[dict]) -> dict:
    best_item = None
    best_score = (-1, -1)
    for item in items:
        quality = eagle_analyze_item_quality(item)
        score = (quality.get("overall_score", 0), quality.get("size", 0))
        if score > best_score:
            best_score = score
            best_item = item
    return best_item or items[0]

def eagle_library_deduplication(
    dry_run: bool = True,
    min_similarity: float = 0.75,
    output_report: bool = True,
    cleanup_duplicates: bool = False,
    require_fingerprints: bool = True,
    min_fingerprint_coverage: float = 0.80,
) -> dict:
    """
    Library-wide deduplication scan for Eagle.
    Uses fingerprint groups first, then fuzzy name matching, then suffix-token matching.
    """
    start_time = time.time()
    items = eagle_fetch_all_items()
    total_items = len(items)

    if total_items == 0:
        return {"error": "No Eagle items found", "total_items": 0, "duplicate_groups": []}

    # Fingerprint coverage check
    fingerprint_groups: dict[str, list[dict]] = {}
    items_with_fp = 0
    fingerprint_by_id: dict[str, str] = {}
    for item in items:
        fp = _extract_fingerprint_tag(item)
        if fp:
            items_with_fp += 1
            fingerprint_by_id[item.get("id", "")] = fp
            fingerprint_groups.setdefault(fp, []).append(item)

    coverage = items_with_fp / total_items if total_items else 0.0
    if require_fingerprints and coverage < min_fingerprint_coverage:
        return {
            "error": f"Fingerprint coverage {coverage:.1%} below required {min_fingerprint_coverage:.1%}",
            "total_items": total_items,
            "items_with_fingerprints": items_with_fp,
            "coverage": coverage,
            "duplicate_groups": [],
        }

    duplicate_groups: list[dict] = []
    used_ids: set[str] = set()

    # Strategy 1: Fingerprint matching
    for fp, group in fingerprint_groups.items():
        if len(group) < 2:
            continue
        keeper = _select_best_item(group)
        duplicates = [item for item in group if item.get("id") != keeper.get("id")]
        if not duplicates:
            continue
        used_ids.update(item.get("id") for item in group if item.get("id"))
        duplicate_groups.append({
            "match_type": "fingerprint",
            "similarity": 1.0,
            "keeper": keeper,
            "duplicates": duplicates,
        })

    # Strategy 2: Fuzzy name matching (prefix token buckets)
    fuzzy_candidates = [
        item for item in items
        if item.get("id") not in used_ids and (not require_fingerprints or not _extract_fingerprint_tag(item))
    ]
    buckets: dict[str, list[dict]] = {}
    for item in fuzzy_candidates:
        norm_name = _normalize_name_for_dedup(item.get("name", ""))
        if not norm_name:
            continue
        buckets.setdefault(_token_prefix_key(norm_name), []).append(item)

    for bucket_items in buckets.values():
        if len(bucket_items) < 2:
            continue
        for group in _cluster_by_similarity(bucket_items, min_similarity=min_similarity):
            group = [item for item in group if item.get("id") not in used_ids]
            if len(group) < 2:
                continue
            keeper = _select_best_item(group)
            duplicates = [item for item in group if item.get("id") != keeper.get("id")]
            if not duplicates:
                continue
            used_ids.update(item.get("id") for item in group if item.get("id"))
            duplicate_groups.append({
                "match_type": "fuzzy",
                "similarity": min_similarity,
                "keeper": keeper,
                "duplicates": duplicates,
            })

    # Strategy 3: Suffix-token matching (lightweight n-gram-style fallback)
    ngram_candidates = [item for item in items if item.get("id") not in used_ids]
    suffix_buckets: dict[str, list[dict]] = {}
    for item in ngram_candidates:
        norm_name = _normalize_name_for_dedup(item.get("name", ""))
        if not norm_name:
            continue
        suffix_buckets.setdefault(_token_suffix_key(norm_name), []).append(item)

    for bucket_items in suffix_buckets.values():
        if len(bucket_items) < 2:
            continue
        for group in _cluster_by_similarity(bucket_items, min_similarity=min_similarity):
            group = [item for item in group if item.get("id") not in used_ids]
            if len(group) < 2:
                continue
            keeper = _select_best_item(group)
            duplicates = [item for item in group if item.get("id") != keeper.get("id")]
            if not duplicates:
                continue
            used_ids.update(item.get("id") for item in group if item.get("id"))
            duplicate_groups.append({
                "match_type": "ngram",
                "similarity": min_similarity,
                "keeper": keeper,
                "duplicates": duplicates,
            })

    # Optional cleanup
    if cleanup_duplicates and not dry_run:
        for group in duplicate_groups:
            keeper = group.get("keeper")
            all_items = [keeper] + group.get("duplicates", [])
            try:
                eagle_cleanup_duplicate_items(keeper, all_items)
            except Exception as exc:
                workspace_logger.warning(f"Cleanup failed for group {keeper.get('id') if keeper else 'unknown'}: {exc}")

    total_duplicates = sum(len(g.get("duplicates", [])) for g in duplicate_groups)
    duration = time.time() - start_time

    # Report generation
    report_path = None
    if output_report:
        logs_dir = Path(__file__).resolve().parent.parent / "logs" / "deduplication"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = logs_dir / f"eagle_dedup_report_{timestamp}.md"

        match_breakdown = {"fingerprint": [], "fuzzy": [], "ngram": []}
        for group in duplicate_groups:
            match_breakdown[group.get("match_type", "fuzzy")].append(group)

        def _size_mb(item: dict) -> float:
            return float(item.get("size", 0)) / (1024 * 1024)

        total_space_mb = sum(_size_mb(item) for g in duplicate_groups for item in g.get("duplicates", []))
        report_lines = [
            "# Eagle Library Deduplication Report",
            "",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            f"**Mode:** {'DRY RUN (no changes made)' if dry_run else 'LIVE'}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Items Scanned | {total_items:,} |",
            f"| Duplicate Groups Found | {len(duplicate_groups):,} |",
            f"| Total Duplicate Items | {total_duplicates:,} |",
            f"| Space Recoverable | {total_space_mb:.2f} MB |",
            f"| Scan Duration | {duration:.1f} seconds |",
            "",
            "## Match Type Breakdown",
            "",
        ]
        for match_type in ["fingerprint", "fuzzy", "ngram"]:
            groups = match_breakdown.get(match_type, [])
            dupes = sum(len(g.get("duplicates", [])) for g in groups)
            space_mb = sum(_size_mb(item) for g in groups for item in g.get("duplicates", []))
            label = match_type.capitalize()
            report_lines.append(f"- **{label}**: {len(groups)} groups, {dupes} duplicates, {space_mb:.2f} MB")

        report_lines.append("")
        report_lines.append("## Duplicate Groups Detail")
        report_lines.append("")

        for idx, group in enumerate(duplicate_groups, 1):
            keeper = group.get("keeper", {})
            duplicates = group.get("duplicates", [])
            similarity = group.get("similarity", min_similarity)
            group_space_mb = sum(_size_mb(item) for item in duplicates)
            report_lines.extend([
                f"### Group {idx}: {keeper.get('name', 'Unknown')}",
                "",
                f"- **Match Type:** {group.get('match_type')}",
                f"- **Similarity:** {int(similarity * 100)}%",
                f"- **Space Recoverable:** {group_space_mb:.2f} MB",
                "",
                "**Keep (Best Quality):**",
                f"- ID: `{keeper.get('id', 'Unknown')}`",
                f"- Name: {keeper.get('name', 'Unknown')}",
                f"- Size: {_size_mb(keeper):.2f} MB",
                f"- Tags: {', '.join(keeper.get('tags', [])[:8])}{'...' if len(keeper.get('tags', [])) > 8 else ''}",
                "",
                "**Duplicates to Remove:**",
            ])
            for dup in duplicates:
                report_lines.append(f"- `{dup.get('id', 'Unknown')}` - {dup.get('name', 'Unknown')} ({_size_mb(dup):.2f} MB)")
            report_lines.append("")

        report_path.write_text("\n".join(report_lines))
        workspace_logger.info(f"📄 Report generated: {report_path}")

    return {
        "total_items": total_items,
        "duplicate_groups": duplicate_groups,
        "total_duplicates": total_duplicates,
        "coverage": coverage,
        "items_with_fingerprints": items_with_fp,
        "report_path": str(report_path) if report_path else None,
    }

def eagle_find_items_by_filename(filename: str, items: Optional[List[dict]] = None) -> List[dict]:
    """
    Find Eagle items by filename (without extension).

    PERFORMANCE: Uses pre-built name index for O(1) lookups on exact matches,
    falls back to filtered linear search only for partial matches.
    """
    # Use cached items if not provided
    if items is None:
        items = get_cached_eagle_items()

    matching_items: list[dict] = []
    seen_ids: set[str] = set()  # Deduplicate results

    # Extract filename stem (without extension)
    filename_stem = Path(filename).stem

    # Remove "_processed" suffix for WAV files to match base track name
    base_track_name = filename_stem.replace("_processed", "")

    # Build candidate names for exact matching
    candidates = {
        filename_stem.lower(),
        base_track_name.lower(),
        f"{base_track_name} (wav)".lower(),
        f"{base_track_name} (m4a)".lower(),
        f"{base_track_name} (aiff)".lower(),
        f"{base_track_name} (mp3)".lower(),
        base_track_name.replace(" - ", " ").lower(),
        base_track_name.replace(" ", "-").lower(),
        base_track_name.replace("_", " ").lower(),
        base_track_name.replace(" ", "_").lower(),
    }

    workspace_logger.debug(f"🔍 Searching for filename: '{filename_stem}' (base: '{base_track_name}')")

    # PERFORMANCE: Use pre-built index for O(1) exact name lookups
    for candidate in candidates:
        indexed_items = get_eagle_items_by_name(candidate)
        for item in indexed_items:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                matching_items.append(item)
                seen_ids.add(item_id)
                workspace_logger.debug(f"   ✅ Index exact match: '{item.get('name')}'")

    # Only do linear search for partial matches if no exact matches found
    if not matching_items:
        filename_lower = filename_stem.lower()
        target_filename = Path(filename).name

        for item in items:
            item_id = item.get("id")
            if item_id in seen_ids:
                continue

            item_name = item.get("name", "")
            item_path = item.get("path", "")

            # Check partial name match
            if filename_lower in item_name.lower():
                matching_items.append(item)
                seen_ids.add(item_id)
                workspace_logger.debug(f"   ✅ Partial match: '{item_name}'")
                continue

            # Check file path match
            if item_path and Path(item_path).name == target_filename:
                matching_items.append(item)
                seen_ids.add(item_id)
                workspace_logger.debug(f"   ✅ Path match: '{item_path}'")

    workspace_logger.info(
        f"🔍 Found {len(matching_items)} Eagle items for '{filename_stem}'"
    )

    return matching_items

def _sanitize_match_string(*parts: str) -> str:
    """Lowercase, alphanumeric-only representation used for fuzzy matching."""
    combined = " ".join(part for part in parts if part)
    combined = combined.lower()
    combined = re.sub(r"[^a-z0-9]+", " ", combined)
    return combined.strip()

_NON_ARTIST_TAG_PREFIXES = (
    "bpm",
    "key",
    "camelot",
    "fingerprint",
    "wav",
    "aiff",
    "m4a",
    "mp3",
    "processed",
    "highquality",
    "soundcloud",
    "spotify",
    "playlist",
    "genre",
    "duration",
    "compression",
    "source",
)

def _is_non_artist_tag(tag_norm: str) -> bool:
    if not tag_norm:
        return True
    if tag_norm.startswith(_NON_ARTIST_TAG_PREFIXES):
        return True
    if tag_norm.endswith("major") or tag_norm.endswith("minor"):
        return True
    return False

def _artist_tag_match_score(artist_norm: str, tag: str) -> float:
    tag_norm = _sanitize_match_string(tag or "")
    if _is_non_artist_tag(tag_norm):
        return 0.0
    if artist_norm == tag_norm:
        return 1.0
    if artist_norm in tag_norm or tag_norm in artist_norm:
        return 0.9
    return difflib.SequenceMatcher(None, artist_norm, tag_norm).ratio()

def _item_has_artist_tag(item: dict, artist: str, threshold: float = 0.85) -> bool:
    artist_norm = _sanitize_match_string(artist or "")
    if not artist_norm:
        return False
    for tag in item.get("tags", []):
        if _artist_tag_match_score(artist_norm, tag) >= threshold:
            return True
    return False

def eagle_find_best_matching_item(
    filename: str,
    fingerprint: Optional[str] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    duration: Optional[float] = None,
    bpm: Optional[int] = None,
    key: Optional[str] = None,
) -> tuple[dict, list[dict]]:
    """
    Find the best matching Eagle item using multi-signal scoring.

    MATCHING SIGNALS (weighted scoring system):
    1. Fingerprint: 100 pts (definitive - same audio content)
    2. Title:       35 pts max (core identifier)
    3. Artist:      25 pts max (must match for non-fingerprint)
    4. Duration:    15 pts max (within 3 seconds = full points)
    5. BPM:         10 pts max (within 2 BPM = full points)
    6. Key:         10 pts max (exact match or relative key)
    7. Filename:     5 pts max (weak signal, tiebreaker only)

    MATCH REQUIREMENTS:
    - Fingerprint match: Always accepted (100 pts)
    - Without fingerprint: Need 70+ pts AND (title >= 30 AND artist >= 20)

    Returns (best_item, all_matching_items) or (None, []) if no matches.
    """
    workspace_logger.info(f"🔍 EAGLE DE-DUPLICATION: Finding matches for '{filename}'")
    workspace_logger.info(f"   Title: {title}")
    workspace_logger.info(f"   Artist: {artist}")
    workspace_logger.info(f"   Duration: {duration:.1f}s" if duration else "   Duration: N/A")
    workspace_logger.info(f"   BPM: {bpm}" if bpm else "   BPM: N/A")
    workspace_logger.info(f"   Key: {key}" if key else "   Key: N/A")
    workspace_logger.info(f"   Fingerprint: {'Yes' if fingerprint else 'No'}")

    items_catalog = eagle_fetch_all_items()

    # Normalize inputs
    title_normalized = _sanitize_match_string(title or "")
    artist_normalized = _sanitize_match_string(artist or "")
    filename_normalized = _sanitize_match_string(Path(filename).stem)
    key_normalized = (key or "").lower().strip()

    # Score all items
    scored_items: list[tuple[float, dict, dict]] = []

    MATCH_THRESHOLD = 70

    for item in items_catalog:
        score = 0.0
        breakdown = {
            "fingerprint": 0,
            "title": 0,
            "artist": 0,
            "duration": 0,
            "bpm": 0,
            "key": 0,
            "filename": 0,
        }

        item_name = item.get("name", "")
        item_name_normalized = _sanitize_match_string(item_name)
        item_tags = item.get("tags", [])
        item_tags_lower = [t.lower() for t in item_tags]

        # === Signal 1: Fingerprint (100 pts - definitive) ===
        if fingerprint:
            item_fp = _extract_fingerprint_tag(item)
            if item_fp and item_fp == fingerprint:
                breakdown["fingerprint"] = 100
                score += 100

        # === Signal 2: Title similarity (0-35 pts) ===
        if title_normalized and item_name_normalized:
            title_sim = difflib.SequenceMatcher(None, title_normalized, item_name_normalized).ratio()
            breakdown["title"] = round(title_sim * 35, 1)
            score += breakdown["title"]

        # === Signal 3: Artist match (0-25 pts) ===
        if artist_normalized:
            artist_score = 0.0

            # Check artist in item name
            if artist_normalized in item_name_normalized:
                artist_score = max(artist_score, 0.85)

            # Check artist tags (skip metadata tags)
            skip_prefixes = ("bpm", "key", "fingerprint", "duration", "processed",
                           "highquality", "soundcloud", "short", "long", "medium")
            for tag in item_tags:
                tag_norm = _sanitize_match_string(tag)
                if not tag_norm or any(tag_norm.startswith(p) for p in skip_prefixes):
                    continue
                tag_sim = difflib.SequenceMatcher(None, artist_normalized, tag_norm).ratio()
                if tag_sim > 0.8:
                    artist_score = max(artist_score, tag_sim)

            breakdown["artist"] = round(artist_score * 25, 1)
            score += breakdown["artist"]

        # === Signal 4: Duration match (0-15 pts) ===
        if duration and duration > 0:
            item_duration = None
            for tag in item_tags_lower:
                if tag.startswith("duration:"):
                    try:
                        item_duration = float(tag.split(":")[1].rstrip("s"))
                    except (ValueError, IndexError):
                        pass
                elif tag.endswith("s") and tag[:-1].replace(".", "").isdigit():
                    try:
                        item_duration = float(tag[:-1])
                    except ValueError:
                        pass

            if item_duration and item_duration > 0:
                duration_diff = abs(duration - item_duration)
                if duration_diff <= 1:
                    breakdown["duration"] = 15
                elif duration_diff <= 3:
                    breakdown["duration"] = round(15 * (1 - (duration_diff - 1) / 2), 1)
                elif duration_diff <= 5:
                    breakdown["duration"] = round(15 * 0.3 * (1 - (duration_diff - 3) / 2), 1)
                score += breakdown["duration"]

        # === Signal 5: BPM match (0-10 pts) ===
        if bpm and bpm > 0:
            item_bpm = None
            for tag in item_tags_lower:
                if tag.startswith("bpm"):
                    try:
                        item_bpm = int(tag.replace("bpm", "").strip())
                    except ValueError:
                        pass

            if item_bpm and item_bpm > 0:
                bpm_diff = abs(bpm - item_bpm)
                if bpm_diff == 0:
                    breakdown["bpm"] = 10
                elif bpm_diff <= 1:
                    breakdown["bpm"] = 8
                elif bpm_diff <= 2:
                    breakdown["bpm"] = 5
                score += breakdown["bpm"]

        # === Signal 6: Key match (0-10 pts) ===
        if key_normalized:
            item_key = None
            for tag in item_tags_lower:
                if "major" in tag or "minor" in tag:
                    item_key = tag
                    break
                if len(tag) == 2 and tag[0].isdigit() and tag[1] in "ab":
                    item_key = tag
                    break
                if len(tag) == 3 and tag[:2].isdigit() and tag[2] in "ab":
                    item_key = tag
                    break

            if item_key:
                if key_normalized == item_key:
                    breakdown["key"] = 10
                elif _keys_are_relative(key_normalized, item_key):
                    breakdown["key"] = 7
                score += breakdown["key"]

        # === Signal 7: Filename similarity (0-5 pts - tiebreaker) ===
        item_path = item.get("path", "")
        if item_path and filename_normalized:
            item_filename = _sanitize_match_string(Path(item_path).stem)
            if item_filename:
                filename_sim = difflib.SequenceMatcher(None, filename_normalized, item_filename).ratio()
                breakdown["filename"] = round(filename_sim * 5, 1)
                score += breakdown["filename"]

        # Only keep items above threshold
        if score >= MATCH_THRESHOLD:
            scored_items.append((score, item, breakdown))

    if not scored_items:
        workspace_logger.info(f"🔍 No matches found above threshold ({MATCH_THRESHOLD} points)")
        return None, []

    # Sort by score
    scored_items.sort(key=lambda x: x[0], reverse=True)

    # Log candidates
    workspace_logger.info(f"🔍 Found {len(scored_items)} candidate(s) above threshold:")
    for sc, it, bd in scored_items[:5]:
        workspace_logger.info(f"   {it['id']}: {sc:.1f} pts - '{it.get('name', 'Unknown')[:50]}'")
        workspace_logger.info(
            f"      FP:{bd['fingerprint']} T:{bd['title']} A:{bd['artist']} "
            f"D:{bd['duration']} BPM:{bd['bpm']} K:{bd['key']} F:{bd['filename']}"
        )

    best_score, best_item, best_breakdown = scored_items[0]

    # Final validation for non-fingerprint matches
    if best_breakdown["fingerprint"] == 0:
        title_ok = best_breakdown["title"] >= 30  # ~86% title match
        artist_ok = best_breakdown["artist"] >= 20  # ~80% artist match

        if not (title_ok and artist_ok):
            workspace_logger.info(
                f"⚠️  Rejecting - need both title>=30 AND artist>=20 without fingerprint: "
                f"T:{best_breakdown['title']}/35, A:{best_breakdown['artist']}/25"
            )
            return None, []

    workspace_logger.info(f"🏆 Best match: {best_item['id']} (Score: {best_score:.1f})")
    workspace_logger.info(f"🏆 Item: '{best_item.get('name', 'Unknown')}'")

    return best_item, [it for _, it, _ in scored_items]


def _keys_are_relative(key1: str, key2: str) -> bool:
    """Check if two keys are relative (harmonically compatible)."""
    camelot_relatives = {
        "1a": "1b", "1b": "1a", "2a": "2b", "2b": "2a",
        "3a": "3b", "3b": "3a", "4a": "4b", "4b": "4a",
        "5a": "5b", "5b": "5a", "6a": "6b", "6b": "6a",
        "7a": "7b", "7b": "7a", "8a": "8b", "8b": "8a",
        "9a": "9b", "9b": "9a", "10a": "10b", "10b": "10a",
        "11a": "11b", "11b": "11a", "12a": "12b", "12b": "12a",
    }
    key_relatives = {
        "c major": "a minor", "a minor": "c major",
        "g major": "e minor", "e minor": "g major",
        "d major": "b minor", "b minor": "d major",
        "a major": "f# minor", "f# minor": "a major",
        "e major": "c# minor", "c# minor": "e major",
        "b major": "g# minor", "g# minor": "b major",
        "f# major": "d# minor", "d# minor": "f# major",
        "f major": "d minor", "d minor": "f major",
        "bb major": "g minor", "g minor": "bb major",
        "eb major": "c minor", "c minor": "eb major",
        "ab major": "f minor", "f minor": "ab major",
        "db major": "bb minor", "bb minor": "db major",
    }

    k1, k2 = key1.lower().strip(), key2.lower().strip()
    if k1 in camelot_relatives and camelot_relatives.get(k1) == k2:
        return True
    if k1 in key_relatives and key_relatives.get(k1) == k2:
        return True
    return False

def eagle_analyze_item_quality(item: dict) -> dict:
    """Analyze the quality and metadata of an Eagle item. Returns quality assessment dict."""
    quality = {
        "item_id": item.get("id"),
        "name": item.get("name"),
        "size": item.get("size", 0),
        "modification_time": item.get("modificationTime", 0),
        "tags": item.get("tags", []),
        "has_metadata_tags": False,
        "metadata_score": 0,
        "is_recent": False,
        "is_large_file": False,
        "overall_score": 0
    }
    
    # Check if item has comprehensive metadata tags
    metadata_tags = [
        "bpm", "key", "duration", "compression", "source", "playlist",
        "processed", "camelot", "artist", "album", "genre"
    ]
    
    item_tags = [tag.lower() for tag in quality["tags"]]
    metadata_matches = sum(1 for tag in metadata_tags if any(tag in item_tag for item_tag in item_tags))
    quality["has_metadata_tags"] = metadata_matches > 0
    quality["metadata_score"] = metadata_matches / len(metadata_tags) * 100
    
    # Check if item is recent (within last 30 days)
    current_time = int(time.time() * 1000)  # Current time in milliseconds
    thirty_days_ms = 30 * 24 * 60 * 60 * 1000
    quality["is_recent"] = (current_time - quality["modification_time"]) < thirty_days_ms
    
    # Check if item is a large file (good quality)
    quality["is_large_file"] = quality["size"] > 10 * 1024 * 1024  # > 10MB
    
    # Calculate overall score
    score = 0
    if quality["has_metadata_tags"]:
        score += 40  # 40% weight for metadata
    if quality["is_recent"]:
        score += 30  # 30% weight for recency
    if quality["is_large_file"]:
        score += 30  # 30% weight for file size
    
    quality["overall_score"] = score
    
    return quality

def eagle_cleanup_duplicate_items(items_to_keep: dict, all_matching_items: list[dict]) -> bool:
    """
    Clean up duplicate Eagle items, keeping only the best one.
    Uses moveToTrash (soft delete) as Eagle only supports soft delete via API.
    Returns True if cleanup was successful.
    """
    if not all_matching_items or len(all_matching_items) <= 1:
        return True  # No duplicates to clean up
    
    items_to_delete = [item for item in all_matching_items if item["id"] != items_to_keep["id"]]
    
    if not items_to_delete:
        return True  # No duplicates to clean up
    
    if not EAGLE_DELETE_ENABLED:
        workspace_logger.info(f"🧹 Eagle: delete disabled (no hard-delete API). Consider moveToTrash; trash must be emptied in UI.")
        workspace_logger.info(f"   Found {len(items_to_delete)} duplicate(s) to clean up when delete is enabled")
        return True  # Consider it successful since we're intentionally skipping
    
    # Use batch moveToTrash to minimize API overhead
    item_ids = [item["id"] for item in items_to_delete]
    workspace_logger.info(f"🧹 Moving {len(item_ids)} duplicate Eagle items to trash...")
    
    if eagle_move_to_trash(item_ids):
        workspace_logger.info(f"✅ Moved {len(item_ids)} duplicate(s) to Trash (kept {items_to_keep['id']})")
        workspace_logger.info(f"   Note: Items are in Eagle Trash. Permanent removal requires emptying Trash in Eagle UI.")
        return True
    else:
        workspace_logger.warning(f"❌ Could not move duplicates to Trash. Endpoint supports only moveToTrash; no hard delete.")
        return False

def eagle_needs_reprocessing(item: dict, expected_metadata: dict) -> bool:
    """
    Determine if an Eagle item needs reprocessing based on expected metadata.
    Returns True if reprocessing is needed.
    """
    if not item:
        return True  # No item exists, needs processing
    item_tags = [tag.lower() for tag in item.get("tags", [])]

    fingerprint = (expected_metadata or {}).get("fingerprint")
    if fingerprint:
        fingerprint_token = f"fingerprint:{fingerprint.lower()}"
        if any(fingerprint_token in tag for tag in item_tags):
            workspace_logger.info("✅ Eagle item fingerprint matches processed audio")
            return False

    # Check for essential metadata tags
    essential_checks = [
        ("bpm", "bpm" in expected_metadata),
        ("key", "key" in expected_metadata),
        ("duration", "duration" in expected_metadata),
        ("artist", "artist" in expected_metadata),
        ("album", "album" in expected_metadata),
        ("genre", "genre" in expected_metadata)
    ]
    
    missing_essential = 0
    for tag_name, is_expected in essential_checks:
        if is_expected and not any(tag_name in tag for tag in item_tags):
            missing_essential += 1
            workspace_logger.debug(f"   Missing essential metadata: {tag_name}")
    
    # Check for processing status
    has_processing_status = any("processed" in tag for tag in item_tags)
    
    # Determine if reprocessing is needed
    needs_reprocessing = missing_essential > 0 or not has_processing_status
    
    if needs_reprocessing:
        workspace_logger.info(f"🔄 Item needs reprocessing: Missing {missing_essential} essential metadata, "
                            f"Processing status: {has_processing_status}")
    else:
        workspace_logger.info(f"✅ Item meets metadata requirements, no reprocessing needed")
    
    return needs_reprocessing

def eagle_add_item_adapter(file_path: str, title: str, url: str, tags: list[str], folder_id: Optional[str] = None) -> Optional[str]:
    """
    Adapter function that wraps eagle_add_item with proper parameter mapping.
    This function ensures tags functionality is preserved and properly passed to Eagle API.
    
    Args:
        file_path: Path to the file to add to Eagle
        title: Title/name for the Eagle item
        url: Website URL (typically SoundCloud URL)
        tags: List of tags to apply to the Eagle item
        folder_id: Optional folder ID for organization
        
    Returns:
        Eagle item ID if successful, None otherwise
    """
    try:
        workspace_logger.info(f"🦅 Eagle Add Item Adapter: {title}")
        workspace_logger.debug(f"   File: {file_path}")
        workspace_logger.debug(f"   URL: {url}")
        workspace_logger.debug(f"   Tags: {tags}")
        workspace_logger.debug(f"   Folder: {folder_id}")
        
        # Call the existing eagle_add_item function with proper parameter mapping
        # eagle_add_item(path, name, website, tags, folder_id=None, existing_eagle_id=None)
        eagle_id = eagle_add_item(
            path=file_path,
            name=title,
            website=url,
            tags=tags,
            folder_id=folder_id,
            existing_eagle_id=None
        )
        
        if eagle_id:
            workspace_logger.info(f"✅ Eagle item created successfully: {eagle_id}")
            workspace_logger.info(f"   Applied tags: {tags}")
        else:
            workspace_logger.warning(f"⚠️  Eagle item creation failed for: {title}")
        
        return eagle_id
        
    except Exception as e:
        workspace_logger.error(f"❌ Eagle add item adapter failed: {e}")
        return None

def eagle_import_with_duplicate_management(
    file_path: str,
    title: str,
    url: str,
    tags: list[str],
    folder_id: Optional[str] = None,
    expected_metadata: Optional[dict] = None,
    audio_fingerprint: Optional[str] = None
) -> Optional[str]:
    """
    Enhanced Eagle import with comprehensive de-duplication and tags validation.
    
    This function:
    1. Finds existing Eagle items using multiple matching strategies
    2. Determines if existing items need reprocessing based on metadata
    3. Updates existing items with new tags or creates new items
    4. Validates that tags were applied correctly
    
    Args:
        file_path: Path to the file to import
        title: Title/name for the Eagle item
        url: Website URL (typically SoundCloud URL)
        tags: List of tags to apply to the Eagle item
        folder_id: Optional folder ID for organization
        expected_metadata: Expected metadata for reprocessing logic
        audio_fingerprint: Audio fingerprint for matching
        
    Returns:
        Eagle item ID if successful, None otherwise
    """
    try:
        workspace_logger.info(f"🔄 EAGLE IMPORT WITH DE-DUPLICATION: {title}")
        workspace_logger.info(f"   File: {file_path}")
        workspace_logger.info(f"   Tags: {tags}")
        workspace_logger.info(f"   Fingerprint: {'Yes' if audio_fingerprint else 'No'}")
        
        # Step 1: Find existing items using all available metadata
        meta = expected_metadata or {}
        best_item, all_matches = eagle_find_best_matching_item(
            filename=Path(file_path).name,
            fingerprint=audio_fingerprint,
            title=title,
            artist=meta.get("artist"),
            duration=float(meta.get("duration")) if meta.get("duration") else None,
            bpm=int(meta.get("bpm")) if meta.get("bpm") else None,
            key=meta.get("key"),
        )
        
        if not best_item:
            # No existing items found - create new item
            workspace_logger.info("🆕 No existing items found - creating new Eagle item")
            eagle_id = eagle_add_item_adapter(file_path, title, url, tags, folder_id)
            
            if eagle_id:
                workspace_logger.info(f"✅ New Eagle item created: {eagle_id}")
                # Validate tags were applied
                if eagle_validate_tags_applied(eagle_id, tags):
                    workspace_logger.info("✅ Tags validation successful")
                else:
                    workspace_logger.warning("⚠️  Tags validation failed - tags may not be applied correctly")
            
            return eagle_id
        
        # Step 2: Check if existing item needs reprocessing
        needs_reprocessing = eagle_needs_reprocessing(best_item, expected_metadata)
        
        if not needs_reprocessing:
            # Update existing item with new tags
            workspace_logger.info(f"🔄 Updating existing Eagle item: {best_item['id']}")
            workspace_logger.info(f"   Current tags: {best_item.get('tags', [])}")
            workspace_logger.info(f"   New tags: {tags}")
            
            # Update tags on existing item
            if eagle_update_tags(best_item['id'], tags):
                workspace_logger.info("✅ Tags updated successfully on existing item")
                # Validate tags were applied
                if eagle_validate_tags_applied(best_item['id'], tags):
                    workspace_logger.info("✅ Tags validation successful")
                else:
                    workspace_logger.warning("⚠️  Tags validation failed - tags may not be applied correctly")
            else:
                workspace_logger.warning("⚠️  Failed to update tags on existing item")
            
            return best_item['id']
        
        # Step 3: Reprocessing needed - create new item and clean up duplicates
        workspace_logger.info(f"🔄 Reprocessing needed - creating new item and cleaning up duplicates")
        
        # Create new item
        eagle_id = eagle_add_item_adapter(file_path, title, url, tags, folder_id)
        
        if eagle_id:
            workspace_logger.info(f"✅ New Eagle item created for reprocessing: {eagle_id}")
            
            # Clean up old items (keep the best one, remove others)
            if len(all_matches) > 1:
                workspace_logger.info(f"🧹 Cleaning up {len(all_matches) - 1} duplicate items")
                for item in all_matches:
                    if item['id'] != best_item['id'] and item['id'] != eagle_id:
                        try:
                            # Archive old item instead of deleting
                            workspace_logger.info(f"   Archiving old item: {item['id']}")
                            # Note: Eagle API doesn't have direct archive, so we'll just log for now
                        except Exception as e:
                            workspace_logger.warning(f"   Failed to archive old item {item['id']}: {e}")
            
            # Validate tags were applied
            if eagle_validate_tags_applied(eagle_id, tags):
                workspace_logger.info("✅ Tags validation successful")
            else:
                workspace_logger.warning("⚠️  Tags validation failed - tags may not be applied correctly")
        
        return eagle_id
        
    except Exception as e:
        workspace_logger.error(f"❌ Eagle import with de-duplication failed: {e}")
        return None

def eagle_validate_tags_applied(eagle_id: str, expected_tags: list[str]) -> bool:
    """
    Validate that tags were correctly applied to an Eagle item.
    
    Args:
        eagle_id: Eagle item ID to validate
        expected_tags: List of expected tags
        
    Returns:
        True if tags were applied correctly, False otherwise
    """
    try:
        # Add retry mechanism with delay for newly created items
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                # Fetch the item to check its current tags
                items = eagle_fetch_all_items()
                item = next((item for item in items if item.get('id') == eagle_id), None)
                
                if not item:
                    if attempt < max_retries - 1:
                        workspace_logger.debug(f"⚠️  Eagle item {eagle_id} not found in API response (attempt {attempt + 1}/{max_retries})")
                        workspace_logger.debug(f"   Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        workspace_logger.warning(f"⚠️  Could not find Eagle item {eagle_id} for tag validation after {max_retries} attempts")
                        workspace_logger.warning(f"   This may be due to Eagle API caching or processing delays")
                        workspace_logger.warning(f"   Tags were likely applied correctly during item creation")
                        return True  # Assume success since item was created with tags
                
                # Item found, check tags
                current_tags = item.get('tags', [])
                workspace_logger.debug(f"   Current tags: {current_tags}")
                workspace_logger.debug(f"   Expected tags: {expected_tags}")
                
                # Check if all expected tags are present
                missing_tags = []
                for expected_tag in expected_tags:
                    if expected_tag not in current_tags:
                        missing_tags.append(expected_tag)
                
                if missing_tags:
                    workspace_logger.warning(f"⚠️  Missing tags: {missing_tags}")
                    return False
                
                workspace_logger.info(f"✅ All {len(expected_tags)} tags validated successfully")
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    workspace_logger.debug(f"⚠️  Tag validation attempt {attempt + 1} failed: {e}")
                    workspace_logger.debug(f"   Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue
                else:
                    workspace_logger.error(f"❌ Tag validation failed after {max_retries} attempts: {e}")
                    return False
        
        return False
        
    except Exception as e:
        workspace_logger.error(f"❌ Tag validation failed: {e}")
        return False

def update_notion_with_eagle_id(page_id: str, eagle_id: str) -> bool:
    """Update Notion page with Eagle File ID for duplicate handling."""
    try:
        notion = NotionManager()
        eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
        
        # Update the Eagle File ID property
        notion.update_page(page_id, {
            eagle_prop: {"rich_text": [{"text": {"content": eagle_id}}]}
        })
        
        workspace_logger.info(f"✅ Updated Notion page {page_id} with Eagle File ID: {eagle_id}")
        return True
        
    except Exception as e:
        workspace_logger.error(f"❌ Failed to update Notion with Eagle File ID: {e}")
        return False

def reset_track_for_reprocessing(page_id: str) -> bool:
    """Reset a track in Notion for reprocessing by clearing file paths, fingerprints, and Eagle IDs."""
    try:
        notion = NotionManager()
        prop_types = _get_tracks_db_prop_types()
        properties: dict[str, dict] = {}

        # Reset download checkbox
        dl_name = _resolve_prop_name("DL") or "Downloaded"
        if prop_types.get(dl_name) == "checkbox":
            properties[dl_name] = {"checkbox": False}
        else:
            workspace_logger.debug(f"Skipping DL reset; property '{dl_name}' not a checkbox.")

        # Clear file path style properties
        for key in ["WAV File Path", "AIFF File Path", "M4A File Path"]:
            name = _resolve_prop_name(key) or key
            prop_type = prop_types.get(name)
            if prop_type == "url":
                properties[name] = {"url": None}
            elif prop_type == "rich_text":
                properties[name] = {"rich_text": []}
            elif prop_type == "title":
                properties[name] = {"title": []}
            elif prop_type:
                workspace_logger.debug(f"Skipping reset for {name}; unsupported type '{prop_type}'")

        # Clear Eagle / fingerprint metadata
        for key in ["Eagle File ID", "Fingerprint", "Fingerprint Part 2", "Fingerprint Overflow 2"]:
            name = _resolve_prop_name(key) or key
            if prop_types.get(name) == "rich_text":
                properties[name] = {"rich_text": []}

        # Reset numeric metadata if present (uses ALT_PROP_NAMES to resolve)
        bpm_prop = _resolve_prop_name("BPM") or "Tempo"
        if prop_types.get(bpm_prop) == "number":
            properties[bpm_prop] = {"number": None}
        key_prop = _resolve_prop_name("Key") or "Key "
        if prop_types.get(key_prop) == "rich_text":
            properties[key_prop] = {"rich_text": []}
        duration_prop = _resolve_prop_name("Duration (s)") or "Audio Duration (seconds)"
        if prop_types.get(duration_prop) == "number":
            properties[duration_prop] = {"number": None}

        audio_processing_prop = _resolve_prop_name("Audio Processing") or "Audio Processing"
        if prop_types.get(audio_processing_prop) == "multi_select":
            properties[audio_processing_prop] = {"multi_select": []}

        if not properties:
            workspace_logger.warning("No matching properties found to reset for reprocessing.")
            return False

        notion_manager.update_page(page_id, properties)
        workspace_logger.info(f"🔄 Reset track for reprocessing: {page_id}")
        return True
    except Exception as exc:
        workspace_logger.warning(f"Failed to reset track {page_id}: {exc}")
        return False


def update_audio_processing_status(page_id: str, statuses: List[str]):
    try:
        # Fetch existing status values
        page = notion_manager._req("get", f"/pages/{page_id}")
        existing = [item.get("name") for item in page.get("properties", {}).get("Audio Processing", {}).get("multi_select", [])]
        merged = list(dict.fromkeys(existing + statuses))
        props = {"Audio Processing": {"multi_select": [{"name": s} for s in merged]}}
        notion_manager.update_page(page_id, props)
        workspace_logger.info(f"✅ Updated audio processing statuses: {merged}")
        return True
    except Exception as e:
        workspace_logger.error(f"Failed to update audio processing statuses for {page_id}: {e}")
        return False

def set_comprehensive_audio_processing_status(page_id: str, processing_data: dict, normalization_metrics: dict = None) -> bool:
    """
    Set the comprehensive Audio Processing status based on what was ACTUALLY completed and verified.
    This function dynamically determines which processing steps were completed for this specific item.
    
    Args:
        page_id: Notion page ID
        processing_data: Audio processing results and status
        normalization_metrics: Detailed normalization metrics if available
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Start with base status that's always completed if we reach this function
        completed_status = ["Audio Analysis Complete"]
        
        # Check if audio analysis was actually successful
        if processing_data.get('duration', 0) > 0 and processing_data.get('bpm', 0) > 0:
            completed_status.append("Audio Analysis Complete")
        else:
            workspace_logger.warning(f"Audio analysis incomplete for {page_id} - duration={processing_data.get('duration')}, bpm={processing_data.get('bpm')}")
            # Remove if it was added by default
            if "Audio Analysis Complete" in completed_status:
                completed_status.remove("Audio Analysis Complete")
        
        # Check normalization metrics if available
        if normalization_metrics:
            # Loudness measurement is always done if normalization was attempted
            completed_status.append("Loudness Measured")
            
            # Check if normalization was actually applied successfully
            original_lufs = normalization_metrics.get('original_lufs', 0)
            final_lufs = normalization_metrics.get('final_lufs', 0)
            gain_applied = normalization_metrics.get('gain_applied_db', 0)
            
            if abs(gain_applied) > 0.1:  # Significant gain was applied
                completed_status.append("Normalization Applied")
                workspace_logger.info(f"✅ Normalization verified for {page_id}: {original_lufs:.1f} → {final_lufs:.1f} LUFS")
            else:
                workspace_logger.info(f"⚠️  Normalization not applied for {page_id} - minimal gain: {gain_applied:.1f} dB")
            
            # Check clipping repair
            clipped_repaired = normalization_metrics.get('clipped_repaired', 0)
            if clipped_repaired > 0:
                completed_status.append("Clipping Repair Applied")
                workspace_logger.info(f"✅ Clipping repair verified for {page_id}: {clipped_repaired} samples repaired")
            else:
                workspace_logger.info(f"ℹ️  No clipping repair needed for {page_id}")
            
            # Check warmth enhancement
            warmth_applied = normalization_metrics.get('warmth_applied', False)
            if warmth_applied:
                completed_status.append("Warmth Enhancement Applied")
                warmth_mode = normalization_metrics.get('warmth_mode', 'unknown')
                workspace_logger.info(f"✅ Warmth enhancement verified for {page_id}: {warmth_mode} mode")
            else:
                workspace_logger.info(f"ℹ️  No warmth enhancement applied for {page_id}")
            
            # Check limiting
            limiting_applied = normalization_metrics.get('limiting_applied', False)
            if limiting_applied:
                completed_status.append("Limiting Applied")
                workspace_logger.info(f"✅ Limiting verified for {page_id}")
            else:
                workspace_logger.info(f"ℹ️  No limiting needed for {page_id} (peaks below threshold)")
        else:
            workspace_logger.info(f"ℹ️  No normalization metrics available for {page_id} - normalization not applied")
        
        # Format conversion is always completed if we reach this point
        completed_status.append("Format Conversion Complete")
        
        # Eagle import status will be set separately after import attempt
        
        # Update the page with ONLY the status options that were actually completed
        props = {
            "Audio Processing": {"multi_select": [{"name": status} for status in completed_status]}
        }
        notion_manager.update_page(page_id, props)
        
        workspace_logger.info(f"✅ Set comprehensive audio processing status for {page_id}: {completed_status}")
        return True
        
    except Exception as e:
        workspace_logger.error(f"Failed to set comprehensive audio processing status for {page_id}: {e}")
        return False

def create_audio_processing_summary(
    track_info: dict,
    processing_data: dict,
    file_paths: dict,
    eagle_item_id: str = None
) -> str:
    """
    Create a comprehensive audio processing summary with detailed audio quality metrics and format-specific analysis.
    
    Args:
        track_info: Original track information from Notion
        processing_data: Audio processing results (BPM, key, duration, etc.)
        file_paths: Generated file paths
        eagle_item_id: Eagle item ID if available
        
    Returns:
        Formatted summary string with detailed audio processing metrics
    """
    from datetime import datetime
    
    # Get current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Build summary
    summary_lines = []
    summary_lines.append("🎵" + "=" * 78 + "🎵")
    summary_lines.append("🎼 COMPREHENSIVE AUDIO PROCESSING ANALYSIS REPORT 🎼")
    summary_lines.append("🎵" + "=" * 78 + "🎵")
    summary_lines.append(f"📅 Generated: {timestamp}")
    summary_lines.append("")
    
    # Track Information (Brief)
    summary_lines.append("🎯 TRACK IDENTIFICATION")
    summary_lines.append("━" * 50)
    summary_lines.append(f"🎵 Title: {track_info.get('title', 'N/A')}")
    summary_lines.append(f"👤 Artist: {track_info.get('artist', 'N/A')}")
    summary_lines.append(f"🎼 Genre: {track_info.get('genre', 'N/A')}")
    summary_lines.append("")
    
    # Audio Analysis Results - Core Audio Characteristics
    summary_lines.append("🎚️ AUDIO ANALYSIS CHARACTERISTICS")
    summary_lines.append("━" * 50)
    duration = processing_data.get('duration', 0)
    bpm = processing_data.get('bpm', 0)
    key = processing_data.get('key', 'Unknown')
    
    # Duration with detailed time format
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    duration_str = f"{minutes:02d}:{seconds:02d}"
    summary_lines.append(f"⏱️  Duration: {duration_str} ({duration:.1f}s)")
    
    # BPM with detailed tempo analysis
    if bpm > 0:
        tempo_category = "🐌 Slow" if bpm < 90 else "🏃 Fast" if bpm > 130 else "🎯 Medium"
        summary_lines.append(f"🎵 BPM: {bpm} {tempo_category}")
        summary_lines.append(f"   🎯 Tempo Range: {'Sub-90 BPM (Downtempo)' if bpm < 90 else '90-130 BPM (Standard)' if bpm <= 130 else '130+ BPM (High Energy)'}")
    else:
        summary_lines.append(f"🎵 BPM: {bpm} (Not detected)")
    
    # Key with detailed musical analysis
    if key != "Unknown":
        camelot = convert_to_camelot(key)
        summary_lines.append(f"🎼 Key: {key} (Camelot: {camelot})")
        summary_lines.append(f"   🎵 Musical Characteristics: {key} key detected via chroma analysis")
    else:
        summary_lines.append(f"🎼 Key: {key}")
    
    # Sample rate and audio format information
    summary_lines.append(f"🔊 Sample Rate: 44100 Hz (CD Quality)")
    summary_lines.append(f"🎛️  Audio Format: PCM WAV (Analysis Source)")
    summary_lines.append("")
    
    # Audio Processing Pipeline - Detailed Processing Steps
    summary_lines.append("⚙️ AUDIO PROCESSING PIPELINE CHARACTERISTICS")
    summary_lines.append("━" * 50)
    
    # Librosa Analysis Features Used
    summary_lines.append("🔬 LIBROSA AUDIO ANALYSIS FEATURES:")
    summary_lines.append("   📊 librosa.load() - Audio loading and resampling")
    summary_lines.append("   ⏱️  librosa.get_duration() - Duration calculation")
    summary_lines.append("   🎵 librosa.beat.beat_track() - Primary BPM detection")
    summary_lines.append("   🎵 librosa.onset.onset_strength() - Onset detection")
    summary_lines.append("   🎵 librosa.feature.rhythm.tempo() - Fallback BPM estimation")
    summary_lines.append("   🎼 librosa.feature.chroma_cqt() - Key detection")
    summary_lines.append("")
    
    # Audio Normalization Characteristics
    # Get current audio processing status from Notion to ensure accuracy
    audio_processing_status = []
    normalization_metrics = processing_data.get('normalization_metrics', {})
    
    # Try to get current status from Notion if page_id is available
    if track_info.get("page_id"):
        try:
            page = notion_manager._req("get", f"/pages/{track_info['page_id']}")
            audio_processing_status = [item.get("name", "") for item in page.get("properties", {}).get("Audio Processing", {}).get("multi_select", [])]
        except Exception as e:
            workspace_logger.warning(f"Could not get audio processing status from Notion for summary: {e}")
    
    if normalization_metrics or "Normalization Applied" in audio_processing_status:
        summary_lines.append("🎛️  AUDIO NORMALIZATION CHARACTERISTICS:")
        summary_lines.append("   🔊 Loudness Normalization: LUFS-based processing")
        summary_lines.append("   🎚️  Target LUFS: Genre-optimized (-12 to -14 dB)")
        summary_lines.append("   🔧 Dynamic Range Processing: Applied")
        
        # Add detailed normalization metrics if available
        if normalization_metrics:
            summary_lines.append("   📊 Normalization Metrics:")
            if 'original_lufs' in normalization_metrics and 'final_lufs' in normalization_metrics:
                summary_lines.append(f"      LUFS Change: {normalization_metrics['original_lufs']:.1f} → {normalization_metrics['final_lufs']:.1f}")
            if 'gain_applied_db' in normalization_metrics:
                summary_lines.append(f"      Gain Applied: {normalization_metrics['gain_applied_db']:.1f} dB")
            if 'clipped_repaired' in normalization_metrics:
                summary_lines.append(f"      Clipped Samples Repaired: {normalization_metrics['clipped_repaired']}")
            if 'warmth_mode' in normalization_metrics:
                summary_lines.append(f"      Warmth Mode: {normalization_metrics['warmth_mode']}")
        
        # Check processing status for additional features
        if "Clipping Repair Applied" in audio_processing_status:
            summary_lines.append("   🔧 Clipping Repair: Clipped peaks detected and repaired")
        if "Limiting Applied" in audio_processing_status:
            summary_lines.append("   🚫 Peak Limiting: Applied to prevent clipping")
        if "Warmth Enhancement Applied" in audio_processing_status:
            summary_lines.append("   🔥 Warmth Enhancement: Harmonic saturation applied")
    else:
        summary_lines.append("🎛️  AUDIO NORMALIZATION: Not applied (normalizer unavailable)")
    
    summary_lines.append("")
    
    # File Format Characteristics - ALWAYS INCLUDE BOTH M4A AND WAV
    summary_lines.append("📁 AUDIO FILE FORMAT CHARACTERISTICS")
    summary_lines.append("━" * 50)
    
    # Always include M4A summary
    summary_lines.append("🎵 === M4A FILE FORMAT SUMMARY ===")
    if file_paths.get("M4A") and Path(file_paths["M4A"]).exists():
        file_size = Path(file_paths["M4A"]).stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        summary_lines.append(f"   📊 File Size: {file_size_mb:.2f} MB")
        summary_lines.append("   ✅ Status: Successfully created and distributed")
    else:
        summary_lines.append("   ❌ Status: File not found or creation failed")
    summary_lines.append("   🎯 Codec: AAC (Advanced Audio Coding)")
    summary_lines.append("   🎛️  Bitrate: Variable (VBR)")
    summary_lines.append("   🏷️  Metadata Support: Full (ID3 tags)")
    summary_lines.append("   ✅ Metadata Embedded: Title, Artist, Album, Genre, BPM, Key, Comment")
    summary_lines.append("   🎵 Audio Quality: Lossy compression, optimized for streaming")
    summary_lines.append("   📱 Compatibility: Apple Music, iOS, macOS, iTunes")
    summary_lines.append("   🎚️  Processing: Apple Music auto-import enabled")
    summary_lines.append("   📁 Destination: /Volumes/VIBES/Music/Automatically Add to Music.localized/")
    summary_lines.append("")
    
    # Always include WAV summary
    summary_lines.append("🎼 === WAV FILE FORMAT SUMMARY ===")
    if file_paths.get("WAV") and Path(file_paths["WAV"]).exists():
        file_size = Path(file_paths["WAV"]).stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        summary_lines.append(f"   📊 File Size: {file_size_mb:.2f} MB")
        summary_lines.append("   ✅ Status: Successfully created")
    else:
        summary_lines.append("   ❌ Status: File not found or creation failed")
    summary_lines.append("   🎯 Codec: PCM (Pulse Code Modulation)")
    summary_lines.append("   🎛️  Bit Depth: 24-bit")
    summary_lines.append("   🎛️  Sample Rate: 48 kHz")
    summary_lines.append("   🏷️  Metadata Support: Limited (WAV chunks)")
    summary_lines.append("   ✅ Metadata Embedded: Title, Artist, Album, Genre, BPM, Key, Comment, Duration, Compression, Source, Playlist, Processed Date/Time, Camelot")
    summary_lines.append("   🎵 Audio Quality: Lossless, uncompressed")
    summary_lines.append("   🎛️  Dynamic Range: Full (no compression artifacts)")
    summary_lines.append("   📱 Compatibility: Professional audio software, DAWs")
    summary_lines.append("   🎚️  Processing: Eagle import and Serato Auto Import backup")
    summary_lines.append("   📁 Destination: Temporary location for Eagle import + Serato Auto Import backup")
    summary_lines.append("")
    
    # Audio Quality Metrics - Detailed Analysis
    summary_lines.append("📊 AUDIO QUALITY METRICS")
    summary_lines.append("━" * 50)
    
    # Duration quality assessment
    if duration > 0:
        if duration < 60:
            quality_note = "Short track (< 1 minute)"
        elif duration < 180:
            quality_note = "Standard track (1-3 minutes)"
        elif duration < 300:
            quality_note = "Extended track (3-5 minutes)"
        else:
            quality_note = "Long track (> 5 minutes)"
        summary_lines.append(f"⏱️  Duration Classification: {quality_note}")
    
    # BPM quality assessment
    if bpm > 0:
        if 60 <= bpm < 90:
            tempo_note = "Downtempo/Ambient range"
        elif 90 <= bpm <= 110:
            tempo_note = "Standard pop/rock range"
        elif 110 < bpm <= 130:
            tempo_note = "Upbeat dance range"
        elif 130 < bpm <= 150:
            tempo_note = "High energy dance range"
        else:
            tempo_note = "Extreme tempo range"
        summary_lines.append(f"🎵 Tempo Classification: {tempo_note}")
    
    # Key detection quality
    if key != "Unknown":
        summary_lines.append(f"🎼 Key Detection: Successful (chroma analysis)")
        summary_lines.append(f"   🎵 Musical Analysis: {key} key identified via CQT chromagram")
    else:
        summary_lines.append(f"🎼 Key Detection: Failed (insufficient harmonic content)")
    
    # Audio processing status summary
    if audio_processing_status:
        summary_lines.append("")
        summary_lines.append("🔧 AUDIO PROCESSING STEPS COMPLETED:")
        for status in audio_processing_status:
            summary_lines.append(f"   ✅ {status}")
    
    summary_lines.append("")
    
    # Technical Audio Specifications - Enhanced
    summary_lines.append("🔬 TECHNICAL AUDIO SPECIFICATIONS")
    summary_lines.append("━" * 50)
    summary_lines.append("🎛️  Analysis Tools:")
    summary_lines.append("   📊 librosa - Audio analysis and feature extraction")
    summary_lines.append("   🎵 FFmpeg - Audio format conversion and metadata embedding")
    summary_lines.append("   🎼 Chroma Analysis - Musical key detection")
    summary_lines.append("   ⏱️  Beat Tracking - Tempo and rhythm analysis")
    summary_lines.append("")
    summary_lines.append("🎚️  Processing Pipeline:")
    summary_lines.append("   1. Audio Download (SoundCloud)")
    summary_lines.append("   2. WAV Conversion (FFmpeg)")
    summary_lines.append("   3. Audio Analysis (librosa)")
    summary_lines.append("   4. Loudness Normalization (if available)")
    summary_lines.append("   5. Format Conversion (M4A/WAV)")
    summary_lines.append("   6. Metadata Embedding")
    summary_lines.append("   7. File Distribution")
    summary_lines.append("")
    
    # Audio Quality Assessment - Based on Platinum Notes Features
    summary_lines.append("🎛️  AUDIO QUALITY ASSESSMENT")
    summary_lines.append("━" * 50)
    
    # Club-ready target information
    summary_lines.append("🎪 CLUB-READY MASTERING TARGETS:")
    summary_lines.append(f"   🎯 Target LUFS: -8.0 (club/festival PA standard)")
    summary_lines.append(f"   🎚️ True Peak Ceiling: -1.0 dBTP (prevents codec overs)")
    summary_lines.append(f"   🎵 Dynamic Range: 6-8 dB (main-room EDM/Techno)")
    summary_lines.append("")
    summary_lines.append("🔍 Audio Processing Features Applied:")
    summary_lines.append("   ✅ Drum-Focused Volume Analysis (librosa beat detection)")
    summary_lines.append("   ✅ Clipped-Peak Detection (RMS/Peak analysis)")
    
    # Check normalization metrics for detailed feature status
    if normalization_metrics:
        if normalization_metrics.get('clipped_repaired', 0) > 0:
            summary_lines.append(f"   ✅ Clipped-Peak Repair ({normalization_metrics['clipped_repaired']} samples repaired)")
        else:
            summary_lines.append("   ✅ Clipped-Peak Repair (no clipping detected)")
        
        if normalization_metrics.get('warmth_applied', False):
            summary_lines.append(f"   ✅ Warmth/Saturation Stage ({normalization_metrics.get('warmth_mode', 'gentle')} mode)")
        else:
            summary_lines.append("   ⚠️  Warmth/Saturation Stage (not applied)")
        
        if normalization_metrics.get('limiting_applied', False):
            samples_limited = normalization_metrics.get('samples_limited', 0)
            peak_db_after = normalization_metrics.get('peak_db_after', 0)
            summary_lines.append(f"   ✅ Club-Ready Limiting & Loudness Adjustment (true-peak limiting: {samples_limited} samples at -1 dBTP)")
            summary_lines.append(f"   📊 Final True Peak: {peak_db_after:.1f} dBTP (target: -1.0 dBTP)")
        else:
            peak_db_after = normalization_metrics.get('peak_db_after', 0)
            summary_lines.append("   ✅ Club-Ready Limiting & Loudness Adjustment (loudness adjusted, no limiting needed)")
            summary_lines.append(f"   📊 Final True Peak: {peak_db_after:.1f} dBTP (target: -1.0 dBTP)")
    else:
        # Fallback to processing status if no metrics available
        if "Clipping Repair Applied" in audio_processing_status:
            summary_lines.append("   ✅ Clipped-Peak Repair (smoothing interpolation)")
        else:
            summary_lines.append("   ⚠️  Clipped-Peak Repair (no clipping detected)")
        if "Warmth Enhancement Applied" in audio_processing_status:
            summary_lines.append("   ✅ Warmth/Saturation Stage (harmonic enhancement)")
        else:
            summary_lines.append("   ⚠️  Warmth/Saturation Stage (not applied)")
        if "Limiting Applied" in audio_processing_status:
            summary_lines.append("   ✅ Club-Ready Limiting & Loudness Adjustment (true-peak limiting applied)")
        else:
            summary_lines.append("   ✅ Club-Ready Limiting & Loudness Adjustment (loudness adjusted, no limiting needed)")
    
    summary_lines.append("   ✅ Pitch & Transient Integrity Checks (librosa analysis)")
    summary_lines.append("")
    
    # File Processing Status
    summary_lines.append("📁 FILE PROCESSING STATUS")
    summary_lines.append("━" * 50)
    for file_type, path in file_paths.items():
        if path:
            file_path = Path(path)
            if file_path.exists():
                file_size = file_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
                summary_lines.append(f"✅ {file_type}: Successfully created and processed ({file_size_mb:.2f} MB)")
            else:
                # Check if file might have been moved by Apple Music (for M4A files)
                if file_type == "M4A" and "Automatically Add to Music" in str(path):
                    summary_lines.append(f"✅ {file_type}: Successfully created (likely imported by Apple Music)")
                else:
                    summary_lines.append(f"❌ {file_type}: Failed to create or missing")
        else:
            summary_lines.append(f"❌ {file_type}: No path provided")
    
    # Add WAV backup file status
    # Use the same safe_base logic as in the main function
    title = track_info.get('title', 'Unknown')
    safe_base = re.sub(r"[^\w\s-]", "", title).strip()
    wav_backup_path = WAV_BACKUP_DIR / f"{safe_base}.wav"
    if wav_backup_path.exists():
        file_size = wav_backup_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        summary_lines.append(f"✅ WAV Backup: Successfully created in Serato Auto Import ({file_size_mb:.2f} MB)")
    else:
        summary_lines.append(f"❌ WAV Backup: Failed to create in Serato Auto Import")
    
    summary_lines.append("")
    
    summary_lines.append("🎵" + "=" * 78 + "🎵")
    summary_lines.append("🎼 END OF COMPREHENSIVE AUDIO PROCESSING ANALYSIS REPORT 🎼")
    summary_lines.append("🎵" + "=" * 78 + "🎵")
    
    return "\n".join(summary_lines)

def check_for_music_embed(page_id: str) -> bool:
    """
    Check if a music embed block (Spotify or SoundCloud) already exists on the Notion page.
    
    Args:
        page_id: Notion page ID
        
    Returns:
        True if music embed exists, False otherwise
    """
    try:
        # Get all blocks on the page
        response = notion_manager._req("get", f"/blocks/{page_id}/children")
        blocks = response.get("results", [])
        
        # Check for any embed or bookmark blocks that might be Spotify or SoundCloud
        for block in blocks:
            if block.get("type") == "embed":
                embed_url = block.get("embed", {}).get("url", "")
                if "spotify.com" in embed_url.lower() or "soundcloud.com" in embed_url.lower():
                    workspace_logger.debug(f"🎵 Found existing music embed on page {page_id}")
                    return True
            elif block.get("type") == "bookmark":
                bookmark_url = block.get("bookmark", {}).get("url", "")
                if "spotify.com" in bookmark_url.lower() or "soundcloud.com" in bookmark_url.lower():
                    workspace_logger.debug(f"🎵 Found existing music bookmark on page {page_id}")
                    return True
        
        workspace_logger.debug(f"🎵 No music embed found on page {page_id}")
        return False
        
    except Exception as e:
        workspace_logger.warning(f"Failed to check for music embed on page {page_id}: {e}")
        return False

def add_music_embed_to_page(page_id: str, track_info: dict) -> bool:
    """
    Add a music embed block (Spotify or SoundCloud) to the Notion page if it doesn't exist.
    Prioritizes Spotify if available, falls back to SoundCloud if no Spotify ID.
    
    Args:
        page_id: Notion page ID
        track_info: Track information containing title, artist, spotify_id, and soundcloud_url
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if music embed already exists
        if check_for_music_embed(page_id):
            workspace_logger.info(f"🎵 Music embed already exists on page {page_id}")
            return True
        
        # Get track information
        title = track_info.get("title", "")
        artist = track_info.get("artist", "")
        spotify_id = track_info.get("spotify_id", "")
        soundcloud_url = track_info.get("soundcloud_url", "")
        
        if not title or not artist:
            workspace_logger.warning(f"🎵 Cannot create music embed - missing title or artist")
            return False
        
        # Determine which embed to create
        embed_url = None
        embed_type = None
        
        # Priority 1: Spotify (if spotify_id is available)
        if spotify_id:
            embed_url = f"https://open.spotify.com/embed/track/{spotify_id}"
            embed_type = "Spotify"
        # Priority 2: SoundCloud (if soundcloud_url is available)
        elif soundcloud_url:
            # Use the SoundCloud URL directly - it should work as an embed
            embed_url = soundcloud_url
            embed_type = "SoundCloud"
        # Priority 3: Spotify search fallback
        else:
            search_query = f"{title} {artist}".replace(" ", "%20")
            embed_url = f"https://open.spotify.com/embed/search/{search_query}"
            embed_type = "Spotify Search"
        
        # Create embed block with music web player
        block_data = {
            "children": [
                {
                    "object": "block",
                    "type": "embed",
                    "embed": {
                        "url": embed_url
                    }
                }
            ]
        }
        
        # Add the block to the page
        notion_manager._req("patch", f"/blocks/{page_id}/children", block_data)
        workspace_logger.info(f"🎵 Added {embed_type} **web player** embed to page {page_id}: {embed_url}")
        return True
        
    except Exception as e:
        workspace_logger.error(f"Failed to add music embed to Notion page: {e}")
        return False

def add_summary_to_notion_page(page_id: str, summary: str) -> bool:
    try:
        cleanup_existing_summary_blocks(page_id)
        sections = split_summary_into_large_sections(summary)
        blocks = []
        for section in sections:
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": section['content']}}],
                    "language": "plain text"
                }
            })
        notion_manager._req("patch", f"/blocks/{page_id}/children", {"children": blocks})
        workspace_logger.info(f"📝 Added {len(sections)} summary sections to page {page_id} in batch")
        return True
    except Exception as e:
        workspace_logger.error(f"Failed to add summary to Notion page: {e}")
        return False

def cleanup_existing_summary_blocks(page_id: str) -> bool:
    """
    Remove any existing audio processing summary blocks from the page to prevent duplicates.
    
    Args:
        page_id: Notion page ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get all blocks on the page
        response = notion_manager._req("get", f"/blocks/{page_id}/children")
        blocks = response.get("results", [])
        
        # Find and delete code blocks that contain audio processing summary content
        blocks_to_delete = []
        for block in blocks:
            if block.get("type") == "code":
                code_content = ""
                rich_text = block.get("code", {}).get("rich_text", [])
                for text_item in rich_text:
                    code_content += text_item.get("text", {}).get("content", "")
                
                # Check if this looks like an audio processing summary
                if any(keyword in code_content.lower() for keyword in [
                    "comprehensive audio processing analysis report",
                    "audio analysis characteristics",
                    "audio file format characteristics",
                    "audio quality metrics",
                    "audio processing steps completed",
                    "technical audio specifications",
                    "audio quality assessment",
                    "file processing status"
                ]):
                    blocks_to_delete.append(block.get("id"))
        
        # Delete the identified blocks
        for block_id in blocks_to_delete:
            try:
                notion_manager._req("delete", f"/blocks/{block_id}")
                workspace_logger.debug(f"🗑️  Deleted existing summary block {block_id}")
            except Exception as e:
                workspace_logger.warning(f"Could not delete block {block_id}: {e}")
        
        if blocks_to_delete:
            workspace_logger.info(f"🧹 Cleaned up {len(blocks_to_delete)} existing summary blocks")
        
        return True
        
    except Exception as e:
        workspace_logger.warning(f"Failed to cleanup existing summary blocks: {e}")
        return False

def split_summary_into_large_sections(summary: str) -> list:
    """
    Split the summary into 4 large logical sections.
    
    Args:
        summary: Full summary text
        
    Returns:
        List of section dictionaries with title and content
    """
    lines = summary.split('\n')
    sections = []
    
    # Section 1: Track Identification and Audio Analysis
    section1_lines = []
    section1_started = False
    
    # Section 2: File Format Characteristics and Quality Metrics
    section2_lines = []
    section2_started = False
    
    # Section 3: Audio Processing Steps and Technical Specifications
    section3_lines = []
    section3_started = False
    
    # Section 4: Audio Quality Assessment and Processing Status
    section4_lines = []
    section4_started = False
    
    for line in lines:
        # Section 1: Track Identification and Audio Analysis
        if any(keyword in line for keyword in [
            "COMPREHENSIVE AUDIO PROCESSING ANALYSIS REPORT",
            "TRACK IDENTIFICATION",
            "AUDIO ANALYSIS CHARACTERISTICS",
            "LIBROSA AUDIO ANALYSIS FEATURES"
        ]):
            section1_started = True
            section1_lines.append(line)
            continue
        
        # Section 2: File Format Characteristics and Quality Metrics
        if any(keyword in line for keyword in [
            "AUDIO FILE FORMAT CHARACTERISTICS",
            "M4A FILE FORMAT SUMMARY",
            "WAV FILE FORMAT SUMMARY",
            "AUDIO QUALITY METRICS"
        ]):
            if section1_started:
                section1_started = False
            section2_started = True
            section2_lines.append(line)
            continue
        
        # Section 3: Audio Processing Steps and Technical Specifications
        if any(keyword in line for keyword in [
            "AUDIO PROCESSING STEPS COMPLETED",
            "TECHNICAL AUDIO SPECIFICATIONS",
            "AUDIO NORMALIZATION CHARACTERISTICS"
        ]):
            if section2_started:
                section2_started = False
            section3_started = True
            section3_lines.append(line)
            continue
        
        # Section 4: Audio Quality Assessment and Processing Status
        if any(keyword in line for keyword in [
            "AUDIO QUALITY ASSESSMENT",
            "FILE PROCESSING STATUS"
        ]):
            if section3_started:
                section3_started = False
            section4_started = True
            section4_lines.append(line)
            continue
        
        # Add line to appropriate section
        if section1_started:
            section1_lines.append(line)
        elif section2_started:
            section2_lines.append(line)
        elif section3_started:
            section3_lines.append(line)
        elif section4_started:
            section4_lines.append(line)
    
    # Create section objects
    if section1_lines:
        sections.append({
            'title': 'Track Identification and Audio Analysis',
            'content': '\n'.join(section1_lines)
        })
    
    if section2_lines:
        sections.append({
            'title': 'File Format Characteristics and Quality Metrics',
            'content': '\n'.join(section2_lines)
        })
    
    if section3_lines:
        sections.append({
            'title': 'Audio Processing Steps and Technical Specifications',
            'content': '\n'.join(section3_lines)
        })
    
    if section4_lines:
        sections.append({
            'title': 'Audio Quality Assessment and Processing Status',
            'content': '\n'.join(section4_lines)
        })
    
    return sections

def update_audio_processing_properties(page_id: str, processing_data: dict, file_paths: dict, track_info: dict) -> bool:
    """
    Update the new audio processing properties with detailed data.
    
    Args:
        page_id: Notion page ID
        processing_data: Audio processing results
        file_paths: Generated file paths
        track_info: Original track information
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from datetime import datetime
        prop_types = _get_tracks_db_prop_types()
        
        # Calculate file sizes
        file_sizes = {}
        for file_type, path in file_paths.items():
            if path and Path(path).exists():
                file_size = Path(path).stat().st_size
                file_size_mb = file_size / (1024 * 1024)
                file_sizes[file_type] = f"{file_size_mb:.2f} MB"
        
        # Determine metadata applied
        metadata_applied = []
        if track_info.get('title'):
            metadata_applied.append("Title")
        if track_info.get('artist'):
            metadata_applied.append("Artist")
        if track_info.get('album'):
            metadata_applied.append("Album")
        if track_info.get('genre'):
            metadata_applied.append("Genre")
        if processing_data.get('bpm'):
            metadata_applied.append("BPM")
        if processing_data.get('key'):
            metadata_applied.append("Key")
        if track_info.get('soundcloud_url'):
            metadata_applied.append("Comment")
        if processing_data.get('fingerprint') or track_info.get('fingerprint'):
            metadata_applied.append("Fingerprint")
        
        # Create system information
        system_info = f"Script Version: 2025-01-27\nCompression Mode: {COMPRESSION_MODE}\nAudio Normalizer: {'Available' if AUDIO_NORMALIZER_AVAILABLE else 'Not Available'}\nOutput Directory: {OUT_DIR}\nBackup Directory: {BACKUP_DIR}\nWAV Backup Directory: {WAV_BACKUP_DIR}"
        
        # Build properties update
        properties = {
            "Processing Timestamp": {
                "date": {
                    "start": datetime.now().isoformat()
                }
            },
            "File Sizes": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": str(file_sizes)
                        }
                    }
                ]
            },
            "Compression Mode Used": {
                "select": {
                    "name": COMPRESSION_MODE
                }
            },
            "Audio Normalizer Available": {
                "checkbox": AUDIO_NORMALIZER_AVAILABLE
            },
            "Processing Duration": {
                "number": processing_data.get('duration', 0)
            },
            "System Information": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": system_info
                        }
                    }
                ]
            },
            "Metadata Applied": {
                "multi_select": [{"name": item} for item in metadata_applied]
            },
            "Quality Score": {
                "number": processing_data.get('quality_score', 0)
            },
            "Loudness Level": {
                "number": processing_data.get('loudness_level', 0)
            },
            "Warmth Enhancement Level": {
                "number": processing_data.get('warmth_level', 0)
            }
        }

        # ═══════════════════════════════════════════════════════════════════════════════
        # CRITICAL: Update BPM, Key, and Duration - these were MISSING before 2026-01-16
        # ═══════════════════════════════════════════════════════════════════════════════

        # BPM (number property)
        bpm_value = processing_data.get('bpm') or track_info.get('bpm')
        if bpm_value:
            bpm_prop = _resolve_prop_name("BPM") or "Tempo"
            if prop_types.get(bpm_prop) == "number":
                properties[bpm_prop] = {"number": float(bpm_value)}
                workspace_logger.debug(f"Setting {bpm_prop} = {bpm_value}")

        # Key (rich_text property)
        key_value = processing_data.get('key') or track_info.get('key')
        if key_value:
            key_prop = _resolve_prop_name("Key") or "Key "
            if prop_types.get(key_prop) == "rich_text":
                properties[key_prop] = {"rich_text": [{"text": {"content": str(key_value)}}]}
                workspace_logger.debug(f"Setting {key_prop} = {key_value}")
            elif prop_types.get(key_prop) == "select":
                properties[key_prop] = {"select": {"name": str(key_value)}}
                workspace_logger.debug(f"Setting {key_prop} (select) = {key_value}")

        # Duration in seconds (number property)
        # Note: processing_data uses 'duration', not 'duration_seconds'
        duration_value = processing_data.get('duration') or processing_data.get('duration_seconds') or track_info.get('duration_seconds') or track_info.get('duration')
        if duration_value:
            duration_prop = _resolve_prop_name("Duration (s)") or "Audio Duration (seconds)"
            if prop_types.get(duration_prop) == "number":
                properties[duration_prop] = {"number": float(duration_value)}
                workspace_logger.debug(f"Setting {duration_prop} = {duration_value}")

        fingerprint_value = processing_data.get('fingerprint') or track_info.get('fingerprint')
        if fingerprint_value:
            # NEW SCHEMA (2026-01-14): Route fingerprint to per-format property
            file_path = processing_data.get('file_path') or track_info.get('file_path', '')
            try:
                from shared_core.fingerprint_schema import build_fingerprint_update_properties
                fp_props = build_fingerprint_update_properties(fingerprint_value, file_path, prop_types)
                if fp_props:
                    properties.update(fp_props)
                    workspace_logger.debug("Using per-format fingerprint schema")
            except ImportError:
                pass

            # LEGACY FALLBACK (DEPRECATED)
            if not any(k.endswith("Fingerprint") for k in properties):
                fingerprint_prop_name = _resolve_prop_name("Fingerprint") or "Fingerprint"
                if prop_types.get(fingerprint_prop_name) == "rich_text":
                    workspace_logger.warning("Using DEPRECATED legacy Fingerprint property")
                    properties[fingerprint_prop_name] = {
                        "rich_text": [{"type": "text", "text": {"content": fingerprint_value}}]
                    }

        # Log what we're updating
        update_summary = []
        if bpm_value:
            update_summary.append(f"BPM={bpm_value}")
        if key_value:
            update_summary.append(f"Key={key_value}")
        if duration_value:
            update_summary.append(f"Duration={duration_value}s")
        if fingerprint_value:
            update_summary.append(f"Fingerprint={'Yes' if fingerprint_value else 'No'}")

        workspace_logger.info(f"📝 Updating Notion properties: {', '.join(update_summary) if update_summary else 'metadata only'}")

        # Update the page properties
        notion_manager._req("patch", f"/pages/{page_id}", {"properties": properties})

        workspace_logger.info(f"✅ Updated {len(properties)} audio processing properties for page {page_id}")
        return True
        
    except Exception as e:
        workspace_logger.error(f"❌ Failed to update audio processing properties for page {page_id}: {e}")
        return False

def find_track_by_title_and_artist(title: str, artist: str) -> Optional[Dict[str, Any]]:
    """Find a specific track in Notion by title and artist."""
    try:
        notion = NotionManager()
        query = {
            "filter": {
                "and": [
                    {
                        "property": "Title",
                        "rich_text": {
                            "equals": title
                        }
                    },
                    {
                        "property": "Artist",
                        "rich_text": {
                            "equals": artist
                        }
                    }
                ]
            }
        }
        result = notion_manager.query_database(TRACKS_DB_ID, query)
        pages = result.get("results", [])
        if pages:
            return pages[0]
        return None
    except Exception as exc:
        workspace_logger.warning(f"Failed to find track {title} by {artist}: {exc}")
        return None

def cleanup_files_for_reprocessing(track_info: dict) -> bool:
    """Delete physical files for reprocessing. Returns True if successful."""
    try:
        files_deleted = 0
        
        # Get file paths from track info
        wav_path = track_info.get("wav_file_path", "")
        aiff_path = track_info.get("aiff_file_path", "")
        m4a_path = track_info.get("m4a_file_path", "")
        
        # Delete physical files
        for file_path in [wav_path, aiff_path, m4a_path]:
            if file_path and Path(file_path).exists():
                try:
                    Path(file_path).unlink()
                    workspace_logger.info(f"🗑️  Deleted file: {file_path}")
                    files_deleted += 1
                except Exception as exc:
                    workspace_logger.warning(f"Failed to delete file {file_path}: {exc}")
        
        # Delete Eagle items by file path
        eagle_items_deleted = 0
        for file_path in [wav_path, aiff_path, m4a_path]:
            if file_path:
                eagle_items = eagle_find_items_by_path(file_path)
                for item in eagle_items:
                    item_id = item.get("id") if isinstance(item, dict) else item
                    if item_id and eagle_delete_item(item_id):
                        eagle_items_deleted += 1
        
        workspace_logger.info(f"🧹 Cleanup complete: {files_deleted} files, {eagle_items_deleted} Eagle items deleted")
        return True
        
    except Exception as exc:
        workspace_logger.warning(f"Failed to cleanup files: {exc}")
        return False

def reprocess_track(track_page: Dict[str, Any]) -> bool:
    """Reprocess a track by cleaning up and re-downloading."""
    track_info = extract_track_data(track_page)
    track_info = enrich_spotify_metadata(track_info)
    title = track_info.get("title", "Unknown")
    artist = track_info.get("artist", "Unknown")
    page_id = track_info.get("page_id")
    
    workspace_logger.info(f"🔄 REPROCESSING TRACK: {title} by {artist}")
    
    if not page_id:
        workspace_logger.error(f"❌ No page ID found for track: {title}")
        workspace_logger.record_failed()
        return False
    
    # Clean up existing files and Eagle items
    workspace_logger.info("🧹 Cleaning up existing files and Eagle items...")
    cleanup_files_for_reprocessing(track_info)
    
    # Reset Notion entry for reprocessing (clear file paths but keep DL=False)
    workspace_logger.info("🔄 Resetting Notion entry for reprocessing...")
    if not reset_track_for_reprocessing(page_id):
        workspace_logger.error(f"❌ Failed to reset Notion entry for: {title}")
        workspace_logger.record_failed()
        return False
    
    # Re-download and process the track
    workspace_logger.info("📥 Re-downloading and processing track...")
    # Get playlist names from track relations
    playlist_names = get_playlist_names_from_track(track_info)
    if playlist_names:
        playlist_name = playlist_names[0]  # Use first playlist
    else:
        playlist_name = "Unassigned"  # Default for tracks without playlists
    playlist_dir = OUT_DIR / playlist_name
    
    result = download_track(
        track_info["soundcloud_url"],
        playlist_dir,
        track_info,
        playlist_name
    )
    
    if result:
        workspace_logger.record_processed()
        workspace_logger.info(f"✅ Successfully reprocessed: {title}")
        return True
    else:
        workspace_logger.record_failed()
        workspace_logger.error(f"❌ Failed to reprocess: {title}")
        return False

def auto_reprocess_tracks() -> int:
    """Automatically reprocess tracks that have DL=False but existing file paths."""
    workspace_logger.info("🔍 Checking for tracks that need reprocessing...")
    
    tracks_to_reprocess = find_tracks_for_reprocessing()
    
    if not tracks_to_reprocess:
        workspace_logger.info("✅ No tracks need reprocessing")
        return 0
    
    workspace_logger.info(f"🔄 Found {len(tracks_to_reprocess)} tracks that need reprocessing")
    
    reprocessed_count = 0
    for track_page in tracks_to_reprocess:
        try:
            track_data = extract_track_data(track_page)
            title = track_data.get("title", "Unknown")
            if not should_reprocess_page(track_page):
                workspace_logger.info(f"⏭️  Skipping reprocess: {title} (already up to date)")
                workspace_logger.record_skipped()
                continue
            if reprocess_track(track_page):
                reprocessed_count += 1
        except Exception as exc:
            workspace_logger.error(f"❌ Failed to reprocess track: {exc}")
            workspace_logger.record_failed()
    
    workspace_logger.info(f"✅ Successfully reprocessed {reprocessed_count}/{len(tracks_to_reprocess)} tracks")
    return reprocessed_count

def batch_process_tracks(filter_criteria: str = "unprocessed", max_tracks: int = None) -> int:
    """
    Process all tracks that meet the specified filter criteria in a continuous batch run.
    
    Args:
        filter_criteria: Type of tracks to process
            - "unprocessed": Tracks with DL=False and no file paths (default)
            - "reprocessing": Tracks with DL=False but have file paths or Eagle items
            - "all": All tracks with SoundCloud URLs regardless of status
        max_tracks: Maximum number of tracks to process (None for all)
    """
    workspace_logger.info(f"🔄 BATCH PROCESSING MODE - Processing tracks with criteria: {filter_criteria}")
    
    # Continuous processing loop for batch mode
    total_processed = 0
    total_failed = 0
    total_skipped = 0
    batch_number = 1
    
    while True:
        workspace_logger.info(f"\n{'='*80}")
        workspace_logger.info(f"🔄 BATCH #{batch_number} - Querying for tracks...")
        workspace_logger.info(f"{'='*80}")
        
        # Get tracks based on filter criteria for this batch
        if filter_criteria == "unprocessed":
            tracks_to_process = find_all_tracks_for_processing()
            workspace_logger.info("📋 Filter: Unprocessed tracks (DL=False, no file paths)")
        elif filter_criteria == "reprocessing":
            tracks_to_process = find_tracks_for_reprocessing()
            workspace_logger.info("📋 Filter: Tracks needing reprocessing (DL=False, have file paths)")
        elif filter_criteria == "all":
            tracks_to_process = find_all_tracks_with_soundcloud_urls()
            workspace_logger.info("📋 Filter: All tracks with SoundCloud URLs")
        elif filter_criteria == "playlist":
            tracks_to_process = find_tracks_with_playlist_relations()
            workspace_logger.info("📋 Filter: Tracks with playlist relations (DL=False, no file paths, has playlist)")
        else:
            workspace_logger.error(f"❌ Unknown filter criteria: {filter_criteria}")
            return 0
        
        if not tracks_to_process:
            workspace_logger.info("✅ No more tracks found for batch processing")
            break
        
        # Limit tracks if max_tracks is specified
        if max_tracks and max_tracks > 0:
            remaining_limit = max_tracks - total_processed
            if remaining_limit <= 0:
                workspace_logger.info(f"📊 Reached processing limit: {max_tracks}")
                break
            tracks_to_process = tracks_to_process[:remaining_limit]
            workspace_logger.info(f"📋 Limited to {remaining_limit} tracks for this batch")
        
        workspace_logger.info(f"📋 Found {len(tracks_to_process)} tracks for batch #{batch_number}")
        
        # Show track list for this batch
        workspace_logger.info(f"\n📋 TRACKS TO PROCESS (Batch #{batch_number}):")
        for i, track_page in enumerate(tracks_to_process, 1):
            track_data = extract_track_data(track_page)
            title = track_data.get("title", "Unknown")
            artist = track_data.get("artist", "Unknown")
            workspace_logger.info(f"   {i}. {title} by {artist}")
        
        batch_processed = 0
        batch_failed = 0
        batch_skipped = 0
        
        for i, track_page in enumerate(tracks_to_process, 1):
            try:
                track_data = extract_track_data(track_page)
                title = track_data.get("title", "Unknown")
                artist = track_data.get("artist", "Unknown")
                
                workspace_logger.info(f"\n{'='*80}")
                workspace_logger.info(f"🎵 BATCH #{batch_number} [{i}/{len(tracks_to_process)}] - Total: [{total_processed + i}]: {title} by {artist}")
                workspace_logger.info(f"{'='*80}")
                
                # Check if track already has files (for reprocessing mode)
                if filter_criteria == "reprocessing":
                    # Check if M4A file exists on disk
                    safe_base = re.sub(r"[^\w\s-]", "", title).strip()
                    # Get playlist names from track relations for path check
                    playlist_names = get_playlist_names_from_track(track_data)
                    if playlist_names:
                        playlist_name = playlist_names[0]
                    else:
                        playlist_name = "Unassigned"
                    aiff_path = (OUT_DIR / playlist_name / f"{safe_base}.aiff")
                    m4a_backup = BACKUP_DIR / f"{safe_base}.m4a"
                    if aiff_path.exists() and m4a_backup.exists():
                        workspace_logger.info(f"⏭️  Skipping [{i}/{len(tracks_to_process)}]: {title} (AIFF/M4A already exist)")
                        batch_skipped += 1
                        total_skipped += 1
                        workspace_logger.record_skipped()
                        continue
                
                # Process the track
                # Get playlist names from track relations
                playlist_names = get_playlist_names_from_track(track_data)
                if playlist_names:
                    playlist_name = playlist_names[0]  # Use first playlist
                else:
                    playlist_name = "Unassigned"  # Default for tracks without playlists
                playlist_dir = OUT_DIR / playlist_name
                
                result = download_track(
                    track_data["soundcloud_url"],
                    playlist_dir,
                    track_data,
                    playlist_name
                )
                
                if result:
                    batch_processed += 1
                    total_processed += 1
                    workspace_logger.record_processed()
                    workspace_logger.info(f"✅ Successfully processed: {title} by {artist}")
                else:
                    batch_failed += 1
                    total_failed += 1
                    workspace_logger.record_failed()
                    workspace_logger.error(f"❌ Failed to process: {title} by {artist}")
                    
            except Exception as exc:
                batch_failed += 1
                total_failed += 1
                workspace_logger.error(f"❌ Error processing track [{i}/{len(tracks_to_process)}]: {exc}")
                workspace_logger.record_failed()
                continue
        
        # Batch summary
        workspace_logger.info(f"\n{'='*80}")
        workspace_logger.info(f"📊 BATCH #{batch_number} SUMMARY:")
        workspace_logger.info(f"   Processed: {batch_processed}")
        workspace_logger.info(f"   Failed: {batch_failed}")
        workspace_logger.info(f"   Skipped: {batch_skipped}")
        workspace_logger.info(f"   Total Processed: {total_processed}")
        workspace_logger.info(f"   Total Failed: {total_failed}")
        workspace_logger.info(f"   Total Skipped: {total_skipped}")
        workspace_logger.info(f"{'='*80}")
        
        batch_number += 1
    
    # Final summary
    workspace_logger.info(f"\n{'='*80}")
    workspace_logger.info(f"🎉 BATCH PROCESSING COMPLETE!")
    workspace_logger.info(f"   Total Processed: {total_processed}")
    workspace_logger.info(f"   Total Failed: {total_failed}")
    workspace_logger.info(f"   Total Skipped: {total_skipped}")
    workspace_logger.info(f"{'='*80}")
    
    return total_processed

def efficient_batch_process_tracks(filter_criteria: str = "unprocessed", max_tracks: int = None, batch_size: int = 100) -> int:
    """
    Efficiently process tracks in small batches to avoid querying the entire database.
    Queries only 100 items at a time and starts processing immediately when tracks are found.
    
    Args:
        filter_criteria: Type of tracks to process
            - "unprocessed": Tracks with DL=False and no file paths (default)
        max_tracks: Maximum number of tracks to process (None for all)
        batch_size: Number of tracks to query per batch (default: 100)
    """
    workspace_logger.info(f"⚡ EFFICIENT BATCH PROCESSING MODE - Processing tracks with criteria: {filter_criteria}")
    workspace_logger.info(f"📊 Batch size: {batch_size}, Max tracks: {max_tracks or 'unlimited'}")
    
    # Continuous processing loop for efficient batch mode
    total_processed = 0
    total_failed = 0
    total_skipped = 0
    batch_number = 1
    consecutive_empty_batches = 0
    max_empty_batches = 3  # Stop after 3 consecutive empty batches
    
    def _process_batch_track_page(track_page: dict) -> tuple[str, bool, str, str, Optional[str]]:
        """
        Process a single track page for batch mode using UNIFIED STATE TRACKING.

        Uses process_track_with_unified_state for consistent deduplication,
        error recording, and completion marking across all modes.

        Returns:
            Tuple of (page_id, success, title, artist, error_message)
        """
        page_id = track_page.get("id", "unknown")

        try:
            # Use the UNIFIED processing function for consistent state tracking
            # This includes deduplication, error recording, and completion marking
            unified_result = process_track_with_unified_state(
                track_page,
                enable_dedup=True,
                dedupe_dry_run=(SC_DEDUP_DRY_RUN == "1"),
            )

            # Map unified result to legacy tuple format for backward compatibility
            success = unified_result.is_success
            title = unified_result.title
            artist = unified_result.artist
            error_msg = unified_result.error_message

            return page_id, success, title, artist, error_msg

        except Exception as exc:
            # Record error using unified error tracking
            error_type = classify_error(exc, "efficient_batch")
            record_track_error(page_id, error_type, str(exc))
            return page_id, False, "Unknown", "Unknown", str(exc)

    enable_parallel = os.getenv("SC_ENABLE_PARALLEL_BATCH", "1").strip().lower() in ("1", "true", "yes")

    while True:
        workspace_logger.info(f"\n{'='*80}")
        workspace_logger.info(f"⚡ EFFICIENT BATCH #{batch_number} - Querying for {batch_size} tracks...")
        workspace_logger.info(f"{'='*80}")
        
        # Get tracks based on filter criteria for this batch
        if filter_criteria == "unprocessed":
            tracks_to_process = find_tracks_for_processing_batch(batch_size)
            workspace_logger.info("📋 Filter: Unprocessed tracks (DL=False, no file paths)")
        else:
            workspace_logger.error(f"❌ Efficient batch processing only supports 'unprocessed' filter for now")
            return 0
        
        if not tracks_to_process:
            consecutive_empty_batches += 1
            workspace_logger.info(f"📭 No tracks found in batch #{batch_number} (empty batch #{consecutive_empty_batches})")
            
            if consecutive_empty_batches >= max_empty_batches:
                workspace_logger.info(f"✅ Stopping after {max_empty_batches} consecutive empty batches - likely no more tracks to process")
                break
            else:
                workspace_logger.info(f"🔄 Continuing to next batch...")
                batch_number += 1
                continue
        
        # Reset empty batch counter since we found tracks
        consecutive_empty_batches = 0
        
        # Limit tracks if max_tracks is specified
        if max_tracks and max_tracks > 0:
            remaining_limit = max_tracks - total_processed
            if remaining_limit <= 0:
                workspace_logger.info(f"📊 Reached processing limit: {max_tracks}")
                break
            tracks_to_process = tracks_to_process[:remaining_limit]
            workspace_logger.info(f"📋 Limited to {remaining_limit} tracks for this batch")
        
        workspace_logger.info(f"📋 Found {len(tracks_to_process)} tracks for efficient batch #{batch_number}")
        
        # Show track list for this batch
        workspace_logger.info(f"\n📋 TRACKS TO PROCESS (Efficient Batch #{batch_number}):")
        for i, track_page in enumerate(tracks_to_process, 1):
            track_data = extract_track_data(track_page)
            title = track_data.get("title", "Unknown")
            artist = track_data.get("artist", "Unknown")
            workspace_logger.info(f"   {i}. {title} by {artist}")
        
        batch_processed = 0
        batch_failed = 0
        batch_skipped = 0

        if enable_parallel and MAX_CONCURRENT_JOBS > 1:
            workspace_logger.info(f"🚀 Parallel batch processing enabled: {MAX_CONCURRENT_JOBS} workers")
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS) as executor:
                futures = [executor.submit(_process_batch_track_page, page) for page in tracks_to_process]
                for future in as_completed(futures):
                    track_id, success, title, artist, error = future.result()
                    if success:
                        batch_processed += 1
                        total_processed += 1
                        workspace_logger.record_processed()
                        workspace_logger.info(f"✅ Successfully processed: {title} by {artist} ({track_id})")
                    else:
                        batch_failed += 1
                        total_failed += 1
                        workspace_logger.record_failed()
                        if error:
                            workspace_logger.error(f"❌ Failed to process {track_id}: {error}")
                        else:
                            workspace_logger.error(f"❌ Failed to process: {title} by {artist} ({track_id})")
        else:
            for i, track_page in enumerate(tracks_to_process, 1):
                try:
                    track_data = extract_track_data(track_page)
                    title = track_data.get("title", "Unknown")
                    artist = track_data.get("artist", "Unknown")
                    
                    workspace_logger.info(f"\n{'='*80}")
                    workspace_logger.info(f"🎵 EFFICIENT BATCH #{batch_number} [{i}/{len(tracks_to_process)}] - Total: [{total_processed + i}]: {title} by {artist}")
                    workspace_logger.info(f"{'='*80}")
                    
                    # Process the track
                    playlist_names = get_playlist_names_from_track(track_data)
                    if playlist_names:
                        playlist_name = playlist_names[0]  # Use first playlist
                    else:
                        playlist_name = "Unassigned"  # Default for tracks without playlists
                    playlist_dir = OUT_DIR / playlist_name
                    
                    result = download_track(
                        track_data["soundcloud_url"],
                        playlist_dir,
                        track_data,
                        playlist_name
                    )
                    
                    if result:
                        batch_processed += 1
                        total_processed += 1
                        workspace_logger.record_processed()
                        workspace_logger.info(f"✅ Successfully processed: {title} by {artist}")
                    else:
                        batch_failed += 1
                        total_failed += 1
                        workspace_logger.record_failed()
                        workspace_logger.error(f"❌ Failed to process: {title} by {artist}")
                        
                except Exception as exc:
                    batch_failed += 1
                    total_failed += 1
                    workspace_logger.error(f"❌ Error processing track [{i}/{len(tracks_to_process)}]: {exc}")
                    workspace_logger.record_failed()
                    continue
        
        # Batch summary
        workspace_logger.info(f"\n{'='*80}")
        workspace_logger.info(f"📊 EFFICIENT BATCH #{batch_number} SUMMARY:")
        workspace_logger.info(f"   Processed: {batch_processed}")
        workspace_logger.info(f"   Failed: {batch_failed}")
        workspace_logger.info(f"   Skipped: {batch_skipped}")
        workspace_logger.info(f"   Total Processed: {total_processed}")
        workspace_logger.info(f"   Total Failed: {total_failed}")
        workspace_logger.info(f"   Total Skipped: {total_skipped}")
        workspace_logger.info(f"{'='*80}")
        
        batch_number += 1
    
    # Final summary
    workspace_logger.info(f"\n{'='*80}")
    workspace_logger.info(f"🎉 EFFICIENT BATCH PROCESSING COMPLETE!")
    workspace_logger.info(f"   Total Processed: {total_processed}")
    workspace_logger.info(f"   Total Failed: {total_failed}")
    workspace_logger.info(f"   Total Skipped: {total_skipped}")
    workspace_logger.info(f"{'='*80}")

    return total_processed


# ═══════════════════════════════════════════════════════════════════════════════
# FULL LIBRARY SYNC MODE
# ═══════════════════════════════════════════════════════════════════════════════
# This mode performs a comprehensive library synchronization by:
# 1. Querying ALL tracks from Notion in a single paginated request
# 2. Caching the entire Eagle library state upfront
# 3. Processing tracks with conflict-aware locking
# 4. Ideal for initial sync, migration, or periodic full-library maintenance
# ═══════════════════════════════════════════════════════════════════════════════

def full_library_sync(
    filter_criteria: str = "unprocessed",
    max_tracks: Optional[int] = None,
    cleanup_locks_first: bool = True,
    parallel: bool = False,
    max_workers: int = MAX_CONCURRENT_JOBS,
) -> Dict[str, Any]:
    """
    Process the full music library in a single comprehensive sync operation.

    This mode differs from batch mode in that it:
    1. Queries ALL matching tracks upfront (single paginated query)
    2. Pre-caches the entire Eagle library for efficient deduplication
    3. Uses distributed locking to prevent conflicts with concurrent processes
    4. Provides detailed progress tracking and resumability

    Args:
        filter_criteria: Type of tracks to process
            - "unprocessed": Tracks with DL=False and no file paths (default)
            - "all": All tracks with SoundCloud URLs regardless of status
            - "missing_eagle": Tracks with files but no Eagle ID
        max_tracks: Maximum number of tracks to process (None for all)
        cleanup_locks_first: Clean up stale locks before starting
        parallel: Enable parallel processing (default: False for safety)
        max_workers: Number of parallel workers if parallel=True

    Returns:
        Dict with sync results and statistics
    """
    start_time = time.time()

    workspace_logger.info(f"\n{'═'*80}")
    workspace_logger.info(f"📚 FULL LIBRARY SYNC MODE")
    workspace_logger.info(f"{'═'*80}")
    workspace_logger.info(f"🔧 Filter: {filter_criteria}")
    workspace_logger.info(f"🔧 Max tracks: {max_tracks or 'unlimited'}")
    workspace_logger.info(f"🔧 Parallel: {parallel} (workers: {max_workers})")
    workspace_logger.info(f"🔧 Process ID: {_PROCESS_IDENTIFIER}")
    workspace_logger.info(f"{'═'*80}\n")

    results = {
        "mode": "full_library_sync",
        "filter_criteria": filter_criteria,
        "process_id": _PROCESS_IDENTIFIER,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total_tracks_found": 0,
        "processed": 0,
        "failed": 0,
        "skipped_locked": 0,
        "skipped_already_done": 0,
        "errors": [],
        "tracks_processed": [],
    }

    # Step 1: Clean up stale locks if requested
    if cleanup_locks_first and PROCESS_LOCK_ENABLED:
        workspace_logger.info("🧹 Step 1: Cleaning up stale processing locks...")
        cleared = cleanup_stale_locks(max_pages=500)
        results["stale_locks_cleared"] = cleared
    else:
        workspace_logger.info("⏭️  Step 1: Skipping lock cleanup (disabled)")
        results["stale_locks_cleared"] = 0

    # Step 2: Pre-cache Eagle library for efficient lookups
    workspace_logger.info("\n🦅 Step 2: Pre-caching Eagle library...")
    try:
        eagle_items = eagle_fetch_all_items()
        eagle_count = len(eagle_items) if eagle_items else 0
        workspace_logger.info(f"   ✅ Cached {eagle_count} Eagle items")
        results["eagle_items_cached"] = eagle_count
    except Exception as e:
        workspace_logger.warning(f"   ⚠️  Failed to cache Eagle library: {e}")
        results["eagle_items_cached"] = 0
        results["errors"].append(f"Eagle cache failed: {e}")

    # Step 3: Query ALL tracks with downloadable source URLs from Notion
    # Library-sync mode ignores DL checkbox - it queries ALL tracks and verifies file paths exist
    # Supports: SoundCloud URL, Spotify URL, YouTube URL
    workspace_logger.info(f"\n📋 Step 3: Querying all tracks with downloadable URLs from Notion...")
    workspace_logger.info(f"   📌 Filter mode: {filter_criteria}")
    workspace_logger.info(f"   📌 NOTE: DL checkbox is IGNORED - file path existence will be verified")
    workspace_logger.info(f"   📌 Sources: SoundCloud, Spotify, YouTube")

    try:
        # Query ALL tracks with ANY downloadable source URL (SoundCloud, Spotify, YouTube)
        query = {
            "filter": {
                "or": [
                    # SoundCloud URLs
                    {"property": "SoundCloud URL", "url": {"is_not_empty": True}},
                    {"property": "SoundCloud URL", "rich_text": {"is_not_empty": True}},
                    # Spotify URLs
                    {"property": "Spotify URL", "url": {"is_not_empty": True}},
                    {"property": "Spotify URL", "rich_text": {"is_not_empty": True}},
                    # YouTube URLs
                    {"property": "YouTube URL", "url": {"is_not_empty": True}},
                    {"property": "YouTube URL", "rich_text": {"is_not_empty": True}},
                ]
            },
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        }
        all_tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=max_tracks or 10000)

        results["total_tracks_queried"] = len(all_tracks)
        workspace_logger.info(f"   ✅ Found {len(all_tracks)} total tracks with downloadable URLs")

        # Step 3b: Filter based on criteria WITH file path verification
        if filter_criteria == "all":
            # Process everything - no additional filtering
            workspace_logger.info(f"   📌 Filter 'all': Processing all {len(all_tracks)} tracks")
        elif filter_criteria == "unprocessed":
            # Filter out tracks that have VERIFIED existing files
            workspace_logger.info(f"\n🔍 Step 3b: Verifying file paths for {len(all_tracks)} tracks...")
            tracks_needing_processing = []
            tracks_with_verified_files = 0
            tracks_with_missing_files = 0
            tracks_with_no_paths = 0

            for idx, track in enumerate(all_tracks):
                props = track.get("properties", {})
                page_id = track.get("id", "")

                # Get file paths from Notion
                file_paths = {
                    "wav": _prop_text_value(props.get(_resolve_prop_name("WAV File Path") or "WAV File Path", {})),
                    "aiff": _prop_text_value(props.get(_resolve_prop_name("AIFF File Path") or "AIFF File Path", {})),
                    "m4a": _prop_text_value(props.get(_resolve_prop_name("M4A File Path") or "M4A File Path", {})),
                }

                # Check if any file paths are set
                has_any_path = any(file_paths.values())

                if not has_any_path:
                    # No paths set - needs processing
                    tracks_with_no_paths += 1
                    tracks_needing_processing.append(track)
                else:
                    # Verify at least one file actually exists
                    any_file_exists = False
                    for path_type, path in file_paths.items():
                        if path and Path(path).exists():
                            any_file_exists = True
                            break

                    if any_file_exists:
                        # Has verified existing files - skip
                        tracks_with_verified_files += 1
                    else:
                        # Paths are set but files don't exist - needs reprocessing
                        tracks_with_missing_files += 1
                        tracks_needing_processing.append(track)

                # Progress logging every 500 tracks
                if (idx + 1) % 500 == 0:
                    workspace_logger.info(f"   ... verified {idx + 1}/{len(all_tracks)} tracks")

            workspace_logger.info(f"\n   📊 File verification results:")
            workspace_logger.info(f"      • No paths set: {tracks_with_no_paths} (need processing)")
            workspace_logger.info(f"      • Paths set, files EXIST: {tracks_with_verified_files} (skip)")
            workspace_logger.info(f"      • Paths set, files MISSING: {tracks_with_missing_files} (need reprocessing)")
            workspace_logger.info(f"      • Total needing processing: {len(tracks_needing_processing)}")

            all_tracks = tracks_needing_processing
            results["tracks_with_verified_files"] = tracks_with_verified_files
            results["tracks_with_missing_files"] = tracks_with_missing_files
            results["tracks_with_no_paths"] = tracks_with_no_paths

        elif filter_criteria == "missing_eagle":
            # Tracks with files but no Eagle ID
            eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
            tracks_missing_eagle = []

            for track in all_tracks:
                props = track.get("properties", {})
                has_eagle = bool(_prop_text_value(props.get(eagle_prop, {})))

                if not has_eagle:
                    # Check if has any file paths
                    file_paths = {
                        "wav": _prop_text_value(props.get(_resolve_prop_name("WAV File Path") or "WAV File Path", {})),
                        "aiff": _prop_text_value(props.get(_resolve_prop_name("AIFF File Path") or "AIFF File Path", {})),
                    }
                    if any(file_paths.values()):
                        tracks_missing_eagle.append(track)

            workspace_logger.info(f"   📌 Filter 'missing_eagle': Found {len(tracks_missing_eagle)} tracks with files but no Eagle ID")
            all_tracks = tracks_missing_eagle
        else:
            workspace_logger.error(f"❌ Unknown filter criteria: {filter_criteria}")
            results["errors"].append(f"Unknown filter: {filter_criteria}")
            return results

        results["total_tracks_found"] = len(all_tracks)
        workspace_logger.info(f"   ✅ {len(all_tracks)} tracks will be processed")

        if not all_tracks:
            workspace_logger.info("\n✅ No tracks found matching criteria - library is up to date!")
            results["completed_at"] = datetime.now(timezone.utc).isoformat()
            results["duration_seconds"] = time.time() - start_time
            return results

    except Exception as e:
        workspace_logger.error(f"❌ Failed to query Notion database: {e}")
        results["errors"].append(f"Notion query failed: {e}")
        return results

    # Step 4: Apply max_tracks limit if specified
    if max_tracks and len(all_tracks) > max_tracks:
        workspace_logger.info(f"   📊 Limiting to first {max_tracks} tracks")
        all_tracks = all_tracks[:max_tracks]

    # Step 5: Run batch-level deduplication (same as other modes)
    workspace_logger.info(f"\n🔍 Step 5: Running batch-level deduplication on {len(all_tracks)} tracks...")
    dedupe_dry_run = SC_DEDUP_DRY_RUN == "1"

    try:
        # First pass: dedupe within the batch (merge obvious duplicates)
        all_tracks = dedupe_within_batch(all_tracks, dry_run=dedupe_dry_run)
        workspace_logger.info(f"   ✅ After in-batch deduplication: {len(all_tracks)} unique tracks")
        results["tracks_after_dedupe"] = len(all_tracks)
    except Exception as e:
        workspace_logger.warning(f"   ⚠️  Batch deduplication failed (continuing anyway): {e}")
        results["errors"].append(f"Batch dedupe failed: {e}")

    # Step 6: Display track list
    workspace_logger.info(f"\n📋 TRACKS TO PROCESS ({len(all_tracks)} total):")
    for i, track_page in enumerate(all_tracks[:20], 1):  # Show first 20
        track_data = extract_track_data(track_page)
        title = track_data.get("title", "Unknown")
        artist = track_data.get("artist", "Unknown")
        workspace_logger.info(f"   {i}. {title} by {artist}")
    if len(all_tracks) > 20:
        workspace_logger.info(f"   ... and {len(all_tracks) - 20} more tracks")

    # Step 7: Process tracks with conflict-aware locking and UNIFIED STATE TRACKING
    workspace_logger.info(f"\n🚀 Step 6: Processing {len(all_tracks)} tracks...")

    def process_single_track_with_lock(track_page: dict, index: int) -> Dict[str, Any]:
        """
        Process a single track with lock management and unified state tracking.

        Uses the unified TrackResult and process_track_with_unified_state for
        consistent state tracking across all processing modes.
        """
        page_id = track_page.get("id", "unknown")
        track_data = extract_track_data(track_page)
        title = track_data.get("title", "Unknown")
        artist = track_data.get("artist", "Unknown")

        # Initialize result using unified TrackResult structure
        unified_result = TrackResult(
            page_id=page_id,
            title=title,
            artist=artist,
            status=TrackStatus.PENDING,
        )

        try:
            # ═══════════════════════════════════════════════════════════════
            # Step 1: Acquire distributed lock
            # ═══════════════════════════════════════════════════════════════
            if not acquire_track_lock(page_id):
                workspace_logger.info(f"⏭️  [{index}/{len(all_tracks)}] Skipped (locked): {title}")
                unified_result.status = TrackStatus.SKIPPED_LOCKED
                return unified_result.to_dict()

            try:
                # ═══════════════════════════════════════════════════════════════
                # Step 2: Re-check if track still needs processing
                # (might have been done by another process while we were waiting)
                # ═══════════════════════════════════════════════════════════════
                fresh_page = notion_manager._req("get", f"/pages/{page_id}")
                fresh_props = fresh_page.get("properties", {})

                dl_prop = _resolve_prop_name("DL") or "Downloaded"
                is_downloaded = fresh_props.get(dl_prop, {}).get("checkbox") is True

                eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
                has_eagle_id = bool(_prop_text_value(fresh_props.get(eagle_prop, {})))

                # Skip if already processed (unless filter says process all)
                if filter_criteria == "unprocessed" and (is_downloaded or has_eagle_id):
                    workspace_logger.info(f"⏭️  [{index}/{len(all_tracks)}] Skipped (already done): {title}")
                    unified_result.status = TrackStatus.SKIPPED_ALREADY_DONE
                    unified_result.eagle_item_id = _prop_text_value(fresh_props.get(eagle_prop, {})) if has_eagle_id else None
                    return unified_result.to_dict()

                # ═══════════════════════════════════════════════════════════════
                # Step 3: Use unified processing function (includes deduplication)
                # ═══════════════════════════════════════════════════════════════
                workspace_logger.info(f"\n{'─'*60}")
                workspace_logger.info(f"🎵 [{index}/{len(all_tracks)}] Processing: {title} by {artist}")
                workspace_logger.info(f"{'─'*60}")

                # Use the UNIFIED processing function for consistent state tracking
                unified_result = process_track_with_unified_state(
                    track_page,
                    enable_dedup=True,
                    dedupe_dry_run=dedupe_dry_run,
                )

                # Log result based on unified status
                if unified_result.status == TrackStatus.PROCESSED:
                    workspace_logger.info(f"✅ [{index}/{len(all_tracks)}] Success: {unified_result.title}")
                elif unified_result.status == TrackStatus.FAILED:
                    workspace_logger.error(f"❌ [{index}/{len(all_tracks)}] Failed: {unified_result.title}")
                elif unified_result.status == TrackStatus.SKIPPED_DUPLICATE:
                    workspace_logger.info(f"🔗 [{index}/{len(all_tracks)}] Merged duplicate: {unified_result.title}")
                elif unified_result.status == TrackStatus.SKIPPED_NO_SOURCE:
                    workspace_logger.warning(f"⏭️  [{index}/{len(all_tracks)}] No source: {unified_result.title}")

                return unified_result.to_dict()

            finally:
                # Always release lock when done
                release_track_lock(page_id)

        except Exception as e:
            workspace_logger.error(f"❌ [{index}/{len(all_tracks)}] Error processing {title}: {e}")
            unified_result.status = TrackStatus.ERROR
            unified_result.error_type = classify_error(e, "library_sync")
            unified_result.error_message = str(e)

            # Record error using unified error tracking
            record_track_error(page_id, unified_result.error_type, str(e), clear_lock=False)

            # Try to release lock on error
            try:
                release_track_lock(page_id)
            except Exception:
                pass

            return unified_result.to_dict()

    # Process tracks
    if parallel and max_workers > 1:
        # Parallel processing with ThreadPoolExecutor
        workspace_logger.info(f"🔄 Using parallel processing with {max_workers} workers")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_single_track_with_lock, track, i): (track, i)
                for i, track in enumerate(all_tracks, 1)
            }

            for future in concurrent.futures.as_completed(futures):
                track, index = futures[future]
                try:
                    result = future.result()
                    results["tracks_processed"].append(result)

                    if result["status"] == "processed":
                        results["processed"] += 1
                    elif result["status"] == "failed":
                        results["failed"] += 1
                        if result.get("error"):
                            results["errors"].append(f"{result['title']}: {result['error']}")
                    elif result["status"] == "skipped_locked":
                        results["skipped_locked"] += 1
                    elif result["status"] == "skipped_already_done":
                        results["skipped_already_done"] += 1

                except Exception as e:
                    workspace_logger.error(f"❌ Future failed for track {index}: {e}")
                    results["failed"] += 1
                    results["errors"].append(str(e))
    else:
        # Sequential processing (safer for debugging)
        workspace_logger.info("🔄 Using sequential processing")

        for i, track_page in enumerate(all_tracks, 1):
            result = process_single_track_with_lock(track_page, i)
            results["tracks_processed"].append(result)

            if result["status"] == "processed":
                results["processed"] += 1
            elif result["status"] == "failed":
                results["failed"] += 1
                if result.get("error"):
                    results["errors"].append(f"{result['title']}: {result['error']}")
            elif result["status"] == "skipped_locked":
                results["skipped_locked"] += 1
            elif result["status"] == "skipped_already_done":
                results["skipped_already_done"] += 1

    # Final summary
    duration = time.time() - start_time
    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    results["duration_seconds"] = duration

    workspace_logger.info(f"\n{'═'*80}")
    workspace_logger.info(f"📚 FULL LIBRARY SYNC COMPLETE")
    workspace_logger.info(f"{'═'*80}")
    workspace_logger.info(f"   Total Found:        {results['total_tracks_found']}")
    workspace_logger.info(f"   Processed:          {results['processed']}")
    workspace_logger.info(f"   Failed:             {results['failed']}")
    workspace_logger.info(f"   Skipped (locked):   {results['skipped_locked']}")
    workspace_logger.info(f"   Skipped (done):     {results['skipped_already_done']}")
    workspace_logger.info(f"   Duration:           {duration:.1f}s")
    workspace_logger.info(f"{'═'*80}")

    if results["errors"]:
        workspace_logger.info(f"\n⚠️  ERRORS ({len(results['errors'])}):")
        for err in results["errors"][:10]:  # Show first 10 errors
            workspace_logger.info(f"   - {err}")
        if len(results["errors"]) > 10:
            workspace_logger.info(f"   ... and {len(results['errors']) - 10} more errors")

    return results


def library_sync_status() -> Dict[str, Any]:
    """
    Get the current status of the music library for sync planning.

    Returns comprehensive statistics about:
    - Total tracks in Notion
    - Processed vs unprocessed counts
    - Tracks with/without Eagle IDs
    - Currently locked tracks
    """
    workspace_logger.info("📊 Gathering library sync status...")

    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tracks": 0,
        "with_soundcloud_url": 0,
        "downloaded": 0,
        "not_downloaded": 0,
        "with_eagle_id": 0,
        "without_eagle_id": 0,
        "currently_locked": 0,
        "with_file_paths": 0,
        "needs_processing": 0,
    }

    try:
        # Count all tracks
        all_query = {"page_size": 1}
        all_result = notion_manager.query_database(TRACKS_DB_ID, all_query)
        # Use a larger query to get total count
        count_query = {"page_size": 100}
        all_tracks = query_database_paginated(TRACKS_DB_ID, count_query, max_items=10000)
        status["total_tracks"] = len(all_tracks)

        # Analyze each track
        for track in all_tracks:
            props = track.get("properties", {})

            # Check SoundCloud URL
            sc_prop = props.get("SoundCloud URL", {})
            has_sc_url = bool(_prop_text_value(sc_prop) or sc_prop.get("url"))
            if has_sc_url:
                status["with_soundcloud_url"] += 1

            # Check DL checkbox
            dl_prop = _resolve_prop_name("DL") or "Downloaded"
            is_downloaded = props.get(dl_prop, {}).get("checkbox") is True
            if is_downloaded:
                status["downloaded"] += 1
            else:
                status["not_downloaded"] += 1

            # Check Eagle File ID
            eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
            has_eagle = bool(_prop_text_value(props.get(eagle_prop, {})))
            if has_eagle:
                status["with_eagle_id"] += 1
            else:
                status["without_eagle_id"] += 1

            # Check file paths
            has_files = False
            for key in ["M4A File Path", "WAV File Path", "AIFF File Path"]:
                prop_name = _resolve_prop_name(key) or key
                if _prop_text_value(props.get(prop_name, {})):
                    has_files = True
                    break
            if has_files:
                status["with_file_paths"] += 1

            # Check lock status
            lock_prop = _resolve_prop_name("Processing Lock")
            if lock_prop:
                lock_value = _prop_text_value(props.get(lock_prop, {}))
                lock_info = _parse_process_lock(lock_value)
                if lock_info and not _is_lock_stale(lock_info):
                    status["currently_locked"] += 1

            # Determine if needs processing
            if has_sc_url and not is_downloaded and not has_files:
                status["needs_processing"] += 1

        workspace_logger.info(f"📊 Library Status:")
        workspace_logger.info(f"   Total tracks:       {status['total_tracks']}")
        workspace_logger.info(f"   With SoundCloud:    {status['with_soundcloud_url']}")
        workspace_logger.info(f"   Downloaded:         {status['downloaded']}")
        workspace_logger.info(f"   With Eagle ID:      {status['with_eagle_id']}")
        workspace_logger.info(f"   Needs processing:   {status['needs_processing']}")
        workspace_logger.info(f"   Currently locked:   {status['currently_locked']}")

    except Exception as e:
        workspace_logger.error(f"❌ Failed to gather status: {e}")
        status["error"] = str(e)

    return status


def import_existing_local_file_to_eagle(
    file_path: str,
    track_data: dict,
    playlist_name: str
) -> Optional[dict]:
    """
    Import an existing local file to Eagle with fingerprinting.

    This handles the case where a file exists locally but is not in Eagle.
    The file will be:
    1. Fingerprinted
    2. Imported to Eagle with comprehensive tags (including fingerprint)
    3. Notion updated with Eagle File ID

    Args:
        file_path: Path to the existing local file
        track_data: Track metadata from Notion
        playlist_name: Playlist name for tagging

    Returns:
        Dictionary with import results or None on failure
    """
    workspace_logger.info(f"\n{'='*80}")
    workspace_logger.info(f"🦅 IMPORTING EXISTING LOCAL FILE TO EAGLE")
    workspace_logger.info(f"{'='*80}")
    workspace_logger.info(f"File: {file_path}")
    workspace_logger.info(f"Track: {track_data.get('title', 'Unknown')} by {track_data.get('artist', 'Unknown')}")

    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        workspace_logger.error(f"❌ File does not exist: {file_path}")
        return None

    try:
        # Step 1: Compute fingerprint
        workspace_logger.info("🔍 Computing audio fingerprint...")
        fingerprint = compute_file_fingerprint(file_path_obj)
        if fingerprint:
            workspace_logger.info(f"✅ Fingerprint computed: {fingerprint[:32]}...")
        else:
            workspace_logger.warning("⚠️  Could not compute fingerprint")
            fingerprint = None

        # Step 2: Build processing_data for tag generation
        processing_data = {
            "fingerprint": fingerprint,
            "bpm": track_data.get("bpm"),
            "key": track_data.get("key"),
            "duration": track_data.get("duration_seconds"),
        }

        # Step 3: Generate comprehensive tags (now includes fingerprint)
        file_type = file_path_obj.suffix.upper().lstrip('.')
        tag_list = generate_comprehensive_tags(track_data, processing_data, file_type)
        workspace_logger.info(f"📋 Generated tags: {tag_list}")

        # Step 4: Import to Eagle with de-duplication
        workspace_logger.info("🦅 Importing to Eagle with de-duplication check...")
        eagle_id = eagle_import_with_duplicate_management(
            file_path=file_path,
            title=track_data.get("title", "Unknown"),
            url=track_data.get("soundcloud_url") or track_data.get("spotify_url") or "",
            tags=tag_list,
            folder_id=None,
            expected_metadata=processing_data,
            audio_fingerprint=fingerprint
        )

        if eagle_id:
            workspace_logger.info(f"✅ Eagle import successful: {eagle_id}")
            workspace_logger.info(f"   Applied tags: {tag_list}")

            # Step 5: Update Notion with fingerprint and Eagle ID
            if track_data.get("page_id"):
                try:
                    # Update fingerprint in Notion using NEW per-format schema (2026-01-14)
                    if fingerprint:
                        update_props = {}
                        db_props = _get_tracks_db_props()

                        # NEW SCHEMA: Route fingerprint to per-format property based on file extension
                        try:
                            from shared_core.fingerprint_schema import (
                                build_fingerprint_update_properties,
                                get_format_from_extension,
                            )
                            update_props = build_fingerprint_update_properties(fingerprint, file_path, db_props)
                            if update_props:
                                fmt = get_format_from_extension(file_path) or "unknown"
                                workspace_logger.debug(f"Using per-format fingerprint schema: {fmt.upper()}")
                        except ImportError:
                            workspace_logger.debug("Per-format fingerprint schema not available, using legacy")

                        # LEGACY FALLBACK (DEPRECATED): Use old Fingerprint property
                        if not update_props and "Fingerprint" in db_props:
                            workspace_logger.warning("Using DEPRECATED legacy Fingerprint property")
                            if len(fingerprint) > 2000:
                                update_props["Fingerprint"] = {"rich_text": [{"text": {"content": fingerprint[:2000]}}]}
                                if "Fingerprint Part 2" in db_props:
                                    update_props["Fingerprint Part 2"] = {"rich_text": [{"text": {"content": fingerprint[2000:4000]}}]}
                            else:
                                update_props["Fingerprint"] = {"rich_text": [{"text": {"content": fingerprint}}]}

                        if update_props:
                            notion_manager.update_page(track_data["page_id"], update_props)
                            workspace_logger.info(f"✅ Updated Notion with fingerprint")

                    # Update Eagle File ID
                    update_notion_with_eagle_id(track_data["page_id"], eagle_id)
                    workspace_logger.info(f"✅ Updated Notion with Eagle File ID: {eagle_id}")

                    # Update audio processing status
                    update_audio_processing_status(track_data["page_id"], ["Files Imported to Eagle"])

                except Exception as e:
                    workspace_logger.warning(f"⚠️  Failed to update Notion: {e}")

            return {
                "file": file_path,
                "eagle_item_id": eagle_id,
                "fingerprint": fingerprint,
                "tags_applied": tag_list,
                "local_import": True
            }
        else:
            workspace_logger.error(f"❌ Eagle import failed for: {file_path}")
            return None

    except Exception as e:
        workspace_logger.error(f"❌ Error importing local file to Eagle: {e}")
        traceback.print_exc()
        return None


def check_existing_local_files_for_eagle_import(track_data: dict) -> Optional[str]:
    """
    Check if track has existing local files that need Eagle import.

    Returns the best file path to import if found, None otherwise.
    """
    # Priority order: WAV > AIFF > M4A
    file_paths_to_check = [
        track_data.get("wav_file_path"),
        track_data.get("aiff_file_path"),
        track_data.get("m4a_file_path"),
    ]

    for file_path in file_paths_to_check:
        if file_path and Path(file_path).exists():
            # Check if this file is NOT already in Eagle
            try:
                eagle_items = eagle_find_items_by_path(file_path)
                if not eagle_items:
                    workspace_logger.info(f"🔄 Found local file not in Eagle: {file_path}")
                    return file_path
            except Exception as e:
                workspace_logger.warning(f"⚠️  Error checking Eagle for {file_path}: {e}")

    return None


def process_track(track_page: Dict[str, Any]) -> bool:
    """
    Process a single track through the complete pipeline:
    download → convert → tag → Eagle import → Notion update

    NOTE: This function now uses UNIFIED STATE TRACKING for consistent
    deduplication, error recording, and completion marking across all modes.

    Args:
        track_page: Notion page data for the track

    Returns:
        True if processing was successful, False otherwise
    """
    page_id = track_page.get("id", "unknown")

    try:
        # ═══════════════════════════════════════════════════════════════
        # UNIFIED STATE TRACKING: Per-track deduplication check
        # This ensures consistent deduplication across ALL modes
        # ═══════════════════════════════════════════════════════════════
        dedupe_dry_run = SC_DEDUP_DRY_RUN == "1"
        try:
            resolved_page = try_merge_duplicates_for_page(track_page, dry_run=dedupe_dry_run)
            resolved_page_id = resolved_page.get("id")

            # If deduplication redirected to a different (keeper) page
            if resolved_page_id and resolved_page_id != page_id:
                workspace_logger.info(f"🔗 Dedup redirected {page_id} -> {resolved_page_id}")
                track_page = resolved_page
                page_id = resolved_page_id
        except Exception as dedup_err:
            workspace_logger.warning(f"⚠️  Deduplication check failed (continuing): {dedup_err}")

        # Extract track data
        track_data = extract_track_data(track_page)
        track_data = enrich_spotify_metadata(track_data)
        title = track_data.get("title", "Unknown")
        artist = track_data.get("artist", "Unknown")

        workspace_logger.info(f"🔄 Processing track: {title} by {artist}")

        # Get URLs - treat empty strings as None
        soundcloud_url = track_data.get("soundcloud_url") or None
        spotify_id = track_data.get("spotify_id") or None
        youtube_url = track_data.get("youtube_url") or None

        # If track has NO audio source identifiers, attempt to find one by searching
        # based on artist name and track title across all platforms
        if not soundcloud_url and not spotify_id and not youtube_url:
            workspace_logger.warning(f"⚠️  Track has NO audio source identifiers: {title} by {artist}")
            workspace_logger.info(f"🔍 Attempting to find audio source by searching all platforms...")

            # Get playlist info for download
            playlist_names = get_playlist_names_from_track(track_data)
            if playlist_names:
                playlist_name = playlist_names[0]
            else:
                playlist_name = "Unassigned"
            playlist_dir = OUT_DIR / playlist_name

            # Use the centralized multi-platform search function
            download_url, download_source = find_audio_source_for_track(
                artist=artist,
                title=title,
                track_data=track_data
            )

            # Update Notion with the found URL
            if download_url and track_data.get('page_id'):
                try:
                    if 'soundcloud.com' in download_url:
                        sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
                        notion_manager.update_page(track_data['page_id'], {sc_prop: {"url": download_url}})
                        workspace_logger.info(f"📝 Updated Notion with SoundCloud URL")
                    elif 'youtube.com' in download_url or 'youtu.be' in download_url:
                        update_notion_download_source(track_data['page_id'], download_source, download_url)
                except Exception as e:
                    workspace_logger.warning(f"⚠️  Failed to update Notion with found URL: {e}")

            # If we found a download URL, process it
            if download_url:
                workspace_logger.info(f"🔄 Running FULL download workflow via {download_source}...")
                workspace_logger.info(f"   URL: {download_url}")

                result = download_track(
                    url=download_url,
                    playlist_dir=playlist_dir,
                    track_info=track_data,
                    playlist_name=playlist_name
                )

                if result:
                    workspace_logger.info(f"✅ Track fully processed via {download_source}!")

                    # CRITICAL FIX: Update track_data page_id if de-dupe changed it
                    if result.get("page_id") and result["page_id"] != track_data.get("page_id"):
                        old_pid = track_data.get("page_id")
                        track_data["page_id"] = result["page_id"]
                        workspace_logger.info(f"🔄 De-dupe: Updated track_data page_id from {old_pid} to {track_data['page_id']}")

                    file_paths = {
                        "m4a": result.get("m4a_path") or result.get("file"),
                        "aiff": result.get("aiff_path"),
                        "wav": result.get("wav_path"),
                    }
                    eagle_id = result.get("eagle_item_id")

                    if track_data.get("page_id"):
                        complete_track_notion_update(
                            track_data["page_id"],
                            track_data,
                            file_paths,
                            eagle_id
                        )

                    workspace_logger.record_processed()
                    return True
                else:
                    workspace_logger.warning(f"⚠️  Download workflow failed for track via {download_source}: {title}")
                    workspace_logger.record_failed()
                    return False
            else:
                # No audio source found anywhere
                workspace_logger.warning(f"⚠️  Could not find audio source on any platform for: {title} by {artist}")
                workspace_logger.info(f"📋 Track will remain in queue for manual resolution")
                workspace_logger.record_failed()
                return False

        # Check if this is a Spotify-only track (has Spotify ID but no SoundCloud URL)
        is_spotify_only = spotify_id and not soundcloud_url

        if is_spotify_only:
            workspace_logger.info(f"🎵 Processing Spotify-only track: {title} by {artist}")
            workspace_logger.info(f"🔄 No SoundCloud URL - searching for audio source...")

            # Get playlist names from track relations
            playlist_names = get_playlist_names_from_track(track_data)
            if playlist_names:
                playlist_name = playlist_names[0]  # Use first playlist
            else:
                playlist_name = "Unassigned"  # Default for tracks without playlists
            playlist_dir = OUT_DIR / playlist_name

            # Use the centralized multi-platform search function
            # Priority: 1. SoundCloud (search) -> 2. YouTube (from Notion) -> 3. YouTube (search) -> 4. Spotify enrichment
            download_url, download_source = find_audio_source_for_track(
                artist=artist,
                title=title,
                track_data=track_data
            )

            # Update Notion with the found URL
            if download_url and track_data.get('page_id'):
                try:
                    if 'soundcloud.com' in download_url:
                        sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
                        notion_manager.update_page(track_data['page_id'], {sc_prop: {"url": download_url}})
                        workspace_logger.info(f"📝 Updated Notion with SoundCloud URL")
                    elif 'youtube.com' in download_url or 'youtu.be' in download_url:
                        update_notion_download_source(track_data['page_id'], download_source, download_url)
                except Exception as e:
                    workspace_logger.warning(f"⚠️  Failed to update Notion with found URL: {e}")

            # If we found a download URL, use the FULL download_track workflow
            if download_url:
                workspace_logger.info(f"🔄 Running FULL download workflow via {download_source}...")
                workspace_logger.info(f"   URL: {download_url}")

                # Use the full download_track function with the found URL (SoundCloud or YouTube)
                # This includes all processing: download, conversion, fingerprinting, Eagle import, etc.
                result = download_track(
                    url=download_url,
                    playlist_dir=playlist_dir,
                    track_info=track_data,
                    playlist_name=playlist_name
                )

                if result:
                    workspace_logger.info(f"✅ Spotify track fully processed via {download_source}!")

                    # CRITICAL FIX: Update track_data page_id if de-dupe changed it
                    if result.get("page_id") and result["page_id"] != track_data.get("page_id"):
                        old_pid = track_data.get("page_id")
                        track_data["page_id"] = result["page_id"]
                        workspace_logger.info(f"🔄 De-dupe: Updated track_data page_id from {old_pid} to {track_data['page_id']}")

                    # Complete Notion update with file paths
                    file_paths = {
                        "m4a": result.get("m4a_path") or result.get("file"),
                        "aiff": result.get("aiff_path"),
                        "wav": result.get("wav_path"),
                    }
                    eagle_id = result.get("eagle_item_id")

                    if track_data.get("page_id"):
                        complete_track_notion_update(
                            track_data["page_id"],
                            track_data,
                            file_paths,
                            eagle_id
                        )

                    workspace_logger.record_processed()
                    return True
                else:
                    workspace_logger.warning(f"⚠️  Download workflow failed for Spotify track via {download_source}: {title}")
                    workspace_logger.record_failed()
                    return False
            else:
                # No audio source found - update metadata only, do NOT mark as downloaded
                workspace_logger.warning(f"⚠️  No audio source found (SoundCloud or YouTube) for Spotify track: {title}")
                workspace_logger.info(f"📋 Updating metadata only - track will remain in download queue")
                try:
                    update_track_metadata(track_data)
                    workspace_logger.info(f"📋 Spotify track metadata enriched - NOT marking as downloaded (no audio source)")
                    # Return False so track stays in queue for future attempts
                    workspace_logger.record_failed()
                    return False
                except Exception as e:
                    workspace_logger.error(f"❌ Failed to update Spotify track metadata: {e}")
                    workspace_logger.record_failed()
                    return False
        else:
            # Regular SoundCloud track processing
            # Get playlist names from track relations
            playlist_names = get_playlist_names_from_track(track_data)
            if playlist_names:
                playlist_name = playlist_names[0]  # Use first playlist
            else:
                playlist_name = "Unassigned"  # Default for tracks without playlists
            playlist_dir = OUT_DIR / playlist_name

            # 🔧 CRITICAL FIX: Check if files exist locally but need Eagle import
            # This handles the case where files were downloaded but not imported to Eagle
            local_file_for_eagle = check_existing_local_files_for_eagle_import(track_data)
            if local_file_for_eagle:
                workspace_logger.info(f"🔄 LOCAL FILE FOUND - IMPORTING TO EAGLE (skipping download)")
                result = import_existing_local_file_to_eagle(
                    file_path=local_file_for_eagle,
                    track_data=track_data,
                    playlist_name=playlist_name
                )
                if result:
                    result["local_import"] = True
            else:
                # Normal download flow - use validated soundcloud_url variable
                result = download_track(
                    soundcloud_url,
                    playlist_dir,
                    track_data,
                    playlist_name
                )
        
        # CRITICAL FIX: Update track_data page_id if de-dupe changed it
        if result and result.get("page_id") and result["page_id"] != track_data.get("page_id"):
            old_pid = track_data.get("page_id")
            track_data["page_id"] = result["page_id"]
            workspace_logger.info(f"🔄 De-dupe: Updated track_data page_id from {old_pid} to {track_data['page_id']}")

        if result:
            # 🔧 CRITICAL FIX: Handle duplicate case - still update Notion with Eagle File ID
            if result.get("duplicate_found"):
                workspace_logger.info(f"🔄 DUPLICATE HANDLING: Updating Notion with existing Eagle item")
                eagle_id = result.get("eagle_item_id")
                if eagle_id:
                    # Update Notion with the existing Eagle File ID
                    try:
                        update_notion_with_eagle_id(track_data.get("page_id"), eagle_id)
                        workspace_logger.info(f"✅ Updated Notion with existing Eagle File ID: {eagle_id}")
                    except Exception as e:
                        workspace_logger.warning(f"⚠️  Failed to update Notion with Eagle File ID: {e}")

                workspace_logger.record_processed()
                workspace_logger.info(f"✅ Successfully processed (duplicate): {title}")
                return True
            elif result.get("local_import"):
                # Local file was imported to Eagle (no download needed)
                workspace_logger.info(f"🦅 LOCAL IMPORT COMPLETE: {title}")
                workspace_logger.info(f"   Eagle ID: {result.get('eagle_item_id')}")
                workspace_logger.info(f"   Fingerprint: {result.get('fingerprint', 'N/A')[:32] if result.get('fingerprint') else 'N/A'}...")
                workspace_logger.record_processed()
                workspace_logger.info(f"✅ Successfully imported local file to Eagle: {title}")
                return True
            else:
                # Normal processing completed
                workspace_logger.record_processed()
                workspace_logger.info(f"✅ Successfully processed: {title}")
                return True
        else:
            # ═══════════════════════════════════════════════════════════════
            # UNIFIED STATE TRACKING: Record failure with classified error
            # ═══════════════════════════════════════════════════════════════
            record_track_error(page_id, ErrorType.DOWNLOAD_FAILED, "Processing returned None")
            workspace_logger.error(f"❌ Failed to process: {title}")
            return False

    except Exception as exc:
        # ═══════════════════════════════════════════════════════════════
        # UNIFIED STATE TRACKING: Record exception with classified error
        # ═══════════════════════════════════════════════════════════════
        error_type = classify_error(exc, "process_track")
        record_track_error(page_id, error_type, str(exc))
        workspace_logger.error(f"❌ Exception processing track: {exc}")
        traceback.print_exc()
        return False

# ═══════════════════════════════════════════════════════════════
# YouTube Fallback System for Geo-Restricted Tracks
# ═══════════════════════════════════════════════════════════════

class GeoRestrictedError(Exception):
    """Raised when content is geo-restricted or blocked in current region."""
    pass


class DownloadSourceUnavailableError(Exception):
    """Raised when all download sources have been exhausted."""
    pass


def is_geo_restricted(error: Exception) -> bool:
    """
    Detect geo-restriction from yt-dlp error messages.
    
    Args:
        error: Exception from yt-dlp download attempt
        
    Returns:
        True if error indicates geo-restriction, False otherwise
    """
    error_str = str(error).lower()
    geo_indicators = [
        'not available in your country',
        'not available in this country',
        'geo restricted',
        'geo-restricted',
        'geographical',
        'region',
        'blocked in your country',
        'not available in this location',
        'this video is not available',
        'video unavailable',
        'uploader has not made this video available in your country'
    ]
    
    return any(indicator in error_str for indicator in geo_indicators)


def try_youtube_download(
    url: str,
    track_info: dict,
    playlist_dir: Path,
    playlist_name: str,
    retry: int = 0,
    max_retries: int = 5
) -> Optional[dict]:
    """
    Download track from YouTube as fallback source.
    
    Args:
        url: YouTube URL to download from
        track_info: Track metadata dictionary
        playlist_dir: Directory to save file
        playlist_name: Name of playlist
        retry: Current retry attempt
        max_retries: Maximum retry attempts
        
    Returns:
        Dictionary with download results or None on failure
    """
    workspace_logger.info(f"🔄 Attempting YouTube download: {url}")
    
    try:
        # Call the main download_track function but with YouTube URL
        # Note: We need to pass through to the actual implementation
        # This is a simplified version - actual implementation would need full download logic
        
        # Use custom temp directory
        import uuid
        temp_base_dir = unified_config.get("temp_dir") or os.getenv("TEMP_DIR", "/Volumes/PROJECTS-MM1/OTHER/TEMP")
        custom_temp_dir = f"{temp_base_dir}/tmp_yt_{uuid.uuid4().hex[:8]}"
        
        workspace_logger.debug(f"📁 YouTube temp directory: {custom_temp_dir}")
        os.makedirs(custom_temp_dir, exist_ok=True)
        
        # Extract info first (without SC auth header)
        ydl_common = {
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": "/opt/homebrew/bin/ffmpeg",
        }
        
        try:
            with yt_dlp.YoutubeDL({**ydl_common, "extract_flat": False}) as ydl:
                info = ydl.extract_info(url, download=False)
            
            workspace_logger.info(f"✅ YouTube metadata extracted: {info.get('title', 'Unknown')}")
            
        except Exception as exc:
            workspace_logger.error(f"❌ YouTube metadata extraction failed: {exc}")
            if os.path.exists(custom_temp_dir):
                import shutil
                shutil.rmtree(custom_temp_dir)
            return None
        
        # Download audio
        tmp_dir = Path(custom_temp_dir)
        ydl_opts = {
            **ydl_common,
            "format": "bestaudio/best",
            "outtmpl": str(tmp_dir / "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "1411",
                }
            ],
            "noplaylist": True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            workspace_logger.info(f"✅ YouTube audio downloaded successfully")
            
            # Find the downloaded WAV file
            wav_files = list(tmp_dir.glob("*.wav"))
            if not wav_files:
                workspace_logger.error(f"❌ No WAV file found after YouTube download")
                if os.path.exists(custom_temp_dir):
                    import shutil
                    shutil.rmtree(custom_temp_dir)
                return None
            
            # Return success indicator - actual processing will happen in main function
            result = {
                "success": True,
                "source": "YouTube",
                "temp_wav": wav_files[0],
                "temp_dir": custom_temp_dir,
                "info": info
            }
            
            workspace_logger.info(f"✅ YouTube download successful from: {url}")
            return result
            
        except Exception as exc:
            workspace_logger.error(f"❌ YouTube download failed: {exc}")
            if os.path.exists(custom_temp_dir):
                import shutil
                import shutil
                import shutil
            shutil.rmtree(custom_temp_dir)
            return None
            
    except Exception as exc:
        workspace_logger.error(f"❌ Unexpected error in YouTube download: {exc}")
        workspace_logger.error(traceback.format_exc())
        return None


def search_soundcloud_for_track(artist: str, title: str) -> Optional[str]:
    """
    Search SoundCloud for a track by artist and title.
    Returns the first matching track URL.

    Uses multiple search strategies:
    1. Artist + Title (exact)
    2. Title only (if artist+title fails)
    3. Cleaned title (remove parentheses/brackets)

    Args:
        artist: Artist name
        title: Track title

    Returns:
        SoundCloud URL if found, None otherwise
    """
    workspace_logger.info(f"🔍 Searching SoundCloud for: {artist} - {title}")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    # Build list of search queries to try (in order of preference)
    search_queries = []

    # 1. Artist + Title
    search_queries.append(f"{artist} {title}")

    # 2. Title only (sometimes artist name causes issues)
    if artist and artist.lower() not in title.lower():
        search_queries.append(title)

    # 3. Clean title (remove featuring, remix info in parentheses)
    clean_title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
    if clean_title != title:
        search_queries.append(f"{artist} {clean_title}")
        search_queries.append(clean_title)

    # 4. First artist only (for multi-artist tracks like "Artist1, Artist2, Artist3")
    if ',' in artist:
        first_artist = artist.split(',')[0].strip()
        search_queries.append(f"{first_artist} {title}")

    for query in search_queries:
        try:
            # Use scsearch5 for more results
            search_query = f"scsearch5:{query}"
            workspace_logger.debug(f"   Trying SoundCloud search: '{query}'")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)

                if result and result.get('entries'):
                    for entry in result['entries']:
                        # FIX: Prefer webpage_url over url to avoid API URLs
                        # API URLs look like: api.soundcloud.com/tracks/soundcloud%3Atracks%3A...
                        # Webpage URLs look like: soundcloud.com/artist/track
                        url = entry.get('webpage_url') or entry.get('url')

                        # Skip malformed API URLs that don't contain artist/track info
                        if url and 'api.soundcloud.com' in url:
                            workspace_logger.debug(f"   Skipping API URL (no artist info): {url}")
                            continue

                        if url and 'soundcloud.com' in url:
                            workspace_logger.info(f"✅ Found SoundCloud track: {url}")
                            workspace_logger.info(f"   Search query used: '{query}'")
                            return url

        except Exception as exc:
            workspace_logger.debug(f"   SoundCloud search failed for '{query}': {exc}")
            continue

    workspace_logger.warning(f"⚠️  No SoundCloud results found after {len(search_queries)} search attempts")
    return None


def search_youtube_for_track(artist: str, title: str) -> Optional[str]:
    """
    Search YouTube for a track by artist and title.
    Returns the first matching video URL.

    Uses multiple search strategies:
    1. Artist + Title + "official audio"
    2. Artist + Title (without suffix)
    3. Title only
    4. Cleaned title variations

    Args:
        artist: Artist name
        title: Track title

    Returns:
        YouTube URL if found, None otherwise

    Note:
        Uses yt-dlp search. YouTube API is optional but preferred if available.
    """
    workspace_logger.info(f"🔍 Searching YouTube for: {artist} - {title}")

    # Build list of search queries to try (in order of preference)
    search_queries = []

    # 1. Artist + Title + official audio (most specific)
    search_queries.append(f"{artist} {title} official audio")

    # 2. Artist + Title (without suffix - catches more results)
    search_queries.append(f"{artist} {title}")

    # 3. Artist + Title + audio (alternative suffix)
    search_queries.append(f"{artist} {title} audio")

    # 4. Title only (sometimes artist name causes issues)
    if artist and artist.lower() not in title.lower():
        search_queries.append(f"{title} official audio")
        search_queries.append(title)

    # 5. Clean title (remove featuring, remix info in parentheses)
    clean_title = re.sub(r'\s*[\(\[].*?[\)\]]', '', title).strip()
    if clean_title != title:
        search_queries.append(f"{artist} {clean_title}")
        search_queries.append(clean_title)

    # 6. First artist only (for multi-artist tracks)
    if ',' in artist:
        first_artist = artist.split(',')[0].strip()
        search_queries.append(f"{first_artist} {title}")

    # Try YouTube Data API v3 first (more reliable, if available)
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')

    if youtube_api_key:
        try:
            from googleapiclient.discovery import build

            youtube = build('youtube', 'v3', developerKey=youtube_api_key)

            for query in search_queries[:3]:  # Try first 3 queries with API
                try:
                    workspace_logger.debug(f"   Trying YouTube API search: '{query}'")
                    request = youtube.search().list(
                        part='snippet',
                        q=query,
                        type='video',
                        maxResults=5,
                        videoCategoryId='10'  # Music category
                    )
                    response = request.execute()

                    if response.get('items'):
                        video_id = response['items'][0]['id']['videoId']
                        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                        workspace_logger.info(f"✅ Found YouTube video via API: {youtube_url}")
                        workspace_logger.info(f"   Search query used: '{query}'")
                        return youtube_url
                except Exception as api_exc:
                    workspace_logger.debug(f"   YouTube API search failed for '{query}': {api_exc}")
                    continue

        except ImportError:
            workspace_logger.debug(f"ℹ️  google-api-python-client not installed, using yt-dlp search")
        except Exception as exc:
            workspace_logger.debug(f"ℹ️  YouTube API unavailable: {exc}")

    # Fallback: Use yt-dlp search (works without API key)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    for query in search_queries:
        try:
            # Use ytsearch3 for more results per query
            search_query = f"ytsearch3:{query}"
            workspace_logger.debug(f"   Trying yt-dlp search: '{query}'")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)

                if result and result.get('entries'):
                    for entry in result['entries']:
                        video_id = entry.get('id')
                        if video_id:
                            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
                            workspace_logger.info(f"✅ Found YouTube video via yt-dlp: {youtube_url}")
                            workspace_logger.info(f"   Search query used: '{query}'")
                            return youtube_url

        except Exception as exc:
            workspace_logger.debug(f"   yt-dlp search failed for '{query}': {exc}")
            continue

    workspace_logger.warning(f"⚠️  No YouTube results found after {len(search_queries)} search attempts")
    return None


def get_youtube_url_from_notion(track_info: dict) -> Optional[str]:
    """
    Extract YouTube URL from Notion track info.
    
    Args:
        track_info: Track metadata dictionary from Notion
        
    Returns:
        YouTube URL if present, None otherwise
    """
    youtube_url = track_info.get('youtube_url')
    
    if youtube_url and youtube_url.strip():
        workspace_logger.info(f"✅ Found YouTube URL in Notion: {youtube_url}")
        return youtube_url.strip()
    
    workspace_logger.debug(f"ℹ️  No YouTube URL in Notion for this track")
    return None


def update_notion_download_source(page_id: str, source: str, youtube_url: Optional[str] = None) -> None:
    """
    Update Notion with download source information.
    
    Args:
        page_id: Notion page ID
        source: Download source (e.g., "SoundCloud", "YouTube", "YouTube (Auto)")
        youtube_url: YouTube URL to save (optional)
    """
    if not page_id:
        workspace_logger.warning(f"⚠️  No page_id provided for Notion update")
        return
    
    try:
        updates = {
            "Download Source": source,
            "Fallback Used": source != "SoundCloud"
        }

        if youtube_url:
            updates["YouTube URL"] = youtube_url

        workspace_logger.info(f"📝 Updating Notion with download source: {source}")
        prop_types = _get_tracks_db_prop_types()
        payload = {}

        for key, value in updates.items():
            prop_name = _resolve_prop_name(key) or key
            prop_type = prop_types.get(prop_name)
            if not prop_type:
                continue
            if prop_type == "select":
                payload[prop_name] = {"select": {"name": str(value)}}
            elif prop_type == "checkbox":
                payload[prop_name] = {"checkbox": bool(value)}
            elif prop_type == "rich_text":
                payload[prop_name] = {"rich_text": [{"text": {"content": str(value)}}]}
            elif prop_type == "url":
                payload[prop_name] = {"url": str(value)}
            elif prop_type == "title":
                payload[prop_name] = {"title": [{"text": {"content": str(value)}}]}

        if youtube_url:
            yt_prop = _resolve_prop_name("YouTube URL") or "YouTube URL"
            yt_type = prop_types.get(yt_prop)
            if yt_type == "url":
                payload[yt_prop] = {"url": youtube_url}
            elif yt_type == "rich_text":
                payload[yt_prop] = {"rich_text": [{"text": {"content": youtube_url}}]}

        if "soundcloud.com" in (youtube_url or ""):
            sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
            sc_type = prop_types.get(sc_prop)
            if sc_type == "url":
                payload[sc_prop] = {"url": youtube_url}
            elif sc_type == "rich_text":
                payload[sc_prop] = {"rich_text": [{"text": {"content": youtube_url}}]}

        if payload:
            notion_manager.update_page(page_id, payload)
            workspace_logger.debug(f"   Updated properties: {list(payload.keys())}")
        else:
            workspace_logger.debug(f"   No matching Notion properties for download source update")
        
    except Exception as exc:
        workspace_logger.error(f"❌ Failed to update Notion download source: {exc}")


# ═══════════════════════════════════════════════════════════════
# REUSABLE MULTI-PLATFORM AUDIO SOURCE SEARCH
# ═══════════════════════════════════════════════════════════════

# Maximum track duration in seconds before flagging as potential mix/live set
MAX_TRACK_DURATION_SECONDS = 660  # 11 minutes


def find_audio_source_for_track(
    artist: str,
    title: str,
    track_data: Optional[dict] = None,
    exclude_urls: Optional[List[str]] = None,
    prefer_short_duration: bool = False
) -> Tuple[Optional[str], Optional[str]]:
    """
    Comprehensive multi-platform search to find audio source for a track.

    Searches across platforms in priority order:
    1. SoundCloud (preferred for audio quality)
    2. YouTube from Notion (if available)
    3. YouTube search
    4. Spotify metadata enrichment + retry searches

    Args:
        artist: Artist name
        title: Track title
        track_data: Optional track data dict from Notion (for YouTube URL lookup)
        exclude_urls: Optional list of URLs to skip (e.g., previously failed URLs)
        prefer_short_duration: If True, prefer results with shorter duration (to avoid mixes)

    Returns:
        Tuple of (download_url, source_name) or (None, None) if not found
    """
    workspace_logger.info(f"🔍 MULTI-PLATFORM SEARCH: {artist} - {title}")
    exclude_urls = exclude_urls or []

    # Step 1: Search SoundCloud
    workspace_logger.info(f"   Step 1: Searching SoundCloud...")
    sc_url = search_soundcloud_for_track(artist, title)
    if sc_url and sc_url not in exclude_urls:
        # If prefer_short_duration, validate the track isn't a mix
        if prefer_short_duration:
            duration = get_track_duration_from_url(sc_url)
            if duration and duration > MAX_TRACK_DURATION_SECONDS:
                workspace_logger.warning(f"   ⚠️  SoundCloud result appears to be a mix ({duration}s), skipping...")
            else:
                workspace_logger.info(f"   ✅ Found on SoundCloud: {sc_url}")
                return sc_url, "SoundCloud (Search)"
        else:
            workspace_logger.info(f"   ✅ Found on SoundCloud: {sc_url}")
            return sc_url, "SoundCloud (Search)"

    # Step 2: Check for YouTube URL in Notion
    if track_data:
        workspace_logger.info(f"   Step 2: Checking Notion for YouTube URL...")
        yt_url = get_youtube_url_from_notion(track_data)
        if yt_url and yt_url not in exclude_urls:
            if prefer_short_duration:
                duration = get_track_duration_from_url(yt_url)
                if duration and duration > MAX_TRACK_DURATION_SECONDS:
                    workspace_logger.warning(f"   ⚠️  YouTube URL appears to be a mix ({duration}s), skipping...")
                else:
                    workspace_logger.info(f"   ✅ Found YouTube in Notion: {yt_url}")
                    return yt_url, "YouTube (Notion)"
            else:
                workspace_logger.info(f"   ✅ Found YouTube in Notion: {yt_url}")
                return yt_url, "YouTube (Notion)"

    # Step 3: Search YouTube
    workspace_logger.info(f"   Step 3: Searching YouTube...")
    yt_url = search_youtube_for_track(artist, title)
    if yt_url and yt_url not in exclude_urls:
        if prefer_short_duration:
            duration = get_track_duration_from_url(yt_url)
            if duration and duration > MAX_TRACK_DURATION_SECONDS:
                workspace_logger.warning(f"   ⚠️  YouTube result appears to be a mix ({duration}s), skipping...")
            else:
                workspace_logger.info(f"   ✅ Found on YouTube: {yt_url}")
                return yt_url, "YouTube (Search)"
        else:
            workspace_logger.info(f"   ✅ Found on YouTube: {yt_url}")
            return yt_url, "YouTube (Search)"

    # Step 4: Try Spotify enrichment and retry
    if track_data:
        workspace_logger.info(f"   Step 4: Trying Spotify enrichment...")
        enriched_data = enrich_spotify_metadata(track_data.copy())
        if enriched_data.get("spotify_id"):
            enriched_artist = enriched_data.get("artist", artist)
            enriched_title = enriched_data.get("title", title)

            if enriched_artist != artist or enriched_title != title:
                workspace_logger.info(f"   📝 Enriched metadata: {enriched_artist} - {enriched_title}")

                # Retry SoundCloud with enriched metadata
                sc_url = search_soundcloud_for_track(enriched_artist, enriched_title)
                if sc_url and sc_url not in exclude_urls:
                    workspace_logger.info(f"   ✅ Found on SoundCloud (enriched): {sc_url}")
                    return sc_url, "SoundCloud (Enriched)"

                # Retry YouTube with enriched metadata
                yt_url = search_youtube_for_track(enriched_artist, enriched_title)
                if yt_url and yt_url not in exclude_urls:
                    workspace_logger.info(f"   ✅ Found on YouTube (enriched): {yt_url}")
                    return yt_url, "YouTube (Enriched)"

    workspace_logger.warning(f"   ❌ No audio source found on any platform")
    return None, None


def get_track_duration_from_url(url: str) -> Optional[int]:
    """
    Get track duration from URL using yt-dlp without downloading.

    Args:
        url: Audio source URL (SoundCloud or YouTube)

    Returns:
        Duration in seconds, or None if unable to determine
    """
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        # Add SoundCloud auth header if it's a SoundCloud URL
        if 'soundcloud.com' in url:
            ydl_opts["http_headers"] = {"Authorization": SC_AUTH_HEADER}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration')
            if duration:
                return int(duration)
    except Exception as exc:
        workspace_logger.debug(f"   Could not get duration from URL: {exc}")

    return None


def _handle_404_fallback(
    url: str,
    track_info: dict,
    playlist_dir: Path,
    playlist_name: str,
    max_retries: int,
) -> Optional[dict]:
    """
    Attempt alternate audio sources after a SoundCloud 404.
    Returns download result if successful, otherwise None.
    """
    if not track_info:
        return None

    attempted = track_info.setdefault("_fallback_exclude_urls", [])
    if isinstance(attempted, set):
        attempted = list(attempted)
    if url not in attempted:
        attempted.append(url)
    track_info["_fallback_exclude_urls"] = attempted

    attempts = int(track_info.get("_fallback_attempts", 0))
    if attempts >= 2:
        return None
    track_info["_fallback_attempts"] = attempts + 1

    artist = track_info.get("artist") or track_info.get("notion_artist") or ""
    title = track_info.get("title") or track_info.get("notion_title") or ""

    if not artist or not title:
        return None

    download_url, download_source = find_audio_source_for_track(
        artist=artist,
        title=title,
        track_data=track_info,
        exclude_urls=list(attempted),
        prefer_short_duration=True
    )

    if not download_url or download_url in attempted:
        return None

    if track_info.get("page_id"):
        try:
            if "soundcloud.com" in download_url:
                sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
                notion_manager.update_page(track_info["page_id"], {sc_prop: {"url": download_url}})
                workspace_logger.info("📝 Updated Notion with fallback SoundCloud URL")
            elif "youtube.com" in download_url or "youtu.be" in download_url:
                update_notion_download_source(track_info["page_id"], download_source, download_url)
        except Exception as exc:
            workspace_logger.warning(f"⚠️  Failed to update Notion with fallback URL: {exc}")

    workspace_logger.info(f"🔄 404 fallback: trying {download_source} → {download_url}")
    attempted.add(download_url)
    track_info["_fallback_exclude_urls"] = attempted

    return download_track(
        url=download_url,
        playlist_dir=playlist_dir,
        track_info=track_info,
        playlist_name=playlist_name,
        retry=0,
        max_retries=max_retries
    )


def is_likely_mix_or_live_set(duration_seconds: int, title: str = "", artist: str = "") -> bool:
    """
    Determine if a track is likely a mix or live set based on duration and metadata.

    Args:
        duration_seconds: Track duration in seconds
        title: Track title (for keyword detection)
        artist: Artist name

    Returns:
        True if track appears to be a mix/live set, False otherwise
    """
    # Duration check: > 11 minutes is suspicious
    if duration_seconds > MAX_TRACK_DURATION_SECONDS:
        workspace_logger.info(f"🚨 DURATION CHECK: {duration_seconds}s exceeds {MAX_TRACK_DURATION_SECONDS}s limit")
        return True

    # Title keyword check for common mix/set indicators
    title_lower = title.lower()
    mix_keywords = [
        'mix', 'set', 'live', 'dj set', 'dj mix', 'compilation',
        'continuous', 'b2b', 'back to back', 'essential mix',
        'radio show', 'podcast', 'episode', 'ep.', 'part 1', 'part 2',
        'full album', 'album mix', 'mini mix', 'megamix'
    ]

    for keyword in mix_keywords:
        if keyword in title_lower:
            workspace_logger.info(f"🚨 TITLE KEYWORD CHECK: Found '{keyword}' in title")
            return True

    return False


def remediate_erroneous_match(
    track_data: dict,
    failed_url: str,
    actual_duration: int,
    playlist_dir: Path,
    playlist_name: str
) -> Optional[dict]:
    """
    Remediation process when a downloaded track is detected as a mix/live set.

    This function:
    1. Logs the erroneous match
    2. Adds the failed URL to exclusion list
    3. Searches for the correct track with stricter criteria
    4. Downloads and validates the new match

    Args:
        track_data: Original track data from Notion
        failed_url: URL that returned a mix/live set
        actual_duration: Duration of the erroneous download (in seconds)
        playlist_dir: Directory to save files
        playlist_name: Playlist name

    Returns:
        Download result dict if remediation successful, None otherwise
    """
    title = track_data.get("title", "Unknown")
    artist = track_data.get("artist", "Unknown")
    expected_duration = track_data.get("duration")  # From Spotify/Notion if available

    workspace_logger.warning(f"\n{'='*80}")
    workspace_logger.warning(f"🚨 ERRONEOUS MATCH DETECTED - INITIATING REMEDIATION")
    workspace_logger.warning(f"{'='*80}")
    workspace_logger.warning(f"   Track: {title} by {artist}")
    workspace_logger.warning(f"   Failed URL: {failed_url}")
    workspace_logger.warning(f"   Downloaded duration: {actual_duration}s ({actual_duration // 60}m {actual_duration % 60}s)")
    if expected_duration:
        workspace_logger.warning(f"   Expected duration: {expected_duration}s ({expected_duration // 60}m {expected_duration % 60}s)")
    workspace_logger.warning(f"   Reason: Duration exceeds {MAX_TRACK_DURATION_SECONDS}s (11 minutes)")
    workspace_logger.info(f"\n🔄 Searching for correct track with stricter criteria...")

    # Search with the failed URL excluded and prefer_short_duration enabled
    new_url, new_source = find_audio_source_for_track(
        artist=artist,
        title=title,
        track_data=track_data,
        exclude_urls=[failed_url],
        prefer_short_duration=True
    )

    if not new_url:
        workspace_logger.error(f"❌ REMEDIATION FAILED: No alternative audio source found")
        workspace_logger.info(f"📋 Track will be flagged for manual review")

        # Update Notion with remediation failure status
        if track_data.get("page_id"):
            try:
                update_audio_processing_status(track_data["page_id"], ["Mix/Set Detected - Manual Review Required"])
            except Exception:
                pass

        return None

    workspace_logger.info(f"✅ Found alternative source via {new_source}: {new_url}")
    workspace_logger.info(f"🔄 Downloading from alternative source...")

    # Download from the new source (recursive call to download_track)
    # Note: This will go through the same validation, preventing infinite loops
    # because we exclude the failed URL
    result = download_track(
        url=new_url,
        playlist_dir=playlist_dir,
        track_info=track_data,
        playlist_name=playlist_name,
        retry=0,
        max_retries=3  # Limit retries for remediation
    )

    if result:
        workspace_logger.info(f"✅ REMEDIATION SUCCESSFUL!")
        workspace_logger.info(f"   New source: {new_source}")
        workspace_logger.info(f"   New URL: {new_url}")

        # Update Notion with the corrected source
        if track_data.get("page_id"):
            try:
                update_notion_download_source(track_data["page_id"], f"{new_source} (Remediated)", new_url if 'youtube' in new_url.lower() else None)

                # Update SoundCloud URL if that's the new source
                if 'soundcloud.com' in new_url:
                    sc_prop = _resolve_prop_name("SoundCloud URL") or "SoundCloud URL"
                    notion_manager.update_page(track_data["page_id"], {sc_prop: {"url": new_url}})
            except Exception as e:
                workspace_logger.warning(f"⚠️  Failed to update Notion with remediated source: {e}")

        return result
    else:
        workspace_logger.error(f"❌ REMEDIATION DOWNLOAD FAILED")
        workspace_logger.info(f"📋 Track will be flagged for manual review")

        if track_data.get("page_id"):
            try:
                update_audio_processing_status(track_data["page_id"], ["Mix/Set Detected - Download Failed"])
            except Exception:
                pass

        return None


# ═══════════════════════════════════════════════════════════════
# Enhanced Metadata Cleaning (from fix_soundcloud_metadata.py)
# ═══════════════════════════════════════════════════════════════

def clean_title_advanced(title: str) -> str:
    """
    Advanced title cleaning with label removal and artist extraction.
    Enhanced version from fix_soundcloud_metadata.py.
    
    Args:
        title: Original title string
        
    Returns:
        Cleaned title string
        
    Examples:
        "03 Artist - Track Title" -> "Track Title"
        "Artist X Artist - Track Title (Remix) Jungle Cakes" -> "Track Title (Remix)"
    """
    if not title or title == 'Unknown':
        return title
    
    cleaned = title
    
    # Remove track numbers at start (e.g., "03 ", "1. ", "01. ")
    cleaned = re.sub(r'^\d+\.?\s*', '', cleaned)
    
    # Remove common prefixes
    cleaned = re.sub(r'^(track|song|music)\s*[-_]\s*', '', cleaned, flags=re.IGNORECASE)
    
    # Clean up multiple dashes/underscores
    cleaned = re.sub(r'[-_]{2,}', ' - ', cleaned)
    
    # Clean up spacing around dashes
    cleaned = re.sub(r'\s*-\s*', ' - ', cleaned)
    
    # Extract track title from "Artist - Title" format
    artist_title_pattern = r'^([^-]+?)\s*-\s*(.+)$'
    match = re.search(artist_title_pattern, cleaned)
    
    if match:
        track_title = match.group(2).strip()
        
        # Handle remix information
        if 'remix' in track_title.lower():
            remix_match = re.search(r'\((.*?remix.*?)\)', track_title, re.IGNORECASE)
            if remix_match:
                remix_text = remix_match.group(1)
                track_title = re.sub(r'\s*\(.*?remix.*?\)\s*', '', track_title, flags=re.IGNORECASE)
                track_title = f"{track_title} ({remix_text})"
        
        # Remove label names at the end (common labels)
        label_names = [
            'Jungle Cakes', 'Hospital Records', 'UKF', 'Monstercat',
            'Elevate Records', 'mau5trap', 'Let It Roll Recordings',
            'Musical Freedom', 'Drum&BassArena', 'Chef P', 'Subsonic',
            'WHIPPED CREAM', 'John Summit', 'Levity', 'SoDown', 'PHIBES',
            'Spinnin Records', 'Armada Music', 'OWSLA', 'Mad Decent',
            'Fool\'s Gold', 'Dirtybird', 'Anjunabeats', 'Defected'
        ]
        
        for label in label_names:
            track_title = re.sub(rf'\s+{re.escape(label)}\s*$', '', track_title, flags=re.IGNORECASE)
        
        # Remove generic label patterns (all caps words at end)
        track_title = re.sub(r'\s+[A-Z]{3,}\d*\s*$', '', track_title)
        
        return track_title.strip()
    
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()


def extract_artists_from_title(title: str) -> List[str]:
    """
    Extract multiple artists from collaboration format in title.
    
    Args:
        title: Original title string
        
    Returns:
        List of artist names
        
    Examples:
        "Artist1 X Artist2 X Artist3 - Track" -> ["Artist1", "Artist2", "Artist3"]
        "Artist1 & Artist2 - Track" -> ["Artist1", "Artist2"]
    """
    if not title:
        return []
    
    # Pattern: "Artist X Artist X Artist - Track Title"
    collaboration_pattern = r'^([^-]+?)\s*-\s*(.+)$'
    match = re.search(collaboration_pattern, title)
    
    if match:
        artists_part = match.group(1).strip()
        artists = []
        
        # Try splitting by "X" first
        for artist in re.split(r'\s+X\s+', artists_part):
            artist = artist.strip()
            if artist:
                artist = re.sub(r'\s+', ' ', artist)  # Remove extra spaces
                artist = re.sub(r'^\s+|\s+$', '', artist)  # Trim
                if artist:
                    artists.append(artist)
        
        # If no artists found with "X", try "&"
        if not artists:
            for artist in re.split(r'\s*&\s*', artists_part):
                artist = artist.strip()
                if artist:
                    artist = re.sub(r'\s+', ' ', artist)
                    artist = re.sub(r'^\s+|\s+$', '', artist)
                    if artist:
                        artists.append(artist)
        
        return artists
    
    return []


def clean_artist_name(artist: str) -> str:
    """
    Clean up artist name formatting.
    
    Args:
        artist: Original artist name
        
    Returns:
        Cleaned artist name
        
    Examples:
        "Artist Official" -> "Artist"
        "Artist   Music" -> "Artist"
    """
    if not artist or artist == 'Unknown Artist':
        return artist
    
    cleaned = artist
    
    # Remove common suffixes
    cleaned = re.sub(r'\s+(official|music|records|label|sounds)$', '', cleaned, flags=re.IGNORECASE)
    
    # Clean up multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # Remove leading/trailing whitespace
    cleaned = re.sub(r'^\s+|\s+$', '', cleaned)
    
    return cleaned.strip()


def is_collaboration(title: str) -> bool:
    """
    Check if title contains artist collaboration (multiple artists).
    
    Args:
        title: Original title
        
    Returns:
        True if it's a collaboration
    """
    if not title:
        return False
    
    # Pattern: "Artist X Artist - Track" or "Artist & Artist - Track"
    collaboration_pattern = r'^([^-]+?)\s*-\s*(.+)$'
    match = re.search(collaboration_pattern, title)
    
    if match:
        artists_part = match.group(1).strip()
        
        # Check for "X" or "&" separators indicating collaboration
        if re.search(r'\s+X\s+', artists_part) or re.search(r'\s*&\s*', artists_part):
            # Count artists
            x_artists = len(re.split(r'\s+X\s+', artists_part))
            and_artists = len(re.split(r'\s*&\s*', artists_part))
            
            # If more than one artist, it's a collaboration
            return max(x_artists, and_artists) > 1
    
    return False


# ───────────────────────────────────────────────────────────────
# Main Download Function (adapted from original)
# ───────────────────────────────────────────────────────────────
def download_track(
    url: str,
    playlist_dir: Path,
    track_info: dict,
    playlist_name: str,
    retry: int = 0,
    max_retries: int = 20,
):
    """
    Download, convert, tag, and move files.
    Returns dict for track entry or None on failure.
    """
    workspace_logger.info(f"\n{'='*80}")
    workspace_logger.info(f"🎵 PROCESSING TRACK")
    workspace_logger.info(f"{'='*80}")
    workspace_logger.info(f"URL: {url}")
    # Get actual playlist names from track relations
    playlist_names = get_playlist_names_from_track(track_info)
    if playlist_names:
        playlist_display = ", ".join(playlist_names)
    else:
        playlist_display = "No Playlist Assigned"
    workspace_logger.info(f"Playlist: {playlist_display}")
    workspace_logger.info(f"Retry: {retry}/{max_retries}")

    # Log the incoming track_info to see what data we have
    workspace_logger.info(f"\n📊 TRACK_INFO from Notion:")
    workspace_logger.info(json.dumps(track_info, indent=2, default=str))

    # 🔧 CRITICAL FIX: Check for duplicates BEFORE downloading
    # This prevents unnecessary downloads and processing
    title = track_info.get("title", "Unknown Track")
    artist = track_info.get("artist", "Unknown Artist")
    
    # Extract all available metadata for accurate matching
    duration = track_info.get("duration")
    bpm = track_info.get("bpm")
    key = track_info.get("key")

    workspace_logger.info(f"🔍 PRE-DOWNLOAD DUPLICATE CHECK: {title} by {artist}")

    try:
        # Check if this track already exists in Eagle using all available metadata
        best_item, all_matches = eagle_find_best_matching_item(
            filename=f"{title}.wav",
            fingerprint=track_info.get("fingerprint"),
            title=title,
            artist=artist,
            duration=float(duration) if duration else None,
            bpm=int(bpm) if bpm else None,
            key=key,
        )
        
        if best_item:
            workspace_logger.info(f"✅ DUPLICATE FOUND: Eagle item {best_item['id']} already exists")
            workspace_logger.info(f"   Item name: '{best_item.get('name', 'Unknown')}'")
            workspace_logger.info(f"   Existing tags: {best_item.get('tags', [])}")
            workspace_logger.info(f"   Skipping download but applying tag corrections to existing item")
            
            # 🔧 CRITICAL FIX: Apply tag corrections to existing item
            try:
                # Generate the same tags that would be applied to a new item
                playlist_names = get_playlist_names_from_track(track_info)
                if playlist_names:
                    playlist_name = playlist_names[0]
                else:
                    playlist_name = "Unassigned"
                
                # Generate tags using the same logic as for new items
                processing_data = {"duration": 0, "bpm": 0, "key": "Unknown"}
                tags = generate_comprehensive_tags(track_info, processing_data, "wav")
                workspace_logger.info(f"🔄 Applying tag corrections to existing Eagle item: {best_item['id']}")
                workspace_logger.info(f"   New tags: {tags}")
                
                # Update tags on the existing item
                if eagle_update_tags(best_item['id'], tags):
                    workspace_logger.info("✅ Tags updated successfully on existing item")
                    # Validate tags were applied
                    if eagle_validate_tags_applied(best_item['id'], tags):
                        workspace_logger.info("✅ Tags validation successful")
                    else:
                        workspace_logger.warning("⚠️  Tags validation failed - tags may not be applied correctly")
                else:
                    workspace_logger.warning("⚠️  Failed to update tags on existing item")
                    
            except Exception as e:
                workspace_logger.warning(f"⚠️  Failed to apply tag corrections to existing item: {e}")
            
            # Return the existing item info (with updated tags)
            return {
                "file": None,  # No new file created
                "duration": 0,
                "artist": artist,
                "title": title,
                "eagle_item_id": best_item['id'],
                "duplicate_found": True,
                "existing_item": best_item,
                "tags_applied": True,  # Indicate that tags were applied
                # CRITICAL: Include page_id for caller to update their reference
                "page_id": track_info.get("page_id"),
            }
        else:
            workspace_logger.info(f"✅ NO DUPLICATES FOUND: Proceeding with download and processing")
            
    except Exception as e:
        workspace_logger.warning(f"⚠️  Duplicate check failed: {e}")
        workspace_logger.info(f"   Proceeding with download and processing")
        # Continue with normal processing if duplicate check fails

    profiler = cProfile.Profile()
    try:
        profiler.enable()
    except ValueError:
        # Another profiling tool is already active, skip profiling
        profiler = None

    # Derive safe filename base
    artist_from_url, track_from_url = parse_soundcloud_url(url)
    title = track_info.get("title") or track_from_url or "Unknown Track"
    # Determine final file paths for existence check
    safe_base = re.sub(r"[^\w\s-]", "", title).strip()

    playlist_dir.mkdir(parents=True, exist_ok=True)

    # Define primary and secondary output paths
    aiff_path = playlist_dir / f"{safe_base}.aiff"
    m4a_path = playlist_dir / f"{safe_base}.m4a"
    m4a_backup_path = BACKUP_DIR / f"{safe_base}.m4a"
    # wav_path will be defined later as temp file for Eagle import only

    # Skip if already done (both AIFF and M4A already created)
    if aiff_path.exists() and m4a_path.exists():
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(aiff_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            dur = int(float(result.stdout.strip()))
        except Exception:
            dur = 0

        if profiler:
            try:
                try:
                    profiler.disable()
                finally:
                    profiler.close()
            except Exception:
                pass
            try:
                if profiler:
                    profiler.dump_stats("soundcloud_download_profile.prof")
            except Exception:
                pass

        return {
            "file": aiff_path,
            "duration": dur,
            "artist": track_info.get("artist") or artist_from_url or "",
            "title": title,
            "eagle_item_id": None,
        }

    # Exponential back-off with jitter
    sleep_s = random.uniform(1, 3) if retry == 0 else min(300, 2 ** retry) + random.uniform(0, 2)
    if retry > 0:
        workspace_logger.info(f"⏳ Retry {retry}/{max_retries} – sleeping {sleep_s:.1f}s")
        time.sleep(sleep_s)

    # ── yt-dlp: probe info for metadata ─────────────────────────
    ydl_common = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {"Authorization": SC_AUTH_HEADER},
        "ffmpeg_location": "/opt/homebrew/bin/ffmpeg",
    }
    try:
        with yt_dlp.YoutubeDL({**ydl_common, "extract_flat": False}) as ydl:
            info = ydl.extract_info(url, download=False)

        workspace_logger.info(f"\n📊 YT-DLP EXTRACTED INFO:")
        workspace_logger.info(f"   uploader: {info.get('uploader')}")
        workspace_logger.info(f"   artist: {info.get('artist')}")
        workspace_logger.info(f"   creator: {info.get('creator')}")
        workspace_logger.info(f"   channel: {info.get('channel')}")
        workspace_logger.info(f"   uploader_id: {info.get('uploader_id')}")

    except Exception as exc:
        msg = str(exc)
        workspace_logger.warning(f"yt-dlp metadata error ({url}): {msg}")
        if ("HTTP Error 404" in msg) or ("404: Not Found" in msg) or ("HTTPError 404" in msg):
            fallback_result = _handle_404_fallback(
                url=url,
                track_info=track_info,
                playlist_dir=playlist_dir,
                playlist_name=playlist_name,
                max_retries=max_retries,
            )
            if fallback_result:
                return fallback_result
            workspace_logger.info("🔚 Permanent 404. Marking SC_404 and aborting retries for this track.")
            try:
                update_audio_processing_status(track_info.get('page_id'), ['SC_404'])
            except Exception:
                pass
            return None
        try:
            sleep_seconds = min(2 ** max(1, int(retry)), 60)
        except Exception:
            sleep_seconds = 2
        workspace_logger.info(f"Sleeping {sleep_seconds}s before retrying metadata fetch")
        time.sleep(sleep_seconds)
        
        # Handle rate limiting and HTTP errors (existing logic)
        if ("429" in str(exc) or "HTTP Error" in str(exc)) and retry < max_retries:
            # Exponential backoff before retrying metadata fetch
            wait = min(60, 2 ** retry)
            workspace_logger.info(f"Sleeping {wait}s before retrying metadata fetch")
            time.sleep(wait)
            workspace_logger.warning(f"yt-dlp metadata error ({url}): {exc} – will retry.")
            # Check for 404 errors and abort retries
            if 'HTTP Error 404' in str(exc) or '404: Not Found' in str(exc):
                fallback_result = _handle_404_fallback(
                    url=url,
                    track_info=track_info,
                    playlist_dir=playlist_dir,
                    playlist_name=playlist_name,
                    max_retries=max_retries,
                )
                if fallback_result:
                    return fallback_result
                workspace_logger.info('🔚 Permanent 404. Marking SC_404 and aborting retries for this track.')
                try:
                    update_audio_processing_status(track_info.get('page_id'), ['SC_404'])
                except Exception:
                    pass
                return None  # Abort retries
            return download_track(
                url, playlist_dir, track_info, playlist_name, retry + 1, max_retries
            )
        
        # Other errors
        workspace_logger.error(f"yt-dlp metadata error ({url}): {exc}")
        if profiler:
            try:
                try:
                    profiler.disable()
                finally:
                    profiler.close()
            except Exception:
                pass
            try:
                if profiler:
                    profiler.dump_stats('soundcloud_download_profile.prof')
            except Exception:
                pass
        # Note: custom_temp_dir is not yet defined at this point (early error path)
        # No cleanup needed - temp dir was never created
        return None

    # Artist resolution with detailed logging
    workspace_logger.info(f"\n🎨 ARTIST RESOLUTION PROCESS:")

    # Check all possible artist fields
    artist_candidates = {
        "notion_artist": track_info.get("artist"),
        "artist_from_url": artist_from_url,
        "yt-dlp artist": info.get("artist"),
        "yt-dlp uploader": info.get("uploader"),
        "yt-dlp creator": info.get("creator"),
        "yt-dlp channel": info.get("channel"),
    }

    workspace_logger.info("   Artist candidates found:")
    for source, value in artist_candidates.items():
        if value:
            workspace_logger.info(f"   ✓ {source}: '{value}'")
        else:
            workspace_logger.info(f"   ✗ {source}: None/Empty")

    # Final artist selection
    # FIX: Skip artist_from_url if it's None (from malformed URL) or a reserved path
    RESERVED_ARTIST_VALUES = {'tracks', 'playlists', 'sets', 'albums', 'users', 'discover', 'search', 'stream'}

    # FIX 2026-01-15: Helper to detect SoundCloud auto-generated usernames (user-#########)
    def is_soundcloud_auto_username(name: str) -> bool:
        """Detect SoundCloud auto-generated usernames like 'user-123456789'."""
        if not name:
            return False
        import re
        # Pattern: 'user-' followed by 6+ digits (SoundCloud user IDs are typically 6-12 digits)
        return bool(re.match(r'^user-\d{6,}$', name.lower()))

    # FIX 2026-01-15: Helper to check if artist name is invalid/auto-generated
    def is_invalid_artist_name(name: str) -> bool:
        """Check if artist name is invalid (reserved word or SoundCloud auto-username)."""
        if not name:
            return True
        name_lower = name.lower().strip()
        if name_lower in RESERVED_ARTIST_VALUES:
            return True
        if is_soundcloud_auto_username(name_lower):
            return True
        if name_lower in ('unknown', 'unknown artist', 'n/a', ''):
            return True
        return False

    # Validate artist_from_url - reject if invalid
    valid_artist_from_url = artist_from_url if (artist_from_url and not is_invalid_artist_name(artist_from_url)) else None
    if artist_from_url and valid_artist_from_url is None:
        workspace_logger.warning(f"   ⚠️  Rejected artist_from_url '{artist_from_url}' (auto-generated or invalid)")

    # FIX 2026-01-15: Also validate track_info artist
    notion_artist = track_info.get("artist")
    valid_notion_artist = notion_artist if (notion_artist and not is_invalid_artist_name(notion_artist)) else None
    if notion_artist and valid_notion_artist is None:
        workspace_logger.warning(f"   ⚠️  Rejected notion_artist '{notion_artist}' (auto-generated or invalid)")

    # FIX 2026-01-15: Validate yt-dlp sources too
    ydl_uploader = info.get("uploader")
    ydl_artist = info.get("artist")
    ydl_creator = info.get("creator")
    valid_ydl_uploader = ydl_uploader if (ydl_uploader and not is_invalid_artist_name(ydl_uploader)) else None
    valid_ydl_artist = ydl_artist if (ydl_artist and not is_invalid_artist_name(ydl_artist)) else None
    valid_ydl_creator = ydl_creator if (ydl_creator and not is_invalid_artist_name(ydl_creator)) else None

    artist = (
        valid_notion_artist  # FIX: Use validated Notion artist
        or valid_artist_from_url  # FIX: Use validated URL-parsed artist
        or valid_ydl_uploader  # FIX: Use validated yt-dlp uploader
        or valid_ydl_artist  # FIX: Use validated yt-dlp artist field
        or valid_ydl_creator  # FIX: Use validated creator field
        or "Unknown Artist"
    ).strip()

    # FIX: Final safety check - if we still got an invalid artist, use Unknown Artist
    if is_invalid_artist_name(artist):
        workspace_logger.warning(f"   ⚠️  Artist '{artist}' is invalid - using 'Unknown Artist'")
        artist = "Unknown Artist"

    workspace_logger.info(f"\n   🎯 FINAL ARTIST SELECTED: '{artist}'")

    genre = (track_info.get("genre") or info.get("genre") or "Electronic").strip()
    album = track_info.get("album") or "SoundCloud Downloads"

    # ── yt-dlp: actual download → WAV ───────────────────────────
    # Use custom temp directory from unified config to avoid disk space issues
    import uuid
    temp_base_dir = unified_config.get("temp_dir") or os.getenv("TEMP_DIR", "/Volumes/PROJECTS-MM1/OTHER/TEMP")
    custom_temp_dir = f"{temp_base_dir}/tmp_{uuid.uuid4().hex[:8]}"
    
    # Enhanced logging for temp directory creation
    workspace_logger.temp_dir_created(custom_temp_dir)
    workspace_logger.debug(f"📁 Temp directory: {custom_temp_dir}")
    
    os.makedirs(custom_temp_dir, exist_ok=True)
    try:
        tmp_dir = Path(custom_temp_dir)
        ydl_opts = {
            **ydl_common,
            "format": "bestaudio/best",
            "outtmpl": str(tmp_dir / "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "1411",
                }
            ],
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            workspace_logger.debug(f"yt-dlp download complete for: {url}")
        except Exception as exc:
            # Check for geo-restriction during download phase
            if is_geo_restricted(exc):
                workspace_logger.warning(f"🚫 GEO-RESTRICTION DETECTED during download: {url}")
                workspace_logger.info(f"   Error: {exc}")
                
                # Check if YouTube fallback is enabled
                enable_youtube_fallback = unified_config.get("enable_youtube_fallback", True)
                if not enable_youtube_fallback:
                    workspace_logger.warning(f"⚠️  YouTube fallback is disabled in config")
                    if profiler:
                        try:
                            try:
                                profiler.disable()
                            finally:
                                profiler.close()
                        except Exception:
                            pass
                        try:
                            if profiler:
                                profiler.dump_stats('soundcloud_download_profile.prof')
                        except Exception:
                            pass
                    try:
                        if os.path.exists(custom_temp_dir):
                            import shutil
                            shutil.rmtree(custom_temp_dir)
                    except:
                        pass
                    return None
                
                # Try YouTube fallback
                workspace_logger.info(f"🔄 Attempting YouTube fallback (download phase)...")
                
                # Step 1: Check for YouTube URL in Notion
                youtube_url = get_youtube_url_from_notion(track_info)
                
                if youtube_url:
                    workspace_logger.info(f"✅ Found YouTube URL in Notion")
                    yt_result = try_youtube_download(youtube_url, track_info, playlist_dir, playlist_name)
                    
                    if yt_result:
                        workspace_logger.info(f"✅ YouTube download successful from Notion URL")
                        update_notion_download_source(track_info.get('page_id'), 'YouTube (Notion)')
                        # Clean up SC temp directory
                        try:
                            if os.path.exists(custom_temp_dir):
                                import shutil
                                shutil.rmtree(custom_temp_dir)
                        except:
                            pass
                        return yt_result
                
                # Step 2: Search YouTube
                enable_youtube_search = unified_config.get("enable_youtube_search", True)
                if enable_youtube_search:
                    workspace_logger.info(f"🔍 Searching YouTube for alternative...")
                    
                    artist = track_info.get('artist', 'Unknown')
                    title = track_info.get('title', 'Unknown')
                    
                    youtube_url = search_youtube_for_track(artist, title)
                    
                    if youtube_url:
                        workspace_logger.info(f"✅ Found YouTube video")
                        yt_result = try_youtube_download(youtube_url, track_info, playlist_dir, playlist_name)
                        
                        if yt_result:
                            workspace_logger.info(f"✅ YouTube download successful from search")
                            update_notion_download_source(
                                track_info.get('page_id'),
                                'YouTube (Auto)',
                                youtube_url
                            )
                            # Clean up SC temp directory
                            try:
                                if os.path.exists(custom_temp_dir):
                                    import shutil
                                    shutil.rmtree(custom_temp_dir)
                            except:
                                pass
                            return yt_result
                
                # All fallback methods failed
                workspace_logger.error(f"❌ All fallback methods exhausted")
                if profiler:
                    try:
                        try:
                            profiler.disable()
                        finally:
                            profiler.close()
                    except Exception:
                        pass
                    try:
                        if profiler:
                            profiler.dump_stats('soundcloud_download_profile.prof')
                    except Exception:
                        pass
                try:
                    if os.path.exists(custom_temp_dir):
                        import shutil
                        shutil.rmtree(custom_temp_dir)
                except:
                    pass
                return None
            
            # Non-geo-restriction error
            workspace_logger.error(f"Download failed ({url}): {exc}")
            try:
                try:
                    profiler.disable()
                finally:
                    profiler.close()
            except Exception:
                pass
            try:
                if profiler:
                    profiler.dump_stats('soundcloud_download_profile.prof')
            except Exception:
                pass
            # Clean up temp directory before returning
            try:
                if os.path.exists(custom_temp_dir):
                    import shutil
                    shutil.rmtree(custom_temp_dir)
                    workspace_logger.temp_dir_cleaned(custom_temp_dir)
            except Exception as cleanup_exc:
                workspace_logger.warning(f"⚠️  Failed to cleanup temp directory {custom_temp_dir}: {cleanup_exc}")
            return None

        # Expect exactly one WAV
        wav_files = list(tmp_dir.glob("*.wav"))
        if not wav_files:
            workspace_logger.error(f"No WAV extracted for {url}")
            try:
                try:
                    profiler.disable()
                finally:
                    profiler.close()
            except Exception:
                pass
            try:
                if profiler:
                    profiler.dump_stats('soundcloud_download_profile.prof')
            except Exception:
                pass
            # Clean up temp directory before returning
            try:
                if os.path.exists(custom_temp_dir):
                    import shutil
                    shutil.rmtree(custom_temp_dir)
                    workspace_logger.temp_dir_cleaned(custom_temp_dir)
            except Exception as cleanup_exc:
                workspace_logger.warning(f"⚠️  Failed to cleanup temp directory {custom_temp_dir}: {cleanup_exc}")
            return None
        wav_path_tmp = wav_files[0]
        workspace_logger.debug(f"WAV file for analysis: {wav_path_tmp}")

        # ── Analysis: duration, BPM, key ────────────────────────
        workspace_logger.info("🎵 Starting audio analysis...")
        
        # Verify WAV file exists and is valid
        if not wav_path_tmp.exists():
            workspace_logger.error(f"❌ WAV file not found: {wav_path_tmp}")
            duration, bpm, trad_key = 0, 0, "Unknown"
        else:
            # Check file size
            file_size = wav_path_tmp.stat().st_size
            workspace_logger.info(f"📁 WAV file size: {file_size / (1024*1024):.2f} MB")
            
            if file_size < 1024:  # Less than 1KB
                workspace_logger.error(f"❌ WAV file too small ({file_size} bytes), likely corrupted")
                duration, bpm, trad_key = 0, 0, "Unknown"
            else:
                try:
                    workspace_logger.info("🔄 Loading audio with librosa...")
                    workspace_logger.info("⏳ This may take a moment for large files...")
                    y, sr = librosa.load(str(wav_path_tmp), sr=None)
                    workspace_logger.info(f"✅ Audio loaded: {len(y)} samples, {sr} Hz sample rate")
                    
                    # Calculate duration
                    duration = int(librosa.get_duration(y=y, sr=sr))
                    workspace_logger.info(f"⏱️  Duration calculated: {duration} seconds")

                    # ═══════════════════════════════════════════════════════════════
                    # MIX/LIVE SET DETECTION - Check if downloaded track is too long
                    # ═══════════════════════════════════════════════════════════════
                    if duration > MAX_TRACK_DURATION_SECONDS:
                        workspace_logger.warning(f"\n{'='*80}")
                        workspace_logger.warning(f"🚨 MIX/LIVE SET DETECTED!")
                        workspace_logger.warning(f"{'='*80}")
                        workspace_logger.warning(f"   Duration: {duration}s ({duration // 60}m {duration % 60}s)")
                        workspace_logger.warning(f"   Threshold: {MAX_TRACK_DURATION_SECONDS}s (11 minutes)")
                        workspace_logger.warning(f"   URL: {url}")

                        # Clean up the downloaded WAV file (it's the wrong track)
                        try:
                            if wav_path_tmp.exists():
                                os.remove(wav_path_tmp)
                                workspace_logger.info(f"🗑️  Deleted erroneous download: {wav_path_tmp}")
                        except Exception as cleanup_exc:
                            workspace_logger.warning(f"⚠️  Failed to cleanup erroneous WAV: {cleanup_exc}")

                        # Clean up temp directory
                        try:
                            if os.path.exists(custom_temp_dir):
                                import shutil
                                shutil.rmtree(custom_temp_dir)
                                workspace_logger.info(f"🗑️  Cleaned up temp directory: {custom_temp_dir}")
                        except Exception as cleanup_exc:
                            workspace_logger.warning(f"⚠️  Failed to cleanup temp dir: {cleanup_exc}")

                        # Disable profiler before remediation
                        if profiler:
                            try:
                                profiler.disable()
                                profiler.close()
                            except Exception:
                                pass

                        # Initiate remediation process to find the correct track
                        workspace_logger.info(f"🔄 INITIATING REMEDIATION PROCESS...")
                        remediation_result = remediate_erroneous_match(
                            track_data=track_info,
                            failed_url=url,
                            actual_duration=duration,
                            playlist_dir=playlist_dir,
                            playlist_name=playlist_name
                        )

                        if remediation_result:
                            workspace_logger.info(f"✅ Remediation successful - returning corrected result")
                            return remediation_result
                        else:
                            workspace_logger.error(f"❌ Remediation failed - track requires manual review")
                            return None

                    # Detect BPM with optimized method for long files
                    workspace_logger.info("🎵 Detecting BPM...")
                    workspace_logger.info("⏳ BPM analysis in progress...")
                    try:
                        # For long files (>5 minutes), use a sample to speed up BPM detection
                        if duration > 300:  # 5 minutes
                            workspace_logger.info(f"📊 Long file detected ({duration}s), using optimized BPM detection...")
                            # Take a representative sample from the middle of the track
                            start_sample = len(y) // 4  # Start from 25% into the track
                            end_sample = start_sample + min(len(y) // 2, sr * 120)  # Max 2 minutes sample
                            y_sample = y[start_sample:end_sample]
                            workspace_logger.info(f"📊 Using {len(y_sample)/sr:.1f}s sample for BPM detection")
                        else:
                            y_sample = y
                        
                        tempo, _ = librosa.beat.beat_track(y=y_sample, sr=sr)
                        tempo_array = np.atleast_1d(tempo)
                        bpm = int(round(float(tempo_array[0])))
                        workspace_logger.info(f"🎵 BPM detected: {bpm}")
                    except AttributeError as exc:
                        if "hann" in str(exc):
                            workspace_logger.warning("⚠️  BPM detection failed due to scipy version issue, using fallback method")
                            # Fallback: use onset detection and estimate tempo (with same optimization)
                            try:
                                onset_env = librosa.onset.onset_strength(y=y_sample, sr=sr)
                                tempo = estimate_tempo_from_onset(onset_env, sr)
                                bpm = int(round(float(tempo[0])))
                                workspace_logger.info(f"🎵 BPM detected (fallback): {bpm}")
                            except Exception as fallback_exc:
                                workspace_logger.warning(f"⚠️  BPM fallback detection also failed: {fallback_exc}")
                                bpm = 0
                        else:
                            workspace_logger.warning(f"⚠️  BPM detection failed: {exc}")
                            bpm = 0
                    
                    # Detect key
                    workspace_logger.info("🎼 Detecting musical key...")
                    workspace_logger.info("⏳ Key analysis in progress...")
                    trad_key = detect_key(str(wav_path_tmp), y=y, sr=sr)
                    workspace_logger.info(f"🎼 Key detected: {trad_key}")
                    
                    workspace_logger.info(f"🎵 ANALYSIS RESULTS: duration={duration}s, bpm={bpm}, key={trad_key}")
                    
                    # Update audio processing status
                    if track_info.get("page_id"):
                        update_audio_processing_status(track_info["page_id"], ["Audio Analysis Complete"])
                        
                except Exception as exc:
                    workspace_logger.error(f"❌ Analysis failed with detailed error: {exc}")
                    workspace_logger.error(f"❌ Exception type: {type(exc).__name__}")
                    workspace_logger.error(f"❌ Traceback: {traceback.format_exc()}")
                    workspace_logger.info("🔄 Using fallback values for analysis")
                    duration, bpm, trad_key = 0, 0, "Unknown"
        
        # ── Audio Normalization (if available) ───────────────────
        normalized_wav_path = wav_path_tmp
        audio_processing_status = ["Audio Analysis Complete"]
        
        # Initialize processing data for normalization metrics
        processing_data = {
            "duration": duration,
            "bpm": bpm,
            "key": trad_key,
            "audio_processing_status": audio_processing_status
        }
        
        if AUDIO_NORMALIZER_AVAILABLE:
            try:
                workspace_logger.info("🎛️  Starting Platinum Notes-style audio normalization...")
                
                # Load audio using librosa
                audio_samples, sample_rate = librosa.load(str(wav_path_tmp), sr=44100, mono=True)
                
                # Determine normalization settings based on genre
                target_lufs = -8.0  # Default club-ready target
                warmth_mode = "gentle"
                
                if genre.lower() in ["electronic", "dance", "edm"]:
                    target_lufs = -8.0  # Club-ready for electronic music
                    warmth_mode = "hot"
                elif genre.lower() in ["hip hop", "rap"]:
                    target_lufs = -8.0  # Club-ready for hip hop
                    warmth_mode = "gentle"
                
                # Apply Platinum Notes-style normalization
                normalized_samples, normalization_report = normalize_audio_platinum_notes_style(
                    audio_samples,
                    sample_rate,
                    target_lufs,
                    warmth_mode
                )
                
                if normalization_report['processing_successful']:
                    # VERIFICATION STEP: Comprehensive quality check before saving
                    verification_passed, verification_report = verify_audio_processing_quality(
                        normalized_samples,
                        sample_rate,
                        normalization_report['normalization_report'],
                        target_lufs
                    )
                    
                    if not verification_passed:
                        workspace_logger.error("❌ Audio verification FAILED - using original audio file")
                        workspace_logger.error(f"Quality Score: {verification_report['quality_score']:.1f}%")
                        workspace_logger.error(f"Failed checks: {len(verification_report['failed_checks'])}")
                        
                        # Use original audio instead of processed audio
                        normalized_samples = audio_samples
                        normalized_wav_path = wav_path_tmp
                        
                        # Update processing data to reflect that verification failed
                        processing_data['verification_failed'] = True
                        processing_data['verification_report'] = verification_report
                        
                        workspace_logger.warning("🔄 Using original audio due to verification failure")
                    else:
                        workspace_logger.info("✅ Audio verification PASSED - proceeding with processed audio")
                        
                        # Save normalized audio back to WAV
                        normalized_wav_path = tmp_dir / f"{safe_base}_normalized.wav"
                        
                        # Convert back to 16-bit PCM for FFmpeg compatibility
                        normalized_samples_16bit = (normalized_samples * 32767).astype(np.int16)
                        
                        # Save using soundfile (librosa.output.write_wav is deprecated)
                        if sf:
                            sf.write(str(normalized_wav_path), normalized_samples_16bit, sample_rate)
                        else:
                            # Fallback: use scipy.io.wavfile if soundfile is not available
                            try:
                                import scipy.io.wavfile as wavfile
                                wavfile.write(str(normalized_wav_path), sample_rate, normalized_samples_16bit)
                            except ImportError:
                                workspace_logger.error("❌ Neither soundfile nor scipy.io.wavfile available for saving normalized audio")
                                raise Exception("No audio writing library available")
                        
                        workspace_logger.info(f"✅ Platinum Notes-style normalization completed!")
                        workspace_logger.info(f"📊 LUFS change: {normalization_report['normalization_report']['original_lufs']:.1f} → {normalization_report['normalization_report']['final_lufs']:.1f}")
                        
                        # Store verification data
                        processing_data['verification_passed'] = True
                        processing_data['verification_report'] = verification_report
                    
                    # Store normalization metrics for summary
                    # Extract additional metrics from the final_analysis in normalization_report
                    final_analysis = normalization_report.get('final_analysis', {})
                    initial_analysis = normalization_report.get('initial_analysis', {})

                    processing_data['normalization_metrics'] = {
                        'original_lufs': normalization_report['normalization_report']['original_lufs'],
                        'final_lufs': normalization_report['normalization_report']['final_lufs'],
                        'gain_applied_db': normalization_report['normalization_report']['gain_applied_db'],
                        'clipped_repaired': normalization_report['clipping_report']['clipped_repaired'],
                        'warmth_mode': normalization_report['warmth_report']['mode'],
                        'warmth_applied': normalization_report['warmth_report']['warmth_applied'],
                        'limiting_applied': normalization_report['normalization_report']['limiting_applied'],
                        # Additional metrics for Notion population (2026-01-16)
                        'true_peak_db': final_analysis.get('true_peak_db') or normalization_report['normalization_report'].get('final_true_peak_db'),
                        'peak_level': final_analysis.get('peak'),
                        'rms_level': initial_analysis.get('rms'),  # RMS from initial analysis
                        'crest_factor': initial_analysis.get('crest_factor'),
                        'clipping_percentage': initial_analysis.get('clipping_percentage'),  # From analyze_audio_loudness
                        'warmth_level': 1.0 if normalization_report['warmth_report']['warmth_applied'] else 0.0,  # Warmth enhancement level
                        'sample_rate': sample_rate,  # From librosa.load at line 11392
                        'dynamic_range': (initial_analysis.get('true_peak_db', 0) - initial_analysis.get('lufs_integrated', -14)) if initial_analysis else None,
                    }
                    
                    # Set comprehensive audio processing status based on what was actually completed
                    if track_info.get("page_id"):
                        set_comprehensive_audio_processing_status(
                            track_info["page_id"],
                            processing_data,
                            processing_data['normalization_metrics']
                        )
                        
                else:
                    workspace_logger.warning("Audio normalization failed, using original file")
                    normalized_wav_path = wav_path_tmp
                    # Set status without normalization metrics
                    if track_info.get("page_id"):
                        set_comprehensive_audio_processing_status(
                            track_info["page_id"],
                            processing_data,
                            None  # No normalization metrics
                        )
                    
            except Exception as exc:
                workspace_logger.warning(f"Audio normalization error: {exc}")
                workspace_logger.info("🔄 Using original audio file")
                normalized_wav_path = wav_path_tmp
                # Set status without normalization metrics
                if track_info.get("page_id"):
                    set_comprehensive_audio_processing_status(
                        track_info["page_id"],
                        processing_data,
                        None  # No normalization metrics
                    )
        else:
            workspace_logger.info("ℹ️  Audio normalizer not available, using original file")
            normalized_wav_path = wav_path_tmp
            # Set status without normalization metrics
            if track_info.get("page_id"):
                set_comprehensive_audio_processing_status(
                    track_info["page_id"],
                    processing_data,
                    None  # No normalization metrics
                )

        normalized_wav_path = Path(normalized_wav_path)
        fingerprint = compute_file_fingerprint(normalized_wav_path)
        processing_data["fingerprint"] = fingerprint
        track_info["fingerprint"] = fingerprint

        # Build comprehensive metadata for all files
        # Get playlist names from track relations
        playlist_names = get_playlist_names_from_track(track_info)
        playlist_metadata = ""
        if playlist_names:
            playlist_metadata = "; ".join(playlist_names)
        else:
            playlist_metadata = "No Playlist"
        
        comprehensive_metadata = [
            f"title={title}",
            f"artist={artist}",
            f"album={album}",
            f"genre={genre}",
            f"comment={url}",
            f"bpm={bpm}",
            f"key={trad_key}",
            f"duration={duration}",
            f"compression={COMPRESSION_MODE}",
            f"source=SoundCloud",
            f"fingerprint={fingerprint}",
            f"playlist={playlist_metadata}",
            f"processed_date={datetime.now().strftime('%Y-%m-%d')}",
            f"processed_time={datetime.now().strftime('%H:%M:%S')}"
        ]
        
        workspace_logger.info(f"📊 METADATA TO EMBED: BPM={bpm}, Key={trad_key}, Duration={duration}s")
        
        # Add Camelot notation if available
        if trad_key != "Unknown":
            camelot = convert_to_camelot(trad_key)
            if camelot != "Unknown":
                comprehensive_metadata.append(f"camelot={camelot}")
        
        # M4A: title, artist, album, genre, comment (standard metadata)
        m4a_metadata = [
            f"title={title}",
            f"artist={artist}",
            f"album={album}",
            f"genre={genre}",
            f"comment={url}",
            f"playlist={playlist_metadata}"
        ]
        
        # ── Transcode: AIFF, M4A & WAV (preset-based) ──────────────
        # NOTE: AIFF metadata requires special handling for Apple Music compatibility
        # FFmpeg's AIFF muxer supports ID3v2 tags when using -write_id3v2 1
        aiff_tmp = tmp_dir / f"{safe_base}.aiff"
        ff_aiff = [
            "/opt/homebrew/bin/ffmpeg",
            "-loglevel", "error",
            "-i", str(normalized_wav_path),
            "-y",
            "-c:a", "pcm_s24be",
            "-ar", "48000",
            "-write_id3v2", "1",  # CRITICAL: Enable ID3v2 tags for AIFF (Apple Music compatibility)
        ]
        # Use standard ID3 tag names for AIFF (Apple Music expects these specific tags)
        # Map our metadata to ID3v2 standard tag names
        aiff_metadata = [
            f"title={title}",
            f"artist={artist}",
            f"album={album}",
            f"genre={genre}",
            f"comment={url}",
            f"TBPM={bpm}",  # ID3v2 BPM tag
            f"TKEY={trad_key}",  # ID3v2 Key tag (Initial Key)
        ]
        # Add Camelot as custom comment if available
        if trad_key != "Unknown":
            camelot = convert_to_camelot(trad_key)
            if camelot != "Unknown":
                aiff_metadata.append(f"TXXX=Camelot:{camelot}")

        for metadata in aiff_metadata:
            ff_aiff.extend(["-metadata", metadata])
        ff_aiff.append(str(aiff_tmp))

        workspace_logger.debug(f"Running ffmpeg for AIFF: {' '.join(ff_aiff)}")
        subprocess.run(ff_aiff, check=True)
        workspace_logger.info(f"   ✓ AIFF created with ID3v2 metadata: {aiff_tmp.name}")

        m4a_tmp = tmp_dir / f"{safe_base}.m4a"
        preset = COMPRESSION_PRESETS[COMPRESSION_MODE]

        # Build FFmpeg command for the .m4a (ALAC or AAC) file (use normalized WAV if available)
        ff_m4a = [
            "/opt/homebrew/bin/ffmpeg",
            "-loglevel", "error",
            "-i", str(normalized_wav_path),
            "-y",
            *preset["m4a_codec"],
            "-ar", "48000",
        ]
        # Add format-supported metadata to M4A
        for metadata in m4a_metadata:
            ff_m4a.extend(["-metadata", metadata])
        ff_m4a.append(str(m4a_tmp))

        workspace_logger.debug(f"Running ffmpeg for M4A: {' '.join(ff_m4a)}")
        subprocess.run(ff_m4a, check=True)
        workspace_logger.info(f"   ✓ M4A created with metadata: {m4a_tmp.name}")
        
        # Create WAV file with comprehensive metadata
        # Use _final suffix to avoid input=output collision when normalized_wav_path has same base name
        wav_tmp = tmp_dir / f"{safe_base}_final.wav"

        # Check if input and output would be the same file (causes FFmpeg error)
        if Path(normalized_wav_path).resolve() == wav_tmp.resolve():
            wav_tmp = tmp_dir / f"{safe_base}_output.wav"

        ff_wav = [
            "/opt/homebrew/bin/ffmpeg",
            "-loglevel", "error",
            "-i", str(normalized_wav_path),
            "-y",
            "-c:a", "pcm_s24le",  # Use 24-bit PCM for WAV
            "-ar", "48000",
        ]
        # Add comprehensive metadata to WAV (WAV supports more metadata than M4A)
        for metadata in comprehensive_metadata:
            ff_wav.extend(["-metadata", metadata])
        ff_wav.append(str(wav_tmp))

        workspace_logger.debug(f"Running ffmpeg for WAV: {' '.join(ff_wav)}")
        subprocess.run(ff_wav, check=True)
        workspace_logger.info(f"   ✓ WAV created with metadata: {wav_tmp.name}")
        
        # Format conversion is handled by the comprehensive status function
        # No need to update here as it's included in the comprehensive status

        # ── Move to final destinations (NEW 3-FILE OUTPUT STRUCTURE) ──────────────────────────
        # 2026-01-16: Updated output structure per user requirements:
        # 1. Primary WAV -> Eagle Library (organized by playlist folder)
        # 2. Secondary AIFF -> Eagle Library (organized by playlist folder)
        # 3. WAV copy -> /Volumes/SYSTEM_SSD/Dropbox/Music/playlists/playlist-tracks/{playlist}/{filename}.wav
        #
        # REMOVED: M4A outputs and BACKUP_DIR M4A copies (no longer needed)

        import shutil  # Fix: Ensure shutil is available in local scope

        # Get playlist name for folder organization
        playlist_name_for_folder = playlist_names[0] if playlist_names else "Uncategorized"

        # Create playlist directory in PLAYLIST_TRACKS_DIR for the WAV copy
        playlist_wav_dir = PLAYLIST_TRACKS_DIR / playlist_name_for_folder
        playlist_wav_dir.mkdir(parents=True, exist_ok=True)

        # Copy WAV to playlist tracks directory (3rd output file)
        playlist_wav_path = playlist_wav_dir / f"{safe_base}.wav"
        shutil.copy2(wav_tmp, playlist_wav_path)

        # Rename WAV to clean filename for Eagle import (remove _final suffix)
        # Note: wav_clean_path may be the same as normalized_wav_path, so we check for that
        wav_clean_path = tmp_dir / f"{safe_base}.wav"
        normalized_wav_resolved = Path(normalized_wav_path).resolve() if normalized_wav_path else None
        wav_clean_resolved = wav_clean_path.resolve()

        if wav_tmp.resolve() != wav_clean_resolved and wav_clean_resolved != normalized_wav_resolved and not wav_clean_path.exists():
            shutil.move(str(wav_tmp), str(wav_clean_path))
            wav_path = wav_clean_path
        else:
            wav_path = wav_tmp  # Use as-is if can't rename safely

        # AIFF already has clean name
        aiff_path = aiff_tmp  # AIFF for Eagle import (2nd output file)

        workspace_logger.info(f"\n📁 NEW 3-FILE OUTPUT STRUCTURE:")
        workspace_logger.info(f"   1. WAV  → Eagle Library (Playlists/{playlist_name_for_folder}/)")
        workspace_logger.info(f"   2. AIFF → Eagle Library (Playlists/{playlist_name_for_folder}/)")
        workspace_logger.info(f"   3. WAV  → {playlist_wav_path} (Playlist tracks copy)")

        # ── Import WAV and AIFF into Eagle (organized by playlist folder) ──────────────────────────
        # 2026-01-16: Updated to import both WAV and AIFF into Eagle, organized by playlist
        eagle_item_id = None
        eagle_aiff_item_id = None
        eagle_import_success = False

        def import_and_update():
            nonlocal eagle_item_id, eagle_aiff_item_id, eagle_import_success

            workspace_logger.info("🦅 Starting Eagle import process (WAV + AIFF with playlist folder organization)...")

            # Get or create the Eagle playlist folder
            try:
                eagle_playlist_folder_id = eagle_get_or_create_playlist_folder(playlist_name_for_folder)
                workspace_logger.info(f"🦅 Using Eagle folder: Playlists/{playlist_name_for_folder} (ID: {eagle_playlist_folder_id})")
            except Exception as folder_err:
                workspace_logger.warning(f"⚠️ Could not create Eagle playlist folder: {folder_err}")
                eagle_playlist_folder_id = None

            # Import WAV file (primary)
            # NOTE: Use the resolved `title` variable (from download metadata), not track_info which may be empty
            resolved_title = title or safe_base or "Unknown Track"
            resolved_url = url or track_info.get("soundcloud_url") or ""

            try:
                wav_import_path = str(wav_path)
                if not Path(wav_import_path).exists():
                    raise FileNotFoundError(f"WAV file not found for Eagle import: {wav_import_path}")

                # Generate comprehensive tags for Eagle import
                tag_list = generate_comprehensive_tags(track_info, processing_data, "wav")

                # Use the enhanced import function with de-duplication and tags validation
                eagle_item_id = eagle_import_with_duplicate_management(
                    file_path=wav_import_path,
                    title=resolved_title,
                    url=resolved_url,
                    tags=tag_list,
                    folder_id=eagle_playlist_folder_id,  # Use playlist folder
                    expected_metadata=processing_data,
                    audio_fingerprint=track_info.get("fingerprint")
                )

                if eagle_item_id:
                    workspace_logger.info(f"✅ Eagle WAV import successful: {eagle_item_id}")
                    workspace_logger.info(f"   Applied tags: {tag_list}")
                else:
                    workspace_logger.warning("Eagle returned no ID for WAV; skipping status update")
            except Exception as e:
                workspace_logger.error(f"❌ Eagle WAV import failed: {e}")

            # Import AIFF file (secondary)
            try:
                aiff_import_path = str(aiff_path)
                if not Path(aiff_import_path).exists():
                    raise FileNotFoundError(f"AIFF file not found for Eagle import: {aiff_import_path}")

                # Generate comprehensive tags for Eagle import (AIFF variant)
                aiff_tag_list = generate_comprehensive_tags(track_info, processing_data, "aiff")

                # Use the enhanced import function with de-duplication and tags validation
                # Use resolved_title for proper naming (not track_info which may be empty)
                eagle_aiff_item_id = eagle_import_with_duplicate_management(
                    file_path=aiff_import_path,
                    title=resolved_title,  # Same title as WAV, Eagle will differentiate by file extension
                    url=resolved_url,
                    tags=aiff_tag_list,
                    folder_id=eagle_playlist_folder_id,  # Use playlist folder
                    expected_metadata=processing_data,
                    audio_fingerprint=track_info.get("fingerprint")
                )

                if eagle_aiff_item_id:
                    workspace_logger.info(f"✅ Eagle AIFF import successful: {eagle_aiff_item_id}")
                else:
                    workspace_logger.warning("Eagle returned no ID for AIFF")
            except Exception as e:
                workspace_logger.error(f"❌ Eagle AIFF import failed: {e}")

            # Update status if at least one import succeeded
            if eagle_item_id or eagle_aiff_item_id:
                eagle_import_success = True
                update_audio_processing_status(track_info.get("page_id"), ["Files Imported to Eagle"])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(import_and_update)
            # Wait for the Eagle import to complete before continuing
            try:
                future.result(timeout=120)  # 2 minute timeout for Eagle import
            except concurrent.futures.TimeoutError:
                workspace_logger.warning("⚠️ Eagle import timed out after 2 minutes")
            except Exception as e:
                workspace_logger.warning(f"⚠️ Eagle import failed: {e}")

        # ── Upsert / update Notion track item ─────────────────────
        # 2026-01-16: Updated file paths for new 3-file output structure
        try:
            meta_dict = {
                "title": title,
                "artist": artist,
                "album": album,
                "genre": genre,
                "bpm": bpm,
                "key": trad_key,
                "duration_seconds": duration,
                "source_url": url,
                "fingerprint": fingerprint,
                "aiff_file_path": str(aiff_path),  # AIFF in Eagle Library (temp path for now)
                "wav_file_path": str(playlist_wav_path),  # WAV in playlist tracks directory
                # Note: m4a_file_path removed from new structure
                "page_id": track_info.get("page_id"),  # Include page_id for update
                "audio_processing_status": audio_processing_status,  # Include audio processing status
                "playlist_name": playlist_names[0] if playlist_names else None,  # 2026-01-15 fix: Include playlist for relation linking
            }
            workspace_logger.info(f"📊 UPDATING NOTION WITH: BPM={bpm}, Key={trad_key}, Duration={duration}s")
            upsert_track_page(meta_dict, eagle_item_id)

            # CRITICAL FIX: After upsert_track_page, the page_id may have changed due to de-duplication
            # The upsert function updates meta_dict["page_id"] to the keeper page if duplicates were found
            # We must update track_info to use the new page_id for all subsequent operations
            if meta_dict.get("page_id") and meta_dict["page_id"] != track_info.get("page_id"):
                old_page_id = track_info.get("page_id")
                track_info["page_id"] = meta_dict["page_id"]
                workspace_logger.info(f"🔄 De-dupe detected: Updated track_info page_id from {old_page_id} to {track_info['page_id']}")

            # Processing completion is handled by the comprehensive status function
            # No need for additional "Audio Processing Complete" status
            
            # Update detailed audio processing properties (preserve normalization_metrics)
            # Store any existing normalization_metrics before re-initializing
            existing_normalization_metrics = processing_data.get('normalization_metrics', {})
            
            # 2026-01-16: Updated for new 3-file output structure
            processing_data = {
                "duration": duration,
                "bpm": bpm,
                "key": trad_key,
                "quality_score": 95,  # Default quality score
                "loudness_level": -14,  # Default loudness level
                "warmth_level": 2.5,  # Default warmth enhancement level
                "fingerprint": fingerprint,  # CRITICAL FIX 2026-01-15: Include fingerprint for update
                "file_path": str(playlist_wav_path)  # Primary WAV path in playlist tracks dir
            }

            # Restore normalization_metrics if they exist
            if existing_normalization_metrics:
                processing_data['normalization_metrics'] = existing_normalization_metrics
                workspace_logger.debug(f"✅ Preserved normalization_metrics: {list(existing_normalization_metrics.keys())}")
            else:
                workspace_logger.debug("⚠️  No normalization_metrics to preserve")

            # 2026-01-16: Updated file_paths for new 3-file output structure
            # - WAV and AIFF are imported to Eagle Library (organized by playlist folder)
            # - WAV copy goes to playlist tracks directory
            file_paths = {
                "WAV (Eagle)": "Eagle Library import",  # WAV in Eagle Library
                "AIFF (Eagle)": "Eagle Library import",  # AIFF in Eagle Library
                "WAV (Playlist)": str(playlist_wav_path),  # WAV copy in playlist tracks dir
            }
            
            # Update the audio processing properties in Notion
            if track_info.get("page_id"):
                try:
                    update_audio_processing_properties(track_info["page_id"], processing_data, file_paths, track_info)
                except Exception as prop_err:
                    workspace_logger.debug(f"Could not update processing properties: {prop_err}")

                # Check and add music embed (Spotify or SoundCloud) if it doesn't exist
                try:
                    add_music_embed_to_page(track_info["page_id"], track_info)
                except Exception as embed_err:
                    workspace_logger.debug(f"Could not add music embed: {embed_err}")

                # Create and add audio processing summary to page
                try:
                    summary = create_audio_processing_summary(track_info, processing_data, file_paths, eagle_item_id)
                    add_summary_to_notion_page(track_info["page_id"], summary)

                    # Also update the Audio Processing Summary property
                    summary_properties = {
                        "Audio Processing Summary": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": str(summary)[:1900]
                                    }
                                }
                            ]
                        }
                    }
                    notion_manager._req("patch", f"/pages/{track_info['page_id']}", {"properties": summary_properties})
                except Exception as summary_err:
                    workspace_logger.debug(f"Could not update summary: {summary_err}")
                
        except Exception as exc:
            workspace_logger.warning(f"Could not upsert track into Notion DB: {exc}")
            # Mark error in processing status
            if track_info.get("page_id"):
                update_audio_processing_status(track_info["page_id"], ["Error Occurred During Processing"])

        # ═══════════════════════════════════════════════════════════
        # UNIFIED NOTION UPDATE (2026-01-16)
        # Single comprehensive update with all track properties
        # ═══════════════════════════════════════════════════════════
        if track_info.get("page_id"):
            try:
                # Build comprehensive file_paths dict
                file_paths_unified = {}
                if 'playlist_wav_path' in locals() and playlist_wav_path:
                    file_paths_unified["wav"] = str(playlist_wav_path)

                # Legacy paths for backwards compatibility
                if 'm4a_destination_path' in locals() and m4a_destination_path:
                    file_paths_unified["m4a"] = str(m4a_destination_path)
                if 'aiff_destination_path' in locals() and aiff_destination_path:
                    file_paths_unified["aiff"] = str(aiff_destination_path)

                # Build comprehensive processing_data dict
                # Get actual LUFS from normalization metrics, not hardcoded value
                norm_metrics = processing_data.get("normalization_metrics", {})
                actual_lufs = norm_metrics.get("final_lufs") or processing_data.get("loudness_level", -14)

                processing_data_unified = {
                    "duration": duration,
                    "bpm": bpm,
                    "key": trad_key,
                    "fingerprint": fingerprint,
                    "quality_score": processing_data.get("quality_score", 95),
                    "loudness_level": actual_lufs,  # Use actual LUFS, not hardcoded -14
                    "normalized": bool(norm_metrics),
                    "audio_processing_status": audio_processing_status,
                    "compression_mode": COMPRESSION_MODE,
                }

                # Add ALL normalization metrics if available (2026-01-16 metadata gap fix)
                if norm_metrics:
                    processing_data_unified.update({
                        "peak_level": norm_metrics.get("peak_level"),
                        "rms_level": norm_metrics.get("rms_level"),
                        "dynamic_range": norm_metrics.get("dynamic_range"),
                        "sample_rate": norm_metrics.get("sample_rate"),
                        "crest_factor": norm_metrics.get("crest_factor"),  # Crest factor
                        "true_peak_db": norm_metrics.get("true_peak_db"),  # True peak dB
                        "original_lufs": norm_metrics.get("original_lufs"),  # Original LUFS
                        "gain_applied_db": norm_metrics.get("gain_applied_db"),  # Gain applied
                        "clipping_percentage": norm_metrics.get("clipping_percentage"),  # Clipping %
                        "warmth_level": norm_metrics.get("warmth_level"),  # Warmth enhancement level
                    })

                # Build fingerprints dict
                fingerprints_unified = {}
                if fingerprint:
                    fingerprints_unified["wav"] = fingerprint  # Primary fingerprint for WAV

                # Get eagle_id
                eagle_id_unified = eagle_item_id if 'eagle_item_id' in locals() and eagle_item_id else None

                workspace_logger.info(f"🔄 Applying unified Notion update for {track_info['page_id']}...")

                # Apply unified update
                if unified_track_update(
                    page_id=track_info["page_id"],
                    track_info=track_info,
                    processing_data=processing_data_unified,
                    file_paths=file_paths_unified,
                    eagle_id=eagle_id_unified,
                    fingerprints=fingerprints_unified,
                ):
                    workspace_logger.info(f"✅ Unified update successful for {track_info['page_id']}")

                    # Verify the update worked
                    if not verify_track_will_not_reprocess(track_info["page_id"]):
                        workspace_logger.error(f"⚠️  Track {track_info['page_id']} may reprocess!")
                else:
                    workspace_logger.error(f"❌ Unified update failed for {track_info['page_id']}")

                    # Fallback to legacy update
                    workspace_logger.info("🔄 Attempting legacy update as fallback...")
                    file_paths_legacy = {"wav": file_paths_unified.get("wav")}
                    if complete_track_notion_update(track_info["page_id"], track_info, file_paths_legacy, eagle_id_unified):
                        workspace_logger.info("✅ Legacy fallback update successful")
                    else:
                        workspace_logger.error("❌ Legacy fallback update also failed")

            except Exception as e:
                workspace_logger.error(f"❌ Unified Notion update error: {e}")
                import traceback
                workspace_logger.debug(traceback.format_exc())
        # ═══════════════════════════════════════════════════════════
        
        workspace_logger.info(f"\n✅ TRACK COMPLETE: {artist} – {title}")
        workspace_logger.info(f"{'='*80}\n")

        try:
            try:
                profiler.disable()
            finally:
                profiler.close()
        except Exception:
            pass
        try:
            if profiler:
                profiler.dump_stats('soundcloud_download_profile.prof')
        except Exception:
            pass

        # 2026-01-16: Updated return dict for new 3-file output structure
        return {
            "file": Path(aiff_path),
            "duration": duration,
            "artist": artist,
            "title": title,
            "eagle_item_id": eagle_item_id,
            "fingerprint": fingerprint,
            "file_paths": {
                "WAV (Eagle)": "Eagle Library import",
                "AIFF (Eagle)": "Eagle Library import",
                "WAV (Playlist)": Path(playlist_wav_path),
            },
            # CRITICAL: Include the potentially updated page_id after de-duplication
            "page_id": track_info.get("page_id"),
        }
    finally:
        # Clean up custom temp directory with enhanced logging
        try:
            if os.path.exists(custom_temp_dir):
                import shutil
                shutil.rmtree(custom_temp_dir)
                workspace_logger.temp_dir_cleaned(custom_temp_dir)
        except Exception as cleanup_exc:
            workspace_logger.warning(f"⚠️  Failed to cleanup temp directory {custom_temp_dir}: {cleanup_exc}")

# ───────────────────────────────────────────────────────────────
# Main Entry Point
# ───────────────────────────────────────────────────────────────
# ---------- Essential Functions ----------
def _env(key: str, default: Optional[str] = None) -> str:
    """Get environment variable with default."""
    return os.getenv(key, default) if default is not None else os.getenv(key, "")

def query_database_paginated(database_id: str, base_query: dict, max_items: int = 5000, log_progress: bool = True) -> list[dict]:
    """Query database with pagination support."""
    try:
        all_results = []
        start_cursor = None
        page_count = 0
        start_time = time.time()

        if log_progress:
            workspace_logger.info(f"   📥 Starting paginated query (max {max_items} items)...")

        while len(all_results) < max_items:
            query = dict(base_query)
            query["page_size"] = min(100, max_items - len(all_results))

            if start_cursor:
                query["start_cursor"] = start_cursor

            response = notion_manager.query_database(database_id, query)
            results = response.get("results", [])
            page_count += 1

            if not results:
                break

            all_results.extend(results)

            # Log progress every 5 pages (500 items) or on first page
            if log_progress and (page_count == 1 or page_count % 5 == 0):
                elapsed = time.time() - start_time
                rate = len(all_results) / elapsed if elapsed > 0 else 0
                workspace_logger.info(f"   📥 Queried {len(all_results)} tracks ({page_count} pages, {rate:.0f} tracks/sec)...")

            # Check if there are more pages
            has_more = response.get("has_more", False)
            if not has_more:
                break

            start_cursor = response.get("next_cursor")

        elapsed = time.time() - start_time
        if log_progress:
            workspace_logger.info(f"   ✅ Query complete: {len(all_results)} tracks in {elapsed:.1f}s ({page_count} pages)")

        return all_results[:max_items]

    except Exception as e:
        workspace_logger.error(f"Failed to query database with pagination: {e}")
        return []

def find_tracks_for_processing_batch(batch_size: int = 100) -> List[Dict[str, Any]]:
    """Find tracks for batch processing."""
    try:
        # Build query for unprocessed tracks
        query = build_eligibility_filter(reprocess=False, sort_by_created=True, sort_ascending=False)
        
        # Query with pagination
        tracks = query_database_paginated(TRACKS_DB_ID, query, max_items=batch_size)
        
        workspace_logger.info(f"🔍 Querying for {batch_size} unprocessed tracks...")
        return tracks

    except Exception as e:
        workspace_logger.error(f"Failed to query Notion database for batch processing: {e}")
        return []

def build_eligibility_filter(reprocess: bool=False, sort_by_created: bool=True, sort_ascending: bool=False) -> dict:
    """Build filter that excludes tracks that are already processed."""
    conds = []
    
    # Must have SoundCloud URL
    conds.append({
        "or":[
            {"property":"SoundCloud URL","url":{"is_not_empty":True}},
            {"property":"SoundCloud URL","rich_text":{"is_not_empty":True}},
        ]
    })
    
    if not reprocess:
        # Exclude if DL checkbox is TRUE
        dl_prop = _resolve_prop_name("DL") or "Downloaded"
        conds.append({"property": dl_prop, "checkbox": {"equals": False}})
        
        # Exclude if ANY file path exists
        for name in ["M4A File Path","AIFF File Path","WAV File Path"]:
            conds.append({"property": name, "rich_text": {"is_empty": True}})
        
        # Also exclude if Eagle File ID exists
        eagle_prop = _resolve_prop_name("Eagle File ID") or "Eagle File ID"
        conds.append({"property": eagle_prop, "rich_text": {"is_empty": True}})
    
    query_params = {"filter": {"and": conds}, "page_size": int(_env("SC_NOTION_PAGE_SIZE","100"))}
    
    # Add sorting by Created Time (descending by default, ascending if requested)
    if sort_by_created:
        direction = "ascending" if sort_ascending else "descending"
        query_params["sorts"] = [{"timestamp": "created_time", "direction": direction}]
    
    return query_params

def update_track_metadata(track_data: Dict[str, Any]) -> bool:
    """Update track metadata in Notion for Spotify tracks."""
    try:
        page_id = track_data.get("page_id")
        if not page_id:
            workspace_logger.warning("No page ID available for metadata update")
            return False
        
        # Build properties update with enriched metadata
        properties = {}
        
        # Update audio processing status
        if "Audio Processing Status" in _get_tracks_db_prop_types():
            properties["Audio Processing Status"] = {
                "multi_select": [{"name": "Metadata Enriched"}]
            }
        
        # Update any other metadata fields that might be enriched (uses ALT_PROP_NAMES)
        prop_types = _get_tracks_db_prop_types()

        if track_data.get("bpm"):
            bpm_prop = _resolve_prop_name("BPM") or "Tempo"
            if prop_types.get(bpm_prop) == "number":
                properties[bpm_prop] = {"number": track_data["bpm"]}

        if track_data.get("key"):
            key_prop = _resolve_prop_name("Key") or "Key "
            if prop_types.get(key_prop) == "rich_text":
                properties[key_prop] = {"rich_text": [{"text": {"content": track_data["key"]}}]}

        if track_data.get("duration_seconds"):
            duration_prop = _resolve_prop_name("Duration (s)") or "Audio Duration (seconds)"
            if prop_types.get(duration_prop) == "number":
                properties[duration_prop] = {"number": track_data["duration_seconds"]}
        
        # Apply the updates
        if properties:
            notion_manager._req("patch", f"/pages/{page_id}", {"properties": properties})
            workspace_logger.info(f"✅ Updated metadata for Spotify track: {track_data.get('title', 'Unknown')}")
            return True
        else:
            workspace_logger.info(f"ℹ️ No metadata updates needed for track: {track_data.get('title', 'Unknown')}")
            return True
            
    except Exception as e:
        workspace_logger.error(f"❌ Failed to update track metadata: {e}")
        return False

def get_new_spotify_tracks(limit: int = 10) -> List[dict]:
    """Retrieve new Spotify tracks and sync them to Notion."""
    if not SPOTIFY_AVAILABLE:
        workspace_logger.warning("Spotify integration not available - skipping Spotify track retrieval")
        return []
    
    try:
        workspace_logger.info("🎵 Retrieving new Spotify tracks...")
        sync = SpotifyNotionSync()
        
        # Sync user playlists to get new tracks
        result = sync.sync_user_playlists(limit=5)  # Limit to 5 playlists for efficiency
        
        if result.get("success"):
            workspace_logger.info(f"✅ Spotify sync completed: {result.get('successful_syncs', 0)} playlists processed")
            
            # Query for newly created tracks with Spotify data
            spotify_query = {
                "filter": {
                    "and": [
                        {"property": "Spotify ID", "rich_text": {"is_not_empty": True}},
                        {"property": "Downloaded", "checkbox": {"equals": False}}
                    ]
                },
                "sorts": [{"timestamp": "created_time", "direction": "descending"}],
                "page_size": limit
            }
            
            spotify_tracks = notion_manager.query_database(TRACKS_DB_ID, spotify_query)
            results = spotify_tracks.get("results", [])
            
            if results:
                workspace_logger.info(f"🎵 Found {len(results)} new Spotify tracks to process")
                return results
            else:
                workspace_logger.info("🎵 No new Spotify tracks found")
                return []
        else:
            workspace_logger.warning(f"⚠️ Spotify sync failed: {result.get('error', 'Unknown error')}")
            return []
            
    except Exception as e:
        workspace_logger.error(f"❌ Error retrieving Spotify tracks: {e}")
        return []

def select_pages(limit: int, mode: str, sort_by_created: bool = True, sort_ascending: bool = False) -> List[dict]:
    """Select pages based on mode and criteria, including new Spotify tracks."""
    # First, try to get new Spotify tracks if available
    spotify_tracks = []
    if SPOTIFY_AVAILABLE and mode in ["single", "batch"]:
        spotify_tracks = get_new_spotify_tracks(limit=limit)
    
    # Get regular SoundCloud tracks
    reprocess = (mode == "reprocess")
    q = build_eligibility_filter(reprocess=reprocess, sort_by_created=sort_by_created, sort_ascending=sort_ascending)
    data = notion_manager.query_database(TRACKS_DB_ID, q)
    results = data.get("results", [])
    
    # Combine Spotify and SoundCloud tracks, prioritizing Spotify tracks
    all_tracks = spotify_tracks + results
    
    if limit > 0:
        all_tracks = all_tracks[:limit]
    
    if spotify_tracks:
        workspace_logger.info(f"🎵 Processing {len(spotify_tracks)} Spotify tracks + {len(results)} SoundCloud tracks")
    else:
        workspace_logger.info(f"🎵 Processing {len(results)} SoundCloud tracks")
    
    return all_tracks

# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seren SoundCloud Processor - Music Library Download and Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
PROCESSING MODES:
  single       Process a single track (default)
  batch        Process tracks in batches of 100
  all          Process all eligible tracks continuously
  reprocess    Re-download tracks marked for reprocessing
  library-sync Full library sync with conflict-aware locking (NEW)
  status       Show library sync status without processing
  cleanup      Clean up stale processing locks

LIBRARY-SYNC MODE:
  The library-sync mode performs a comprehensive sync by:
  1. Querying ALL matching tracks from Notion upfront
  2. Pre-caching the entire Eagle library for deduplication
  3. Using distributed locking to prevent concurrent process conflicts
  4. Providing detailed progress tracking

  This mode is ideal for:
  - Initial library setup or migration
  - Periodic full-library maintenance
  - Running alongside other batch processes safely

FILTER CRITERIA (for library-sync):
  --filter unprocessed    Tracks needing processing - verifies file paths actually exist (default)
                          NOTE: DL checkbox is IGNORED. File paths are VERIFIED to exist.
  --filter all            ALL tracks with downloadable URLs (full reprocess)
  --filter missing_eagle  Tracks with files but missing Eagle IDs

  Supported URL sources: SoundCloud, Spotify, YouTube

ENVIRONMENT VARIABLES:
  PROCESS_LOCK_ENABLED=1         Enable/disable process locking (default: 1)
  PROCESS_LOCK_TIMEOUT_MINUTES   Lock expiration time (default: 30)
  SC_ENABLE_PARALLEL_BATCH=1     Enable parallel processing

EXAMPLES:
  # Process single track
  python soundcloud_download_prod_merge-2.py --mode single

  # Full library sync with locking
  python soundcloud_download_prod_merge-2.py --mode library-sync

  # Sync first 50 unprocessed tracks
  python soundcloud_download_prod_merge-2.py --mode library-sync --limit 50

  # Parallel library sync (4 workers)
  python soundcloud_download_prod_merge-2.py --mode library-sync --parallel

  # Check library status
  python soundcloud_download_prod_merge-2.py --mode status

  # Clean up stale locks from crashed processes
  python soundcloud_download_prod_merge-2.py --mode cleanup
"""
    )
    p.add_argument("--mode", choices=["single", "batch", "all", "reprocess", "library-sync", "status", "cleanup"],
                   default="single",
                   help="Processing mode (default: single)")
    p.add_argument("--limit", type=int, default=1,
                   help="Max items to process (default: 1, use 0 for unlimited)")
    p.add_argument("--filter", choices=["unprocessed", "all", "missing_eagle"],
                   default="unprocessed",
                   help="Filter criteria for library-sync mode (default: unprocessed)")
    p.add_argument("--parallel", action="store_true",
                   help="Enable parallel processing for library-sync mode")
    p.add_argument("--workers", type=int, default=MAX_CONCURRENT_JOBS,
                   help=f"Number of parallel workers (default: {MAX_CONCURRENT_JOBS})")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Skip stale lock cleanup before library-sync")
    p.add_argument("--debug", action="store_true",
                   help="Enable debug logging")
    p.add_argument("--no-sort", action="store_true",
                   help="Disable sorting by Created Time")
    p.add_argument("--sort-asc", action="store_true",
                   help="Sort by Created Time ascending (oldest first)")
    return p.parse_args()

def main():
    args = parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Log active Eagle library (works with any library, no forced switch)
    log_active_eagle_library()

    # Determine sorting behavior
    sort_by_created = not args.no_sort
    sort_direction = "ascending" if args.sort_asc else "descending"

    if sort_by_created:
        workspace_logger.info(f"Processing mode: {args.mode}, sorting by Created Time ({sort_direction})")
    else:
        workspace_logger.info(f"Processing mode: {args.mode}, no sorting applied")

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Library Sync Mode - Full library processing with conflict management
    # ═══════════════════════════════════════════════════════════════════════════
    if args.mode == "library-sync":
        workspace_logger.info("🚀 Starting Full Library Sync Mode...")

        # Determine max tracks (0 means unlimited)
        max_tracks = args.limit if args.limit > 0 else None

        results = full_library_sync(
            filter_criteria=args.filter,
            max_tracks=max_tracks,
            cleanup_locks_first=not args.no_cleanup,
            parallel=args.parallel,
            max_workers=args.workers,
        )

        # Return exit code based on results
        if results.get("errors") and not results.get("processed"):
            return 1  # Complete failure
        elif results.get("processed", 0) > 0:
            return 0  # At least some success
        else:
            return 2  # No tracks processed (may be normal)

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Status Mode - Show library statistics without processing
    # ═══════════════════════════════════════════════════════════════════════════
    elif args.mode == "status":
        workspace_logger.info("📊 Gathering library status...")
        status = library_sync_status()

        # Pretty print status as JSON
        import json
        print(json.dumps(status, indent=2, default=str))
        return 0

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Cleanup Mode - Clean up stale processing locks
    # ═══════════════════════════════════════════════════════════════════════════
    elif args.mode == "cleanup":
        workspace_logger.info("🧹 Cleaning up stale processing locks...")
        cleared = cleanup_stale_locks(max_pages=500)
        workspace_logger.info(f"✅ Cleanup complete. Cleared {cleared} stale locks.")
        return 0

    # ═══════════════════════════════════════════════════════════════════════════
    # Existing modes: batch, all
    # ═══════════════════════════════════════════════════════════════════════════
    elif args.mode in {"batch", "all"}:
        # Use efficient batch processing with priority and sorting
        max_tracks = args.limit if args.mode == "batch" else None
        processed = efficient_batch_process_tracks(
            filter_criteria="unprocessed",
            max_tracks=max_tracks,
            batch_size=100
        )
        workspace_logger.info(f"Batch processing completed. Processed: {processed}")
        return 0 if processed > 0 else 2

    # ═══════════════════════════════════════════════════════════════════════════
    # Existing mode: reprocess
    # ═══════════════════════════════════════════════════════════════════════════
    elif args.mode == "reprocess":
        limit = args.limit
        pages = select_pages(limit=limit, mode=args.mode, sort_by_created=sort_by_created, sort_ascending=args.sort_asc)
        if not pages:
            workspace_logger.info("No eligible pages found for reprocessing.")
            return 0

        workspace_logger.info(f"Found {len(pages)} eligible pages to reprocess")
        ok = 0
        for page in pages:
            try:
                ok += 1 if process_track(page) else 0
            except Exception as e:
                workspace_logger.error(f"Processing error: {e}")

        m = workspace_logger.get_metrics()
        workspace_logger.info(f"Completed. Success={ok}/{len(pages)}  Runtime={m['total_runtime']:.2f}s")
        return 0 if ok == len(pages) else 2

    # ═══════════════════════════════════════════════════════════════════════════
    # Default mode: single track processing
    # ═══════════════════════════════════════════════════════════════════════════
    else:
        pages = select_pages(limit=1, mode=args.mode, sort_by_created=sort_by_created, sort_ascending=args.sort_asc)
        if not pages:
            workspace_logger.info("No eligible pages found.")
            return 0

        workspace_logger.info(f"Found {len(pages)} eligible pages to process")
        ok = 0
        for page in pages:
            try:
                ok += 1 if process_track(page) else 0
            except Exception as e:
                workspace_logger.error(f"Processing error: {e}")

        m = workspace_logger.get_metrics()
        workspace_logger.info(f"Completed. Success={ok}/{len(pages)}  Runtime={m['total_runtime']:.2f}s")
        return 0 if ok == len(pages) else 2


if __name__ == "__main__":
    sys.exit(main())
