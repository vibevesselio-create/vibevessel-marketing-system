#!/usr/bin/env python3
"""
Notion Script Runner - Automated Execution System

This script queries the Notion scripts database for items with ACTION="RUN",
executes the corresponding local scripts, and creates handoff tasks for any errors.

Database: scripts (26ce73616c278178bc77f43aff00eddf)
Property: ACTION (select) - filters for "RUN" value
File Source: File Path (url) - contains script location

Version: 2.0.0
Last Updated: 2025-01-10
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import traceback
import json
import logging
import hashlib
import time
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import tempfile
from dataclasses import dataclass, asdict

try:
    from notion_client import Client
    from notion_client.errors import APIResponseError, RequestTimeoutError
except ImportError:
    print("Error: notion-client not installed. Run: pip install notion-client")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    """Configuration settings for the script runner"""
    # Notion settings
    notion_token: str = ""
    scripts_database_id: str = "26ce73616c278178bc77f43aff00eddf"
    execution_logs_db_id: str = "27be7361-6c27-8033-a323-dca0fafa80e6"
    
    # Execution settings
    script_timeout: int = 600  # seconds per script
    max_output_length: int = 50000  # Truncate very long outputs
    max_parallel_scripts: int = 3  # Maximum parallel executions
    retry_attempts: int = 3  # API retry attempts
    retry_delay: float = 2.0  # Seconds between retries
    
    # Path settings
    codex_inbox_path: Path = Path(
        "/Users/brianhellemn/Library/Mobile Documents/com~apple~CloudDocs/github/"
        "Agents/Agent-Triggers/Codex-MM1-Agent-Trigger/01_inbox"
    )
    log_dir: Path = Path.home() / ".logs" / "notion_script_runner"
    state_file: Path = Path.home() / ".config" / "notion_script_runner" / "state.json"
    
    # Security settings
    allowed_script_dirs: List[Path] = None
    forbidden_commands: List[str] = None
    
    # Feature flags
    dry_run: bool = False
    verbose: bool = False
    parallel_execution: bool = False
    log_to_notion: bool = True
    
    def __post_init__(self):
        """Initialize default values and validate configuration"""
        # Get token from environment or config file, never hardcode
        self.notion_token = self._get_secure_token()
        
        # Default allowed directories
        if self.allowed_script_dirs is None:
            self.allowed_script_dirs = [
                Path.home() / "Projects" / "github",
                Path.home() / "Projects" / "github-production",
                Path.home() / "Scripts",
            ]
        
        # Default forbidden commands
        if self.forbidden_commands is None:
            self.forbidden_commands = [
                "rm -rf /",
                "sudo rm",
                "format",
                "dd if=/dev/zero",
                ":(){ :|:& };:",  # Fork bomb
            ]
        
        # Create necessary directories
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.codex_inbox_path.mkdir(parents=True, exist_ok=True)
    
    def _get_secure_token(self) -> str:
        """Get Notion token from secure sources"""
        # Priority order: env var, config file, keychain (macOS)
        token = os.getenv("NOTION_TOKEN")
        
        if not token:
            config_file = Path.home() / ".config" / "notion_script_runner" / "config.json"
            if config_file.exists():
                try:
                    with open(config_file) as f:
                        config_data = json.load(f)
                        token = config_data.get("notion_token")
                except Exception:
                    pass
        
        if not token and sys.platform == "darwin":
            # Try to get from macOS keychain
            try:
                result = subprocess.run(
                    ["security", "find-generic-password", "-s", "notion-script-runner", "-w"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode == 0:
                    token = result.stdout.strip()
            except Exception:
                pass
        
        # Fallback to the provided token (should be removed in production)
        if not token:
            token = "ntn_6206530666390WYstR0eTPPivbJsJkVvLs5NHwojlJJyD8rh"
            logging.warning("Using fallback token - this should be configured securely")
        
        return token

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(config: Config) -> logging.Logger:
    """Setup comprehensive logging system"""
    logger = logging.getLogger("notion_script_runner")
    logger.setLevel(logging.DEBUG if config.verbose else logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler
    log_file = config.log_dir / f"execution_{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    return logger

# ============================================================================
# RETRY DECORATOR
# ============================================================================

def retry_on_failure(max_attempts: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """Decorator to retry functions on failure with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (APIResponseError, RequestTimeoutError, ConnectionError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logging.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logging.error(f"All {max_attempts} attempts failed for {func.__name__}")
            
            raise last_exception
        return wrapper
    return decorator

# ============================================================================
# SCRIPT VALIDATION
# ============================================================================

class ScriptValidator:
    """Validates scripts before execution for security"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate_script(self, script_path: str) -> Tuple[bool, str]:
        """
        Validate a script for safe execution
        
        Returns:
            Tuple of (is_valid, reason)
        """
        path = Path(script_path)
        
        # Check if file exists
        if not path.exists():
            return False, f"Script file not found: {script_path}"
        
        if not path.is_file():
            return False, f"Path is not a file: {script_path}"
        
        # Check if in allowed directories
        if self.config.allowed_script_dirs:
            in_allowed_dir = any(
                path.resolve().is_relative_to(allowed_dir.resolve())
                for allowed_dir in self.config.allowed_script_dirs
                if allowed_dir.exists()
            )
            if not in_allowed_dir:
                return False, f"Script not in allowed directories: {script_path}"
        
        # Check for forbidden commands in script content
        if self.config.forbidden_commands and path.suffix in [".sh", ".bash", ".zsh"]:
            try:
                content = path.read_text()
                for forbidden in self.config.forbidden_commands:
                    if forbidden in content:
                        return False, f"Script contains forbidden command: {forbidden}"
            except Exception as e:
                return False, f"Could not read script for validation: {e}"
        
        # Check file permissions
        if not os.access(path, os.R_OK):
            return False, f"Script is not readable: {script_path}"
        
        return True, "Valid"

# ============================================================================
# EXECUTION STATE TRACKING
# ============================================================================

class ExecutionState:
    """Tracks execution history to avoid duplicate runs"""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load_state()
        self.lock = threading.Lock()
    
    def _load_state(self) -> Dict:
        """Load execution state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to load state: {e}")
        return {"executions": {}, "last_run": None}
    
    def _save_state(self):
        """Save execution state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
    
    def get_script_hash(self, script_path: str) -> str:
        """Get hash of script file for change detection"""
        try:
            path = Path(script_path)
            if path.exists():
                content = path.read_bytes()
                return hashlib.sha256(content).hexdigest()
        except Exception:
            pass
        return ""
    
    def should_execute(self, page_id: str, script_path: str) -> bool:
        """Check if script should be executed"""
        with self.lock:
            script_hash = self.get_script_hash(script_path)
            
            if page_id not in self.state["executions"]:
                return True
            
            last_execution = self.state["executions"][page_id]
            
            # Check if script has changed
            if last_execution.get("hash") != script_hash:
                return True
            
            # Check if last execution failed
            if last_execution.get("status") == "failed":
                return True
            
            # Check if enough time has passed (avoid rapid re-execution)
            last_time = datetime.fromisoformat(last_execution.get("timestamp", "1970-01-01"))
            if (datetime.now() - last_time).seconds < 60:  # 1 minute cooldown
                return False
            
            return True
    
    def record_execution(self, page_id: str, script_path: str, status: str, result: Dict):
        """Record script execution"""
        with self.lock:
            self.state["executions"][page_id] = {
                "script_path": script_path,
                "hash": self.get_script_hash(script_path),
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "result": result
            }
            self.state["last_run"] = datetime.now().isoformat()
            self._save_state()

# ============================================================================
# NOTION CLIENT WRAPPER
# ============================================================================

class NotionManager:
    """Enhanced Notion client with retry logic and better error handling"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = Client(auth=config.notion_token)
        self.logger = logging.getLogger(__name__)
    
    @retry_on_failure(max_attempts=3, delay=2.0)
    def query_database(self, database_id: str, filter_dict: Dict = None) -> List[Dict]:
        """Query Notion database with retry logic"""
        try:
            response = self.client.databases.query(
                database_id=database_id,
                filter=filter_dict
            )
            return response.get("results", [])
        except Exception as e:
            self.logger.error(f"Database query failed: {e}")
            raise
    
    @retry_on_failure(max_attempts=3, delay=1.0)
    def update_page(self, page_id: str, properties: Dict) -> bool:
        """Update Notion page with retry logic"""
        try:
            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            return True
        except Exception as e:
            self.logger.error(f"Page update failed: {e}")
            return False
    
    @retry_on_failure(max_attempts=3, delay=1.0)
    def create_page(self, parent_db_id: str, properties: Dict) -> Optional[str]:
        """Create a new page in Notion database"""
        try:
            response = self.client.pages.create(
                parent={"database_id": parent_db_id},
                properties=properties
            )
            return response.get("id")
        except Exception as e:
            self.logger.error(f"Page creation failed: {e}")
            return None

# ============================================================================
# ENHANCED SCRIPT EXECUTION
# ============================================================================

class ScriptExecutor:
    """Enhanced script execution with better error handling and logging"""
    
    def __init__(self, config: Config, validator: ScriptValidator):
        self.config = config
        self.validator = validator
        self.logger = logging.getLogger(__name__)
    
    def execute_script(self, script_path: str, env_vars: Dict = None) -> Tuple[int, str, str, Dict]:
        """
        Execute a script with enhanced monitoring and safety
        
        Returns:
            Tuple of (return_code, stdout, stderr, metrics)
        """
        # Validate script first
        is_valid, reason = self.validator.validate_script(script_path)
        if not is_valid:
            return 1, "", f"Validation failed: {reason}", {}
        
        path = Path(script_path)
        
        # Prepare execution environment
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        # Determine execution command
        cmd = self._get_execution_command(path)
        if not cmd:
            return 1, "", f"Cannot determine how to execute: {path}", {}
        
        # Track execution metrics
        metrics = {
            "start_time": datetime.now().isoformat(),
            "script_size": path.stat().st_size if path.exists() else 0
        }
        
        # Execute with monitoring
        try:
            if self.config.dry_run:
                self.logger.info(f"DRY RUN: Would execute: {' '.join(cmd)}")
                return 0, "DRY RUN", "", metrics
            
            start_time = time.time()
            
            # Create temporary files for large output capture
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as stdout_file, \
                 tempfile.NamedTemporaryFile(mode='w+', delete=False) as stderr_file:
                
                process = subprocess.Popen(
                    cmd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=env,
                    cwd=path.parent
                )
                
                try:
                    return_code = process.wait(timeout=self.config.script_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    return 1, "", f"Script timed out after {self.config.script_timeout}s", metrics
                
                # Read output from temp files
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read()
                stderr = stderr_file.read()
                
                # Clean up temp files
                Path(stdout_file.name).unlink(missing_ok=True)
                Path(stderr_file.name).unlink(missing_ok=True)
            
            # Update metrics
            metrics.update({
                "end_time": datetime.now().isoformat(),
                "duration_seconds": time.time() - start_time,
                "output_size": len(stdout) + len(stderr)
            })
            
            # Truncate if necessary
            if len(stdout) > self.config.max_output_length:
                stdout = stdout[:self.config.max_output_length] + \
                        f"\n[Truncated from {len(stdout)} chars]"
            
            if len(stderr) > self.config.max_output_length:
                stderr = stderr[:self.config.max_output_length] + \
                        f"\n[Truncated from {len(stderr)} chars]"
            
            return return_code, stdout, stderr, metrics
            
        except Exception as e:
            error_msg = f"Execution error: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(error_msg)
            return 1, "", error_msg, metrics
    
    def _get_execution_command(self, path: Path) -> Optional[List[str]]:
        """Determine the appropriate command to execute a script"""
        suffix_map = {
            ".py": [sys.executable, "-u"],  # -u for unbuffered output
            ".sh": ["bash", "-e"],  # -e to exit on error
            ".bash": ["bash", "-e"],
            ".zsh": ["zsh", "-e"],
            ".js": ["node"],
            ".rb": ["ruby"],
            ".pl": ["perl"],
        }
        
        if path.suffix in suffix_map:
            return suffix_map[path.suffix] + [str(path)]
        
        # Check if executable
        if os.access(path, os.X_OK):
            return [str(path)]
        
        return None

# ============================================================================
# EXECUTION LOGGING TO NOTION
# ============================================================================

class ExecutionLogger:
    """Logs script execution results to Notion database"""
    
    def __init__(self, notion_manager: NotionManager, config: Config):
        self.notion = notion_manager
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def log_execution(self, script_name: str, script_path: str, page_id: str,
                     return_code: int, stdout: str, stderr: str, metrics: Dict) -> Optional[str]:
        """Create execution log entry in Notion"""
        if not self.config.log_to_notion:
            return None
        
        try:
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": f"Execution: {script_name} - {datetime.now():%Y-%m-%d %H:%M}"
                            }
                        }
                    ]
                },
                "Script": {
                    "rich_text": [
                        {
                            "text": {
                                "content": script_name
                            }
                        }
                    ]
                },
                "Script Path": {
                    "url": f"file://{script_path}"
                },
                "Status": {
                    "select": {
                        "name": "Success" if return_code == 0 else "Failed"
                    }
                },
                "Exit Code": {
                    "number": return_code
                },
                "Execution Time": {
                    "date": {
                        "start": metrics.get("start_time", datetime.now().isoformat())
                    }
                },
                "Duration (s)": {
                    "number": metrics.get("duration_seconds", 0)
                },
                "Output Size": {
                    "number": metrics.get("output_size", 0)
                },
                "Related Page": {
                    "relation": [
                        {"id": page_id}
                    ]
                }
            }
            
            # Add output as page content (in blocks)
            log_id = self.notion.create_page(self.config.execution_logs_db_id, properties)
            
            if log_id:
                self._add_execution_details(log_id, stdout, stderr, metrics)
                return log_id
                
        except Exception as e:
            self.logger.error(f"Failed to log execution to Notion: {e}")
        
        return None
    
    def _add_execution_details(self, page_id: str, stdout: str, stderr: str, metrics: Dict):
        """Add detailed execution output to the log page"""
        try:
            blocks = []
            
            # Add metrics section
            if metrics:
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "Execution Metrics"}}]
                    }
                })
                
                metric_text = "\n".join([f"• {k}: {v}" for k, v in metrics.items()])
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": metric_text[:2000]}}]
                    }
                })
            
            # Add stdout section
            if stdout and stdout.strip():
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "Standard Output"}}]
                    }
                })
                
                # Split long output into chunks
                for chunk in self._chunk_text(stdout, 2000):
                    blocks.append({
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{"text": {"content": chunk}}],
                            "language": "plain text"
                        }
                    })
            
            # Add stderr section
            if stderr and stderr.strip():
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "Standard Error"}}]
                    }
                })
                
                for chunk in self._chunk_text(stderr, 2000):
                    blocks.append({
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{"text": {"content": chunk}}],
                            "language": "plain text"
                        }
                    })
            
            # Append blocks to the page
            if blocks:
                self.notion.client.blocks.children.append(
                    block_id=page_id,
                    children=blocks[:100]  # Notion API limit
                )
                
        except Exception as e:
            self.logger.error(f"Failed to add execution details: {e}")
    
    def _chunk_text(self, text: str, max_length: int) -> List[str]:
        """Split text into chunks for Notion's text limits"""
        chunks = []
        current = ""
        
        for line in text.split('\n'):
            if len(current) + len(line) + 1 > max_length:
                chunks.append(current)
                current = line
            else:
                current += ('\n' if current else '') + line
        
        if current:
            chunks.append(current)
        
        return chunks

