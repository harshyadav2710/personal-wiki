import os
import json
import ast
import operator
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from postgres_store import connect, initialize_schema, search_notes
from wiki_engine import LLM_BACKEND, answer_question_from_notes

load_dotenv()
app = Flask(__name__)

postgres_status = "PostgreSQL is not connected"
try:
    initialize_schema()
    postgres_status = "Connected to PostgreSQL"
except RuntimeError:
    pass


def local_notes():
    return [
        {
            "id": "demo-1",
            "title": "Welcome to your wiki",
            "content": "Capture ideas, decisions, links, and things you want to remember. Ask the assistant anything about your notes.",
            "tags": ["getting-started"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": "demo-2",
            "title": "Weekly review ritual",
            "content": "On Friday, review open loops, write down useful lessons, and choose three priorities for next week.",
            "tags": ["routine", "work"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]


def postgres_notes():
    with connect() as connection:
        rows = connection.execute("""SELECT id, title, content, tags, created_at
                        FROM wiki_notes
                        ORDER BY CASE WHEN tags @> '[\"myself\"]'::jsonb OR lower(title) LIKE '%%personal%%' THEN 0 ELSE 1 END,
                             created_at DESC""").fetchall()
    return [{"_id": row["id"], **row} for row in rows]


def serialize_postgres_note(note):
    return {
        "id": str(note["id"] if "id" in note else note["_id"]),
        "title": note.get("title", "Untitled note"),
        "content": note.get("content", ""),
        "tags": note.get("tags", []),
        "created_at": note.get("created_at", datetime.now(timezone.utc)).isoformat(),
    }


def calculate_expression(message):
    expression = message.replace("=", "").strip()
    if not expression or not all(character in "0123456789+-*/(). %" for character in expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval").body
        operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

        def evaluate(node):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in operations:
                return operations[type(node.op)](evaluate(node.left), evaluate(node.right))
            raise ValueError

        return str(evaluate(tree))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None


@app.get("/")
def index():
    return render_template("index.html", postgres_status=postgres_status)


@app.get("/api/notes")
def get_notes():
    try:
        return jsonify({"notes": [serialize_postgres_note(note) for note in postgres_notes()], "postgres_connected": True})
    except RuntimeError:
        return jsonify({"notes": local_notes(), "postgres_connected": False})


@app.post("/api/notes")
def create_note():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()
    content = str(payload.get("content", "")).strip()
    tags = [tag.strip() for tag in payload.get("tags", []) if str(tag).strip()]

    if not title or not content:
        return jsonify({"error": "A title and note content are required."}), 400
    try:
        with connect() as connection:
            row = connection.execute(
                """INSERT INTO wiki_notes (source_id, title, content, tags, raw_data, created_at)
                   VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id, title, content, tags, created_at""",
                (f"app:{datetime.now(timezone.utc).timestamp()}", title, content, json.dumps(tags), json.dumps({}), datetime.now(timezone.utc)),
            ).fetchone()
            for index, chunk in enumerate(content.split("\n\n")):
                connection.execute("INSERT INTO wiki_chunks (note_id, chunk_index, content) VALUES (%s, %s, %s)", (row["id"], index, chunk))
            connection.commit()
        return jsonify({"note": serialize_postgres_note(row)}), 201
    except RuntimeError:
        return jsonify({"error": "PostgreSQL is unavailable. Start PostgreSQL or check PG_DSN."}), 503


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Ask a question or share something to remember."}), 400

    math_answer = calculate_expression(message)
    if math_answer is not None:
        return jsonify({"answer": math_answer, "matches": []})

    if message.lower().strip(" .,!?\n") in {"hi", "hello", "hey", "hiya", "good morning", "good afternoon", "good evening"}:
        answer = "Hi. What would you like to remember or find in your wiki?"
        try:
            with connect() as connection:
                connection.execute("INSERT INTO wiki_chats (message, answer, raw_data, created_at) VALUES (%s, %s, %s::jsonb, %s)", (message, answer, json.dumps({}), datetime.now(timezone.utc)))
                connection.commit()
        except RuntimeError:
            pass
        return jsonify({"answer": answer, "matches": []})

    configuration_question = message.lower()
    if "mcp" in configuration_question and any(term in configuration_question for term in ("ai", "connect", "connected", "use", "using")):
        return jsonify({
            "answer": "The Recall MCP server connects Claude Desktop to your PostgreSQL personal wiki. The browser chat is a separate interface and uses the wiki's grounded answers; it does not connect to Claude through MCP.",
            "matches": [],
        })

    try:
        personal_question = any(phrase in message.lower() for phrase in (
            "about myself", "about me", "my background", "my profile", "who am i",
            "my achievement", "my project", "my skill", "my education", "my experience",
            "my career", "my qualification", "my qualification",
        )) or (
            any(re.search(rf"\b{word}\b", message.lower()) for word in ("achievement", "achievements", "projects", "skills", "education", "experience", "career", "qualification"))
            and any(re.search(rf"\b{word}\b", message.lower()) for word in ("my", "me", "myself", "i"))
        )
        if personal_question:
            with connect() as connection:
                retrieved_notes = connection.execute(
                          """SELECT id, title, content, tags, created_at
                              FROM wiki_notes
                              WHERE tags @> %s::jsonb
                                  OR (lower(title) LIKE %s AND NOT tags @> %s::jsonb)
                              ORDER BY tags @> %s::jsonb DESC, created_at DESC
                              LIMIT 5""",
                          (json.dumps(["myself"]), "%personal%", json.dumps(["file-ingestion"]), json.dumps(["myself"])),
                ).fetchall()
        else:
            retrieved_notes = search_notes(message)
        if not retrieved_notes:
            retrieved_notes = postgres_notes()[:10]
        answer = answer_question_from_notes(message, retrieved_notes)
        matching_notes = [serialize_postgres_note(note) for note in retrieved_notes]
        with connect() as connection:
            connection.execute("INSERT INTO wiki_chats (message, answer, raw_data, created_at) VALUES (%s, %s, %s::jsonb, %s)", (message, answer, "{}", datetime.now(timezone.utc)))
            connection.commit()
    except RuntimeError:
        answer = "PostgreSQL is unavailable. Start PostgreSQL and try again."
        matching_notes = []
    return jsonify({"answer": answer, "matches": matching_notes})


@app.get("/api/health")
def health():
    return jsonify({"postgres_connected": postgres_status == "Connected to PostgreSQL", "llm_backend": LLM_BACKEND, "status": postgres_status})


if __name__ == "__main__":
    app.run(debug=False, port=int(os.getenv("PORT", "5000")))
