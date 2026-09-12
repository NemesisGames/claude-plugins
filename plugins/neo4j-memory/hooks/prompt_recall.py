#!/usr/bin/env python3
"""UserPromptSubmit hook: recall memory relevant to *this* prompt, and store it.

This runs on every message, so it is the latency-critical path. Two rules:

  - Read is narrow, thresholded, and time-boxed. A wide net here would inject
    junk into every single turn.
  - The write is handed to a detached background process. Entity extraction
    calls an LLM; the user must not wait on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from memory_lib import (  # noqa: E402
    MIN_PROMPT_CHARS,
    RECALL_BUDGET,
    RECALL_THRESHOLD,
    emit_context,
    format_recall,
    get_prompt,
    log,
    project_scope,
    read_hook_input,
    run_memory,
    session_id_for,
    spawn_detached,
)


def main() -> None:
    data = read_hook_input()
    prompt = get_prompt(data)
    cwd = data.get("cwd") or "."

    if not prompt:
        sys.exit(0)

    # Store every prompt, including short ones -- "ship it" is worth having in
    # the thread even though it is worthless as a search query.
    spawn_detached(
        "capture.py",
        {
            "mode": "message",
            "role": "user",
            "content": prompt,
            "session_id": session_id_for(cwd),
            "cwd": cwd,
        },
    )

    # Recall only when there is enough text to match on.
    if len(prompt) < MIN_PROMPT_CHARS:
        sys.exit(0)

    scope = project_scope(cwd)

    async def recall(client):
        entities = await client.long_term.search_entities(
            query=prompt,
            limit=4,
            threshold=RECALL_THRESHOLD,
        )
        preferences = await client.long_term.search_preferences(
            query=prompt,
            limit=3,
            threshold=RECALL_THRESHOLD,
        )
        messages = await client.short_term.search_messages(
            query=prompt,
            limit=4,
            session_prefix=scope,
            threshold=RECALL_THRESHOLD,
        )
        return entities, preferences, messages

    result = run_memory(recall, budget=RECALL_BUDGET, default=None)
    if not result:
        sys.exit(0)

    entities, preferences, messages = result
    context = format_recall(
        entities=entities or [],
        preferences=preferences or [],
        messages=messages or [],
        heading="Recalled context",
    )

    emit_context("UserPromptSubmit", context)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log(f"prompt_recall fatal: {exc}")
        sys.exit(0)
