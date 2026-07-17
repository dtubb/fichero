"""The engine must not import the AI universe to answer /health (#3950).

WHY THESE TESTS ASSERT ON MODULES, NOT MILLISECONDS
---------------------------------------------------
Wall-clock import timings on this codebase have produced four separate
retracted claims ("77% faster", "5.16s", "89%", "14.79s -> 6.94s"). Every one
was a cold-cache baseline compared against a warm-cache candidate. A page cache
cannot be controlled for reliably from a test.

`"langgraph" not in sys.modules` cannot be confounded by a warm page cache. It
is a deterministic statement about what the engine imports. That is the whole
point of #3946 and it is the only form of assertion in this file.

Each test runs in a SUBPROCESS. sys.modules is process-global and the rest of
the suite pollutes it — an in-process assertion here would pass or fail
depending on test ordering, which is exactly the kind of confound above.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# src/ root — derived from this file so it can never test the stale tree the
# venv is editable-installed against.
_SRC = str(Path(__file__).resolve().parents[2] / "src")

# Heavy dependencies that must NOT be imported just to serve the app.
# Each costs seconds of import time and none is needed to bind a socket.
HEAVY_MODULES = ["langgraph", "mcp", "Quartz"]

# Ceiling on modules imported to build the app. Measured before this change:
# 1799. The point of the budget is to fail loudly if someone reintroduces an
# eager edge into the AI stack — not to chase a precise number, so it has
# headroom above the measured post-change value.
MODULE_BUDGET = 1300


def _run(code: str) -> str:
    """Run *code* in a clean interpreter with src/ on the path."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": _SRC, "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(f"subprocess failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result.stdout.strip()


@pytest.mark.parametrize("heavy", HEAVY_MODULES)
def test_heavy_module_absent_after_app_import(heavy: str) -> None:
    """Importing the app must not import the AI stack.

    These load in a background warm-up after the socket is bound, so the user
    is reading their library while it happens rather than staring at a
    launch screen.
    """
    out = _run(
        f"""
        import sys
        import fichero.api.main  # noqa: F401
        present = [m for m in sys.modules if m == {heavy!r} or m.startswith({heavy!r} + ".")]
        print("PRESENT" if present else "ABSENT")
        """
    )
    assert out == "ABSENT", (
        f"{heavy} is imported at engine startup. It must load lazily — the user "
        f"pays this cost before the window opens. See #3950."
    )


def test_module_count_budget_at_app_import() -> None:
    """A blunt backstop: total modules imported to build the app."""
    out = _run(
        """
        import sys
        import fichero.api.main  # noqa: F401
        print(len(sys.modules))
        """
    )
    count = int(out)
    assert count <= MODULE_BUDGET, (
        f"app import pulls {count} modules, budget is {MODULE_BUDGET}. "
        f"Something eager crept back into the import graph (#3950)."
    )


def test_fastapi_app_still_builds_without_heavy_deps() -> None:
    """Laziness is worthless if the app doesn't work. Routes must still exist."""
    out = _run(
        """
        from fichero.api.main import app
        print(len(app.routes))
        """
    )
    assert int(out) > 50, "app lost its routes"


def test_workflows_tools_imports_standalone() -> None:
    """The fichero.db <-> api.main cycle must be gone.

    Before #3950 this raised ImportError: cannot import name 'Database' from
    partially initialized module 'fichero.db'. A background warm-up cannot
    import the tools package at all while that cycle exists.
    """
    out = _run(
        """
        import fichero.workflows.tools  # noqa: F401
        print("OK")
        """
    )
    assert out == "OK"


