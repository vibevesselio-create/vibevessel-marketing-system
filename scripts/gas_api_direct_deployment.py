#!/usr/bin/env python3
"""
Google Apps Script API Direct Deployment Module
===============================================

Deploys Google Apps Script projects directly via the Apps Script API
without using clasp. Supports creating new projects and updating existing ones.

Author: Cursor MM1 Agent
Created: 2026-01-16
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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
    IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)

# Scopes required for Apps Script API
SCOPES = [
    'https://www.googleapis.com/auth/script.projects',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/script.deployments'
]


class GASAPIDirectDeployment:
    """Direct deployment to Google Apps Script via API"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize deployment manager.
        
        Args:
            credentials_path: Path to OAuth credentials JSON
        """
        if not GOOGLE_API_AVAILABLE:
            raise RuntimeError(
                f"Google API libraries not available. Install with: "
                f"pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        
        self.credentials_path = credentials_path
        self.credentials = None
        self.script_service = None
        self.drive_service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google APIs"""
        creds = None
        token_path = Path.home() / '.gas_api_token.pickle'
        
        # Load existing token
        if token_path.exists():
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                logger.warning(f"Could not load token: {e}")
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path:
                    # Environment override (preferred for CI / multi-env setups)
                    env_path = (
                        os.getenv("GAS_API_CREDENTIALS_PATH")
                        or os.getenv("GOOGLE_OAUTH_CREDENTIALS_PATH")
                        or os.getenv("GOOGLE_CLIENT_SECRETS_PATH")
                    )
                    if env_path and Path(env_path).expanduser().exists():
                        self.credentials_path = str(Path(env_path).expanduser())

                    # Try common locations
                    possible_paths = [
                        Path.home() / '.credentials' / 'gas_api_credentials.json',
                        Path.home() / '.credentials' / 'credentials.json',
                        Path.home() / '.config' / 'gas_api_credentials.json',
                        Path.home() / '.config' / 'credentials.json',
                        project_root / 'credentials' / 'gas_api_credentials.json',
                        project_root / 'credentials' / 'credentials.json',
                        project_root / 'credentials' / 'oauth_credentials.json',
                        project_root / 'credentials' / 'client_secret.json'
                    ]
                    
                    for path in possible_paths:
                        if path.exists():
                            self.credentials_path = str(path)
                            break
                    
                    if not self.credentials_path:
                        searched = "\n".join(f"- {p}" for p in possible_paths)
                        raise FileNotFoundError(
                            "OAuth credentials not found.\n\n"
                            "Provide one of:\n"
                            "- CLI arg: python3 scripts/execute_gas_api_deployment.py --credentials /path/to/client_secret.json\n"
                            "- Env var: GAS_API_CREDENTIALS_PATH=/path/to/client_secret.json\n"
                            "- Place a credentials JSON at one of the searched locations:\n"
                            f"{searched}\n\n"
                            "Tip: run python3 scripts/troubleshoot_gas_api_oauth.py for setup guidance."
                        )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.credentials = creds
        self.script_service = build('script', 'v1', credentials=creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
        logger.info("Authenticated with Google APIs")
    
    def read_project_files(self, project_path: Path) -> Dict[str, str]:
        """
        Read all files from a GAS project directory.
        
        Args:
            project_path: Path to project directory
            
        Returns:
            Dictionary mapping file names to content
        """
        files = {}
        
        # Read main code file
        for code_file in ['Code.js', 'Code.gs', 'main.js', 'main.gs']:
            code_path = project_path / code_file
            if code_path.exists():
                files['Code'] = code_path.read_text(encoding='utf-8')
                break
        
        # Read appsscript.json
        manifest_path = project_path / 'appsscript.json'
        if manifest_path.exists():
            files['appsscript.json'] = manifest_path.read_text(encoding='utf-8')
        
        # Read other JS/GS files
        for file_path in project_path.glob('*.js'):
            if file_path.name not in ['Code.js']:
                name = file_path.stem
                files[name] = file_path.read_text(encoding='utf-8')
        
        for file_path in project_path.glob('*.gs'):
            if file_path.name not in ['Code.gs']:
                name = file_path.stem
                files[name] = file_path.read_text(encoding='utf-8')
        
        return files
    
    def create_project(self, title: str, files: Dict[str, str]) -> Optional[str]:
        """
        Create a new Apps Script project.
        
        Args:
            title: Project title
            files: Dictionary of file names to content
            
        Returns:
            Script ID if successful
        """
        try:
            # Create project
            create_response = self.script_service.projects().create(
                body={'title': title}
            ).execute()
            
            script_id = create_response.get('scriptId')
            if not script_id:
                logger.error("No scriptId in create response")
                return None
            
            logger.info(f"Created project: {script_id}")
            
            # Update content
            if self.update_project_content(script_id, files):
                return script_id
            else:
                logger.error("Failed to update project content")
                return None
                
        except HttpError as e:
            logger.error(f"Error creating project: {e}")
            return None
    
    def update_project_content(self, script_id: str, files: Dict[str, str]) -> bool:
        """
        Update project content.
        
        Args:
            script_id: Script ID
            files: Dictionary of file names to content
            
        Returns:
            True if successful
        """
        try:
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
                        continue
                else:
                    file_list.append({
                        'name': name,
                        'type': 'SERVER_JS',
                        'source': content
                    })
            
            request_body = {'files': file_list}
            
            self.script_service.projects().updateContent(
                scriptId=script_id,
                body=request_body
            ).execute()
            
            logger.info(f"Updated project content: {script_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Error updating content: {e}")
            return False
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """List all Apps Script projects"""
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


def deploy_identified_scripts():
    """Deploy the identified best scripts to all available accounts"""
    from gas_api_deployment_manager import GASFileAnalyzer
    
    print(f"\n{'='*80}")
    print("GOOGLE APPS SCRIPT API DEPLOYMENT")
    print(f"{'='*80}\n")
    
    # Scan and analyze
    analyzer = GASFileAnalyzer()
    base_path = project_root / 'gas-scripts'
    
    analyses = []
    for ext in ['*.js', '*.gs']:
        for file_path in base_path.rglob(ext):
            if '.backup' in str(file_path) or 'node_modules' in str(file_path):
                continue
            analysis = analyzer.analyze_file(file_path)
            analyses.append(analysis)
    
    # Find best scripts
    relation_candidates = [a for a in analyses if a.has_relation_population]
    dedup_candidates = [a for a in analyses if a.has_deduplication]
    
    relation_script = None
    if relation_candidates:
        relation_script = max(relation_candidates, key=lambda a: (
            a.production_ready_score * 0.6 + a.system_alignment_score * 0.4 +
            len(a.relation_functions) * 0.5
        ))
    
    dedup_workflow = None
    if dedup_candidates:
        dedup_workflow = max(dedup_candidates, key=lambda a: (
            a.system_alignment_score * 0.6 + a.production_ready_score * 0.4 +
            len(a.deduplication_functions) * 0.5
        ))
    
    if not relation_script and not dedup_workflow:
        print("❌ No suitable scripts found for deployment")
        return
    
    # Initialize deployment manager
    try:
        deployer = GASAPIDirectDeployment()
        
        # List existing projects
        existing_projects = deployer.list_projects()
        print(f"Found {len(existing_projects)} existing Apps Script projects\n")
        
        deployment_results = {}
        
        # Deploy relation script
        if relation_script:
            project_path = relation_script.path.parent
            project_name = f"{project_path.name}_RelationPopulation"
            
            print(f"📤 Deploying Relation/Population Script:")
            print(f"   Source: {relation_script.path}")
            print(f"   Project Name: {project_name}\n")
            
            files = deployer.read_project_files(project_path)
            
            # Create new project
            script_id = deployer.create_project(project_name, files)
            if script_id:
                deployment_results[project_name] = {'script_id': script_id, 'success': True}
                print(f"   ✅ Created project: {script_id}")
            else:
                deployment_results[project_name] = {'success': False}
                print(f"   ❌ Failed to create project")
        
        # Deploy deduplication workflow
        if dedup_workflow:
            project_path = dedup_workflow.path.parent
            project_name = f"{project_path.name}_Deduplication"
            
            print(f"\n📤 Deploying Deduplication Workflow:")
            print(f"   Source: {dedup_workflow.path}")
            print(f"   Project Name: {project_name}\n")
            
            files = deployer.read_project_files(project_path)
            
            # Create new project
            script_id = deployer.create_project(project_name, files)
            if script_id:
                deployment_results[project_name] = {'script_id': script_id, 'success': True}
                print(f"   ✅ Created project: {script_id}")
            else:
                deployment_results[project_name] = {'success': False}
                print(f"   ❌ Failed to create project")
        
        print(f"\n{'='*80}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*80}\n")
        
        for name, result in deployment_results.items():
            status = "✅" if result.get('success') else "❌"
            script_id = result.get('script_id', 'N/A')
            print(f"{status} {name}: {script_id}")
        
        print("\n✅ Deployment process complete!")
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}", exc_info=True)
        print(f"\n❌ Deployment failed: {e}")


if __name__ == "__main__":
    deploy_identified_scripts()
