#!/usr/bin/env python3
"""Sparkle update pre-publish readiness guardrail (#4901).

The maintainer's last update was SEEN by Sparkle and FAILED to install. The
read-only review (`agent-work/spec-pipeline/sparkle-update-review-2026-09-19.md`)
found two confirmed, independent defects in the pipeline's own history: the
public appcast twelve days stale, and two historical releases sharing one
`sparkle:version` build number. Every check here cites a behavior in
`docs/contributor_manual/specs/harness/release-and-versioning.md`'s "Updates
reach the user and install" section, all under #4901:

    release.update.feed-is-current
    release.update.build-number-strictly-increases
    release.update.signature-made-after-stapling
    release.update.an-update-is-proven-to-install-before-publishing

This script is the "nearest automatable proxy" that section proposes. It
CANNOT prove an update installs (that needs a real, disposable macOS
install) — it rules out every cause the review found live evidence for:
a stale/non-monotonic feed, an enclosure that doesn't match the artifact
about to ship, a feed-URL drift, and (report-only) a not-yet-stapled DMG.

NOT WIRED into any release script yet — this is the guardrail itself, for
review. Proposed insertion point: `scripts/create-github-release.sh`, right
after its "Read version + sizes from built app" block (the point every input
this script needs — VERSION, BUILD, DMG_PATH, DMG_SIZE, the built app's own
Info.plist — already exists as shell variables) and BEFORE "[1/5]
Sparkle-sign", so a stale/colliding feed or a size mismatch is caught before
spending a signature on an artifact that shouldn't ship. It would need the
about-to-be-written appcast `<item>` fragment, which today is only built
later, inside the Python heredoc under "[3/5] Update appcast.xml" — wiring
this in for real means either hoisting that item-building code earlier, or
passing this script the same VERSION/BUILD/DMG_SIZE values directly via
--expect-build/--expect-short-version (enclosure length is always the DMG's
own byte size, so --entry-xml is optional and can be added once the item is
built earlier).

Like the other `scripts/check_*.py` guardrails, `verify_all.sh --fast` sweeps
this file with NO arguments. Arming requires --app AND --dmg EXPLICITLY --
with no args it prints NOT ARMED and exits 0 UNCONDITIONALLY, with no
filesystem probe and no network call, even if a real build happens to be
sitting under build/releases/ at that moment (another lane's in-flight
release work, a stale artifact) — a normal dev gate run must never depend
on the network or on what another lane's worktree happens to hold.

Only what can stop THIS update from installing fails the check: the new
build already present in the live feed, the new build not strictly greater
than the feed's current maximum, a feed-URL mismatch, an enclosure
mismatch, or an unreachable feed. A historical fact already living in the
feed (a duplicate item, a real collision between two past releases) can
never be fixed by this release, so it is printed as a WARNING and never
fails the check -- see `check_build_number_increases`'s own docstring.

Usage:
    scripts/check_sparkle_update_ready.py \\
        --app build/releases/dmg-stage/Fichero.app \\
        --dmg build/releases/Fichero.dmg \\
        [--feed-url https://tubb.ca/apps/fichero/appcast.xml] \\
        [--entry-xml path/to/about-to-publish-item.xml] \\
        [--timeout 10]

Exit codes:
    0  ready (or NOT ARMED — --app/--dmg not both given)
    1  not ready, or the live feed could not be fetched — see printed problems
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_PATH = ROOT / "build" / "releases" / "dmg-stage" / "Fichero.app"
DEFAULT_DMG_PATH = ROOT / "build" / "releases" / "Fichero.dmg"
DEFAULT_FEED_URL = "https://tubb.ca/apps/fichero/appcast.xml"

SPARKLE_NS = "http://www.andymatuschak.org/xml-namespaces/sparkle"
_SPARKLE_VERSION_TAG = f"{{{SPARKLE_NS}}}version"
_SPARKLE_SHORT_VERSION_TAG = f"{{{SPARKLE_NS}}}shortVersionString"
_SPARKLE_CHANNEL_TAG = f"{{{SPARKLE_NS}}}channel"


@dataclass
class AppcastItem:
    """One <item> from an appcast feed (or a single about-to-publish item)."""

    version: str  # sparkle:version, raw text -- may be non-numeric; caller checks
    short_version: str | None
    length: str | None  # enclosure length, raw text
    url: str | None  # enclosure url
    channel: str | None  # sparkle:channel text, e.g. "dev"; None for the public/default item


def parse_appcast(xml_text: str) -> list[AppcastItem]:
    """Parse a full appcast feed OR a single standalone <item> fragment.

    `Element.iter("item")` includes the root itself when the root IS an
    <item> (a caller passing one about-to-publish entry, not a whole feed),
    so one function covers both shapes. A standalone <item> fragment must
    declare `xmlns:sparkle` on itself to parse (XML has no notion of an
    "ambient" namespace from a document it isn't part of).

    This project publishes ONE release as TWO items sharing the same
    sparkle:version AND shortVersionString -- a public (channel-less) item
    and a dev item (`<sparkle:channel>dev</sparkle:channel>`), confirmed
    against the real live feed (every release listed exactly twice, always
    one of each). `channel` is what actually distinguishes them; a caller
    comparing items for identity/collision purposes must include it.
    """
    root = ET.fromstring(xml_text)
    items: list[AppcastItem] = []
    for item_el in root.iter("item"):
        version_el = item_el.find(_SPARKLE_VERSION_TAG)
        short_el = item_el.find(_SPARKLE_SHORT_VERSION_TAG)
        channel_el = item_el.find(_SPARKLE_CHANNEL_TAG)
        enclosure_el = item_el.find("enclosure")
        items.append(
            AppcastItem(
                version=(version_el.text or "").strip() if version_el is not None else "",
                short_version=(short_el.text or "").strip() if short_el is not None else None,
                length=enclosure_el.get("length") if enclosure_el is not None else None,
                url=enclosure_el.get("url") if enclosure_el is not None else None,
                channel=(channel_el.text or "").strip() if channel_el is not None else None,
            )
        )
    return items


def _numeric_build(value: str, *, label: str) -> int:
    """Sparkle compares sparkle:version as an INTEGER, not the marketing
    string (release.update.build-number-strictly-increases) -- a
    non-numeric build number must fail loudly, not silently string-compare
    or crash with an unhandled exception."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} build number {value!r} is not a plain integer") from None


