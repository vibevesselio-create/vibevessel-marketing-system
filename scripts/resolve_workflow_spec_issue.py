#!/usr/bin/env python3
"""
Script to resolve the Post-Content Shoot Data Management Workflow spec issue
by populating the missing Description and Workflow Requirements fields.

ENVIRONMENT MANAGEMENT: Uses shared_core.notion.token_manager (MANDATORY)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from notion_client import Client
    # MANDATORY: Use centralized token manager
    from shared_core.notion.token_manager import get_notion_token
    from main import NotionManager
except ImportError as e:
    print(f"Error importing required modules: {e}")
    sys.exit(1)

# Workflow page ID
WORKFLOW_PAGE_ID = "264e7361-6c27-80ba-90ea-f02a79d856b9"

# Description content
DESCRIPTION_CONTENT = """A data management workflow for post-content shoots, focusing on automation and synchronization within music-related projects. This workflow ensures seamless data handling after content creation sessions, managing file organization, metadata synchronization, and integration with music project databases.

**Purpose:**
- Automate data management processes following content shoots
- Synchronize shoot data with music project databases
- Ensure proper file organization and metadata tracking
- Maintain data integrity across workspace systems

**Scope:**
- Post-shoot file processing and organization
- Metadata extraction and synchronization
- Integration with music project workflows
- Data validation and quality checks"""

# Workflow Requirements content
WORKFLOW_REQUIREMENTS_CONTENT = """Execute the multi-phase data management workflow for post-content shoots:

**Phase 0: Pre-flight Validation**
- Validate configuration and ensure all necessary databases are accessible
- Confirm property schemas and relation integrity
- Verify execution and validation agents are assigned
- Output: Pre-flight validation report

**Phase 1: Discovery and Audit**
- Conduct audit of existing processes and requirements
- Identify data sources and synchronization targets
- Map file structures and metadata requirements
- Output: Audit findings document

**Phase 2: Execution and Implementation**
- Implement data management workflow per audit findings
- Process post-shoot files and organize data
- Synchronize metadata with music project databases
- Output: Workflow implementation report

**Phase 3: Validation and Completion**
- Validate implemented workflow meets all requirements
- Verify data integrity and synchronization accuracy
- Confirm compliance with workspace standards
- Output: Validation report

**Success Criteria:**
- All pre-flight checklist items completed
- Data synchronization successful and accurate
- All required fields and relations satisfied
- Validation status reflects clean state
- Evidence artifacts complete (logs, screenshots, documentation)"""


def update_workflow_spec():
    """Update the workflow page with Description and Workflow Requirements"""
    token = get_notion_token()
    if not token:
        print("ERROR: NOTION_TOKEN not found")
        return False
    
    notion = NotionManager(token)
    
    # Update Description field
    description_properties = {
        "Description": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": DESCRIPTION_CONTENT}
                }
            ]
        }
    }
    
    # Update Workflow Requirements field
    requirements_properties = {
        "Workflow Requirements": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": WORKFLOW_REQUIREMENTS_CONTENT}
                }
            ]
        }
    }
    
    # Combine properties
    update_properties = {**description_properties, **requirements_properties}
    
    # Update the page
    success = notion.update_page(WORKFLOW_PAGE_ID, update_properties)
    
    if success:
        print(f"✓ Successfully updated workflow page {WORKFLOW_PAGE_ID}")
        print("  - Description field populated")
        print("  - Workflow Requirements field populated")
        return True
    else:
        print(f"✗ Failed to update workflow page {WORKFLOW_PAGE_ID}")
        return False


if __name__ == "__main__":
    print("=" * 80)
    print("Resolving Post-Content Shoot Data Management Workflow Spec Issue")
    print("=" * 80)
    
    success = update_workflow_spec()
    
    if success:
        print("\n✓ Workflow spec issue resolved!")
        print(f"  Workflow URL: https://www.notion.so/Post-Content-Shoot-Data-Management-Workflow-{WORKFLOW_PAGE_ID.replace('-', '')}")
        sys.exit(0)
    else:
        print("\n✗ Failed to resolve workflow spec issue")
        sys.exit(1)

