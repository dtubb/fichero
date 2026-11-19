"""scripts/release_guard.py: each test reproduces one thing the 2026.11.14
release needed a person for (docs/contributor_manual/specs/harness/release-and-versioning.md,
"The lane runs unattended"). No Apple, network, Messages or tmutil call is real here."""

from __future__ import annotations

import importlib.util
import os
import plistlib
import re
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
def _fake_attach(version, build, engine_stamp="same"):
    """A mounted Fichero.app; its engine carries the app's own stamp unless `engine_stamp` says otherwise (None: none)."""
    def attach(cmd):
        mount = Path(cmd[cmd.index("-mountpoint") + 1])
        contents = mount / "Fichero.app" / "Contents"
        contents.mkdir(parents=True)
        stamp = f"{version} {build}\n" if engine_stamp == "same" else engine_stamp
        if stamp is not None:
            pkg = contents / "Resources" / "Fichero Server.app" / "Contents" / "Resources" / "app" / "fichero_server"
            pkg.mkdir(parents=True)
            (pkg / "release-stamp.txt").write_text(stamp)
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


def test_smoke_refuses_an_engine_stamped_for_another_release(tmp_path):
    """#6723: a release whose engine would report a version other than the app's is not published."""
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    run = Recorder(on={"attach": _fake_attach("2026.11.18", "29", engine_stamp="2026.11.17 28\n"), "detach": _detach})
    problems = rg.smoke(dmg, "2026.11.18", "29", run=run)
    assert len(problems) == 1 and "engine is stamped 2026.11.17 (28)" in problems[0] and "2026.11.18 (29)" in problems[0]


def test_smoke_refuses_an_engine_with_no_stamp(tmp_path):
    dmg = tmp_path / "Fichero.dmg"
    dmg.write_bytes(b"x")
    run = Recorder(on={"attach": _fake_attach("2026.11.18", "29", engine_stamp=None), "detach": _detach})
    problems = rg.smoke(dmg, "2026.11.18", "29", run=run)
    assert len(problems) == 1 and "no release stamp" in problems[0]


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


def test_a_publish_that_exits_zero_is_publish_ok_and_a_failed_one_is_failed(tmp_path):
    # review: publish-release.sh writes no summary row; the old hand-off waited for one and
    # recorded every publish as FAILED, so no PR was ever opened
    f = tmp_path / "summary.tsv"
    seen = []

    def run(cmd, cwd=None, **_kw):
        seen.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0 if seen[1:] == [] else 1)
    assert rg.publish(["scripts/publish-release.sh"], tmp_path, f, "Fichero 2026.11.15 (25)", run=run)
    assert rg.summary_rows(f) == [("Publish", "OK", "published Fichero 2026.11.15 (25)")]
    assert seen[0] == (["scripts/publish-release.sh"], str(tmp_path))
    assert not rg.publish(["scripts/publish-release.sh"], tmp_path, f, "x", run=run)
    assert rg.summary_rows(f)[0][:2] == ("Publish", "FAILED")


def test_the_publish_command_line_records_the_part_in_the_summary_it_is_given(tmp_path):
    f = tmp_path / "out" / "summary.tsv"
    script = tmp_path / "publish.sh"
    script.write_text("#!/bin/sh\nexit 3\n")
    script.chmod(0o755)
    env_before = rg.os.environ.get("FICHERO_RELEASE_SUMMARY")
    rg.os.environ["FICHERO_RELEASE_SUMMARY"] = str(f)
    try:
        assert rg.main(["publish", str(tmp_path), "label", str(script)]) == 1
    finally:
        if env_before is None:
            del rg.os.environ["FICHERO_RELEASE_SUMMARY"]
        else:
            rg.os.environ["FICHERO_RELEASE_SUMMARY"] = env_before
    assert rg.summary_rows(f)[0][:2] == ("Publish", "FAILED")


def test_morning_release_stops_and_texts_when_the_commits_cannot_be_counted(tmp_path):
    # review: `read < <(guard new-commits)` dropped the guard's failure, so a -1 count went on
    # to cut and publish. The real script runs here against a stub guard and a stub git.
    import os
    import shutil
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    for name in ("morning-release.sh", "find_project_python.sh"):
        shutil.copy(_SCRIPT.parent / name, root / "scripts" / name)
    venv = root / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(sys.executable)
    calls = tmp_path / "calls.txt"
    (venv / "git").write_text(f"#!/bin/sh\necho git \"$@\" >> '{calls}'\nexit 0\n")
    (venv / "git").chmod(0o755)
    (root / "scripts" / "release_guard.py").write_text(
        "import sys\n"
        f"open({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'new-commits':\n    print('-1 '); sys.exit(1)\n")
    rc = subprocess.run(["bash", str(root / "scripts" / "morning-release.sh")],
                        env={"HOME": str(tmp_path), "PATH": os.environ["PATH"]}, timeout=60).returncode
    log = calls.read_text()
    assert rc == 1
    assert "notify Fichero morning release: cannot count commits" in log
    assert "worktree" not in log and "publish" not in log


