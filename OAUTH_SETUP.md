# OAuth Setup Guide

## GitHub OAuth Flow

### Step 1: Register GitHub OAuth App
1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - **Application name**: `Personal Wiki`
   - **Homepage URL**: `https://personal-wiki-tier1.onrender.com` (or your local URL)
   - **Authorization callback URL**: `https://personal-wiki-tier1.onrender.com/oauth/github/callback`
4. Copy the **Client ID** and **Client Secret**

### Step 2: Set Environment Variables
Create a `.env` file (or set on Render):
```bash
GITHUB_CLIENT_ID=your_client_id_here
GITHUB_CLIENT_SECRET=your_client_secret_here
```

### Step 3: Start the OAuth Flow
**In your MCP server or CLI:**
```python
# Get the authorization URL
setup_github_oauth("https://personal-wiki-tier1.onrender.com/oauth/github/callback")
```

### Step 4: User Authorizes
- User clicks the returned URL
- GitHub asks for permission
- GitHub redirects to your callback URL with `code` parameter:
```
https://personal-wiki-tier1.onrender.com/oauth/github/callback?code=abc123def456...
```

### Step 5: Automatic Token Exchange
- Your Flask app **automatically exchanges** the code for an access token
- Token is saved to `/tmp/oauth_creds/github_token.json`
- You see a success response

### Step 6: Use the Token
```python
# Get stored access token
token = github_oauth.get_access_token()

# Use it to make authenticated API calls
headers = {"Authorization": f"token {token}"}
```

---

## Quick Start

### Option A: Local Testing
```bash
# Start Flask app on localhost
python app.py

# In another terminal, call MCP:
mcp tools setup_github_oauth "http://localhost:5000/oauth/github/callback"

# Click the URL, authorize, and you'll be redirected to:
# http://localhost:5000/oauth/github/callback?code=...
```

### Option B: Render Deployment
1. Deploy to Render (update Render deployment URL)
2. Set environment variables on Render dashboard
3. Call the setup tool with your Render URL
4. GitHub redirects to your Render app

---

## API Endpoints

### Check OAuth Status
```bash
GET /oauth/status
```
Response:
```json
{
  "github": "✅ Configured",
  "google": "⚠️ Not configured"
}
```

### GitHub Callback Handler
```
GET /oauth/github/callback?code=...&error=...
```

---

## Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `GITHUB_CLIENT_ID` | Yes | `Iv1.a2c3d4e5f6g7h8i9` |
| `GITHUB_CLIENT_SECRET` | Yes | `ghp_1234567890abcdefghij` |
| `PORT` | No (default: 5000) | `5000` |
| `OAUTH_STORAGE_PATH` | No (default: /tmp/oauth_creds) | `/tmp/oauth_creds` |

---

## Troubleshooting

### "Invalid Client ID"
- Check your `GITHUB_CLIENT_ID` in `.env`
- Verify it matches your GitHub app

### "Redirect URI mismatch"
- Ensure callback URL in Flask matches GitHub app settings
- Example: `https://personal-wiki-tier1.onrender.com/oauth/github/callback`

### Token not saving?
- Check `/tmp/oauth_creds/github_token.json` exists
- Verify file permissions and storage path

### "Failed to exchange code for token"
- Check your `GITHUB_CLIENT_SECRET` is correct
- Ensure network access to `https://github.com/login/oauth/access_token`
