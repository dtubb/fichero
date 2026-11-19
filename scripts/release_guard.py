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
    auto-notes VERSION        write RELEASE_NOTES.md / CHANGELOG.md sections from commit
                              the record (issues, milestones, specs) when none are hand-written
    verify-appcast BUILD      wait for BUILD in the live appcast (publish is not done before)

  morning release (scripts/morning-release.sh):
    lock PATH PID             take the run lock; exit 1 while a live run holds it
    new-commits REF           commits on REF since the newest v* release tag
    may-publish VERSION BUILD DMG...
                              publish only if the DMG part is OK and every DMG smokes

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
        stamp = (app / "Contents" / "Resources" / "Fichero Server.app" / "Contents" / "Resources" / "app"
                 / "fichero_server" / "release-stamp.txt")
        if not stamp.is_file():
            problems.append(f"{app.name}: its engine has no release stamp (#6723), so it would report the contract version")
        else:
            engine = tuple(stamp.read_text().split())
            if engine != got:
                problems.append(f"{app.name}: its engine is stamped {' ('.join(engine)}"
                                f"{')' if len(engine) > 1 else ''}, the app is {got[0]} ({got[1]})")
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


# ── 9. morning release ───────────────────────────────────────────────────────
def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(path: Path, pid: int, *, alive=pid_alive) -> bool:
    """One morning run at a time. A lock left by a dead run is taken over."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = int(path.read_text().strip() or 0)
        except (OSError, ValueError):
            holder = 0
        if holder and alive(holder):
            return False
        path.unlink(missing_ok=True)
        return acquire_lock(path, pid, alive=lambda _p: True)
    with os.fdopen(fd, "w") as fh:
        fh.write(str(pid))
    return True


def new_commits(ref: str, *, run=Run) -> tuple[int, str]:
    """(commits on REF since the newest release tag, that tag)."""
    tags = run(["git", "-C", str(ROOT), "tag", "-l", "v*", "--sort=-creatordate"],
               check=False, capture_output=True, text=True).stdout.split()
    if not tags:
        return -1, ""
    out = run(["git", "-C", str(ROOT), "rev-list", "--count", f"{tags[0]}..{ref}"],
              check=False, capture_output=True, text=True)
    return (int(out.stdout.strip()) if out.returncode == 0 else -1), tags[0]


def may_publish(rows: list[tuple[str, str, str]], dmgs: list[Path], version: str, build: str,
                *, smoke_fn=smoke) -> tuple[bool, str]:
    """The morning run publishes only a DMG that built and smokes clean;
    a failed TestFlight part does not stop the publish."""
    dmg = next((r for r in rows if r[0] == "DMG"), None)
    if dmg is None or dmg[1] != "OK":
        return False, f"DMG part {dmg[1] if dmg else 'missing'}: {dmg[2] if dmg else ''}".rstrip(": ")
    problems = [p for d in dmgs if d.exists() or d.name == "Fichero.dmg" for p in smoke_fn(d, version, build)]
    if problems:
        return False, "smoke failed: " + "; ".join(problems)
    return True, "DMG built and smoke clean"


def publish(cmd: list[str], cwd: Path, summary: Path, label: str, *, run=Run) -> bool:
    """Run publish-release.sh and record the Publish part from its exit status
    (it writes no summary row of its own; set -e makes the status the verdict)."""
    ok = run(cmd, cwd=str(cwd), check=False).returncode == 0
    record(summary, "Publish", "OK" if ok else "FAILED",
           f"published {label}" if ok else "publish-release.sh stopped; see the log")
    return ok


# ── release defaults (#6590) ─────────────────────────────────────────────────
def _has_section(text: str, heading: str) -> bool:
    return re.search(rf"^##[ \t]+{re.escape(heading)}[ \t]*$", text, re.MULTILINE) is not None


_SPEC_TYPES = ("spec", "test", "chore", "ci", "docs", "style")
_GH_QUERY = ("query($owner:String!,$name:String!){repository(owner:$owner,name:$name){%s}}")
_GH_ISSUE = "i%d:issue(number:%d){title state milestone{title} labels(first:30){nodes{name}}}"
ISSUE_CACHE_MAX = 500
ISSUE_CACHE = ROOT / "build" / "releases" / "issue-cache.json"
BUILD_ORDER = ROOT / "docs" / "contributor_manual" / "specs" / "build-order.md"
SPECS_DIR = "docs/contributor_manual/specs"


def read_issues(numbers: list[int], *, run=Run, cache_file: Path = ISSUE_CACHE
                ) -> dict[int, dict] | None:
    """{number: {title, state, milestone, labels}} through GitHub's CLI, one batched query for
    the numbers not cached (closed issues are cached by number). None when GitHub cannot be
    read; the notes then say so and the release goes on."""
    import json
    try:
        cached = {int(k): v for k, v in json.loads(cache_file.read_text()).items()}
    except (OSError, ValueError):
        cached = {}
    found = {n: cached[n] for n in numbers if n in cached}
    todo = [n for n in numbers if n not in found]
    if todo:
        query = _GH_QUERY % " ".join(_GH_ISSUE % (n, n) for n in todo)
        try:
            out = run(["gh", "api", "graphql", "-F", "owner={owner}", "-F", "name={repo}",
                       "-f", f"query={query}"], capture_output=True, text=True, check=False, timeout=60)
            # gh exits 1 when the reply carries `errors` (a cited number that is a PR or does not
            # exist comes back null beside them), so the reply is read whatever the exit code.
            repo = json.loads(out.stdout)["data"]["repository"]
            if not isinstance(repo, dict):
                return None
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            return None
        for n in todo:
            raw = repo.get(f"i{n}")
            if raw is None:  # a number that is not an issue (a PR, a typo): nothing to say about it
                continue
            found[n] = {"title": raw["title"], "state": raw["state"].lower(),
                        "milestone": (raw["milestone"] or {}).get("title"),
                        "labels": [x["name"] for x in raw["labels"]["nodes"]]}
        closed = {n: v for n, v in {**cached, **found}.items() if v["state"] == "closed"}
        closed = dict(sorted(closed.items())[-ISSUE_CACHE_MAX:])  # the newest numbers; the cache cannot grow without bound
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(closed))
        except OSError:
            pass  # the cache is only a speedup
    return found


def milestone_order(text: str) -> list[str]:
    """Milestone names from build-order.md's numbered list, top to bottom."""
    return re.findall(r"^\d+\.\s+`([^`]+)`", text, re.MULTILINE)


