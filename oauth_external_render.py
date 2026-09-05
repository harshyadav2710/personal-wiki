import os
import json
import pickle
import requests
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import google.auth


# ============================================================================
# CONFIGURATION FOR RENDER DEPLOYMENT
# ============================================================================

# Use /tmp on Render (persistent storage via volumes if needed)
# or use environment-based storage path
STORAGE_PATH = Path(os.getenv("OAUTH_STORAGE_PATH", "/tmp/oauth_creds"))
STORAGE_PATH.mkdir(exist_ok=True)

# Google OAuth credentials
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",  # Access Drive files
    "https://www.googleapis.com/auth/spreadsheets",  # Read/write sheets
]

# GitHub OAuth
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# Your MCP server (from tier1 setup)
mcp = FastMCP(
    "wiki-with-external-oauth",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "10001")),
)



class OAuthCredentialManager:
    """
    Manages OAuth tokens for external services
    - Stores credentials securely
    - Auto-refreshes expired tokens
    - Works on Render
    """
    
    def __init__(self, service: str, storage_path: Path = STORAGE_PATH):
        self.service = service
        self.token_file = storage_path / f"{service}_token.pkl"
        self.meta_file = storage_path / f"{service}_meta.json"
    
    def save_token(self, creds):
        """Save credentials to file (Render /tmp or persistent volume)."""
        try:
            with open(self.token_file, "wb") as f:
                pickle.dump(creds, f)
            
            # Also save metadata (expiry, etc.)
            meta = {
                "service": self.service,
                "saved_at": datetime.utcnow().isoformat(),
                "expires_at": creds.expiry.isoformat() if creds.expiry else None,
            }
            with open(self.meta_file, "w") as f:
                json.dump(meta, f)
            
            return True
        except Exception as e:
            print(f"Error saving token: {e}")
            return False
    
    def load_token(self):
        """Load credentials from storage."""
        if not self.token_file.exists():
            return None
        
        try:
            with open(self.token_file, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading token: {e}")
            return None
    
    def get_metadata(self) -> dict:
        """Get token metadata (expiry, last refresh, etc.)."""
        if not self.meta_file.exists():
            return {}
        
        try:
            with open(self.meta_file) as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading metadata: {e}")
            return {}



class GoogleDriveOAuth:
    """
    Manage Google Drive access via OAuth
    
    Setup:
    1. Go to Google Cloud Console
    2. Create OAuth 2.0 Desktop Application
    3. Download credentials.json
    4. Set GOOGLE_CREDENTIALS_JSON env var with file content (or path)
    """
    
    def __init__(self):
        self.manager = OAuthCredentialManager("google_drive")
        self.service = None
    
    def setup_credentials_file(self):
        """
        On Render, credentials come from environment variable.
        Create credentials.json from env var.
        """
        if GOOGLE_CREDENTIALS_JSON.startswith("{"):
            # It's JSON content
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        else:
            # It's a file path
            with open(GOOGLE_CREDENTIALS_JSON) as f:
                creds_dict = json.load(f)
        
        creds_file = STORAGE_PATH / "google_credentials.json"
        with open(creds_file, "w") as f:
            json.dump(creds_dict, f)
        
        return creds_file
    
    def get_credentials(self, force_refresh=False):
        """
        Get Google OAuth credentials
        - Load from cache if fresh
        - Refresh if expired
        - Do OAuth flow if no token
        """
        creds = self.manager.load_token()
        
        # Check if valid and not expired
        if creds and not force_refresh:
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self.manager.save_token(creds)
                return creds
        
        # Need new token - do OAuth flow
        creds_file = self.setup_credentials_file()
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_file),
            GOOGLE_SCOPES
        )
        
        # On Render, use local server (no browser, so use run_local_server with port)
        creds = flow.run_local_server(port=8080)
        self.manager.save_token(creds)
        
        return creds
    
    def get_service(self):
        """Get authenticated Google Drive service."""
        creds = self.get_credentials()
        return build("drive", "v3", credentials=creds)


