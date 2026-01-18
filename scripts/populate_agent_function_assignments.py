#!/usr/bin/env python3
"""
Populate Agent-Function Assignments
===================================

Populates missing Execution-Agent and Review-Agent assignments in Agent-Functions
database based on function purpose, capabilities, and system-designated agent roles.

Agent Capabilities:
- Cursor MM1 Agent: Code/implementation, technical work, testing, GAS scripts
- Claude MM1 Agent: Research/analysis, coordination, review, documentation, validation
- ChatGPT: Strategic planning, analysis, architectural guidance
- Notion AI Data Operations: Data operations, schema work, workspace updates
- Notion AI Research: Documentation, synthesis, research analysis
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
import re
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

try:
    from notion_client import Client
    NOTION_AVAILABLE = True
except ImportError:
    NOTION_AVAILABLE = False
    Client = None

# Database IDs
AGENT_FUNCTIONS_DB_ID = "256e73616c2780c783facd029ff49d2d"

# Agent IDs
CURSOR_MM1_AGENT_ID = "249e7361-6c27-8100-8a74-de7eabb9fc8d"  # Cursor MM1 Agent
CLAUDE_MM1_AGENT_ID = "fa54f05c-e184-403a-ac28-87dd8ce9855b"  # Claude MM1 Agent
CHATGPT_AGENT_ID = "9c4b6040-5e0f-4d31-ae1b-d4a43743b224"  # ChatGPT
NOTION_AI_DATAOPS_ID = "2d9e7361-6c27-80c5-ba24-c6f847789d77"  # Notion AI Data Operations
NOTION_AI_RESEARCH_ID = "2d9e7361-6c27-80c5-ba24-c6f847789d77"  # Notion AI Research (may be same as DataOps)

# Keywords for agent assignment logic
# Based on Universal Four-Agent Coordination Workflow and system capabilities

CURSOR_KEYWORDS = [
    # Code/Implementation
    "code", "implementation", "script", "technical", "development", "programming",
    "gas", "google apps script", "python", "javascript", "typescript", "testing",
    "deploy", "fix", "bug", "error", "function", "class", "api", "integration",
    "sync", "automation", "execution", "build", "create script", "generate code",
    # Technical work
    "technical validation", "security validation", "test", "debug", "refactor",
    "optimize", "performance", "production", "deployment", "clasp", "appsscript"
]

CLAUDE_KEYWORDS = [
    # Review/Coordination
    "review", "coordination", "validation", "audit", "compliance", "analysis",
    "documentation", "diátaxis", "quality assurance", "integration", "orchestration",
    "handoff", "workflow", "protocol", "compliance check", "verify", "validate",
    "research", "investigation", "assessment", "evaluation", "pre-flight",
    # MCP/Agent Coordination
    "mcp", "agent coordination", "task management", "execution log", "decision log",
    "verification", "gate", "checklist", "meta", "registry"
]

CHATGPT_KEYWORDS = [
    # Strategic Planning
    "strategic", "planning", "architecture", "design", "strategy", "roadmap",
    "analysis", "recommendation", "guidance", "approach", "methodology", "discovery",
    "audit", "requirements", "clarification", "architectural"
]

NOTION_DATAOPS_KEYWORDS = [
    # Data Operations
    "data", "database", "schema", "notion", "workspace", "update", "entry",
    "sync", "registry", "metadata", "properties", "relation", "query", "notion database",
    "data source", "data_source", "workspace database", "page", "block"
]

NOTION_RESEARCH_KEYWORDS = [
    # Research/Documentation
    "documentation", "synthesis", "research", "analysis", "report", "summary",
    "notion-ai-research", "research agent", "documentation gap"
]


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


def determine_agents(function_name: str, description: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Determine Execution-Agent and Review-Agent based on function name and description.
    
    Assignment Logic (following Universal Four-Agent Coordination Workflow):
    - Cursor MM1: Code/implementation, technical work, GAS scripts, testing
    - Claude MM1: Review, coordination, validation, documentation, MCP/agent coordination
    - ChatGPT: Strategic planning, analysis, architectural guidance, discovery
    - Notion AI Data Ops: Data operations, schema work, workspace updates, Notion database operations
    - Notion AI Research: Documentation, synthesis, research analysis
    
    Review-Agent assignments:
    - Cursor work → Claude (code review, quality assurance)
    - ChatGPT work → Claude (strategic review, validation)
    - Notion AI Data Ops → Claude (data validation, compliance)
    - Claude work → Cursor (technical validation) or ChatGPT (strategic validation)
    
    Returns: (execution_agent_id, review_agent_id)
    """
    text = f"{function_name} {description}".lower()
    
    execution_agent = None
    review_agent = None
    
    # Priority order: Check most specific first
    # 1. Notion-specific operations
    if any(keyword in text for keyword in NOTION_DATAOPS_KEYWORDS):
        execution_agent = NOTION_AI_DATAOPS_ID
        review_agent = CLAUDE_MM1_AGENT_ID  # Data ops reviewed by Claude
    
    # 2. Strategic/Planning work
    elif any(keyword in text for keyword in CHATGPT_KEYWORDS):
        execution_agent = CHATGPT_AGENT_ID
        review_agent = CLAUDE_MM1_AGENT_ID  # Strategic work reviewed by Claude
    
    # 3. Code/Implementation work
    elif any(keyword in text for keyword in CURSOR_KEYWORDS):
        execution_agent = CURSOR_MM1_AGENT_ID
        review_agent = CLAUDE_MM1_AGENT_ID  # Code reviewed by Claude
    
    # 4. Review/Coordination/Validation work
    elif any(keyword in text for keyword in CLAUDE_KEYWORDS):
        execution_agent = CLAUDE_MM1_AGENT_ID
        # Claude work reviewed by Cursor (technical) or ChatGPT (strategic)
        if any(word in text for word in ["technical", "code", "script", "implementation"]):
            review_agent = CURSOR_MM1_AGENT_ID
        else:
            review_agent = CHATGPT_AGENT_ID
    
    # 5. Research/Documentation
    elif any(keyword in text for keyword in NOTION_RESEARCH_KEYWORDS):
        execution_agent = NOTION_AI_DATAOPS_ID  # Or separate Research agent if available
        review_agent = CLAUDE_MM1_AGENT_ID
    
    # 6. Default fallback logic
    else:
        # Heuristic: Check for technical vs analytical keywords
        technical_words = ["script", "code", "function", "api", "sync", "automation", "gas"]
        analytical_words = ["analysis", "review", "audit", "compliance", "validation", "research"]
        
        if any(word in text for word in technical_words):
            execution_agent = CURSOR_MM1_AGENT_ID
            review_agent = CLAUDE_MM1_AGENT_ID
        elif any(word in text for word in analytical_words):
            execution_agent = CLAUDE_MM1_AGENT_ID
            review_agent = CURSOR_MM1_AGENT_ID
        else:
            # Default: Claude for coordination/analysis, Cursor for review
            execution_agent = CLAUDE_MM1_AGENT_ID
            review_agent = CURSOR_MM1_AGENT_ID
    
    return execution_agent, review_agent


