#!/usr/bin/env python3
"""SessionEnd hook: distil the session into durable memory.

Raw message history is a poor long-term store -- it is long, repetitive, and
mostly scaffolding. This hook asks Claude to compress the session into the
handful of things actually worth remembering (decisions, constraints, gotchas,
stated preferences) and writes those as first-class graph objects.

This is the difference between a transcript archive and a memory.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from memory_lib import (  # noqa: E402
    WRITE_BUDGET,
    log,
    project_key,
    read_hook_input,
    run_memory,
    session_id_for,
    spawn_detached,
    transcript_tail,
)

SUMMARY_PROMPT = """\
You are distilling a software engineering session into long-term memory.

Return ONLY valid JSON matching this shape:

{
  "worth_keeping": true,
  "summary": "2-3 sentences on what was actually accomplished",
  "facts": [
    {"subject": "...", "predicate": "...", "object": "...", "confidence": 0.9}
  ],
  "preferences": [
    {"category": "...", "preference": "...", "confidence": 0.8}
  ],
  "entities": [
    {"name": "...", "type": "PERSON|OBJECT|LOCATION|EVENT|ORGANIZATION",
     "subtype": "...", "description": "..."}
  ]
}

Rules:
- Set "worth_keeping": false if the session was trivial (a quick lookup, a
  one-line fix, an aborted attempt). Most sessions are not worth keeping.
- Record DURABLE things: architectural decisions, constraints discovered,
  conventions agreed, systems and their relationships, stated preferences.
- Do NOT record transient state: file contents, specific line numbers, what
  was typed, or anything true only during this session.
- A preference must be something the user expressed about how they want to
  work, not something you inferred from one instance.
- Empty arrays are correct and expected. Do not invent entries to fill them.

Session transcript follows.
"""


def summarise(turns: list[dict[str, str]]) -> dict | None:
    """Ask Claude what was worth remembering. Returns None on any failure."""
    try:
        import anthropic
    except ImportError:
        log("anthropic sdk not installed; skipping consolidation")
        return None

    api_key = os.environ.get("NAM_LLM_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    if not api_key:
        log("no anthropic api key; skipping consolidation")
        return None

    model = os.environ.get("NEO4J_MEMORY_SUMMARY_MODEL", "claude-sonnet-4-5")
    transcript = "\n\n".join(
        f"[{t['role']}] {t['content']}" for t in turns
    )[:60000]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SUMMARY_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        # Models sometimes wrap JSON in a fence despite instructions.
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.startswith("json") else text

        return json.loads(text.strip())
    except Exception as exc:  # noqa: BLE001
        log(f"consolidation failed: {exc}")
        return None


def worker() -> None:
    payload = read_hook_input()
    turns = payload.get("turns") or []
    session_id = payload.get("session_id")
    key = payload.get("project_key") or "unknown"

    if not turns or not session_id:
        return

    distilled = summarise(turns)
    if not distilled or not distilled.get("worth_keeping"):
        log(f"session_end: nothing worth keeping for {session_id}")
        return

    async def write(client):
        written = 0

        summary = distilled.get("summary")
        if summary:
            await client.short_term.add_message(
                session_id=session_id,
                role="system",
                content=f"[session summary] {summary}",
                extract_entities=False,
            )
            written += 1

        for ent in distilled.get("entities") or []:
            name = ent.get("name")
            etype = ent.get("type")
            if not name or not etype:
                continue
            await client.long_term.add_entity(
                name=name,
                entity_type=etype,
                subtype=ent.get("subtype"),
                description=ent.get("description"),
            )
            written += 1

        for fact in distilled.get("facts") or []:
            if not all(fact.get(k) for k in ("subject", "predicate", "object")):
                continue
            await client.long_term.add_fact(
                subject=fact["subject"],
                predicate=fact["predicate"],
                object_value=fact["object"],
                confidence=float(fact.get("confidence", 0.8)),
            )
            written += 1

        for pref in distilled.get("preferences") or []:
            if not pref.get("preference"):
                continue
            await client.long_term.add_preference(
                category=pref.get("category") or "general",
                preference=pref["preference"],
                confidence=float(pref.get("confidence", 0.7)),
                context=f"project:{key}",
            )
            written += 1

        return written

    count = run_memory(write, budget=WRITE_BUDGET * 2, default=0)
    log(f"session_end: wrote {count} objects for {session_id}")


def hook() -> None:
    data = read_hook_input()
    cwd = data.get("cwd") or "."

    # "clear" and "logout" are not real endings -- do not spend a summary call.
    if data.get("reason") in ("clear", "logout"):
        sys.exit(0)

    turns = transcript_tail(data.get("transcript_path"), max_chars=60000)
    if len(turns) < 4:
        sys.exit(0)

    spawn_detached(
        "session_end.py",
        {
            "turns": turns,
            "session_id": session_id_for(cwd),
            "project_key": project_key(cwd),
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
        log(f"session_end fatal: {exc}")
    sys.exit(0)
