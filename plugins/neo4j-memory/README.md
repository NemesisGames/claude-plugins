# neo4j-memory

Supermemory-style persistent memory for Claude Code, backed by your own Neo4j
instance via [Neo4j Agent Memory](https://neo4j.com/labs/agent-memory/).

Claude remembers your projects across sessions — decisions, constraints,
conventions, who owns what — in a knowledge graph you control.

## How it compares to supermemory

Supermemory self-hosted runs a single binary with an embedded graph engine,
local embeddings (`Xenova/bge-base-en-v1.5`, 768d), and your choice of LLM.
This plugin assembles the same shape out of Neo4j parts:

| | supermemory (self-hosted) | this plugin |
| --- | --- | --- |
| Store | Embedded graph engine | Your Neo4j |
| Embeddings | `Xenova/bge-base-en-v1.5`, local | `BAAI/bge-base-en-v1.5`, local (same model, ONNX vs PyTorch port) |
| Extraction LLM | Yours, any provider | Yours, Anthropic |
| Recall | Injected into the prompt | Injected via `UserPromptSubmit` hook |
| Surface | HTTP API + plugins | MCP tools + hooks + slash commands |

The trade you are making: supermemory hides the plumbing but owns the store.
Here the graph is yours — queryable with Cypher, joinable against whatever
else is already in that database.

## What it does

Four hooks, running automatically:

- **SessionStart** — loads standing preferences, the project's known entities,
  and where you left off.
- **UserPromptSubmit** — semantic search against your prompt; injects only
  matches above a similarity floor. Stores the prompt.
- **Stop** — queues Claude's reply for entity extraction, in the background.
- **SessionEnd** — asks Claude to distil the session into durable facts,
  preferences, and entities. Most sessions produce nothing, by design.

Plus 16 MCP tools, four slash commands (`/remember`, `/recall`,
`/memory-status`, `/forget`), and a skill teaching Claude when memory is worth
writing to.

## Install

### 1. Dependencies

```bash
pip install "neo4j-agent-memory[mcp,anthropic,sentence-transformers,spacy,gliner]"
python -m spacy download en_core_web_sm
```

Requires Python 3.10+ and Neo4j 5.20+ with APOC. Verified working on 3.14.

All five extras matter:

| Extra | Why |
| --- | --- |
| `mcp` | The `neo4j-agent-memory mcp serve` command the plugin's MCP server runs |
| `anthropic` | Native adapter with forced tool use. Without it the library silently falls back to LiteLLM |
| `sentence-transformers` | Local embeddings — the whole point of the no-second-API-key setup |
| `spacy`, `gliner` | Local entity extractors |

Skipping `spacy` and `gliner` is the expensive mistake: `env.example` enables
both, and without them every message falls through to the Anthropic extractor,
so you pay per turn for work that would have run locally for free. If you
deliberately want LLM-only extraction, set `NAM_EXTRACTION__ENABLE_SPACY=false`
and `NAM_EXTRACTION__ENABLE_GLINER=false` rather than just omitting the extras.

Note that `sentence-transformers` and `gliner` both pull PyTorch — around
2-3 GB on Windows.

### 2. Environment

Copy `env.example` and set the values **as real environment variables**, not
in a `.env` file — hooks are spawned by Claude Code, not by a shell.

macOS / Linux, in `~/.zshrc` or `~/.bashrc`:

```bash
export NAM_NEO4J__URI="neo4j+s://xxxx.databases.neo4j.io"
export NAM_NEO4J__USERNAME="neo4j"
export NAM_NEO4J__PASSWORD="..."
export NAM_LLM="anthropic/claude-sonnet-4-5"
export NAM_LLM_API_KEY="sk-ant-..."
export NAM_EMBEDDING="BAAI/bge-base-en-v1.5"
export NAM_EMBEDDING__PROVIDER="sentence_transformers"
export NAM_EMBEDDING__DIMENSIONS="768"
```

Windows PowerShell (persists across sessions):

```powershell
setx NAM_NEO4J__URI "neo4j+s://xxxx.databases.neo4j.io"
setx NAM_NEO4J__PASSWORD "..."
setx NAM_LLM_API_KEY "sk-ant-..."
setx NAM_EMBEDDING "BAAI/bge-base-en-v1.5"
setx NAM_EMBEDDING__PROVIDER "sentence_transformers"
setx NAM_EMBEDDING__DIMENSIONS "768"
```

Open a new terminal afterwards — `setx` does not affect the current one.

### 3. Make sure the launchers are reachable

The plugin starts two things by name, and both are resolved through `PATH` by
a process spawn rather than by your shell:

| What | Runs | Needs |
| --- | --- | --- |
| MCP server | `neo4j-agent-memory` | its console script on `PATH` |
| The four hooks | `python` | Python 3.10+ on `PATH` |

Check both:

```bash
# macOS / Linux
which neo4j-agent-memory && python --version

# Windows
where neo4j-agent-memory && python --version
```

**If `neo4j-agent-memory` isn't found**, pip almost certainly did a *user-site*
install because it couldn't write to the interpreter's directory. The package
imports fine; only the console script landed somewhere `PATH` doesn't look:

- Windows: `%APPDATA%\Python\Python3XX\Scripts\`
- macOS / Linux: `~/.local/bin`

Either add that directory to `PATH`, or point the plugin straight at the
executable without touching `PATH` at all:

```bash
# Windows
setx NEO4J_MEMORY_CMD "C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts\neo4j-agent-memory.exe"

# macOS / Linux
export NEO4J_MEMORY_CMD="$HOME/.local/bin/neo4j-agent-memory"
```

**If `python` isn't found** (common on Debian, Ubuntu, and recent macOS, which
ship only `python3`), the hooks cannot run. They fail silently by design, so
the symptom is memory that simply never happens — no error anywhere. Install a
`python` shim, or use a virtualenv, which provides one.

When the MCP server can't start, Claude Code reports only
`CONNECTION_CLOSED` with no further detail. That message almost always means
one of these two launchers, not a problem with Neo4j.

### 4. Verify before wiring it in

```bash
python scripts/doctor.py
```

The doctor checks both launchers above, then the credentials, the embedding
model, and the vector index dimensions. The first run downloads the embedding
model (~440MB) and may take a minute.

Do not skip this step: a dimension mismatch or a missing extra fails
*silently* at runtime, and you will think the plugin simply does nothing.

### 5. Load the plugin

This plugin ships inside a marketplace repo, so install it from there:

```
/plugin marketplace add <owner>/claude-plugins
/plugin install neo4j-memory@ahuerta-plugins
```

A local path works too, if you have the repo checked out:

```
/plugin marketplace add /path/to/claude-plugins
```

**Claude desktop app**: `--plugin-dir` and the `/plugin` panel are terminal-CLI
features. Use the **+** button next to the prompt box → **Plugins** →
**Add plugin**, and pick this plugin from the marketplace once registered.

**Terminal CLI only**, for developing against a working copy without
installing:

```bash
claude --plugin-dir /path/to/claude-plugins/plugins/neo4j-memory
```

After installing, **fully quit and reopen** the app. Plugin MCP servers do not
connect mid-session — in desktop sessions they wait for the next session.

### 6. Confirm

Start a session and run `/memory-status`. Then have a real conversation, end
it, and start a new one — the SessionStart banner should reflect what you
discussed.

## Schema

Node labels the library creates: `Conversation`, `Message`, `Entity`,
`Preference`, `Fact`, `Trace`, `Step`. Entities use POLE+O typing
(`PERSON`, `OBJECT`, `LOCATION`, `EVENT`, `ORGANIZATION`).

Sessions are keyed `cc:<project>:<date>`, where `<project>` comes from the git
remote (falling back to directory name + path hash). So the same repo cloned
twice shares memory, and two unrelated directories both called `api` do not.

Entities, facts, and preferences are **global** — deliberately. A preference
for terse commit messages is not project-specific, and knowing that Service A
calls Service B is useful from either repo. Only conversation history is
scoped per project.

Inspect it directly:

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(*) ORDER BY count(*) DESC;
MATCH (e:Entity) RETURN e.name, e.type, e.description ORDER BY e.updated_at DESC LIMIT 20;
```

## Cost and latency

- **Recall**: local embedding (~30-60ms CPU) plus a Neo4j vector query. Budget
  is 6s, then it gives up silently.
- **Capture**: detached background process. Zero added latency to your turn.
- **Extraction**: spaCy and GLiNER run locally and free; the Anthropic
  fallback fires only on ambiguous text. Set
  `NAM_EXTRACTION__ENABLE_LLM_FALLBACK=false` to eliminate per-message API
  cost entirely, at some accuracy cost.
- **Session distillation**: one Sonnet call per session end, skipped for
  sessions under four turns.

## Failure behaviour

Every hook catches everything and exits 0. If Neo4j is unreachable, the VPN is
off, or the model cache is cold, you get *no memory* — never a broken session,
never an error banner. Turn on `NEO4J_MEMORY_DEBUG=1` to log to
`~/.claude/neo4j-memory.log` when silence is suspicious.

## Security notes

- Recalled memory is injected wrapped in a tag and explicitly labelled as
  background data, not instructions. This matters: memory is written by past
  sessions, and text in a graph should never be able to issue commands.
- The MCP server blocks write Cypher. `graph_query` is read-only; deletions
  require you to run Cypher yourself, which `/forget` is built around.
- Local embeddings mean message content is never sent to an embedding
  provider. It *is* sent to Anthropic during extraction — set
  `NAM_EXTRACTION__ENABLE_LLM_FALLBACK=false` if that is not acceptable.

## Known rough edges

This targets Neo4j Agent Memory, which Neo4j labels **Experimental ·
Community Supported**. Specifically:

- Method signatures used by the hooks (`search_messages(session_prefix=...)`,
  `search_preferences(threshold=...)`) are from the current SDK. If a release
  changes them, the hooks degrade to silence rather than erroring — check the
  debug log.
- Changing `NAM_EMBEDDING` later requires rebuilding vector indexes. See
  [Migrate Embedding Model](https://neo4j.com/labs/agent-memory/how-to/migrate-embedding-model/).
- `agent_response` is not passed to the Stop hook on every Claude Code build;
  `capture.py` falls back to reading the transcript file.