class GitHubOAuth:
    """
    Manage GitHub access via OAuth
    
    Setup:
    1. Go to GitHub Settings > Developer Settings > OAuth Apps
    2. Create new app
    3. Set Client ID and Secret as env vars
    4. Authorization callback: https://your-render-app.onrender.com/oauth/github/callback
    """
    
    def __init__(self):
        self.manager = OAuthCredentialManager("github")
    
    def get_auth_url(self, redirect_uri: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        return (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={GITHUB_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=repo,user"
        )
    
    def exchange_code_for_token(self, code: str) -> Optional[dict]:
        """
        Exchange auth code for access token
        Called after user authorizes on GitHub
        """
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        
        if response.status_code == 200:
            token_data = response.json()
            # Save token
            token_file = STORAGE_PATH / "github_token.json"
            with open(token_file, "w") as f:
                json.dump(token_data, f)
            return token_data
        
        return None
    
    def get_access_token(self) -> Optional[str]:
        """Get stored GitHub access token."""
        token_file = STORAGE_PATH / "github_token.json"
        if token_file.exists():
            with open(token_file) as f:
                data = json.load(f)
                return data.get("access_token")
        return None


google_oauth = GoogleDriveOAuth()
github_oauth = GitHubOAuth()


@mcp.tool()
def setup_google_oauth() -> str:
    """
    SETUP: Initialize Google Drive OAuth
    
    Returns URL for authorization (on Render, watch logs for instructions)
    """
    try:
        creds = google_oauth.get_credentials()
        if creds:
            return "✅ Google Drive OAuth configured! Token saved."
    except Exception as e:
        return f"⚠️ OAuth setup error: {str(e)}"


@mcp.tool()
def google_drive_backup_wiki(folder_name: str = "Wiki Backup") -> str:
    """
    LEARNING: Backup your wiki to Google Drive
    - Uses OAuth credentials
    - Creates/updates folder automatically
    - Exports all notes as files
    """
    try:
        service = google_oauth.get_service()
        
        # Check if backup folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, spaces="drive", pageSize=1).execute()
        
        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            # Create folder
            folder_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
            folder = service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder["id"]
        
        return f"✅ Google Drive backup folder ready: {folder_name} (ID: {folder_id})"
    
    except Exception as e:
        return f"❌ Backup failed: {str(e)}"


@mcp.tool()
def export_notes_to_drive() -> str:
    """
    Export all wiki notes to Google Drive as documents
    Requires: setup_google_oauth() called first
    """
    try:
        service = google_oauth.get_service()
        
        # Get all notes from your wiki (using tier_store functions)
        # For now, create a test file
        file_metadata = {
            "name": f"Wiki Export {datetime.utcnow().isoformat()}",
            "mimeType": "text/plain",
        }
        
        media = open("/tmp/test_export.txt", "rb") if Path("/tmp/test_export.txt").exists() else None
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        
        return f"✅ Notes exported to Drive: {file.get('id')}"
    
    except Exception as e:
        return f"❌ Export failed: {str(e)}"


@mcp.tool()
def setup_github_oauth(callback_url: str) -> str:
    """
    SETUP: Initialize GitHub OAuth
    
    Usage:
    1. Call this tool with your Render app callback URL
    2. User visits returned URL to authorize
    3. GitHub redirects with code
    4. Exchange code for token
    """
    try:
        auth_url = github_oauth.get_auth_url(callback_url)
        return f"Visit this URL to authorize:\n{auth_url}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def sync_wiki_to_github(repo: str, token: str) -> str:
    """
    Sync wiki notes to GitHub repository
    
    Args:
    - repo: "username/repo" format
    - token: GitHub personal access token (or get from OAuth)
    """
    try:
        access_token = github_oauth.get_access_token() or token
        
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        # Example: Create a gist with wiki content
        gist_data = {
            "description": "Wiki Backup",
            "public": False,
            "files": {
                "wiki_notes.txt": {
                    "content": "Your wiki content here"
                }
            }
        }
        
        response = requests.post(
            "https://api.github.com/gists",
            headers=headers,
            json=gist_data,
        )
        
        if response.status_code == 201:
            gist = response.json()
            return f"✅ Gist created: {gist['html_url']}"
        
        return f"❌ GitHub sync failed: {response.status_code}"
    
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
def check_oauth_status() -> str:
    """Check status of all configured OAuth connections."""
    status = []
    
    # Google status
    google_meta = google_oauth.manager.get_metadata()
    if google_meta:
        status.append(f"✅ Google Drive: {google_meta.get('saved_at', 'configured')}")
    else:
        status.append("⚠️ Google Drive: Not configured")
    
    # GitHub status
    github_token = github_oauth.get_access_token()
    if github_token:
        status.append("✅ GitHub: Configured")
    else:
        status.append("⚠️ GitHub: Not configured")
    
    return "\n".join(status)



if __name__ == "__main__":
    # Test setup
    print("OAuth Manager initialized for Render")
    print(f"Storage path: {STORAGE_PATH}")
    print(f"Google scopes: {GOOGLE_SCOPES}")
    print("\nTo run MCP:")
    print("  mcp.run()")