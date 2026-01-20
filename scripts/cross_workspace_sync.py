#!/usr/bin/env python3
"""
Cross-Workspace Database Sync
=============================

Syncs databases from the primary (Seren Internal) workspace to client workspaces
based on the system-environments and system-databases configuration in Notion.

Usage:
    python scripts/cross_workspace_sync.py --client "VibeVessel Client Workspace" --dry-run
    python scripts/cross_workspace_sync.py --client "VibeVessel Client Workspace" --execute

Configuration is read from Notion:
    - system-environments: Contains client workspace tokens and linked databases
    - system-databases: Contains database metadata and sync configuration

Author: Cursor MM1 Agent
Date: 2026-01-19
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests

# Add shared_core to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_core.notion.token_manager import get_notion_token
from shared_core.logging import setup_logging

# Global logger - initialized in main()
logger = None

# Database IDs
SYSTEM_ENVIRONMENTS_DB_ID = '26ce7361-6c27-8195-8726-f6aeb5b9cd95'
SYSTEM_DATABASES_DB_ID = '299e7361-6c27-80f1-b264-f020e4a4b041'

# Property types that cannot be synced between workspaces
SKIP_PROPERTY_TYPES = {'relation', 'rollup', 'created_by', 'last_edited_by', 
                       'created_time', 'last_edited_time', 'formula', 'unique_id'}

# Block fields to strip when copying blocks to a new page
BLOCK_STRIP_FIELDS = {'id', 'created_time', 'created_by', 'last_edited_time', 
                      'last_edited_by', 'parent', 'archived', 'has_children', 
                      'object', 'request_id'}


def sanitize_select_options(options: List[Dict]) -> List[Dict]:
    """Sanitize select/multi_select options - remove commas which are not allowed."""
    sanitized = []
    seen_names = set()
    
    for opt in options:
        name = opt.get('name', '')
        # Replace commas with semicolons
        name = name.replace(',', ';')
        # Skip empty names or duplicates
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        
        sanitized.append({
            'name': name,
            'color': opt.get('color', 'default')
        })
    
    return sanitized


def has_property_value(prop_val: Dict) -> bool:
    """Check if a Notion property value is populated (not empty/null)."""
    ptype = prop_val.get('type', '')
    
    if ptype == 'title':
        return bool(prop_val.get('title', []))
    elif ptype == 'rich_text':
        return bool(prop_val.get('rich_text', []))
    elif ptype == 'number':
        return prop_val.get('number') is not None
    elif ptype == 'select':
        return prop_val.get('select') is not None
    elif ptype == 'multi_select':
        return bool(prop_val.get('multi_select', []))
    elif ptype == 'date':
        return prop_val.get('date') is not None
    elif ptype == 'checkbox':
        # Checkbox always has a value (true/false), but we only count True as "populated"
        return prop_val.get('checkbox', False) is True
    elif ptype == 'url':
        return prop_val.get('url') is not None
    elif ptype == 'email':
        return prop_val.get('email') is not None
    elif ptype == 'phone_number':
        return prop_val.get('phone_number') is not None
    elif ptype == 'files':
        return bool(prop_val.get('files', []))
    elif ptype == 'relation':
        return bool(prop_val.get('relation', []))
    elif ptype == 'status':
        return prop_val.get('status') is not None
    
    return False


def build_property_schema(prop_def: Dict) -> Optional[Dict]:
    """Build a property schema definition for database creation/update."""
    prop_type = prop_def.get('type', '')
    
    if prop_type in SKIP_PROPERTY_TYPES:
        return None
    
    if prop_type == 'title':
        return {'title': {}}
    elif prop_type == 'rich_text':
        return {'rich_text': {}}
    elif prop_type == 'number':
        return {'number': prop_def.get('number', {})}
    elif prop_type == 'select':
        sel_def = prop_def.get('select', {})
        options = sel_def.get('options', [])
        # Sanitize and limit options
        options = sanitize_select_options(options)[:100]
        return {'select': {'options': options} if options else {}}
    elif prop_type == 'multi_select':
        ms_def = prop_def.get('multi_select', {})
        options = ms_def.get('options', [])
        # Sanitize and limit options
        options = sanitize_select_options(options)[:100]
        return {'multi_select': {'options': options} if options else {}}
    elif prop_type == 'date':
        return {'date': {}}
    elif prop_type == 'checkbox':
        return {'checkbox': {}}
    elif prop_type == 'url':
        return {'url': {}}
    elif prop_type == 'email':
        return {'email': {}}
    elif prop_type == 'phone_number':
        return {'phone_number': {}}
    elif prop_type == 'files':
        return {'files': {}}
    elif prop_type == 'status':
        # Status properties can't be created via API - Notion auto-creates them
        return None
    
    return None


def get_page_blocks(page_id: str, headers: Dict) -> List[Dict]:
    """Retrieve all blocks from a page, handling pagination."""
    blocks = []
    cursor = None
    
    while True:
        url = f'https://api.notion.com/v1/blocks/{page_id}/children'
        params = {'page_size': 100}
        if cursor:
            params['start_cursor'] = cursor
        
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            logger.debug(f'Failed to get blocks for {page_id}: {resp.status_code}')
            break
        
        data = resp.json()
        blocks.extend(data.get('results', []))
        
        if not data.get('has_more'):
            break
        cursor = data.get('next_cursor')
    
    return blocks


def clean_block_for_copy(block: Dict) -> Optional[Dict]:
    """Clean a block for copying to a new page, removing server-generated fields."""
    block_type = block.get('type', '')
    
    # Skip unsupported or problematic block types
    if block_type in ('unsupported', 'child_page', 'child_database', 'synced_block', 
                      'link_to_page', 'table_of_contents'):
        return None
    
    # Create cleaned block with only the fields we need
    cleaned = {'type': block_type}
    
    # Copy the block content (the key matching the type)
    if block_type in block:
        cleaned[block_type] = block[block_type]
    
    return cleaned


class CrossWorkspaceTransfer:
    """
    Handles one-way transfer/relocation of databases between workspaces.
    
    Unlike sync, this:
    - Recreates relation properties pointing to equivalent databases in target workspace
    - Creates related databases if they don't exist (recursive create-if-not-found)
    - Maps source page IDs to target page IDs for relation values
    - Transfers all items with their full content
    """
    
    def __init__(
        self, 
        source_token: str, 
        target_token: str,
        target_parent_page_id: str,
        dry_run: bool = True
    ):
        self.source_token = source_token
        self.target_token = target_token
        self.target_parent_page_id = target_parent_page_id
        self.dry_run = dry_run
        
        self.source_headers = {
            'Authorization': f'Bearer {source_token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        self.target_headers = {
            'Authorization': f'Bearer {target_token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        
        # Mapping of source database IDs to target database IDs
        self.db_id_map: Dict[str, str] = {}
        # Mapping of source page IDs to target page IDs (for relations)
        self.page_id_map: Dict[str, str] = {}
        # Cache of target databases by name (lowercase)
        self.target_dbs_cache: Dict[str, str] = {}
        # Track databases being processed to avoid infinite recursion
        self.processing_dbs: set = set()
        
        self.stats = {
            'databases_created': 0,
            'databases_found': 0,
            'items_transferred': 0,
            'relations_mapped': 0,
            'errors': []
        }
    
    def _get_database_schema(self, db_id: str, headers: Dict) -> Optional[Dict]:
        """Get database schema from either workspace."""
        resp = requests.get(
            f'https://api.notion.com/v1/databases/{db_id}',
            headers=headers
        )
        if resp.status_code != 200:
            logger.error(f'Failed to get database schema {db_id}: {resp.json()}')
            return None
        return resp.json()
    
    def _get_database_name(self, schema: Dict) -> str:
        """Extract database name from schema."""
        title = schema.get('title', [])
        if title:
            return title[0].get('plain_text', 'Untitled')
        return 'Untitled'
    
    def _refresh_target_dbs_cache(self):
        """Refresh cache of databases in target workspace."""
        resp = requests.post(
            'https://api.notion.com/v1/search',
            headers=self.target_headers,
            json={'filter': {'property': 'object', 'value': 'database'}, 'page_size': 100}
        )
        if resp.status_code == 200:
            self.target_dbs_cache = {
                db.get('title', [{}])[0].get('plain_text', '').lower(): db['id']
                for db in resp.json().get('results', [])
                if db.get('title')
            }
            logger.info(f'Cached {len(self.target_dbs_cache)} databases from target workspace')
    
    def _find_or_create_target_database(
        self, 
        source_db_id: str,
        source_schema: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Find or create equivalent database in target workspace.
        Returns target database ID.
        """
        # Check if already mapped
        if source_db_id in self.db_id_map:
            return self.db_id_map[source_db_id]
        
        # Prevent infinite recursion
        if source_db_id in self.processing_dbs:
            logger.warning(f'Circular dependency detected for database {source_db_id}')
            return None
        
        self.processing_dbs.add(source_db_id)
        
        try:
            # Get source schema if not provided
            if not source_schema:
                source_schema = self._get_database_schema(source_db_id, self.source_headers)
                if not source_schema:
                    return None
            
            db_name = self._get_database_name(source_schema)
            logger.info(f'Finding/creating target database: {db_name}')
            
            # Check if exists in target by name
            target_db_id = self.target_dbs_cache.get(db_name.lower())
            
            if target_db_id:
                logger.info(f'  Found existing database: {target_db_id[:8]}...')
                self.db_id_map[source_db_id] = target_db_id
                self.stats['databases_found'] += 1
                return target_db_id
            
            # Need to create - but first process relation dependencies
            if self.dry_run:
                logger.info(f'  [DRY RUN] Would create database: {db_name}')
                return None
            
            # USAGE-DRIVEN: Create database with MINIMAL properties
            # Only include title - other properties will be added based on actual item data
            # This prevents bloating the database with unused properties
            
            # Find the title property name
            title_prop_name = 'Name'  # Default
            for prop_name, prop_def in source_schema.get('properties', {}).items():
                if prop_def.get('type') == 'title':
                    title_prop_name = prop_name
                    break
            
            properties = {
                title_prop_name: {'title': {}}
            }
            
            logger.info(f'  Creating database with minimal schema (title only)')
            
            # Create the database with just title
            payload = {
                'parent': {'type': 'page_id', 'page_id': self.target_parent_page_id},
                'title': [{'type': 'text', 'text': {'content': db_name}}],
                'properties': properties
            }
            
            resp = requests.post(
                'https://api.notion.com/v1/databases',
                headers=self.target_headers,
                json=payload
            )
            
            if resp.status_code != 200:
                logger.error(f'  Failed to create database: {resp.json()}')
                return None
            
            result = resp.json()
            target_db_id = result['id']
            db_url = result.get('url', '')
            
            logger.info(f'  Created database: {db_name}')
            logger.info(f'    ID: {target_db_id}')
            logger.info(f'    URL: {db_url}')
            
            # Update caches
            self.db_id_map[source_db_id] = target_db_id
            self.target_dbs_cache[db_name.lower()] = target_db_id
            self.stats['databases_created'] += 1
            
            # Note: Relation properties will be added later based on actual usage
            # in transfer_database() - not added here to avoid unused properties
            
            return target_db_id
            
        finally:
            self.processing_dbs.discard(source_db_id)
    
    def _add_relation_properties(self, target_db_id: str, relation_props: Dict[str, Dict]):
        """Add relation properties to a database, creating related databases if needed."""
        props_to_add = {}
        
        for prop_name, prop_def in relation_props.items():
            rel_config = prop_def.get('relation', {})
            source_related_db_id = rel_config.get('database_id')
            
            if not source_related_db_id:
                continue
            
            # Find or create the related database in target
            target_related_db_id = self._find_or_create_target_database(source_related_db_id)
            
            if not target_related_db_id:
                logger.warning(f'  Could not resolve related database for property: {prop_name}')
                continue
            
            # Build relation property definition
            rel_type = rel_config.get('type', 'single_property')
            props_to_add[prop_name] = {
                'relation': {
                    'database_id': target_related_db_id,
                    'type': rel_type
                }
            }
            
            # Handle dual_property (two-way relation)
            if rel_type == 'dual_property':
                synced_prop = rel_config.get('dual_property', {}).get('synced_property_name')
                if synced_prop:
                    props_to_add[prop_name]['relation']['dual_property'] = {
                        'synced_property_name': synced_prop
                    }
            
            logger.info(f'  Adding relation property: {prop_name} -> {target_related_db_id[:8]}...')
        
        if props_to_add:
            resp = requests.patch(
                f'https://api.notion.com/v1/databases/{target_db_id}',
                headers=self.target_headers,
                json={'properties': props_to_add}
            )
            
            if resp.status_code != 200:
                logger.error(f'  Failed to add relation properties: {resp.json()}')
            else:
                logger.info(f'  Added {len(props_to_add)} relation properties')
    
    def _query_all_items(self, db_id: str, headers: Dict, max_items: Optional[int] = None) -> List[Dict]:
        """Query items from a database with pagination."""
        items = []
        cursor = None
        page_num = 0
        
        while True:
            page_num += 1
            # Calculate how many more items we need
            if max_items:
                remaining = max_items - len(items)
                if remaining <= 0:
                    break
                page_size = min(100, remaining)
            else:
                page_size = 100
            
            payload = {'page_size': page_size}
            if cursor:
                payload['start_cursor'] = cursor
            
            logger.debug(f'  Querying page {page_num}...', {'db_id': db_id[:8], 'items_so_far': len(items)})
            
            resp = requests.post(
                f'https://api.notion.com/v1/databases/{db_id}/query',
                headers=headers,
                json=payload
            )
            
            if resp.status_code != 200:
                logger.error(f'Failed to query database {db_id}: {resp.json()}')
                break
            
            data = resp.json()
            batch = data.get('results', [])
            items.extend(batch)
            logger.debug(f'  Page {page_num}: got {len(batch)} items (total: {len(items)})')
            
            # Stop if we have enough items
            if max_items and len(items) >= max_items:
                break
            
            if not data.get('has_more'):
                break
            cursor = data.get('next_cursor')
        
        return items
    
    def _copy_property_value(
        self, 
        prop_name: str, 
        prop_val: Dict,
        target_props: set
    ) -> Optional[Dict]:
        """Copy a property value, handling relations with ID mapping."""
        prop_type = prop_val.get('type', '')
        
        # Skip if not in target schema
        if prop_name not in target_props:
            return None
        
        # Skip types that can't be set
        if prop_type in ('created_by', 'last_edited_by', 'created_time', 
                         'last_edited_time', 'formula', 'unique_id', 'rollup'):
            return None
        
        if prop_type == 'title':
            return {'title': prop_val.get('title', [])}
        elif prop_type == 'rich_text':
            return {'rich_text': prop_val.get('rich_text', [])}
        elif prop_type == 'number':
            return {'number': prop_val.get('number')}
        elif prop_type == 'select':
            if prop_val.get('select'):
                return {'select': {'name': prop_val['select'].get('name', '')}}
        elif prop_type == 'multi_select':
            if prop_val.get('multi_select'):
                return {'multi_select': [{'name': s.get('name', '')} for s in prop_val['multi_select']]}
        elif prop_type == 'date':
            if prop_val.get('date'):
                return {'date': prop_val['date']}
        elif prop_type == 'checkbox':
            return {'checkbox': prop_val.get('checkbox', False)}
        elif prop_type == 'url':
            return {'url': prop_val.get('url')}
        elif prop_type == 'email':
            return {'email': prop_val.get('email')}
        elif prop_type == 'phone_number':
            return {'phone_number': prop_val.get('phone_number')}
        elif prop_type == 'status':
            if prop_val.get('status'):
                return {'status': {'name': prop_val['status'].get('name', '')}}
        elif prop_type == 'files':
            if prop_val.get('files'):
                files_list = []
                for f in prop_val['files']:
                    if f.get('type') == 'external':
                        files_list.append({
                            'type': 'external',
                            'name': f.get('name', ''),
                            'external': {'url': f['external']['url']}
                        })
                if files_list:
                    return {'files': files_list}
        elif prop_type == 'relation':
            # Map source page IDs to target page IDs
            if prop_val.get('relation'):
                mapped_relations = []
                for rel in prop_val['relation']:
                    source_page_id = rel.get('id')
                    if source_page_id and source_page_id in self.page_id_map:
                        mapped_relations.append({'id': self.page_id_map[source_page_id]})
                        self.stats['relations_mapped'] += 1
                if mapped_relations:
                    return {'relation': mapped_relations}
        
        return None
    
    def _copy_blocks_to_page(self, source_page_id: str, target_page_id: str) -> int:
        """Copy all blocks from source page to target page."""
        source_blocks = get_page_blocks(source_page_id, self.source_headers)
        
        if not source_blocks:
            return 0
        
        cleaned_blocks = []
        for block in source_blocks:
            cleaned = clean_block_for_copy(block)
            if cleaned:
                cleaned_blocks.append(cleaned)
        
        if not cleaned_blocks:
            return 0
        
        total_copied = 0
        for i in range(0, len(cleaned_blocks), 100):
            batch = cleaned_blocks[i:i+100]
            
            resp = requests.patch(
                f'https://api.notion.com/v1/blocks/{target_page_id}/children',
                headers=self.target_headers,
                json={'children': batch}
            )
            
            if resp.status_code == 200:
                total_copied += len(batch)
            else:
                logger.warning(f'Failed to copy blocks batch: {resp.json().get("message", "Unknown")}')
                break
        
        return total_copied
    
    def transfer_database(
        self, 
        source_db_id: str,
        include_relations: bool = True,
        max_items: Optional[int] = None
    ) -> Dict:
        """
        Transfer a database from source to target workspace.
        
        Args:
            source_db_id: The source database ID
            include_relations: Whether to recreate relations and transfer related data
            max_items: Maximum number of items to transfer (None for all)
        
        Returns:
            Transfer statistics
        """
        logger.info('=' * 60)
        logger.info('CROSS-WORKSPACE DATABASE TRANSFER')
        logger.info('=' * 60)
        logger.info(f'Mode: {"DRY RUN" if self.dry_run else "EXECUTE"}')
        logger.info(f'Source token: ...{self.source_token[-5:]}')
        logger.info(f'Target token: ...{self.target_token[-5:]}')
        logger.info(f'Target parent page: {self.target_parent_page_id}')
        logger.info('')
        
        # Refresh target databases cache
        self._refresh_target_dbs_cache()
        
        # Get source database schema
        source_schema = self._get_database_schema(source_db_id, self.source_headers)
        if not source_schema:
            logger.error('Failed to get source database schema')
            return self.stats
        
        db_name = self._get_database_name(source_schema)
        logger.info(f'Source database: {db_name} ({source_db_id})')
        
        # Find or create target database
        target_db_id = self._find_or_create_target_database(source_db_id, source_schema)
        
        if not target_db_id:
            if not self.dry_run:
                logger.error('Failed to find/create target database')
            return self.stats
        
        logger.info(f'Target database ID: {target_db_id}')
        
        # Query items from source FIRST (with optional limit)
        logger.info('Querying source items...')
        items = self._query_all_items(source_db_id, self.source_headers, max_items=max_items)
        logger.info(f'Retrieved {len(items)} items to transfer')
        
        if self.dry_run:
            logger.info(f'[DRY RUN] Would transfer {len(items)} items')
            return self.stats
        
        # USAGE-DRIVEN PROPERTY ANALYSIS
        # Scan all items to find which properties are actually populated
        logger.info('Analyzing property usage in source items...')
        used_properties = set()
        used_properties.add('title')  # Title is always needed
        
        for item in items:
            for prop_name, prop_val in item['properties'].items():
                if has_property_value(prop_val):
                    used_properties.add(prop_name)
        
        logger.info(f'Found {len(used_properties)} properties with actual values')
        
        # Get current target database schema
        logger.info('Getting target database schema...')
        target_schema = self._get_database_schema(target_db_id, self.target_headers)
        if not target_schema:
            logger.error('Failed to get target database schema')
            return self.stats
        
        current_target_props = set(target_schema.get('properties', {}).keys())
        
        # SELF-CORRECTING: Remove unused properties from target
        props_to_remove = current_target_props - used_properties - {'title', 'Title', 'Name'}
        # Don't remove system properties
        system_props = {'Created', 'Created time', 'Last edited', 'Last edited time', 
                        'Created by', 'Last edited by'}
        props_to_remove = props_to_remove - system_props
        
        if props_to_remove:
            logger.info(f'Removing {len(props_to_remove)} unused properties from target schema')
            # Notion API: set property to null to delete it
            remove_payload = {prop: None for prop in list(props_to_remove)[:50]}  # Limit batch
            resp = requests.patch(
                f'https://api.notion.com/v1/databases/{target_db_id}',
                headers=self.target_headers,
                json={'properties': remove_payload}
            )
            if resp.status_code == 200:
                logger.info(f'  Removed {len(remove_payload)} properties')
            else:
                logger.warning(f'  Failed to remove properties: {resp.json().get("message", "Unknown")}')
        
        # Ensure target has all needed properties from source
        source_schema = self._get_database_schema(source_db_id, self.source_headers)
        props_to_add = {}
        
        for prop_name in used_properties:
            if prop_name not in current_target_props and prop_name in source_schema.get('properties', {}):
                prop_def = source_schema['properties'][prop_name]
                schema_def = build_property_schema(prop_def)
                if schema_def:
                    props_to_add[prop_name] = schema_def
        
        if props_to_add:
            logger.info(f'Adding {len(props_to_add)} properties needed for items')
            resp = requests.patch(
                f'https://api.notion.com/v1/databases/{target_db_id}',
                headers=self.target_headers,
                json={'properties': props_to_add}
            )
            if resp.status_code == 200:
                logger.info(f'  Added {len(props_to_add)} properties')
            else:
                logger.warning(f'  Failed to add properties: {resp.json().get("message", "Unknown")}')
        
        # Refresh target props after modifications
        target_schema = self._get_database_schema(target_db_id, self.target_headers)
        target_props = set(target_schema.get('properties', {}).keys())
        logger.info(f'Target now has {len(target_props)} properties (optimized)')
        
        # First pass: Create all items without relations to build page ID map
        logger.info('Pass 1: Creating items (without relations)...')
        
        for item in items:
            source_page_id = item['id']
            
            # Get title for logging
            title = ''
            for prop_val in item['properties'].values():
                if prop_val.get('type') == 'title':
                    title_arr = prop_val.get('title', [])
                    if title_arr:
                        title = title_arr[0].get('plain_text', '')
                    break
            
            if not title:
                continue
            
            # Build properties (without relations)
            item_props = {}
            for prop_name, prop_val in item['properties'].items():
                if prop_val.get('type') == 'relation':
                    continue  # Skip relations in first pass
                
                copied = self._copy_property_value(prop_name, prop_val, target_props)
                if copied:
                    item_props[prop_name] = copied
            
            # Create page
            resp = requests.post(
                'https://api.notion.com/v1/pages',
                headers=self.target_headers,
                json={
                    'parent': {'database_id': target_db_id},
                    'properties': item_props
                }
            )
            
            if resp.status_code == 200:
                result = resp.json()
                target_page_id = result['id']
                
                # Map source to target page ID
                self.page_id_map[source_page_id] = target_page_id
                
                # Copy page content blocks
                blocks_copied = self._copy_blocks_to_page(source_page_id, target_page_id)
                
                logger.info(f'  Created: {title[:40]}... ({blocks_copied} blocks)')
                self.stats['items_transferred'] += 1
            else:
                logger.warning(f'  Failed to create {title[:30]}: {resp.json().get("message", "Unknown")}')
                self.stats['errors'].append(f'Failed to create: {title}')
        
        # Second pass: Update relations if enabled
        if include_relations and self.page_id_map:
            logger.info('')
            logger.info('Pass 2: Updating relation properties...')
            
            for item in items:
                source_page_id = item['id']
                target_page_id = self.page_id_map.get(source_page_id)
                
                if not target_page_id:
                    continue
                
                # Build relation properties only
                relation_props = {}
                for prop_name, prop_val in item['properties'].items():
                    if prop_val.get('type') != 'relation':
                        continue
                    
                    copied = self._copy_property_value(prop_name, prop_val, target_props)
                    if copied:
                        relation_props[prop_name] = copied
                
                if relation_props:
                    resp = requests.patch(
                        f'https://api.notion.com/v1/pages/{target_page_id}',
                        headers=self.target_headers,
                        json={'properties': relation_props}
                    )
                    
                    if resp.status_code != 200:
                        logger.debug(f'Failed to update relations: {resp.json()}')
        
        # Summary
        logger.info('')
        logger.info('=' * 60)
        logger.info('TRANSFER SUMMARY')
        logger.info('=' * 60)
        logger.info(f'Databases created: {self.stats["databases_created"]}')
        logger.info(f'Databases found: {self.stats["databases_found"]}')
        logger.info(f'Items transferred: {self.stats["items_transferred"]}')
        logger.info(f'Relations mapped: {self.stats["relations_mapped"]}')
        logger.info(f'Errors: {len(self.stats["errors"])}')
        
        return self.stats


