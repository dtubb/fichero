"""`docs/user_manual/` is written by hand and is not guarded (ruled 2026-09-27).

The distinction is who writes it, and it is the right distinction. `reference_manual` and
`contributor_manual` are AI-written about code the writer can read, and holding those to
what the code does is exactly what the docs guards are for. A user manual is a person
describing what the software is FOR, at their own pace and in their own order — and a
guard that fails on a half-written chapter is telling the author to stop writing.

It was also, by then, the ONLY remaining reason `check_docs_paths` and
`check_docs_publication` were red. So guarding it cost two real signals in order to
enforce a rule nobody wanted: every other unlinked page and every other dead path was
hidden behind it.

These tests pin both halves, because the exclusion is only correct if it is narrow. A
`user_manual` prefix match that also swallowed `contributor_manual` would turn two guards
off while reporting PASS, which is worse than the red it replaced.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load(name: str, relative: str):
    root = Path(__file__).resolve().parents[4]
    path = root / relative
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


docs_paths = _load("check_docs_paths", "scripts/check_docs_paths.py")
docs_publication = _load("check_docs_publication", "scripts/check_docs_publication.py")
ROOT = Path(__file__).resolve().parents[4]


class TestTheHandWrittenManualIsNotScanned:
    def test_docs_paths_scans_no_user_manual_page(self):
        leaked = [p for p in docs_paths.doc_files() if "user_manual" in p.parts]
        assert leaked == [], leaked

    def test_docs_publication_builds_no_user_manual_page(self):
        pages = docs_publication.built_pages((ROOT / "mkdocs.yml").read_text())
        leaked = sorted(p for p in pages if p.startswith("user_manual/"))
        assert leaked == [], leaked

    def test_a_path_naming_the_hand_written_manual_is_not_reported_absent(self):
        """A spec citing `docs/user_manual/whatever.md` is citing a chapter that may not
        be written yet, which is the author's business and not a docs defect."""
        absent = docs_paths.missing()
        leaked = sorted(p for p in absent if p.split("/")[:2] == ["docs", "user_manual"])
        assert leaked == [], leaked


class TestTheAiWrittenManualsAreStillGuarded:
    """The half that keeps the exclusion honest. If these ever read zero, the guards are
    off and saying PASS — the failure mode that is worse than being red."""

    def test_the_reference_manual_is_still_scanned(self):
        pages = [p for p in docs_paths.doc_files() if "reference_manual" in p.parts]
        assert len(pages) > 50, len(pages)

    def test_the_contributor_manual_is_still_scanned(self):
        pages = [p for p in docs_paths.doc_files() if "contributor_manual" in p.parts]
        assert len(pages) > 50, len(pages)

    def test_both_manuals_are_still_subject_to_the_nav_check(self):
        pages = docs_publication.built_pages((ROOT / "mkdocs.yml").read_text())
        assert any(p.startswith("reference_manual/") for p in pages)
        assert any(p.startswith("contributor_manual/") for p in pages)

    def test_the_exclusion_matches_a_whole_path_segment(self):
        """`user_manual` and not a prefix: a directory called `user_manual_drafts` is a
        different thing, and `contributor_manual` must never match."""
        assert docs_paths.HAND_WRITTEN_MANUAL == "user_manual"
        assert docs_publication.HAND_WRITTEN_MANUAL == "user_manual"
        docs = ROOT / "docs"
        assert docs_paths.is_hand_written(docs / "user_manual" / "a.md", docs)
        assert not docs_paths.is_hand_written(docs / "contributor_manual" / "a.md", docs)
        assert not docs_paths.is_hand_written(docs / "user_manual_drafts" / "a.md", docs)


class TestBothGuardsPassNow:
    def test_docs_paths_exits_zero(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, "scripts/check_docs_paths.py"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_docs_publication_exits_zero(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, "scripts/check_docs_publication.py"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
