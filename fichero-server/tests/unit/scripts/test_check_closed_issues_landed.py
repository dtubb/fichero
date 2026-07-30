"""Prove `check_closed_issues_landed` can FAIL — a guardrail with no such proof
is decoration (#4425).

The check exists to catch an issue closed against a commit that is real in the
lane's local tree but has never been pushed. Its two halves are deliberately
asymmetric — corpus is `git log --all`, test is against the remote — and the
easy way to break it is to "optimise" the corpus onto the remote, which makes
every commit reachable by construction and the check silently unfailable.

These tests pin the decision itself, so that regression fails here rather than
being discovered by another lost fix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_closed_issues_landed.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("cci_landed", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    assert _SCRIPT.exists(), f"{_SCRIPT} is missing — the check was deleted, not moved"
    return _load()


def test_the_guardrail_fires_on_an_unpushed_commit(mod):
    """THE test that matters: every citing commit local-only => flagged.

    This is the real 2026-07-30 case — #4392/#4404/#4423 closed minutes after a
    local merge, before the push.
    """
    assert mod.classify(["deadbeef1"], reachable=set()) == "unlanded"


def test_one_reachable_commit_is_enough(mod):
    """#2508's shape: some citing commits unreachable, others pushed.

    The phased work landed; only a later completion did not. This check must
    NOT flag that — it is a different defect, findable only from the branch
    side, and flagging it here would produce noise that gets the check turned
    off.
    """
    assert mod.classify(["local1", "pushed1"], reachable={"pushed1"}) == "ok"


def test_no_citing_commit_is_skipped_not_failed(mod):
    """Duplicates, audits, already-implemented triage closures, and work that
    lands as data (e.g. a default_workflows/*.json preset, #3904) legitimately
    cite no commit. Failing those is noise, and a noisy check gets disabled.
    """
    assert mod.classify([], reachable=set()) == "skip"


def test_all_commits_reachable_passes(mod):
    assert mod.classify(["a", "b"], reachable={"a", "b"}) == "ok"


def test_docstring_keeps_the_corpus_warning(mod):
    """The corpus/test asymmetry is load-bearing and easy to 'optimise' away.

    If someone narrows the corpus to the remote, `is_ancestor` is always true,
    nothing is ever flagged, and this becomes a guardrail that cannot fail —
    the #4382 mode, inside the tool built to prevent it. Keep the warning where
    an editor cannot miss it.
    """
    doc = mod.__doc__ or ""
    assert "git log --all" in doc
    assert "cannot fail" in doc.lower() or "CANNOT FAIL" in doc
