# Tiered MCP servers

The project now exposes the personal wiki through three segregated MCP servers
in addition to the original `recall-personal-wiki` server.

## Tiers

Tier assignment is curation-based, driven by a review/sale proxy:

```
score = reviews * 1.0 + sales * 0.1
score >= 80  -> Tier 1   (best / most-reviewed)
score >= 25  -> Tier 2   (mid curation)
score <  25  -> Tier 3   (least curated)
private      -> Tier 3   (forced)
```

The classifier (`tier_classify.py`) seeds scores from a whitelist of canonical
Gutenberg titles and from the Gutenberg ID range. Replace its heuristic with
real review/sale data when you have it.

## Server segregation

| Server                    | MCP_TIER | Sees tiers |
|---------------------------|----------|------------|
| `recall-personal-wiki-tier1` | 1        | 1, 2, 3    |
| `recall-personal-wiki-tier2` | 2        | 2, 3       |
| `recall-personal-wiki-tier3` | 3        | 3          |

Enforcement is application-level: each server reads its tier from
`MCP_TIER` and `tier_store.allowed_tiers()` filters every query.

## Files

- `tier_schema.sql` - additive DDL: `tier_assignments` table and `wiki_notes_tiered` view.
- `tier_store.py` - tier-aware storage wrappers.
- `tier_classify.py` - heuristic review/sale classifier.
- `ingest_tiers.py` - populates `tier_assignments` from existing `wiki_notes`.
- `mcp_server_tier1.py`, `mcp_server_tier2.py`, `mcp_server_tier3.py` - the three
  segregated MCP entrypoints.

## One-time setup

```
python ingest_files.py        # ingest the source files (existing)
python ingest_tiers.py        # assign tiers to every note
```

The `mcp.json` at the repo root already wires all three tier servers for
Claude Desktop.
