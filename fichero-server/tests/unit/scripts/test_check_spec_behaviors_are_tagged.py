"""The untagged-behavior guard (#5120).

WHY this test exists: the guard's whole value is telling an untagged bullet apart from a
tagged one and from a bullet that only LOOKS like a behavior. Each of those three
judgements is proved below against a fixture, because a guard whose precision nobody
pinned is a guard that gets an exclusion bolted on the first time it false-positives, and
then it stops finding anything.

The bug it was written for, twice on one day: `segment-representations.md` had 21
behavior-shaped bullets and `spec_pipeline status` reported 12, and the tables paragraph in
`segments-and-geometry.md` described cells, spans and headers with no `source.table.*`
behavior at all. Both read as covered. Neither could ever be [OK].
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_behaviors_are_tagged.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_behaviors_are_tagged", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)


def write_spec(tmp_path: Path, body: str, name: str = "thing.md") -> Path:
    (tmp_path / name).write_text(body)
    return tmp_path


class TestItFindsTheBulletNobodyCanSee:
    def test_a_bullet_with_no_tag_is_reported(self, tmp_path):
        """The actual defect: prose wearing a behavior's clothes."""
        specs = write_spec(tmp_path, "- `source.table.cells` — a cell knows its row and column.\n")
        assert [e[2] for e in guard.untagged_behaviors(specs)] == ["source.table.cells"]

    def test_the_report_carries_the_line_number_so_it_can_be_opened(self, tmp_path):
        specs = write_spec(tmp_path, "# Heading\n\nsome prose\n\n- `source.table.cells` — text.\n")
        assert guard.untagged_behaviors(specs)[0][1] == 5

    @pytest.mark.parametrize("tag", ["OK", "GAP", "PARTIAL", "BROKEN", "MISSING", "PROPOSED", "CONVENTION", "GAP/BROKEN"])
    def test_every_tag_the_pipeline_knows_counts_as_tagged(self, tmp_path, tag):
        """If the guard disagreed with the pipeline about what a tag IS, it would demand
        re-tagging of behaviors the pipeline already tracks."""
        specs = write_spec(tmp_path, f"- `source.table.cells` — **[{tag}]** (#1) text.\n")
        assert guard.untagged_behaviors(specs) == []

    def test_an_unbolded_tag_counts_too(self, tmp_path):
        """segment-representations.md writes `id` [MISSING] (#4763) — no asterisks. The
        pipeline accepts that spelling, so this must too, or the guard would order a
        cosmetic rewrite of a whole file that is not actually broken."""
        specs = write_spec(tmp_path, "- `segment.read.representations` [MISSING] (#4763) — text.\n")
        assert guard.untagged_behaviors(specs) == []

    def test_a_tag_on_a_continuation_line_counts(self, tmp_path):
        """A long behavior often wraps before its tag."""
        specs = write_spec(tmp_path, "- `source.table.cells`\n  — **[GAP]** (#1) a cell knows its row.\n")
        assert guard.untagged_behaviors(specs) == []


class TestItDoesNotFlagWhatIsNotABehavior:
    """Specs open bullets with filenames and module paths. Demanding a state tag on those
    would be noise, and noise is how a guard gets ignored."""

    @pytest.mark.parametrize("identifier", ["export_openapi_schema.py", "check_docs_paths.py", "build.sh"])
    def test_a_filename_bullet_is_not_a_behavior(self, tmp_path, identifier):
        specs = write_spec(tmp_path, f"- `{identifier}` — writes the schema.\n")
        assert guard.untagged_behaviors(specs) == []

    def test_a_module_path_bullet_is_not_a_behavior(self, tmp_path):
        specs = write_spec(tmp_path, "- `fichero_server.models.hermeneutics` — the module.\n")
        assert guard.untagged_behaviors(specs) == []

    def test_a_real_behavior_that_merely_contains_a_dot_still_counts(self, tmp_path):
        """Guard against over-filtering: the exclusions must not swallow ordinary ids."""
        specs = write_spec(tmp_path, "- `source.format.export-choices` — text.\n")
        assert [e[2] for e in guard.untagged_behaviors(specs)] == ["source.format.export-choices"]

    def test_scaffolding_files_are_skipped(self, tmp_path):
        """_TEMPLATE.md's example bullets are illustrations, not commitments."""
        specs = write_spec(tmp_path, "- `some.example.id` — text.\n", name="_TEMPLATE.md")
        assert guard.untagged_behaviors(specs) == []


class TestANestedWorktreeIsNotPartOfTheSpecs:
    def test_a_worktree_inside_the_specs_dir_is_not_scanned(self, tmp_path):
        """The real incident: an agent's isolated worktree is created at
        `<cwd>/.claude/worktrees/<id>/` -- a whole second repo. Spawned from inside
        specs/source/, it made this guard report 128 bullets from RELEASE_NOTES.md,
        agent-work notes and sandbox research as untagged behaviours."""
        nested = tmp_path / ".claude" / "worktrees" / "agent-x" / "docs"
        nested.mkdir(parents=True)
        (nested / "notes.md").write_text("- `engine.log` — not a spec behaviour.\n")
        assert guard.untagged_behaviors(tmp_path) == []

    def test_a_real_spec_beside_it_is_still_scanned(self, tmp_path):
        """The skip must not swallow the specs it sits next to."""
        (tmp_path / ".claude").mkdir()
        write_spec(tmp_path, "- `source.table.cells` — untagged.\n")
        assert [e[2] for e in guard.untagged_behaviors(tmp_path)] == ["source.table.cells"]


class TestTheBaselineShrinksOnly:
    def test_identity_ignores_the_line_number(self, tmp_path):
        """Editing prose ABOVE a known-untagged bullet moves its line and must not fail the
        build -- otherwise the baseline would have to be rewritten on every unrelated edit,
        and people would stop reading it."""
        before = guard._key(("fixture/x.md", 10, "a.b"))
        after = guard._key(("fixture/x.md", 99, "a.b"))
        assert before == after

    def test_a_baselined_entry_that_got_tagged_must_be_removed(self, tmp_path, monkeypatch, capsys):
        """The half that stops the file rotting: without it, a baseline accumulates entries
        describing behaviors that were fixed years ago and tells you nothing."""
        specs = write_spec(tmp_path, "- `source.table.cells` — **[GAP]** (#1) now tagged.\n")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"untagged": ["thing.md::source.table.cells"]}))
        monkeypatch.setattr(guard, "SPECS_DIR", specs)
        monkeypatch.setattr(guard, "BASELINE", baseline)
        monkeypatch.setattr(sys, "argv", ["guard"])
        assert guard.main() == 1
        assert "is now tagged" in capsys.readouterr().out

    def test_a_new_untagged_bullet_fails_even_with_a_baseline(self, tmp_path, monkeypatch, capsys):
        specs = write_spec(tmp_path, "- `source.table.rows` — brand new, untagged.\n")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"untagged": []}))
        monkeypatch.setattr(guard, "SPECS_DIR", specs)
        monkeypatch.setattr(guard, "BASELINE", baseline)
        monkeypatch.setattr(sys, "argv", ["guard"])
        assert guard.main() == 1
        assert "source.table.rows" in capsys.readouterr().out

    def test_a_missing_specs_dir_is_loud_not_green(self, tmp_path, monkeypatch, capsys):
        """A guard that passes when it found nothing to check is worse than no guard."""
        monkeypatch.setattr(guard, "SPECS_DIR", tmp_path / "nope")
        monkeypatch.setattr(sys, "argv", ["guard"])
        assert guard.main() == 2
        assert "blind, not green" in capsys.readouterr().out
