"""Idempotent appcast <item> upsert (#4901, release.update.appcast-item-insert-is-idempotent).

Proves `scripts/appcast_upsert.py`'s pure `upsert_item()` against fixture XML
-- no real appcast.xml, no site repo, no create-github-release.sh execution.
The live feed's own shape (every release published as a public+dev PAIR,
plus one real build-number collision) is reproduced structurally, not by
copying its actual content, per the task's own instruction.

CORRECTED 2026-09-19: a first delivery here matched an existing item's
identity on (version, short_version) alone. No test in that first delivery
ever called `upsert_item()` twice with the REAL sequence
`create-github-release.sh` actually makes -- public first, then dev, same
version and short_version, different channel -- so nothing caught that the
second (dev) call would silently REPLACE the item the first (public) call
had just written, publishing a feed with no public item at all for every
release with a dev DMG. `test_the_real_public_then_dev_sequence_*` below is
that missing test, and is exactly the check that would have caught this
before delivery.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_APPCAST_UPSERT_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "appcast_upsert.py"
)
_UPSERT_SPEC = importlib.util.spec_from_file_location("appcast_upsert", _APPCAST_UPSERT_SCRIPT)
assert _UPSERT_SPEC and _UPSERT_SPEC.loader
appcast_upsert = importlib.util.module_from_spec(_UPSERT_SPEC)
sys.modules[_UPSERT_SPEC.name] = appcast_upsert
_UPSERT_SPEC.loader.exec_module(appcast_upsert)  # type: ignore[attr-defined]

AppcastEntry = appcast_upsert.AppcastEntry
upsert_item = appcast_upsert.upsert_item
render_item_xml = appcast_upsert.render_item_xml

_READY_SCRIPT = (
    Path(__file__).resolve().parents[4] / "scripts" / "check_sparkle_update_ready.py"
)
_READY_SPEC = importlib.util.spec_from_file_location("check_sparkle_update_ready", _READY_SCRIPT)
assert _READY_SPEC and _READY_SPEC.loader
check_sparkle_update_ready = importlib.util.module_from_spec(_READY_SPEC)
sys.modules[_READY_SPEC.name] = check_sparkle_update_ready
_READY_SPEC.loader.exec_module(check_sparkle_update_ready)  # type: ignore[attr-defined]

parse_appcast = check_sparkle_update_ready.parse_appcast

_EMPTY_CHANNEL = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
    <channel>
        <title>Fichero Updates</title>
        <link>https://tubb.ca/apps/fichero/</link>
        <description>Appcast feed for Fichero Sparkle updates.</description>
        <language>en</language>
    </channel>
</rss>
"""


def _existing_item(
    version: str, short_version: str, url: str = "https://example.com/old.dmg",
    channel: str | None = None,
) -> str:
    entry = AppcastEntry(
        title=f"Fichero {short_version}" + (" (dev)" if channel else ""),
        pub_date="Sat, 07 Sep 2026 00:00:00 +0000",
        version=version,
        short_version=short_version,
        enclosure_url=url,
        enclosure_length="1000",
        ed_signature="oldsig==",
        notes_html="<p>Old notes.</p>",
        channel=channel,
    )
    return render_item_xml(entry)


def _feed_with_items(*item_texts: str) -> str:
    header = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0" '
        'xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">\n'
        "    <channel>\n"
        "        <title>Fichero Updates</title>\n"
        "        <link>https://tubb.ca/apps/fichero/</link>\n"
        "        <description>Appcast feed for Fichero Sparkle updates.</description>\n"
        "        <language>en</language>\n"
    )
    footer = "    </channel>\n</rss>\n"
    return header + "".join(item_texts) + footer


def _new_entry(version="9", short_version="2026.09.19") -> AppcastEntry:
    return AppcastEntry(
        title=f"Fichero {short_version}",
        pub_date="Sat, 19 Sep 2026 00:00:00 +0000",
        version=version,
        short_version=short_version,
        enclosure_url="https://example.com/new.dmg",
        enclosure_length="2000",
        ed_signature="newsig==",
        notes_html="<p>New notes.</p>",
    )


def test_insert_into_an_empty_channel():
    xml = upsert_item(_EMPTY_CHANNEL, _new_entry())
    items = parse_appcast(xml)
    assert len(items) == 1
    assert items[0].version == "9"
    assert items[0].short_version == "2026.09.19"
    # Everything before the inserted item is untouched, byte for byte.
    assert xml.startswith(_EMPTY_CHANNEL.split("<language>")[0])


def test_insert_newest_first_among_existing_items():
    existing = _existing_item("8", "2026.09.07")
    feed = _feed_with_items(existing)
    xml = upsert_item(feed, _new_entry(version="9", short_version="2026.09.19"))
    items = parse_appcast(xml)
    assert [i.version for i in items] == ["9", "8"]
    # The pre-existing item's own bytes are untouched.
    assert existing in xml


