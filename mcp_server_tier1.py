"""MCP server #1: tier 1.

Has access to ALL tiers (1, 2, 3). Launched with MCP_TIER=1.
"""

import os

from mcp.server.fastmcp import FastMCP

from tier_store import (
    get_tiered,
    list_recent_tiered,
    save_tiered,
    search_tiered,
    status as tier_status,
    list_books_by_tier,
    search_books,
    list_books_by_category,
    list_categories,
)

# ============================================================================
# OAUTH IMPORTS (NEW)
# ============================================================================
from oauth_external_render import (
    GoogleDriveOAuth,
    GitHubOAuth,
)


transport = os.getenv("MCP_TRANSPORT", "stdio")
port = int(os.getenv("MCP_TIER1_PORT", os.getenv("PORT", "10001")))

mcp = FastMCP(
    "recall-personal-wiki-tier1",
    host="0.0.0.0",
    port=port,
)

# ============================================================================
# OAUTH INITIALIZATION (NEW)
# ============================================================================
google_oauth = GoogleDriveOAuth()
github_oauth = GitHubOAuth()


def _format_note(note: dict) -> str:
    return (
        f"[{note['id']}] (T{note.get('tier', '?')}) {note['title']}\n"
        f"{note['content']}\n"
        f"Tags: {', '.join(note.get('tags') or [])}"
    )


@mcp.tool()
def search_tiered_wiki(query: str) -> str:
    """Search all tiers of the personal wiki (MCP 1: full access)."""
    results = search_tiered(query, limit=1000)
    if not results:
        return "No matching memories found."
    return "\n\n".join(_format_note(row) for row in results)


@mcp.tool()
def read_tiered_note(note_id: int) -> str:
    """Read a single note by id. Tier-restricted by the running server."""
    note = get_tiered(note_id)
    if not note:
        return "Note not found or not accessible from this tier server."
    return _format_note(note)


@mcp.tool()
def list_recent_tiered_notes(limit: int = 10) -> str:
    """List recent notes accessible to this tier server."""
    notes = list_recent_tiered(limit)
    if not notes:
        return "No notes found."
    return "\n".join(
        f"[{note['id']}] (T{note.get('tier', '?')}) {note['title']} "
        f"(tags: {', '.join(note.get('tags') or [])})"
        for note in notes
    )


@mcp.tool()
def save_tiered_note(title: str, content: str, tags: list[str] | None = None) -> str:
    """Save a new note. Tier is auto-assigned from tags (private -> T3)."""
    if not title.strip() or not content.strip():
        return "Title and content are required."
    note = save_tiered(title, content, tags)
    return f"Saved note [{note['id']}] {note['title']}."


@mcp.tool()
def get_tier_server_status() -> str:
    """Describe the running tier server and counts per tier."""
    info = tier_status()
    counts = ", ".join(f"T{t}: {n}" for t, n in sorted(info["rows_per_tier"].items()))
    return (
        f"MCP server tier {info['server_tier']}; "
        f"allowed tiers: {info['allowed_tiers']}; "
        f"rows: {counts or 'none'}"
    )

@mcp.tool()
def browse_tier(
    tier: int,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Browse records from a specific tier."""

    rows = list_books_by_tier(
        tier=tier,
        page=page,
        page_size=page_size,
    )

    if not rows:
        return "No records found."

    return "\n\n".join(
        f"[{row['id']}] {row['title']}\n"
        f"Tier: {row['tier']}, Score: {row['score']}\n"
        f"Categories: {', '.join(row.get('categories') or []) or 'Uncategorized'}"
        for row in rows
    )


@mcp.tool()
def search_book_titles(
    query: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Search books by title/content/category."""

    rows = search_books(
        query=query,
        page=page,
        page_size=page_size,
    )

    if not rows:
        return "No matching books found."

    return "\n\n".join(
        f"[{row['id']}] {row['title']}\n"
        f"Tier: {row['tier']}, Score: {row['score']}\n"
        f"Categories: {', '.join(row.get('categories') or []) or 'Uncategorized'}"
        for row in rows
    )


@mcp.tool()
def browse_book_category(
    category: str,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Browse books belonging to a specific category."""

    rows = list_books_by_category(
        category=category,
        page=page,
        page_size=page_size,
    )

    if not rows:
        return f"No books found in category: {category}"

    return "\n\n".join(
        f"[{row['id']}] {row['title']}\n"
        f"Tier: {row['tier']}, Score: {row['score']}\n"
        f"Categories: {', '.join(row.get('categories') or []) or 'Uncategorized'}"
        for row in rows
    )


@mcp.tool()
def get_book_categories() -> str:
    """List all available book categories and their book counts."""

    rows = list_categories()

    if not rows:
        return "No book categories found."

    return "\n".join(
        f"{row['category']}: {row['book_count']} books"
        for row in rows
    )

@mcp.tool()
def setup_google_oauth() -> str:
    """Setup Google Drive OAuth - initialize backup connection"""
    try:
        creds = google_oauth.get_credentials()
        if creds:
            return "✅ Google Drive OAuth configured! Credentials saved."
        return "⚠️ Google OAuth setup incomplete"
    except Exception as e:
        return f"❌ Google OAuth error: {str(e)}"


@mcp.tool()
def google_drive_backup_wiki(folder_name: str = "Wiki Backup") -> str:
    """Backup wiki notes to Google Drive folder"""
    try:
        service = google_oauth.get_service()
        
        # Check if folder exists
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, spaces="drive", pageSize=1).execute()
        
        files = results.get("files", [])
        if files:
            folder_id = files[0]["id"]
            return f"✅ Backup folder already exists: {folder_name}"
        else:
            # Create new folder
            folder_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder"
            }
            folder = service.files().create(body=folder_metadata, fields="id").execute()
            folder_id = folder["id"]
            return f"✅ Created backup folder: {folder_name}"
    except Exception as e:
        return f"❌ Backup failed: {str(e)}"


@mcp.tool()
def setup_github_oauth(callback_url: str) -> str:
    """Get GitHub authorization URL"""
    try:
        auth_url = github_oauth.get_auth_url(callback_url)
        return f"🔗 Authorize GitHub:\n{auth_url}"
    except Exception as e:
        return f"❌ GitHub setup error: {str(e)}"


@mcp.tool()
def check_oauth_status() -> str:
    """Check status of OAuth connections (Google Drive, GitHub)"""
    status_lines = []
    
    # Check Google
    google_meta = google_oauth.manager.get_metadata()
    if google_meta:
        saved_at = google_meta.get('saved_at', 'configured')
        status_lines.append(f"✅ Google Drive: {saved_at}")
    else:
        status_lines.append("⚠️ Google Drive: Not configured yet")
    
    # Check GitHub
    github_token = github_oauth.get_access_token()
    if github_token:
        status_lines.append("✅ GitHub: Configured")
    else:
        status_lines.append("⚠️ GitHub: Not configured yet")
    
    return "\n".join(status_lines)


if __name__ == "__main__":
    if transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")