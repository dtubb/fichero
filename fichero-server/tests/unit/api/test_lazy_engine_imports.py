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
import tempfile
import textwrap
from pathlib import Path

import pytest

# src/ root — derived from this file so it can never test the stale tree the
# venv is editable-installed against.
_SRC = str(Path(__file__).resolve().parents[3] / "src")

# Heavy dependencies that must NOT be imported just to serve the app.
# Each costs seconds of import time and none is needed to bind a socket.
#
# langchain_core.messages (#3976): chat.py imported it at MODULE scope, which
# pulled ~24 langchain_core modules AND `requests` onto the boot path — the
# single biggest slice of the engine bind (import went 6.8s -> 2.1s in the venv
# when it was deferred into the chat handler). Guard the `.messages` subtree,
# NOT bare langchain_core: a deliberate #1083 warning-filter import keeps
# langchain_core._api present at startup and that is intentional and light.
#
# httpx / PIL / jinja2 / markupsafe (#3985): the next-biggest boot-path slices.
# httpx was module-top in five feature-only route/inference modules (outbound
# HTTP only runs when a request does) — it left the boot path only once ALL
# five deferred it. PIL rode in via loaders/__init__, which api.main imported
# for the kreuzberg cache-migration side effect (now a lazy PEP 562 package).
# jinja2+markupsafe came from Jinja2Templates in views.py, only needed when an
# HTML view renders. All import lazily now; guard them so they can't creep back.
HEAVY_MODULES = [
    "langgraph",
    "mcp",
    "Quartz",
    "langchain_core.messages",
    "requests",
    "httpx",
    "PIL",
    "jinja2",
    "markupsafe",
]

# Ceiling on modules imported to build the app. Measured 1799 before #3950,
# ~1200 after; 962 after #3976 dropped the langchain_core.messages/requests
# chain; 784 after #3985 dropped httpx/PIL/jinja2/markupsafe. The budget sits
# just above the current value: it fails loudly if an eager edge into the
# AI/HTTP/imaging stack is reintroduced — not to chase a number.
MODULE_BUDGET = 850


