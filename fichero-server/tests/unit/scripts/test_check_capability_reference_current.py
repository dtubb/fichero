"""The generated user-manual reference, and the guardrail that keeps it honest.

The manual's workflow/tool reference is generated from the engine registry and
the shipped presets, so the pages can state the real prompts. That only holds
if regeneration is enforced, and an enforcement check nobody has watched fail
is a guess. These exercise the comparison that decides drift, the run-order
sort that decides what a workflow page says, and both scripts' `--self-test`.

The heavy end-to-end pass — regenerate the whole tree and diff it against what
is committed — is the gate itself:
``scripts/check_capability_reference_current.py``. It imports the engine, so it
belongs in the guardrail sweep rather than in a unit test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"
GENERATOR = SCRIPTS_DIR / "generate_capability_reference.py"
CHECK = SCRIPTS_DIR / "check_capability_reference_current.py"


@pytest.fixture(scope="module")
def modules():
    """Import both scripts; neither touches the engine until it is asked to."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import check_capability_reference_current as check
    import generate_capability_reference as gen

    return gen, check


@pytest.mark.parametrize("script", [GENERATOR, CHECK], ids=["generator", "check"])
def test_self_test_passes(script: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script), "--self-test"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_comparison_reports_clean(modules) -> None:
    _, check = modules
    pages = {"tools/describe.md": "body", "index.md": "overview"}
    assert check.compare(pages, dict(pages)) == ([], [], [])


def test_comparison_fires_on_each_kind_of_drift(modules) -> None:
    """A new tool, a removed tool, and an edited prompt each have to show up."""
    _, check = modules
    pages = {"tools/describe.md": "body", "index.md": "overview"}

    added_tool = {**pages, "tools/brand_new.md": "body"}
    assert check.compare(pages, added_tool)[1] == ["tools/brand_new.md"]

    removed_tool = {"index.md": "overview"}
    assert check.compare(pages, removed_tool)[0] == ["tools/describe.md"]

    edited_prompt = {**pages, "tools/describe.md": "a different prompt"}
    assert check.compare(pages, edited_prompt)[2] == ["tools/describe.md"]


def test_workflow_steps_render_in_run_order(modules) -> None:
    """Pages must list steps the way the run reaches them, not file order."""
    gen, _ = modules
    preset = {
        "nodes": [{"id": "transcribe"}, {"id": "files"}, {"id": "clean"}],
        "edges": [
            {"source": "files", "target": "transcribe"},
            {"source": "transcribe", "target": "clean"},
        ],
    }
    assert [n["id"] for n in gen.run_order(preset)] == ["files", "transcribe", "clean"]


def test_run_order_never_drops_a_step(modules) -> None:
    """A cyclic or malformed preset must still document every node."""
    gen, _ = modules
    cyclic = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    }
    assert {n["id"] for n in gen.run_order(cyclic)} == {"a", "b"}


def test_prompts_survive_backticks(modules) -> None:
    """A prompt containing a fence must not break out of its code block."""
    gen, _ = modules
    block = gen.fenced("say ```this``` back")
    assert block[0] == "````text"
    assert block[2] == "````"


def test_committed_pages_exist_and_carry_the_generated_banner(modules) -> None:
    """The reference is committed output, not a build artefact people forget."""
    gen, _ = modules
    pages = sorted(gen.OUT_DIR.rglob("*.md"))
    assert len(pages) > 90, f"only {len(pages)} reference pages committed"
    for page in pages:
        assert page.read_text().startswith(gen.BANNER), page
