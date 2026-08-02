"""Tests for the #3968 UI-test boot-gating guardrail.

Every fixture synthesises its own Swift in a tmp tree — nothing is borrowed from
the committed source, so these stay honest when the real files move, and none of
them can pass because the real tree happens to be in the right shape today.

The bug being guarded: `isUITesting()` is true in BOTH UI-test modes, so a boot
side effect gated on the bare flag is switched off in the embedded mode whose
whole purpose is to run the real engine. The embedded launch tests then polled
for 120 seconds against an app that had never spawned an engine.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "check_uitest_boot_gating.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_uitest_boot_gating")


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _run(app_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--app-dir", str(app_dir)],
        capture_output=True,
        text=True,
    )


_DEFINITION = """
func isUITesting() -> Bool {
    ProcessInfo.processInfo.arguments.contains("--uitesting")
}

func isEmbeddedEngineUITesting() -> Bool {
    isUITesting() && ProcessInfo.processInfo.arguments.contains("--uitesting-embedded")
}

func suppressesBootSideEffectsForUITesting() -> Bool {
    isUITesting() && !isEmbeddedEngineUITesting()
}
"""

_TWO_GOOD_CALLERS = """
let interactiveLaunch = !(isRunningXCTests() || suppressesBootSideEffectsForUITesting())
let inputs = Inputs(isInertHost: isPreview || suppressesBootSideEffectsForUITesting())
"""


def _healthy(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    _write(app, "Services/UITestSupport.swift", _DEFINITION)
    _write(app, "Boot.swift", _TWO_GOOD_CALLERS)
    return app


# ---------------------------------------------------------------------------
# It fires on the shape that caused the P0
# ---------------------------------------------------------------------------


def test_hand_rolled_carve_out_is_a_violation(tmp_path):
    app = _healthy(tmp_path)
    _write(
        app,
        "NewGate.swift",
        "let inert = isPreview || (isUITesting() && !isEmbeddedEngineUITesting())\n",
    )

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "hand-rolled embedded carve-out" in result.stdout
    assert "NewGate.swift" in result.stdout


def test_the_reversed_spelling_is_caught_too(tmp_path):
    """`!isEmbedded… && isUITesting()` is the same predicate written backwards.

    A guard that only knows one spelling teaches people the other one.
    """
    app = _healthy(tmp_path)
    _write(
        app,
        "NewGate.swift",
        "let inert = !isEmbeddedEngineUITesting() && isUITesting()\n",
    )

    assert _run(app).returncode == 1


def test_the_predicates_own_body_is_not_a_violation(tmp_path):
    """The one place the conjunction belongs is the definition itself."""
    result = _run(_healthy(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_second_copy_inside_the_defining_file_is_still_caught(tmp_path):
    """The exemption is a short window after `func`, not the whole file.

    Exempting the file would let the next hand-rolled copy hide in the very
    file that exists to stop it.
    """
    app = tmp_path / "app"
    _write(app, "Boot.swift", _TWO_GOOD_CALLERS)
    _write(
        app,
        "Services/UITestSupport.swift",
        _DEFINITION + "\nlet sneaky = isUITesting() && !isEmbeddedEngineUITesting()\n",
    )

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "UITestSupport.swift" in result.stdout


# ---------------------------------------------------------------------------
# Near misses it must NOT fire on — a guard that cries wolf gets deleted
# ---------------------------------------------------------------------------


def test_bare_isUITesting_is_allowed(tmp_path):
    """Both modes genuinely want the same answer in several places.

    The disposable support directory, the seeded library fixture and the
    explicitly-owned transport all check the bare flag on purpose. Flagging
    them would make this guard noise.
    """
    app = _healthy(tmp_path)
    _write(
        app,
        "Support.swift",
        """
func uiTestSupportDirectory() -> URL? {
    guard isUITesting(), let path = env["FICHERO_UITEST_HOME"] else { return nil }
    return URL(fileURLWithPath: path)
}
""",
    )

    result = _run(app)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_comment_quoting_the_banned_shape_is_not_a_violation(tmp_path):
    """The rationale has to be allowed to name what it forbids."""
    app = _healthy(tmp_path)
    _write(
        app,
        "Documented.swift",
        "// The carve-out isUITesting() && !isEmbeddedEngineUITesting() used to\n"
        "/// be written out by hand: isUITesting() && !isEmbeddedEngineUITesting()\n"
        "let x = 1\n",
    )

    result = _run(app)

    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Blindness — zero violations must not be reachable by deletion
# ---------------------------------------------------------------------------


def test_deleting_the_predicate_fails_rather_than_passing_clean(tmp_path):
    """Remove the predicate and the banned shape both, and a naive checker
    calls the tree spotless while the P0 is live again."""
    app = tmp_path / "app"
    _write(app, "Boot.swift", "let interactiveLaunch = !isRunningXCTests()\n")

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "Expected exactly 1 definition" in result.stdout


def test_the_predicate_existing_but_unused_fails(tmp_path):
    """Both boot gates must actually call it.

    A definition nobody calls is documentation, not enforcement — and the gate
    it was extracted from would be back on the bare flag.
    """
    app = tmp_path / "app"
    _write(app, "Services/UITestSupport.swift", _DEFINITION)

    result = _run(app)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "call site" in result.stdout


def test_an_empty_tree_does_not_pass(tmp_path):
    app = tmp_path / "app"
    app.mkdir()

    assert _run(app).returncode == 1


def test_missing_scan_root_is_blind_not_a_pass(tmp_path):
    result = _run(tmp_path / "does-not-exist")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLIND" in result.stderr


def test_the_real_tree_gates_on_the_named_predicate():
    """One live, unstubbed check — everything above is synthetic and would stay
    green if the real gating regressed tomorrow."""
    violations, definitions, uses = guard.scan(guard.APP_DIR)

    assert not violations, f"hand-rolled #3968 carve-out is back: {violations}"
    assert definitions == 1
    assert uses >= 2
