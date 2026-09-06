const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const cors = require('cors');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// GitHub OAuth Config
const GITHUB_CLIENT_ID = 'Ov23li8bP11IVJQVJYC2';
const GITHUB_CLIENT_SECRET = process.env.GITHUB_CLIENT_SECRET; // Set in Render env vars
const GITHUB_REDIRECT_URI = 'http://localhost:3000/auth/callback';
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key'; // Change in production
const TIER_SERVER_URL = 'https://personal-wiki-tier1.onrender.com/mcp';

// ============================================
// 1. GITHUB LOGIN - Redirect to GitHub
// ============================================
app.get('/auth/login', (req, res) => {
  const authUrl = `https://github.com/login/oauth/authorize?client_id=${GITHUB_CLIENT_ID}&redirect_uri=${GITHUB_REDIRECT_URI}&scope=repo,user`;
  res.redirect(authUrl);
});

// ============================================
// 2. GITHUB CALLBACK - Exchange code for token
// ============================================
app.get('/auth/callback', async (req, res) => {
  const { code, error } = req.query;

  if (error) {
    return res.status(401).json({ error: 'GitHub auth failed' });
  }

  try {
    // Exchange code for access token
    const tokenResponse = await axios.post(
      'https://github.com/login/oauth/access_token',
      {
        client_id: GITHUB_CLIENT_ID,
        client_secret: GITHUB_CLIENT_SECRET,
        code: code,
        redirect_uri: GITHUB_REDIRECT_URI,
      },
      { headers: { Accept: 'application/json' } }
    );

    const githubToken = tokenResponse.data.access_token;

    if (!githubToken) {
      return res.status(401).json({ error: 'Failed to get GitHub token' });
    }

    // Get GitHub user info
    const userResponse = await axios.get('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${githubToken}` },
    });

    const user = userResponse.data;

    // Create JWT token for your app
    const jwtToken = jwt.sign(
      { id: user.id, login: user.login, name: user.name },
      JWT_SECRET,
      { expiresIn: '7d' }
    );

    // Redirect to frontend with JWT token
    res.redirect(`https://yourdomain.com?token=${jwtToken}`);
    // OR return JSON for API clients:
    // res.json({ token: jwtToken, user: { id: user.id, login: user.login } });
  } catch (error) {
    console.error('OAuth error:', error.message);
    res.status(500).json({ error: 'Authentication failed' });
  }
});

// ============================================
// 3. MIDDLEWARE - Verify JWT Token
// ============================================
const verifyToken = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: 'Missing token. Please authenticate first.' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (error) {
    res.status(403).json({ error: 'Invalid or expired token' });
  }
};

// ============================================
// 4. PROTECTED: Browse Tier (requires auth)
// ============================================
app.get('/api/tier/:tierNum', verifyToken, async (req, res) => {
  try {
    const { tierNum } = req.params;
    const { page = 1, page_size = 20 } = req.query;

    // Forward request to actual tier server
    const response = await axios.get(`${TIER_SERVER_URL}/tier/${tierNum}`, {
      params: { page, page_size },
    });

    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch tier data' });
  }
});

// ============================================
// 5. PROTECTED: Search Books (requires auth)
// ============================================
app.get('/api/search', verifyToken, async (req, res) => {
  try {
    const { query, page = 1, page_size = 20 } = req.query;

    if (!query) {
      return res.status(400).json({ error: 'Query parameter required' });
    }

    const response = await axios.get(`${TIER_SERVER_URL}/search`, {
      params: { query, page, page_size },
    });

    res.json(response.data);
  } catch (error) {
    res.status(500).json({ error: 'Search failed' });
  }
});

// ============================================
// 6. PUBLIC: Health check
// ============================================
app.get('/health', (req, res) => {
  res.json({ status: 'OK' });
});

// ============================================
// 7. Start Server
// ============================================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🔐 Protected tier server running on port ${PORT}`);
  console.log(`📝 Login: http://localhost:${PORT}/auth/login`);
});
