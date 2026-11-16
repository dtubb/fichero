"""scripts/notarize.sh's poll: a failed `notarytool info` call is not "In Progress"
(spec: release.lane.notarize-poll-failed-call-not-in-progress). xcrun and security are fakes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_NOTARIZE = Path(__file__).resolve().parents[4] / "scripts" / "notarize.sh"

FAKE_XCRUN = """#!/bin/bash
echo "$@" >> "$FAKE_LOG"
case "$2" in
  history) exit 0 ;;
  submit) echo '{"id":"sub-1"}' ;;
  info)
    case "$*" in
      *--keychain-profile*) [ "$FAKE_PROFILE" = dead ] && exit 1 ;;
    esac
    [ "$FAKE_API" = dead ] && exit 1
    echo '{"status":"Accepted"}' ;;
esac
exit 0
"""


def _run(tmp_path, *, profile="dead", api="ok", key=True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xcrun", FAKE_XCRUN), ("security", "#!/bin/bash\necho 'Developer ID Application'\n"),
                       ("sleep", "#!/bin/bash\nexit 0\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    keyfile = tmp_path / "AuthKey.p8"
    if key:
        keyfile.write_text("k")
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "calls"),
           "FAKE_PROFILE": profile, "FAKE_API": api, "FICHERO_NOTARY_KEY_PATH": str(keyfile),
           "FICHERO_NOTARY_MAX_POLLS": "8", "FICHERO_NOTARY_POLL_SECONDS": "0"}
    # history succeeds for the profile, so auth starts as the keychain profile
    r = subprocess.run(["bash", str(_NOTARIZE), str(dmg)], env=env, capture_output=True, text=True, timeout=60)
    return r, (tmp_path / "calls").read_text()


def test_dead_profile_info_calls_fall_back_to_the_api_key_and_finish(tmp_path):
    r, calls = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "falling back to the App Store Connect API key" in r.stdout
    assert "info sub-1 --key" in calls


def test_unreadable_status_is_an_error_not_an_hour_of_in_progress(tmp_path):
    r, calls = _run(tmp_path, api="dead")
    assert r.returncode == 1
    assert "status unreadable" in r.stderr
    assert calls.count("info sub-1") == 5