# 8. release defaults (#6590)
_ROOT = _SCRIPT.parents[1]


def test_disk_floor_default_is_15_gb(monkeypatch):
    monkeypatch.delenv("FICHERO_RELEASE_MIN_FREE_GB", raising=False)
    seen = []
    monkeypatch.setattr(rg, "ensure_disk", lambda stage, need, **_k: seen.append(need) or (True, "ok"))
    assert rg.main(["disk", "the engine build"]) == 0
    assert seen == [15.0]


NOTES = "# Release Notes\n\nintro\n\n## 2026.11.12\nOld.\n"
LOG = "# Changelog\n\n## 2026-11-12\n\n- old\n"


def test_missing_sections_are_written_from_commit_subjects():
    subjects = ["feat(segment-editor): two short switches", "spec(release): a spec line",
                "fix: a crash on launch", "Plain subject"]
    notes, log = rg.auto_notes("2026.11.15", NOTES, LOG, subjects, "2026.11.12")
    assert notes.index("## 2026.11.15") < notes.index("## 2026.11.12")
    assert "What changed since 2026.11.12." in notes
    assert "- Segment editor: two short switches" in notes
    assert "- a crash on launch" in notes and "- Plain subject" in notes
    assert "spec line" not in notes
    assert log.index("## 2026-11-15") < log.index("## 2026-11-12")
    # the generated docs satisfy the release-docs gate
    spec = importlib.util.spec_from_file_location("crd", _ROOT / "scripts" / "check_release_docs_ready.py")
    crd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crd)
    assert crd.docs_ready("2026.11.15", notes, log) == []


def test_hand_written_sections_are_never_touched():
    notes = "# Release Notes\n\n## 2026.11.15\nMine.\n\n" + NOTES.split("\n\n", 2)[2]
    log = "# Changelog\n\n## 2026-11-15\n\n- mine\n"
    assert rg.auto_notes("2026.11.15", notes, log, ["feat: x"], "2026.11.12") == (notes, log)


def test_no_user_facing_commits_still_gives_a_nonempty_section():
    notes, _ = rg.auto_notes("2026.11.15", NOTES, LOG, ["spec: only a spec"], "2026.11.12")
    assert "Maintenance release" in notes


def test_publish_is_verified_against_the_live_appcast():
    naps = []
    answers = iter([False, False, True])
    ok, _ = rg.wait_for_appcast(25, 10, has=lambda _b: next(answers), sleep=naps.append)
    assert ok and len(naps) == 2
    ok, msg = rg.wait_for_appcast(25, 1, has=lambda _b: False, sleep=lambda _s: None)
    assert not ok and "not in the live appcast" in msg
    assert rg.appcast_has_build(25, feed=lambda: FEED.replace("23", "25"))
    assert not rg.appcast_has_build(25, feed=lambda: (_ for _ in ()).throw(OSError("down")))


def test_queue_runs_two_workers():
    import tomllib
    cfg = tomllib.loads((_ROOT / "harness.toml").read_text())
    assert cfg["queue"]["workers"] == 2


def _script(name):
    return (_ROOT / "scripts" / name).read_text()


def test_morning_release_builds_the_dev_dmg_only_and_publishes_before_testflight():
    m = _script("morning-release.sh")
    assert "--skip-testflight ${FICHERO_MORNING_ARGS---dev}" in m
    assert "Fichero-dev.dmg" not in m
    assert m.index("publish-release.sh") < m.index("--skip-dmg --skip-notarize")


def test_release_all_names_a_single_tier_dmg_fichero_dmg_and_publishes_before_testflight():
    r = _script("release-all.sh")
    assert 'case "$DMG_TIER:${#DMG_TIERS[@]}" in\n      dev:2) TIER_DMG_PATH="$DEV_DMG_PATH"' in r
    assert r.index('run_part Publish publish_part') < r.index('run_part "Mac TestFlight" mac_testflight')
    assert r.index('guard auto-notes') < r.index('check_release_docs_ready.py')
    assert "verify-appcast" in r


def test_deploy_site_triggers_a_netlify_build():
    d = _script("deploy-site.sh")
    assert 'curl' in d and 'FICHERO_NETLIFY_BUILD_HOOK' in d


def test_the_daily_dev_dmg_is_published_on_the_dev_channel_only():
    c = _script("create-github-release.sh")
    assert 'FICHERO_RELEASE_CHANNEL:-}" = "dev"' in c
    assert "MAIN_ITEM_ARGS=(--channel dev)" in c and "HAVE_DEV_DMG=false" in c
    assert '--ed-signature "$ED_SIGNATURE" \\\n    ${MAIN_ITEM_ARGS[@]+"${MAIN_ITEM_ARGS[@]}"}' in c
    assert 'export FICHERO_RELEASE_CHANNEL="${FICHERO_MORNING_CHANNEL-dev}"' in _script("morning-release.sh")
    assert "export FICHERO_RELEASE_CHANNEL=dev" in _script("release-all.sh")