def commit_range(run=Run) -> tuple[list[dict], str, list[str]]:
    """(commits on HEAD since the newest v* tag, newest first, each {subject, body}; that tag
    without its v; the spec files changed in the range)."""
    git = ["git", "-C", str(ROOT)]
    tags = run(git + ["tag", "-l", "v*", "--sort=-creatordate"],
               check=False, capture_output=True, text=True).stdout.split()
    rng = f"{tags[0]}..HEAD" if tags else "HEAD"
    out = run(git + ["log", "--no-merges", "--format=%s%x1f%b%x1e", rng],
              check=False, capture_output=True, text=True).stdout
    commits = []
    for rec in out.split("\x1e"):
        if rec.strip():
            subject, _, body = rec.strip("\n").partition("\x1f")
            commits.append({"subject": subject, "body": body})
    specs: list[str] = []
    if tags:
        names = run(git + ["diff", "--name-only", rng.replace("..", "..."), "--", SPECS_DIR],
                    check=False, capture_output=True, text=True).stdout.split()
        specs = [n for n in names if n.endswith(".md")]
    return commits, (tags[0][1:] if tags else ""), specs


def _trailers(commit: dict, key: str) -> list[str]:
    return [m.strip() for m in re.findall(rf"^{key}:[ \t]*(.+)$", commit["body"], re.MULTILINE)]


