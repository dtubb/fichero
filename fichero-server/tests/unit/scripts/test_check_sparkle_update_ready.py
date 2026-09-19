"""Sparkle update pre-publish readiness guardrail (#4901).

Proves the pure, network-free logic of `scripts/check_sparkle_update_ready.py`
against fixture appcast XML -- no real HTTP fetch, no real DMG, no real
`sign_update`/`stapler` binaries. Behaviors covered, all in
docs/contributor_manual/specs/harness/release-and-versioning.md's "Updates
reach the user and install" section, under #4901:

    release.update.feed-is-current
    release.update.build-number-strictly-increases
    release.update.signature-made-after-stapling  (report-only path)

Only what can stop THIS update installing fails the check (asserted via the
returned `problems` list / the process exit code): the new build already in
the feed, or not strictly greater than the feed's maximum, a feed-URL
mismatch, an enclosure mismatch, an unreachable feed. A historical fact
already living in the feed (a duplicate listing, a real collision between
two past releases) is a WARNING -- reported, never failing.
"""

from __future__ import annotations

import importlib.util
import plistlib
import sys
import tempfile
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_sparkle_update_ready.py"
)
_SPEC = importlib.util.spec_from_file_location("check_sparkle_update_ready", _SCRIPT)
assert _SPEC and _SPEC.loader
check_sparkle_update_ready = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_sparkle_update_ready
_SPEC.loader.exec_module(check_sparkle_update_ready)  # type: ignore[attr-defined]

parse_appcast = check_sparkle_update_ready.parse_appcast
check_build_number_increases = check_sparkle_update_ready.check_build_number_increases
check_feed_url_matches = check_sparkle_update_ready.check_feed_url_matches
check_enclosure_matches_dmg = check_sparkle_update_ready.check_enclosure_matches_dmg
run_checks = check_sparkle_update_ready.run_checks
main = check_sparkle_update_ready.main

_FEED_HEADER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<rss version="2.0" '
    'xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
    "  <channel>\n"
)
_FEED_FOOTER = "  </channel>\n</rss>\n"


def _item_xml(version: str, short_version: str = "2026.09.07", length: str = "1000") -> str:
    return f"""    <item>
      <sparkle:version>{version}</sparkle:version>
      <sparkle:shortVersionString>{short_version}</sparkle:shortVersionString>
      <enclosure url="https://example.com/Fichero.dmg" length="{length}"
                 type="application/octet-stream" sparkle:edSignature="sig" />
    </item>
"""


def _feed(*items: tuple[str, str]) -> str:
    """items: (version, short_version) pairs."""
    return _FEED_HEADER + "".join(_item_xml(v, sv) for v, sv in items) + _FEED_FOOTER


def _standalone_item(version: str, short_version: str, length: str) -> str:
    return (
        '<item xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        f"  <sparkle:version>{version}</sparkle:version>\n"
        f"  <sparkle:shortVersionString>{short_version}</sparkle:shortVersionString>\n"
        f'  <enclosure url="https://example.com/Fichero.dmg" length="{length}" />\n'
        "</item>\n"
    )


def _app_with_plist(root: Path, *, build: str, short_version: str, feed_url: str) -> Path:
    app_path = root / "Fichero.app"
    (app_path / "Contents").mkdir(parents=True)
    with open(app_path / "Contents" / "Info.plist", "wb") as fh:
        plistlib.dump(
            {
                "CFBundleVersion": build,
                "CFBundleShortVersionString": short_version,
                "SUFeedURL": feed_url,
            },
            fh,
        )
    return app_path


def test_higher_build_passes():
    items = parse_appcast(_feed(("3", "2026.09.07")))
    problems, warnings = check_build_number_increases(items, "4")
    assert problems == []
    assert warnings == []


def test_equal_build_fails():
    items = parse_appcast(_feed(("3", "2026.09.07")))
    problems, _warnings = check_build_number_increases(items, "3")
    assert problems
    assert "already present in the live feed" in problems[0]


