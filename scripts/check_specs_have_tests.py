#!/usr/bin/env python3
"""Design specs are load-bearing: a spec can't be silently deleted or left untested.

The Testing Constitution's loop is **spec -> approve -> test -> code**, and tests cite
the spec they pin in a docstring ("spec: kg-tables", "Spec: specs/workflow-node-config.md").
But nothing ENFORCED that link: a `docs/contributor/specs/*.md` file could be deleted or
renamed and the build stayed green, even though tests still referenced it — and an
APPROVED spec could ship with no test at all. This guardrail makes the specs directory
part of the gate (run by verify_all.sh with every other check_*.py).

Two rules:

  * **No orphaned citation (hard, all specs).** Every spec id a test cites
    ("spec: <stem>" / "specs/<stem>" / "<stem>.md") must correspond to an existing spec
    file. If a spec is deleted or renamed while a test still cites it, this fails and
    names the test — so a spec the tests depend on cannot vanish silently.

  * **Approved specs must be tested (hard, Status: APPROVED only).** A spec whose header
    says `Status: APPROVED` must be cited by at least one test — an approved design that
    ships with no pinning test is exactly what the constitution forbids. DRAFT specs
    (awaiting approval, pre-build) are exempt.

Run: python scripts/check_specs_have_tests.py
"""

from __future__ import annotations

import pathlib
import re
import sys

SPECS_DIR = pathlib.Path("docs/contributor/specs")
TEST_ROOTS = [
    pathlib.Path("fichero/Tests"),
    pathlib.Path("fichero-server/tests"),
    pathlib.Path("fichero-mcp/tests"),
    pathlib.Path("fichero-cli/tests"),
]
TEST_GLOBS = ("*.swift", "*.py")

# A spec stem is lowercase words joined by hyphens (e.g. "kg-entity-inspector").
STEM = r"[a-z0-9]+(?:-[a-z0-9]+)+"
# An explicit path citation to a spec file, anywhere under a `specs/` dir
# (docs/contributor/specs OR agent-work/specs): verified at its own path.
PATH_CITATION_RE = re.compile(r"([A-Za-z0-9_./-]*specs/[A-Za-z0-9_./-]+\.md)")
# A bare "spec: <stem>" docstring citation (not a path, not "<stem>.md"): resolved
# against the canonical + legacy specs dirs by stem.
BARE_CITATION_RE = re.compile(rf"[Ss]pec:\s*({STEM})(?![/.\w])")

# Legacy spec home (older working specs); a bare citation may resolve here too.
LEGACY_SPECS_DIR = pathlib.Path("agent-work/specs")


def _spec_stems() -> set[str]:
    canonical = {p.stem for p in SPECS_DIR.glob("*.md")}
    legacy = {p.stem for p in LEGACY_SPECS_DIR.glob("*.md")} if LEGACY_SPECS_DIR.exists() else set()
    return canonical | legacy


def _approved_stems() -> set[str]:
    """APPROVED specs in the CANONICAL dir — these must be tested (Rule B)."""
    approved = set()
    for p in SPECS_DIR.glob("*.md"):
        head = p.read_text(encoding="utf-8")[:800]
        if re.search(r"Status:\s*APPROVED", head):
            approved.add(p.stem)
    return approved


def _test_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in TEST_ROOTS:
        if not root.exists():
            continue
        for glob in TEST_GLOBS:
            files.extend(root.rglob(glob))
    return files


def _citations() -> tuple[dict[str, list[pathlib.Path]], dict[str, list[pathlib.Path]]]:
    """Return (path_cites, stem_cites): explicit spec PATHS -> test files, and bare spec
    STEMS -> test files, gathered across every test file."""
    path_cites: dict[str, list[pathlib.Path]] = {}
    stem_cites: dict[str, list[pathlib.Path]] = {}
    for path in _test_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in PATH_CITATION_RE.finditer(text):
            path_cites.setdefault(m.group(1), []).append(path)
        for m in BARE_CITATION_RE.finditer(text):
            stem_cites.setdefault(m.group(1), []).append(path)
    return path_cites, stem_cites


def main() -> int:
    if not SPECS_DIR.exists():
        print(f"FAIL: specs directory missing: {SPECS_DIR}")
        return 1

    known = _spec_stems()
    approved = _approved_stems()
    path_cites, stem_cites = _citations()
    failures: list[str] = []

    # Rule A1: every explicit spec PATH a test cites must exist at that path (covers
    # both docs/contributor/specs and agent-work/specs — a deleted/renamed spec fails).
    for rel, files in sorted(path_cites.items()):
        if not pathlib.Path(rel).exists():
            where = ", ".join(str(f) for f in files[:3])
            failures.append(
                f"orphaned citation: tests reference '{rel}' but that file does not "
                f"exist (cited in: {where}). Restore the spec or fix the citation."
            )

    # Rule A2: every bare "spec: <stem>" must resolve to a real spec file.
    for stem, files in sorted(stem_cites.items()):
        if stem not in known:
            where = ", ".join(str(f) for f in files[:3])
            failures.append(
                f"orphaned citation: tests cite spec '{stem}' but no "
                f"{SPECS_DIR}/{stem}.md (or agent-work/specs/{stem}.md) exists "
                f"(cited in: {where}). Restore the spec or fix the citation."
            )

    # Rule B: an APPROVED canonical spec must be cited by >=1 test (by stem or by path).
    def _is_cited(stem: str) -> bool:
        return stem in stem_cites or any(
            rel.endswith(f"/{stem}.md") for rel in path_cites
        )

    for stem in sorted(approved):
        if not _is_cited(stem):
            failures.append(
                f"untested approved spec: {SPECS_DIR}/{stem}.md is Status: APPROVED "
                f"but no test cites it. Add a pinning test (docstring 'spec: {stem}') "
                f"or move it back to DRAFT."
            )

    if failures:
        print("Spec <-> test linkage guardrail FAILED:\n")
        for f in failures:
            print(f"  - {f}")
        print(
            f"\n{len(known)} specs known, {len(approved)} approved, "
            f"{len(path_cites)} path-citations + {len(stem_cites)} stem-citations. "
            f"Specs live in {SPECS_DIR} (git-tracked)."
        )
        return 1

    print(
        f"OK: {len(known)} specs, {len(approved)} approved and all tested; "
        f"{len(path_cites)} path + {len(stem_cites)} stem citations all resolve."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