def check_build_number_increases(
    items: list[AppcastItem], new_build: str
) -> tuple[list[str], list[str]]:
    """release.update.feed-is-current + release.update.build-number-strictly-increases (#4901).

    Returns (problems, warnings). Only what can stop THIS update installing
    is a problem (fails the check). A historical fact already living in the
    feed can never be fixed by this release, so it is a WARNING, reported
    but never failing.

    CORRECTED 2026-09-19: an earlier version of this function treated every
    release appearing twice in the live feed as a "duplicate listing" and
    (in a report, not code) attributed it to a non-idempotent release
    script. Both were wrong. Read from the real live feed (every release
    has EXACTLY two items, always one of each kind, never more): this
    project publishes one release as a public (channel-less) item AND a
    dev item (`<sparkle:channel>dev</sparkle:channel>`) BY DESIGN --
    confirmed against `fichero/fichero/App/SparkleUpdater.swift`'s
    `SparkleChannelDelegate`. There are no re-run duplicates in the live
    feed at all. `AppcastItem.channel` now participates in every identity
    check below so a normal public+dev pair is never mistaken for one.

    - The SAME (sparkle:version, shortVersionString, channel) listed more
      than once -- a GENUINE duplicate/re-run artifact (this is what the
      corrected code actually detects now; it does not fire on a normal
      public+dev pair, which differ by channel).
    - Two DIFFERENT releases (different shortVersionString) sharing one
      sparkle:version -- a real collision, e.g. the live feed's own
      2026.09.04/2026.09.05, both `sparkle:version=2` -- confirmed to occur
      independently in BOTH the public and dev channel. Reported ONCE per
      colliding build number, naming every distinct release AND every
      channel it was seen in, rather than once per channel: the same two
      releases stepping on each other is one underlying mistake, not two.
    - A live item whose sparkle:version isn't a plain integer -- cannot be
      compared, but it is still someone else's past mistake, not something
      this release's own readiness should be blocked on.

    The FAIL gate compares the new build against the MAXIMUM sparkle:version
    across EVERY channel combined, not just the channel about to be
    published to. Why global, not per-channel (read, not guessed --
    `fichero/fichero/App/SparkleUpdater.swift`): the public build's
    `allowedChannels` is empty (sees ONLY channel-less/public items); the
    dev build's is `{"dev"}`, which per Sparkle's own semantics ADDS the
    dev channel on top of the always-visible default channel -- so a dev
    client's comparison pool is public-union-dev, a strict superset of a
    public client's. A channel-less item is therefore visible to every
    client regardless of channel, and this pipeline always mints ONE build
    number per release and publishes it to every channel that release
    ships to (confirmed: `create-github-release.sh` passes the same
    `$BUILD` to both the public and dev `appcast_upsert.py` calls) -- so
    the build counter is meant to be globally, not per-channel, monotonic.
    Requiring strictly-greater-than-the-GLOBAL maximum is at least as
    strict as a same-channel-only check (global max >= same-channel max
    always, so this implies it for free) and additionally protects a
    future asymmetric case a same-channel check would miss entirely: a
    dev-only or public-only release that leaves the two channels' own
    histories at different build numbers.
    """
    problems: list[str] = []
    warnings: list[str] = []
    try:
        new_build_int = _numeric_build(new_build, label="the new release's")
    except ValueError as exc:
        return [str(exc)], []

    # (build, short_version, channel) per item -- channel is part of
    # identity everywhere below, per the correction above.
    parsed: list[tuple[int, str | None, str | None]] = []
    for item in items:
        try:
            build_int = _numeric_build(item.version, label="a live feed item's")
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        parsed.append((build_int, item.short_version, item.channel))

    listing_counts: dict[tuple[int, str | None, str | None], int] = {}
    for key in parsed:
        listing_counts[key] = listing_counts.get(key, 0) + 1
    for (build_int, short_version, channel), count in listing_counts.items():
        if count > 1:
            warnings.append(
                f"release {short_version!r} on channel {channel or 'public'!r} "
                f"(sparkle:version={build_int}) is listed {count} times in the live "
                "feed -- a genuine duplicate/re-run artifact (a public+dev pair is "
                "NOT this: they differ by channel, so they are different keys here)"
            )

    by_build: dict[int, set[str | None]] = {}
    channels_by_build: dict[int, set[str | None]] = {}
    for build_int, short_version, channel in parsed:
        by_build.setdefault(build_int, set()).add(short_version)
        channels_by_build.setdefault(build_int, set()).add(channel)
    for build_int, short_versions in by_build.items():
        if len(short_versions) > 1:
            channel_names = sorted(c or "public" for c in channels_by_build[build_int])
            warnings.append(
                f"live feed has a real build-number collision: sparkle:version={build_int} "
                f"is shared by different releases {sorted(v for v in short_versions if v)!r} "
                f"(seen on channel(s) {channel_names!r})"
            )

    all_builds = {build_int for build_int, _short_version, _channel in parsed}
    if new_build_int in all_builds:
        problems.append(
            f"the new build {new_build} is already present in the live feed "
            "(checked across every channel)"
        )
    elif all_builds:
        feed_max = max(all_builds)
        if new_build_int <= feed_max:
            problems.append(
                f"the new build {new_build} is not strictly greater than the live "
                f"feed's current maximum sparkle:version={feed_max} across every "
                "channel (a channel-less item is visible to every client "
                "regardless of channel, and this release's build number is shared "
                "by every channel it publishes to, so the counter must be globally "
                "monotonic -- see this function's own docstring)"
            )
    return problems, warnings