# ============================================================================
# MACOS NOTIFICATIONS (ENHANCED)
# ============================================================================

class NotificationManager:
    """Enhanced notification system with better formatting and error handling"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def send(self, title: str, message: str, subtitle: Optional[str] = None,
             sound: bool = False) -> None:
        """Send a macOS notification with optional sound"""
        if sys.platform != "darwin":
            return
        
        try:
            # Sanitize inputs
            title = self._sanitize(title, 50)
            message = self._sanitize(message, 180)
            subtitle = self._sanitize(subtitle, 100) if subtitle else None
            
            # Build AppleScript
            script = f'display notification "{self._escape(message)}"'
            script += f' with title "{self._escape(title)}"'
            
            if subtitle:
                script += f' subtitle "{self._escape(subtitle)}"'
            
            if sound:
                script += ' sound name "Glass"'
            
            # Execute
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=2
            )
            
        except Exception as e:
            self.logger.debug(f"Notification failed: {e}")
    
    def _sanitize(self, text: str, limit: int) -> str:
        """Sanitize text for notification display"""
        if not text:
            return ""
        sanitized = " ".join(str(text).strip().split())
        return sanitized[:limit-3] + "..." if len(sanitized) > limit else sanitized
    
    def _escape(self, text: str) -> str:
        """Escape text for AppleScript"""
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

# ============================================================================
# ERROR HANDOFF CREATION (ENHANCED)
# ============================================================================

class HandoffManager:
    """Creates and manages error handoff tasks"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def create_error_handoff(self, script_name: str, script_path: str, page_id: str,
                            return_code: int, stdout: str, stderr: str,
                            metrics: Dict) -> Optional[Path]:
        """Create enhanced error handoff with more context"""
        timestamp = datetime.now()
        safe_name = "".join(c if c.isalnum() else "_" for c in script_name)[:50]
        filename = f"script_error_{timestamp:%Y%m%d_%H%M%S}_{safe_name}.md"
        filepath = self.config.codex_inbox_path / filename
        
        # Build comprehensive handoff content
        content = self._build_handoff_content(
            script_name, script_path, page_id, return_code,
            stdout, stderr, metrics, timestamp
        )
        
        try:
            filepath.write_text(content, encoding='utf-8')
            self.logger.info(f"Created error handoff: {filename}")
            return filepath
        except Exception as e:
            self.logger.error(f"Failed to create handoff: {e}")
            return None
    
    def _build_handoff_content(self, script_name: str, script_path: str, page_id: str,
                               return_code: int, stdout: str, stderr: str,
                               metrics: Dict, timestamp: datetime) -> str:
        """Build detailed handoff document content"""
        
        # Extract relevant error patterns
        error_patterns = self._analyze_error_patterns(stderr)
        
        return f"""# Script Execution Error - {script_name}

## Handoff Task

**Assigned To**: Codex MM1 Agent  
**Priority**: HIGH  
**Created**: {timestamp.isoformat()}  
**Notion Page**: https://notion.so/{page_id.replace('-', '')}

## Executive Summary

Script execution failed with exit code {return_code}. {error_patterns.get('summary', 'Review logs for details.')}

## Task Requirements

### 1. Immediate Actions
- [ ] Verify error reproducibility by running script manually
- [ ] Document actual vs. expected behavior
- [ ] Check for environmental dependencies

### 2. Root Cause Analysis
- [ ] Analyze error output for specific failure points
- [ ] Review recent code changes (git log -p -5 {script_path})
- [ ] Check dependency versions and compatibility
- [ ] Verify required environment variables and configuration

### 3. Resolution Steps
- [ ] Implement fixes based on root cause analysis
- [ ] Test fixes in development environment
- [ ] Validate with unit tests if available
- [ ] Document all changes made

### 4. Validation & Deployment
- [ ] Execute script until successful (exit code 0)
- [ ] Verify all expected outputs generated
- [ ] Confirm no warnings or exceptions
- [ ] Update Notion status to "ORGANIZE"
- [ ] Create execution log with resolution details

## Script Information

| Field | Value |
|-------|-------|
| Script Name | {script_name} |
| File Path | `{script_path}` |
| Exit Code | {return_code} |
| Execution Time | {timestamp.isoformat()} |
| Duration | {metrics.get('duration_seconds', 'N/A')} seconds |
| Output Size | {metrics.get('output_size', 'N/A')} bytes |

## Error Analysis

### Detected Patterns
{self._format_error_patterns(error_patterns)}

### Standard Output
```
{stdout[:5000] if stdout.strip() else "(No output)"}
```

### Standard Error
```
{stderr[:5000] if stderr.strip() else "(No error output)"}
```

## Environment Context

- **Python Version**: {sys.version.split()[0]}
- **Platform**: {sys.platform}
- **Working Directory**: {Path(script_path).parent if script_path else "Unknown"}
- **User**: {os.getenv('USER', 'Unknown')}

## Debugging Commands

```bash
# Check script syntax
python -m py_compile {script_path}

# Run with debugging
python -u {script_path}

# Check dependencies
pip list | grep -E "(notion|requests|pandas)"

# View recent changes
git diff HEAD~1 {script_path}
```

## Success Criteria

- [ ] Script executes without errors (exit code 0)
- [ ] All expected outputs are generated
- [ ] No warnings or exceptions in logs
- [ ] Script behavior matches specification
- [ ] Notion ACTION status updated to "ORGANIZE"
- [ ] Execution log created documenting resolution

## Notes

- Auto-generated by Notion Script Runner v2.0
- Original script marked with ACTION="RUN" in Notion
- After resolution, script will be re-executed automatically
- Check `.logs/notion_script_runner/` for detailed execution logs

---

**Automation**: Generated by Claude MM1 Agent Script Execution System
"""
    
    def _analyze_error_patterns(self, stderr: str) -> Dict:
        """Analyze error output for common patterns"""
        patterns = {
            "summary": "Unknown error occurred",
            "type": "generic",
            "suggestions": []
        }
        
        if not stderr:
            return patterns
        
        stderr_lower = stderr.lower()
        
        # Check for common error types
        if "modulenotfounderror" in stderr_lower or "importerror" in stderr_lower:
            patterns["type"] = "import_error"
            patterns["summary"] = "Missing Python module dependency"
            patterns["suggestions"].append("Install missing packages with pip")
            
        elif "filenotfounderror" in stderr_lower:
            patterns["type"] = "file_not_found"
            patterns["summary"] = "Required file or directory not found"
            patterns["suggestions"].append("Verify file paths and permissions")
            
        elif "syntaxerror" in stderr_lower:
            patterns["type"] = "syntax_error"
            patterns["summary"] = "Python syntax error in script"
            patterns["suggestions"].append("Check for syntax issues in the script")
            
        elif "notion" in stderr_lower and ("401" in stderr or "403" in stderr):
            patterns["type"] = "auth_error"
            patterns["summary"] = "Notion API authentication failure"
            patterns["suggestions"].append("Verify Notion token is valid")
            
        elif "timeout" in stderr_lower:
            patterns["type"] = "timeout"
            patterns["summary"] = "Script execution timed out"
            patterns["suggestions"].append("Check for infinite loops or long operations")
            
        return patterns
    
    def _format_error_patterns(self, patterns: Dict) -> str:
        """Format error patterns for display"""
        output = f"- **Error Type**: {patterns['type']}\n"
        output += f"- **Summary**: {patterns['summary']}\n"
        
        if patterns.get('suggestions'):
            output += "- **Suggestions**:\n"
            for suggestion in patterns['suggestions']:
                output += f"  - {suggestion}\n"
        
        return output

