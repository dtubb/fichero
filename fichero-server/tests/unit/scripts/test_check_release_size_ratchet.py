"""The release-size ratchet guardrail FIRES (#4444).

Guardrails must match granularity: every rule ships with a fixture proving it
fires. There is no real oversized release sitting in the tree to point at (a
good thing), so every fixture here is a synthesized fake .app bundle + .dmg —
built at test time with known byte counts, not borrowed from any baseline.
This mirrors fichero-server/tests/unit/scripts/test_coverage_ratchet_guardrail.py,
another ratchet guardrail invoked as a subprocess against fixture inputs.
"""

from __future__ import annotations

import importlib.util
import json
import plistlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_release_size_ratchet.py"


def _import_script():
    """Import the script as a module so a test can monkeypatch its
    DEFAULT_APP_PATH/DEFAULT_DMG_PATH globals — needed to exercise the argless
    (gate-sweep) path without depending on this machine's local build/ output."""
    spec = importlib.util.spec_from_file_location("check_release_size_ratchet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_ratchet(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _make_app(tmp_path: Path, name: str, executable_bytes: int, resource_bytes: int = 0) -> Path:
    """A minimal but real .app shape: Info.plist naming the executable, the
    executable itself, and (optionally) one resource file — enough for
    `_app_binary_path` and `_bundle_bytes` to do real work, not a mock."""
    app = tmp_path / f"{name}.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleExecutable": name, "CFBundleIdentifier": "app.fichero.fichero"})
    )
    (macos / name).write_bytes(b"\0" * executable_bytes)
    if resource_bytes:
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)
        (resources / "data.bin").write_bytes(b"\0" * resource_bytes)
    return app


def _make_dmg(tmp_path: Path, dmg_bytes: int) -> Path:
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"\0" * dmg_bytes)
    return dmg


def _seed_baseline(path: Path, **sizes_by_name: int) -> None:
    path.write_text(
        json.dumps({name: {"bytes": size, "note": "seed"} for name, size in sizes_by_name.items()}),
        encoding="utf-8",
    )


class TestRatchetFires:
    def test_a_bigger_binary_fires(self, tmp_path):
        """The motivating case: a synthesized growth in the executable itself."""
        app = _make_app(tmp_path, "Fichero", executable_bytes=2000)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, **{
            "release.app_binary": 1000,  # smaller than the 2000 measured above
            "release.app_bundle": 999_999,
            "release.dmg": 999_999,
        })
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 1, r.stdout + r.stderr
        assert "release-size ratchet FAILED" in r.stdout
        assert "release.app_binary" in r.stdout
        assert "GREW" in r.stdout

    def test_a_bigger_dmg_fires_even_if_the_binary_did_not_grow(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        dmg = _make_dmg(tmp_path, 20_000)
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, **{
            "release.app_binary": 1000,
            "release.app_bundle": 999_999,
            "release.dmg": 10_000,  # DMG grew, binary held
        })
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 1, r.stdout + r.stderr
        grown_lines = [line for line in r.stdout.splitlines() if "GREW" in line]
        assert len(grown_lines) == 1
        assert "release.dmg" in grown_lines[0]

    def test_one_byte_over_is_still_a_regression(self, tmp_path):
        """No tolerance: unlike the timing ratchet, one extra byte is never
        explained by the machine — it must fail outright."""
        app = _make_app(tmp_path, "Fichero", executable_bytes=1001)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, **{
            "release.app_binary": 1000,
            "release.app_bundle": 999_999,
            "release.dmg": 999_999,
        })
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 1, r.stdout + r.stderr


