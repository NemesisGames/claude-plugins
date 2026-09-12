# ahuerta-plugins

A Claude Code plugin marketplace.

## Install

Add the marketplace, then install the plugin you want:

```
/plugin marketplace add <your-github-user>/claude-plugins
/plugin install neo4j-memory@ahuerta-plugins
```

In the Claude desktop app, use the **+** button next to the prompt box →
**Plugins** → **Add plugin**, and pick the plugin from this marketplace once
it is registered.

## Plugins

### neo4j-memory

Persistent graph memory for Claude Code, backed by
[Neo4j Agent Memory](https://neo4j.com/labs/agent-memory/). Claude remembers
your projects across sessions — decisions, constraints, conventions, who owns
what — in a knowledge graph you control.

Requires your own Neo4j instance, an Anthropic API key, and a one-time Python
install. See [plugins/neo4j-memory/README.md](plugins/neo4j-memory/README.md)
for setup, and run its `scripts/doctor.py` before trusting it.

## Repository layout

```
.claude-plugin/
└── marketplace.json        catalog; lists each plugin and where to find it
plugins/
└── neo4j-memory/           one self-contained plugin
    ├── .claude-plugin/
    │   └── plugin.json     the plugin's own manifest
    ├── hooks/
    ├── commands/
    ├── skills/
    └── scripts/
```

Plugins are copied to a cache directory on install, so each one must be
self-contained — a plugin cannot reference files outside its own directory.

## Releasing a change

Claude Code decides whether a user gets an update from the `version` field, so
edit both when you change a plugin:

1. Bump `version` in `plugins/<name>/.claude-plugin/plugin.json`
2. Bump the matching `version` in `.claude-plugin/marketplace.json`
3. Commit and push

Users pick the change up on their next marketplace refresh, or immediately with
`/plugin marketplace update ahuerta-plugins`.

Validate before pushing:

```
claude plugin validate .
claude plugin validate ./plugins/neo4j-memory
```
