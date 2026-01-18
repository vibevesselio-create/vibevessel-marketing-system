#!/usr/bin/env python3
"""
Unified Google Apps Script Deployment Module
=============================================

Provides a unified interface for deploying GAS projects with:
- Primary: Google Apps Script API (direct, programmatic)
- Fallback: clasp CLI (when API fails or for legacy operations)

This module should be imported for ALL GAS deployment operations.

Author: Claude Code Agent
Created: 2026-01-18
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Default credentials path
DEFAULT_CREDENTIALS_PATH = Path("/Users/brianhellemn/Projects/github-production/credentials/google-oauth/desktop_credentials.json")

# Try to import Google API libraries
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import pickle
    GOOGLE_API_AVAILABLE = True
except ImportError as e:
    GOOGLE_API_AVAILABLE = False
    GOOGLE_API_IMPORT_ERROR = str(e)


class DeploymentMethod(Enum):
    """Deployment method used"""
    API = "api"
    CLASP = "clasp"
    FAILED = "failed"


@dataclass
class DeploymentResult:
    """Result of a deployment operation"""
    success: bool
    method: DeploymentMethod
    script_id: Optional[str] = None
    version: Optional[int] = None
    error: Optional[str] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class GASDeployment:
    """
    Unified GAS deployment manager with API-first approach.

    Usage:
        deployer = GASDeployment()
        result = deployer.deploy("/path/to/gas-project")

        # Or for existing project updates:
        result = deployer.update("SCRIPT_ID", "/path/to/gas-project")
    """

    # Scopes required for Apps Script API
    SCOPES = [
        'https://www.googleapis.com/auth/script.projects',
        'https://www.googleapis.com/auth/script.deployments',
        'https://www.googleapis.com/auth/drive',
    ]

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        prefer_api: bool = True,
        auto_fallback: bool = True
    ):
        """
        Initialize deployment manager.

        Args:
            credentials_path: Path to OAuth credentials JSON
            prefer_api: If True, try API first (default behavior)
            auto_fallback: If True, automatically fall back to clasp on API failure
        """
        self.prefer_api = prefer_api
        self.auto_fallback = auto_fallback
        self.credentials_path = credentials_path or self._find_credentials()

        # API state
        self.api_available = False
        self.credentials = None
        self.script_service = None
        self.drive_service = None

        # clasp state
        self.clasp_available = self._check_clasp()

        # Try to initialize API
        if self.prefer_api and GOOGLE_API_AVAILABLE:
            try:
                self._init_api()
                self.api_available = True
            except Exception as e:
                logger.warning(f"API initialization failed: {e}")
                if not self.auto_fallback:
                    raise

    def _find_credentials(self) -> Optional[str]:
        """Find OAuth credentials from standard locations"""
        # Check environment variable first
        env_path = os.getenv("GAS_API_CREDENTIALS_PATH")
        if env_path and Path(env_path).exists():
            return env_path

        # Check standard locations
        locations = [
            DEFAULT_CREDENTIALS_PATH,
            Path.home() / '.credentials' / 'gas_api_credentials.json',
            Path.home() / '.credentials' / 'desktop_credentials.json',
            Path.home() / '.config' / 'gas_api_credentials.json',
        ]

        for path in locations:
            if path.exists():
                return str(path)

        return None

    def _check_clasp(self) -> bool:
        """Check if clasp is available"""
        try:
            result = subprocess.run(
                ['clasp', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _init_api(self):
        """Initialize Google API services"""
        if not GOOGLE_API_AVAILABLE:
            raise RuntimeError(
                f"Google API libraries not available. Install with: "
                f"pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )

        if not self.credentials_path:
            raise FileNotFoundError(
                "No OAuth credentials found. Set GAS_API_CREDENTIALS_PATH or place "
                "credentials at a standard location."
            )

        creds = None
        token_path = Path.home() / '.gas_api_token.pickle'

        # Load existing token
        if token_path.exists():
            try:
                with open(token_path, 'rb') as f:
                    creds = pickle.load(f)
            except Exception as e:
                logger.debug(f"Could not load token: {e}")

        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token
            with open(token_path, 'wb') as f:
                pickle.dump(creds, f)

        self.credentials = creds
        self.script_service = build('script', 'v1', credentials=creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
        logger.info("Google API services initialized")

    def read_project_files(self, project_path: Path) -> Dict[str, str]:
        """Read all files from a GAS project directory"""
        project_path = Path(project_path)
        files = {}

        # Read JS and GS files
        for ext in ['*.js', '*.gs']:
            for file_path in project_path.glob(ext):
                if file_path.name.startswith('.'):
                    continue
                name = file_path.stem
                # Code.js/Code.gs should map to 'Code'
                if name.lower() == 'code':
                    name = 'Code'
                files[name] = file_path.read_text(encoding='utf-8')

        # Read manifest
        manifest_path = project_path / 'appsscript.json'
        if manifest_path.exists():
            files['appsscript.json'] = manifest_path.read_text(encoding='utf-8')

        return files

    def deploy(
        self,
        project_path: str,
        title: Optional[str] = None
    ) -> DeploymentResult:
        """
        Deploy a new GAS project.

        Args:
            project_path: Path to project directory
            title: Project title (defaults to directory name)

        Returns:
            DeploymentResult with deployment details
        """
        project_path = Path(project_path)
        title = title or project_path.name

        # Try API first
        if self.api_available and self.prefer_api:
            result = self._deploy_via_api(project_path, title)
            if result.success:
                return result

            if not self.auto_fallback:
                return result

            logger.info("API deployment failed, falling back to clasp")

        # Fall back to clasp
        if self.clasp_available:
            return self._deploy_via_clasp(project_path, title)

        return DeploymentResult(
            success=False,
            method=DeploymentMethod.FAILED,
            error="No deployment method available (API failed, clasp not installed)"
        )

    def update(
        self,
        script_id: str,
        project_path: str
    ) -> DeploymentResult:
        """
        Update an existing GAS project.

        Args:
            script_id: Existing script ID
            project_path: Path to project directory

        Returns:
            DeploymentResult with update details
        """
        project_path = Path(project_path)

        # Try API first
        if self.api_available and self.prefer_api:
            result = self._update_via_api(script_id, project_path)
            if result.success:
                return result

            if not self.auto_fallback:
                return result

            logger.info("API update failed, falling back to clasp")

        # Fall back to clasp
        if self.clasp_available:
            return self._update_via_clasp(script_id, project_path)

        return DeploymentResult(
            success=False,
            method=DeploymentMethod.FAILED,
            error="No deployment method available"
        )

    def execute_function(
        self,
        script_id: str,
        function_name: str,
        parameters: Optional[List[Any]] = None
    ) -> DeploymentResult:
        """
        Execute a function in a GAS project.

        Args:
            script_id: Script ID
            function_name: Function to execute
            parameters: Optional parameters to pass

        Returns:
            DeploymentResult with execution details
        """
        # Try API first
        if self.api_available and self.prefer_api:
            result = self._execute_via_api(script_id, function_name, parameters)
            if result.success:
                return result

            if not self.auto_fallback:
                return result

        # Fall back to clasp
        if self.clasp_available:
            return self._execute_via_clasp(script_id, function_name, parameters)

        return DeploymentResult(
            success=False,
            method=DeploymentMethod.FAILED,
            error="No execution method available"
        )

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all GAS projects accessible to the authenticated user"""
        if self.api_available:
            try:
                query = "mimeType='application/vnd.google-apps.script' and trashed=false"
                results = self.drive_service.files().list(
                    q=query,
                    fields='files(id, name, createdTime, modifiedTime)',
                    pageSize=100
                ).execute()
                return results.get('files', [])
            except Exception as e:
                logger.error(f"Error listing projects: {e}")

        return []

    # ==================== API Methods ====================

    def _deploy_via_api(self, project_path: Path, title: str) -> DeploymentResult:
        """Deploy via Apps Script API"""
        try:
            files = self.read_project_files(project_path)

            # Create project
            create_response = self.script_service.projects().create(
                body={'title': title}
            ).execute()

            script_id = create_response.get('scriptId')
            if not script_id:
                return DeploymentResult(
                    success=False,
                    method=DeploymentMethod.API,
                    error="No scriptId in create response"
                )

            # Update content
            file_list = self._build_file_list(files)
            self.script_service.projects().updateContent(
                scriptId=script_id,
                body={'files': file_list}
            ).execute()

            logger.info(f"Deployed via API: {script_id}")

            return DeploymentResult(
                success=True,
                method=DeploymentMethod.API,
                script_id=script_id,
                details={'files_deployed': list(files.keys())}
            )

        except HttpError as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=f"API error: {e}"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=str(e)
            )

    def _update_via_api(self, script_id: str, project_path: Path) -> DeploymentResult:
        """Update via Apps Script API"""
        try:
            files = self.read_project_files(project_path)
            file_list = self._build_file_list(files)

            self.script_service.projects().updateContent(
                scriptId=script_id,
                body={'files': file_list}
            ).execute()

            logger.info(f"Updated via API: {script_id}")

            return DeploymentResult(
                success=True,
                method=DeploymentMethod.API,
                script_id=script_id,
                details={'files_updated': list(files.keys())}
            )

        except HttpError as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=f"API error: {e}"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=str(e)
            )

    def _execute_via_api(
        self,
        script_id: str,
        function_name: str,
        parameters: Optional[List[Any]]
    ) -> DeploymentResult:
        """Execute function via Apps Script API"""
        try:
            request_body = {'function': function_name}
            if parameters:
                request_body['parameters'] = parameters

            response = self.script_service.scripts().run(
                scriptId=script_id,
                body=request_body
            ).execute()

            if 'error' in response:
                error_info = response['error']
                return DeploymentResult(
                    success=False,
                    method=DeploymentMethod.API,
                    error=f"Execution error: {error_info}"
                )

            return DeploymentResult(
                success=True,
                method=DeploymentMethod.API,
                script_id=script_id,
                details={'response': response.get('response', {})}
            )

        except HttpError as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=f"API error: {e}"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.API,
                error=str(e)
            )

    def _build_file_list(self, files: Dict[str, str]) -> List[Dict[str, str]]:
        """Build file list for API request"""
        file_list = []

        for name, content in files.items():
            if name == 'appsscript.json':
                try:
                    manifest = json.loads(content)
                    file_list.append({
                        'name': name,
                        'type': 'JSON',
                        'source': json.dumps(manifest, indent=2)
                    })
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {name}")
            else:
                file_list.append({
                    'name': name,
                    'type': 'SERVER_JS',
                    'source': content
                })

        return file_list

    # ==================== clasp Methods ====================

    def _deploy_via_clasp(self, project_path: Path, title: str) -> DeploymentResult:
        """Deploy via clasp CLI"""
        try:
            # Check if .clasp.json exists
            clasp_config = project_path / '.clasp.json'

            if not clasp_config.exists():
                # Create new project
                result = subprocess.run(
                    ['clasp', 'create', '--title', title, '--type', 'standalone'],
                    cwd=str(project_path),
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode != 0:
                    return DeploymentResult(
                        success=False,
                        method=DeploymentMethod.CLASP,
                        error=f"clasp create failed: {result.stderr}"
                    )

            # Push code
            result = subprocess.run(
                ['clasp', 'push', '--force'],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return DeploymentResult(
                    success=False,
                    method=DeploymentMethod.CLASP,
                    error=f"clasp push failed: {result.stderr}"
                )

            # Get script ID from config
            script_id = None
            if clasp_config.exists():
                config = json.loads(clasp_config.read_text())
                script_id = config.get('scriptId')

            return DeploymentResult(
                success=True,
                method=DeploymentMethod.CLASP,
                script_id=script_id,
                details={'output': result.stdout}
            )

        except subprocess.TimeoutExpired:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.CLASP,
                error="clasp command timed out"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.CLASP,
                error=str(e)
            )

    def _update_via_clasp(self, script_id: str, project_path: Path) -> DeploymentResult:
        """Update via clasp CLI"""
        try:
            # Ensure .clasp.json has correct script ID
            clasp_config = project_path / '.clasp.json'
            config = {'scriptId': script_id, 'rootDir': ''}

            if clasp_config.exists():
                existing = json.loads(clasp_config.read_text())
                existing['scriptId'] = script_id
                config = existing

            clasp_config.write_text(json.dumps(config, indent=2))

            # Push code
            result = subprocess.run(
                ['clasp', 'push', '--force'],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return DeploymentResult(
                    success=False,
                    method=DeploymentMethod.CLASP,
                    error=f"clasp push failed: {result.stderr}"
                )

            return DeploymentResult(
                success=True,
                method=DeploymentMethod.CLASP,
                script_id=script_id,
                details={'output': result.stdout}
            )

        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.CLASP,
                error=str(e)
            )

    def _execute_via_clasp(
        self,
        script_id: str,
        function_name: str,
        parameters: Optional[List[Any]]
    ) -> DeploymentResult:
        """Execute function via clasp CLI"""
        try:
            # clasp run requires the project directory
            # For now, we'll return failure and recommend API
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.CLASP,
                error="clasp run requires project directory context. Use API method."
            )

        except Exception as e:
            return DeploymentResult(
                success=False,
                method=DeploymentMethod.CLASP,
                error=str(e)
            )


