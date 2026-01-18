#!/usr/bin/env python3
"""
Process Agent-Trigger-Folder Files
===================================

This script processes handoff task files from Agent-Trigger-Folder/01_inbox
and routes them to the appropriate agent inbox folders based on the target_agent
field in the JSON file.

This enables the continuous handoff flow where files are created in Agent-Trigger-Folder
and then automatically routed to agents.
"""

import os
import sys
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# Add project root to path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('process_agent_trigger_folder.log')
    ]
)
logger = logging.getLogger(__name__)

# Import from main.py
try:
    from main import (
        normalize_agent_folder_name, MM1_AGENT_TRIGGER_BASE
    )
except ImportError as e:
    logger.error(f"Failed to import from main.py: {e}")
    sys.exit(1)

# Agent name to folder mapping
AGENT_FOLDER_MAP = {
    "Claude MM1 Agent": "Claude-MM1-Agent",
    "Claude MM2 Agent": "Claude-MM2-Agent",
    "Claude Code Agent": "Claude-Code-Agent",
    "Cursor MM1 Agent": "Cursor-MM1-Agent",
    "Cursor MM2 Agent": "Cursor-MM2-Agent",
    "Codex MM1 Agent": "Codex-MM1-Agent",
    "ChatGPT Code Review Agent": "ChatGPT-Code-Review-Agent",
    "ChatGPT Strategic Agent": "ChatGPT-Strategic-Agent",
    "ChatGPT Personal Assistant Agent": "ChatGPT-Personal-Assistant-Agent",
    "Notion AI Data Operations Agent": "Notion-AI-Data-Operations-Agent",
    "Notion AI Research Agent": "Notion-AI-Research-Agent",
}


def process_trigger_file(file_path: Path) -> bool:
    """
    Process a single trigger file from Agent-Trigger-Folder.
    
    Args:
        file_path: Path to the trigger file
    
    Returns:
        True if successfully processed, False otherwise
    """
    try:
        logger.info(f"Processing: {file_path.name}")
        
        # Read the trigger file
        with open(file_path, 'r', encoding='utf-8') as f:
            trigger_data = json.load(f)
        
        # Get target agent
        target_agent = (
            trigger_data.get('target_agent') or 
            trigger_data.get('agent') or 
            trigger_data.get('assigned_agent')
        )
        
        if not target_agent:
            logger.error(f"No target_agent specified in {file_path.name}")
            return False
        
        # Determine agent folder
        agent_folder = AGENT_FOLDER_MAP.get(target_agent)
        if not agent_folder:
            # Try to normalize the agent name
            agent_folder = normalize_agent_folder_name(target_agent, None)
            if not agent_folder:
                logger.error(f"Could not determine folder for agent: {target_agent}")
                return False
        
        # Create destination path
        dest_inbox = MM1_AGENT_TRIGGER_BASE / agent_folder / "01_inbox"
        dest_inbox.mkdir(parents=True, exist_ok=True)
        
        # Check if file already exists in destination
        dest_file = dest_inbox / file_path.name
        if dest_file.exists():
            logger.warning(f"File already exists in destination: {dest_file.name}. Skipping.")
            # Move source file to processed
            processed_dir = file_path.parent.parent / "02_processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            processed_file = processed_dir / f"{timestamp}__{file_path.name}"
            shutil.move(str(file_path), str(processed_file))
            logger.info(f"Moved duplicate file to processed: {processed_file.name}")
            return True
        
        # Move file to agent inbox
        shutil.move(str(file_path), str(dest_file))
        logger.info(f"✅ Routed to {target_agent}'s inbox: {dest_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
        return False


def process_agent_trigger_folder() -> int:
    """
    Process all files in Agent-Trigger-Folder/01_inbox.
    
    Returns:
        Number of files processed
    """
    trigger_folder = MM1_AGENT_TRIGGER_BASE / "01_inbox" / "Agent-Trigger-Folder"
    
    if not trigger_folder.exists():
        logger.info(f"Agent-Trigger-Folder does not exist: {trigger_folder}")
        return 0
    
    # Get all JSON files
    json_files = list(trigger_folder.glob("*.json"))
    
    if not json_files:
        logger.info("No JSON files found in Agent-Trigger-Folder")
        return 0
    
    logger.info(f"Found {len(json_files)} file(s) to process")
    
    processed_count = 0
    for file_path in json_files:
        if process_trigger_file(file_path):
            processed_count += 1
    
    logger.info(f"Processed {processed_count} of {len(json_files)} file(s)")
    return processed_count


def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Process Agent-Trigger-Folder Files")
    parser.add_argument("--watch", action="store_true", help="Run in continuous watch mode")
    parser.add_argument("--interval", type=int, default=30, help="Interval between checks in seconds (default: 30)")
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("Process Agent-Trigger-Folder Files")
    logger.info("=" * 80)
    
    if args.watch:
        # Continuous loop
        logger.info(f"Starting continuous processing (checking every {args.interval} seconds)")
        logger.info("Press Ctrl+C to stop")
        
        import time
        try:
            while True:
                process_agent_trigger_folder()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("\nStopped by user")
    else:
        # One-time processing
        process_agent_trigger_folder()


if __name__ == "__main__":
    main()





















