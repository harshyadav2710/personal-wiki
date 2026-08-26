# Recall personal wiki

A small Flask + PostgreSQL personal wiki with a chat interface. Save notes, browse recent notes, and ask Recall questions about your saved content.

## Second-brain architecture

The project follows a small language-model-inspired pipeline:

`notes -> retrieve relevant memory -> Claude calls MCP tools -> Claude answers`

- `app.py` owns the web and PostgreSQL boundary.
- `wiki_engine.py` owns browser-chat retrieval and grounded fallback answers.
- PostgreSQL is the long-term memory store.
- Claude uses the MCP server to search and update the PostgreSQL knowledge store.

This follows Karpathy's focus on understanding the data, tokenization, context, and generation loop. The small trainable local model remains available for learning experiments, while Claude provides the conversational intelligence through MCP.

The project also includes an actual small nanoGPT-style decoder in `karpathy_nanogpt.py`. Train it on the ingested corpus with `python train_nanogpt.py`. The browser chat uses grounded answers by default; nanoGPT remains available for training experiments by changing `LLM_BACKEND=nanogpt`. Claude Desktop uses the MCP tools described below.

## Run locally

1. Install Python dependencies:

   `python -m pip install -r requirements.txt`

2. Install PostgreSQL locally, create the `personal_wiki` database, and set `PG_DSN` in `.env`.

3. Start the app:

   `python app.py`

4. Open http://127.0.0.1:5000

PostgreSQL stores your notes, chunks, and chat history. No Ollama service is required.

## PostgreSQL migration and MCP

After installing PostgreSQL natively, create a database named `personal_wiki` and set `PG_DSN` in `.env`.

Install dependencies and ingest files, including raw JSON and searchable text chunks. Large documents are stored intact while search runs on bounded chunks:

`python -m pip install -r requirements.txt`

`python ingest_files.py`

Copy `mcp.json.example` to `mcp.json`, replace the project path, and add it to Claude Desktop's MCP configuration. Claude can then call `search_personal_wiki` against the local PostgreSQL knowledge store.
