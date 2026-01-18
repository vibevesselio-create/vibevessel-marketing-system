#!/usr/bin/env python3
"""Check if Volumes database exists in Notion"""
import os
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()
notion = Client(auth=os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY"))

# Search for databases with "Volumes" in the name
try:
    # Search for pages/databases
    results = notion.search(query="Volumes", filter={"property": "object", "value": "database"})
    
    print("Databases found with 'Volumes' in name:")
    for page in results.get("results", []):
        props = page.get("properties", {})
        title = ""
        if "title" in props:
            title_list = props["title"].get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", "")
        elif "Name" in props:
            title_list = props["Name"].get("title", [])
            if title_list:
                title = title_list[0].get("plain_text", "")
        
        print(f"  - {title}: {page.get('id')}")
        
    if not results.get("results"):
        print("  No Volumes database found")
        print("\nRecommendation: Create Volumes database in Notion or make VOLUMES_DATABASE_ID optional in sync script")
        
except Exception as e:
    print(f"Error searching: {e}")
