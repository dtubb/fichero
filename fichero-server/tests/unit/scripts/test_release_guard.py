"""scripts/release_guard.py: each test reproduces one thing the 2026.11.14
release needed a person for (docs/contributor_manual/specs/harness/release-and-versioning.md,
"The lane runs unattended"). No Apple, network, Messages or tmutil call is real here."""

from __future__ import annotations

import importlib.util
import plistlib
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "release_guard.py"
_SPEC = importlib.util.spec_from_file_location("release_guard", _SCRIPT)
rg = importlib.util.module_from_spec(_SPEC)
sys.modules["release_guard"] = rg
_SPEC.loader.exec_module(rg)


class Recorder:
    def __init__(self, fail=(), on=None):
        self.calls: list[list[str]] = []
        self.fail = fail
        self.on = on or {}

    def __call__(self, cmd, **_kw):
        self.calls.append(list(cmd))
        for key, fn in self.on.items():
            if key in cmd:
                fn(cmd)
        rc = 1 if any(f in cmd for f in self.fail) else 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")


# 1. disk
def test_enough_space_thins_nothing():
    run = Recorder()
    ok, _ = rg.ensure_disk("DMG", 20, free=lambda: 50.0, run=run)
    assert ok and run.calls == []


def test_low_space_thins_snapshots_then_proceeds():
    levels = iter([12.0, 41.0])
    run = Recorder()
    ok, msg = rg.ensure_disk("engine", 20, free=lambda: next(levels), run=run)
    assert ok and "after thinning" in msg
    assert run.calls == [["tmutil", "thinlocalsnapshots", "/", "40000000000", "4"]]


def test_still_low_after_thinning_refuses_and_deletes_nothing():
    run = Recorder()
    ok, msg = rg.ensure_disk("Mac archive", 20, free=lambda: 6.0, run=run)
    assert not ok and "Mac archive" in msg and "never DerivedData" in msg
    assert run.calls == [rg.THIN_CMD]  # the only disk action is the thin


# 2. build number: 2026.11.14 reused build 23, already in the live appcast
FEED = """<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel>
<item><sparkle:version>23</sparkle:version></item>
<item><sparkle:version>23</sparkle:version><sparkle:channel>dev</sparkle:channel></item>
<item><sparkle:version>20</sparkle:version></item></channel></rss>"""


def test_reused_build_is_refused():
    pub = rg.published_builds(FEED, ["release: Fichero 2026.11.13 (build 23)"])
    assert "not above every published build (highest 23)" in rg.build_problem(23, pub)
    assert rg.build_problem(24, pub) is None


def test_next_build_is_above_local_and_every_published_one():
    assert rg.next_build(23, rg.published_builds(FEED, [])) == 24  # pinned version: still bumps
    assert rg.next_build(20, [23]) == 24  # stale local stamp
    assert rg.next_build(30, [23]) == 31
    assert rg.published_builds("", ["Fichero 2026.12.01 (build 40)", "Merge pull request #1"]) == [40]


def test_unreachable_feed_is_blind_not_green():
    def boom():
        raise OSError("offline")
    try:
        rg.published(feed=boom, tags=lambda: [])
    except RuntimeError as exc:
        assert "cannot read the live appcast" in str(exc)
    else:
        raise AssertionError("an unreachable feed must refuse")


def test_local_build_reads_the_xcconfig(tmp_path):
    x = tmp_path / "Version.xcconfig"
    x.write_text("MARKETING_VERSION = 2026.11.14\nCURRENT_PROJECT_VERSION = 23\n")
    assert rg.local_build(x) == 23


# 3. iOS: `.buttonStyle(.link)` surfaced only at the archive, 3 h in
def test_ios_preflight_is_an_unsigned_generic_ios_build_that_shows_errors():
    def run(cmd, **_kw):
        return subprocess.CompletedProcess(
            cmd, 65, stdout="Foo.swift:12:5: error: 'link' is unavailable in iOS\nnoise", stderr="")

    ok, msg = rg.ios_preflight("p.xcodeproj", "Fichero (App Store)", "App Store", "dev", run=run)
    assert not ok and "'link' is unavailable in iOS" in msg and "noise" not in msg
    cmd = rg.ios_preflight_cmd("p.xcodeproj", "S", "C", "dev")
    assert cmd[-1] == "build" and "generic/platform=iOS" in cmd and "CODE_SIGNING_ALLOWED=NO" in cmd
    assert "archive" not in cmd


# 4. Mac TestFlight export sat > 45 min at "Preparing to upload 0%"
def test_watchdog_kills_a_silent_command(tmp_path):
    log = tmp_path / "export.log"
    start = time.monotonic()
    rc = rg.watchdog([sys.executable, "-c", "print('Preparing to upload 0%', flush=True);"
                      "import time; time.sleep(60)"], idle_seconds=1.5, log=log, poll=0.2)
    assert rc == 124 and time.monotonic() - start < 20
    assert "Preparing to upload" in log.read_text()


def test_watchdog_passes_through_a_chatty_command():
    rc = rg.watchdog([sys.executable, "-c", "import time\nfor i in range(4):\n print(i, flush=True); "
                      "time.sleep(0.5)\nraise SystemExit(3)"], idle_seconds=2, poll=0.1)
    assert rc == 3


# 5. ASC key evicted to an iCloud dataless placeholder
def test_dataless_key_is_read_once_to_download(tmp_path):
    key = tmp_path / "AuthKey.p8"
    key.write_text("k")
    states = iter([True, False])
    ok, _ = rg.ensure_key(key, dataless=lambda _p: next(states))
    assert ok


