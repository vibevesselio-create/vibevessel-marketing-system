#!/usr/bin/env python3
"""
Search Agent-Tasks and Issues+Questions databases for workspace/client synchronization items
"""

import os
import sys
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from notion_client import Client
    from shared_core.notion.token_manager import get_notion_token
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    sys.exit(1)

# Database IDs
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"
ISSUES_QUESTIONS_DB_ID = "229e73616c27808ebf06c202b10b5166"

# Search keywords
SEARCH_KEYWORDS = [
    "workspace",
    "sync",
    "synchronization",
    "client",
    "cross",
    "database",
    "notion",
    "workspaces",
    "client-workspace",
    "cross-workspace",
    "drive",
    "sheets",
    "drivesheets",
    "registry"
]

def search_database(
    client: Client,
    database_id: str,
    db_name: str,
    title_property: str,
) -> List[Dict[str, Any]]:
    """Search a database for items matching keywords."""
    results = []
    
    print(f"\n{'='*80}")
    print(f"Searching {db_name} database...")
    print(f"{'='*80}")
    
    # Try multiple search strategies
    for keyword in SEARCH_KEYWORDS:
        try:
            # Search by title contains
            response = client.databases.query(
                database_id=database_id,
                filter={
                    "property": title_property,
                    "title": {"contains": keyword}
                },
                page_size=100
            )
            
            for page in response.get("results", []):
                # Extract title
                title_prop = page.get("properties", {}).get(title_property, {})
                title = ""
                if title_prop.get("title"):
                    title = title_prop["title"][0].get("text", {}).get("content", "")
                
                # Extract description if available
                desc_prop = page.get("properties", {}).get("Description", {})
                description = ""
                if desc_prop.get("rich_text"):
                    description = desc_prop["rich_text"][0].get("text", {}).get("content", "")
                
                # Extract status if available
                status = "Unknown"
                status_prop = page.get("properties", {}).get("Status", {})
                if status_prop.get("status"):
                    status = status_prop["status"].get("name", "Unknown")
                
                # Avoid duplicates
                page_id = page.get("id", "")
                if not any(r.get("id") == page_id for r in results):
                    results.append({
                        "id": page_id,
                        "title": title,
                        "description": description[:200] if description else "",
                        "status": status,
                        "url": page.get("url", ""),
                        "matched_keyword": keyword
                    })
        
        except Exception as e:
            print(f"  ⚠️  Error searching for '{keyword}': {e}")
            continue
    
    # Also try searching by description/content
    try:
        # Get all pages and search in their content
        response = client.databases.query(
            database_id=database_id,
            page_size=100
        )
        
        for page in response.get("results", []):
            title_prop = page.get("properties", {}).get(title_property, {})
            title = ""
            if title_prop.get("title"):
                title = title_prop["title"][0].get("text", {}).get("content", "")
            
            desc_prop = page.get("properties", {}).get("Description", {})
            description = ""
            if desc_prop.get("rich_text"):
                description = desc_prop["rich_text"][0].get("text", {}).get("content", "")
            
            # Check if title or description contains any keywords
            combined_text = (title + " " + description).lower()
            matched_keywords = [kw for kw in SEARCH_KEYWORDS if kw.lower() in combined_text]
            
            if matched_keywords:
                page_id = page.get("id", "")
                if not any(r.get("id") == page_id for r in results):
                    status = "Unknown"
                    status_prop = page.get("properties", {}).get("Status", {})
                    if status_prop.get("status"):
                        status = status_prop["status"].get("name", "Unknown")
                    
                    results.append({
                        "id": page_id,
                        "title": title,
                        "description": description[:200] if description else "",
                        "status": status,
                        "url": page.get("url", ""),
                        "matched_keyword": ", ".join(matched_keywords)
                    })
    
    except Exception as e:
        print(f"  ⚠️  Error in full database scan: {e}")
    
    return results


def main():
    """Main execution."""
    print("="*80)
    print("Searching Agent-Tasks and Issues+Questions for Synchronization Items")
    print("="*80)
    
    # Get Notion client
    try:
        token = get_notion_token()
        if not token:
            print("❌ Error: Could not get Notion token")
            sys.exit(1)
        
        client = Client(auth=token)
    except Exception as e:
        print(f"❌ Error initializing Notion client: {e}")
        sys.exit(1)
    
    # Search Agent-Tasks
    agent_tasks_results = search_database(client, AGENT_TASKS_DB_ID, "Agent-Tasks", "Task Name")
    
    # Search Issues+Questions
    issues_results = search_database(client, ISSUES_QUESTIONS_DB_ID, "Issues+Questions", "Name")
    
    # Print results
    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print(f"{'='*80}")
    print(f"\nAgent-Tasks: {len(agent_tasks_results)} matching items")
    print(f"Issues+Questions: {len(issues_results)} matching items")
    
    # Print Agent-Tasks results
    if agent_tasks_results:
        print(f"\n{'='*80}")
        print("AGENT-TASKS MATCHES")
        print(f"{'='*80}")
        for i, item in enumerate(agent_tasks_results, 1):
            print(f"\n{i}. {item['title']}")
            print(f"   Status: {item['status']}")
            print(f"   Matched: {item['matched_keyword']}")
            if item['description']:
                print(f"   Description: {item['description']}...")
            print(f"   URL: {item['url']}")
    
    # Print Issues+Questions results
    if issues_results:
        print(f"\n{'='*80}")
        print("ISSUES+QUESTIONS MATCHES")
        print(f"{'='*80}")
        for i, item in enumerate(issues_results, 1):
            print(f"\n{i}. {item['title']}")
            print(f"   Status: {item['status']}")
            print(f"   Matched: {item['matched_keyword']}")
            if item['description']:
                print(f"   Description: {item['description']}...")
            print(f"   URL: {item['url']}")
    
    # Filter for most relevant matches
    print(f"\n{'='*80}")
    print("MOST RELEVANT MATCHES (Workspace/Client Sync)")
    print(f"{'='*80}")
    
    relevant_keywords = ["workspace", "client", "cross", "sync", "synchronization", "database"]
    relevant_agent_tasks = [
        item for item in agent_tasks_results
        if any(kw in item['title'].lower() or kw in item['description'].lower() 
               for kw in relevant_keywords)
    ]
    
    relevant_issues = [
        item for item in issues_results
        if any(kw in item['title'].lower() or kw in item['description'].lower() 
               for kw in relevant_keywords)
    ]
    
    print(f"\nRelevant Agent-Tasks: {len(relevant_agent_tasks)}")
    for item in relevant_agent_tasks:
        print(f"  • {item['title']} ({item['status']}) - {item['url']}")
    
    print(f"\nRelevant Issues+Questions: {len(relevant_issues)}")
    for item in relevant_issues:
        print(f"  • {item['title']} ({item['status']}) - {item['url']}")
    
    print(f"\n{'='*80}")
    print("Search Complete")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
