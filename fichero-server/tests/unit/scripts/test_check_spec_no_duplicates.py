"""scripts/check_spec_no_duplicates.py (dev-workflows.run.presubmit-lints): a behaviour defined twice or a long line repeated in one
spec file fails with both line numbers; the known-debt list only shrinks. Offline, text only."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_no_duplicates.py"
_SPEC = importlib.util.spec_from_file_location("check_spec_no_duplicates", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

PARA = "  **Auto send-back** (manager 2026-11-03): a red check on an external lane is sent back by the loop itself, three times a batch, " \
       "with an auto-send-back row and no alert; the fourth is the alert as before."


def _spec(tmp_path, text):
    d = tmp_path / "docs/contributor_manual/specs/harness"
    d.mkdir(parents=True)
    (d / "x.md").write_text(text)
    return tmp_path


def test_a_behaviour_defined_twice_or_a_repeated_paragraph_fails_and_a_clean_spec_passes(tmp_path):
    a = "- `dev-workflows.run.jail-home` [PARTIAL] (#6116) — a rung gets a scratch HOME.\n"
    b = "- `dev-workflows.tool.file` — **[GAP]** (#6116) builder file.\n"
    assert _mod.problems(_spec(tmp_path / "ok", a + b + PARA + "\n"), set()) == ([], [])
    out, _ = _mod.problems(_spec(tmp_path / "id", a + b + a.replace("scratch", "new")), set())
    assert out == ["docs/contributor_manual/specs/harness/x.md:3: behaviour `dev-workflows.run.jail-home` is defined again (first at line 1)"]
    out, _ = _mod.problems(_spec(tmp_path / "em", b + a + b), set())
    assert len(out) == 1 and "dev-workflows.tool.file" in out[0], "the em-dash bold-tag form is a bullet too"
    out, _ = _mod.problems(_spec(tmp_path / "para", a + PARA + "\n" + b + PARA + " Edited later.\n"), set())
    assert out == ["docs/contributor_manual/specs/harness/x.md:4: repeats the text that opens line 2"], "a copy that diverged later"


def test_known_debt_is_reported_not_failed_and_a_fixed_entry_must_leave_the_list(tmp_path):
    a = "- `x.y` [GAP] (#1) one.\n"
    root = _spec(tmp_path, a + a)
    assert _mod.problems(root, {("harness/x.md", "x.y")}) == ([], ["docs/contributor_manual/specs/harness/x.md:2: `x.y` defined twice (known debt)"])
    (root / "docs/contributor_manual/specs/harness/x.md").write_text(a)
    out, _ = _mod.problems(root, {("harness/x.md", "x.y")})
    assert out == ["KNOWN entry harness/x.md `x.y` is no longer duplicated: remove it from KNOWN"]
