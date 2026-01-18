#!/usr/bin/env python3
"""
Direct Script Sync to Notion
=============================

Syncs a single script directly to Notion Scripts database without dependencies
on seren_utils or other complex frameworks.

Usage:
    python sync_script_to_notion_direct.py <script_path>
"""

import os
import sys
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

try:
    from notion_client import Client
except ImportError:
    print("Error: notion-client not available. Install with: pip install notion-client")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Scripts database ID
SCRIPTS_DB_ID = "26ce7361-6c27-8178-bc77-f43aff00eddf"

# Get Notion token
NOTION_TOKEN = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN")
if not NOTION_TOKEN:
    logger.error("NOTION_TOKEN or NOTION_API_TOKEN environment variable not set")
    sys.exit(1)

# Initialize Notion client
notion = Client(auth=NOTION_TOKEN)


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of file contents"""
    try:
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash: {e}")
        return ""


def determine_language(file_path: Path) -> str:
    """Determine script language from file extension"""
    ext_map = {
        '.py': 'Python',
        '.gs': 'JavaScript',  # Google Apps Script
        '.js': 'JavaScript',
        '.sh': 'Shell',
        '.bash': 'Bash'
    }
    return ext_map.get(file_path.suffix, 'Unknown')


def extract_description(content: str) -> str:
    """Extract description from docstring"""
    lines = content.split('\n')
    in_docstring = False
    docstring_lines = []
    
    for line in lines:
        if '"""' in line or "'''" in line:
            if not in_docstring:
                in_docstring = True
                docstring_content = line.split('"""')[1] if '"""' in line else line.split("'''")[1]
                if docstring_content.strip():
                    docstring_lines.append(docstring_content.strip())
            else:
                in_docstring = False
                docstring_content = line.split('"""')[0] if '"""' in line else line.split("'''")[0]
                if docstring_content.strip():
                    docstring_lines.append(docstring_content.strip())
                break
        elif in_docstring:
            docstring_lines.append(line.strip())
    
    return ' '.join(docstring_lines) if docstring_lines else ""


def find_existing_script(script_name: str, file_path: str) -> Optional[Dict]:
    """Find existing script in Notion by name or file path"""
    try:
        # Try to find by Script Name
        response = notion.databases.query(
            database_id=SCRIPTS_DB_ID,
            filter={
                "property": "Script Name",
                "title": {
                    "equals": script_name
                }
            }
        )
        
        if response.get("results"):
            return response["results"][0]
        
        # Try to find by File Path
        file_path_url = f"file://{file_path}"
        response = notion.databases.query(
            database_id=SCRIPTS_DB_ID,
            filter={
                "property": "File Path",
                "url": {
                    "equals": file_path_url
                }
            }
        )
        
        if response.get("results"):
            return response["results"][0]
        
        return None
    except Exception as e:
        logger.error(f"Error finding existing script: {e}")
        return None


def create_or_update_script(script_path: Path, dry_run: bool = False) -> bool:
    """Create or update script in Notion"""
    try:
        # Read file content
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Get script metadata
        script_name = script_path.stem
        file_path_str = str(script_path.resolve())
        file_path_url = f"file://{file_path_str}"
        language = determine_language(script_path)
        file_hash = calculate_file_hash(script_path)
        description = extract_description(content)
        
        # Check if script already exists
        existing = find_existing_script(script_name, file_path_str)
        
        # Build description with hash
        hash_prefix = f"Hash: {file_hash}\n" if file_hash else ""
        full_description = hash_prefix + description if description else hash_prefix.strip()
        
        if existing:
            # Update existing script
            logger.info(f"Updating existing script: {script_name}")
            
            if dry_run:
                logger.info(f"[DRY RUN] Would update script: {script_name}")
                return True
            
            # Update properties
            properties = {
                "Last Sync Time": {
                    "date": {"start": datetime.now(timezone.utc).isoformat()}
                }
            }
            
            if full_description:
                properties["Description"] = {
                    "rich_text": [{"text": {"content": full_description[:2000]}}]
                }
            
            notion.pages.update(
                page_id=existing["id"],
                properties=properties
            )
            
            # Update code block
            _update_code_block(existing["id"], content, language)
            
            logger.info(f"Updated script: {script_name}")
        else:
            # Create new script
            logger.info(f"Creating new script: {script_name}")
            
            if dry_run:
                logger.info(f"[DRY RUN] Would create script: {script_name}")
                return True
            
            properties = {
                "Script Name": {
                    "title": [{"text": {"content": script_name}}]
                },
                "File Path": {
                    "url": file_path_url
                },
                "Language": {
                    "select": {"name": language}
                },
                "Last Sync Time": {
                    "date": {"start": datetime.now(timezone.utc).isoformat()}
                },
                "Status": {
                    "status": {"name": "2-In Development"}
                }
            }
            
            if full_description:
                properties["Description"] = {
                    "rich_text": [{"text": {"content": full_description[:2000]}}]
                }
            
            page = notion.pages.create(
                parent={"database_id": SCRIPTS_DB_ID},
                properties=properties
            )
            
            # Add code block
            _update_code_block(page["id"], content, language)
            
            logger.info(f"Created script: {script_name} (ID: {page['id']})")
        
        return True
        
    except Exception as e:
        logger.error(f"Error syncing script: {e}")
        return False