def test_key_still_dataless_or_missing_refuses(tmp_path):
    key = tmp_path / "AuthKey.p8"
    key.write_text("k")
    assert not rg.ensure_key(key, dataless=lambda _p: True)[0]
    assert not rg.ensure_key(tmp_path / "none.p8")[0]


# 6. smoke check before publish
def _fake_attach(version, build):
    def attach(cmd):
        mount = Path(cmd[cmd.index("-mountpoint") + 1])
        contents = mount / "Fichero.app" / "Contents"
        contents.mkdir(parents=True)
        (contents / "Info.plist").write_bytes(plistlib.dumps(
            {"CFBundleShortVersionString": version, "CFBundleVersion": build}))
    return attach


def _detach(cmd):
    import shutil
    shutil.rmtree(Path(cmd[2]) / "Fichero.app", ignore_errors=True)


def test_smoke_passes_a_good_dmg(tmp_path):
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    run = Recorder(on={"attach": _fake_attach("2026.11.14", "24"), "detach": _detach})
    assert rg.smoke(dmg, "2026.11.14", "24", run=run) == []
    tools = [c[0] if c[0] != "xcrun" else c[1] for c in run.calls]
    assert tools == ["stapler", "hdiutil", "codesign", "spctl", "hdiutil"]
    assert "-readonly" in run.calls[1]


def test_smoke_refuses_unstapled_or_wrong_stamp(tmp_path):
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    run = Recorder(fail=("stapler", "spctl"), on={"attach": _fake_attach("2026.11.14", "23"),
                                                   "detach": _detach})
    problems = rg.smoke(dmg, "2026.11.14", "24", run=run)
    assert len(problems) == 3
    assert any("stapler" in p for p in problems) and any("Gatekeeper" in p for p in problems)
    assert any("(23), the stamp is 2026.11.14 (24)" in p for p in problems)
    assert run.calls[-1][:2] == ["hdiutil", "detach"]


# 7. notify
def test_notify_is_off_without_a_handle():
    spawned = []
    assert rg.notify("hi", env={}, popen=lambda *a, **k: spawned.append(a)) is False
    assert spawned == []


def test_notify_runs_osascript_in_the_background_with_a_timeout():
    spawned = []
    assert rg.notify("Fichero 2026.11.14 (24): Mac TestFlight FAILED", env={"FICHERO_NOTIFY_IMESSAGE": "owner"},
                     popen=lambda cmd, **kw: spawned.append((cmd, kw)))
    (cmd, kw), = spawned
    script = cmd[2]
    assert cmd[:2] == ["osascript", "-e"] and kw["start_new_session"]
    assert "with timeout of 30 seconds" in script and "as «class utf8»" in script
    assert 'participant "owner"' in script
    path = script.split('read POSIX file "')[1].split('"')[0]
    assert "Mac TestFlight FAILED" in Path(path).read_text(encoding="utf-8")


# 8. summary
def test_summary_one_line_per_part_last_status_wins(tmp_path):
    f = tmp_path / "summary.tsv"
    for name, status, reason in [("DMG", "PENDING", ""), ("Mac TestFlight", "PENDING", ""),
                                 ("iOS TestFlight", "SKIPPED", "--skip-ios-testflight"),
                                 ("Publish", "PENDING", ""), ("DMG", "OK", "both tiers"),
                                 ("Mac TestFlight", "FAILED", "upload stalled\n30 min")]:
        rg.record(f, name, status, reason)
    assert rg.summary_rows(f) == [
        ("DMG", "OK", "both tiers"), ("Mac TestFlight", "FAILED", "upload stalled 30 min"),
        ("iOS TestFlight", "SKIPPED", "--skip-ios-testflight"), ("Publish", "SKIPPED", "not reached")]
    assert len(rg.summary_table(f).splitlines()) == 4


# 9. token-free morning release: the decisions morning-release.sh takes
def test_nothing_new_since_the_last_release_tag_skips():
    def run(cmd, **_kw):
        out = "v2026.11.14\nv2026.11.13\n" if cmd[3] == "tag" else "0\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    assert rg.new_commits("origin/integration", run=run) == (0, "v2026.11.14")


def test_new_commits_are_counted_from_the_newest_tag():
    seen = []

    def run(cmd, **_kw):
        seen.append(cmd)
        out = "v2026.11.14\nv2026.11.13\n" if cmd[3] == "tag" else "7\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
    assert rg.new_commits("origin/integration", run=run) == (7, "v2026.11.14")
    assert seen[1][-1] == "v2026.11.14..origin/integration"


def test_lock_held_by_a_live_run_exits_and_a_dead_ones_lock_is_taken(tmp_path):
    lock = tmp_path / "morning.lock"
    assert rg.acquire_lock(lock, 111, alive=lambda _p: True)
    assert not rg.acquire_lock(lock, 222, alive=lambda pid: pid == 111)  # 111 still running
    assert rg.acquire_lock(lock, 333, alive=lambda _p: False)  # 111 died; take over
    assert lock.read_text() == "333"


def test_failed_smoke_means_no_publish(tmp_path):
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    rows = [("DMG", "OK", ""), ("Mac TestFlight", "FAILED", "stalled")]
    ok, why = rg.may_publish(rows, [dmg], "2026.11.15", "25", smoke_fn=lambda *a: ["not stapled"])
    assert not ok and "not stapled" in why
    ok, _ = rg.may_publish(rows, [dmg], "2026.11.15", "25", smoke_fn=lambda *a: [])
    assert ok  # a failed TestFlight part does not hold the publish back


def test_failed_dmg_part_means_no_publish(tmp_path):
    ok, why = rg.may_publish([("DMG", "FAILED", "stopped (exit 1)")], [tmp_path / "Fichero.dmg"],
                             "v", "1", smoke_fn=lambda *a: [])
    assert not ok and "FAILED" in why
