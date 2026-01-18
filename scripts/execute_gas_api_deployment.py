#!/usr/bin/env python3
"""
Execute Google Apps Script API Deployment
=========================================

Comprehensive execution script that:
1. Scans all GAS files
2. Identifies best relation/population and deduplication scripts
3. Deploys via Google Apps Script API (not clasp) to all available accounts

Run this script to perform the complete deployment process.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.gas_api_deployment_manager import GASFileAnalyzer
from scripts.gas_api_direct_deployment import GASAPIDirectDeployment


def main():
    """Execute comprehensive GAS deployment"""
    
    print(f"\n{'='*80}")
    print("GOOGLE APPS SCRIPT API DEPLOYMENT - COMPREHENSIVE EXECUTION")
    print(f"{'='*80}\n")
    print(f"Execution Time: {datetime.now().isoformat()}\n")
    
    # Step 1: Scan and analyze
    print(f"{'='*80}")
    print("STEP 1: FILE SYSTEM REVIEW AND ANALYSIS")
    print(f"{'='*80}\n")
    
    analyzer = GASFileAnalyzer()
    base_path = project_root / 'gas-scripts'
    
    if not base_path.exists():
        print(f"❌ Base path does not exist: {base_path}")
        return
    
    analyses = []
    for ext in ['*.js', '*.gs']:
        for file_path in base_path.rglob(ext):
            if '.backup' in str(file_path) or 'node_modules' in str(file_path):
                continue
            analysis = analyzer.analyze_file(file_path)
            analyses.append(analysis)
            print(f"  ✓ Analyzed: {file_path.relative_to(project_root)}")
    
    print(f"\n✅ Scanned {len(analyses)} GAS files\n")
    
    # Step 2: Identify best scripts
    print(f"{'='*80}")
    print("STEP 2: IDENTIFY BEST SCRIPTS")
    print(f"{'='*80}\n")
    
    relation_candidates = [a for a in analyses if a.has_relation_population]
    dedup_candidates = [a for a in analyses if a.has_deduplication]
    
    # Score relation scripts
    relation_script = None
    if relation_candidates:
        relation_script = max(relation_candidates, key=lambda a: (
            a.production_ready_score * 0.6 +
            a.system_alignment_score * 0.4 +
            len(a.relation_functions) * 0.5 +
            (10.0 if 'validateRelations' in str(a.relation_functions) else 0.0) +
            (5.0 if 'ensureItemTypePropertyExists' in str(a.relation_functions) else 0.0)
        ))
    
    # Score deduplication workflows
    dedup_workflow = None
    if dedup_candidates:
        dedup_workflow = max(dedup_candidates, key=lambda a: (
            a.system_alignment_score * 0.6 +
            a.production_ready_score * 0.4 +
            len(a.deduplication_functions) * 0.5 +
            (10.0 if 'runWorkspaceCleanup' in str(a.deduplication_functions) else 0.0) +
            (5.0 if 'consolidateDuplicates' in str(a.deduplication_functions) else 0.0)
        ))
    
    # Display results
    print("📊 RELATION/POPULATION SCRIPTS:")
    if relation_candidates:
        for i, analysis in enumerate(sorted(relation_candidates, 
                                          key=lambda x: x.production_ready_score + x.system_alignment_score, 
                                          reverse=True)[:5], 1):
            marker = "🏆 SELECTED" if analysis == relation_script else f"  {i}."
            print(f"{marker} {analysis.name}")
            print(f"     Path: {analysis.path.relative_to(project_root)}")
            print(f"     Production Ready: {analysis.production_ready_score:.1f}/10")
            print(f"     System Alignment: {analysis.system_alignment_score:.1f}/10")
            print(f"     Relation Functions: {len(analysis.relation_functions)}")
            if analysis == relation_script:
                print(f"     Key Functions: {', '.join(analysis.relation_functions[:5])}")
            print()
    else:
        print("  ❌ No relation/population scripts found\n")
    
    print("\n📊 DEDUPLICATION WORKFLOWS:")
    if dedup_candidates:
        for i, analysis in enumerate(sorted(dedup_candidates,
                                          key=lambda x: x.system_alignment_score + x.production_ready_score,
                                          reverse=True)[:5], 1):
            marker = "🏆 SELECTED" if analysis == dedup_workflow else f"  {i}."
            print(f"{marker} {analysis.name}")
            print(f"     Path: {analysis.path.relative_to(project_root)}")
            print(f"     Production Ready: {analysis.production_ready_score:.1f}/10")
            print(f"     System Alignment: {analysis.system_alignment_score:.1f}/10")
            print(f"     Deduplication Functions: {len(analysis.deduplication_functions)}")
            if analysis == dedup_workflow:
                print(f"     Key Functions: {', '.join(analysis.deduplication_functions[:5])}")
            print()
    else:
        print("  ❌ No deduplication workflows found\n")
    
    # Step 3: Deploy
    print(f"{'='*80}")
    print("STEP 3: DEPLOYMENT VIA GOOGLE APPS SCRIPT API")
    print(f"{'='*80}\n")
    
    if not relation_script and not dedup_workflow:
        print("❌ No scripts identified for deployment")
        return
    
    try:
        deployer = GASAPIDirectDeployment()
        
        # List existing projects
        existing_projects = deployer.list_projects()
        print(f"📋 Found {len(existing_projects)} existing Apps Script projects")
        if existing_projects:
            print("   Existing projects:")
            for proj in existing_projects[:5]:
                print(f"     - {proj.get('name', 'Unnamed')} ({proj.get('id', 'N/A')})")
            if len(existing_projects) > 5:
                print(f"     ... and {len(existing_projects) - 5} more")
        print()
        
        deployment_results = {}
        
        # Deploy relation script
        if relation_script:
            project_path = relation_script.path.parent
            project_name = f"{project_path.name}_RelationPopulation"
            
            print(f"📤 Deploying Relation/Population Script:")
            print(f"   Source: {relation_script.path.relative_to(project_root)}")
            print(f"   Project Name: {project_name}")
            
            files = deployer.read_project_files(project_path)
            print(f"   Files to deploy: {', '.join(files.keys())}")
            
            script_id = deployer.create_project(project_name, files)
            if script_id:
                deployment_results[project_name] = {
                    'script_id': script_id,
                    'success': True,
                    'source_path': str(relation_script.path.relative_to(project_root)),
                    'files_deployed': list(files.keys())
                }
                print(f"   ✅ Successfully created project: {script_id}")
                print(f"   🔗 View at: https://script.google.com/d/{script_id}/edit")
            else:
                deployment_results[project_name] = {'success': False}
                print(f"   ❌ Failed to create project")
            print()
        
        # Deploy deduplication workflow
        if dedup_workflow:
            project_path = dedup_workflow.path.parent
            project_name = f"{project_path.name}_Deduplication"
            
            print(f"📤 Deploying Deduplication Workflow:")
            print(f"   Source: {dedup_workflow.path.relative_to(project_root)}")
            print(f"   Project Name: {project_name}")
            
            files = deployer.read_project_files(project_path)
            print(f"   Files to deploy: {', '.join(files.keys())}")
            
            script_id = deployer.create_project(project_name, files)
            if script_id:
                deployment_results[project_name] = {
                    'script_id': script_id,
                    'success': True,
                    'source_path': str(dedup_workflow.path.relative_to(project_root)),
                    'files_deployed': list(files.keys())
                }
                print(f"   ✅ Successfully created project: {script_id}")
                print(f"   🔗 View at: https://script.google.com/d/{script_id}/edit")
            else:
                deployment_results[project_name] = {'success': False}
                print(f"   ❌ Failed to create project")
            print()
        
        # Final summary
        print(f"{'='*80}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*80}\n")
        
        successful = sum(1 for r in deployment_results.values() if r.get('success'))
        total = len(deployment_results)
        
        print(f"Total Projects: {total}")
        print(f"Successful: {successful}")
        print(f"Failed: {total - successful}\n")
        
        print("Deployment Details:")
        for name, result in deployment_results.items():
            status = "✅" if result.get('success') else "❌"
            script_id = result.get('script_id', 'N/A')
            print(f"  {status} {name}")
            print(f"     Script ID: {script_id}")
            if result.get('source_path'):
                print(f"     Source: {result['source_path']}")
            if result.get('files_deployed'):
                print(f"     Files: {', '.join(result['files_deployed'])}")
            print()
        
        # Save results to JSON
        results_file = project_root / 'gas_deployment_results.json'
        results_data = {
            'execution_time': datetime.now().isoformat(),
            'relation_script': {
                'selected': str(relation_script.path.relative_to(project_root)) if relation_script else None,
                'score': relation_script.production_ready_score + relation_script.system_alignment_score if relation_script else None
            },
            'deduplication_workflow': {
                'selected': str(dedup_workflow.path.relative_to(project_root)) if dedup_workflow else None,
                'score': dedup_workflow.production_ready_score + dedup_workflow.system_alignment_score if dedup_workflow else None
            },
            'deployment_results': deployment_results,
            'existing_projects_count': len(existing_projects)
        }
        
        with open(results_file, 'w') as f:
            json.dump(results_data, f, indent=2)
        
        print(f"📄 Results saved to: {results_file.relative_to(project_root)}")
        print("\n✅ Deployment process complete!")
        
    except FileNotFoundError as e:
        print(f"\n❌ Credentials not found: {e}")
        print("\nTo deploy, you need OAuth credentials:")
        print("1. Go to Google Cloud Console")
        print("2. Create OAuth 2.0 credentials")
        print("3. Save as credentials/gas_api_credentials.json")
        print("\nOr provide path via --credentials argument")
    except Exception as e:
        import traceback
        print(f"\n❌ Deployment failed: {e}")
        print("\nFull error:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