def test_the_dev_channel_follows_the_built_artifact_not_the_publish_flags():
    ra, c = _script("release-all.sh"), _script("create-github-release.sh")
    assert '> "$TIER_DMG_PATH.tier"' in ra and 'rm -f "$DMG_PATH.tier"' in ra
    assert '"$DMG_PATH.tier"' in c and "export FICHERO_RELEASE_CHANNEL=dev" in c
    # the stray dev DMG is dropped before the first upload_asset call, not after
    assert c.index('HAVE_DEV_DMG=false; fi') < c.index('upload_asset "$DMG_PATH"')


def test_spec_ids_in_release_and_versioning_are_unique():
    import collections
    text = (_ROOT / "docs/contributor_manual/specs/harness/release-and-versioning.md").read_text()
    ids = [m for m in re.findall(r"^- `(release\.[\w.\-]+)` —", text, re.M)]
    assert [i for i, n in collections.Counter(ids).items() if n > 1] == []


def test_docs_download_links_name_fichero_dmg_and_the_one_dmg_text_calls_it_the_dev_build():
    # Only the dev build is posted, as Fichero-dev.dmg (owner 2026-11-18, release-channels-and-feature-tiers): the site links name it.
    for md in list((_ROOT / "docs").glob("*.md")) + [_ROOT / "README.md"]:
        assert "releases/latest/download/Fichero.dmg" not in md.read_text(), md.name
    c = _script("create-github-release.sh")
    assert 'DOWNLOAD_LINE="Download \\`$ASSET_NAME\\` below (the dev build, with every feature on' in c
    assert c.index("DOWNLOAD_LINE=") < c.index('RELEASE_BODY="## Installation')
    assert "still runs it last" not in (_ROOT / "docs/contributor_manual/specs/harness/release-and-versioning.md").read_text()


def test_release_all_builds_only_the_dev_dmg_and_public_only_changes_how_it_is_published():
    """release-channels-and-feature-tiers (owner 2026-11-17): one dev DMG is built; no flag publishes it as a dev-channel
    pre-release with no site; --public publishes the same DMG as the public item (Latest, appcast, site)."""
    r, c, p = _script("release-all.sh"), _script("create-github-release.sh"), _script("publish-release.sh")
    tiers = r[r.index("# DMG tiers for this run"):]
    tiers = tiers[:tiers.index("\nfi\n")]
    assert "DMG_TIERS=(dev alpha)" not in r and "DMG_TIERS=(dev)\n  FICHERO_RELEASE_TIER=dev" in tiers
    assert "--public) PUBLIC_RELEASE=true ;;" in r
    publish = r[r.index("publish_part() {"):]
    public, dev = publish.split("  else\n", 1)
    assert "export FICHERO_RELEASE_PUBLIC=1" in public and "unset FICHERO_RELEASE_CHANNEL" in public
    assert "export FICHERO_RELEASE_CHANNEL=dev FICHERO_SKIP_SITE=1" in dev and 'GITHUB_ARGS+=("--prerelease")' in dev
    assert '"${FICHERO_RELEASE_PUBLIC:-0}" != 1 ] && [ -f "$DMG_PATH.tier" ]' in c, "a public run keeps the dev DMG public"
    assert "--github \"$@\"" in p, "publish-release.sh passes --public on"


def _public_download_line(script: str, have_dev_dmg: str, public: str, channel: str = "") -> tuple[str, str]:
    """Run create-github-release.sh's clear-the-dev-DMG line and its DOWNLOAD_LINE choice in bash; return both results."""
    clear = next(ln for ln in script.splitlines() if ln.endswith("HAVE_DEV_DMG=false; fi") and "FICHERO_RELEASE_CHANNEL" in ln)
    start = script.index('if [ "$HAVE_DEV_DMG" != true ]; then')
    asset = script.index('ASSET_NAME="Fichero.dmg"')
    name = script[asset:script.index("\nfi\n", asset) + 4]  # the posted name: Fichero-dev.dmg for the dev build
    pick = script[start:script.index('RELEASE_BODY="## Installation')]
    code = f'{clear}\n{name}\n{pick}\necho "$HAVE_DEV_DMG"; echo "$DOWNLOAD_LINE"'
    done = subprocess.run(["bash", "-c", code], capture_output=True, text=True, timeout=30, check=True,
                          env={"PATH": os.environ["PATH"], "HAVE_DEV_DMG": have_dev_dmg, "FICHERO_RELEASE_PUBLIC": public,
                               "FICHERO_RELEASE_CHANNEL": channel})
    have, line = done.stdout.strip().split("\n", 1)
    return have, line


def test_a_public_release_body_names_only_the_attached_dmg_and_ignores_a_stale_dev_dmg_6665():
    c = _script("create-github-release.sh")
    have, line = _public_download_line(c, "true", "1")  # a stale Fichero-dev.dmg is still on disk
    assert have == "false" and "`Fichero-dev.dmg`" in line and "`Fichero.dmg`" not in line
    have, line = _public_download_line(c, "true", "0")  # the two-DMG hand run still names both
    assert have == "true" and "Fichero-dev.dmg" in line
