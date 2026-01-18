#!/usr/bin/env python3
"""
Issues+Questions Database Cleanup Script
========================================
Archives duplicate resolved issues to clean up the database.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from dotenv import load_dotenv
load_dotenv()

from notion_client import Client

def main():
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token
        token = get_notion_token()
    except ImportError:
        token = os.getenv('NOTION_TOKEN')
    if not token:
        print("ERROR: NOTION_TOKEN not set")
        return 1

    client = Client(auth=token)
    ISSUES_DB_ID = '229e73616c27808ebf06c202b10b5166'

    # Get database
    db = client.databases.retrieve(database_id=ISSUES_DB_ID)
    data_sources = db.get('data_sources', [])
    data_source_id = data_sources[0].get('id') if data_sources else None

    # Query all issues
    print('=== Issues+Questions Database Cleanup ===\n')

    if data_source_id:
        response = client.data_sources.query(
            data_source_id=data_source_id,
            page_size=500
        )
    else:
        response = client.databases.query(
            database_id=ISSUES_DB_ID,
            page_size=500
        )

    issues = response.get('results', [])
    print(f'Total issues: {len(issues)}')

    # Find duplicate "Execution-Logs Schema: Type Mismatches" entries that are Resolved
    target_title_prefix = "Execution-Logs Schema: Type Mismatches"
    duplicates_to_archive = []

    for issue in issues:
        props = issue.get('properties', {})

        # Get title
        name_prop = props.get('Name', {})
        if name_prop.get('title'):
            title = name_prop['title'][0].get('plain_text', '') if name_prop['title'] else ''
        else:
            title = ''

        # Get status
        status_prop = props.get('Status', {})
        if status_prop.get('type') == 'status' and status_prop.get('status'):
            status = status_prop['status'].get('name', '')
        else:
            status = ''

        if title.startswith(target_title_prefix) and status == 'Resolved':
            duplicates_to_archive.append({
                'id': issue.get('id'),
                'title': title
            })

    print(f'Found {len(duplicates_to_archive)} resolved duplicate entries to archive')

    # Keep the first one, archive the rest
    if len(duplicates_to_archive) > 1:
        keep = duplicates_to_archive[0]
        to_archive = duplicates_to_archive[1:]

        print(f'Keeping: {keep["title"][:50]}... ({keep["id"][:8]}...)')
        print(f'Archiving {len(to_archive)} duplicates...')

        archived_count = 0
        for item in to_archive:
            try:
                client.pages.update(
                    page_id=item['id'],
                    archived=True
                )
                archived_count += 1
                if archived_count % 10 == 0:
                    print(f'  Archived {archived_count}/{len(to_archive)}...')
            except Exception as e:
                print(f'  Error archiving {item["id"][:8]}: {e}')

        print(f'Successfully archived {archived_count} duplicate entries')
    else:
        print('No duplicates to archive')

    return 0

if __name__ == '__main__':
    sys.exit(main())
