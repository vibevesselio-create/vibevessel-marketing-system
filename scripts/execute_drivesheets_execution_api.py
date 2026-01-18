#!/usr/bin/env python3
"""
Execute DriveSheetsSync via Apps Script Execution API

Uses Google Apps Script Execution API to execute manualRunDriveSheets() function.
"""

import os
import sys
import json
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import pickle
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    print("❌ ERROR: Google API libraries not available")
    print("   Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    sys.exit(1)

# Scopes for Apps Script Execution API
SCOPES = [
    'https://www.googleapis.com/auth/script.scriptapp',
    'https://www.googleapis.com/auth/drive',
]

SCRIPT_ID = "1n8vraQ0Rrfbeor7c3seWv2dh8saRVAJBJzgKm0oVQzgJrp5E1dLrAGf-"
FUNCTION_NAME = "manualRunDriveSheets"

def get_credentials():
    """Get OAuth credentials."""
    creds = None
    token_path = Path.home() / '.gas_execution_token.pickle'
    
    # Load existing token
    if token_path.exists():
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        except Exception as e:
            print(f"⚠️  Could not load token: {e}")
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Find credentials file
            credentials_path = os.getenv('GAS_API_CREDENTIALS_PATH')
            if not credentials_path:
                possible_paths = [
                    Path.home() / 'Projects' / 'github-production' / 'credentials' / 'google-oauth' / 'desktop_credentials.json',
                    Path.home() / '.credentials' / 'gas_api_credentials.json',
                    Path.home() / '.credentials' / 'credentials.json',
                ]
                for path in possible_paths:
                    if path.exists():
                        credentials_path = str(path)
                        break
            
            if not credentials_path or not Path(credentials_path).exists():
                print("❌ ERROR: OAuth credentials not found")
                print(f"   Set GAS_API_CREDENTIALS_PATH or place credentials at:")
                for path in possible_paths:
                    print(f"   - {path}")
                sys.exit(1)
            
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save token
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def execute_function():
    """Execute manualRunDriveSheets() via Execution API."""
    print("=" * 80)
    print("EXECUTING PRODUCTION WORKFLOW via Apps Script Execution API")
    print("=" * 80)
    print(f"Script ID: {SCRIPT_ID}")
    print(f"Function: {FUNCTION_NAME}")
    print()
    
    try:
        # Get credentials
        print("Authenticating...")
        creds = get_credentials()
        
        # Build service
        print("Building Apps Script service...")
        service = build('script', 'v1', credentials=creds)
        
        # Execute function
        print(f"Executing {FUNCTION_NAME}()...")
        print()
        
        request = {
            'function': FUNCTION_NAME
        }
        
        response = service.scripts().run(
            scriptId=SCRIPT_ID,
            body=request
        ).execute()
        
        # Check for errors
        if 'error' in response:
            error = response['error']
            print("❌ EXECUTION ERROR:")
            print(f"   Error Type: {error.get('errorType', 'Unknown')}")
            print(f"   Error Message: {error.get('errorMessage', 'Unknown error')}")
            
            if 'details' in error:
                print("\n   Details:")
                for detail in error['details']:
                    print(f"     - {detail}")
            
            return 1
        
        # Success
        print("✅ EXECUTION COMPLETED")
        
        if 'response' in response:
            result = response['response']
            if 'result' in result:
                print(f"\nResult: {result['result']}")
        
        return 0
        
    except HttpError as e:
        print(f"❌ HTTP ERROR: {e}")
        error_details = json.loads(e.content.decode('utf-8'))
        if 'error' in error_details:
            print(f"   {error_details['error']}")
        return 1
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(execute_function())