def _update_code_block(page_id: str, content: str, language: str):
    """Update or create code block on Notion page"""
    try:
        # Map language to Notion code block language
        lang_map = {
            'Python': 'python',
            'JavaScript': 'javascript',
            'Shell': 'shell',
            'Bash': 'bash'
        }
        notion_language = lang_map.get(language, 'plain text')
        
        # Get existing blocks
        all_blocks = []
        start_cursor = None
        
        while True:
            response = notion.blocks.children.list(block_id=page_id, start_cursor=start_cursor)
            all_blocks.extend(response.get("results", []))
            
            if not response.get("has_more"):
                break
            
            start_cursor = response.get("next_cursor")
        
        # Find existing code block
        code_block_id = None
        for block in all_blocks:
            if block.get("type") == "code":
                code_block_id = block["id"]
                break
        
        # Split content into chunks (Notion has 2000 char limit per text element)
        max_chunk_size = 1990
        rich_text_elements = []
        remaining_content = content
        
        while remaining_content:
            if len(remaining_content) <= max_chunk_size:
                rich_text_elements.append({"type": "text", "text": {"content": remaining_content}})
                remaining_content = ""
            else:
                chunk = remaining_content[:max_chunk_size]
                last_newline = chunk.rfind('\n')
                if last_newline > max_chunk_size * 0.8:
                    chunk = chunk[:last_newline + 1]
                    remaining_content = remaining_content[last_newline + 1:]
                else:
                    remaining_content = remaining_content[max_chunk_size:]
                if len(chunk) > 2000:
                    chunk = chunk[:2000]
                rich_text_elements.append({"type": "text", "text": {"content": chunk}})
        
        # Notion has a limit of 100 rich_text elements per code block
        MAX_RICH_TEXT_ELEMENTS = 100
        
        if len(rich_text_elements) > MAX_RICH_TEXT_ELEMENTS:
            # Split into multiple code blocks
            logger.info(f"Code block requires {len(rich_text_elements)} segments, splitting into multiple blocks")
            
            # Delete existing code block if present
            if code_block_id:
                try:
                    notion.blocks.delete(block_id=code_block_id)
                except:
                    pass
            
            # Create multiple code blocks
            for i in range(0, len(rich_text_elements), MAX_RICH_TEXT_ELEMENTS):
                chunk_elements = rich_text_elements[i:i + MAX_RICH_TEXT_ELEMENTS]
                code_block = {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": chunk_elements,
                        "language": notion_language,
                        "caption": []
                    }
                }
                
                if i > 0:
                    code_block["code"]["caption"] = [{"type": "text", "text": {"content": f"Part {i // MAX_RICH_TEXT_ELEMENTS + 1}"}}]
                
                notion.blocks.children.append(block_id=page_id, children=[code_block])
        else:
            # Single code block
            code_block = {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": rich_text_elements,
                    "language": notion_language,
                    "caption": []
                }
            }
            
            if code_block_id:
                # Update existing code block
                try:
                    notion.blocks.update(block_id=code_block_id, **code_block)
                except:
                    # If update fails, delete and recreate
                    try:
                        notion.blocks.delete(block_id=code_block_id)
                        notion.blocks.children.append(block_id=page_id, children=[code_block])
                    except Exception as e:
                        logger.warning(f"Could not update code block: {e}")
            else:
                # Create new code block
                notion.blocks.children.append(block_id=page_id, children=[code_block])
        
    except Exception as e:
        logger.warning(f"Error updating code block: {e}")


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Sync a script directly to Notion Scripts database"
    )
    parser.add_argument(
        'script_path',
        type=str,
        help='Path to the script file to sync'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making changes'
    )
    
    args = parser.parse_args()
    
    # Resolve script path
    script_path = Path(args.script_path)
    if not script_path.is_absolute():
        if (Path.cwd() / script_path).exists():
            script_path = Path.cwd() / script_path
        elif (Path(__file__).parent / script_path).exists():
            script_path = Path(__file__).parent / script_path
    
    if not script_path.exists():
        logger.error(f"Script not found: {args.script_path}")
        sys.exit(1)
    
    logger.info(f"Syncing script: {script_path}")
    
    success = create_or_update_script(script_path, dry_run=args.dry_run)
    
    if success:
        logger.info("Script sync completed successfully")
    else:
        logger.error("Script sync failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
