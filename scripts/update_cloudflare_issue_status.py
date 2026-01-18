#!/usr/bin/env python3
"""
Update Cloudflare Issue Status in Notion

Updates the Cloudflare Tunnel DNS Missing issue to Resolved status.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import NotionManager, get_notion_token

# Cloudflare Tunnel DNS Missing issue ID
ISSUE_ID = "2c8e7361-6c27-8184-954f-e1279bbe0e7f"

def main():
    """Update Cloudflare issue status to Resolved"""
    print(f"Updating Cloudflare issue status for {ISSUE_ID}...")

    # Initialize Notion client
    token = get_notion_token()
    if not token:
        print("❌ Failed to get Notion token")
        return 1

    notion = NotionManager(token)

    # Update issue status to "Resolved" and update description
    update_properties = {
        "Status": {"status": {"name": "Resolved"}},
        "Description": {"rich_text": [{"text": {"content": """RESOLVED 2026-01-14:
- Cloudflare API token generated: 7bfYkayoDp-ruBHkk9ZASTSrmzBnins7tzEmm-P1
- Token added to github-production/.env and vibevessel-marketing-system/.env.example
- Zone ID: fd809936bdb57102151e3c631f76cc43
- Account ID: d5903a7830890738e0f5bd82af87b5f2
- Pending: DNS propagation verification and SSL certificate

Original Issue: Cloudflare tunnel running but DNS records missing for webhook.vibevessel.space"""}}]}
    }

    if notion.update_page(ISSUE_ID, update_properties):
        print(f"✅ Cloudflare issue status updated to 'Resolved'")
        return 0
    else:
        print("❌ Failed to update issue status")
        return 1

if __name__ == "__main__":
    sys.exit(main())
