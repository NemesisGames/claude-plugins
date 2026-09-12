---
description: Remove or supersede something in the memory graph
argument-hint: [what to forget]
allowed-tools: mcp__neo4j-memory__memory_search, mcp__neo4j-memory__memory_get_entity, mcp__neo4j-memory__graph_query, mcp__neo4j-memory__memory_add_fact
---

I want this out of memory: **$ARGUMENTS**

The MCP server blocks write Cypher, so deletion is a two-step process and you
must not pretend otherwise.

1. Find it. Use `memory_search` and `graph_query` to locate the exact nodes —
   show me their labels, ids, and content so I can confirm we have the right
   ones.

2. Ask me which of these applies:
   - **Superseded** — the fact changed. You can handle this yourself: write
     the corrected fact with `memory_add_fact` and an appropriate `valid_from`.
     Temporal validity means the old version stays as history, which is
     usually what you actually want.
   - **Hard delete** — it must be gone (it was wrong, or it is sensitive).
     This needs write access I have to run myself. Give me the exact Cypher
     `DETACH DELETE` statement, scoped by id, to paste into Neo4j Browser or
     cypher-shell. Do not attempt it through the MCP tools.

Never delete without showing me what will be removed first. If the match is
ambiguous, stop and ask rather than guessing at scope.
