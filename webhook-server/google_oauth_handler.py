#!/usr/bin/env python3
"""
Google OAuth Handler for Webhook Server
======================================

Handles Google OAuth2 authentication flows within the FastAPI webhook server.
Integrates with the existing webhook infrastructure to provide OAuth callback endpoints.

Author: Seren Development • v1.0.0 • 2025-11-24
"""

import os
import json
import pickle
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google OAuth2 Configuration
GOOGLE_OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid'
]

# Default paths
# Use GOOGLE_OAUTH_CLIENT_SECRETS_FILE to specify the client_secret JSON file
# Default to the first available client_secret file in the credentials directory
DEFAULT_CREDENTIALS_PATH = os.getenv(
    'GOOGLE_OAUTH_CLIENT_SECRETS_FILE',
    os.getenv(
        'GOOGLE_OAUTH_CREDENTIALS_PATH',  # Legacy env var for backward compatibility
        '/Users/brianhellemn/Library/CloudStorage/GoogleDrive-vibe.vessel.io@gmail.com/My Drive/VibeVessel-Internal-WS-gd/database-parent-page/scripts/github-dev/credentials/google-oauth/client_secret_797362328200-ki5cbaoauictkugd87mm8u70o75euvqk.apps.googleusercontent.com.json'
    )
)
DEFAULT_TOKEN_DIR = os.getenv('GOOGLE_OAUTH_TOKEN_DIR', '/Users/brianhellemn/.credentials')
# Redirect URI: Must match exactly what's configured in Google Cloud Console
# Default uses port 5001 (server default), but can be overridden via env var
DEFAULT_REDIRECT_URI = os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'http://localhost:5001/auth/google/callback')


class GoogleOAuthHandler:
    """Handles Google OAuth2 authentication flows"""
    
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        scopes: Optional[list] = None
    ):
        """
        Initialize Google OAuth Handler
        
        Args:
            credentials_path: Path to OAuth2 credentials JSON file
            redirect_uri: OAuth redirect URI (must match Google Cloud Console)
            scopes: List of OAuth scopes to request
        """
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.redirect_uri = redirect_uri or DEFAULT_REDIRECT_URI
        self.scopes = scopes or GOOGLE_OAUTH_SCOPES
        self.token_dir = Path(DEFAULT_TOKEN_DIR)
        self.token_dir.mkdir(parents=True, exist_ok=True)
        
        # Load client configuration
        self.client_config = self._load_client_config()
        
        # Store active flows (for state management)
        self.active_flows: Dict[str, Flow] = {}
    
    def _load_client_config(self) -> Dict[str, Any]:
        """Load OAuth2 client configuration from credentials file"""
        try:
            if not os.path.exists(self.credentials_path):
                raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
            
            with open(self.credentials_path, 'r') as f:
                config = json.load(f)
            
            # Handle both 'installed' and 'web' application types
            if 'installed' in config:
                return config['installed']
            elif 'web' in config:
                return config['web']
            else:
                raise ValueError("Invalid credentials format: missing 'installed' or 'web' key")
                
        except Exception as e:
            print(f"❌ Error loading OAuth credentials: {e}")
            raise
    
    def create_authorization_url(self, state: Optional[str] = None, redirect_uri: Optional[str] = None) -> tuple[str, str]:
        """
        Create Google OAuth2 authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
            redirect_uri: Optional redirect URI (overrides instance default)
            
        Returns:
            Tuple of (authorization_url, state)
        """
        try:
            # Use provided redirect_uri or fall back to instance default
            redirect_uri_to_use = redirect_uri or self.redirect_uri
            
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_config.get('client_id'),
                        "client_secret": self.client_config.get('client_secret'),
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri_to_use]
                    }
                },
                scopes=self.scopes,
                redirect_uri=redirect_uri_to_use
            )
            
            # Generate state if not provided
            if not state:
                import secrets
                state = secrets.token_urlsafe(32)
            
            # Store flow for later use
            self.active_flows[state] = flow
            
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            return authorization_url, state
            
        except Exception as e:
            print(f"❌ Error creating authorization URL: {e}")
            raise
    
    def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        """
        Handle OAuth callback and exchange authorization code for tokens
        
        Args:
            code: Authorization code from Google
            state: State parameter from authorization request
            
        Returns:
            Dictionary with credentials info and user data
        """
        try:
            if state not in self.active_flows:
                raise ValueError(f"Invalid state parameter: {state}")
            
            flow = self.active_flows[state]
            
            # Exchange authorization code for credentials
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Get user info
            user_info = self._get_user_info(credentials)
            
            # Save credentials
            token_path = self._save_credentials(credentials, user_info)
            
            # Clean up flow
            del self.active_flows[state]
            
            return {
                "status": "success",
                "user_info": user_info,
                "token_path": str(token_path),
                "scopes": credentials.scopes,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None
            }
            
        except Exception as e:
            print(f"❌ Error handling OAuth callback: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _get_user_info(self, credentials: Credentials) -> Dict[str, Any]:
        """Get user information from Google API"""
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info
        except Exception as e:
            print(f"⚠️ Could not fetch user info: {e}")
            return {}
    
    def _save_credentials(self, credentials: Credentials, user_info: Dict[str, Any]) -> Path:
        """Save credentials to file"""
        try:
            # Use email as identifier if available
            email = user_info.get('email', 'default')
            safe_email = email.replace('@', '_at_').replace('.', '_')
            token_filename = f"google_oauth_token_{safe_email}.pickle"
            token_path = self.token_dir / token_filename
            
            # Save credentials
            with open(token_path, 'wb') as token_file:
                pickle.dump(credentials, token_file)
            
            print(f"✅ Credentials saved to: {token_path}")
            return token_path
            
        except Exception as e:
            print(f"❌ Error saving credentials: {e}")
            raise
    
    def load_credentials(self, email: Optional[str] = None) -> Optional[Credentials]:
        """
        Load saved credentials
        
        Args:
            email: Email address to load credentials for (optional)
            
        Returns:
            Credentials object or None if not found
        """
        try:
            if email:
                safe_email = email.replace('@', '_at_').replace('.', '_')
                token_filename = f"google_oauth_token_{safe_email}.pickle"
                token_path = self.token_dir / token_filename
            else:
                # Find the most recent token file
                token_files = list(self.token_dir.glob("google_oauth_token_*.pickle"))
                if not token_files:
                    return None
                token_path = max(token_files, key=lambda p: p.stat().st_mtime)
            
            if not token_path.exists():
                return None
            
            with open(token_path, 'rb') as token_file:
                credentials = pickle.load(token_file)
            
            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                self._save_credentials(credentials, {})
            
            return credentials
            
        except Exception as e:
            print(f"⚠️ Error loading credentials: {e}")
            return None
    
    def get_client_info(self) -> Dict[str, Any]:
        """Get OAuth client configuration info"""
        return {
            "client_id": self.client_config.get('client_id'),
            "project_id": self.client_config.get('project_id'),
            "redirect_uri": self.redirect_uri,
            "scopes": self.scopes,
            "credentials_path": self.credentials_path
        }


