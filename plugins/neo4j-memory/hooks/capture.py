#!/usr/bin/env python3
"""Capture: write conversation turns into the graph.

Runs in two modes:

  hook mode     (no args)     -- invoked by the Stop hook. Reads the transcript
                                 tail, queues the assistant's answer, returns
                                 immediately.
  worker mode   (--worker)    -- invoked detached by another hook. Does the
                                 actual Neo4j + LLM work, with no one waiting.

Splitting these is the whole trick. Entity extraction is an LLM round trip;
running it inline would add seconds to every turn.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from memory_lib import (  # noqa: E402
    WRITE_BUDGET,
    log,
    read_hook_input,
    run_memory,
    session_id_for,
    spawn_detached,
    transcript_tail,
)

# Content shorter than this is not worth an extraction call.
MIN_EXTRACT_CHARS = 40


def worker() -> None:
    """Do the write. Nothing is waiting on us, so we can take our time."""
    payload = read_hook_input()
    content = (payload.get("content") or "").strip()
    role = payload.get("role") or "user"
    session_id = payload.get("session_id")

    if not content or not session_id:
        return

    # Extraction is where the Anthropic key gets spent. Only pay for it on
    # substantive turns; a one-word reply has no entities in it.
    extract = len(content) >= MIN_EXTRACT_CHARS

    async def write(client):
        await client.short_term.add_message(
            session_id=session_id,
            role=role,
            content=content,
            extract_entities=extract,
        )
        return True

    ok = run_memory(write, budget=WRITE_BUDGET, default=False)
    log(f"capture worker: role={role} extract={extract} ok={ok} len={len(content)}")


def hook() -> None:
    """Stop hook: queue the assistant's last answer, then get out of the way."""
    data = read_hook_input()
    cwd = data.get("cwd") or "."
    session_id = session_id_for(cwd)

    content = (data.get("agent_response") or "").strip()

    # Older Claude Code builds do not pass agent_response; fall back to the
    # transcript, which is always on disk.
    if not content:
        turns = transcript_tail(data.get("transcript_path"), max_chars=4000)
        for turn in reversed(turns):
            if turn["role"] == "assistant":
                content = turn["content"]
                break

    if not content or len(content) < MIN_EXTRACT_CHARS:
        sys.exit(0)

    spawn_detached(
        "capture.py",
        {
            "mode": "message",
            "role": "assistant",
            "content": content,
            "session_id": session_id,
            "cwd": cwd,
        },
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        if "--worker" in sys.argv:
            worker()
        else:
            hook()
    except Exception as exc:  # noqa: BLE001
        log(f"capture fatal: {exc}")
    sys.exit(0)
