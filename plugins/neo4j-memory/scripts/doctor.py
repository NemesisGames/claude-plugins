#!/usr/bin/env python3
"""Verify the neo4j-memory plugin can actually work.

Run this before trusting the plugin, and whenever recall goes quiet.
Checks each link in the chain and reports the first one that is broken.
"""

from __future__ import annotations

import asyncio
import os
import sys

OK = "[ ok ]"
BAD = "[fail]"
WARN = "[warn]"

failures = 0


def check(label: str, passed: bool, detail: str = "", fatal: bool = True) -> bool:
    global failures
    mark = OK if passed else (BAD if fatal else WARN)
    print(f"{mark} {label}" + (f" - {detail}" if detail else ""))
    if not passed and fatal:
        failures += 1
    return passed


def main() -> int:
    print("neo4j-memory doctor\n" + "=" * 40)

    # 1. Package
    try:
        import neo4j_agent_memory  # noqa: F401

        version = getattr(neo4j_agent_memory, "__version__", "unknown")
        check("neo4j-agent-memory installed", True, f"version {version}")
    except ImportError:
        check(
            "neo4j-agent-memory installed",
            False,
            'pip install "neo4j-agent-memory[mcp,anthropic,'
            'sentence-transformers,spacy,gliner]"',
        )
        return 1

    # 1b. Launch preflight.
    #
    # The library being importable is not the same as the plugin being able to
    # START it. The MCP server runs a console script, and the hooks run a
    # Python interpreter -- both resolved through PATH by a process spawn, not
    # by your shell. A user-site pip install puts the console script in a
    # directory Windows does not add to PATH, which presents as an opaque
    # "Connection closed" with no other clue. Check both launchers explicitly.
    import shutil

    mcp_cmd = os.environ.get("NEO4J_MEMORY_CMD", "neo4j-agent-memory")
    resolved = shutil.which(mcp_cmd)
    if resolved:
        check("MCP launcher on PATH", True, resolved)
    else:
        import sysconfig

        guesses = []
        for scheme in ("nt_user", "posix_user", "nt", "posix_prefix"):
            try:
                d = sysconfig.get_path("scripts", scheme)
            except Exception:
                continue
            if d and os.path.isdir(d):
                for ext in (".exe", ""):
                    p = os.path.join(d, "neo4j-agent-memory" + ext)
                    if os.path.isfile(p):
                        guesses.append(p)
        detail = f"'{mcp_cmd}' not found on PATH"
        if guesses:
            detail += (
                f" -- but it exists at {guesses[0]}. Either add that folder to"
                f" PATH, or set NEO4J_MEMORY_CMD to the full path"
            )
        else:
            detail += " -- reinstall with the [mcp] extra, or set NEO4J_MEMORY_CMD"
        check("MCP launcher on PATH", False, detail)

    # Resolve the interpreter exactly the way hooks.json does:
    # ${NEO4J_MEMORY_PYTHON:-python}. Checking anything else here would let the
    # doctor pass while the hooks silently fail.
    hook_name = os.environ.get("NEO4J_MEMORY_PYTHON", "python")
    hook_py = shutil.which(hook_name)
    if not hook_py:
        alt = shutil.which("python3")
        if alt:
            check(
                "hook interpreter",
                False,
                f"hooks will run '{hook_name}', which is not on PATH -- but"
                f" python3 is, at {alt}. Set NEO4J_MEMORY_PYTHON=python3",
            )
        else:
            check(
                "hook interpreter",
                False,
                f"'{hook_name}' not on PATH and no python3 either. The hooks"
                " cannot run, and they fail silently by design, so memory"
                " would simply never happen",
            )
        hook_py = None

    if hook_py:
        import subprocess

        try:
            out = subprocess.run(
                [hook_py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                capture_output=True, text=True, timeout=15,
            ).stdout.strip()
            major, minor = (int(x) for x in out.split("."))
            check(
                "hook interpreter",
                (major, minor) >= (3, 10),
                f"{hook_py} (Python {out})"
                + ("" if (major, minor) >= (3, 10) else " -- needs 3.10+"),
            )
        except Exception as exc:  # noqa: BLE001
            check("hook interpreter", False, f"{hook_py} unusable: {exc}", fatal=False)

    # 1c. Actually start the MCP server.
    #
    # Everything else here tests the library. The MCP server is a separate
    # process launched through the CLI, and the CLI reads a DIFFERENT set of
    # environment variables than the library does (NEO4J_PASSWORD, not
    # NAM_NEO4J__PASSWORD). A config that satisfies the hooks can still leave
    # the server exiting instantly, and Claude Code reports only
    # "CONNECTION_CLOSED" with none of the detail. So launch it and read stderr.
    if resolved:
        import subprocess

        bridged = dict(os.environ)
        for cli_name, lib_name, fallback in (
            ("NEO4J_URI", "NAM_NEO4J__URI", "bolt://localhost:7687"),
            ("NEO4J_USER", "NAM_NEO4J__USERNAME", "neo4j"),
            ("NEO4J_PASSWORD", "NAM_NEO4J__PASSWORD", None),
            ("NEO4J_DATABASE", "NAM_NEO4J__DATABASE", "neo4j"),
        ):
            value = os.environ.get(cli_name) or os.environ.get(lib_name) or fallback
            if value:
                bridged[cli_name] = value

        proc = None
        try:
            proc = subprocess.Popen(
                [resolved, "mcp", "serve", "--profile", "extended",
                 "--session-strategy", "persistent"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=bridged, text=True,
            )
            # A healthy stdio server stays up waiting for JSON-RPC. A broken one
            # exits within a second or two.
            try:
                _, err = proc.communicate(timeout=25)
                first = next(
                    (ln for ln in (err or "").splitlines()
                     if ln.strip() and "Warning" not in ln
                     and "warn" not in ln.lower()),
                    "exited with no message",
                )
                check("MCP server starts", False, f"exited immediately: {first}")
            except subprocess.TimeoutExpired:
                check("MCP server starts", True, "stayed up (healthy)")
        except Exception as exc:  # noqa: BLE001
            check("MCP server starts", False, f"could not launch: {exc}", fatal=False)
        finally:
            if proc and proc.poll() is None:
                proc.kill()

    # 2. Environment
    uri = os.environ.get("NAM_NEO4J__URI") or os.environ.get("NEO4J_URI")
    password = os.environ.get("NAM_NEO4J__PASSWORD") or os.environ.get(
        "NEO4J_PASSWORD"
    )
    anthropic_key = os.environ.get("NAM_LLM_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )

    check("NAM_NEO4J__URI set", bool(uri), uri or "missing")
    check("NAM_NEO4J__PASSWORD set", bool(password), "hidden" if password else "missing")
    check(
        "Anthropic key set",
        bool(anthropic_key),
        "found" if anthropic_key else "entity extraction will be disabled",
        fatal=False,
    )

    embedding = os.environ.get("NAM_EMBEDDING", "BAAI/bge-base-en-v1.5")
    llm = os.environ.get("NAM_LLM", "anthropic/claude-sonnet-4-5")
    print(f"       embedding: {embedding}")
    print(f"       llm:       {llm}")

    if failures:
        return 1

    # 3. Embedding backend
    if embedding.startswith(("BAAI/", "sentence-transformers/", "Xenova/")):
        try:
            import sentence_transformers  # noqa: F401

            check("sentence-transformers installed", True)
        except ImportError:
            check(
                "sentence-transformers installed",
                False,
                'pip install "neo4j-agent-memory[sentence-transformers]"',
            )
            return 1

    if llm.startswith("anthropic/"):
        try:
            import anthropic  # noqa: F401

            check("anthropic sdk installed", True)
        except ImportError:
            check(
                "anthropic sdk installed",
                False,
                'pip install "neo4j-agent-memory[anthropic]"',
                fatal=False,
            )

    # 3b. Local extractors. Missing these is not fatal, but it silently routes
    # every message to the paid LLM extractor -- worth shouting about.
    def enabled(var: str, default: str = "true") -> bool:
        return os.environ.get(var, default).lower() in ("1", "true", "yes")

    if enabled("NAM_EXTRACTION__ENABLE_SPACY"):
        try:
            import spacy

            model = os.environ.get(
                "NAM_EXTRACTION__SPACY_MODEL", "en_core_web_sm"
            )
            try:
                spacy.load(model)
                check(f"spacy + {model}", True)
            except OSError:
                check(
                    f"spacy model {model}",
                    False,
                    f"python -m spacy download {model}",
                    fatal=False,
                )
        except ImportError:
            check(
                "spacy installed",
                False,
                'enabled in env but missing: pip install "neo4j-agent-memory[spacy]"'
                " (every message will hit the paid LLM extractor)",
                fatal=False,
            )

    if enabled("NAM_EXTRACTION__ENABLE_GLINER"):
        try:
            import gliner  # noqa: F401

            check("gliner installed", True)
        except ImportError:
            check(
                "gliner installed",
                False,
                'enabled in env but missing: pip install "neo4j-agent-memory[gliner]"',
                fatal=False,
            )

    # 4. Live connection + round trip
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
    from memory_lib import _settings  # noqa: E402

    from neo4j_agent_memory import MemoryClient  # noqa: E402

    async def probe():
        async with MemoryClient(_settings()) as client:
            entities = await client.long_term.search_entities(
                query="connectivity probe", limit=1
            )
            return entities

    try:
        result = asyncio.run(asyncio.wait_for(probe(), timeout=90))
        check("Neo4j connect + vector search", True, f"{len(result)} result(s)")
    except asyncio.TimeoutError:
        check(
            "Neo4j connect + vector search",
            False,
            "timed out (first run downloads the ~440MB embedding model; retry)",
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        check("Neo4j connect + vector search", False, f"{type(exc).__name__}: {exc}")
        return 1

    # 5. Index dimensions -- the classic silent failure
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.environ.get("NAM_NEO4J__URI", "bolt://localhost:7687"),
            auth=(
                os.environ.get("NAM_NEO4J__USERNAME", "neo4j"),
                password,
            ),
        )
        with driver.session(
            database=os.environ.get("NAM_NEO4J__DATABASE", "neo4j")
        ) as session:
            rows = session.run(
                "SHOW VECTOR INDEXES YIELD name, options "
                "RETURN name, options.indexConfig.`vector.dimensions` AS dim"
            ).data()
        driver.close()

        if rows:
            dims = {r["dim"] for r in rows if r.get("dim")}
            check(
                "vector index dimensions consistent",
                len(dims) <= 1,
                f"{dims}" if dims else "none reported",
            )
        else:
            check(
                "vector indexes exist",
                False,
                "none found - they are created on first write",
                fatal=False,
            )
    except Exception as exc:  # noqa: BLE001
        check("vector index check", False, str(exc), fatal=False)

    print("=" * 40)
    if failures:
        print(f"{failures} problem(s) found.")
        return 1
    print("Memory is healthy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
