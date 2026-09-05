"""
Get Google & GitHub OAuth tokens and export as env vars for Render.
Run this LOCALLY (not on Render) to get tokens via browser OAuth flow.

python get_oauth_tokens.py
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("OAUTH TOKEN GENERATOR FOR RENDER")
print("=" * 80)

# ============================================================================
# 1. GET GOOGLE OAUTH TOKEN
# ============================================================================
print("\n1️⃣  GOOGLE OAUTH TOKEN")
print("-" * 80)

try:
    from oauth_external_render import google_oauth
    
    print("Getting Google credentials (browser will open)...")
    creds = google_oauth.get_credentials()
    
    if creds and creds.token:
        google_token = creds.token
        print(f"✅ Got Google access token")
        print(f"   Length: {len(google_token)} chars")
        if creds.expiry:
            print(f"   Expires: {creds.expiry}")
        print(f"\n   Token: {google_token}")
    else:
        print(f"❌ Failed to get Google token")
        google_token = None
        
except Exception as e:
    print(f"❌ Google OAuth error: {e}")
    google_token = None

# ============================================================================
# 2. GET GITHUB OAUTH TOKEN
# ============================================================================
print("\n2️⃣  GITHUB OAUTH TOKEN")
print("-" * 80)

try:
    from oauth_external_render import github_oauth
    
    # Check if already stored
    stored_token = github_oauth.get_access_token()
    if stored_token:
        print(f"✅ Found stored GitHub token")
        github_token = stored_token
        print(f"   Length: {len(github_token)} chars")
        print(f"\n   Token: {github_token}")
    else:
        print("No stored GitHub token found.")
        print("\nTo get GitHub token:")
        print("1. Visit: https://github.com/settings/tokens")
        print("2. Create new token (classic)")
        print("3. Select scopes: repo, user")
        print("4. Copy token and paste below")
        github_token = input("\nPaste GitHub token here (or press Enter to skip): ").strip()
        
        if github_token:
            print(f"✅ GitHub token captured")
            print(f"   Length: {len(github_token)} chars")
        
except Exception as e:
    print(f"⚠️  GitHub token note: {e}")
    github_token = None

# ============================================================================
# 3. OUTPUT FOR RENDER ENV VARS
# ============================================================================
print("\n" + "=" * 80)
print("COPY & PASTE TO RENDER ENVIRONMENT")
print("=" * 80)

env_vars = {}

if google_token:
    env_vars["GOOGLE_ACCESS_TOKEN"] = google_token

if github_token:
    env_vars["GITHUB_ACCESS_TOKEN"] = github_token

if env_vars:
    print("\nAdd these to Render Environment Variables:")
    print("-" * 80)
    
    for key, value in env_vars.items():
        print(f"{key}={value}")
    
    print("\n" + "-" * 80)
    print("Or in JSON format:")
    print(json.dumps(env_vars, indent=2))
else:
    print("\n❌ No tokens obtained. Make sure you:")
    print("   1. Have GOOGLE_CREDENTIALS_JSON set locally")
    print("   2. Run this script locally (not on Render)")
    print("   3. Allow browser popup for Google OAuth")

# ============================================================================
# 4. CODE CHANGES FOR RENDER
# ============================================================================
print("\n" + "=" * 80)
print("CODE CHANGES NEEDED")
print("=" * 80)

print("""
Update oauth_external_render.py to read tokens from env vars:

# At the top of GoogleDriveOAuth class:
def get_credentials(self, force_refresh=False):
    # First, check if token is in env var (Render)
    token_from_env = os.getenv("GOOGLE_ACCESS_TOKEN")
    if token_from_env and not force_refresh:
        from google.oauth2.credentials import Credentials
        return Credentials(token=token_from_env)
    
    # Otherwise, do the normal OAuth flow
    creds = self.manager.load_token()
    if creds and not force_refresh:
        if creds.valid:
            return creds
    ...

# For GitHub:
def get_access_token(self) -> Optional[str]:
    # First check env var (Render)
    token = os.getenv("GITHUB_ACCESS_TOKEN")
    if token:
        return token
    
    # Fall back to stored file
    token_file = STORAGE_PATH / "github_token.json"
    if token_file.exists():
        with open(token_file) as f:
            data = json.load(f)
            return data.get("access_token")
    return None
""")

print("\n" + "=" * 80)
print("STEPS")
print("=" * 80)
print("""
1. Run this script locally: python get_oauth_tokens.py
2. Copy the tokens shown above
3. Go to Render dashboard → Environment
4. Add GOOGLE_ACCESS_TOKEN and GITHUB_ACCESS_TOKEN
5. Update oauth_external_render.py with env var checks (see above)
6. Deploy to Render
7. Your tokens now persist across spins!
""")

print("=" * 80)