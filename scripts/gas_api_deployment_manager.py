#!/usr/bin/env python3
"""
Google Apps Script API Deployment Manager
==========================================

Comprehensive file system review and deployment tool for Google Apps Script projects.
Uses Google Apps Script API directly (not clasp) to:
1. Scan and analyze all GAS files
2. Identify most performant relation/population scripts
3. Identify most system-aligned deduplication workflows
4. Deploy to all available Google Apps Script accounts

Author: Cursor MM1 Agent
Created: 2026-01-16
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import pickle
    GOOGLE_API_AVAILABLE = True
except ImportError as e:
    GOOGLE_API_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Google Apps Script API scopes
SCOPES = [
    'https://www.googleapis.com/auth/script.projects',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/script.deployments',
    'https://www.googleapis.com/auth/cloud-platform'
]


@dataclass
class GASFileAnalysis:
    """Analysis results for a GAS file"""
    path: Path
    name: str
    lines: int
    has_relation_population: bool = False
    has_deduplication: bool = False
    relation_functions: List[str] = field(default_factory=list)
    deduplication_functions: List[str] = field(default_factory=list)
    production_ready_score: float = 0.0
    system_alignment_score: float = 0.0
    features: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


@dataclass
class GASProject:
    """Represents a Google Apps Script project"""
    script_id: str
    name: str
    path: Path
    appsscript_json: Optional[Dict[str, Any]] = None
    clasp_json: Optional[Dict[str, Any]] = None


class GASFileAnalyzer:
    """Analyzes Google Apps Script files for features and quality"""
    
    RELATION_PATTERNS = [
        r'relation.*populate|populate.*relation',
        r'ensurePropertyExists.*relation',
        r'validateRelations',
        r'getOrCreateItemType',
        r'ensureItemTypePropertyExists',
        r'relation.*\[.*id',
        r'setRelation|addRelation|createRelation',
        r'Item-Type|ItemType',
        r'Most Recent Log.*relation',
        r'Clients.*relation|Scripts.*relation'
    ]
    
    DEDUPLICATION_PATTERNS = [
        r'deduplicat|remove.*duplicate|consolidate.*duplicate',
        r'runWorkspaceCleanup',
        r'consolidateDuplicates',
        r'duplicate.*folder|duplicate.*file',
        r'check.*existing.*before.*create',
        r'age.*based.*deduplication',
        r'prevent.*duplicate',
        r'isDuplicate|hasDuplicate'
    ]
    
    PRODUCTION_READY_INDICATORS = [
        r'error.*handling|try.*catch',
        r'logging|UL\.(info|warn|error|debug)',
        r'validation|validate',
        r'config|CONFIG',
        r'retry|backoff',
        r'timeout',
        r'rate.*limit',
        r'batch.*process',
        r'cache|caching'
    ]
    
    SYSTEM_ALIGNMENT_INDICATORS = [
        r'notion.*api|NOTION',
        r'workspace.*database|WORKSPACE',
        r'environment.*instance|ENVIRONMENT',
        r'execution.*log|EXECUTION',
        r'script.*property|PROPS',
        r'database.*id|DB_ID',
        r'discoverDatabaseByName',
        r'dynamic.*discovery'
    ]
    
    def analyze_file(self, file_path: Path) -> GASFileAnalysis:
        """Analyze a GAS file for features and quality"""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            analysis = GASFileAnalysis(
                path=file_path,
                name=file_path.name,
                lines=len(lines)
            )
            
            # Check for relation population features
            relation_matches = []
            for pattern in self.RELATION_PATTERNS:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    # Extract function name if possible
                    context = content[max(0, match.start()-50):match.end()+50]
                    func_match = re.search(r'function\s+(\w+)', context)
                    if func_match:
                        func_name = func_match.group(1)
                        if func_name not in analysis.relation_functions:
                            analysis.relation_functions.append(func_name)
                    relation_matches.append(match.group(0))
            
            if relation_matches:
                analysis.has_relation_population = True
                analysis.features.append(f"Relation Population ({len(relation_matches)} matches)")
            
            # Check for deduplication features
            dedup_matches = []
            for pattern in self.DEDUPLICATION_PATTERNS:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    context = content[max(0, match.start()-50):match.end()+50]
                    func_match = re.search(r'function\s+(\w+)', context)
                    if func_match:
                        func_name = func_match.group(1)
                        if func_name not in analysis.deduplication_functions:
                            analysis.deduplication_functions.append(func_name)
                    dedup_matches.append(match.group(0))
            
            if dedup_matches:
                analysis.has_deduplication = True
                analysis.features.append(f"Deduplication ({len(dedup_matches)} matches)")
            
            # Calculate production ready score
            production_score = 0.0
            for pattern in self.PRODUCTION_READY_INDICATORS:
                matches = len(re.findall(pattern, content, re.IGNORECASE))
                production_score += min(matches * 0.1, 1.0)  # Cap at 1.0 per indicator
            
            analysis.production_ready_score = min(production_score / len(self.PRODUCTION_READY_INDICATORS) * 10, 10.0)
            
            # Calculate system alignment score
            alignment_score = 0.0
            for pattern in self.SYSTEM_ALIGNMENT_INDICATORS:
                matches = len(re.findall(pattern, content, re.IGNORECASE))
                alignment_score += min(matches * 0.15, 1.0)
            
            analysis.system_alignment_score = min(alignment_score / len(self.SYSTEM_ALIGNMENT_INDICATORS) * 10, 10.0)
            
            # Check for common issues
            if 'TODO' in content or 'FIXME' in content:
                analysis.issues.append("Contains TODO/FIXME comments")
            
            if not re.search(r'error.*handling|try.*catch', content, re.IGNORECASE):
                analysis.issues.append("Limited error handling")
            
            if len(lines) > 10000:
                analysis.issues.append("Very large file (>10k lines) - consider modularization")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return GASFileAnalysis(
                path=file_path,
                name=file_path.name,
                lines=0,
                issues=[f"Analysis error: {e}"]
            )


class GASAPIDeploymentManager:
    """Manages Google Apps Script deployments via API (not clasp)"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize the deployment manager.
        
        Args:
            credentials_path: Path to OAuth credentials JSON file
        """
        if not GOOGLE_API_AVAILABLE:
            raise RuntimeError(
                f"Google API libraries not available. Install with: "
                f"pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\n"
                f"Error: {IMPORT_ERROR}"
            )
        
        self.credentials_path = credentials_path
        self.credentials = None
        self.script_service = None
        self.drive_service = None
        self.analyzer = GASFileAnalyzer()
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google APIs"""
        creds = None
        token_path = Path.home() / '.gas_api_token.pickle'
        
        # Try to load existing token
        if token_path.exists():
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                logger.warning(f"Could not load existing token: {e}")
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path:
                    # Try to find credentials in common locations
                    possible_paths = [
                        Path.home() / '.credentials' / 'gas_api_credentials.json',
                        Path.home() / '.config' / 'gas_api_credentials.json',
                        project_root / 'credentials' / 'gas_api_credentials.json'
                    ]
                    
                    for path in possible_paths:
                        if path.exists():
                            self.credentials_path = str(path)
                            break
                    
                    if not self.credentials_path:
                        raise FileNotFoundError(
                            "OAuth credentials file not found. Please provide credentials_path or "
                            "place credentials.json in one of: " + ", ".join(str(p) for p in possible_paths)
                        )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next time
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.credentials = creds
        
        # Build services
        self.script_service = build('script', 'v1', credentials=creds)
        self.drive_service = build('drive', 'v3', credentials=creds)
        
        logger.info("Successfully authenticated with Google APIs")
    
    def scan_gas_files(self, base_path: Optional[Path] = None) -> List[GASFileAnalysis]:
        """
        Scan for all Google Apps Script files.
        
        Args:
            base_path: Base directory to scan (defaults to gas-scripts)
            
        Returns:
            List of file analyses
        """
        if base_path is None:
            base_path = project_root / 'gas-scripts'
        
        if not base_path.exists():
            logger.warning(f"Base path does not exist: {base_path}")
            return []
        
        analyses = []
        
        # Find all .js and .gs files
        for ext in ['*.js', '*.gs']:
            for file_path in base_path.rglob(ext):
                # Skip backups and node_modules
                if '.backup' in str(file_path) or 'node_modules' in str(file_path):
                    continue
                
                analysis = self.analyzer.analyze_file(file_path)
                analyses.append(analysis)
                logger.debug(f"Analyzed: {file_path.name} - Relations: {analysis.has_relation_population}, Dedup: {analysis.has_deduplication}")
        
        logger.info(f"Scanned {len(analyses)} GAS files")
        return analyses
    
    def find_best_relation_population_script(self, analyses: List[GASFileAnalysis]) -> Optional[GASFileAnalysis]:
        """Find the most performant and production-ready relation/population script"""
        candidates = [a for a in analyses if a.has_relation_population]
        
        if not candidates:
            return None
        
        # Score: production_ready_score * 0.6 + system_alignment_score * 0.4 + relation function count bonus
        best = max(candidates, key=lambda a: (
            a.production_ready_score * 0.6 +
            a.system_alignment_score * 0.4 +
            len(a.relation_functions) * 0.5 +
            (10.0 if 'validateRelations' in str(a.relation_functions) else 0.0) +
            (5.0 if 'ensureItemTypePropertyExists' in str(a.relation_functions) else 0.0)
        ))
        
        return best
    
    def find_best_deduplication_workflow(self, analyses: List[GASFileAnalysis]) -> Optional[GASFileAnalysis]:
        """Find the most system-aligned deduplication workflow"""
        candidates = [a for a in analyses if a.has_deduplication]
        
        if not candidates:
            return None
        
        # Score: system_alignment_score * 0.6 + production_ready_score * 0.4 + dedup function count bonus
        best = max(candidates, key=lambda a: (
            a.system_alignment_score * 0.6 +
            a.production_ready_score * 0.4 +
            len(a.deduplication_functions) * 0.5 +
            (10.0 if 'runWorkspaceCleanup' in str(a.deduplication_functions) else 0.0) +
            (5.0 if 'consolidateDuplicates' in str(a.deduplication_functions) else 0.0)
        ))
        
        return best
    
    def get_project_files(self, project_path: Path) -> Dict[str, str]:
        """
        Get all files for a GAS project.
        
        Args:
            project_path: Path to project directory
            
        Returns:
            Dictionary mapping file names to content
        """
        files = {}
        
        # Read Code.js or Code.gs
        for code_file in ['Code.js', 'Code.gs', 'main.js', 'main.gs']:
            code_path = project_path / code_file
            if code_path.exists():
                files['Code'] = code_path.read_text(encoding='utf-8')
                break
        
        # Read appsscript.json
        manifest_path = project_path / 'appsscript.json'
        if manifest_path.exists():
            manifest_content = manifest_path.read_text(encoding='utf-8')
            files['appsscript.json'] = manifest_content
        
        # Read other .js/.gs files
        for file_path in project_path.glob('*.js'):
            if file_path.name not in ['Code.js']:
                files[file_path.stem] = file_path.read_text(encoding='utf-8')
        
        for file_path in project_path.glob('*.gs'):
            if file_path.name not in ['Code.gs']:
                files[file_path.stem] = file_path.read_text(encoding='utf-8')
        
        return files
    
    def create_project_via_api(
        self,
        title: str,
        files: Dict[str, str],
        parent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new Google Apps Script project via API.
        
        Args:
            title: Project title
            files: Dictionary of file names to content
            parent_id: Optional parent Drive folder ID
            
        Returns:
            Script ID if successful, None otherwise
        """
        try:
            # Create project
            create_request = {
                'title': title
            }
            
            response = self.script_service.projects().create(body=create_request).execute()
            script_id = response.get('scriptId')
            
            if not script_id:
                logger.error("Failed to get script ID from create response")
                return None
            
            logger.info(f"Created project: {script_id}")
            
            # Update project content
            self.update_project_content(script_id, files)
            
            # Move to parent folder if specified
            if parent_id:
                try:
                    self.drive_service.files().update(
                        fileId=script_id,
                        addParents=parent_id,
                        removeParents='',
                        fields='id, parents'
                    ).execute()
                    logger.info(f"Moved project to folder: {parent_id}")
                except Exception as e:
                    logger.warning(f"Could not move project to folder: {e}")
            
            return script_id
            
        except HttpError as e:
            logger.error(f"Error creating project: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating project: {e}")
            return None
    
    def update_project_content(self, script_id: str, files: Dict[str, str]) -> bool:
        """
        Update project content via API.
        
        Args:
            script_id: Script ID
            files: Dictionary of file names to content
            
        Returns:
            True if successful
        """
        try:
            # Build file list for API
            file_list = []
            
            for name, content in files.items():
                if name == 'appsscript.json':
                    # Parse JSON manifest
                    try:
                        manifest = json.loads(content)
                        file_list.append({
                            'name': name,
                            'type': 'JSON',
                            'source': json.dumps(manifest, indent=2)
                        })
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in appsscript.json: {e}")
                        continue
                else:
                    # Regular script file
                    file_list.append({
                        'name': name,
                        'type': 'SERVER_JS',
                        'source': content
                    })
            
            # Update project content
            request_body = {
                'files': file_list
            }
            
            response = self.script_service.projects().updateContent(
                scriptId=script_id,
                body=request_body
            ).execute()
            
            logger.info(f"Updated project content: {script_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Error updating project content: {e}")
            if e.resp.status == 404:
                logger.error(f"Project not found: {script_id}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating project content: {e}")
            return False
    
    def list_available_projects(self) -> List[Dict[str, Any]]:
        """
        List all available Google Apps Script projects.
        
        Returns:
            List of project dictionaries
        """
        try:
            # Use Drive API to find Apps Script files
            query = "mimeType='application/vnd.google-apps.script' and trashed=false"
            results = self.drive_service.files().list(
                q=query,
                fields='files(id, name, createdTime, modifiedTime, parents)',
                pageSize=100
            ).execute()
            
            projects = results.get('files', [])
            logger.info(f"Found {len(projects)} Apps Script projects")
            return projects
            
        except Exception as e:
            logger.error(f"Error listing projects: {e}")
            return []
    
    def get_project_info(self, script_id: str) -> Optional[Dict[str, Any]]:
        """
        Get project information.
        
        Args:
            script_id: Script ID
            
        Returns:
            Project info dictionary
        """
        try:
            project = self.script_service.projects().get(scriptId=script_id).execute()
            return project
        except HttpError as e:
            logger.error(f"Error getting project info: {e}")
            return None
    
    def deploy_to_all_accounts(
        self,
        project_path: Path,
        project_name: str,
        script_ids: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Deploy a project to all available accounts/projects.
        
        Args:
            project_path: Path to local project
            project_name: Name for the project
            script_ids: Optional list of specific script IDs to update (if None, creates new)
            
        Returns:
            Dictionary mapping script IDs to success status
        """
        results = {}
        
        # Get project files
        files = self.get_project_files(project_path)
        if not files:
            logger.error(f"No files found in {project_path}")
            return results
        
        if script_ids:
            # Update existing projects
            for script_id in script_ids:
                logger.info(f"Updating project: {script_id}")
                success = self.update_project_content(script_id, files)
                results[script_id] = success
        else:
            # Create new project
            logger.info(f"Creating new project: {project_name}")
            script_id = self.create_project_via_api(project_name, files)
            if script_id:
                results[script_id] = True
            else:
                results['NEW'] = False
        
        return results


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Google Apps Script API Deployment Manager - Scan, analyze, and deploy GAS projects"
    )
    parser.add_argument(
        '--scan-only',
        action='store_true',
        help='Only scan and analyze files, do not deploy'
    )
    parser.add_argument(
        '--credentials',
        help='Path to OAuth credentials JSON file'
    )
    parser.add_argument(
        '--base-path',
        help='Base path to scan for GAS files (default: gas-scripts)'
    )
    parser.add_argument(
        '--deploy',
        action='store_true',
        help='Deploy identified scripts'
    )
    parser.add_argument(
        '--script-ids',
        nargs='+',
        help='Specific script IDs to update (if not provided, creates new projects)'
    )
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = GASFileAnalyzer()
    
    # Scan files
    base_path = Path(args.base_path) if args.base_path else project_root / 'gas-scripts'
    print(f"\n{'='*80}")
    print("SCANNING GOOGLE APPS SCRIPT FILES")
    print(f"{'='*80}\n")
    
    # Scan files using analyzer directly
    analyses = []
    if base_path.exists():
        for ext in ['*.js', '*.gs']:
            for file_path in base_path.rglob(ext):
                if '.backup' in str(file_path) or 'node_modules' in str(file_path):
                    continue
                analysis = analyzer.analyze_file(file_path)
                analyses.append(analysis)
                logger.debug(f"Analyzed: {file_path.name}")
    else:
        print(f"❌ Base path does not exist: {base_path}")
        return
    
    if not analyses:
        print("❌ No GAS files found")
        return
    
    print(f"✅ Found {len(analyses)} GAS files\n")
    
    # Find best scripts
    print(f"{'='*80}")
    print("ANALYSIS RESULTS")
    print(f"{'='*80}\n")
    
    # Find best scripts
    relation_candidates = [a for a in analyses if a.has_relation_population]
    dedup_candidates = [a for a in analyses if a.has_deduplication]
    
    relation_script = None
    if relation_candidates:
        relation_script = max(relation_candidates, key=lambda a: (
            a.production_ready_score * 0.6 +
            a.system_alignment_score * 0.4 +
            len(a.relation_functions) * 0.5 +
            (10.0 if 'validateRelations' in str(a.relation_functions) else 0.0) +
            (5.0 if 'ensureItemTypePropertyExists' in str(a.relation_functions) else 0.0)
        ))
    
    dedup_workflow = None
    if dedup_candidates:
        dedup_workflow = max(dedup_candidates, key=lambda a: (
            a.system_alignment_score * 0.6 +
            a.production_ready_score * 0.4 +
            len(a.deduplication_functions) * 0.5 +
            (10.0 if 'runWorkspaceCleanup' in str(a.deduplication_functions) else 0.0) +
            (5.0 if 'consolidateDuplicates' in str(a.deduplication_functions) else 0.0)
        ))
    
    print("📊 RELATION/POPULATION SCRIPTS:")
    for i, analysis in enumerate(sorted(relation_candidates, key=lambda x: x.production_ready_score + x.system_alignment_score, reverse=True)[:5], 1):
        marker = "🏆" if analysis == relation_script else "  "
        print(f"{marker} {i}. {analysis.name}")
        print(f"     Path: {analysis.path}")
        print(f"     Production Ready: {analysis.production_ready_score:.1f}/10")
        print(f"     System Alignment: {analysis.system_alignment_score:.1f}/10")
        print(f"     Relation Functions: {len(analysis.relation_functions)}")
        print(f"     Features: {', '.join(analysis.features)}")
        if analysis.issues:
            print(f"     ⚠️  Issues: {', '.join(analysis.issues)}")
        print()
    
    print("\n📊 DEDUPLICATION WORKFLOWS:")
    for i, analysis in enumerate(sorted(dedup_candidates, key=lambda x: x.system_alignment_score + x.production_ready_score, reverse=True)[:5], 1):
        marker = "🏆" if analysis == dedup_workflow else "  "
        print(f"{marker} {i}. {analysis.name}")
        print(f"     Path: {analysis.path}")
        print(f"     Production Ready: {analysis.production_ready_score:.1f}/10")
        print(f"     System Alignment: {analysis.system_alignment_score:.1f}/10")
        print(f"     Deduplication Functions: {len(analysis.deduplication_functions)}")
        print(f"     Features: {', '.join(analysis.features)}")
        if analysis.issues:
            print(f"     ⚠️  Issues: {', '.join(analysis.issues)}")
        print()
    
    # Summary
    print(f"{'='*80}")
    print("SELECTED SCRIPTS")
    print(f"{'='*80}\n")
    
    if relation_script:
        print(f"✅ BEST RELATION/POPULATION SCRIPT:")
        print(f"   File: {relation_script.name}")
        print(f"   Path: {relation_script.path}")
        print(f"   Score: {relation_script.production_ready_score + relation_script.system_alignment_score:.1f}/20")
        print(f"   Functions: {', '.join(relation_script.relation_functions[:5])}")
        print()
    else:
        print("❌ No relation/population script found\n")
    
    if dedup_workflow:
        print(f"✅ BEST DEDUPLICATION WORKFLOW:")
        print(f"   File: {dedup_workflow.name}")
        print(f"   Path: {dedup_workflow.path}")
        print(f"   Score: {dedup_workflow.production_ready_score + dedup_workflow.system_alignment_score:.1f}/20")
        print(f"   Functions: {', '.join(dedup_workflow.deduplication_functions[:5])}")
        print()
    else:
        print("❌ No deduplication workflow found\n")
    
    if args.scan_only:
        print("Scan-only mode - deployment skipped")
        return
    
    # Deploy if requested
    if args.deploy:
        if not GOOGLE_API_AVAILABLE:
            print("\n❌ Google API libraries not available. Cannot deploy.")
            print("Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
            return
        
        try:
            manager = GASAPIDeploymentManager(credentials_path=args.credentials)
            
            print(f"\n{'='*80}")
            print("DEPLOYMENT")
            print(f"{'='*80}\n")
            
            # List available projects
            projects = manager.list_available_projects()
            print(f"Found {len(projects)} existing Apps Script projects")
            
            # Deploy relation script if found
            if relation_script:
                project_path = relation_script.path.parent
                project_name = f"{project_path.name}_RelationPopulation"
                
                print(f"\n📤 Deploying relation/population script: {project_name}")
                results = manager.deploy_to_all_accounts(
                    project_path=project_path,
                    project_name=project_name,
                    script_ids=args.script_ids
                )
                
                for script_id, success in results.items():
                    status = "✅" if success else "❌"
                    print(f"   {status} {script_id}: {'Success' if success else 'Failed'}")
            
            # Deploy deduplication workflow if found
            if dedup_workflow:
                project_path = dedup_workflow.path.parent
                project_name = f"{project_path.name}_Deduplication"
                
                print(f"\n📤 Deploying deduplication workflow: {project_name}")
                results = manager.deploy_to_all_accounts(
                    project_path=project_path,
                    project_name=project_name,
                    script_ids=args.script_ids
                )
                
                for script_id, success in results.items():
                    status = "✅" if success else "❌"
                    print(f"   {status} {script_id}: {'Success' if success else 'Failed'}")
            
            print("\n✅ Deployment complete!")
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}", exc_info=True)
            print(f"\n❌ Deployment failed: {e}")


if __name__ == "__main__":
    main()