# Verified token and parent page mappings (2026-01-19)
# Tokens are loaded from environment variables for security
# These override any tokens found in system-environments if specified
CLIENT_WORKSPACE_CONFIG = {
    'VibeVessel Client Workspace': {
        'token_env': 'NOTION_VIBEVESSELCLIENT_TOKEN',
        'database_parent_page_id': '2cf33d7a-491b-806d-8ac7-f401ddde95f9'
    },
    'VibeVessel Automations Workspace': {
        'token_env': 'NOTION_VIBEVESSEL_AUTOMATIONS_TOKEN',
        'database_parent_page_id': None  # TODO: Set when known
    },
    'VibeVessel Music Workspace': {
        'token_env': 'NOTION_VIBEVESSEL_MUSIC_TOKEN',
        'database_parent_page_id': '2ed9037e-a041-80c0-89c9-d8a23a44c072'
    }
}


def get_client_workspace_token(workspace_name: str) -> str | None:
    """Get token for a client workspace from environment variables."""
    config = CLIENT_WORKSPACE_CONFIG.get(workspace_name)
    if config and 'token_env' in config:
        return os.getenv(config['token_env'])
    return None


class CrossWorkspaceSync:
    """Handles cross-workspace database synchronization."""
    
    def __init__(self, primary_token: str, dry_run: bool = True):
        self.primary_token = primary_token
        self.dry_run = dry_run
        self.primary_headers = {
            'Authorization': f'Bearer {primary_token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        self.stats = {
            'databases_checked': 0,
            'databases_synced': 0,
            'items_synced': 0,
            'errors': []
        }
    
    def get_client_environments(self) -> List[Dict]:
        """Get all client workspace environments from system-environments."""
        logger.info('Fetching client environments from system-environments...')
        
        resp = requests.post(
            f'https://api.notion.com/v1/databases/{SYSTEM_ENVIRONMENTS_DB_ID}/query',
            headers=self.primary_headers,
            json={'page_size': 100}
        )
        
        if resp.status_code != 200:
            logger.error(f'Failed to query system-environments: {resp.json()}')
            return []
        
        environments = []
        for item in resp.json().get('results', []):
            props = item['properties']
            
            # Get name
            name = ''
            if 'Name' in props and props['Name'].get('title'):
                name = props['Name']['title'][0].get('plain_text', '') if props['Name']['title'] else ''
            
            # Get token
            token = ''
            if 'Primary-Token' in props and props['Primary-Token'].get('rich_text'):
                token = props['Primary-Token']['rich_text'][0].get('plain_text', '') if props['Primary-Token']['rich_text'] else ''
            
            # Get related system-databases
            related_dbs = []
            rel_prop = props.get('Related to system-databases (system-environments)', {})
            if rel_prop.get('relation'):
                related_dbs = [r['id'] for r in rel_prop['relation']]
            
            # Get environment type
            env_type = ''
            if 'Environment-Type' in props and props['Environment-Type'].get('select'):
                env_type = props['Environment-Type']['select'].get('name', '')
            
            if name and token and related_dbs:
                environments.append({
                    'id': item['id'],
                    'name': name,
                    'token': token,
                    'related_databases': related_dbs,
                    'environment_type': env_type
                })
        
        logger.info(f'Found {len(environments)} client environments with tokens')
        return environments
    
    def get_database_details(self, db_page_id: str) -> Optional[Dict]:
        """Get details of a database from system-databases."""
        resp = requests.get(
            f'https://api.notion.com/v1/pages/{db_page_id}',
            headers=self.primary_headers
        )
        
        if resp.status_code != 200:
            return None
        
        props = resp.json()['properties']
        
        # Get name
        name = ''
        if 'Name' in props and props['Name'].get('title'):
            name = props['Name']['title'][0].get('plain_text', '') if props['Name']['title'] else ''
        
        # Get sync status
        sync_status = ''
        if 'Sync' in props and props['Sync'].get('status'):
            sync_status = props['Sync']['status'].get('name', '')
        
        # Get primary database ID (the actual Notion database ID)
        primary_db_id = ''
        
        # Try Data Source ID first
        if 'Data Source ID' in props and props['Data Source ID'].get('rich_text'):
            primary_db_id = props['Data Source ID']['rich_text'][0].get('plain_text', '') if props['Data Source ID']['rich_text'] else ''
        
        # Try Database ID
        if not primary_db_id and 'Database ID' in props and props['Database ID'].get('rich_text'):
            primary_db_id = props['Database ID']['rich_text'][0].get('plain_text', '') if props['Database ID']['rich_text'] else ''
        
        # Try NID
        if not primary_db_id and 'NID' in props and props['NID'].get('rich_text'):
            primary_db_id = props['NID']['rich_text'][0].get('plain_text', '') if props['NID']['rich_text'] else ''
        
        # Try to extract from Database URL
        if not primary_db_id and 'Database URL' in props and props['Database URL'].get('url'):
            url = props['Database URL']['url']
            # URLs look like: https://www.notion.so/284e73616c27808da10bc027c2eb11ff
            if url:
                import re
                # Extract 32-char hex ID from URL
                match = re.search(r'([a-f0-9]{32})', url)
                if match:
                    hex_id = match.group(1)
                    # Convert to UUID format
                    primary_db_id = f'{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}'
        
        return {
            'page_id': db_page_id,
            'name': name,
            'sync_status': sync_status,
            'primary_db_id': primary_db_id
        }
    
    def get_primary_database_schema(self, db_id: str) -> Optional[Dict]:
        """Get the schema of a database in the primary workspace."""
        resp = requests.get(
            f'https://api.notion.com/v1/databases/{db_id}',
            headers=self.primary_headers
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    
    def create_database_in_client(
        self, 
        db_name: str, 
        primary_schema: Dict,
        client_headers: Dict,
        parent_page_id: Optional[str] = None
    ) -> Optional[str]:
        """Create a database in the client workspace with the same schema."""
        if self.dry_run:
            logger.info(f'  [DRY RUN] Would create database: {db_name}')
            return None
        
        # Build properties - skip relations and rollups (they reference primary workspace)
        properties = {}
        skip_types = {'relation', 'rollup', 'created_by', 'last_edited_by', 'created_time', 'last_edited_time'}
        
        for prop_name, prop_def in primary_schema.get('properties', {}).items():
            prop_type = prop_def.get('type', '')
            if prop_type in skip_types:
                continue
            
            # Copy the property definition
            if prop_type == 'title':
                properties[prop_name] = {'title': {}}
            elif prop_type == 'rich_text':
                properties[prop_name] = {'rich_text': {}}
            elif prop_type == 'number':
                properties[prop_name] = {'number': prop_def.get('number', {})}
            elif prop_type == 'select':
                # Limit options to 100 (Notion API limit)
                sel_def = prop_def.get('select', {})
                if 'options' in sel_def and len(sel_def.get('options', [])) > 100:
                    sel_def = {'options': sel_def['options'][:100]}
                properties[prop_name] = {'select': sel_def}
            elif prop_type == 'multi_select':
                # Limit options to 100 (Notion API limit)
                ms_def = prop_def.get('multi_select', {})
                if 'options' in ms_def and len(ms_def.get('options', [])) > 100:
                    ms_def = {'options': ms_def['options'][:100]}
                properties[prop_name] = {'multi_select': ms_def}
            elif prop_type == 'date':
                properties[prop_name] = {'date': {}}
            elif prop_type == 'checkbox':
                properties[prop_name] = {'checkbox': {}}
            elif prop_type == 'url':
                properties[prop_name] = {'url': {}}
            elif prop_type == 'email':
                properties[prop_name] = {'email': {}}
            elif prop_type == 'phone_number':
                properties[prop_name] = {'phone_number': {}}
            elif prop_type == 'status':
                # Status properties can't be created via API - skip
                # They are auto-created by Notion
                pass
            elif prop_type == 'files':
                properties[prop_name] = {'files': {}}
        
        # Create database payload
        # Note: For databases, we need a parent page in the client workspace
        # This would need to be configured per-client
        payload = {
            'title': [{'type': 'text', 'text': {'content': db_name}}],
            'properties': properties
        }
        
        # Find database-parent-page - THE ONLY ACCEPTED PARENT FOR DATABASES
        # First check if we have a configured parent page ID
        if parent_page_id:
            payload['parent'] = {'type': 'page_id', 'page_id': parent_page_id}
            logger.info(f'  Using provided parent page: {parent_page_id}')
        elif hasattr(self, 'client_parent_page_id') and self.client_parent_page_id:
            payload['parent'] = {'type': 'page_id', 'page_id': self.client_parent_page_id}
            logger.info(f'  Using configured parent page: {self.client_parent_page_id}')
        else:
            # Search for database-parent-page (MANDATORY - this is the only accepted location)
            search_resp = requests.post(
                'https://api.notion.com/v1/search',
                headers=client_headers,
                json={'query': 'database-parent-page', 'filter': {'property': 'object', 'value': 'page'}, 'page_size': 10}
            )
            pages = search_resp.json().get('results', [])
            
            # Find exact match for "database-parent-page"
            parent_found = None
            for page in pages:
                props = page.get('properties', {})
                for pname, pval in props.items():
                    if pval.get('type') == 'title':
                        title_arr = pval.get('title', [])
                        if title_arr:
                            title = title_arr[0].get('plain_text', '')
                            if title.lower() == 'database-parent-page':
                                parent_found = page['id']
                                break
                if parent_found:
                    break
            
            if parent_found:
                payload['parent'] = {'type': 'page_id', 'page_id': parent_found}
                logger.info(f'  Using database-parent-page: {parent_found}')
            else:
                logger.error(f'  CRITICAL: database-parent-page not found in client workspace!')
                logger.error(f'  Databases MUST be created under database-parent-page')
                return None
        
        # Create the database
        resp = requests.post(
            'https://api.notion.com/v1/databases',
            headers=client_headers,
            json=payload
        )
        
        if resp.status_code == 200:
            result = resp.json()
            new_db_id = result['id']
            db_url = result.get('url', f'https://www.notion.so/{new_db_id.replace("-", "")}')
            logger.info(f'  Created database: {db_name}')
            logger.info(f'    ID: {new_db_id}')
            logger.info(f'    URL: {db_url}')
            return new_db_id
        else:
            logger.error(f'  Failed to create database: {resp.json()}')
            return None
    
    def sync_client_workspace(self, client_env: Dict) -> Dict:
        """Sync databases to a client workspace."""
        client_name = client_env['name']
        client_token = client_env['token']
        related_dbs = client_env['related_databases']
        
        # Check for verified config override
        if client_name in CLIENT_WORKSPACE_CONFIG:
            config = CLIENT_WORKSPACE_CONFIG[client_name]
            env_token = get_client_workspace_token(client_name)
            if env_token:
                client_token = env_token
                logger.info(f'Using verified token from environment variable')
            self.client_parent_page_id = config.get('database_parent_page_id')
        else:
            self.client_parent_page_id = None
        
        logger.info(f'=== Syncing to: {client_name} ===')
        logger.info(f'Related databases: {len(related_dbs)}')
        logger.info(f'Primary token: ...{self.primary_token[-5:]}')
        logger.info(f'Client token: ...{client_token[-5:]}')
        if self.client_parent_page_id:
            logger.info(f'Database parent page: {self.client_parent_page_id}')
        
        # Validate client token
        client_headers = {
            'Authorization': f'Bearer {client_token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        
        test_resp = requests.get('https://api.notion.com/v1/users/me', headers=client_headers)
        if test_resp.status_code != 200:
            error = f'Client token invalid for {client_name} (token: ...{client_token[-5:]})'
            logger.error(error)
            self.stats['errors'].append(error)
            return {'success': False, 'error': error}
        
        logger.info(f'Client bot: {test_resp.json().get("name", "Unknown")}')
        
        # Get databases in client workspace
        client_dbs_resp = requests.post(
            'https://api.notion.com/v1/search',
            headers=client_headers,
            json={'filter': {'property': 'object', 'value': 'database'}, 'page_size': 100}
        )
        client_dbs = {
            db.get('title', [{}])[0].get('plain_text', '').lower(): db['id']
            for db in client_dbs_resp.json().get('results', [])
            if db.get('title')
        }
        logger.info(f'Existing databases in client workspace: {len(client_dbs)}')
        
        # Process each related database
        synced = 0
        created = 0
        for db_page_id in related_dbs:
            self.stats['databases_checked'] += 1
            
            db_details = self.get_database_details(db_page_id)
            if not db_details:
                logger.warning(f'Could not get details for database {db_page_id}')
                continue
            
            db_name = db_details['name']
            sync_status = db_details['sync_status']
            primary_db_id = db_details['primary_db_id']
            
            logger.info(f'Processing: {db_name} (sync: {sync_status})')
            
            # Check if sync is configured
            if sync_status == 'No Sync' or not sync_status:
                logger.info(f'  Skipping - sync not configured')
                continue
            
            # Check if database exists in client workspace
            client_db_id = client_dbs.get(db_name.lower())
            
            if not client_db_id and primary_db_id:
                # Database doesn't exist - create it
                logger.info(f'  Database not found in client workspace - creating...')
                primary_schema = self.get_primary_database_schema(primary_db_id)
                if primary_schema:
                    client_db_id = self.create_database_in_client(
                        db_name,
                        primary_schema,
                        client_headers
                    )
                    if client_db_id:
                        created += 1
                        client_dbs[db_name.lower()] = client_db_id
            
            if client_db_id and primary_db_id:
                logger.info(f'  Syncing to client: {client_db_id[:8]}...')
                
                # Sync items from primary to client
                items_synced = self.sync_database_items(
                    primary_db_id, 
                    client_db_id,
                    client_headers,
                    db_name
                )
                self.stats['items_synced'] += items_synced
                synced += 1
            elif not primary_db_id:
                logger.warning(f'  No primary database ID configured')
        
        self.stats['databases_synced'] += synced
        logger.info(f'Created {created} new databases, synced {synced} databases')
        return {'success': True, 'synced': synced, 'created': created}
    
    def ensure_client_schema_matches(
        self,
        primary_db_id: str,
        client_db_id: str,
        client_headers: Dict
    ) -> bool:
        """Ensure the client database has all properties from the source database."""
        # Get source schema
        source_schema = self.get_primary_database_schema(primary_db_id)
        if not source_schema:
            logger.error(f'  Failed to get source database schema')
            return False
        
        # Get client schema
        client_resp = requests.get(
            f'https://api.notion.com/v1/databases/{client_db_id}',
            headers=client_headers
        )
        if client_resp.status_code != 200:
            logger.error(f'  Failed to get client database schema')
            return False
        
        client_schema = client_resp.json()
        client_props = set(client_schema.get('properties', {}).keys())
        
        # Find missing properties
        missing_props = {}
        for prop_name, prop_def in source_schema.get('properties', {}).items():
            if prop_name not in client_props:
                schema_def = build_property_schema(prop_def)
                if schema_def:
                    missing_props[prop_name] = schema_def
        
        if missing_props:
            logger.info(f'  Adding {len(missing_props)} missing properties to client schema: {list(missing_props.keys())}')
            
            # Update client database schema
            patch_resp = requests.patch(
                f'https://api.notion.com/v1/databases/{client_db_id}',
                headers=client_headers,
                json={'properties': missing_props}
            )
            
            if patch_resp.status_code != 200:
                logger.error(f'  Failed to update client schema: {patch_resp.json()}')
                return False
            
            logger.info(f'  Successfully updated client schema')
        else:
            logger.info(f'  Client schema already has all source properties')
        
        return True
    
    def copy_blocks_to_page(
        self,
        source_page_id: str,
        target_page_id: str,
        client_headers: Dict
    ) -> int:
        """Copy all blocks from source page to target page."""
        # Get blocks from source
        source_blocks = get_page_blocks(source_page_id, self.primary_headers)
        
        if not source_blocks:
            return 0
        
        # Clean blocks for copying
        cleaned_blocks = []
        for block in source_blocks:
            cleaned = clean_block_for_copy(block)
            if cleaned:
                cleaned_blocks.append(cleaned)
        
        if not cleaned_blocks:
            return 0
        
        logger.debug(f'      Copying {len(cleaned_blocks)} blocks to new page')
        
        # Append blocks in batches of 100 (Notion API limit)
        total_copied = 0
        for i in range(0, len(cleaned_blocks), 100):
            batch = cleaned_blocks[i:i+100]
            
            resp = requests.patch(
                f'https://api.notion.com/v1/blocks/{target_page_id}/children',
                headers=client_headers,
                json={'children': batch}
            )
            
            if resp.status_code == 200:
                total_copied += len(batch)
            else:
                logger.warning(f'      Failed to copy blocks batch: {resp.json().get("message", "Unknown")}')
                break
        
        return total_copied
    
    def sync_database_items(
        self, 
        primary_db_id: str, 
        client_db_id: str,
        client_headers: Dict,
        db_name: str
    ) -> int:
        """Sync items from primary database to client database."""
        # First, ensure client schema matches source
        if not self.dry_run:
            self.ensure_client_schema_matches(primary_db_id, client_db_id, client_headers)
        
        # Query primary database
        resp = requests.post(
            f'https://api.notion.com/v1/databases/{primary_db_id}/query',
            headers=self.primary_headers,
            json={'page_size': 100}
        )
        
        if resp.status_code != 200:
            logger.error(f'  Failed to query primary database: {resp.json()}')
            return 0
        
        items = resp.json().get('results', [])
        logger.info(f'  Found {len(items)} items in primary')
        
        if self.dry_run:
            logger.info(f'  [DRY RUN] Would sync {len(items)} items to {client_db_id[:8]}...')
            return 0
        
        # Get client database schema to know which properties exist (after schema sync)
        client_schema_resp = requests.get(
            f'https://api.notion.com/v1/databases/{client_db_id}',
            headers=client_headers
        )
        if client_schema_resp.status_code != 200:
            logger.error(f'  Failed to get client database schema')
            return 0
        
        client_props = set(client_schema_resp.json().get('properties', {}).keys())
        logger.info(f'  Client schema has {len(client_props)} properties: {sorted(client_props)[:10]}...')
        
        synced = 0
        for item in items[:50]:  # Limit for safety in initial run
            source_page_id = item['id']
            
            # Get title for logging
            title = ''
            title_prop_name = None
            for prop_name, prop_val in item['properties'].items():
                if prop_val.get('type') == 'title':
                    title_prop_name = prop_name
                    title_arr = prop_val.get('title', [])
                    if title_arr:
                        title = title_arr[0].get('plain_text', '')
                    break
            
            if not title:
                logger.debug(f'    Skipping item with no title: {source_page_id}')
                continue
            
            # Build properties for client
            client_item_props = {}
            for prop_name, prop_val in item['properties'].items():
                prop_type = prop_val.get('type', '')
                
                # Skip if not in client schema or is a skip type
                if prop_name not in client_props or prop_type in SKIP_PROPERTY_TYPES:
                    continue
                
                # Copy the property value based on type
                if prop_type == 'title':
                    client_item_props[prop_name] = {'title': prop_val.get('title', [])}
                elif prop_type == 'rich_text':
                    client_item_props[prop_name] = {'rich_text': prop_val.get('rich_text', [])}
                elif prop_type == 'number':
                    client_item_props[prop_name] = {'number': prop_val.get('number')}
                elif prop_type == 'select':
                    if prop_val.get('select'):
                        client_item_props[prop_name] = {'select': {'name': prop_val['select'].get('name', '')}}
                elif prop_type == 'multi_select':
                    if prop_val.get('multi_select'):
                        client_item_props[prop_name] = {'multi_select': [{'name': s.get('name', '')} for s in prop_val['multi_select']]}
                elif prop_type == 'date':
                    if prop_val.get('date'):
                        client_item_props[prop_name] = {'date': prop_val['date']}
                elif prop_type == 'checkbox':
                    client_item_props[prop_name] = {'checkbox': prop_val.get('checkbox', False)}
                elif prop_type == 'url':
                    client_item_props[prop_name] = {'url': prop_val.get('url')}
                elif prop_type == 'email':
                    client_item_props[prop_name] = {'email': prop_val.get('email')}
                elif prop_type == 'phone_number':
                    client_item_props[prop_name] = {'phone_number': prop_val.get('phone_number')}
                elif prop_type == 'status':
                    if prop_val.get('status'):
                        client_item_props[prop_name] = {'status': {'name': prop_val['status'].get('name', '')}}
                elif prop_type == 'files':
                    # Handle files - only external files can be copied
                    if prop_val.get('files'):
                        files_list = []
                        for f in prop_val['files']:
                            if f.get('type') == 'external':
                                files_list.append({
                                    'type': 'external',
                                    'name': f.get('name', ''),
                                    'external': {'url': f['external']['url']}
                                })
                            # Note: Notion-hosted files cannot be copied to other workspaces
                        if files_list:
                            client_item_props[prop_name] = {'files': files_list}
            
            # Debug logging - show what we're sending
            logger.debug(f'    Item properties to sync: {list(client_item_props.keys())}')
            
            # Create item in client
            create_resp = requests.post(
                'https://api.notion.com/v1/pages',
                headers=client_headers,
                json={
                    'parent': {'database_id': client_db_id},
                    'properties': client_item_props
                }
            )
            
            if create_resp.status_code == 200:
                result = create_resp.json()
                new_page_id = result['id']
                page_url = result.get('url', f'https://www.notion.so/{new_page_id.replace("-", "")}')
                logger.info(f'    Created: {title[:40]}...')
                logger.info(f'      URL: {page_url}')
                
                # Copy page body content (blocks) from source to new page
                blocks_copied = self.copy_blocks_to_page(source_page_id, new_page_id, client_headers)
                if blocks_copied > 0:
                    logger.info(f'      Copied {blocks_copied} content blocks')
                
                synced += 1
            else:
                error_msg = create_resp.json().get('message', 'Unknown')
                logger.warning(f'    Failed to create {title[:30]}: {error_msg}')
                # Log the full payload for debugging
                logger.debug(f'    Failed payload: {json.dumps(client_item_props)[:500]}')
        
        logger.info(f'  Synced {synced}/{len(items)} items')
        return synced
    
    def run(self, client_filter: Optional[str] = None):
        """Run the cross-workspace sync."""
        logger.info('=' * 60)
        logger.info('CROSS-WORKSPACE DATABASE SYNC')
        logger.info('=' * 60)
        logger.info(f'Mode: {"DRY RUN" if self.dry_run else "EXECUTE"}')
        logger.info('')
        
        # Get client environments
        environments = self.get_client_environments()
        
        if client_filter:
            environments = [e for e in environments if client_filter.lower() in e['name'].lower()]
            logger.info(f'Filtered to {len(environments)} environments matching "{client_filter}"')
        
        # Sync each client
        for env in environments:
            self.sync_client_workspace(env)
            logger.info('')
        
        # Summary
        logger.info('=' * 60)
        logger.info('SYNC SUMMARY')
        logger.info('=' * 60)
        logger.info(f'Databases checked: {self.stats["databases_checked"]}')
        logger.info(f'Databases synced: {self.stats["databases_synced"]}')
        logger.info(f'Items synced: {self.stats["items_synced"]}')
        logger.info(f'Errors: {len(self.stats["errors"])}')
        
        if self.stats['errors']:
            logger.info('')
            logger.info('Errors:')
            for error in self.stats['errors']:
                logger.error(f'  - {error}')
        
        return self.stats


def main():
    parser = argparse.ArgumentParser(
        description='Cross-Workspace Database Sync and Transfer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync mode (default) - sync configured databases to client workspace
  python scripts/cross_workspace_sync.py --client "VibeVessel Client" --execute
  
  # Transfer mode - one-way transfer with full relation support
  python scripts/cross_workspace_sync.py --transfer \\
      --source-db "223e7361-6c27-80f2-98ed-e1c531c68c2a" \\
      --target-token "ntn_..." \\
      --target-parent "2cf33d7a-491b-806d-8ac7-f401ddde95f9" \\
      --execute
"""
    )
    
    # Mode selection
    parser.add_argument('--transfer', action='store_true', 
                        help='Use transfer mode (one-way with relations) instead of sync mode')
    
    # Sync mode options
    parser.add_argument('--client', type=str, help='Filter to specific client workspace (sync mode)')
    
    # Transfer mode options
    parser.add_argument('--source-db', type=str, 
                        help='Source database ID to transfer (transfer mode)')
    parser.add_argument('--source-token', type=str,
                        help='Source workspace token (transfer mode, defaults to primary token)')
    parser.add_argument('--target-token', type=str,
                        help='Target workspace token (transfer mode)')
    parser.add_argument('--target-parent', type=str,
                        help='Target parent page ID for new databases (transfer mode)')
    parser.add_argument('--max-items', type=int,
                        help='Maximum items to transfer (transfer mode)')
    parser.add_argument('--no-relations', action='store_true',
                        help='Skip relation processing (transfer mode)')
    
    # Common options
    parser.add_argument('--dry-run', action='store_true', default=True, 
                        help='Dry run mode (default)')
    parser.add_argument('--execute', action='store_true', 
                        help='Execute operation (not dry run)')
    
    args = parser.parse_args()
    
    # Initialize unified logger
    global logger
    mode = "transfer" if args.transfer else "sync"
    logger = setup_logging(
        session_id=f"cross_workspace_{mode}",
        log_level="DEBUG" if args.execute else "INFO",
        enable_file_logging=True,
        env="PROD"
    )
    
    # Get primary token
    token = get_notion_token()
    if not token:
        logger.error('Notion token not available')
        logger.finalize(ok=False, error="Notion token not available")
        sys.exit(1)
    
    dry_run = not args.execute
    
    if args.transfer:
        # Transfer mode
        if not args.source_db:
            logger.error('--source-db is required for transfer mode')
            sys.exit(1)
        if not args.target_token:
            logger.error('--target-token is required for transfer mode')
            sys.exit(1)
        if not args.target_parent:
            logger.error('--target-parent is required for transfer mode')
            sys.exit(1)
        
        source_token = args.source_token or token
        
        transfer = CrossWorkspaceTransfer(
            source_token=source_token,
            target_token=args.target_token,
            target_parent_page_id=args.target_parent,
            dry_run=dry_run
        )
        
        stats = transfer.transfer_database(
            source_db_id=args.source_db,
            include_relations=not args.no_relations,
            max_items=args.max_items
        )
        
        logger.finalize(ok=len(stats['errors']) == 0, summary=stats)
        sys.exit(1 if stats['errors'] else 0)
    
    else:
        # Sync mode (default)
        syncer = CrossWorkspaceSync(token, dry_run=dry_run)
        stats = syncer.run(client_filter=args.client)
        
        logger.finalize(ok=len(stats['errors']) == 0, summary=stats)
        sys.exit(1 if stats['errors'] else 0)


if __name__ == '__main__':
    main()
