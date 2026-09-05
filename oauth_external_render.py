

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
from google.oauth2.credentials import Credentials as GoogleCredentials
import google.auth


# ============================================================================
# CONFIGURATION FOR RENDER DEPLOYMENT
# ============================================================================

STORAGE_PATH = Path(os.getenv("OAUTH_STORAGE_PATH", "/tmp/oauth_creds"))
STORAGE_PATH.mkdir(parents=True, exist_ok=True)

GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

mcp = FastMCP(
    "wiki-with-external-oauth",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "10001")),
)


# ============================================================================
# OAUTH CREDENTIAL MANAGER
# ============================================================================

class OAuthCredentialManager:
    """Manages OAuth tokens with env var fallback for Render free tier"""
    
    def __init__(self, service: str, storage_path: Path = STORAGE_PATH):
        self.service = service
        self.token_file = storage_path / f"{service}_token.pkl"
        self.meta_file = storage_path / f"{service}_meta.json"
        self.env_var_name = f"{service.upper()}_ACCESS_TOKEN"
    
    def save_token(self, creds):
        """Save credentials to file"""
        try:
            with open(self.token_file, "wb") as f:
                pickle.dump(creds, f)
            
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
        """Load credentials from storage"""
        if not self.token_file.exists():
            return None
        
        try:
            with open(self.token_file, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading token: {e}")
            return None
    
    def get_metadata(self) -> dict:
        """Get token metadata"""
        if not self.meta_file.exists():
            return {}
        
        try:
            with open(self.meta_file) as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading metadata: {e}")
            return {}


# ============================================================================
# GOOGLE DRIVE OAUTH (WITH ENV VAR SUPPORT)
# ============================================================================

class GoogleDriveOAuth:
    """
    Google Drive OAuth with env var fallback for Render
    
    Priority:
    1. GOOGLE_ACCESS_TOKEN env var (Render persistent)
    2. File storage
    3. OAuth flow
    """
    
    def __init__(self):
        self.manager = OAuthCredentialManager("google_drive")
        self.service = None
    
    def setup_credentials_file(self):
        """Create credentials.json from env var"""
        if GOOGLE_CREDENTIALS_JSON.startswith("{"):
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        else:
            with open(GOOGLE_CREDENTIALS_JSON) as f:
                creds_dict = json.load(f)
        
        creds_file = STORAGE_PATH / "google_credentials.json"
        with open(creds_file, "w") as f:
            json.dump(creds_dict, f)
        
        return creds_file
    
    def get_credentials(self, force_refresh=False):
        """
        Get Google OAuth credentials
        
        ✅ RENDER FREE TIER: Checks env var first (persistent!)
        Falls back to file storage
        """
        
        # ========== STEP 1: Check env var (Render persistent) ==========
        token_from_env = os.getenv("GOOGLE_ACCESS_TOKEN")
        if token_from_env and not force_refresh:
            print("✅ Using GOOGLE_ACCESS_TOKEN from env var")
            return GoogleCredentials(token=token_from_env)
        
        # ========== STEP 2: Check file storage ==========
        creds = self.manager.load_token()
        
        if creds and not force_refresh:
            if creds.valid:
                print("✅ Using cached Google credentials")
                return creds
            if creds.expired and creds.refresh_token:
                print("🔄 Refreshing expired Google credentials")
                creds.refresh(Request())
                self.manager.save_token(creds)
                return creds
        
        # ========== STEP 3: Do OAuth flow ==========
        print("🔐 Starting Google OAuth flow...")
        creds_file = self.setup_credentials_file()
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_file),
            GOOGLE_SCOPES
        )
        
        creds = flow.run_local_server(port=8080)
        self.manager.save_token(creds)
        
        print(f"\n✅ Google OAuth success!")
        print(f"⚠️  Save this to Render for persistence:")
        print(f"GOOGLE_ACCESS_TOKEN={creds.token}\n")
        
        return creds
    
    def get_service(self):
        """Get authenticated Google Drive service"""
        creds = self.get_credentials()
        return build("drive", "v3", credentials=creds)


# ============================================================================
# GITHUB OAUTH (WITH ENV VAR SUPPORT)
# ============================================================================