class TestRatchetPasses:
    def test_a_smaller_build_tightens_the_bar(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=500)
        dmg = _make_dmg(tmp_path, 4000)
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, **{
            "release.app_binary": 1000,
            "release.app_bundle": 999_999,
            "release.dmg": 5000,
        })
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "tightened" in r.stdout
        updated = json.loads(baseline.read_text())
        assert updated["release.app_binary"]["bytes"] == 500
        assert updated["release.dmg"]["bytes"] == 4000

    def test_an_identical_size_passes_without_rewriting(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        # First pass sets the baseline to the actual measured bundle size.
        r1 = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r1.returncode == 0, r1.stdout + r1.stderr
        # Second, identical pass must pass and report no growth.
        r2 = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r2.returncode == 0, r2.stdout + r2.stderr
        assert "GREW" not in r2.stdout

    def test_first_run_sets_the_baseline(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000, resource_bytes=2000)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "baseline set" in r.stdout
        data = json.loads(baseline.read_text())
        assert data["release.app_binary"]["bytes"] == 1000
        assert data["release.dmg"]["bytes"] == 5000
        # The bundle total includes Info.plist + the executable + the resource,
        # so it must be strictly larger than the executable alone.
        assert data["release.app_bundle"]["bytes"] > 1000

    def test_symlinks_inside_the_bundle_are_not_double_counted(self, tmp_path):
        """A framework's Versions/Current symlink must not add its target's
        bytes a second time to the bundle total."""
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        real_dir = app / "Contents" / "Frameworks" / "Sparkle.framework" / "Versions" / "A"
        real_dir.mkdir(parents=True)
        (real_dir / "Sparkle").write_bytes(b"\0" * 3000)
        current_link = app / "Contents" / "Frameworks" / "Sparkle.framework" / "Versions" / "Current"
        current_link.symlink_to(real_dir)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 0, r.stdout + r.stderr
        data = json.loads(baseline.read_text())
        # 1000 (binary) + Info.plist (small) + 3000 (real Sparkle binary) once.
        assert data["release.app_bundle"]["bytes"] < 1000 + 3000 + 3000  # not double-counted


class TestUpdateBaseline:
    def test_update_baseline_records_measured_values_unconditionally(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=9000)
        dmg = _make_dmg(tmp_path, 50_000)
        baseline = tmp_path / "baseline.json"
        _seed_baseline(baseline, **{
            "release.app_binary": 1000,  # smaller than the new build
            "release.app_bundle": 999_999,
            "release.dmg": 999_999,
        })
        r = run_ratchet(
            "--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline), "--update-baseline"
        )
        assert r.returncode == 0, r.stdout + r.stderr
        updated = json.loads(baseline.read_text())
        assert updated["release.app_binary"]["bytes"] == 9000
        assert updated["release.dmg"]["bytes"] == 50_000

    def test_update_baseline_creates_the_default_baseline_from_scratch(
        self, tmp_path, monkeypatch
    ):
        """The real bug this guards against: --update-baseline with no
        --baseline flag is exactly how a fresh default baseline gets
        created (this is how scripts/release_size_baseline.json itself was
        seeded) — the "default baseline must exist" BLIND check must not
        block its own creation mechanism."""
        module = _import_script()
        app = _make_app(tmp_path, "Fichero", executable_bytes=1234)
        dmg = _make_dmg(tmp_path, 4321)
        default_baseline = tmp_path / "does-not-exist-yet.json"
        monkeypatch.setattr(module, "DEFAULT_APP_PATH", app)
        monkeypatch.setattr(module, "DEFAULT_DMG_PATH", dmg)
        monkeypatch.setattr(module, "DEFAULT_BASELINE", default_baseline)
        rc = module.main(["--update-baseline"])
        assert rc == 0
        assert default_baseline.is_file()
        data = json.loads(default_baseline.read_text())
        assert data["release.app_binary"]["bytes"] == 1234


class TestTheArglessGateSweep:
    """scripts/verify_all.sh's --fast tier runs EVERY scripts/check_*.py with
    no arguments (see run_fast() in verify_all.sh) — required --app/--dmg
    would break the gate for everyone on every ordinary run. Argless must
    fall back to the standard build/releases/ layout and, when nothing was
    just built there (the normal case), report NOT ARMED rather than BLIND
    or a usage error."""

    def test_no_args_with_nothing_built_is_not_armed(self, tmp_path, monkeypatch):
        module = _import_script()
        monkeypatch.setattr(module, "DEFAULT_APP_PATH", tmp_path / "nope.app")
        monkeypatch.setattr(module, "DEFAULT_DMG_PATH", tmp_path / "nope.dmg")
        rc = module.main([])
        assert rc == 0

    def test_no_args_with_a_build_present_measures_it(self, tmp_path, monkeypatch, capsys):
        module = _import_script()
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        dmg = _make_dmg(tmp_path, 5000)
        # In a real checkout the default baseline is always committed content
        # (that is exactly what makes its ABSENCE mean "the tree moved" —
        # see TestTheDefaultBaselineIsRequired below) — seed one here so this
        # test models an ordinary repo, not the synthetic moved-tree case.
        default_baseline = tmp_path / "baseline.json"
        _seed_baseline(default_baseline, **{})
        monkeypatch.setattr(module, "DEFAULT_APP_PATH", app)
        monkeypatch.setattr(module, "DEFAULT_DMG_PATH", dmg)
        monkeypatch.setattr(module, "DEFAULT_BASELINE", default_baseline)
        rc = module.main([])
        assert rc == 0
        assert "baseline set" in capsys.readouterr().out

    def test_default_baseline_missing_is_blind_not_not_armed(self, tmp_path, monkeypatch):
        """The exact scenario test_guardrails_fail_on_missing_input.py (#4382)
        checks: this script alone in an empty directory, so its committed
        default baseline genuinely doesn't exist. That must be BLIND, never
        the same green 0 as an ordinary dev machine with no release built."""
        module = _import_script()
        monkeypatch.setattr(module, "DEFAULT_APP_PATH", tmp_path / "nope.app")
        monkeypatch.setattr(module, "DEFAULT_DMG_PATH", tmp_path / "nope.dmg")
        monkeypatch.setattr(module, "DEFAULT_BASELINE", tmp_path / "does-not-exist.json")
        rc = module.main([])
        assert rc == module.BLIND_EXIT_CODE

    def test_explicit_missing_app_is_blind_even_without_dmg_flag(self, tmp_path):
        """Passing only --app (still missing) must NOT fall back to
        NOT-ARMED — an explicit ask is held to full rigor."""
        r = run_ratchet("--app", str(tmp_path / "missing.app"), "--baseline", str(tmp_path / "b.json"))
        assert r.returncode == 2, r.stdout + r.stderr
        assert "BLIND" in r.stderr


class TestGoingBlind:
    """A missing artifact is a DIFFERENT claim than "no regression" — it must
    exit with a distinct code (2), never silently report success."""

    def test_a_missing_app_bundle_is_blind_not_green(self, tmp_path):
        dmg = _make_dmg(tmp_path, 5000)
        r = run_ratchet(
            "--app", str(tmp_path / "does-not-exist.app"),
            "--dmg", str(dmg),
            "--baseline", str(tmp_path / "baseline.json"),
        )
        assert r.returncode == 2, r.stdout + r.stderr
        assert "BLIND" in r.stderr

    def test_a_missing_dmg_is_blind_not_green(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        r = run_ratchet(
            "--app", str(app),
            "--dmg", str(tmp_path / "does-not-exist.dmg"),
            "--baseline", str(tmp_path / "baseline.json"),
        )
        assert r.returncode == 2, r.stdout + r.stderr
        assert "BLIND" in r.stderr

    def test_a_bundle_with_no_cfbundleexecutable_is_blind(self, tmp_path):
        """Synthesize the exact violation this guards against: a real .app
        shape whose Info.plist forgot to name its own executable."""
        app = tmp_path / "Fichero.app"
        (app / "Contents" / "MacOS").mkdir(parents=True)
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "x"}))
        dmg = _make_dmg(tmp_path, 5000)
        r = run_ratchet(
            "--app", str(app), "--dmg", str(dmg), "--baseline", str(tmp_path / "baseline.json")
        )
        assert r.returncode == 2, r.stdout + r.stderr
        assert "CFBundleExecutable" in r.stderr

    def test_a_corrupt_baseline_is_blind_not_a_silent_reset(self, tmp_path):
        app = _make_app(tmp_path, "Fichero", executable_bytes=1000)
        dmg = _make_dmg(tmp_path, 5000)
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{ not json", encoding="utf-8")
        r = run_ratchet("--app", str(app), "--dmg", str(dmg), "--baseline", str(baseline))
        assert r.returncode == 2, r.stdout + r.stderr
        assert "restore it from git" in r.stderr


# ---------------------------------------------------------------------------
# iOS (#4466) — the platform whose broken builds actually shipped
# ---------------------------------------------------------------------------


def _make_ios_app(tmp_path: Path, name: str, executable_bytes: int) -> Path:
    """An iOS .app: FLAT. Info.plist and the executable at the bundle root.

    Written out by hand rather than reusing `_make_app` precisely because the
    layouts differ — a fixture that shared the macOS shape would have hidden
    the bug this test exists to prevent.
    """
    app = tmp_path / f"{name}.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleExecutable": name})
    )
    (app / name).write_bytes(b"\0" * executable_bytes)
    return app


