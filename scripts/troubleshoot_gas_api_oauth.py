#!/usr/bin/env python3
"""
Troubleshoot GAS API OAuth Credentials Issue
============================================

Immediately troubleshoots the OAuth credentials issue after Notion issue creation.
Checks for existing credentials and provides guidance.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_existing_credentials() -> List[Path]:
    """Check for existing OAuth credentials in common locations"""
    possible_locations = [
        Path.home() / '.credentials' / 'gas_api_credentials.json',
        Path.home() / '.credentials' / 'client_secret.json',
        Path.home() / '.credentials' / 'credentials.json',
        Path.home() / '.config' / 'gas_api_credentials.json',
        Path.home() / '.config' / 'client_secret.json',
        Path.home() / '.config' / 'credentials.json',
        project_root / 'credentials' / 'gas_api_credentials.json',
        project_root / 'credentials' / 'client_secret.json',
        project_root / 'credentials' / 'credentials.json',
        project_root / 'credentials' / 'oauth_credentials.json',
        project_root / 'credentials.json',
    ]
    
    found = []
    for path in possible_locations:
        if path.exists():
            found.append(path)
    
    return found


def check_google_cloud_config() -> bool:
    """Check if gcloud CLI is configured"""
    try:
        import subprocess
        result = subprocess.run(
            ['gcloud', 'config', 'list', '--format=json'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def provide_oauth_setup_instructions():
    """Provide detailed OAuth setup instructions"""
    print("\n" + "="*80)
    print("OAUTH CREDENTIALS SETUP INSTRUCTIONS")
    print("="*80 + "\n")
    
    print("To resolve the OAuth credentials issue, follow these steps:\n")
    
    print("1. GO TO GOOGLE CLOUD CONSOLE")
    print("   https://console.cloud.google.com/\n")
    
    print("2. SELECT OR CREATE A PROJECT")
    print("   - Use existing project or create new one")
    print("   - Note the Project ID\n")
    
    print("3. ENABLE REQUIRED APIS")
    print("   - Go to 'APIs & Services' > 'Library'")
    print("   - Enable: Google Apps Script API")
    print("   - Enable: Google Drive API")
    print("   - (Optional) Enable: Google Cloud Resource Manager API\n")
    
    print("4. CREATE OAuth 2.0 CREDENTIALS")
    print("   - Go to 'APIs & Services' > 'Credentials'")
    print("   - Click 'Create Credentials' > 'OAuth client ID'")
    print("   - Application type: 'Desktop app'")
    print("   - Name: 'GAS API Deployment'")
    print("   - Click 'Create'\n")
    
    print("5. DOWNLOAD CREDENTIALS")
    print("   - Click 'Download JSON'")
    print("   - Save the file\n")
    
    print("6. PLACE CREDENTIALS FILE")
    print("   - Copy downloaded JSON file to:")
    print(f"   - {project_root / 'credentials' / 'gas_api_credentials.json'}")
    print(f"   - (also accepted) {project_root / 'credentials' / 'client_secret.json'}")
    print(f"   - (also accepted) {project_root / 'credentials' / 'credentials.json'}")
    print("   - Or provide path via --credentials argument\n")
    
    print("7. VERIFY CREDENTIALS")
    print("   - Run: python3 scripts/execute_gas_api_deployment.py")
    print("   - First run will open browser for OAuth consent\n")
    
    print("="*80 + "\n")


def troubleshoot():
    """Main troubleshooting function"""
    print("\n" + "="*80)
    print("TROUBLESHOOTING GAS API OAUTH CREDENTIALS ISSUE")
    print("="*80 + "\n")
    
    # Check for existing credentials
    print("1. Checking for existing credentials...")
    found_creds = check_existing_credentials()
    
    if found_creds:
        print(f"   ✅ Found {len(found_creds)} credential file(s):")
        for cred in found_creds:
            print(f"      - {cred}")
            print(f"        Size: {cred.stat().st_size} bytes")
        
        # Check if credentials are valid JSON
        for cred in found_creds:
            try:
                import json
                with open(cred, 'r') as f:
                    data = json.load(f)
                    if 'installed' in data or 'web' in data:
                        print(f"      ✅ Valid OAuth credentials format")
                        if 'installed' in data:
                            client_id = data['installed'].get('client_id', 'N/A')
                            print(f"      Client ID: {client_id[:20]}...")
                    else:
                        print(f"      ⚠️  Unexpected format (missing 'installed' or 'web' key)")
            except json.JSONDecodeError:
                print(f"      ❌ Invalid JSON format")
            except Exception as e:
                print(f"      ⚠️  Error reading: {e}")
        
        print("\n   💡 You can use existing credentials:")
        print(f"      python3 scripts/execute_gas_api_deployment.py --credentials {found_creds[0]}")
    else:
        print("   ❌ No credentials found in common locations")
    
    print()
    
    # Check gcloud CLI
    print("2. Checking Google Cloud CLI...")
    if check_google_cloud_config():
        print("   ✅ gcloud CLI is configured")
        try:
            import subprocess
            result = subprocess.run(
                ['gcloud', 'config', 'get-value', 'project'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                project_id = result.stdout.strip()
                print(f"   Current project: {project_id}")
        except:
            pass
    else:
        print("   ⚠️  gcloud CLI not found or not configured")
        print("   (Not required for OAuth, but helpful for API enablement)")
    
    print()
    
    # Provide instructions
    print("3. Setup Instructions:")
    provide_oauth_setup_instructions()
    
    # Check credentials directory
    print("4. Checking credentials directory...")
    creds_dir = project_root / 'credentials'
    if creds_dir.exists():
        print(f"   ✅ Directory exists: {creds_dir}")
        files = list(creds_dir.glob('*.json'))
        if files:
            print(f"   Found {len(files)} JSON file(s):")
            for f in files:
                print(f"      - {f.name}")
        else:
            print("   ⚠️  No JSON files found")
    else:
        print(f"   ⚠️  Directory does not exist: {creds_dir}")
        print(f"   Creating directory...")
        try:
            creds_dir.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created: {creds_dir}")
        except Exception as e:
            print(f"   ❌ Failed to create: {e}")
    
    print()
    
    # Summary
    print("="*80)
    print("TROUBLESHOOTING SUMMARY")
    print("="*80 + "\n")
    
    if found_creds:
        print("✅ Credentials found - Issue may be resolved")
        print(f"   Use: --credentials {found_creds[0]}")
    else:
        print("❌ Credentials not found - Setup required")
        print("   Follow instructions above to create OAuth credentials")
    
    print()


if __name__ == "__main__":
    troubleshoot()
