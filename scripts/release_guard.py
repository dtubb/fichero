#!/usr/bin/env python3
"""Small, testable guards for the unattended release lane (release-all.sh).

Every subcommand is one thing the 2026.11.14 release needed a person for
(spec: docs/contributor_manual/specs/harness/release-and-versioning.md,
"The lane runs unattended"):

    disk STAGE                free space before a heavy stage; thins Time Machine
                              local snapshots once, re-checks, else refuses
    next-build                the build number to stamp: one above both the local
                              stamp and every published build
    check-build N             refuse N unless it is above every published build
    asc-key PATH              the App Store Connect .p8 is downloaded, not an
                              iCloud dataless placeholder
    ios-preflight             fast unsigned iOS compile before the long lane
    watchdog -- CMD...        run CMD, kill it after N idle seconds (exit 124)
    smoke DMG VERSION BUILD   stapled, signed, Gatekeeper-accepted, right stamp
    notify MESSAGE            text the owner via Messages in the background
    part NAME STATUS [REASON] record a lane part's outcome in the summary file
    summary                   print the one-line-per-part table

No subcommand ever deletes DerivedData, DMGs or anything else: the only disk
action is `tmutil thinlocalsnapshots`.
"""

from __future__ import annotations

import argparse
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
XCCONFIG = ROOT / "fichero" / "Configs" / "Version.xcconfig"
FEED_URL = os.environ.get("SPARKLE_FEED_URL", "https://tubb.ca/apps/fichero/appcast.xml")
THIN_CMD = ["tmutil", "thinlocalsnapshots", "/", "40000000000", "4"]
SF_DATALESS = 0x40000000  # <sys/stat.h>: file content lives in iCloud, not on disk
STATUSES = ("OK", "FAILED", "SKIPPED", "PENDING")

Run = subprocess.run


# ── 1. disk ──────────────────────────────────────────────────────────────────
def free_gb(path: str = "/") -> float:
    return shutil.disk_usage(path).free / 1e9


def ensure_disk(stage: str, need_gb: float, *, free=free_gb, run=Run) -> tuple[bool, str]:
    """Free space for STAGE, thinning local snapshots once when short.

    APFS local Time Machine snapshots pin deleted blocks, so a nearly full disk
    often has tens of GB back after a thin. Nothing is deleted here."""
    have = free()
    if have >= need_gb:
        return True, f"  disk OK for {stage}: {have:.1f} GB free (need {need_gb:g})"
    print(f"  disk: {have:.1f} GB free before {stage} (need {need_gb:g}); thinning local snapshots")
    try:
        run(THIN_CMD, check=False, timeout=600, capture_output=True)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  disk: tmutil thinlocalsnapshots did not finish: {exc}")
    have = free()
    if have >= need_gb:
        return True, f"  disk OK for {stage} after thinning: {have:.1f} GB free"
    return False, (
        f"error: {have:.1f} GB free before {stage}; it needs {need_gb:g} GB even after thinning "
        "Time Machine local snapshots. Free space by hand (never DerivedData or old DMGs), "
        "or lower FICHERO_RELEASE_MIN_FREE_GB if you know the stage fits."
    )


# ── 2. build number ──────────────────────────────────────────────────────────
def local_build(xcconfig: Path = XCCONFIG) -> int:
    m = re.search(r"^CURRENT_PROJECT_VERSION = (\d+)\s*$", xcconfig.read_text(), re.M)
    return int(m.group(1)) if m else 0


def published_builds(appcast_xml: str, tag_subjects: list[str]) -> list[int]:
    """Every build number already shipped: the live appcast's sparkle:version
    values and the `(build N)` that create-github-release.sh writes into each
    release tag's annotation."""
    builds = [int(n) for n in re.findall(r"<sparkle:version>\s*(\d+)\s*</sparkle:version>", appcast_xml)]
    for subject in tag_subjects:
        builds += [int(n) for n in re.findall(r"\(build (\d+)\)", subject)]
    return builds


def next_build(local: int, published: list[int]) -> int:
    return max([local, *published]) + 1


def build_problem(build: int, published: list[int]) -> str | None:
    top = max(published, default=0)
    if build > top:
        return None
    return (
        f"error: build number {build} is not above every published build (highest {top}). "
        "Sparkle orders updates by this integer, so users would never be offered this release."
    )


def fetch_feed(url: str = FEED_URL, timeout: float = 15.0) -> str:
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed https feed)
        return resp.read().decode("utf-8")


def tag_subjects(run=Run) -> list[str]:
    run(["git", "-C", str(ROOT), "fetch", "-q", "--tags", "origin"], check=False, timeout=60,
        capture_output=True)
    out = run(["git", "-C", str(ROOT), "for-each-ref", "refs/tags/v*", "--format=%(contents:subject)"],
              check=False, capture_output=True, text=True, timeout=30)
    return out.stdout.splitlines()


