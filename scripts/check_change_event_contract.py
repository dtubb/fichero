#!/usr/bin/env python3
"""ChangeEvent is the one engine<->app contract with no codegen backstop (#4211).

Every other boundary is enforced by generation: change a Pydantic field, the
OpenAPI spec moves, the Swift type regenerates, a mismatch breaks the build.
`ChangeEvent` is served as an SSE `StreamingResponse`, and FastAPI cannot model
a streaming body as a response schema — so it never enters the spec, the Swift
side is HAND-WRITTEN, and a divergence is silent by construction. On the
payload behind every live update in the app.

This is the missing backstop. It compares FIELD-NAME SETS, never source text:
a check pinned to literal Swift breaks on a harmless rename, which is how the
stranded `0345f4208` test died with its branch.

The two directions are NOT symmetric, deliberately:

* A Swift coding key with no Python field is a HARD FAILURE. Swift is decoding
  something the engine never sends, so it silently gets nil/garbage — the
  dangerous direction, and the reason this script exists.

* A Python field Swift does not consume is USUALLY FINE. The engine carries
  replay/bookkeeping the client ignores. Those are listed in
  ENGINE_ONLY_FIELDS with a reason each, so the set is a reviewed decision
  rather than an accident. A NEW unlisted one fails, which forces a
  deliberate answer: should the client consume this, or is it engine
  bookkeeping? That is the question nobody was asked when `document_parents`
  was added.

Usage:
    scripts/check_change_event_contract.py
    scripts/check_change_event_contract.py --list
    scripts/check_change_event_contract.py --help
"""
from __future__ import annotations

import ast
import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_SOURCE = ROOT / "fichero-server" / "src" / "fichero_server" / "api" / "change_stream.py"
SWIFT_SOURCE = ROOT / "fichero" / "fichero" / "Services" / "LibraryChangeStream.swift"
RULE_DOC = "#4211"

# Engine fields the Swift client deliberately does not decode. Each needs a
# reason: an unexplained entry here is indistinguishable from an oversight.
ENGINE_ONLY_FIELDS: dict[str, str] = {
    "artifact_ids": "no artifact-scoped store on the client yet",
    "interpretation_ids": "no interpretation-scoped store on the client yet",
    "metadata": "free-form diagnostic payload; nothing client-side reads it",
    "origin_user": "multi-user self-echo de-dup is server-side (#2023)",
    "event_id": "replay bookkeeping; the client reconnects rather than replays",
    "replay_required": "replay bookkeeping (see event_id)",
    "gap_reason": "replay bookkeeping (see event_id)",
    "dropped_event_count": "replay bookkeeping (see event_id)",
    "last_event_id": "replay bookkeeping (see event_id)",
    "oldest_available_event_id": "replay bookkeeping (see event_id)",
    "latest_available_event_id": "replay bookkeeping (see event_id)",
    "document_parents": (
        "#4205 — engine-only TODAY, but the client SHOULD consume it: it is what "
        "lets the import filter skip documents it cannot be showing. Remove this "
        "entry when LibraryChangeStream decodes it. NOTE the contract: an id "
        "ABSENT from the map means 'parent unknown, fetch it', NEVER 'root'."
    ),
}

_CODING_KEYS = re.compile(r"enum\s+CodingKeys\s*:[^{]*\{(.*?)\n\s*\}", re.DOTALL)
_CASE = re.compile(r"case\s+(\w+)(?:\s*=\s*\"([^\"]+)\")?")


