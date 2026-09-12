---
description: Store something in the project memory graph, on purpose
argument-hint: [what to remember]
allowed-tools: mcp__neo4j-memory__memory_add_fact, mcp__neo4j-memory__memory_add_preference, mcp__neo4j-memory__memory_add_entity, mcp__neo4j-memory__memory_create_relationship, mcp__neo4j-memory__memory_search
---

Record this in the project knowledge graph: **$ARGUMENTS**

Follow the `graph-memory` skill conventions. Specifically:

1. Decide what kind of memory this is — a fact, a preference, an entity, or a
   relationship between entities. It may be several.
2. Search first with `memory_search` to check whether it already exists or
   contradicts something stored. If it contradicts, say so before writing.
3. Write it with the appropriate tool, using POLE+O types and
   `UPPER_SNAKE_CASE` relationships.
4. Confirm in one line what you stored and where. Do not restate the whole
   graph back at me.

If what I asked you to remember is transient — a file path, a command I just
ran, today's branch name — push back instead of storing it.