def published(feed=fetch_feed, tags=tag_subjects) -> list[int]:
    """Blind is not green: an unreachable feed raises, and the lane refuses."""
    try:
        xml = feed()
    except Exception as exc:  # noqa: BLE001 (any fetch failure means we cannot judge)
        raise RuntimeError(f"error: cannot read the live appcast to judge the build number: {exc}") from exc
    return published_builds(xml, tags())


# ── 5. App Store Connect key ─────────────────────────────────────────────────
def is_dataless(path: Path) -> bool:
    return bool(getattr(os.stat(path), "st_flags", 0) & SF_DATALESS)


def ensure_key(path: Path, *, dataless=is_dataless) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"error: App Store Connect key not found: {path}"
    if dataless(path):
        print(f"  ASC key is an iCloud placeholder (dataless); downloading: {path.name}")
        path.read_bytes()  # reading it makes iCloud download the content
        if dataless(path):
            return False, (f"error: App Store Connect key {path} is still dataless after a read; "
                           "open it in Finder (or check iCloud) and re-run.")
    return True, f"  App Store Connect key on disk: {path.name}"


# ── 3. iOS compile preflight ─────────────────────────────────────────────────
def ios_preflight_cmd(project: str, scheme: str, config: str, tier: str) -> list[str]:
    return ["xcodebuild", "-project", project, "-scheme", scheme, "-configuration", config,
            "-destination", "generic/platform=iOS", "-skipPackagePluginValidation",
            "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", f"FICHERO_FEATURE_TIER={tier}",
            "build"]


def ios_preflight(project: str, scheme: str, config: str, tier: str, *, run=Run) -> tuple[bool, str]:
    proc = run(ios_preflight_cmd(project, scheme, config, tier), check=False,
               capture_output=True, text=True)
    if proc.returncode == 0:
        return True, "  iOS compile preflight OK"
    errors = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ": error:" in ln]
    return False, ("error: the iOS app does not compile, so the iOS TestFlight archive would fail "
                   "hours in. Fix these, or re-run with --skip-ios-testflight:\n  "
                   + "\n  ".join(errors[:20] or ["(no ': error:' lines; run the build by hand)"]))