def python_fields(path: Path = PY_SOURCE) -> set[str]:
    """Field names on the Pydantic `ChangeEvent`, by AST rather than import.

    Parsing keeps this script standalone — the guardrail sweep runs it without
    the engine on PYTHONPATH.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ChangeEvent":
            return {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
    # #4487: parse resolved NOTHING from a present input — BLIND (exit 2),
    # not a violation (exit 1). "I could not read my own contract source"
    # must never share a code with "the contract is broken".
    print(
        f"BLIND: no ChangeEvent class found in {path} — the parser resolved "
        "nothing from a present input (#4487)",
        file=sys.stderr,
    )
    raise SystemExit(2)


def swift_wire_keys(path: Path = SWIFT_SOURCE) -> set[str]:
    """Wire names the Swift `ChangeEvent` decodes, from its CodingKeys enum.

    A bare `case actor` means the wire name IS the property name.

    The search starts AT `struct ChangeEvent` rather than at the top of the
    file. Taking the first CodingKeys in the file would silently compare a
    different Decodable type if one were ever declared above this one — and it
    would still PASS, which is the failure direction that hides.
    """
    source = path.read_text(encoding="utf-8")
    declaration = re.search(r"\bstruct\s+ChangeEvent\b", source)
    if not declaration:
        print(f"BLIND: no `struct ChangeEvent` found in {path} (#4487)", file=sys.stderr)
        raise SystemExit(2)

    match = _CODING_KEYS.search(source, declaration.end())
    if not match:
        print(f"BLIND: ChangeEvent has no CodingKeys enum in {path} (#4487)", file=sys.stderr)
        raise SystemExit(2)

    # Nothing may declare another type between ChangeEvent and its CodingKeys,
    # or the enum we just found belongs to that type instead.
    between = source[declaration.end() : match.start()]
    intruder = re.search(r"\b(?:struct|class|enum)\s+(\w+)", between)
    if intruder and intruder.group(1) != "CodingKeys":
        raise SystemExit(
            f"error: `{intruder.group(1)}` is declared between ChangeEvent and the "
            f"CodingKeys enum in {path}; the parsed keys may not be ChangeEvent's"
        )

    return {wire or swift for swift, wire in _CASE.findall(match.group(1))}


def scan() -> tuple[set[str], set[str]]:
    """(swift keys the engine does not send, engine fields Swift ignores)."""
    python = python_fields()
    swift = swift_wire_keys()
    return swift - python, python - swift


def main() -> int:
    # #4487 scan floor: both sides of the contract must resolve.
    # 22 engine fields / 10 Swift keys on 2026-08-02.
    require_scan_floor(len(python_fields()), 11, "ChangeEvent engine fields (22 on 2026-08-02)")
    require_scan_floor(len(swift_wire_keys()), 5, "Swift ChangeEvent wire keys (10 on 2026-08-02)")
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    undelivered, unconsumed = scan()
    known = set(ENGINE_ONLY_FIELDS)

    if "--list" in argv:
        print(f"Swift decodes {len(swift_wire_keys())} of {len(python_fields())} engine fields.\n")
        for field in sorted(unconsumed):
            tag = "known" if field in known else "NEW"
            print(f"  [{tag}] engine-only: {field}")
        return 0

    new_unconsumed = sorted(unconsumed - known)
    stale = sorted(known - unconsumed)

    print("ChangeEvent contract: fichero_server.api.change_stream <-> LibraryChangeStream.swift")
    print(f"  {len(swift_wire_keys())} Swift keys; {len(python_fields())} engine fields.")

    if stale:
        print(f"\n  {len(stale)} ENGINE_ONLY_FIELDS entr(ies) no longer apply; remove them:")
        for field in stale:
            print(f"      {field}")

    if undelivered:
        print(f"\n  {len(undelivered)} Swift key(s) the engine DOES NOT SEND:")
        for field in sorted(undelivered):
            print(f"      {field}")
        print(
            "\nThe client is decoding a field that no longer exists, so it silently\n"
            "receives nil. Rename or remove it in LibraryChangeStream.swift, or add\n"
            f"the field back to ChangeEvent. Rule pointer: {RULE_DOC}."
        )
        return 1

    if new_unconsumed:
        print(f"\n  {len(new_unconsumed)} NEW engine field(s) the client does not decode:")
        for field in new_unconsumed:
            print(f"      {field}")
        print(
            "\nDecide deliberately: should LibraryChangeStream decode this, or is it\n"
            "engine bookkeeping? If the client should use it, wire it up. If not, add\n"
            f"it to ENGINE_ONLY_FIELDS with a reason. Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n✗ Stale ENGINE_ONLY_FIELDS entries (listed above).")
        return 1

    print("\nPASS engine and app agree on the ChangeEvent wire contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