def _commit_line(subject: str) -> str | None:
    m = re.match(r"^(\w+)(?:\(([^)]*)\))?!?:\s*(.+)$", subject)
    if not m:
        return "- " + subject.strip()[:240]
    kind, scope, text = m.groups()
    if kind in _SPEC_TYPES:
        return None  # not user-facing
    label = scope.replace("-", " ") + ": " if scope else ""
    return f"- {kind}: {label}{text.strip()[:240]}"


def build_notes(commits: list[dict], issues: dict[int, dict] | None, specs: list[tuple[str, str]],
                order: list[str]) -> str:
    """The body of a release's notes, from the record: milestones with their issues, other
    changes, specs, a "What's new" on top and a "Test this" list. specs is [(path, text)] of
    the spec files changed in the range; issues None means GitHub could not be read."""
    refs: dict[int, int] = {}      # issue -> commits citing it
    plain: list[str] = []          # commits with no issue
    for c in commits:
        nums = sorted({int(n) for n in re.findall(r"#(\d+)", c["subject"] + "\n" + c["body"])})
        for n in nums:
            refs[n] = refs.get(n, 0) + 1
        if not nums or issues is None:
            if (line := _commit_line(c["subject"])) and line not in plain:
                plain.append(line)
    sections: dict[str, list[int]] = {}
    unread: list[int] = []
    for n in sorted(refs):
        if issues is None or n not in issues:
            unread.append(n)
        else:
            sections.setdefault(issues[n]["milestone"] or "No milestone", []).append(n)
    weight = {m: sum(refs[n] for n in ns) for m, ns in sections.items()}
    names = sorted(sections, key=lambda m: (order.index(m) if m in order else len(order), -weight[m], m))
    closed = {m: sum(issues[n]["state"] == "closed" for n in sections[m]) for m in sections}  # type: ignore[index]

    out: list[str] = []
    top = [m for m in sorted(sections, key=lambda m: (-closed[m], names.index(m))) if closed[m]][:5]
    if top:
        out += ["### What's new", ""] + [
            f"- {m}: {closed[m]} {'thing' if closed[m] == 1 else 'things'} finished." for m in top] + [""]
    elif issues is None:
        out += ["### What's new", "", "- The issues could not be read from GitHub; the changes are listed below.", ""]
    for m in names:
        out += [f"### {m}", ""] + [
            f"- {issues[n]['title']} (#{n}), {'closed' if issues[n]['state'] == 'closed' else 'in progress'}"  # type: ignore[index]
            for n in sections[m]] + [""]
    if unread:
        out += ["### Issues not read", "",
                "GitHub could not be read, so these are only numbers: " + ", ".join(f"#{n}" for n in unread) + ".", ""]
    if plain:
        out += ["### Other changes", ""] + plain + [""]
    ids = [i for c in commits for i in _trailers(c, "Behaviour")]
    changes = [t for c in commits for t in _trailers(c, "Spec-change") if t.lower() != "none"]
    spec_lines = []
    for path, text in specs:
        done = [i for i in dict.fromkeys(ids)
                if re.search(rf"`{re.escape(i)}`[^\n]*\[OK\]", text)]
        spec_lines.append(f"- {path}" + (f": now working: {', '.join(done)}" if done else ""))
    if spec_lines or changes:
        out += ["### Specs", ""] + spec_lines + [f"- Spec change: {t}" for t in dict.fromkeys(changes)] + [""]
    test = [n for n in sorted(refs) if issues and n in issues and issues[n]["state"] == "closed"
            and "needs-your-test" in issues[n]["labels"]]
    if test:
        out += ["### Test this", ""] + [f"- {issues[n]['title']} (#{n})" for n in test] + [""]  # type: ignore[index]
    return "\n".join(out).strip("\n") + "\n" if out else "- Maintenance release: no user-facing changes.\n"


def changelog_day(version: str) -> str:
    return "-".join(version.split("-")[0].split(".")[:3])


