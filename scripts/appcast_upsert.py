#!/usr/bin/env python3
"""Idempotent appcast <item> upsert (#4901, release.update.appcast-item-insert-is-idempotent).

`create-github-release.sh`'s "[3/5] Update appcast.xml" step used to build a
new `<item>` and insert it UNCONDITIONALLY, every run, with no check for an
existing item matching the release about to publish -- unlike the GitHub
release step right above it (`gh release view "$TAG"` first, "update notes"
if it already exists). A retried or re-run release for the SAME item
therefore appended a second copy rather than converging, which is a real
defect this module fixes.

CORRECTED 2026-09-19: an earlier version of this docstring claimed that
defect was WHY the live feed shows every release listed twice. It is not.
Reading the actual live feed (saved structure, see
`fichero-server/tests/unit/scripts/test_appcast_upsert.py`): every release
has EXACTLY two items, always one of each kind, never more -- there are no
re-run duplicates in the live feed at all. This project publishes one
release as a public (channel-less) item AND a dev item
(`<sparkle:channel>dev</sparkle:channel>`) BY DESIGN (confirmed against
`fichero/fichero/App/SparkleUpdater.swift`'s `SparkleChannelDelegate`,
which opts dev builds into the `dev` channel so they see both). The
non-idempotent-insert defect is real and worth fixing regardless (a true
re-run WOULD append a duplicate), but it is not the explanation for the
"twice" pattern anyone will observe in the live feed today.

This module is that insert step, extracted into a PURE function so it is
unit tested with fixture XML instead of only being exercised by actually
running the release script -- a release script neither engine-lane nor
team-lead may run.

RULE: identity is the THREE-WAY match (`sparkle:version`,
`sparkle:shortVersionString`, `sparkle:channel` -- `None` for the
channel-less/public item). An item matching all three is REPLACED in place
(a re-run converges); a different channel is NOT the same release and is
inserted as its own item (the normal public+dev pairing) -- getting this
key wrong once already caused a real incident (see the module-level
comment history / the delivery report): matching on
(version, short_version) ALONE made the dev-channel call silently replace
the public item it had just written, because both calls share the same
build number and marketing version by design. Otherwise the new item is
inserted newest-first, in the exact spot the original heredoc used --
immediately after `<language>...</language>`, or after `<channel>` if that
is somehow absent (matches the original's own fallback, confirmed by
reading it).

Serialization is TEXTUAL, not via `xml.etree.ElementTree` round-tripping the
whole document: ElementTree does not preserve a document's original
attribute-quoting/namespace-prefix declarations or whitespace on
serialization (it is free to normalize both), and this file is read by
Sparkle AND by a human reviewing the site repo's diff -- a full re-serialize
would touch every existing item's bytes, not just the one that changed. This
module finds the `<item>...</item>` block by regex and replaces or inserts
only that text span, leaving every other byte -- the XML declaration,
namespaces, other items, indentation -- untouched.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_ITEM_RE = re.compile(r"( {8}<item>.*?</item>\n)", re.DOTALL)
_VERSION_RE = re.compile(r"<sparkle:version>([^<]*)</sparkle:version>")
_SHORT_VERSION_RE = re.compile(r"<sparkle:shortVersionString>([^<]*)</sparkle:shortVersionString>")
_ITEM_CHANNEL_RE = re.compile(r"<sparkle:channel>([^<]*)</sparkle:channel>")
_LANGUAGE_RE = re.compile(r"(<language>[^<]*</language>\s*\n)")
_CHANNEL_OPEN_RE = re.compile(r"(<channel>\s*\n)")


@dataclass
class AppcastEntry:
    """Exactly the fields the original heredoc wrote -- no more."""

    title: str  # e.g. "Fichero 2026.09.19" or "Fichero 2026.09.19 (dev)"
    pub_date: str  # RFC 2822, e.g. `date -R` output
    version: str  # sparkle:version (the integer build, CFBundleVersion)
    short_version: str  # sparkle:shortVersionString (CFBundleShortVersionString)
    enclosure_url: str
    enclosure_length: str
    ed_signature: str
    notes_html: str  # release notes, inlined as CDATA (matches today's design)
    minimum_system_version: str = "15.0"
    channel: str | None = None  # e.g. "dev"; None for the public/alpha item


def render_item_xml(entry: AppcastEntry) -> str:
    """Byte-for-byte the same shape `create-github-release.sh`'s original
    `item()` python function produced, parameterized instead of shell-
    variable-substituted."""
    channel_block = (
        f"            <sparkle:channel>{entry.channel}</sparkle:channel>\n"
        if entry.channel
        else ""
    )
    return (
        "        <item>\n"
        f"            <title>{entry.title}</title>\n"
        f"            <pubDate>{entry.pub_date}</pubDate>\n"
        f"{channel_block}"
        f"            <sparkle:version>{entry.version}</sparkle:version>\n"
        f"            <sparkle:shortVersionString>{entry.short_version}</sparkle:shortVersionString>\n"
        f"            <sparkle:minimumSystemVersion>{entry.minimum_system_version}</sparkle:minimumSystemVersion>\n"
        "            <description><![CDATA[\n"
        f"{entry.notes_html}\n"
        "]]></description>\n"
        "            <enclosure\n"
        f'                url="{entry.enclosure_url}"\n'
        f'                length="{entry.enclosure_length}"\n'
        '                type="application/octet-stream"\n'
        f'                sparkle:edSignature="{entry.ed_signature}"\n'
        "            />\n"
        "        </item>\n"
    )


def _item_key(item_text: str) -> tuple[str, str, str | None] | None:
    version_match = _VERSION_RE.search(item_text)
    short_version_match = _SHORT_VERSION_RE.search(item_text)
    if version_match is None or short_version_match is None:
        return None
    channel_match = _ITEM_CHANNEL_RE.search(item_text)
    channel = channel_match.group(1) if channel_match else None
    return version_match.group(1), short_version_match.group(1), channel


def upsert_item(xml_text: str, entry: AppcastEntry) -> str:
    """Insert or replace `entry` in `xml_text`, touching only that one
    <item> block's bytes.

    release.update.appcast-item-insert-is-idempotent (#4901): identity is
    the THREE-WAY match on `sparkle:version`, `sparkle:shortVersionString`,
    AND `sparkle:channel` (`None` for the public/channel-less item). An
    item matching all three is the SAME item republishing (a retry, a
    re-run) and is replaced in place -- the item count does not grow. A
    DIFFERENT channel sharing the same version/short_version is the normal
    public+dev pairing, NOT the same item -- it is inserted as its own
    item. (Matching on version/short_version alone was tried and is wrong:
    both channels of one release share those two fields by design, so a
    two-key match made the dev-channel call silently replace the public
    item just written by the previous call in the same release.) A
    DIFFERENT shortVersionString sharing the same sparkle:version and
    channel is a real collision, inserted as its own item, which is
    exactly what `check_sparkle_update_ready.py` then refuses to publish
    over.
    """
    new_item_text = render_item_xml(entry)
    target_key = (entry.version, entry.short_version, entry.channel)

    for match in _ITEM_RE.finditer(xml_text):
        if _item_key(match.group(1)) == target_key:
            return xml_text[: match.start()] + new_item_text + xml_text[match.end() :]

    # No existing item for this release: insert newest-first, exactly where
    # the original heredoc inserted -- right after <language>, falling back
    # to right after <channel> if <language> is somehow absent.
    language_match = _LANGUAGE_RE.search(xml_text)
    if language_match:
        return xml_text[: language_match.end()] + new_item_text + xml_text[language_match.end() :]
    channel_match = _CHANNEL_OPEN_RE.search(xml_text)
    if channel_match:
        return xml_text[: channel_match.end()] + new_item_text + xml_text[channel_match.end() :]
    raise ValueError("appcast XML has neither <language> nor <channel> to insert after")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("appcast_path", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--pub-date", required=True)
    parser.add_argument("--version", required=True, help="sparkle:version (the build number)")
    parser.add_argument("--short-version", required=True, help="sparkle:shortVersionString")
    parser.add_argument("--enclosure-url", required=True)
    parser.add_argument("--enclosure-length", required=True)
    parser.add_argument("--ed-signature", required=True)
    parser.add_argument("--minimum-system-version", default="15.0")
    parser.add_argument("--channel", default=None, help='e.g. "dev"; omit for the public item')
    parser.add_argument(
        "--notes-html-env",
        default="NOTES_HTML",
        help="Env var holding the release notes HTML (matches create-github-release.sh's "
        "existing `export NOTES_HTML` convention -- multi-line HTML has no clean CLI-arg form)",
    )
    args = parser.parse_args(argv)

    notes_html = os.environ.get(args.notes_html_env, "")
    if not notes_html:
        print(f"error: ${args.notes_html_env} is empty or unset", file=sys.stderr)
        return 1

    entry = AppcastEntry(
        title=args.title,
        pub_date=args.pub_date,
        version=args.version,
        short_version=args.short_version,
        enclosure_url=args.enclosure_url,
        enclosure_length=args.enclosure_length,
        ed_signature=args.ed_signature,
        notes_html=notes_html,
        minimum_system_version=args.minimum_system_version,
        channel=args.channel,
    )

    xml_text = args.appcast_path.read_text()
    try:
        new_xml_text = upsert_item(xml_text, entry)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.appcast_path.write_text(new_xml_text)
    print(f"appcast_upsert: wrote {args.appcast_path} (version={args.version}, short_version={args.short_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
