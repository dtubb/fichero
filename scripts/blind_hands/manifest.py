"""The blind-hands benchmark manifest (#6966, `hands.bench.manifest-is-fixed-and-versioned`).

One JSON file with a version. Per hand: script, period, licence, whether its pages may leave this Mac, the page ids of
its adaptation pool and its held-out pages, and the manuscript of each page. `load` refuses a manifest in which a
manuscript has pages on both sides, a hand has no held-out page, or a page has no licence. The committed file holds
open-licensed and non-commercial hands; private hands are in a second file outside the repository, and
`check_committed` refuses a committed file that names one of them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

COMMITTED = Path(__file__).with_name("manifest.json")
OPEN_LICENCES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "public-domain"}
NON_COMMERCIAL_LICENCES = {"CC-BY-NC-4.0", "CC-BY-NC-SA-4.0"}
HAND_KEYS = {"id", "script", "period", "licence", "may_leave_this_mac", "pool", "held_out", "manuscripts"}


class ManifestError(ValueError):
    pass


def page_list_digest(hands: list[dict]) -> str:
    """Hash of every hand's page ids and manuscripts; it changes when a page list changes."""
    parts = [{"id": h["id"], "pool": sorted(h["pool"]), "held_out": sorted(h["held_out"]), "manuscripts": h["manuscripts"]}
             for h in sorted(hands, key=lambda h: h["id"])]
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


def validate(manifest: dict, *, private: bool = False) -> dict:
    """Return the manifest if it holds, else raise ManifestError naming the first fault."""
    if not isinstance(manifest.get("version"), int) or manifest["version"] < 0:
        raise ManifestError("the manifest has no integer version")
    hands = manifest.get("hands")
    if not isinstance(hands, list):
        raise ManifestError("the manifest has no hands list")
    allowed = OPEN_LICENCES | NON_COMMERCIAL_LICENCES
    seen_hands: set[str] = set()
    side_of: dict[str, tuple[str, str]] = {}
    for hand in hands:
        missing = HAND_KEYS - hand.keys()
        if missing:
            raise ManifestError(f"hand {hand.get('id')!r} lacks {sorted(missing)}")
        hid = hand["id"]
        if hid in seen_hands:
            raise ManifestError(f"hand {hid!r} is listed twice")
        seen_hands.add(hid)
        if not hand["held_out"]:
            raise ManifestError(f"hand {hid!r} has no held-out page")
        pages = hand["pool"] + hand["held_out"]
        if len(set(pages)) != len(pages):
            raise ManifestError(f"hand {hid!r} lists a page twice or on both sides")
        if not hand["licence"] or (not private and hand["licence"] not in allowed):
            raise ManifestError(f"hand {hid!r} has no licence the committed manifest accepts: {hand['licence']!r}")
        if hand["may_leave_this_mac"] and hand["licence"] not in OPEN_LICENCES:
            raise ManifestError(f"hand {hid!r} may leave this Mac without an open licence")
        for side, ids in (("pool", hand["pool"]), ("held_out", hand["held_out"])):
            for page in ids:
                ms = hand["manuscripts"].get(page)
                if not ms:
                    raise ManifestError(f"page {page!r} of hand {hid!r} has no manuscript")
                if side_of.setdefault(ms, (side, page))[0] != side:
                    raise ManifestError(f"manuscript {ms!r} has pages on both sides ({side_of[ms][1]!r}, {page!r})")
    if not private and manifest.get("page_list_sha256") != page_list_digest(hands):
        raise ManifestError("the page list changed without a new version: set page_list_sha256 and raise version")
    return manifest


def load(path: Path = COMMITTED, *, private: bool = False) -> dict:
    return validate(json.loads(Path(path).read_text()), private=private)


def check_committed(committed: dict, private: dict) -> None:
    """Refuse a committed manifest that names a private hand or one of its pages."""
    pids = {h["id"] for h in private["hands"]}
    ppages = {p for h in private["hands"] for p in h["pool"] + h["held_out"]}
    for hand in committed["hands"]:
        if hand["id"] in pids or ppages & set(hand["pool"] + hand["held_out"]):
            raise ManifestError(f"the committed manifest names the private hand {hand['id']!r}")


def one_column(rows: list[dict]) -> int:
    """The manifest version of rows shown together; refuses rows of two versions."""
    versions = {r["manifest_version"] for r in rows}
    if len(versions) > 1:
        raise ManifestError(f"figures of manifest versions {sorted(versions)} are never shown in one column")
    return versions.pop() if versions else -1