def get_function_text(item: Dict[str, Any]) -> Tuple[str, str]:
    """Extract function name and description from Agent-Function item."""
    properties = item.get("properties", {})
    
    # Get name/title
    name_prop = properties.get("Name") or properties.get("Title") or {}
    name = ""
    if name_prop.get("title"):
        name = " ".join([t.get("plain_text", "") for t in name_prop["title"]])
    
    # Get description
    desc_prop = properties.get("Description") or properties.get("Function Description") or {}
    description = ""
    if desc_prop.get("rich_text"):
        description = " ".join([t.get("plain_text", "") for t in desc_prop["rich_text"]])
    elif desc_prop.get("text"):
        description = desc_prop["text"]
    
    return name, description


def update_agent_assignments(
    client: Client,
    item_id: str,
    execution_agent_id: str,
    review_agent_id: str,
    dry_run: bool = False
) -> bool:
    """Update Agent-Function with Default-Execution-agent assignment.

    Note: The Agent-Functions database only has Default-Execution-agent property.
    Review-Agent property doesn't exist in this database schema.
    We store the execution agent assignment in the existing property.
    """
    try:
        # Use the actual property name from the database schema
        properties = {
            "Default-Execution-agent": {
                "relation": [{"id": execution_agent_id}]
            }
        }
        
        if not dry_run:
            client.pages.update(page_id=item_id, properties=properties)
        
        return True
    except Exception as e:
        print(f"   ❌ Error updating {item_id}: {e}", file=sys.stderr)
        return False


