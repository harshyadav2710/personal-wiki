"""MCP server #3: tier 3.

Has access to ONLY Tier 3. Launched with MCP_TIER=3.
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
port = int(os.getenv("MCP_TIER3_PORT", os.getenv("PORT", "10003")))

mcp = FastMCP(
    "recall-personal-wiki-tier3",
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
    """Search ONLY Tier 3 of the personal wiki (MCP 3)."""
    results = search_tiered(query, limit=10)
    if not results:
        return "No matching memories found in Tier 3."
    return "\n\n".join(_format_note(row) for row in results)


@mcp.tool()
def read_tiered_note(note_id: int) -> str:
    """Read a single note by id if it is in Tier 3."""
    note = get_tiered(note_id)
    if not note:
        return "Note not found or not accessible from this tier server (Tiers 1 and 2 are hidden)."
    return _format_note(note)


@mcp.tool()
def list_recent_tiered_notes(limit: int = 10) -> str:
    """List recent Tier 3 notes."""
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
    """Save a new note. New notes default to Tier 3 unless they are private
    (private notes are also Tier 3, with is_private=true)."""
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
