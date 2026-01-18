#!/usr/bin/env python3
"""
Create Notion Issue for GAS API OAuth Credentials Problem
==========================================================

Documents the missing OAuth credentials issue and provides troubleshooting steps.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared_core.notion.issues_questions import create_issue_or_question


def main():
    """Create issue for OAuth credentials problem"""
    
    issue_name = "[Blocker] Google Apps Script API Deployment - Missing OAuth Credentials"
    
    description = f"""**Issue**: Google Apps Script API deployment requires OAuth 2.0 credentials that are not currently configured.

**Context**:
- Comprehensive GAS deployment system has been implemented
- Scripts identified: drive-sheets-sync/Code.js (Relation/Population & Deduplication)
- Deployment ready but blocked by missing OAuth credentials

**Error Encountered**:
```
FileNotFoundError: OAuth credentials not found. Please provide credentials_path or 
place credentials.json in credentials directory
```

**Required Actions**:
1. Create OAuth 2.0 Client ID in Google Cloud Console
2. Download credentials JSON file
3. Save to: `credentials/gas_api_credentials.json`
4. Required scopes:
   - https://www.googleapis.com/auth/script.projects
   - https://www.googleapis.com/auth/drive
   - https://www.googleapis.com/auth/script.deployments

**Files Affected**:
- `scripts/gas_api_deployment_manager.py`
- `scripts/gas_api_direct_deployment.py`
- `scripts/execute_gas_api_deployment.py`

**Deployment Status**: Ready (blocked by credentials)

**Created**: {datetime.now().isoformat()}
"""
    
    try:
        issue_id = create_issue_or_question(
            name=issue_name,
            type=["Blocker", "Configuration"],
            status="Unreported",
            priority="High",
            blocked=True,
            description=description,
            tags=["GAS", "OAuth", "Deployment", "API"]
        )
        
        if issue_id:
            print(f"✅ Created issue: {issue_id}")
            print(f"   Name: {issue_name}")
            print(f"\n📋 Next Steps:")
            print(f"   1. Go to Google Cloud Console")
            print(f"   2. Create OAuth 2.0 Client ID")
            print(f"   3. Download credentials JSON")
            print(f"   4. Save to: credentials/gas_api_credentials.json")
            print(f"   5. Run: python3 scripts/execute_gas_api_deployment.py")
            return issue_id
        else:
            print("❌ Failed to create issue")
            return None
            
    except Exception as e:
        print(f"❌ Error creating issue: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