def test_rerun_with_same_version_and_build_replaces_not_appends():
    """A re-run after a partial failure must converge: the item count stays
    the same, and the replaced item carries the NEW fields."""
    old = _existing_item("9", "2026.09.19", url="https://example.com/old.dmg")
    feed = _feed_with_items(old)
    new_entry = _new_entry(version="9", short_version="2026.09.19")

    xml = upsert_item(feed, new_entry)

    items = parse_appcast(xml)
    assert len(items) == 1
    assert items[0].url == "https://example.com/new.dmg"
    assert "old.dmg" not in xml


def test_same_build_different_short_version_is_not_treated_as_the_same_release():
    """This is exactly the collision check_sparkle_update_ready.py then
    refuses to publish over -- appcast_upsert's job is only to insert it
    faithfully, not to silently merge it with a different release."""
    existing = _existing_item("2", "2026.09.04")
    feed = _feed_with_items(existing)
    new_entry = _new_entry(version="2", short_version="2026.09.05")

    xml = upsert_item(feed, new_entry)

    items = parse_appcast(xml)
    assert len(items) == 2
    assert {i.short_version for i in items} == {"2026.09.04", "2026.09.05"}
    assert existing in xml  # the old item is untouched, not merged


def test_the_real_public_then_dev_sequence_yields_two_items_public_still_present():
    """THE bug: `create-github-release.sh` calls appcast_upsert.py TWICE per
    release -- public first, then (if a dev DMG exists) dev -- with the
    SAME --version/--short-version and only --channel differing. A first,
    wrong delivery matched identity on (version, short_version) alone, so
    the second call replaced the item the first call had just written.
    This test runs that exact real sequence and asserts BOTH survive."""
    public_entry = _new_entry(version="9", short_version="2026.09.19")
    public_entry.enclosure_url = "https://example.com/Fichero.dmg"

    xml = upsert_item(_EMPTY_CHANNEL, public_entry)

    dev_entry = _new_entry(version="9", short_version="2026.09.19")
    dev_entry.channel = "dev"
    dev_entry.enclosure_url = "https://example.com/Fichero-dev.dmg"
    dev_entry.title = "Fichero 2026.09.19 (dev)"

    xml = upsert_item(xml, dev_entry)

    items = parse_appcast(xml)
    assert len(items) == 2, "the public item must still be present after the dev call"
    urls = {i.url for i in items}
    assert urls == {"https://example.com/Fichero.dmg", "https://example.com/Fichero-dev.dmg"}
    channels = {i.channel for i in items}
    assert channels == {None, "dev"}


def test_rerunning_the_real_sequence_yields_the_same_two_items_byte_identical():
    """A full re-run of the real public-then-dev sequence for the SAME
    release must converge (replace both in place), not grow the feed."""
    public_entry = _new_entry(version="9", short_version="2026.09.19")
    public_entry.enclosure_url = "https://example.com/Fichero.dmg"
    dev_entry = _new_entry(version="9", short_version="2026.09.19")
    dev_entry.channel = "dev"
    dev_entry.enclosure_url = "https://example.com/Fichero-dev.dmg"
    dev_entry.title = "Fichero 2026.09.19 (dev)"

    xml = upsert_item(_EMPTY_CHANNEL, public_entry)
    xml = upsert_item(xml, dev_entry)
    first_run_xml = xml

    # Re-run the identical sequence (a retried release for the same version).
    xml = upsert_item(xml, public_entry)
    xml = upsert_item(xml, dev_entry)

    assert xml == first_run_xml
    items = parse_appcast(xml)
    assert len(items) == 2


def test_a_feed_shaped_like_the_live_feed_is_left_as_is_apart_from_one_pair():
    """The live feed's REAL shape (team-lead's saved file, mirrored
    structurally, not its actual content): 4 releases, each published as a
    public+dev PAIR (8 items total), with one real build-number collision
    (2026.09.04 and 2026.09.05 both build 2, in both channels -- NOT a
    duplicate-listing bug). Upserting a NEW release must not touch any of
    that pre-existing structure."""
    pairs = []
    for version, short_version in [("1", "2026.09.03"), ("2", "2026.09.04"),
                                    ("2", "2026.09.05"), ("3", "2026.09.07")]:
        pairs.append(_existing_item(version, short_version))
        pairs.append(_existing_item(version, short_version, url=f"https://example.com/{short_version}-dev.dmg", channel="dev"))
    feed = _feed_with_items(*pairs)

    new_entry = _new_entry(version="4", short_version="2026.09.19")
    xml = upsert_item(feed, new_entry)

    # The new item was inserted; every pre-existing item is byte-identical.
    for existing_item_text in pairs:
        assert existing_item_text in xml
    items = parse_appcast(xml)
    assert len(items) == 9
    assert items[0].version == "4"  # inserted newest-first


def test_output_is_well_formed_xml_readable_by_the_checkers_own_parser():
    feed = _feed_with_items(_existing_item("8", "2026.09.07"))
    xml = upsert_item(feed, _new_entry())
    # parse_appcast raises ET.ParseError on malformed XML -- this both
    # proves well-formedness and exercises the checker's own reader.
    items = parse_appcast(xml)
    assert len(items) == 2


def test_dev_channel_item_carries_the_channel_tag():
    entry = _new_entry()
    entry.channel = "dev"
    xml = upsert_item(_EMPTY_CHANNEL, entry)
    assert "<sparkle:channel>dev</sparkle:channel>" in xml