# ── 4. watchdog ──────────────────────────────────────────────────────────────
def watchdog(cmd: list[str], idle_seconds: float, log: Path | None = None, *, poll: float = 1.0) -> int:
    """Run CMD, echoing its output; kill its process group after IDLE_SECONDS
    with no output. Returns CMD's exit code, or 124 when it was killed."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    out = proc.stdout
    assert out is not None
    last = [time.monotonic()]
    sink = log.open("ab") if log else None

    def pump() -> None:
        for line in iter(out.readline, b""):
            last[0] = time.monotonic()
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
            if sink:
                sink.write(line)
                sink.flush()

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        while proc.poll() is None:
            if time.monotonic() - last[0] > idle_seconds:
                print(f"\nwatchdog: no output for {idle_seconds:g} s; killing {cmd[0]}", file=sys.stderr)
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=20)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                return 124
            time.sleep(poll)
        reader.join(timeout=5)
        return proc.returncode
    finally:
        if sink:
            sink.close()


# ── 6. smoke check before publish ────────────────────────────────────────────
def smoke(dmg: Path, version: str, build: str, *, run=Run) -> list[str]:
    """Problems with DMG; empty means it may be published."""
    def ok(cmd: list[str]) -> bool:
        return run(cmd, check=False, capture_output=True, text=True).returncode == 0

    if not dmg.is_file():
        return [f"{dmg} does not exist"]
    problems = []
    if not ok(["xcrun", "stapler", "validate", str(dmg)]):
        problems.append(f"{dmg.name}: no valid notarization ticket stapled (xcrun stapler validate)")
    mount = Path(tempfile.mkdtemp(prefix="fichero-smoke-"))
    if not ok(["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(dmg)]):
        mount.rmdir()
        return [*problems, f"{dmg.name}: could not be mounted read-only"]
    try:
        apps = sorted(mount.glob("*.app"))
        if not apps:
            return [*problems, f"{dmg.name}: no .app inside"]
        app = apps[0]
        if not ok(["codesign", "--verify", "--deep", "--strict", str(app)]):
            problems.append(f"{app.name}: codesign --verify --deep --strict failed")
        if not ok(["spctl", "-a", "-t", "exec", str(app)]):
            problems.append(f"{app.name}: Gatekeeper (spctl -a) rejects it")
        info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
        got = (str(info.get("CFBundleShortVersionString")), str(info.get("CFBundleVersion")))
        if got != (version, str(build)):
            problems.append(f"{app.name}: carries {got[0]} ({got[1]}), the stamp is {version} ({build})")
    finally:
        run(["hdiutil", "detach", str(mount), "-force"], check=False, capture_output=True)
        try:
            mount.rmdir()
        except OSError:
            pass
    return problems


# ── 7. notify ────────────────────────────────────────────────────────────────
def notify_script(handle: str, message_file: Path) -> str:
    h = handle.replace("\\", "").replace('"', "")
    return (
        "with timeout of 30 seconds\n"
        '  tell application "Messages"\n'
        "    set svc to 1st account whose service type = iMessage\n"
        f'    send (read POSIX file "{message_file}" as «class utf8») to participant "{h}" of svc\n'
        "  end tell\n"
        "end timeout\n"
    )


def notify(message: str, *, env=os.environ, popen=subprocess.Popen) -> bool:
    """Text the owner in the background; never blocks, never fails the lane.
    The handle comes only from FICHERO_NOTIFY_IMESSAGE (unset = no text)."""
    handle = env.get("FICHERO_NOTIFY_IMESSAGE", "").strip()
    if not handle:
        return False
    fd, name = tempfile.mkstemp(prefix="fichero-notify-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(message)
    popen(["osascript", "-e", notify_script(handle, Path(name))], stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, start_new_session=True)
    return True


# ── 8. summary ───────────────────────────────────────────────────────────────
def record(summary: Path, name: str, status: str, reason: str = "") -> None:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with summary.open("a", encoding="utf-8") as fh:
        fh.write(f"{name}\t{status}\t{' '.join(reason.split())}\n")


def summary_rows(summary: Path) -> list[tuple[str, str, str]]:
    """Last record per part wins, in first-seen order; PENDING was never reached."""
    rows: dict[str, tuple[str, str]] = {}
    if summary.exists():
        for line in summary.read_text(encoding="utf-8").splitlines():
            name, status, reason = (line.split("\t") + ["", ""])[:3]
            rows[name] = (status, reason)
    return [(n, "SKIPPED", "not reached") if s == "PENDING" else (n, s, r) for n, (s, r) in rows.items()]


def summary_table(summary: Path) -> str:
    rows = summary_rows(summary)
    width = max([len(n) for n, _, _ in rows] + [4])
    return "\n".join(f"{n:<{width}}  {s:<7}  {r}".rstrip() for n, s, r in rows)


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("disk")
    d.add_argument("stage")
    d.add_argument("--need-gb", type=float, default=float(os.environ.get("FICHERO_RELEASE_MIN_FREE_GB", "20")))
    sub.add_parser("next-build").add_argument("--xcconfig", type=Path, default=XCCONFIG)
    sub.add_parser("check-build").add_argument("build", type=int)
    sub.add_parser("asc-key").add_argument("path", type=Path)
    i = sub.add_parser("ios-preflight")
    for a in ("project", "scheme", "config", "tier"):
        i.add_argument(a)
    w = sub.add_parser("watchdog")
    w.add_argument("--idle-seconds", type=float,
                   default=60 * float(os.environ.get("FICHERO_UPLOAD_IDLE_MINUTES", "30")))
    w.add_argument("--log", type=Path)
    w.add_argument("command", nargs=argparse.REMAINDER)
    s = sub.add_parser("smoke")
    s.add_argument("dmg", type=Path)
    s.add_argument("version")
    s.add_argument("build")
    sub.add_parser("notify").add_argument("message")
    pt = sub.add_parser("part")
    pt.add_argument("name")
    pt.add_argument("status", choices=STATUSES)
    pt.add_argument("reason", nargs="?", default="")
    sub.add_parser("summary")
    a = p.parse_args(argv)
    summary_file = Path(os.environ.get("FICHERO_RELEASE_SUMMARY", ROOT / "build" / "releases" / "summary.tsv"))

    if a.cmd == "disk":
        ok, msg = ensure_disk(a.stage, a.need_gb)
    elif a.cmd in ("next-build", "check-build"):
        try:
            pub = published()
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
        if a.cmd == "next-build":
            print(next_build(local_build(a.xcconfig), pub))
            return 0
        problem = build_problem(a.build, pub)
        ok, msg = problem is None, problem or f"  build {a.build} is above every published build"
    elif a.cmd == "asc-key":
        ok, msg = ensure_key(a.path)
    elif a.cmd == "ios-preflight":
        ok, msg = ios_preflight(a.project, a.scheme, a.config, a.tier)
    elif a.cmd == "watchdog":
        cmd = a.command[1:] if a.command[:1] == ["--"] else a.command
        return watchdog(cmd, a.idle_seconds, a.log)
    elif a.cmd == "smoke":
        problems = smoke(a.dmg, a.version, a.build)
        ok = not problems
        msg = f"  smoke OK: {a.dmg.name}" if ok else "error: refusing to publish:\n  " + "\n  ".join(problems)
    elif a.cmd == "notify":
        notify(a.message)
        return 0
    elif a.cmd == "part":
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        record(summary_file, a.name, a.status, a.reason)
        return 0
    else:
        print(summary_table(summary_file))
        return 0
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