def test_lower_build_fails():
    items = parse_appcast(_feed(("5", "2026.09.07")))
    problems, _warnings = check_build_number_increases(items, "3")
    assert problems
    assert "not strictly greater" in problems[0]


def test_non_numeric_new_build_fails_loudly():
    items = parse_appcast(_feed(("3", "2026.09.07")))
    problems, _warnings = check_build_number_increases(items, "not-a-number")
    assert problems
    assert "not a plain integer" in problems[0]


def test_non_numeric_feed_item_build_is_a_warning_not_a_failure():
    """A malformed HISTORICAL entry is someone else's past mistake, not
    something the new release's own readiness should be blocked on."""
    items = parse_appcast(_feed(("abc", "2026.09.01")))
    problems, warnings = check_build_number_increases(items, "4")
    assert problems == []
    assert any("not a plain integer" in w for w in warnings)


def test_duplicate_listing_of_one_release_is_not_a_collision():
    """Every release in the live feed appears twice (verified by team-lead
    against the real feed): same sparkle:version AND same
    shortVersionString repeated. That is a duplicate LISTING, not a
    build-number collision between two different releases, and must not be
    reported as one."""
    items = parse_appcast(
        _feed(("3", "2026.09.07"), ("3", "2026.09.07"), ("2", "2026.09.05"), ("2", "2026.09.05"))
    )
    problems, warnings = check_build_number_increases(items, "4")
    assert problems == []
    assert any("listed 2 times" in w and "not a build-number collision" in w for w in warnings)
    assert not any("collision" in w and "shared by different releases" in w for w in warnings)


def test_real_collision_between_two_releases_warns_and_does_not_fail():
    """Two DIFFERENT releases sharing one sparkle:version -- the actual
    2026.09.04/2026.09.05 incident shape -- warns but does not fail when
    the new build itself is fine."""
    items = parse_appcast(_feed(("2", "2026.09.04"), ("2", "2026.09.05")))
    problems, warnings = check_build_number_increases(items, "3")
    assert problems == []
    assert any("shared by different releases" in w for w in warnings)


def test_new_build_equal_to_an_existing_item_fails_even_amid_warnings():
    """A real historical collision must still warn (not fail) while the new
    build being non-increasing is what actually fails."""
    items = parse_appcast(_feed(("2", "2026.09.04"), ("2", "2026.09.05")))
    problems, warnings = check_build_number_increases(items, "2")
    assert any("already present in the live feed" in p for p in problems)
    assert any("shared by different releases" in w for w in warnings)


def test_feed_url_mismatch_fails():
    problems = check_feed_url_matches(
        "https://old.example.com/appcast.xml", "https://tubb.ca/apps/fichero/appcast.xml"
    )
    assert problems


def test_feed_url_match_passes():
    assert (
        check_feed_url_matches(
            "https://tubb.ca/apps/fichero/appcast.xml", "https://tubb.ca/apps/fichero/appcast.xml"
        )
        == []
    )


def test_enclosure_length_mismatch_fails():
    entry = parse_appcast(_standalone_item("9", "2026.09.09", "1000"))[0]
    problems = check_enclosure_matches_dmg(
        entry, dmg_size=999, expected_short_version="2026.09.09", expected_build="9"
    )
    assert any("enclosure length" in p for p in problems)


def test_enclosure_version_mismatch_fails():
    entry = parse_appcast(_standalone_item("9", "2026.09.09", "1000"))[0]
    problems = check_enclosure_matches_dmg(
        entry, dmg_size=1000, expected_short_version="2026.09.09", expected_build="10"
    )
    assert any("CFBundleVersion" in p for p in problems)


def test_enclosure_matching_entry_passes():
    entry = parse_appcast(_standalone_item("9", "2026.09.09", "1000"))[0]
    assert (
        check_enclosure_matches_dmg(
            entry, dmg_size=1000, expected_short_version="2026.09.09", expected_build="9"
        )
        == []
    )


