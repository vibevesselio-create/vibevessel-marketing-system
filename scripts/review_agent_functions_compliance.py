#!/usr/bin/env python3
"""
Review Agent-Functions Compliance
==================================

Reviews all Agent-Functions items for compliance with:
1. Execution-Agent and Review-Agent assignments
2. Agent-Tasks for missing Agent-Function links
3. Database template availability and matching for target databases

Per Agent-Functions Compliance Check requirements:
- All Agent-Functions must have Execution-Agent and Review-Agent assignments
- All Agent-Tasks must be linked to an Agent-Function
- All Agent-Functions must identify and use available database templates for target databases
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from notion_client import Client
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

# Database IDs
AGENT_FUNCTIONS_DB_ID = "256e73616c2780c783facd029ff49d2d"  # From execution logs
AGENT_TASKS_DB_ID = "284e73616c278018872aeb14e82e0392"  # Primary Agent-Tasks DB

def get_notion_token() -> Optional[str]:
    """Get Notion API token from shared_core token manager"""
    # Use centralized token manager (MANDATORY per CLAUDE.md)
    try:
        from shared_core.notion.token_manager import get_notion_token as _get_notion_token
        token = _get_notion_token()
        if token:
            return token
    except ImportError:
        pass

    # Fallback for backwards compatibility
    return os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_TOKEN") or os.getenv("VV_AUTOMATIONS_WS_TOKEN")

def get_notion_client() -> Optional[Client]:
    """Get Notion client."""
    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not set", file=sys.stderr)
        return None
    return Client(auth=token)

def get_database_templates(client: Client, database_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all templates from a Notion database.
    
    Steps:
    1. Retrieve database to get data_source_id
    2. List templates using data_source_id
    3. Return template details
    
    Args:
        client: Notion client
        database_id: Database ID to retrieve templates from
        
    Returns:
        List of template dictionaries with id, name, is_default, etc.
    """
    templates = []
    
    try:
        # Step 1: Retrieve database to get data sources
        db_info = client.databases.retrieve(database_id=database_id)
        data_sources = db_info.get("data_sources", [])
        
        if not data_sources:
            return templates
        
        # Step 2: For each data source, list templates
        for data_source in data_sources:
            data_source_id = data_source.get("id")
            if not data_source_id:
                continue
            
            try:
                # List templates for this data source
                # Note: This uses the Notion API endpoint for listing data source templates
                # The notion-client library may not have this directly, so we may need to use raw API
                import requests
                import json
                
                token = get_notion_token()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Notion-Version": "2025-09-03",
                    "Content-Type": "application/json"
                }
                
                url = f"https://api.notion.com/v1/data_sources/{data_source_id}/templates"
                response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    template_list = data.get("results", [])
                    templates.extend(template_list)
                elif response.status_code == 404:
                    # No templates endpoint or data source doesn't support templates
                    pass
                else:
                    print(f"  ⚠ Warning: Could not retrieve templates for data source {data_source_id[:8]}: {response.status_code}")
                    
            except Exception as e:
                # If direct API call fails, try alternative method
                # Templates might be stored as pages with specific properties
                pass
        
    except Exception as e:
        print(f"  ⚠ Warning: Error retrieving templates for database {database_id[:8]}: {e}")
    
    return templates

