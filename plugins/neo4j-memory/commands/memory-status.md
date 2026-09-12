---
description: Show what the memory graph holds for this project, and whether it is healthy
allowed-tools: Bash, mcp__neo4j-memory__graph_query, mcp__neo4j-memory__memory_list_sessions
---

Report the state of the project memory graph.

1. Run the doctor script to verify connectivity, the embedding model, and
   vector index dimensions:

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
   ```

2. Then use `graph_query` for the content picture:

   ```cypher
   MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC
   ```

   ```cypher
   MATCH (e:Entity) RETURN e.name, e.type, e.description
   ORDER BY e.updated_at DESC LIMIT 15
   ```

   ```cypher
   MATCH (p:Preference) RETURN p.category, p.preference, p.confidence
   ORDER BY p.confidence DESC LIMIT 15
   ```

3. Call `memory_list_sessions` to show which sessions exist for this project
   (they are prefixed `cc:<project>:`).

Present it as a compact status report: is memory working, how much is stored,
and what the most recent things learned were. Flag anything that looks wrong —
zero entities after heavy use, a dimension mismatch, or preferences that
contradict each other.