# Convenience functions for direct usage

def deploy_project(project_path: str, title: Optional[str] = None) -> DeploymentResult:
    """Deploy a GAS project (API-first with clasp fallback)"""
    deployer = GASDeployment()
    return deployer.deploy(project_path, title)


def update_project(script_id: str, project_path: str) -> DeploymentResult:
    """Update an existing GAS project (API-first with clasp fallback)"""
    deployer = GASDeployment()
    return deployer.update(script_id, project_path)


def execute_function(
    script_id: str,
    function_name: str,
    parameters: Optional[List[Any]] = None
) -> DeploymentResult:
    """Execute a function in a GAS project (API-first with clasp fallback)"""
    deployer = GASDeployment()
    return deployer.execute_function(script_id, function_name, parameters)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GAS Deployment Tool (API-first)")
    parser.add_argument("action", choices=["deploy", "update", "execute", "list"])
    parser.add_argument("--path", help="Project path")
    parser.add_argument("--title", help="Project title")
    parser.add_argument("--script-id", help="Script ID for update/execute")
    parser.add_argument("--function", help="Function name for execute")
    parser.add_argument("--credentials", help="Path to OAuth credentials")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    deployer = GASDeployment(credentials_path=args.credentials)

    if args.action == "deploy":
        if not args.path:
            print("Error: --path required for deploy")
            sys.exit(1)
        result = deployer.deploy(args.path, args.title)

    elif args.action == "update":
        if not args.path or not args.script_id:
            print("Error: --path and --script-id required for update")
            sys.exit(1)
        result = deployer.update(args.script_id, args.path)

    elif args.action == "execute":
        if not args.script_id or not args.function:
            print("Error: --script-id and --function required for execute")
            sys.exit(1)
        result = deployer.execute_function(args.script_id, args.function)

    elif args.action == "list":
        projects = deployer.list_projects()
        print(f"\nFound {len(projects)} GAS projects:\n")
        for p in projects:
            print(f"  - {p['name']} (ID: {p['id']})")
        sys.exit(0)

    print(f"\nResult:")
    print(f"  Success: {result.success}")
    print(f"  Method: {result.method.value}")
    if result.script_id:
        print(f"  Script ID: {result.script_id}")
    if result.error:
        print(f"  Error: {result.error}")
    if result.details:
        print(f"  Details: {json.dumps(result.details, indent=4)}")

    sys.exit(0 if result.success else 1)