def check_feed_url_matches(app_feed_url: str | None, expected_feed_url: str) -> list[str]:
    """release.update.feed-is-current (#4901): the built app must point at
    the feed this release is actually about to publish to, or Sparkle will
    check a feed nobody is updating."""
    if app_feed_url != expected_feed_url:
        return [
            f"built app SUFeedURL {app_feed_url!r} does not match the "
            f"expected published feed {expected_feed_url!r}"
        ]
    return []


def check_enclosure_matches_dmg(
    entry: AppcastItem, dmg_size: int, expected_short_version: str | None, expected_build: str
) -> list[str]:
    """Given the appcast <item> about to be published, fail unless its
    declared enclosure length equals the DMG's actual byte size and its
    version fields match the built app's own -- a self-consistency check
    on the release script's own output, not the feed."""
    problems: list[str] = []
    if entry.length is None or not entry.length.isdigit() or int(entry.length) != dmg_size:
        problems.append(
            f"about-to-publish appcast entry enclosure length {entry.length!r} "
            f"does not equal the DMG's actual byte size {dmg_size}"
        )
    if entry.version != expected_build:
        problems.append(
            f"about-to-publish appcast entry sparkle:version {entry.version!r} "
            f"does not match the app's CFBundleVersion {expected_build!r}"
        )
    if entry.short_version != expected_short_version:
        problems.append(
            f"about-to-publish appcast entry shortVersionString {entry.short_version!r} "
            f"does not match the app's CFBundleShortVersionString {expected_short_version!r}"
        )
    return problems


