#!/usr/bin/env python3
"""SessionStart hook: load standing project memory into the fresh context.

This is the "what do you already know about this project" moment. It runs once
per session, so it can afford a wider net than the per-prompt recall: standing
preferences, the main entities, and a short thread of what happened last time.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from memory_lib import (  # noqa: E402
    RECALL_BUDGET,
    emit_context,
    format_recall,
    log,
    project_key,
    project_scope,
    read_hook_input,
    recall_summary,
    run_memory,
    session_id_for,
    unavailable_summary,
)


def main() -> None:
    data = read_hook_input()
    cwd = data.get("cwd") or "."
    scope = project_scope(cwd)
    key = project_key(cwd)
    session_id = session_id_for(cwd)

    log(f"session_start: project={key} session={session_id}")

    async def load(client):
        # Standing preferences: how this user wants to be worked with. These
        # are global by design -- a preference for terse commit messages is not
        # project-specific.
        preferences = await client.long_term.search_preferences(
            query=f"working style conventions {key}",
            limit=8,
        )

        # The entities that matter in this codebase: services, people, systems.
        entities = await client.long_term.search_entities(
            query=key.replace("-", " "),
            limit=8,
        )

        # Where we left off. Scoped to this project across all days.
        messages = await client.short_term.search_messages(
            query="decision blocker next step",
            limit=5,
            session_prefix=scope,
        )

        return preferences, entities, messages

    result = run_memory(load, budget=RECALL_BUDGET * 2, default=None)

    if not result:
        # No memory available. Nothing goes into Claude's context, but the user
        # is told, so a dead graph does not look like an empty one.
        emit_context("SessionStart", "", unavailable_summary("project memory"))

    preferences, entities, messages = result
    context = format_recall(
        entities=entities or [],
        preferences=preferences or [],
        messages=messages or [],
        heading="Project memory",
    )

    if context:
        context += (
            f"\n\nMemory session for this project: `{session_id}`. "
            f"Use the neo4j-memory MCP tools to search deeper or record "
            f"something worth keeping."
        )

    emit_context(
        "SessionStart",
        context,
        recall_summary(
            entities=entities or [],
            preferences=preferences or [],
            messages=messages or [],
            label="project memory",
        ),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log(f"session_start fatal: {exc}")
        sys.exit(0)
