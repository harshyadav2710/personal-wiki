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
)


transport = os.getenv("MCP_TRANSPORT", "stdio")
port = int(os.getenv("MCP_TIER1_PORT", os.getenv("PORT", "10001")))

mcp = FastMCP(
    "recall-personal-wiki-tier1",
    host="0.0.0.0",
    port=port,
)


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


if __name__ == "__main__":
    if transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
