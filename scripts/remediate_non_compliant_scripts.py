#!/usr/bin/env python3
"""
Remediate non-compliant scripts in Notion database.
Performs analysis and archives/updates scripts to bring them to compliance.
"""

import os
import sys
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, List, Any

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
    load_dotenv(project_root / 'shared' / 'api.env')

notion = Client(auth=os.getenv('NOTION_API_KEY'))
scripts_db_id = '26ce73616c278178bc77f43aff00eddf'

def check_file_exists(file_path_str):
    """Check if a file path exists"""
    if not file_path_str or file_path_str == 'None':
        return False
    
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

def analyze_script_for_archival(page: Dict) -> Dict[str, Any]:
    """Analyze a script page to determine if it should be archived"""
    
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
    
    # Get status
    status_prop = page['properties'].get('Status', {})
    status = status_prop.get('status', {}).get('name', '') if status_prop else ''
    
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
    
    # Check if it mentions other scripts
    script_mentions = ['project manager bot', 'drivesheetsync', 'combining', 'merging', 'consolidating']
    mentions_other_scripts = any(mention in combined_text for mention in script_mentions)
    
    # Check for archive keywords
    archive_keywords = ['archive', 'deprecated', 'obsolete', 'replaced', 'superseded']
    should_archive = any(keyword in combined_text for keyword in archive_keywords)
    
    # Determine action
    action = 'keep'
    reason = ''
    
    # Priority 1: Explicitly marked for archiving
    if should_archive:
        action = 'archive'
        reason = 'Explicitly marked for archiving'
    
    # Priority 2: Consolidation proposals without implementation
    elif is_consolidation and not file_exists:
        action = 'archive'
        reason = 'Consolidation proposal without implementation (similar to archived PMB+CSV sync)'
    
    # Priority 3: Proposals without implementation (older than 30 days)
    elif is_proposal and not file_exists:
        created_time = page.get('created_time', '')
        if created_time:
            from dateutil import parser
            created_date = parser.parse(created_time)
            days_old = (datetime.now(created_date.tzinfo) - created_date).days
            if days_old > 30:
                action = 'archive'
                reason = f'Proposal without implementation ({days_old} days old)'
            else:
                action = 'update_status'
                reason = f'Proposal without implementation ({days_old} days old) - move to Planned'
    
    # Priority 4: No file found and status is "In Development" - only archive if very old AND consolidation/proposal
    elif not file_exists and status == '2-In Development':
        created_time = page.get('created_time', '')
        if created_time:
            from dateutil import parser
            created_date = parser.parse(created_time)
            days_old = (datetime.now(created_date.tzinfo) - created_date).days
            # Only archive if it's a consolidation/proposal AND very old (>90 days)
            if (is_consolidation or is_proposal) and days_old > 90:
                action = 'archive'
                reason = f'Consolidation/proposal without implementation ({days_old} days old)'
            elif days_old > 180:  # Very old scripts (>6 months) with no file
                action = 'archive'
                reason = f'No file found, marked "In Development" for {days_old} days'
            else:
                # Keep as-is for now - might be legitimate scripts without File Path set
                action = 'keep'
                reason = f'No file found but may be legitimate ({days_old} days old)'
    
    return {
        'page_id': page_id,
        'title': title,
        'url': f"https://www.notion.so/{page_id.replace('-', '')}",
        'action': action,
        'reason': reason,
        'file_exists': file_exists,
        'is_consolidation': is_consolidation,
        'is_proposal': is_proposal,
        'mentions_other_scripts': mentions_other_scripts,
        'status': status,
        'description': desc_text[:200]
    }

def archive_page(page_id: str, reason: str) -> bool:
    """Archive a Notion page"""
    try:
        notion.pages.update(
            page_id=page_id,
            archived=True
        )
        print(f"  ✅ Archived: {page_id}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to archive {page_id}: {e}")
        return False

def update_status_to_planned(page_id: str) -> bool:
    """Update status to '1-Planned'"""
    try:
        # Get the status property ID first
        page = notion.pages.retrieve(page_id)
        status_prop = page['properties'].get('Status', {})
        
        notion.pages.update(
            page_id=page_id,
            properties={
                'Status': {
                    'status': {
                        'name': '1-Planned'
                    }
                }
            }
        )
        print(f"  ✅ Updated status to 'Planned': {page_id}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to update status for {page_id}: {e}")
        return False

def main():
    """Main execution"""
    print("=" * 80)
    print("NON-COMPLIANT SCRIPTS REMEDIATION")
    print("=" * 80)
    print()
    
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
    
    # Analyze each script
    actions = {
        'archive': [],
        'update_status': [],
        'keep': []
    }
    
    print("Analyzing scripts...")
    for page in results['results']:
        analysis = analyze_script_for_archival(page)
        actions[analysis['action']].append(analysis)
    
    # Print summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Scripts to archive: {len(actions['archive'])}")
    print(f"Scripts to update status: {len(actions['update_status'])}")
    print(f"Scripts to keep: {len(actions['keep'])}")
    
    # Show scripts to archive
    if actions['archive']:
        print("\n" + "=" * 80)
        print("SCRIPTS TO ARCHIVE")
        print("=" * 80)
        for item in actions['archive']:
            print(f"\n• {item['title']}")
            print(f"  URL: {item['url']}")
            print(f"  Reason: {item['reason']}")
            print(f"  Consolidation: {item['is_consolidation']}")
            print(f"  File Exists: {item['file_exists']}")
    
    # Show scripts to update status
    if actions['update_status']:
        print("\n" + "=" * 80)
        print("SCRIPTS TO UPDATE STATUS")
        print("=" * 80)
        for item in actions['update_status']:
            print(f"\n• {item['title']}")
            print(f"  URL: {item['url']}")
            print(f"  Reason: {item['reason']}")
    
    # Ask for confirmation
    print("\n" + "=" * 80)
    print("REMEDIATION ACTIONS")
    print("=" * 80)
    
    if actions['archive']:
        print(f"\nWill archive {len(actions['archive'])} scripts...")
        for item in actions['archive']:
            archive_page(item['page_id'], item['reason'])
    
    if actions['update_status']:
        print(f"\nWill update status for {len(actions['update_status'])} scripts...")
        for item in actions['update_status']:
            update_status_to_planned(item['page_id'])
    
    # Save results
    output = {
        'remediation_date': datetime.now().isoformat(),
        'total_analyzed': len(results['results']),
        'archived': len(actions['archive']),
        'status_updated': len(actions['update_status']),
        'kept': len(actions['keep']),
        'archived_scripts': actions['archive'],
        'status_updated_scripts': actions['update_status']
    }
    
    output_file = project_root / 'scripts_remediation_results.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\nRemediation complete!")
    print(f"Results saved to: {output_file}")

if __name__ == '__main__':
    try:
        from dateutil import parser
    except ImportError:
        print("ERROR: python-dateutil not installed. Install with: pip install python-dateutil")
        sys.exit(1)
    
    main()

