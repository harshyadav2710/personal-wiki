// ============================================
// CLIENT EXAMPLE - Using Protected Tier API
// ============================================

const API_BASE = 'https://personal-wiki-tier1.onrender.com';

// ============================================
// 1. LOGIN - Start GitHub OAuth flow
// ============================================
function login() {
  window.location.href = `${API_BASE}/auth/login`;
}

// ============================================
// 2. GET TOKEN FROM URL (after redirect back)
// ============================================
function getTokenFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  if (token) {
    localStorage.setItem('auth_token', token);
    window.history.replaceState({}, document.title, window.location.pathname);
    return token;
  }
  return localStorage.getItem('auth_token');
}

// ============================================
// 3. FETCH PROTECTED TIER DATA
// ============================================
async function fetchTierBooks(tierNum, page = 1) {
  const token = getTokenFromUrl();

  if (!token) {
    console.error('❌ Not authenticated. Please login first.');
    return;
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/tier/${tierNum}?page=${page}&page_size=20`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log(`✅ Tier ${tierNum} books:`, data);
    return data;
  } catch (error) {
    console.error('❌ Error fetching tier data:', error.message);
  }
}

// ============================================
// 4. SEARCH BOOKS (requires auth)
// ============================================
async function searchBooks(query, page = 1) {
  const token = getTokenFromUrl();

  if (!token) {
    console.error('❌ Not authenticated. Please login first.');
    return;
  }

  try {
    const response = await fetch(
      `${API_BASE}/api/search?query=${encodeURIComponent(query)}&page=${page}&page_size=20`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    console.log(`✅ Search results for "${query}":`, data);
    return data;
  } catch (error) {
    console.error('❌ Error searching:', error.message);
  }
}

// ============================================
// 5. LOGOUT
// ============================================
function logout() {
  localStorage.removeItem('auth_token');
  console.log('✅ Logged out');
}

// ============================================
// 6. CHECK IF LOGGED IN
// ============================================
function isLoggedIn() {
  return !!getTokenFromUrl();
}

// ============================================
// EXAMPLE USAGE (in HTML)
// ============================================
/*
<!DOCTYPE html>
<html>
<head>
  <title>Tier Books</title>
</head>
<body>
  <div id="auth">
    <button onclick="login()">Login with GitHub</button>
  </div>

  <div id="content" style="display:none">
    <button onclick="logout()">Logout</button>
    <button onclick="fetchTierBooks(1)">Fetch Tier 1</button>
    <button onclick="searchBooks('Tom Sawyer')">Search Tom Sawyer</button>
    <pre id="results"></pre>
  </div>

  <script src="client-example.js"></script>
  <script>
    if (isLoggedIn()) {
      document.getElementById('auth').style.display = 'none';
      document.getElementById('content').style.display = 'block';
    }
  </script>
</body>
</html>
*/