def auto_notes(version: str, notes: str, changelog: str, body: str, prev: str) -> tuple[str, str]:
    """Add the version's section to the notes and the day's to the changelog when absent.
    A section that exists (hand-written) is returned untouched."""
    day = changelog_day(version)

    def put(text: str, heading: str, intro: str) -> str:
        if _has_section(text, heading):
            return text
        block = f"## {heading}\n{intro}{body}\n"
        m = re.search(r"^## ", text, re.MULTILINE)
        return text[: m.start()] + block + text[m.start():] if m else text.rstrip("\n") + "\n\n" + block

    since = f"What changed since {prev}.\n\n" if prev else ""
    return put(notes, version, since), put(changelog, day, "\n")


def appcast_has_build(build: int, *, feed=fetch_feed) -> bool:
    try:
        return build in published_builds(feed(), [])
    except Exception:  # noqa: BLE001 (an unreadable feed is not proof)
        return False


def wait_for_appcast(build: int, minutes: float, *, has=appcast_has_build, sleep=time.sleep,
                     interval: float = 30.0) -> tuple[bool, str]:
    tries = max(1, int(minutes * 60 / interval))
    for attempt in range(tries):
        if has(build):
            return True, f"  live appcast carries build {build}"
        if attempt + 1 < tries:
            sleep(interval)
    return False, f"error: build {build} is not in the live appcast at {FEED_URL} after {minutes:g} minutes"


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("disk")
    d.add_argument("stage")
    d.add_argument("--need-gb", type=float, default=float(os.environ.get("FICHERO_RELEASE_MIN_FREE_GB", "15")))
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
    lk = sub.add_parser("lock")
    lk.add_argument("path", type=Path)
    lk.add_argument("pid", type=int)
    sub.add_parser("new-commits").add_argument("ref")
    pb = sub.add_parser("publish")
    pb.add_argument("cwd", type=Path)
    pb.add_argument("label")
    pb.add_argument("command", nargs=argparse.REMAINDER)
    mp = sub.add_parser("may-publish")
    mp.add_argument("version")
    mp.add_argument("build")
    mp.add_argument("dmgs", type=Path, nargs="+")
    sub.add_parser("auto-notes").add_argument("version")
    va = sub.add_parser("verify-appcast")
    va.add_argument("build", type=int)
    va.add_argument("--minutes", type=float, default=float(os.environ.get("FICHERO_APPCAST_WAIT_MINUTES", "10")))
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
    elif a.cmd == "lock":
        ok = acquire_lock(a.path, a.pid)
        msg = "  lock taken" if ok else f"another morning release holds {a.path}; exiting"
    elif a.cmd == "new-commits":
        count, tag = new_commits(a.ref)
        print(f"{count} {tag}")
        return 0 if count >= 0 else 1
    elif a.cmd == "publish":
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        return 0 if publish(a.command, a.cwd, summary_file, a.label) else 1


    elif a.cmd == "auto-notes":
        rn, cl = ROOT / "RELEASE_NOTES.md", ROOT / "CHANGELOG.md"
        commits, prev, spec_paths = commit_range()
        have = (_has_section(rn.read_text(), a.version)
                and _has_section(cl.read_text(), changelog_day(a.version)))
        if not have:
            nums = sorted({int(n) for c in commits for n in re.findall(r"#(\d+)", c["subject"] + "\n" + c["body"])})
            issues = read_issues(nums) if nums else {}
            if issues is None:
                print("  issues not read: GitHub was not reachable", file=sys.stderr)
            specs = [(p, (ROOT / p).read_text()) for p in spec_paths if (ROOT / p).exists()]
            order = milestone_order(BUILD_ORDER.read_text()) if BUILD_ORDER.exists() else []
            body = build_notes(commits, issues, specs, order)
        else:
            body = ""
        for path, new in zip((rn, cl), auto_notes(a.version, rn.read_text(), cl.read_text(), body, prev)):
            if new != path.read_text():
                path.write_text(new)
                print(f"  wrote an auto-generated section into {path.name}")
        return 0
    elif a.cmd == "verify-appcast":
        ok, msg = wait_for_appcast(a.build, a.minutes)
    elif a.cmd == "may-publish":
        ok, msg = may_publish(summary_rows(summary_file), a.dmgs, a.version, a.build)
    else:
        print(summary_table(summary_file))
        return 0
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
