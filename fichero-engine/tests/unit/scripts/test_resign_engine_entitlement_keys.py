"""The App Store engine must carry EXACTLY app-sandbox + inherit (#3952).

`get-task-allow` alongside `com.apple.security.inherit` makes the system abort
the sandboxed child (Apple's Entitlement Key Reference), so the engine dies on
launch and the app renders nothing. `resign_engine_in_archive.sh` refuses to
sign when the entitlement key set is anything but the two-key pair — one of
Daniel's three distribution targets, previously with no test at all.

A stranded commit (`0345f4208`, 25 July) carried a test for this and never
merged. Its assertion was `extractor in RESIGN_ENGINE.read_text()` — it pinned
the literal text of the awk program, so when the extractor was later TIGHTENED
(counting only `com.apple.*` keys instead of any assignment line) the test would
have broken on a change that improved the very thing it guarded.

So these assert BEHAVIOUR, never implementation text: the real script runs with
`PLISTBUDDY` pointed at a stub emitting representative output, and the
assertions are on what the script accepts and rejects. Tightening the pattern
again will not break them; only a real regression will.

WHAT THESE DO NOT GUARD, established by measurement rather than assumed: they
pin the two-key RULE, not the extraction pattern. Mutating the extractor back
to the pre-`0345f4208` looser form (any assignment line, rather than only
`com.apple.*` keys) leaves all of these passing, because the two forms produce
identical output for real entitlements: PlistBuddy's `Dict {` root contains no
`=`, so NEITHER pattern ever matched it. Distinguishing the two would need a
nested `0 = /tmp` line that no genuine two-key entitlements plist contains —
an input invented to justify a distinction that does not arise in practice.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "resign_engine_in_archive.sh"

TWO_KEY_ERROR = "must hold exactly app-sandbox + inherit"

# What PlistBuddy actually prints for the correct engine entitlements: a
# structural `Dict {` root, the two keys, and a closing brace.
VALID_PLIST_OUTPUT = """Dict {
    com.apple.security.app-sandbox = true
    com.apple.security.inherit = true
}
"""

# The failure this script exists to prevent: the export re-signed the engine
# with the main app's TestFlight entitlements.
GET_TASK_ALLOW_OUTPUT = """Dict {
    com.apple.security.app-sandbox = true
    com.apple.security.inherit = true
    com.apple.security.get-task-allow = true
}
"""

MISSING_INHERIT_OUTPUT = """Dict {
    com.apple.security.app-sandbox = true
}
"""


@pytest.fixture
def fake_archive(tmp_path):
    """A bundle shaped enough to reach the entitlement check, plus stubs.

    `codesign` and `file` are stubbed onto PATH so the script never touches a
    real keychain: what is under test is the key-set rule, not signing.
    """
    app = tmp_path / "Fichero.app"
    (app / "Contents" / "Helpers" / "Fichero Engine.app").mkdir(parents=True)
    entitlements = tmp_path / "engine.entitlements"
    entitlements.write_text("<plist/>", encoding="utf-8")

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    for name in ("codesign", "file"):
        stub = stub_bin / name
        stub.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)

    def run(plist_output: str) -> subprocess.CompletedProcess:
        plistbuddy = tmp_path / "plistbuddy-stub"
        plistbuddy.write_text(
            "#!/bin/bash\ncat <<'EOF'\n" + plist_output + "EOF\n", encoding="utf-8"
        )
        plistbuddy.chmod(0o755)

        env = dict(os.environ)
        env["PLISTBUDDY"] = str(plistbuddy)
        env["PATH"] = f"{stub_bin}:{env['PATH']}"
        return subprocess.run(
            ["bash", str(SCRIPT), str(app), "Fake Identity", str(entitlements)],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    return run


def test_the_two_key_pair_is_accepted(fake_archive):
    """The correct App Store set must pass the rule."""
    result = fake_archive(VALID_PLIST_OUTPUT)

    assert TWO_KEY_ERROR not in result.stderr, (
        "the valid two-key entitlement set was rejected:\n" + result.stderr
    )


def test_the_plistbuddy_dict_marker_is_not_counted_as_a_key(fake_archive):
    """`Dict {` is PlistBuddy structure, not an entitlement.

    This is the whole point of the stranded commit: an extractor that counted
    any assignment-ish line saw the root marker as a third key and refused to
    sign a perfectly valid engine.
    """
    assert "Dict {" in VALID_PLIST_OUTPUT  # the fixture really does exercise it

    result = fake_archive(VALID_PLIST_OUTPUT)

    assert TWO_KEY_ERROR not in result.stderr


def test_get_task_allow_is_rejected(fake_archive):
    """The launch-killer. get-task-allow + inherit aborts the sandboxed child."""
    result = fake_archive(GET_TASK_ALLOW_OUTPUT)

    assert result.returncode != 0, "an engine carrying get-task-allow was signed"
    assert TWO_KEY_ERROR in result.stderr
    assert "get-task-allow" in result.stderr, (
        "the offending key set should be printed so the failure is diagnosable"
    )


def test_a_missing_key_is_rejected(fake_archive):
    """Exactly two keys — not 'at least app-sandbox'."""
    result = fake_archive(MISSING_INHERIT_OUTPUT)

    assert result.returncode != 0
    assert TWO_KEY_ERROR in result.stderr


def test_an_unrelated_apple_key_is_rejected(fake_archive):
    """Exactly the two keys — not "any two sandbox keys".

    A third `com.apple.*` key passes the extractor's own pattern, so this
    pins the count rule rather than the match rule.
    """
    result = fake_archive(
        "Dict {\n"
        "    com.apple.security.app-sandbox = true\n"
        "    com.apple.security.inherit = true\n"
        "    com.apple.security.network.client = true\n"
        "}\n"
    )

    assert result.returncode != 0
    assert TWO_KEY_ERROR in result.stderr