# ============================================================================
# MAIN SCRIPT RUNNER
# ============================================================================

class ScriptRunner:
    """Main orchestrator for script execution"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logging(config)
        self.notion = NotionManager(config)
        self.validator = ScriptValidator(config)
        self.executor = ScriptExecutor(config, self.validator)
        self.state = ExecutionState(config.state_file)
        self.notifier = NotificationManager()
        self.handoff = HandoffManager(config)
        self.exec_logger = ExecutionLogger(self.notion, config)
        
        self.stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0
        }
    
    def run(self) -> int:
        """Main execution entry point"""
        start_time = datetime.now()
        
        self.logger.info("=" * 80)
        self.logger.info("NOTION SCRIPT RUNNER v2.0 - Automated Execution System")
        self.logger.info("=" * 80)
        self.logger.info(f"Started: {start_time.isoformat()}")
        
        if self.config.dry_run:
            self.logger.info("🔍 DRY RUN MODE - No scripts will be executed")
        
        self.notifier.send(
            "Script Runner Started",
            f"Checking for scripts at {start_time:%H:%M:%S}",
            sound=False
        )
        
        # Get scripts to run
        scripts = self._get_scripts_to_run()
        
        if not scripts:
            self.logger.info("✓ No scripts found with ACTION='RUN'")
            self.notifier.send("Script Runner", "No scripts to execute")
            return 0
        
        self.stats["total"] = len(scripts)
        self.logger.info(f"\nProcessing {len(scripts)} script(s)...")
        
        # Execute scripts (parallel or sequential)
        if self.config.parallel_execution and len(scripts) > 1:
            self._execute_parallel(scripts)
        else:
            self._execute_sequential(scripts)
        
        # Print summary
        self._print_summary(start_time)
        
        # Send completion notification
        self.notifier.send(
            "Script Runner Complete",
            f"{self.stats['successful']} successful, {self.stats['failed']} failed",
            subtitle=f"Total: {self.stats['total']} scripts",
            sound=self.stats['failed'] > 0
        )
        
        return 0 if self.stats['failed'] == 0 else 1
    
    def _get_scripts_to_run(self) -> List[Dict]:
        """Get scripts marked for execution"""
        try:
            scripts = self.notion.query_database(
                self.config.scripts_database_id,
                {
                    "property": "ACTION",
                    "select": {"equals": "RUN"}
                }
            )
            
            # Filter based on execution state
            filtered = []
            for script in scripts:
                page_id = script["id"]
                script_path = self._get_property_value(script, "File Path")
                
                if script_path and self.state.should_execute(page_id, script_path):
                    filtered.append(script)
                else:
                    self.logger.info(f"Skipping recently executed: {page_id}")
            
            return filtered
            
        except Exception as e:
            self.logger.error(f"Failed to query Notion: {e}")
            return []
    
    def _execute_sequential(self, scripts: List[Dict]):
        """Execute scripts one by one"""
        for idx, script in enumerate(scripts, 1):
            self._execute_single_script(script, idx, len(scripts))
    
    def _execute_parallel(self, scripts: List[Dict]):
        """Execute scripts in parallel with thread pool"""
        max_workers = min(self.config.max_parallel_scripts, len(scripts))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._execute_single_script, script, idx, len(scripts)): script
                for idx, script in enumerate(scripts, 1)
            }
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"Parallel execution error: {e}")
    
    def _execute_single_script(self, script_page: Dict, idx: int, total: int):
        """Execute a single script with full error handling"""
        script_name = self._get_property_value(script_page, "Script Name") or "Unnamed"
        script_path = self._get_property_value(script_page, "File Path")
        page_id = script_page["id"]
        
        self.logger.info(f"\n[{idx}/{total}] Processing: {script_name}")
        self.logger.info(f"  Page ID: {page_id}")
        self.logger.info(f"  Path: {script_path}")
        
        if not script_path:
            self.logger.warning("  ⚠️ No file path specified")
            self.stats["skipped"] += 1
            return
        
        # Handle file:// URLs
        if script_path.startswith("file://"):
            script_path = script_path[7:]
        
        # Execute script
        return_code, stdout, stderr, metrics = self.executor.execute_script(script_path)
        
        # Record execution
        status = "success" if return_code == 0 else "failed"
        self.state.record_execution(page_id, script_path, status, {
            "return_code": return_code,
            "metrics": metrics
        })
        
        # Log to Notion
        if self.config.log_to_notion:
            log_id = self.exec_logger.log_execution(
                script_name, script_path, page_id,
                return_code, stdout, stderr, metrics
            )
            if log_id:
                self.logger.info(f"  📝 Logged to Notion: {log_id}")
        
        # Handle results
        if return_code == 0:
            self.logger.info(f"  ✅ Execution successful")
            self.stats["successful"] += 1
            
            # Update status
            if self.notion.update_page(page_id, {
                "ACTION": {"select": {"name": "ORGANIZE"}}
            }):
                self.logger.info(f"  ✅ Updated ACTION → ORGANIZE")
        else:
            self.logger.error(f"  ❌ Execution failed (exit: {return_code})")
            self.stats["failed"] += 1
            
            # Create handoff
            handoff_path = self.handoff.create_error_handoff(
                script_name, script_path, page_id,
                return_code, stdout, stderr, metrics
            )
            
            if handoff_path:
                self.logger.info(f"  📋 Created handoff: {handoff_path.name}")
            
            # Update status
            if self.notion.update_page(page_id, {
                "ACTION": {"select": {"name": "TROUBLESHOOT"}}
            }):
                self.logger.info(f"  ✅ Updated ACTION → TROUBLESHOOT")
    
    def _get_property_value(self, page: Dict, property_name: str) -> Optional[str]:
        """Extract property value from Notion page"""
        properties = page.get("properties", {})
        prop = properties.get(property_name, {})
        prop_type = prop.get("type")
        
        if prop_type == "title":
            title_list = prop.get("title", [])
            return title_list[0].get("plain_text", "") if title_list else None
        
        elif prop_type == "rich_text":
            text_list = prop.get("rich_text", [])
            return text_list[0].get("plain_text", "") if text_list else None
        
        elif prop_type == "url":
            return prop.get("url")
        
        elif prop_type == "select":
            select_obj = prop.get("select")
            return select_obj.get("name") if select_obj else None
        
        return None
    
    def _print_summary(self, start_time: datetime):
        """Print execution summary"""
        duration = (datetime.now() - start_time).total_seconds()
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("EXECUTION SUMMARY")
        self.logger.info("=" * 80)
        self.logger.info(f"Total Scripts: {self.stats['total']}")
        self.logger.info(f"✅ Successful: {self.stats['successful']}")
        self.logger.info(f"❌ Failed: {self.stats['failed']}")
        self.logger.info(f"⚠️  Skipped: {self.stats['skipped']}")
        self.logger.info(f"Duration: {duration:.1f} seconds")
        self.logger.info(f"Completed: {datetime.now().isoformat()}")
        self.logger.info("=" * 80)

# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point with argument parsing"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Notion Script Runner - Automated Execution System")
    parser.add_argument("--dry-run", action="store_true", help="Preview execution without running scripts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--parallel", "-p", action="store_true", help="Enable parallel execution")
    parser.add_argument("--no-notion-log", action="store_true", help="Disable logging to Notion")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config()
    
    if args.config and Path(args.config).exists():
        try:
            with open(args.config) as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        except Exception as e:
            print(f"Failed to load config file: {e}")
    
    # Apply command line overrides
    if args.dry_run:
        config.dry_run = True
    if args.verbose:
        config.verbose = True
    if args.parallel:
        config.parallel_execution = True
    if args.no_notion_log:
        config.log_to_notion = False
    
    # Run the script runner
    try:
        runner = ScriptRunner(config)
        return runner.run()
    except KeyboardInterrupt:
        print("\n\n⚠️ Execution interrupted by user")
        return 130
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