def test_registry_is_complete_on_first_access_standalone() -> None:
    """The 116-vs-118 trap.

    registry._register_builtin_tools() installs basic defs; the @register_tool
    decorators in tools/ then OVERRIDE them with full config schemas (including
    the prompt field). Between those two points TOOL_DEFS holds incomplete
    definitions. Any reader in that window silently gets wrong data — worse
    than slow.

    Before #3950, importing registry WITHOUT importing api.main first hit the
    circular import, which _load_tool_implementations() swallowed as a DEBUG
    log — leaving the registry permanently incomplete with no error at all.
    """
    out = _run(
        """
        # Deliberately NO 'import fichero.api.main' first — that is the path
        # that silently produced an incomplete registry.
        from fichero.workflows import registry
        print(len(registry.TOOL_DEFS), len(registry.TOOLS))
        """
    )
    tool_defs, tools = (int(x) for x in out.split())
    assert tools >= 118, f"TOOLS incomplete on standalone access: {tools} (expected >= 118)"
    assert tool_defs >= 135, f"TOOL_DEFS incomplete on standalone access: {tool_defs} (expected >= 135)"


def test_registry_read_paths_trigger_tool_load() -> None:
    """Every public read path must load tools first, not just attribute access.

    list_tools() returning the 116 incomplete builtins is the failure this
    guards: a caller gets tool defs with no prompt field and no error.
    """
    out = _run(
        """
        from fichero.workflows import registry
        defs = registry.list_tools()
        transcribe = [d for d in defs if d.name == "transcribe"]
        print(len(defs), "PROMPT" if transcribe and transcribe[0].default_prompt else "NOPROMPT")
        """
    )
    count, prompt = out.split()
    assert int(count) >= 135, f"list_tools() returned {count} defs — incomplete registry"
    assert prompt == "PROMPT", (
        "list_tools() returned tool defs without their full config schema — the "
        "@register_tool decorators had not run. This is the 116-vs-118 trap."
    )


def test_warm_up_runs_after_bind_and_loads_the_stack() -> None:
    """The deferred cost must be paid in the background, not dropped.

    Daniel's design (#3950): "load it once UX is up, but before clicking."
    Deferring the imports is only half the job — if nothing warms them, the
    first click on Workflows pays the whole bill with a spinner in front of it.

    Asserts the warm-up is wired into the lifespan AND that running it
    actually populates sys.modules with the heavy stack.
    """
    out = _run(
        """
        import asyncio, sys
        from fastapi import FastAPI
        from fichero.api.main import lifespan

        async def main():
            app = FastAPI()
            async with lifespan(app):
                # Socket would be bound here. The stack must NOT be loaded yet
                # for the warm-up to be meaningful, but it runs in an executor
                # so we cannot assert absence without a race. Just drive it.
                pass
            # Lifespan exit awaits the warm-up future, so by here it has run.
            print("langgraph" in sys.modules or
                  any(m.startswith("langgraph.") for m in sys.modules))

        asyncio.run(main())
        """
    )
    assert out.strip().endswith("True"), (
        "the lifespan warm-up did not import the workflow stack — deferring the "
        "imports without warming them just moves the wait to the first click"
    )


def test_tool_load_failure_raises_loudly() -> None:
    """A broken tool import must NOT be swallowed.

    #3951: zoom and consistency_check vanished from the registry with no error.
    The old code caught ImportError and logged it at DEBUG, so an engine with a
    silently-empty tool registry looked healthy. Never again — if tools cannot
    load, say so.
    """
    out = _run(
        """
        import sys, types
        # Poison the tools package so importing it fails.
        broken = types.ModuleType("fichero.workflows.tools")
        def _boom(*a, **k):
            raise ImportError("simulated broken tool module")
        broken.__getattr__ = _boom
        import fichero.workflows.registry as registry
        registry._TOOLS_LOADED = False
        sys.modules["fichero.workflows.tools"] = None  # forces ImportError on import
        try:
            registry.list_tools()
            print("SWALLOWED")
        except ImportError:
            print("RAISED")
        """
    )
    assert out == "RAISED", (
        "a failing tool import was swallowed — that is exactly how zoom and "
        "consistency_check disappeared silently (#3951)"
    )
