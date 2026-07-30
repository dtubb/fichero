"""Seam category 6 — discarded success/failure results (#4420).

The archetype is #4395. ``db.embed(doc)`` returns ``bool`` and is called as a
bare expression statement at ``importers/ingest.py:392``. Nothing read the
result, so an import that embedded nothing reported complete success. Measured
consequence: 668 documents with text and 12 vectors in Daniel's Local library,
invisible until someone read the vector store by hand.

The rule: **if a function's contract is to report success or failure, someone
must read the report.** A returned status nobody reads is the same as no
status at all — and it is worse than none, because reviewers see a status
being returned and assume it is handled.

METHOD. Two AST passes over ``src/fichero_server``, no text matching:

1. collect every function/method whose signature is annotated ``-> bool``;
2. flag every call to one of those names used as a bare ``ast.Expr``
   statement (including ``await``-ed ones), where the value is discarded.

Annotation-driven rather than name-driven, so nothing depends on a naming
convention and a newly added ``-> bool`` API inherits the check.

FALSE POSITIVES ARE REAL, AND THAT IS WHY THE ALLOWLIST IS SITE-SCOPED.
Discarding a boolean is sometimes exactly right, and the two most alarming
hits in this codebase turned out to be correct code:

* ``accounts.verify_password(body.password, _dummy_password_hash())`` on the
  unknown-user branch of login — a deliberate timing-attack mitigation. It
  hashes a dummy so an unknown username costs the same as a wrong password
  and response time cannot be used to enumerate accounts. Discarding the
  result IS the point. The *other* call in that module is properly checked.
* ``grant_access(...)`` — failure is signalled by raising
  ``BookmarkGrantError``, not by the return value, so the bool carries no
  information the caller needs.

Both were read before being excused; neither is allowlisted by name alone,
because the same function is used correctly elsewhere. Keys are
``"name@module.py"`` so an exception cannot silently spread to another file.

Everything else is reported for triage, not fixed (#4420). Each remaining
name needs the same question asked of it that these two answered.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"

# Site-scoped exceptions: "function_name@relative/module.py" -> reason.
# Each was read and understood before being added.
JUSTIFIED_DISCARDS: dict[str, str] = {
    "verify_password@api/routes/auth/accounts.py": (
        "timing-attack mitigation: the unknown-user branch deliberately hashes "
        "a dummy password so an unknown username costs the same as a wrong one "
        "and response time cannot enumerate accounts; discarding the result is "
        "the purpose. The real check in the same module IS tested."
    ),
    "grant_access@api/routes/auth/sandbox_access.py": (
        "failure is raised as BookmarkGrantError and handled; the bool carries "
        "no information the caller needs"
    ),
}


def _python_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _bool_returning_names() -> set[str]:
    names: set[str] = set()
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is not None and ast.unparse(node.returns).strip() == "bool":
                    names.add(node.name)
    return names


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _discarded_sites() -> dict[str, list[str]]:
    """function name -> ['relative/module.py:line', …] where status is dropped."""
    status_names = _bool_returning_names()
    found: dict[str, list[str]] = defaultdict(list)

    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        rel = str(path.relative_to(SRC))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr):
                continue
            value = node.value
            if isinstance(value, ast.Await):
                value = value.value
            if not isinstance(value, ast.Call):
                continue
            name = _called_name(value)
            if name is None or name not in status_names:
                continue
            if f"{name}@{rel}" in JUSTIFIED_DISCARDS:
                continue
            found[name].append(f"{rel}:{node.lineno}")

    return dict(found)


def test_the_sweep_has_something_to_scan():
    """Guard the guard (#4382)."""
    files = _python_files()
    assert len(files) >= 200, (
        f"only {len(files)} python modules found under {SRC} — nothing is "
        "being scanned"
    )
    status_names = _bool_returning_names()
    assert len(status_names) >= 100, (
        f"only {len(status_names)} functions annotated '-> bool' were parsed — "
        "the annotation matcher has stopped working and this sweep would pass "
        "vacuously"
    )


def test_no_success_status_is_discarded_at_its_call_site():
    """A returned status nobody reads is the same as no status."""
    discarded = _discarded_sites()
    total = sum(len(sites) for sites in discarded.values())
    rendered = "\n  ".join(
        f"{name}() — {len(sites)} site(s): {', '.join(sites[:3])}"
        + (f" (+{len(sites) - 3} more)" if len(sites) > 3 else "")
        for name, sites in sorted(discarded.items(), key=lambda kv: -len(kv[1]))
    )
    assert discarded == {}, (
        f"{total} call site(s) across {len(discarded)} function(s) discard a "
        "declared '-> bool' success/failure result. Each needs the same "
        "question answered that verify_password and grant_access answered: is "
        "the status genuinely uninteresting here, or is a failure being "
        "silently dropped? db.embed is the known-costly one — #4395, 656 "
        "documents:\n  " + rendered
    )


def test_embed_result_is_never_discarded():
    """#4395 specifically, addressable on its own.

    Split out of the broad sweep so a fix for the embeddings outage shows up
    as this test going green, independently of the triage state of the other
    names.
    """
    discarded = _discarded_sites()
    embed_sites = discarded.get("embed", [])
    assert embed_sites == [], (
        "db.embed()'s success flag is thrown away at these sites, so an import "
        "that embedded nothing still reports success — the defect that left "
        f"656 documents unsearchable (#4395): {embed_sites}"
    )


def test_justified_discards_are_still_real_and_reasoned():
    """Bidirectional hygiene: a stale exception must fail, not linger."""
    status_names = _bool_returning_names()
    stale: list[str] = []

    for key in JUSTIFIED_DISCARDS:
        name, _, rel = key.partition("@")
        path = SRC / rel
        if not path.is_file():
            stale.append(f"{key}: module no longer exists")
            continue
        if name not in status_names:
            stale.append(f"{key}: {name}() is no longer declared '-> bool'")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        still_discarded = any(
            isinstance(node, ast.Expr)
            and isinstance(node.value, (ast.Call, ast.Await))
            and _called_name(
                node.value if isinstance(node.value, ast.Call) else node.value.value
            )
            == name
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr)
            and isinstance(
                node.value.value if isinstance(node.value, ast.Await) else node.value,
                ast.Call,
            )
        )
        if not still_discarded:
            stale.append(f"{key}: no discarded call remains — drop the exception")

    assert stale == [], (
        "these justified-discard entries no longer describe the code:\n  "
        + "\n  ".join(stale)
    )

    missing_reason = sorted(
        key for key, reason in JUSTIFIED_DISCARDS.items() if not str(reason).strip()
    )
    assert missing_reason == [], f"entries without a reason: {missing_reason}"