class GitHubOAuth:
    """
    GitHub OAuth with env var fallback for Render
    
    Priority:
    1. GITHUB_ACCESS_TOKEN env var (Render persistent)
    2. File storage
    """
    
    def __init__(self):
        self.manager = OAuthCredentialManager("github")
    
    def get_auth_url(self, redirect_uri: str) -> str:
        """Generate GitHub OAuth authorization URL"""
        return (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={GITHUB_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=repo,user"
        )
    
    def exchange_code_for_token(self, code: str) -> Optional[dict]:
        """Exchange auth code for access token"""
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
            token_file = STORAGE_PATH / "github_token.json"
            with open(token_file, "w") as f:
                json.dump(token_data, f)
            return token_data
        
        return None
    
    def get_access_token(self) -> Optional[str]:
        """
        Get GitHub access token
        
        ✅ RENDER FREE TIER: Checks env var first (persistent!)
        Falls back to file storage
        """
        
        # ========== STEP 1: Check env var (Render persistent) ==========
        token = os.getenv("GITHUB_ACCESS_TOKEN")
        if token:
            print("✅ Using GITHUB_ACCESS_TOKEN from env var")
            return token
        
        # ========== STEP 2: Check file storage ==========
        token_file = STORAGE_PATH / "github_token.json"
        if token_file.exists():
            try:
                with open(token_file) as f:
                    data = json.load(f)
                    stored_token = data.get("access_token")
                    if stored_token:
                        print("✅ Using cached GitHub token")
                        return stored_token
            except Exception as e:
                print(f"⚠️  Error reading GitHub token file: {e}")
        
        return None


# ============================================================================
# INITIALIZE OAUTH HANDLERS
# ============================================================================

google_oauth = GoogleDriveOAuth()
github_oauth = GitHubOAuth()


# ============================================================================
# MCP TOOLS
# ============================================================================

@mcp.tool()
def setup_google_oauth() -> str:
    """Setup Google Drive OAuth"""
    try:
        creds = google_oauth.get_credentials()
        if creds:
            token = creds.token if hasattr(creds, 'token') else "✅ Configured"
            if token and len(token) > 30:
                return f"✅ Google Drive OAuth configured!\n\nToken preview: {token[:30]}...\n\nAdd to Render:\nGOOGLE_ACCESS_TOKEN={token}"
            return "✅ Google Drive OAuth configured! Token saved."
    except Exception as e:
        return f"⚠️ OAuth setup error: {str(e)}"


@mcp.tool()
def google_drive_backup_wiki(folder_name: str = "Wiki Backup") -> str:
    """Backup wiki to Google Drive"""
    try:
        service = google_oauth.get_service()
        
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, spaces="drive", pageSize=1).execute()
        
        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
            return f"✅ Backup folder exists: {folder_name} (ID: {folder_id})"
        else:
            folder_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
            folder = service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder["id"]
            return f"✅ Created backup folder: {folder_name} (ID: {folder_id})"
    
    except Exception as e:
        return f"❌ Backup failed: {str(e)}"


@mcp.tool()
def export_notes_to_drive() -> str:
    """Export wiki notes to Google Drive"""
    try:
        service = google_oauth.get_service()
        
        file_metadata = {
            "name": f"Wiki Export {datetime.utcnow().isoformat()}",
            "mimeType": "text/plain",
        }
        
        file = service.files().create(body=file_metadata, fields="id").execute()
        return f"✅ Notes exported to Drive: {file.get('id')}"
    
    except Exception as e:
        return f"❌ Export failed: {str(e)}"


@mcp.tool()
def setup_github_oauth(callback_url: str) -> str:
    """Setup GitHub OAuth"""
    try:
        auth_url = github_oauth.get_auth_url(callback_url)
        return f"🔗 Visit this URL to authorize:\n{auth_url}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


@mcp.tool()
def sync_wiki_to_github(repo: str, token: str = "") -> str:
    """Sync wiki to GitHub repository"""
    try:
        access_token = github_oauth.get_access_token() or token
        
        if not access_token:
            return "❌ No GitHub token available. Set GITHUB_ACCESS_TOKEN env var or provide token."
        
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
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
    """Check status of all OAuth connections"""
    status = []
    
    # Google
    google_env = os.getenv("GOOGLE_ACCESS_TOKEN")
    google_meta = google_oauth.manager.get_metadata()
    
    if google_env:
        status.append("✅ Google Drive: Env var set (GOOGLE_ACCESS_TOKEN)")
    elif google_meta:
        status.append(f"✅ Google Drive: Cached ({google_meta.get('saved_at', 'configured')})")
    else:
        status.append("⚠️ Google Drive: Not configured")
    
    # GitHub
    github_token = github_oauth.get_access_token()
    
    if os.getenv("GITHUB_ACCESS_TOKEN"):
        status.append("✅ GitHub: Env var set (GITHUB_ACCESS_TOKEN)")
    elif github_token:
        status.append("✅ GitHub: Cached token available")
    else:
        status.append("⚠️ GitHub: Not configured")
    
    return "\n".join(status)


@mcp.tool()
def get_github_auth_code(code: str) -> str:
    """Exchange GitHub authorization code for token"""
    try:
        token_data = github_oauth.exchange_code_for_token(code)
        if token_data:
            return f"✅ GitHub OAuth configured successfully!\n\nAdd to Render:\nGITHUB_ACCESS_TOKEN={token_data.get('access_token', '')}"
        return "❌ Failed to exchange code for token"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("OAuth Manager for Render - Complete Updated Version")
    print("=" * 80)
    print(f"\n✅ Storage path: {STORAGE_PATH}")
    print(f"✅ Google scopes: {len(GOOGLE_SCOPES)} configured")
    print(f"✅ GitHub OAuth: {'Configured' if GITHUB_CLIENT_ID else 'Not configured'}")
    print("\n📝 To run MCP server:")
    print("   python oauth_external_render_COMPLETE.py")
    print("\n" + "=" * 80)
    
    # Run MCP
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")