def main():
    """Main execution."""
    if not NOTION_AVAILABLE:
        print("❌ notion-client not available. Install with: pip install notion-client")
        sys.exit(1)
    
    token = get_notion_token()
    if not token:
        print("❌ NOTION_TOKEN not found in environment or unified_config")
        sys.exit(1)
    
    client = Client(auth=token)
    
    # Check for dry-run flag
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")
    
    print("🚀 Populating Agent-Function Assignments...\n")
    print("="*80)
    
    try:
        # Query all Agent-Functions
        all_items = []
        response = client.databases.query(
            database_id=AGENT_FUNCTIONS_DB_ID,
            page_size=100
        )
        all_items.extend(response.get("results", []))
        
        # Handle pagination
        while response.get("has_more"):
            next_cursor = response.get("next_cursor")
            response = client.databases.query(
                database_id=AGENT_FUNCTIONS_DB_ID,
                page_size=100,
                start_cursor=next_cursor
            )
            all_items.extend(response.get("results", []))
        
        print(f"Found {len(all_items)} Agent-Function items\n")
        
        # Process each item
        stats = {
            "total": len(all_items),
            "missing_both": 0,
            "missing_execution": 0,
            "missing_review": 0,
            "already_complete": 0,
            "updated": 0,
            "errors": 0
        }
        
        for item in all_items:
            page_id = item.get("id", "")
            properties = item.get("properties", {})
            
            # Get function name and description
            name, description = get_function_text(item)
            if not name:
                name = f"[No Title - {page_id[:8]}]"
            
            # Check current assignments
            # Note: Using actual property name from database schema
            execution_agent = properties.get("Default-Execution-agent", {})
            has_execution_agent = bool(execution_agent.get("relation", []))

            # No Review-Agent property exists in this database - set to False
            has_review_agent = True  # Skip review-agent checks since property doesn't exist
            
            # Skip if both already assigned
            if has_execution_agent and has_review_agent:
                stats["already_complete"] += 1
                continue
            
            # Determine appropriate agents
            exec_id, review_id = determine_agents(name, description)
            
            # Update assignments (only checking execution agent since Review-Agent property doesn't exist)
            if not has_execution_agent:
                stats["missing_execution"] += 1
                print(f"📝 {name[:60]}")
                print(f"   Missing: Default-Execution-agent")
                print(f"   Assigning: Execution={exec_id[:8]}...")
                
                if update_agent_assignments(client, page_id, exec_id, review_id, dry_run):
                    stats["updated"] += 1
                    if not dry_run:
                        print(f"   ✅ Updated")
                else:
                    stats["errors"] += 1
                print()
        
        # Print summary
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total items: {stats['total']}")
        print(f"Already have Default-Execution-agent: {stats['already_complete']}")
        print(f"Missing Default-Execution-agent: {stats['missing_execution']}")
        print(f"Updated: {stats['updated']}")
        print(f"Errors: {stats['errors']}")
        
        if dry_run:
            print("\n🔍 DRY RUN - No changes were made")
            print("Run without --dry-run to apply changes")
        else:
            print(f"\n✅ Updated {stats['updated']} Agent-Function items")
        
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

