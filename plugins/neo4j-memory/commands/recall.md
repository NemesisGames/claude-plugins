---
description: Search the project memory graph and report what is known
argument-hint: [topic or question]
allowed-tools: mcp__neo4j-memory__memory_search, mcp__neo4j-memory__memory_get_entity, mcp__neo4j-memory__memory_get_context, mcp__neo4j-memory__graph_query
---

Search the knowledge graph for: **$ARGUMENTS**

1. Run `memory_search` across messages, entities, and preferences.
2. If a specific entity dominates the results, follow up with
   `memory_get_entity` (`include_neighbors: true`) to show how it connects.
3. Report what you found as a short digest — not a raw dump. Group by what it
   is (facts / preferences / past discussion), and note when something was
   recorded if the timing matters.
4. If you find contradictions between stored items, flag them explicitly
   rather than silently picking one.

If nothing comes back, say so plainly. Do not fill the gap with what you
merely infer from the current repo — the point of this command is to show what
is actually in the graph.
