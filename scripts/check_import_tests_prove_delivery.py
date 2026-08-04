#!/usr/bin/env python3
"""A drop/import test must prove something was DELIVERED, not just classified.

#4473. #3390, #702 and #570 were each closed on a real, correct commit that fixed
how a drop was *classified* — while PDF drag-drop stayed broken from other
sources. That is how #2386 survived three fixes and had to be reopened.

The mechanical shape of that failure, in a test:

    with patch("...ingest.ingest_file", return_value=doc):   # delivery removed
        r = client.post("/api/ingest/file", json={"path": ...})
    assert r.status_code == 200                              # plumbing only

The route accepted the request. Nothing was imported — it could not be, the
importer is a mock — and no assertion would notice if nothing ever were. The test
passes on a build where drag-drop delivers nothing at all.

So this check flags a test that, together:
  * exercises an ingest/import route,
  * patches out the function that performs delivery,
  * asserts a SUCCESS status, and
  * asserts nothing about what was delivered.

Any ONE piece of evidence about the outcome clears it — a document id in the
response body, a row read back from the db, page children, an audit row, an
emitted event, a task id for the async folder path. The bar is deliberately low:
this is not "test it thoroughly", it is "assert that the thing happened at all".

Error-path tests are untouched: a test asserting 400 is not claiming delivery.

Run: python scripts/check_import_tests_prove_delivery.py
"""

from __future__ import annotations

import ast
import pathlib
import sys

TESTS_ROOT = pathlib.Path("fichero-server/tests")

# A test that hits one of these is claiming something about importing.
IMPORT_ROUTES = ("/api/ingest", "/api/import")

# Patching any of these removes the delivery the test would otherwise prove.
DELIVERY_FUNCTIONS = ("ingest_file", "ingest_folder", "import_file")

# Any of these in the test body counts as evidence about the outcome.
DELIVERY_EVIDENCE = (
    "page_content",
    "children",
    "db.all",
    "db.get",
    "ActionAudit",
    "emit",
    "task_id",
    "documents",
    "document_id",
    "doc.id",
    "json()",
)

SUCCESS_CODES = {200, 201, 202, 204}

# Known debt, dated 2026-08-03 (#4473). These are NOT approved — each one is a
# success-path import test that would stay green if importing delivered nothing.
# They are listed so the rule can land as a ratchet: no NEW ones. Fixing one
# means deleting its line here, and the check then holds it fixed.
#
# Do not add to this list to make a new test pass. That inverts the rule into
# the thing it exists to catch.
KNOWN_UNPROVEN = {
    "test_api.py::test_ingest_file",
    "test_api.py::test_ingest_file_with_parameters",
    "test_api.py::test_ingest_file_different_file_types",
    "test_api.py::test_ingest_file_with_special_characters",
    "test_routes_ingest.py::test_rejects_server_paths_outside_allowed_roots_but_allows_library_file",
    "test_routes_ingest.py::test_background_ingest_uses_fresh_db_handle",
}


def _string_constants(node: ast.AST) -> list[str]:
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _int_constants(node: ast.AST) -> set[int]:
    return {
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, int)
    }


def find_unproven(root: pathlib.Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not fn.name.startswith("test_"):
                continue

            strings = _string_constants(fn)
            if not any(any(r in s for r in IMPORT_ROUTES) for s in strings):
                continue
            if not any(any(d in s for d in DELIVERY_FUNCTIONS) for s in strings):
                continue
            # Only tests claiming success are claiming delivery.
            if not (_int_constants(fn) & SUCCESS_CODES):
                continue

            dumped = ast.dump(fn)
            if any(k in dumped for k in DELIVERY_EVIDENCE):
                continue

            offenders.append(f"{path.name}::{fn.name}")
    return offenders


_BAD = '''
from unittest.mock import patch
def test_looks_fine_but_delivers_nothing(client, tmp_path):
    with patch("fichero_server.importers.ingest.ingest_file", return_value=object()):
        r = client.post("/api/ingest/file", json={"path": "/x.pdf"})
    assert r.status_code == 200
'''

_GOOD = '''
def test_delivers(client, db, tmp_path):
    r = client.post("/api/ingest/file", json={"path": "/x.pdf"})
    assert r.status_code == 200
    stored = db.get(Document, r.json()["id"])
    assert stored is not None
'''

_ERROR_PATH = '''
from unittest.mock import patch
def test_missing_file_is_rejected(client, tmp_path):
    with patch("fichero_server.importers.ingest.ingest_file"):
        r = client.post("/api/ingest/file", json={"path": "/gone.pdf"})
    assert r.status_code == 400
'''


def _self_test() -> int:
    """Prove the rule fires, and fires only on the shape it names.

    A rule nobody has watched catch the bad case is a rule that passes because
    nothing looks like the pattern it scans for. This is the difference between
    "no violations" and "no detection" — and tonight that distinction cost four
    separate false greens across the codebase and its tooling.
    """
    import tempfile

    cases = [(_BAD, True), (_GOOD, False), (_ERROR_PATH, False)]
    failures = []
    for source, should_flag in cases:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "test_case.py"
            path.write_text(source, encoding="utf-8")
            flagged = bool(find_unproven(pathlib.Path(tmp)))
        if flagged != should_flag:
            failures.append(
                f"expected {'a flag' if should_flag else 'no flag'}, got "
                f"{'a flag' if flagged else 'no flag'} for:\n{source}"
            )

    if failures:
        print("✗ The rule does not behave as documented:\n")
        for failure in failures:
            print(f"    {failure}")
        return 1

    print("✓ Self-test: flags the mocked-delivery success test, and only that.")
    print("  (Clean delivery assertions and error-path tests are left alone.)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()

    if not TESTS_ROOT.is_dir():
        print(f"✗ {TESTS_ROOT} not found — run from the repository root.")
        return 2

    offenders = find_unproven(TESTS_ROOT)
    new = [o for o in offenders if o not in KNOWN_UNPROVEN]
    fixed = [k for k in sorted(KNOWN_UNPROVEN) if k not in offenders]

    if new:
        print("✗ Import tests that assert success but prove no delivery:\n")
        for offender in new:
            print(f"    {offender}")
        print(
            "\n  Each hits an import route with the importer patched out and "
            "asserts only a status code.\n"
            "  It would pass on a build where importing delivers nothing — the "
            "defect behind #2386.\n"
            "  Assert something about the outcome: a document id in the "
            "response, a row read back,\n"
            "  page children, an audit row, an emitted event, or a task id."
        )
        return 1

    if fixed:
        print("✓ These no longer need the exemption — delete them from KNOWN_UNPROVEN:\n")
        for entry in fixed:
            print(f"    {entry}")
        print("\n  (Stale entries mean the list is drifting out of date.)")
        return 1

    print(
        f"✓ No new import tests assert success without proving delivery "
        f"({len(KNOWN_UNPROVEN)} known, unfixed)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
