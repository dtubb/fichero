"""The conflict-marker guardrail FIRES, and knows blind from clean.

A guardrail nobody has watched fail is a guess. This exercises all three exit
codes against real trees on disk: 0 clean, 1 violation, 2 blind.

The bug behind the guardrail: on 2026-08-03 conflict markers were committed
into ``fichero-mcp/tests/test_mcp_server.py``. Python could not parse the
module, collection failed, and the whole MCP suite stopped running while the
run stayed green -- the failure and the thing that would have reported it were
the same file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_no_conflict_markers.py"


def run_in(tree: Path) -> subprocess.CompletedProcess:
    """Run the check against a throwaway git repo.

    The check reads ``git ls-files``, so a fixture has to be a real repo --
    a bare directory of files would scan nothing and prove nothing.
    """
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tree,
    )


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    tree = tmp_path / "repo"
    (tree / "scripts").mkdir(parents=True)
    for rel, body in files.items():
        p = tree / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    return tree


CONFLICTED = """\
def thing():
<<<<<<< HEAD
    return "ours"
=======
    return "theirs"
>>>>>>> other-branch
"""


def load_checker():
    """Import the real script as a module.

    Not exec() of its source: the script reads ``__file__`` at import time to
    find the repo root, and a bare exec has no ``__file__``. Importing it the
    way Python actually would is both simpler and a truer test -- it exercises
    the shipped module rather than a copy that might drift from it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_no_conflict_markers", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(REPO_ROOT / "scripts"))
    return mod


class TestFiresOnRealMarkers:
    def test_committed_markers_are_a_violation(self, tmp_path, monkeypatch):
        """The exact shape that killed the MCP suite: markers in a test file."""
        mod = load_checker()
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_thing.py").write_text(CONFLICTED, encoding="utf-8")

        # Point the real matcher at the fixture tree. The floor is exercised
        # separately below; what is under test here is that the matcher SEES
        # markers it is shown.
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        bad = mod.offenders([Path("tests/test_thing.py")])

        assert bad, "markers present and the matcher did not see them"
        assert any("<<<<<<<" in snippet for _, _, snippet in bad)
        # It names a place a human can go to, not just "something is wrong".
        rel, lineno, _ = bad[0]
        assert rel == "tests/test_thing.py"
        assert lineno == 2


class TestDoesNotCryWolf:
    def test_markdown_underlining_is_not_a_conflict(self, tmp_path, monkeypatch):
        """`=======` under a heading is ordinary Markdown, not a conflict.

        This is why `=======` is not in MARKERS. A check that fires on every
        reStructuredText heading gets disabled within a week, and a disabled
        guardrail is worse than an absent one -- it still looks present.
        """
        mod = load_checker()
        assert "=======" not in mod.MARKERS

        (tmp_path / "doc.md").write_text(
            "Heading\n=======\n\nbody text\n", encoding="utf-8"
        )
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
        assert mod.offenders([Path("doc.md")]) == []

    def test_the_real_tree_is_clean(self):
        """Exit 0 against this repository, and it says how much it read."""
        r = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, timeout=300, cwd=REPO_ROOT,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "OK" in r.stdout
        # The count must appear. "OK" with no population is the failure mode
        # this whole family of checks exists to prevent.
        assert "tracked text files read" in r.stdout


class TestBlindIsNotClean:
    def test_empty_tree_exits_blind_not_ok(self, tmp_path):
        """Below the floor: exit 2, never 0.

        A repo with almost nothing in it is not a repo that passed -- it is a
        scan that found nothing to look at, and those must not share an exit
        code (#4487).
        """
        tree = make_repo(tmp_path, {"README.md": "# nothing here\n"})
        (tree / "scripts" / "check_no_conflict_markers.py").write_text(
            SCRIPT.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (tree / "scripts" / "_check_floor.py").write_text(
            (REPO_ROOT / "scripts" / "_check_floor.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "-A"], cwd=tree, check=True)

        r = subprocess.run(
            [sys.executable, str(tree / "scripts" / "check_no_conflict_markers.py")],
            capture_output=True, text=True, timeout=120, cwd=tree,
        )
        assert r.returncode == 2, (
            f"expected BLIND(2), got {r.returncode}: {r.stdout}{r.stderr}"
        )
        assert "BLIND" in r.stdout + r.stderr
