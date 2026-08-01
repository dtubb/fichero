"""Seam category 7 — swallowed exceptions (#4420).

The archetype is #4395: ``db.embed`` caught every exception, logged, and
returned the same falsy value for "nothing to embed" and "the model failed to
load" — 656 documents silently unembedded. The general rule #4420 states:
**a legitimate skip must be distinguishable in the return value from a
failure.** A broad handler whose body ONLY logs (or passes) makes the
exception influence nothing downstream — the caller cannot tell disaster
from routine.

WHAT IS SWEPT: every ``except``/``except Exception``/``except BaseException``
handler in ``fichero-server/src`` whose body consists solely of logging
calls, ``pass`` and/or ``continue``. Handlers that re-raise, return an error
marker, set state, or fall back to an alternative are NOT flagged — those at
least route the failure somewhere a caller or test can see.

WHY A BASELINE AND NOT A PER-ENTRY ALLOWLIST: the first measurement found
**242** such handlers. Writing 242 individually-reasoned entries would be an
estimate dressed as diligence; pretending 242 defects should fail the suite
today would get the sweep deleted. So this is a RATCHET over an enumerated
debt file, the same shape as ``check_environment_forwarding``'s baseline:

* a NEW only-log handler (new function, or a higher count in a known
  function) fails the sweep — the debt may not grow;
* a REMOVED one fails the sweep as a stale baseline entry — shrink the file
  with the fix, so the ledger always states the true debt (bidirectional
  hygiene, #4382);
* entries are keyed ``relative/path.py::qualified.function`` with a count —
  function-scoped rather than line-scoped, so ordinary edits above a handler
  do not churn the ledger.

Regenerate after fixing sites:

    python -m pytest tests/unit/seams/test_swallowed_exception_seam.py \
        --regen-swallowed-baseline

(the flag is wired via conftest-free argv sniffing below to keep this file
self-contained).

Scope, stated honestly: Swift ``try?`` is the same category and is NOT swept
here — a first count found it needs its own calibration pass (many
``try?`` sites feed optionals that ARE checked). Recorded on #4420 rather
than half-built.

Findings are reported, not fixed (#4420).
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
BASELINE = Path(__file__).with_name("known_swallowed_exceptions.txt")

_LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}


def _only_logs(body: list[ast.stmt]) -> bool:
    """True when the handler body is nothing but logging / pass / continue."""
    for node in body:
        if isinstance(node, (ast.Pass, ast.Continue)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr in _LOG_METHODS
        ):
            continue
        return False
    return True


class _FunctionStack(ast.NodeVisitor):
    """Collect only-log broad handlers keyed by their enclosing function."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.found: Counter[str] = Counter()

    def _visit_scope(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scope(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scope(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, node.name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        t = node.type
        broad = t is None or (
            isinstance(t, ast.Name) and t.id in ("Exception", "BaseException")
        )
        if broad and _only_logs(node.body):
            self.found[".".join(self.stack) or "<module>"] += 1
        self.generic_visit(node)


def _scan(root: Path) -> tuple[Counter, int]:
    """Counter of 'relpath::qualname' -> count, plus files walked."""
    found: Counter[str] = Counter()
    files = 0
    for path in sorted(root.rglob("*.py")):
        files += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        visitor = _FunctionStack()
        visitor.visit(tree)
        rel = path.relative_to(root).as_posix()
        for qual, count in visitor.found.items():
            found[f"{rel}::{qual}"] += count
    return found, files


def _read_baseline() -> Counter:
    baseline: Counter[str] = Counter()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, count = line.rpartition(" ")
        baseline[key] = int(count)
    return baseline


def _write_baseline(found: Counter) -> None:
    lines = [
        "# Only-log broad exception handlers in fichero-server/src (#4420 cat 7).",
        "# ENUMERATED DEBT, not an endorsement: each is a place where an",
        "# exception influences nothing downstream. The sweep fails when this",
        "# list grows OR when it is stale — fix a site, delete its line.",
        "# Format: <relpath>::<qualified.function> <count>",
        "",
    ]
    lines += [f"{key} {count}" for key, count in sorted(found.items())]
    BASELINE.write_text("\n".join(lines) + "\n", encoding="utf-8")


if "--regen-swallowed-baseline" in sys.argv:  # pragma: no cover - maintenance path
    _write_baseline(_scan(SRC)[0])


def _real_tree() -> Counter:
    found, files = _scan(SRC)
    # Guard the guard (#4382): walking nothing must fail, not pass.
    assert files >= 100, f"only {files} Python files walked under {SRC}"
    return found

def test_no_new_swallowed_exception():
    """The debt may not grow: a new only-log broad handler fails here."""
    found = _real_tree()
    baseline = _read_baseline()
    grown = {
        key: (baseline.get(key, 0), count)
        for key, count in found.items()
        if count > baseline.get(key, 0)
    }
    assert grown == {}, (
        "NEW only-log broad exception handlers (an exception that influences "
        "nothing downstream — the #4395 shape). Route the failure somewhere a "
        "caller can see, or add the site to known_swallowed_exceptions.txt "
        "with the debt acknowledged:\n  "
        + "\n  ".join(
            f"{k}: baseline {b} -> now {n}" for k, (b, n) in sorted(grown.items())
        )
    )


def test_the_baseline_is_not_stale():
    """Bidirectional hygiene: a fixed site must leave the ledger."""
    found = _real_tree()
    baseline = _read_baseline()
    stale = {
        key: (count, found.get(key, 0))
        for key, count in baseline.items()
        if found.get(key, 0) < count
    }
    assert stale == {}, (
        "baseline entries whose handlers were fixed or moved — delete/adjust "
        "these lines so the ledger states the true debt:\n  "
        + "\n  ".join(
            f"{k}: baseline {b}, now {n}" for k, (b, n) in sorted(stale.items())
        )
    )


def test_the_baseline_matches_reality_exactly():
    """The two directions above, stated once as the invariant."""
    assert _real_tree() == _read_baseline()


class TestTheSweepItselfFires:
    """Drive the check: prove the detector trips on a seeded swallow and
    stays quiet on handlers that route the failure somewhere."""

    def test_detects_an_only_log_handler(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "import logging\nlog = logging.getLogger(__name__)\n"
            "def risky():\n"
            "    try:\n"
            "        return 1\n"
            "    except Exception as exc:\n"
            "        log.warning('boom %s', exc)\n"
        )
        found, files = _scan(tmp_path)
        assert files == 1
        assert found == {"mod.py::risky": 1}

    def test_detects_a_bare_except_pass(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "def quiet():\n    try:\n        return 1\n    except:\n        pass\n"
        )
        found, _ = _scan(tmp_path)
        assert found == {"mod.py::quiet": 1}

    def test_a_reraising_handler_is_not_flagged(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "def loud():\n"
            "    try:\n"
            "        return 1\n"
            "    except Exception as exc:\n"
            "        raise RuntimeError('typed') from exc\n"
        )
        found, _ = _scan(tmp_path)
        assert found == {}

    def test_a_handler_returning_a_marker_is_not_flagged(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "def marked():\n"
            "    try:\n"
            "        return 1\n"
            "    except Exception:\n"
            "        return None\n"
        )
        found, _ = _scan(tmp_path)
        assert found == {}

    def test_a_narrow_handler_is_not_flagged(self, tmp_path):
        (tmp_path / "mod.py").write_text(
            "import logging\nlog = logging.getLogger(__name__)\n"
            "def narrow():\n"
            "    try:\n"
            "        return 1\n"
            "    except FileNotFoundError as exc:\n"
            "        log.info('expected %s', exc)\n"
        )
        found, _ = _scan(tmp_path)
        assert found == {}
