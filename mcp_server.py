import os
from mcp.server.fastmcp import FastMCP

from postgres_store import get_note, list_recent_notes, save_note, search_notes


mcp = FastMCP("recall-personal-wiki")


@mcp.tool()
def search_personal_wiki(query: str) -> str:
    """Search the user's private personal wiki and return relevant memory."""
    results = search_notes(query)

    if not results:
        return "No matching memories found."

    return "\n\n".join(
        f"[{result['id']}] {result['title']}\n"
        f"{result['content']}\n"
        f"Tags: {', '.join(result['tags'])}"
        for result in results
    )


@mcp.tool()
def read_personal_note(note_id: int) -> str:
    """Read one complete personal wiki note by its PostgreSQL id."""
    note = get_note(note_id)

    if not note:
        return "Note not found."

    return (
        f"[{note['id']}] {note['title']}\n"
        f"{note['content']}\n"
        f"Tags: {', '.join(note['tags'])}"
    )


@mcp.tool()
def list_recent_personal_notes(limit: int = 10) -> str:
    """List recent notes in the personal wiki."""
    limit = max(1, min(limit, 50))

    notes = list_recent_notes(limit)

    return (
        "\n".join(
            f"[{note['id']}] {note['title']} "
            f"(tags: {', '.join(note['tags'])})"
            for note in notes
        )
        or "No notes found."
    )


@mcp.tool()
def save_personal_note(
    title: str,
    content: str,
    tags: list[str] | None = None
) -> str:
    """Save a new note to the personal wiki and index it for search."""

    if not title.strip() or not content.strip():
        return "Title and content are required."

    note = save_note(title, content, tags)

    return f"Saved note [{note['id']}] {note['title']}."


@mcp.tool()
def get_wiki_status() -> str:
    """Check that the Recall PostgreSQL knowledge store is available."""

    try:
        search_notes("status")
        return "Recall PostgreSQL knowledge store is available."

    except Exception as error:
        return f"Recall PostgreSQL is unavailable: {error}"


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "http":
        port = int(os.getenv("PORT", "10000"))

        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=port,
        )

    else:
        mcp.run(
            transport="stdio"
        )