#!/usr/bin/env python3
"""
Create handoff files for all Spotify review tasks we just created.
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from create_handoff_from_notion_task import process_next_task, get_notion_token
from notion_client import Client

def main():
    """Create handoff files for all review tasks related to Spotify issue"""
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found. Cannot proceed.")
        sys.exit(1)
    
    notion_client = Client(auth=token)
    
    # Process tasks one by one - run the handoff script multiple times
    # Each call processes one task
    print("Creating handoff files for Spotify review tasks...")
    print("=" * 80)
    
    tasks_created = 0
    max_iterations = 15  # Process up to 15 tasks (should cover our 10 + any other pending)
    
    for i in range(max_iterations):
        print(f"\n--- Iteration {i+1} ---")
        result = process_next_task(notion_client)
        
        if result:
            tasks_created += 1
        else:
            print("No more tasks to process or all already have handoff files")
            break
    
    print("\n" + "=" * 80)
    print(f"✅ Created {tasks_created} handoff files")
    print("=" * 80)
    
    if tasks_created > 0:
        print("\nHandoff files created successfully!")
        print("Files are located in: /Users/brianhellemn/Documents/Agents/Agent-Triggers/01_inbox/Agent-Trigger-Folder/")
        print("\nNext steps:")
        print("1. Assigned agents will receive trigger files in their inbox")
        print("2. Agents should process tasks and move files to 02_processed")
        print("3. Tasks will be updated in Notion as work progresses")
    else:
        print("\n⚠️  No handoff files were created. Possible reasons:")
        print("   - Tasks already have handoff files")
        print("   - No incomplete tasks found")
        print("   - Tasks are not in the correct status")

if __name__ == "__main__":
    main()