def test_unreachable_feed_fails():
    """A network fetch failure is a FAILURE with its own message, never a
    silent pass -- proven by injecting a fetcher that raises, exactly as a
    real DNS/timeout failure would, with no real network call."""

    def _boom(url, timeout=10.0):
        raise RuntimeError(f"could not fetch the live appcast at {url}: simulated DNS failure")

    with tempfile.TemporaryDirectory() as tmp:
        app_path = _app_with_plist(
            Path(tmp), build="4", short_version="2026.09.19",
            feed_url="https://tubb.ca/apps/fichero/appcast.xml",
        )
        dmg_path = Path(tmp) / "Fichero.dmg"
        dmg_path.write_bytes(b"0" * 1000)

        problems, _warnings = run_checks(
            app_path=app_path,
            dmg_path=dmg_path,
            feed_url="https://tubb.ca/apps/fichero/appcast.xml",
            entry_xml=None,
            timeout=1.0,
            sign_update_bin=Path("/nonexistent/sign_update"),
            fetch_feed=_boom,
        )

    assert any("could not fetch" in p for p in problems)


def test_no_args_never_fetches_and_exits_zero(monkeypatch):
    """verify_all.sh --fast sweeps this file with no arguments; it must
    NEVER touch the network, regardless of what happens to be on disk."""

    def _fetcher_that_must_not_be_called(url, timeout=10.0):
        raise AssertionError("fetch_live_feed must not be called with no --app/--dmg")

    monkeypatch.setattr(check_sparkle_update_ready, "fetch_live_feed", _fetcher_that_must_not_be_called)
    assert main([]) == 0


def test_exit_code_follows_the_verdict_not_ready(monkeypatch):
    """A NOT-READY run (new build not increasing) must exit 1, through
    main() -- the actual process exit code, not just the internal list."""
    with tempfile.TemporaryDirectory() as tmp:
        app_path = _app_with_plist(
            Path(tmp), build="2", short_version="2026.09.19",
            feed_url="https://tubb.ca/apps/fichero/appcast.xml",
        )
        dmg_path = Path(tmp) / "Fichero.dmg"
        dmg_path.write_bytes(b"0" * 1000)

        def _fake_fetch(url, timeout=10.0):
            return _feed(("2", "2026.09.07"))

        monkeypatch.setattr(check_sparkle_update_ready, "fetch_live_feed", _fake_fetch)

        exit_code = main(
            [
                "--app", str(app_path),
                "--dmg", str(dmg_path),
                "--feed-url", "https://tubb.ca/apps/fichero/appcast.xml",
            ]
        )
    assert exit_code == 1


def test_exit_code_follows_the_verdict_ready(monkeypatch):
    """A READY run (new build strictly greater, feed URL matches) must
    exit 0 through main(), even with a historical warning present."""
    with tempfile.TemporaryDirectory() as tmp:
        app_path = _app_with_plist(
            Path(tmp), build="5", short_version="2026.09.19",
            feed_url="https://tubb.ca/apps/fichero/appcast.xml",
        )
        dmg_path = Path(tmp) / "Fichero.dmg"
        dmg_path.write_bytes(b"0" * 1000)

        def _fake_fetch(url, timeout=10.0):
            # A historical collision (2026.09.04/05 sharing build 2) present
            # but irrelevant to the new build 5 -- must warn, not fail.
            return _feed(("2", "2026.09.04"), ("2", "2026.09.05"))

        monkeypatch.setattr(check_sparkle_update_ready, "fetch_live_feed", _fake_fetch)

        exit_code = main(
            [
                "--app", str(app_path),
                "--dmg", str(dmg_path),
                "--feed-url", "https://tubb.ca/apps/fichero/appcast.xml",
            ]
        )
    assert exit_code == 0