def fetch_live_feed(url: str, timeout: float = 10.0) -> str:
    """A network fetch gets a timeout and a clear failure, never a silent
    pass -- an unreachable feed is a FAILURE with its own message, not a
    skipped check."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed https feed URL)
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"could not fetch the live appcast at {url}: {exc}") from exc


def check_staple_and_signature(
    dmg_path: Path, sign_update_bin: Path | None = None
) -> tuple[bool, str]:
    """release.update.signature-made-after-stapling (#4901): REPORTS,
    does not fail the overall check -- stapling status is informational
    here because the real release lane already enforces the correct order
    by construction (notarize.sh staples before create-github-release.sh
    signs); this is a second, independent confirmation, not the only guard.

    Verifies the EdDSA signature only if a verifier is reachable with NO
    new dependency: probes the Sparkle `sign_update` binary's own --help
    for a verify mode, per the maintainer's own account of it having one.
    This script does not vendor a from-scratch Ed25519 implementation or
    add a crypto dependency to do this itself -- if no such mode is
    discoverable, it says plainly the signature was not verified rather
    than guessing at undocumented flags.
    """
    try:
        subprocess.run(
            ["xcrun", "stapler", "validate", str(dmg_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        stapled = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        stapled = False

    if not stapled:
        return False, "DMG is NOT stapled (xcrun stapler validate failed) -- staple before signing"

    if sign_update_bin is None or not sign_update_bin.exists():
        return True, "DMG is stapled. Signature NOT verified (no sign_update binary found)."

    try:
        help_text = subprocess.run(
            [str(sign_update_bin), "--help"], capture_output=True, text=True, timeout=10
        ).stdout.lower()
    except (OSError, subprocess.TimeoutExpired):
        help_text = ""

    if "verify" not in help_text:
        return True, (
            "DMG is stapled. Signature NOT verified (installed sign_update "
            "advertises no verify mode in --help)."
        )

    try:
        result = subprocess.run(
            [str(sign_update_bin), "--verify", str(dmg_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return True, f"DMG is stapled. sign_update --verify attempt errored: {exc}"

    if result.returncode == 0:
        return True, "DMG is stapled. Signature verified via sign_update --verify."
    return True, (
        "DMG is stapled. sign_update --verify reported failure: "
        f"{(result.stderr or result.stdout).strip()}"
    )


def read_app_plist(app_path: Path) -> dict:
    plist_path = app_path / "Contents" / "Info.plist"
    with open(plist_path, "rb") as fh:
        return plistlib.load(fh)


def run_checks(
    *,
    app_path: Path,
    dmg_path: Path,
    feed_url: str,
    entry_xml: str | None,
    timeout: float,
    sign_update_bin: Path | None,
    fetch_feed=None,
) -> tuple[list[str], list[str]]:
    """Returns (problems, warnings). Only `problems` affects the exit code.

    `fetch_feed` is injectable so a test (or a caller that never wants to
    touch the network at all, e.g. the NOT-ARMED no-args path in `main()`)
    can prove the fetcher is never called, instead of relying on
    monkeypatching the module-level `fetch_live_feed`.
    """
    if fetch_feed is None:
        fetch_feed = fetch_live_feed
    problems: list[str] = []
    warnings: list[str] = []
    plist = read_app_plist(app_path)
    build = str(plist.get("CFBundleVersion", ""))
    short_version = plist.get("CFBundleShortVersionString")
    app_feed_url = plist.get("SUFeedURL")

    problems += check_feed_url_matches(app_feed_url, feed_url)

    try:
        feed_xml = fetch_feed(feed_url, timeout=timeout)
    except RuntimeError as exc:
        # Never a silent pass: an unreachable feed is a hard failure with
        # its own message, reported alongside (not instead of) the other
        # checks that don't need the network. The build-number comparison
        # is skipped, not silently "passed" -- there is nothing to compare
        # against, and the fetch failure alone already fails the run.
        problems.append(str(exc))
    else:
        feed_items = parse_appcast(feed_xml)
        build_problems, build_warnings = check_build_number_increases(feed_items, build)
        problems += build_problems
        warnings += build_warnings

    if entry_xml is not None:
        entries = parse_appcast(entry_xml)
        if not entries:
            problems.append("--entry-xml did not contain an <item>")
        else:
            dmg_size = dmg_path.stat().st_size
            problems += check_enclosure_matches_dmg(entries[0], dmg_size, short_version, build)

    stapled, staple_message = check_staple_and_signature(dmg_path, sign_update_bin)
    print(f"staple/signature (report-only): {staple_message}")
    del stapled  # informational only, per release.update.signature-made-after-stapling

    return problems, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--app", type=Path, default=None, help=f"default: {DEFAULT_APP_PATH}")
    parser.add_argument("--dmg", type=Path, default=None, help=f"default: {DEFAULT_DMG_PATH}")
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL)
    parser.add_argument(
        "--entry-xml",
        type=Path,
        default=None,
        help="Path to the about-to-publish appcast <item> XML fragment (optional)",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--sign-update-bin",
        type=Path,
        default=Path.home() / "code" / "sparkle-tools" / "bin" / "sign_update",
    )
    args = parser.parse_args(argv)

    # Arming requires BOTH --app and --dmg explicitly, always, with no
    # existence-probing fallback to a default path. `verify_all.sh --fast`
    # sweeps every scripts/check_*.py with NO arguments; a real release
    # build can be sitting in build/releases/ (another lane's in-flight
    # work, a stale artifact) at the exact moment an unrelated dev gate
    # runs, and this check must NEVER reach the network in that case.
    # NOT ARMED, unconditionally, on no args -- no filesystem probe, no
    # network call, always exit 0.
    if args.app is None or args.dmg is None:
        print("sparkle-update readiness: NOT ARMED — pass --app and --dmg explicitly to run this check")
        return 0

    app_path = args.app
    dmg_path = args.dmg

    if not app_path.exists():
        print(f"error: app not found at {app_path}", file=sys.stderr)
        return 1
    if not dmg_path.exists():
        print(f"error: DMG not found at {dmg_path}", file=sys.stderr)
        return 1

    entry_xml_text = args.entry_xml.read_text() if args.entry_xml is not None else None

    problems, warnings = run_checks(
        app_path=app_path,
        dmg_path=dmg_path,
        feed_url=args.feed_url,
        entry_xml=entry_xml_text,
        timeout=args.timeout,
        sign_update_bin=args.sign_update_bin,
    )

    for warning in warnings:
        print(f"warning (historical, not blocking): {warning}")

    if problems:
        print("sparkle-update readiness: NOT READY", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("sparkle-update readiness: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