def _run(code: str) -> str:
    """Run *code* in a clean interpreter with src/ on the path.

    #4024: the subprocess gets an ISOLATED throwaway HOME (and the canonical
    test isolation env from conftest) so warm-up code that opens the app-wide
    ``~/Library/Application Support/com.fichero.fichero/app.duckdb`` can never
    read or lock the user's REAL data — which collided with the running backend.
    """
    with tempfile.TemporaryDirectory(prefix="fichero-lazy-home-") as home:
        base = Path(home) / "base"
        base.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": _SRC,
                "PATH": "/usr/bin:/bin",
                # HOME drives Path.home() → app.duckdb location; point it at the
                # throwaway dir so nothing touches real user data.
                "HOME": home,
                "FICHERO_BASE_PATH": str(base),
                "FICHERO_DISABLE_AUTH": "1",
                "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
                "FICHERO_FEATURE_TIER": "dev",
            },
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
        import fichero_server.api.main  # noqa: F401
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
        import fichero_server.api.main  # noqa: F401
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
        from fichero_server.api.main import app
        print(len(app.routes))
        """
    )
    assert int(out) > 50, "app lost its routes"


def test_workflows_tools_imports_standalone() -> None:
    """The fichero_server.db <-> api.main cycle must be gone.

    Before #3950 this raised ImportError: cannot import name 'Database' from
    partially initialized module 'fichero_server.db'. A background warm-up cannot
    import the tools package at all while that cycle exists.
    """
    out = _run(
        """
        import fichero_server.workflows.tools  # noqa: F401
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
        # Deliberately NO 'import fichero_server.api.main' first — that is the path
        # that silently produced an incomplete registry.
        from fichero_server.workflows import registry
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
        from fichero_server.workflows import registry
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

    The design (#3950): "load it once UX is up, but before clicking."
    Deferring the imports is only half the job — if nothing warms them, the
    first click on Workflows pays the whole bill with a spinner in front of it.

    Asserts the warm-up is wired into the lifespan AND that running it
    actually populates sys.modules with the heavy stack.
    """
    out = _run(
        """
        import asyncio, sys
        from fastapi import FastAPI
        from fichero_server.api.main import lifespan

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


def test_concurrent_readers_never_see_a_half_loaded_registry() -> None:
    """The warm-up thread must not let a request thread read an incomplete registry.

    The lifespan warms the tool stack on an executor thread while requests are
    already being served, so two threads reach _ensure_tools_loaded() at once.
    A bare `if _loading: return` re-entrancy guard would let the REQUEST thread
    skip the load and read the registry mid-population — 116 incomplete defs,
    silently, which is the #3950 trap resurrected as a race. The guard is keyed
    to the loading thread's ident so only that thread may re-enter; everyone
    else blocks.

    This test fails against a bare-bool guard.
    """
    out = _run(
        """
        import threading
        from fichero_server.workflows import registry

        results, barrier = [], threading.Barrier(8)

        def read():
            barrier.wait()          # maximise overlap on the load
            results.append(len(registry.list_tools()))

        threads = [threading.Thread(target=read) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        print(min(results), max(results))
        """
    )
    low, high = (int(x) for x in out.split())
    assert low == high, (
        f"concurrent readers saw DIFFERENT registry sizes ({low} vs {high}) — a "
        f"thread read the registry while it was still being populated"
    )
    assert low >= 135, f"concurrent readers saw an incomplete registry: {low} defs"


def test_langchain_core_fully_absent_after_app_import() -> None:
    """Bare ``langchain_core`` is off the bind path after #4038.

    Before #4038, api.main imported ``langchain_core._api.deprecation`` at
    module top purely to name the warning CATEGORY for a #1083 filter — that one
    import pulled ~langchain_core (importtime cumulative ~250ms) onto the bind
    path. The fix registers the filter by MESSAGE ONLY. This asserts the stronger
    post-#4038 property: NOTHING under ``langchain_core`` is present after the app
    is built, so re-adding a ``category=<langchain warning>`` import (which would
    silently drag the package back on) fails here.

    NB: HEAVY_MODULES guards ``langchain_core.messages`` for the older #3976
    regression; this guards the whole ``langchain_core`` tree for #4038.
    """
    out = _run(
        """
        import sys
        import fichero_server.api.main  # noqa: F401
        present = [m for m in sys.modules
                   if m == "langchain_core" or m.startswith("langchain_core.")]
        print("PRESENT:" + ",".join(sorted(present)) if present else "ABSENT")
        """
    )
    assert out == "ABSENT", (
        f"langchain_core is imported at engine startup ({out}). #4038 registers "
        f"the allowed_objects warning filter by message only so the package stays "
        f"off the bind path — something re-imported it for the warning category."
    )


def test_allowed_objects_warning_filter_is_registered_message_only() -> None:
    """The #1083 filter must exist AND be message-only (#4038).

    The filter has to be registered before the first workflow click (otherwise
    the ``allowed_objects`` PendingDeprecationWarning leaks to the user). But it
    must NOT be registered against a langchain warning class — naming the
    category re-imports langchain_core onto the bind path, the exact regression
    #4038 removed. A message-only ``warnings.filterwarnings`` defaults the
    category to the base ``Warning``, so we assert both: the filter is present
    with a pattern matching ``allowed_objects`` AND its category is base
    ``Warning`` (not a langchain subclass).
    """
    out = _run(
        """
        import warnings
        import fichero_server.api.main  # noqa: F401
        hits = [
            f for f in warnings.filters
            if f[1] is not None and "allowed_objects" in getattr(f[1], "pattern", "")
        ]
        if not hits:
            print("MISSING")
        else:
            action, _pat, category, *_ = hits[0]
            # module-qualname pins it to the stdlib base Warning, not a
            # langchain_core.* subclass that would have re-imported the package.
            print(f"{action}|{category.__module__}.{category.__name__}")
        """
    )
    assert out == "ignore|builtins.Warning", (
        f"allowed_objects filter is not message-only ({out}). It must be "
        f"registered with the base Warning category (message-only) so naming a "
        f"langchain warning class can't drag langchain_core onto the bind path "
        f"(#4038)."
    )


def test_mcp_modules_import_without_langchain() -> None:
    """Importing the MCP modules must not pull langchain onto the bind path.

    ``routes.mcp`` / ``routes.workflow`` import ``fichero_server.mcp.manager`` and
    ``fichero_server.workflows.tools.mcp`` at module scope, so those two modules are on
    the engine bind path. #4038 moved their ``langchain_core.tools.BaseTool`` /
    ``langchain_mcp_adapters`` imports behind ``TYPE_CHECKING`` (annotation-only)
    and into the methods that actually call them. If any of those imports creep
    back to module scope, langchain rides the bind path again — this catches it.
    """
    out = _run(
        """
        import sys
        import fichero_server.mcp.manager  # noqa: F401
        import fichero_server.workflows.tools.mcp  # noqa: F401
        leaked = [
            m for m in sys.modules
            if any(m == p or m.startswith(p + ".")
                   for p in ("langchain_core", "langchain_mcp_adapters", "langgraph"))
        ]
        print("LEAKED:" + ",".join(sorted(leaked)) if leaked else "CLEAN")
        """
    )
    assert out == "CLEAN", (
        f"importing the MCP modules pulled langchain onto the bind path ({out}). "
        f"#4038 keeps BaseTool/ClientSession/create_session/load_mcp_tools behind "
        f"TYPE_CHECKING or function-local — one crept back to module scope."
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
        broken = types.ModuleType("fichero_server.workflows.tools")
        def _boom(*a, **k):
            raise ImportError("simulated broken tool module")
        broken.__getattr__ = _boom
        import fichero_server.workflows.registry as registry
        registry._TOOLS_LOADED = False
        sys.modules["fichero_server.workflows.tools"] = None  # forces ImportError on import
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
