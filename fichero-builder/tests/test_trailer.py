"""agent-profiles.trailer.one-line: one trailer, `Written-By: <MODEL> using <HARNESS> using Fichero Builder`, on every new commit."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fichero_builder import policy_hook as ph

ROOT = Path(__file__).resolve().parents[2]
LINE = "Written-By: Claude Sonnet 5.5 using Claude Code using Fichero Builder"
CFG = ph.load(ROOT)


def _msg(*trailers: str) -> str:
    return "feat: a step\n\nBehaviour: x.y\n\n" + "\n".join(trailers) + "\n"


def test_the_one_line_is_accepted():
    assert ph.commit_msg_problems(_msg(LINE), CFG) == []
    assert ph.commit_msg_problems(_msg("Written-By: Qwen3-Coder-Next using opencode using Fichero Builder"), CFG) == []


@pytest.mark.parametrize("trailers", [
    ("Co-Authored-By: Claude <noreply@anthropic.com>",),
    ("Directed-By: the maintainer",),
    ("Written-By: sonnet",),
    (LINE, "Co-Authored-By: Claude <noreply@anthropic.com>"),
    (LINE, LINE),
    (LINE, "Written-By: Claude Opus using Claude Code using Fichero Builder"),
], ids=["co-authored-only", "directed-only", "bare-model", "plus-co-authored", "two-identical", "two-lines"])
def test_every_other_shape_is_refused_naming_the_rule(trailers):
    problems = ph.commit_msg_problems(_msg(*trailers), CFG)
    assert problems and all("Written-By" in p for p in problems)


def test_the_push_range_guard_recognises_the_line():
    spec = importlib.util.spec_from_file_location("guard", ROOT / "scripts" / "check_agent_commits_authored_as_claude.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard.AGENT_TRAILER.search(_msg(LINE))
    assert not guard.AGENT_TRAILER.search("feat: x\n\nWritten-By in prose\n")