def identify_target_database(agent_function_item: Dict[str, Any]) -> Optional[str]:
    """
    Identify the target database where this Agent-Function creates items.
    
    Checks various properties that might indicate the target database:
    - Target Database (relation or rich_text)
    - Output Database (relation or rich_text)
    - Creates Items In (relation or rich_text)
    - Database (relation)
    
    Args:
        agent_function_item: Agent-Function item from Notion
        
    Returns:
        Database ID if found, None otherwise
    """
    properties = agent_function_item.get("properties", {})
    
    # Try various property names
    target_db_props = [
        "Target Database",
        "Output Database",
        "Creates Items In",
        "Database",
        "Target-Database",
        "Output-Database"
    ]
    
    for prop_name in target_db_props:
        prop = properties.get(prop_name, {})
        
        # Check if it's a relation property
        if prop.get("type") == "relation":
            relations = prop.get("relation", [])
            if relations:
                # For relation, we'd need to fetch the related page to get database ID
                # This is a simplified version - may need enhancement
                return relations[0].get("id")
        
        # Check if it's a rich_text property with database ID
        if prop.get("type") == "rich_text":
            rich_text = prop.get("rich_text", [])
            for text_item in rich_text:
                text_content = text_item.get("plain_text", "")
                # Look for database ID pattern (32 hex chars or UUID)
                import re
                db_id_match = re.search(r'[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text_content, re.IGNORECASE)
                if db_id_match:
                    return db_id_match.group(0)
    
    return None

def review_database_templates(client: Client, agent_functions_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Review database templates for Agent-Functions.
    
    For each Agent-Function:
    1. Identify target database
    2. Retrieve all templates from target database
    3. Match templates to function process
    4. Document findings
    
    Args:
        client: Notion client
        agent_functions_items: List of Agent-Function items
        
    Returns:
        Dictionary with template review results
    """
    print("\n" + "="*80)
    print("REVIEWING DATABASE TEMPLATES FOR AGENT-FUNCTIONS")
    print("="*80)
    
    results = {
        "total_functions_reviewed": 0,
        "functions_with_target_db": 0,
        "functions_with_templates": 0,
        "functions_without_templates": 0,
        "functions_missing_target_db": [],
        "template_findings": [],
        "errors": []
    }
    
    print(f"\nReviewing {len(agent_functions_items)} Agent-Function items for template availability...")
    
    for item in agent_functions_items:
        results["total_functions_reviewed"] += 1
        page_id = item.get("id", "")
        properties = item.get("properties", {})
        
        # Get title
        title_prop = properties.get("Name") or properties.get("Title") or {}
        title = ""
        if title_prop.get("title"):
            title = " ".join([t.get("plain_text", "") for t in title_prop["title"]])
        title = title or f"[No Title - {page_id[:8]}]"
        
        # Identify target database
        target_db_id = identify_target_database(item)
        
        if not target_db_id:
            results["functions_missing_target_db"].append({
                "page_id": page_id,
                "title": title,
                "url": f"https://www.notion.so/{page_id.replace('-', '')}"
            })
            print(f"  ⚠ {title}: No target database identified")
            continue
        
        results["functions_with_target_db"] += 1
        
        # Retrieve templates from target database
        try:
            templates = get_database_templates(client, target_db_id)
            
            if templates:
                results["functions_with_templates"] += 1
                template_names = [t.get("name", "Unnamed") for t in templates]
                default_template = next((t for t in templates if t.get("is_default", False)), None)
                
                finding = {
                    "function_page_id": page_id,
                    "function_title": title,
                    "function_url": f"https://www.notion.so/{page_id.replace('-', '')}",
                    "target_database_id": target_db_id,
                    "target_database_url": f"https://www.notion.so/{target_db_id.replace('-', '')}",
                    "template_count": len(templates),
                    "template_names": template_names,
                    "has_default_template": default_template is not None,
                    "default_template_name": default_template.get("name", "") if default_template else None,
                    "templates": templates
                }
                
                results["template_findings"].append(finding)
                print(f"  ✓ {title}: Found {len(templates)} template(s) in target database")
                if template_names:
                    print(f"    Templates: {', '.join(template_names[:3])}{'...' if len(template_names) > 3 else ''}")
            else:
                results["functions_without_templates"] += 1
                finding = {
                    "function_page_id": page_id,
                    "function_title": title,
                    "function_url": f"https://www.notion.so/{page_id.replace('-', '')}",
                    "target_database_id": target_db_id,
                    "target_database_url": f"https://www.notion.so/{target_db_id.replace('-', '')}",
                    "template_count": 0,
                    "issue": "No templates found in target database"
                }
                results["template_findings"].append(finding)
                print(f"  ⚠ {title}: No templates found in target database")
                
        except Exception as e:
            error_msg = f"Error retrieving templates for {title}: {e}"
            results["errors"].append(error_msg)
            print(f"  ❌ {error_msg}", file=sys.stderr)
    
    return results

def review_agent_functions(client: Client) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Review all Agent-Functions items."""
    print("\n" + "="*80)
    print("REVIEWING AGENT-FUNCTIONS DATABASE")
    print("="*80)
    
    results = {
        "total_items": 0,
        "missing_execution_agent": [],
        "missing_review_agent": [],
        "missing_both": [],
        "compliant": [],
        "errors": []
    }
    
    all_items = []  # Store all items for template review
    
    try:
        # Query all Agent-Functions
        response = client.databases.query(
            database_id=AGENT_FUNCTIONS_DB_ID,
            page_size=100
        )
        
        items = response.get("results", [])
        results["total_items"] = len(items)
        all_items.extend(items)
        
        print(f"\nFound {len(items)} Agent-Function items")
        
        for item in items:
            page_id = item.get("id", "")
            properties = item.get("properties", {})
            
            # Get title
            title_prop = properties.get("Name") or properties.get("Title") or {}
            title = ""
            if title_prop.get("title"):
                title = " ".join([t.get("plain_text", "") for t in title_prop["title"]])
            
            # Check Execution-Agent
            execution_agent = properties.get("Execution-Agent", {})
            has_execution_agent = bool(execution_agent.get("relation", []))
            
            # Check Review-Agent
            review_agent = properties.get("Review-Agent", {})
            has_review_agent = bool(review_agent.get("relation", []))
            
            item_info = {
                "page_id": page_id,
                "title": title or f"[No Title - {page_id[:8]}]",
                "url": f"https://www.notion.so/{page_id.replace('-', '')}"
            }
            
            if not has_execution_agent and not has_review_agent:
                results["missing_both"].append(item_info)
                print(f"  ✗ {item_info['title']}: Missing BOTH Execution-Agent and Review-Agent")
            elif not has_execution_agent:
                results["missing_execution_agent"].append(item_info)
                print(f"  ⚠ {item_info['title']}: Missing Execution-Agent")
            elif not has_review_agent:
                results["missing_review_agent"].append(item_info)
                print(f"  ⚠ {item_info['title']}: Missing Review-Agent")
            else:
                results["compliant"].append(item_info)
                print(f"  ✓ {item_info['title']}: Compliant")
        
        # Handle pagination
        while response.get("has_more"):
            next_cursor = response.get("next_cursor")
            response = client.databases.query(
                database_id=AGENT_FUNCTIONS_DB_ID,
                page_size=100,
                start_cursor=next_cursor
            )
            items = response.get("results", [])
            results["total_items"] += len(items)
            
            for item in items:
                page_id = item.get("id", "")
                properties = item.get("properties", {})
                
                title_prop = properties.get("Name") or properties.get("Title") or {}
                title = ""
                if title_prop.get("title"):
                    title = " ".join([t.get("plain_text", "") for t in title_prop["title"]])
                
                execution_agent = properties.get("Execution-Agent", {})
                has_execution_agent = bool(execution_agent.get("relation", []))
                
                review_agent = properties.get("Review-Agent", {})
                has_review_agent = bool(review_agent.get("relation", []))
                
                item_info = {
                    "page_id": page_id,
                    "title": title or f"[No Title - {page_id[:8]}]",
                    "url": f"https://www.notion.so/{page_id.replace('-', '')}"
                }
                
                if not has_execution_agent and not has_review_agent:
                    results["missing_both"].append(item_info)
                    print(f"  ✗ {item_info['title']}: Missing BOTH Execution-Agent and Review-Agent")
                elif not has_execution_agent:
                    results["missing_execution_agent"].append(item_info)
                    print(f"  ⚠ {item_info['title']}: Missing Execution-Agent")
                elif not has_review_agent:
                    results["missing_review_agent"].append(item_info)
                    print(f"  ⚠ {item_info['title']}: Missing Review-Agent")
                else:
                    results["compliant"].append(item_info)
                    print(f"  ✓ {item_info['title']}: Compliant")
        
    except Exception as e:
        error_msg = f"Error querying Agent-Functions database: {e}"
        results["errors"].append(error_msg)
        print(f"\n❌ {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    return results, all_items

def review_agent_tasks(client: Client) -> Dict[str, Any]:
    """Review Agent-Tasks for missing Agent-Function links."""
    print("\n" + "="*80)
    print("REVIEWING AGENT-TASKS DATABASE")
    print("="*80)
    
    results = {
        "total_items": 0,
        "missing_agent_function": [],
        "compliant": [],
        "errors": []
    }
    
    try:
        # Query all Agent-Tasks
        response = client.databases.query(
            database_id=AGENT_TASKS_DB_ID,
            page_size=100
        )
        
        items = response.get("results", [])
        results["total_items"] = len(items)
        
        print(f"\nFound {len(items)} Agent-Task items")
        
        for item in items:
            page_id = item.get("id", "")
            properties = item.get("properties", {})
            
            # Get title
            title_prop = properties.get("Name") or properties.get("Title") or properties.get("Task Name", {})
            title = ""
            if title_prop.get("title"):
                title = " ".join([t.get("plain_text", "") for t in title_prop["title"]])
            
            # Check Agent-Function relation
            agent_function = properties.get("Agent-Function", {})
            has_agent_function = bool(agent_function.get("relation", []))
            
            item_info = {
                "page_id": page_id,
                "title": title or f"[No Title - {page_id[:8]}]",
                "url": f"https://www.notion.so/{page_id.replace('-', '')}"
            }
            
            if not has_agent_function:
                results["missing_agent_function"].append(item_info)
                print(f"  ✗ {item_info['title']}: Missing Agent-Function link")
            else:
                results["compliant"].append(item_info)
                print(f"  ✓ {item_info['title']}: Has Agent-Function link")
        
        # Handle pagination
        while response.get("has_more"):
            next_cursor = response.get("next_cursor")
            response = client.databases.query(
                database_id=AGENT_TASKS_DB_ID,
                page_size=100,
                start_cursor=next_cursor
            )
            items = response.get("results", [])
            results["total_items"] += len(items)
            
            for item in items:
                page_id = item.get("id", "")
                properties = item.get("properties", {})
                
                title_prop = properties.get("Name") or properties.get("Title") or properties.get("Task Name", {})
                title = ""
                if title_prop.get("title"):
                    title = " ".join([t.get("plain_text", "") for t in title_prop["title"]])
                
                agent_function = properties.get("Agent-Function", {})
                has_agent_function = bool(agent_function.get("relation", []))
                
                item_info = {
                    "page_id": page_id,
                    "title": title or f"[No Title - {page_id[:8]}]",
                    "url": f"https://www.notion.so/{page_id.replace('-', '')}"
                }
                
                if not has_agent_function:
                    results["missing_agent_function"].append(item_info)
                    print(f"  ✗ {item_info['title']}: Missing Agent-Function link")
                else:
                    results["compliant"].append(item_info)
                    print(f"  ✓ {item_info['title']}: Has Agent-Function link")
        
    except Exception as e:
        error_msg = f"Error querying Agent-Tasks database: {e}"
        results["errors"].append(error_msg)
        print(f"\n❌ {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    
    return results

def generate_report(
    agent_functions_results: Dict[str, Any],
    agent_tasks_results: Dict[str, Any],
    template_results: Dict[str, Any]
) -> str:
    """Generate comprehensive compliance report."""
    report = []
    report.append("# Agent-Functions Compliance Review Report")
    report.append(f"\n**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    report.append(f"**Agent:** Cursor MM1 Agent")
    report.append("\n---\n")
    
    # Agent-Functions Summary
    report.append("## Agent-Functions Database Review")
    report.append(f"\n**Total Items:** {agent_functions_results['total_items']}")
    report.append(f"**Compliant:** {len(agent_functions_results['compliant'])}")
    report.append(f"**Missing Execution-Agent Only:** {len(agent_functions_results['missing_execution_agent'])}")
    report.append(f"**Missing Review-Agent Only:** {len(agent_functions_results['missing_review_agent'])}")
    report.append(f"**Missing Both:** {len(agent_functions_results['missing_both'])}")
    
    if agent_functions_results['missing_both']:
        report.append("\n### Items Missing Both Execution-Agent and Review-Agent:")
        for item in agent_functions_results['missing_both']:
            report.append(f"- [{item['title']}]({item['url']})")
    
    if agent_functions_results['missing_execution_agent']:
        report.append("\n### Items Missing Execution-Agent Only:")
        for item in agent_functions_results['missing_execution_agent']:
            report.append(f"- [{item['title']}]({item['url']})")
    
    if agent_functions_results['missing_review_agent']:
        report.append("\n### Items Missing Review-Agent Only:")
        for item in agent_functions_results['missing_review_agent']:
            report.append(f"- [{item['title']}]({item['url']})")
    
    # Agent-Tasks Summary
    report.append("\n## Agent-Tasks Database Review")
    report.append(f"\n**Total Items:** {agent_tasks_results['total_items']}")
    report.append(f"**Compliant (Has Agent-Function):** {len(agent_tasks_results['compliant'])}")
    report.append(f"**Missing Agent-Function Link:** {len(agent_tasks_results['missing_agent_function'])}")
    
    if agent_tasks_results['missing_agent_function']:
        report.append("\n### Tasks Missing Agent-Function Link:")
        for item in agent_tasks_results['missing_agent_function'][:50]:  # Limit to first 50
            report.append(f"- [{item['title']}]({item['url']})")
        if len(agent_tasks_results['missing_agent_function']) > 50:
            report.append(f"\n... and {len(agent_tasks_results['missing_agent_function']) - 50} more")
    
    # Errors
    if agent_functions_results['errors'] or agent_tasks_results['errors']:
        report.append("\n## Errors")
        for error in agent_functions_results['errors']:
            report.append(f"- {error}")
        for error in agent_tasks_results['errors']:
            report.append(f"- {error}")
    
    # Recommendations
    report.append("\n## Recommendations")
    total_issues = (
        len(agent_functions_results['missing_execution_agent']) +
        len(agent_functions_results['missing_review_agent']) +
        len(agent_functions_results['missing_both']) +
        len(agent_tasks_results['missing_agent_function'])
    )
    
    if total_issues > 0:
        report.append(f"\n**Total Compliance Issues Found:** {total_issues}")
        report.append("\n### Required Actions:")
        
        if agent_functions_results['missing_both'] or agent_functions_results['missing_execution_agent'] or agent_functions_results['missing_review_agent']:
            report.append("\n1. **Agent-Functions Missing Assignments:**")
            report.append("   - Update each Agent-Function item to include:")
            report.append("     - Execution-Agent (relation property + page content link)")
            report.append("     - Review-Agent (relation property + page content link)")
        
    if agent_tasks_results['missing_agent_function']:
        report.append("\n2. **Agent-Tasks Missing Agent-Function Links:**")
        report.append("   - Link each Agent-Task to the appropriate Agent-Function item")
        report.append("   - This is required for compliance per Agent-Functions Compliance Check")
    
    # Template Review Summary
    report.append("\n## Database Templates Review")
    report.append(f"\n**Total Functions Reviewed:** {template_results['total_functions_reviewed']}")
    report.append(f"**Functions with Target Database Identified:** {template_results['functions_with_target_db']}")
    report.append(f"**Functions with Templates Available:** {template_results['functions_with_templates']}")
    report.append(f"**Functions without Templates:** {template_results['functions_without_templates']}")
    report.append(f"**Functions Missing Target Database:** {len(template_results['functions_missing_target_db'])}")
    
    if template_results['functions_missing_target_db']:
        report.append("\n### Functions Missing Target Database Identification:")
        for item in template_results['functions_missing_target_db'][:20]:  # Limit to first 20
            report.append(f"- [{item['title']}]({item['url']})")
        if len(template_results['functions_missing_target_db']) > 20:
            report.append(f"\n... and {len(template_results['functions_missing_target_db']) - 20} more")
    
    if template_results['template_findings']:
        report.append("\n### Template Findings:")
        for finding in template_results['template_findings'][:20]:  # Limit to first 20
            if finding.get('template_count', 0) > 0:
                templates_str = ', '.join(finding.get('template_names', [])[:3])
                report.append(f"- **[{finding['function_title']}]({finding['function_url']})**: {finding['template_count']} template(s) found")
                report.append(f"  - Target Database: [{finding['target_database_id'][:8]}...]({finding['target_database_url']})")
                report.append(f"  - Templates: {templates_str}")
                if finding.get('has_default_template'):
                    report.append(f"  - Default Template: {finding.get('default_template_name', 'Unknown')}")
            else:
                report.append(f"- **[{finding['function_title']}]({finding['function_url']})**: No templates found")
                report.append(f"  - Target Database: [{finding['target_database_id'][:8]}...]({finding['target_database_url']})")
                report.append(f"  - ⚠ Issue: {finding.get('issue', 'No templates available')}")
        if len(template_results['template_findings']) > 20:
            report.append(f"\n... and {len(template_results['template_findings']) - 20} more findings")
    
    if template_results['errors']:
        report.append("\n### Template Review Errors:")
        for error in template_results['errors']:
            report.append(f"- {error}")
    
    # Add template recommendations
    if template_results['functions_without_templates'] > 0 or template_results['functions_missing_target_db']:
        report.append("\n3. **Database Template Requirements:**")
        report.append("   - All Agent-Functions MUST identify their target database")
        report.append("   - All Agent-Functions MUST use available database templates when creating items")
        report.append("   - Templates provide the most efficient and reliable way to create items")
        report.append("   - Templates are assumed to be updated and production-ready")
        report.append("   - If no template exists, document the requirement for template creation")
    
    total_issues = (
        len(agent_functions_results['missing_execution_agent']) +
        len(agent_functions_results['missing_review_agent']) +
        len(agent_functions_results['missing_both']) +
        len(agent_tasks_results['missing_agent_function']) +
        template_results['functions_without_templates'] +
        len(template_results['functions_missing_target_db'])
    )
    
    if total_issues == 0:
        report.append("\n✅ **All items are compliant!**")
    else:
        report.append(f"\n**Total Compliance Issues Found:** {total_issues}")
    
    return "\n".join(report)

def main():
    """Main execution."""
    print("Agent-Functions Compliance Review")
    print("="*80)
    
    client = get_notion_client()
    if not client:
        print("ERROR: Cannot proceed without Notion client", file=sys.stderr)
        return 1
    
    # Review Agent-Functions
    agent_functions_results, agent_functions_items = review_agent_functions(client)
    
    # Review Agent-Tasks
    agent_tasks_results = review_agent_tasks(client)
    
    # Review Database Templates
    template_results = review_database_templates(client, agent_functions_items)
    
    # Generate report
    report = generate_report(agent_functions_results, agent_tasks_results, template_results)
    
    # Save report
    report_file = project_root / "docs" / "ops" / "agent_functions_compliance_review.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report, encoding='utf-8')
    
    print("\n" + "="*80)
    print("REVIEW COMPLETE")
    print("="*80)
    print(f"\nReport saved to: {report_file}")
    print("\nSummary:")
    print(f"  Agent-Functions: {len(agent_functions_results['compliant'])}/{agent_functions_results['total_items']} compliant")
    print(f"  Agent-Tasks: {len(agent_tasks_results['compliant'])}/{agent_tasks_results['total_items']} compliant")
    print(f"  Database Templates: {template_results['functions_with_templates']}/{template_results['functions_with_target_db']} functions have templates available")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