def test_an_ios_bundle_is_measured_despite_its_flat_layout(tmp_path):
    """The bug caught before shipping: `Contents/Info.plist` is macOS-only.

    Pointing the macOS resolver at an iOS bundle raises Blind on every real
    build — a ratchet that looks armed and can never measure anything.
    """
    ios_app = _make_ios_app(tmp_path, "Fichero", executable_bytes=5000)
    baseline = tmp_path / "baseline.json"

    assert _import_script().main(["--ios-app", str(ios_app), "--baseline", str(baseline)]) == 0

    recorded = json.loads(baseline.read_text())
    assert recorded["release.ios_app_binary"]["bytes"] == 5000
    assert "release.ios_app_bundle" in recorded


def test_a_bigger_ios_binary_fires(tmp_path):
    baseline = tmp_path / "baseline.json"
    _import_script().main(["--ios-app", str(_make_ios_app(tmp_path / "a", "Fichero", 5000)),
          "--baseline", str(baseline)])

    assert _import_script().main(["--ios-app", str(_make_ios_app(tmp_path / "b", "Fichero", 5001)),
                 "--baseline", str(baseline)]) == 1


def test_ios_only_does_not_demand_the_macos_artifacts(tmp_path):
    """The gate's iOS leg produces a .app and no DMG. Requiring the macOS
    artifacts would make the iOS ratchet unrunnable exactly where it runs."""
    ios_app = _make_ios_app(tmp_path, "Fichero", executable_bytes=1234)
    baseline = tmp_path / "baseline.json"

    assert _import_script().main(["--ios-app", str(ios_app), "--baseline", str(baseline)]) == 0
    assert "release.dmg" not in json.loads(baseline.read_text())


def test_a_missing_ios_bundle_is_BLIND_not_a_pass(tmp_path):
    """Same rule as every other artifact: asked to check a specific build that
    cannot be measured is exit 2, never 0."""
    assert _import_script().main(["--ios-app", str(tmp_path / "absent.app"),
                 "--baseline", str(tmp_path / "b.json")]) == 2


def test_ios_and_macos_can_be_measured_together(tmp_path):
    """One baseline file holds both. A second ratchet with a second baseline is
    the divergence this project keeps finding elsewhere."""
    app = _make_app(tmp_path, "Fichero", executable_bytes=100)
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"\0" * 200)
    ios_app = _make_ios_app(tmp_path / "ios", "Fichero", executable_bytes=300)
    baseline = tmp_path / "baseline.json"

    assert _import_script().main(["--app", str(app), "--dmg", str(dmg), "--ios-app", str(ios_app),
                 "--baseline", str(baseline)]) == 0

    recorded = json.loads(baseline.read_text())
    for key in ("release.app_binary", "release.dmg", "release.ios_app_binary"):
        assert key in recorded
