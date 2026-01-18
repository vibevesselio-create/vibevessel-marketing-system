#!/usr/bin/env python3
"""
Analyze Notion scripts database for non-compliant items similar to the archived consolidation proposal.
"""

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from notion_client import Client
from dotenv import load_dotenv

# Load environment variables
env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    # Try alternative locations
    load_dotenv(project_root / 'shared' / 'api.env')

notion = Client(auth=os.getenv('NOTION_API_KEY'))
scripts_db_id = '26ce73616c278178bc77f43aff00eddf'

def check_file_exists(file_path_str):
    """Check if a file path exists"""
    if not file_path_str or file_path_str == 'None':
        return False
    
    # Try different path formats
    clean_path = str(file_path_str).replace('file://', '')
    paths_to_check = [
        clean_path,
        project_root / clean_path.lstrip('/'),
        project_root / clean_path,
    ]
    
    for path in paths_to_check:
        p = Path(path)
        if p.exists() and p.is_file():
            return True
    
    return False

def analyze_scripts():
    """Analyze scripts in Notion database for non-compliance"""
    
    # Query for 'In Development' status
    print("Querying Notion scripts database...")
    results = notion.databases.query(
        database_id=scripts_db_id,
        filter={
            'property': 'Status',
            'status': {'equals': '2-In Development'}
        },
        page_size=100
    )
    
    print(f'Found {len(results["results"])} scripts with status "2-In Development"\n')
    print('=' * 80)
    
    non_compliant = []
    
    for page in results['results']:
        page_id = page['id']
        title_prop = page['properties'].get('Script Name', {}).get('title', [])
        title = title_prop[0]['plain_text'] if title_prop else 'No title'
        
        # Get properties
        file_path_prop = page['properties'].get('File Path', {})
        file_path = file_path_prop.get('url', '') if file_path_prop else ''
        
        script_path_prop = page['properties'].get('Script Path', {})
        script_path_text = ''
        if script_path_prop:
            script_path_rich = script_path_prop.get('rich_text', [])
            script_path_text = script_path_rich[0]['plain_text'] if script_path_rich else ''
        
        description_prop = page['properties'].get('Description', {})
        desc_text = ''
        if description_prop:
            desc_rich = description_prop.get('rich_text', [])
            desc_text = desc_rich[0]['plain_text'] if desc_rich else ''
        
        # Combine text for analysis
        combined_text = f"{title} {desc_text}".lower()
        
        # Check if file exists
        file_exists = check_file_exists(file_path) or check_file_exists(script_path_text)
        
        # Check for consolidation keywords
        consolidation_keywords = ['consolidat', 'merge', 'combine', 'unified', 'integrated', 'consolidated']
        is_consolidation = any(keyword in combined_text for keyword in consolidation_keywords)
        
        # Check for proposal keywords
        proposal_keywords = ['proposal', 'proposed', 'plan', 'design', 'specification', 'planned']
        is_proposal = any(keyword in combined_text for keyword in proposal_keywords)
        
        # Check if it's a variation
        variation_of = page['properties'].get('Variation Of', {}).get('relation', [])
        is_variation = len(variation_of) > 0
        
        # Check if it mentions other scripts (like consolidation)
        script_mentions = ['project manager bot', 'drivesheetsync', 'combining', 'merging', 'consolidating']
        mentions_other_scripts = any(mention in combined_text for mention in script_mentions)
        
        # Check for "should be archived" indicators
        archive_keywords = ['archive', 'deprecated', 'obsolete', 'replaced', 'superseded']
        should_archive = any(keyword in combined_text for keyword in archive_keywords)
        
        # Build issues list
        issues = []
        if not file_exists and not is_proposal:
            issues.append('No file found')
        if is_consolidation:
            issues.append('Consolidation proposal')
        if is_proposal and not file_exists:
            issues.append('Proposal without implementation')
        if mentions_other_scripts and is_consolidation:
            issues.append('Unnecessary consolidation')
        if should_archive:
            issues.append('Should be archived')
        if is_variation and not file_exists:
            issues.append('Variation without implementation')
        
        # Check if it's similar to the archived one (consolidation of working scripts)
        is_similar_to_archived = (
            is_consolidation and 
            mentions_other_scripts and 
            not file_exists
        )
        
        if issues or is_similar_to_archived:
            non_compliant.append({
                'title': title,
                'id': page_id,
                'url': f"https://www.notion.so/{page_id.replace('-', '')}",
                'issues': issues,
                'file_path': file_path or script_path_text or 'None',
                'file_exists': file_exists,
                'description': desc_text[:200] + '...' if len(desc_text) > 200 else desc_text,
                'is_consolidation': is_consolidation,
                'is_proposal': is_proposal,
                'is_variation': is_variation,
                'mentions_other_scripts': mentions_other_scripts,
                'similar_to_archived': is_similar_to_archived
            })
    
    return non_compliant

def main():
    """Main execution"""
    print("Analyzing non-compliant scripts in Notion database...\n")
    
    non_compliant = analyze_scripts()
    
    print(f'\nFound {len(non_compliant)} potentially non-compliant scripts:\n')
    print('=' * 80)
    
    # Group by issue type
    by_issue = {}
    for item in non_compliant:
        for issue in item['issues']:
            if issue not in by_issue:
                by_issue[issue] = []
            by_issue[issue].append(item)
    
    # Print summary by issue type
    for issue_type, items in sorted(by_issue.items()):
        print(f"\n{issue_type}: {len(items)} scripts")
        print("-" * 80)
        for item in items[:5]:  # Show first 5
            print(f"  • {item['title']}")
            print(f"    URL: {item['url']}")
            print(f"    File Exists: {item['file_exists']}")
            if item['similar_to_archived']:
                print(f"    ⚠️  SIMILAR TO ARCHIVED CONSOLIDATION")
            print()
    
    # Print all non-compliant scripts
    print("\n" + "=" * 80)
    print("ALL NON-COMPLIANT SCRIPTS:")
    print("=" * 80)
    
    for idx, item in enumerate(non_compliant, 1):
        print(f"\n{idx}. {item['title']}")
        print(f"   ID: {item['id']}")
        print(f"   URL: {item['url']}")
        print(f"   Issues: {', '.join(item['issues'])}")
        print(f"   File Path: {item['file_path']}")
        print(f"   File Exists: {item['file_exists']}")
        if item['description']:
            print(f"   Description: {item['description'][:150]}...")
        if item['similar_to_archived']:
            print(f"   ⚠️  SIMILAR TO ARCHIVED CONSOLIDATION PROPOSAL")
    
    # Save results
    output_file = project_root / 'non_compliant_scripts_analysis.json'
    with open(output_file, 'w') as f:
        json.dump({
            'analysis_date': datetime.now().isoformat(),
            'total_found': len(non_compliant),
            'scripts': non_compliant
        }, f, indent=2)
    
    print(f'\n\nFull analysis saved to: {output_file}')
    print(f'\nTotal non-compliant scripts found: {len(non_compliant)}')

if __name__ == '__main__':
    main()

