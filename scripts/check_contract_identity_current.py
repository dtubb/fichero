#!/usr/bin/env python3
"""Fail when the baked contract identity does not hash the committed contract (#5047).

`check_openapi_version_current.py` binds every contract's ``info.version`` to
``pyproject.toml``. This binds the contract's DIGEST to the contract, which is a
different property and was unguarded.

WHY IT EXISTS. On 2026-09-26, merging `integration` into `spec/page-model` put
two correct branches into an incorrect state with nobody editing anything. The
merge brought `integration`'s `contract_identity_generated.py`, whose
`CONTRACT_SHA256` hashes `integration`'s contract; the feature branch's contract
was a different document (slice 8 had added three paths, two schemas and two
anchor fields). So the baked digest no longer hashed the contract beside it.

A runtime contract mismatch REFUSES a remote connection — the engine bakes the
identity, the client hashes the same document, and a disagreement is a closed
door. That branch would have shipped an engine refusing remote connections, and
**the version guardrail could not see it**: `info.version` was 2026.9.20 on both
sides. Only the digest differed.

WHY THE EXISTING TEST DOES NOT COVER IT. `tests/unit/api/test_contract_identity.py`
asserts `CONTRACT_SHA256 == digest` — against a temp file it wrote itself
moments earlier. That proves the WRITER is correct and says nothing about the
committed pair. Checking the artefact the system actually consumes, rather than
the intention upstream of it, is the whole point of this file.

OFFLINE BY CONSTRUCTION. `verify_all.sh` auto-runs every `scripts/check_*.py`
with no arguments, so this reads files and nothing else: no network, no
database, no app construction, no imports from the package under test.

Exit codes:
    0  the baked digest hashes the committed contract
    1  they disagree — regenerate, never hand-edit
    2  BLIND: an input could not be read or parsed. Never silently "pass".

Usage:
    check_contract_identity_current.py [--repo-root .]
    check_contract_identity_current.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tempfile
from pathlib import Path

#: The contract the engine hashes. `export_openapi_schema.py` writes the
#: identity from the bytes it exported, and the three committed copies are
#: written from that same document, so any one of them is the right thing to
#: hash. This one is the engine's own test fixture copy, which is the closest to
#: what ships.
CONTRACT = "fichero-server/tests/contracts/openapi.json"
IDENTITY = "fichero-server/src/fichero_server/api/contract_identity_generated.py"

_SHA_LINE = re.compile(r'^\s*CONTRACT_SHA256\s*=\s*"([0-9a-fA-F]{64})"', re.MULTILINE)
_VERSION_LINE = re.compile(r'^\s*CONTRACT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


class Blind(Exception):
    """An input could not be read. The check has gone blind, it has not passed."""


def baked_identity(repo_root: Path) -> tuple[str, str]:
    """``(version, sha256)`` as baked into the engine package."""
    path = repo_root / IDENTITY
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Blind(f"cannot read {path}: {exc}") from exc
    sha = _SHA_LINE.search(text)
    if sha is None:
        raise Blind(
            f"no CONTRACT_SHA256 in {path} — a 64-character hex literal is "
            "expected, so either the generator changed shape or the file was "
            "hand-edited"
        )
    version = _VERSION_LINE.search(text)
    if version is None:
        raise Blind(f"no CONTRACT_VERSION in {path}")
    return version.group(1), sha.group(1).lower()


def contract_digest(repo_root: Path) -> str:
    """The sha256 of the committed contract's BYTES.

    Bytes, not parsed JSON re-serialised: the engine hashes what it exported, so
    anything that re-formats the document would compute a different digest and
    this check would be measuring its own formatting rather than the artefact.
    """
    path = repo_root / CONTRACT
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Blind(f"cannot read {path}: {exc}") from exc


def check(repo_root: Path) -> int:
    version, baked = baked_identity(repo_root)
    actual = contract_digest(repo_root)

    print(f"{IDENTITY}\n  CONTRACT_VERSION = {version}\n  CONTRACT_SHA256  = {baked}")
    print(f"{CONTRACT}\n  sha256           = {actual}")

    if baked == actual:
        print("\nThe baked identity hashes the committed contract.")
        return 0

    print(
        "\nMISMATCH: the baked digest does not hash the contract beside it.\n"
        "\n"
        "A runtime contract mismatch REFUSES a remote connection, so shipping\n"
        "this would ship an engine that turns remote clients away. The version\n"
        "guardrail cannot see this: both sides can agree on info.version while\n"
        "the digest disagrees.\n"
        "\n"
        "The usual cause is a MERGE, not an edit — a branch with its own\n"
        "contract changes taking another branch's identity file. Regenerate,\n"
        "never hand-edit the digest (AGENTS.md rule 3):\n"
        "  FICHERO_PYTHON_BIN=/path/to/a/.venv/bin/python \\\n"
        "    ./fichero-server/scripts/sync_openapi_schema.sh",
        file=sys.stderr,
    )
    return 1


def self_test() -> int:
    """Prove the check catches a mismatch, and goes blind rather than passing.

    Every case is SYNTHESISED in a temporary tree, never borrowed from the real
    repository — a self-test that reads the live tree passes vacuously the day
    the live tree is fine, which is every day until it matters.
    """
    failures: list[str] = []

    def case(name: str, ok: bool) -> None:
        print(f"  {'✓' if ok else '✗'} {name}")
        if not ok:
            failures.append(name)

    def build(root: Path, *, contract: bytes, sha: str | None, version: str = "1.2.3") -> None:
        (root / CONTRACT).parent.mkdir(parents=True, exist_ok=True)
        (root / IDENTITY).parent.mkdir(parents=True, exist_ok=True)
        (root / CONTRACT).write_bytes(contract)
        digest = hashlib.sha256(contract).hexdigest() if sha is None else sha
        (root / IDENTITY).write_text(
            f'"""generated"""\n\nCONTRACT_VERSION = "{version}"\n'
            f'CONTRACT_SHA256 = "{digest}"\n'
        )

    faithful = b'{"info": {"version": "1.2.3"}, "paths": {}}\n'

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, contract=faithful, sha=None)
        case("a faithful pair passes", check(root) == 0)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # The exact 2026-09-26 shape: a valid digest, of a DIFFERENT document.
        other = hashlib.sha256(b'{"info": {"version": "1.2.3"}, "paths": {"/a": {}}}\n').hexdigest()
        build(root, contract=faithful, sha=other)
        case("a digest of another document is caught", check(root) == 1)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, contract=faithful, sha=None)
        # One byte of the contract changes and nothing else — the smallest drift
        # this guard has to notice.
        (root / CONTRACT).write_bytes(faithful.replace(b"1.2.3", b"1.2.4"))
        case("a one-byte contract change is caught", check(root) == 1)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, contract=faithful, sha=None)
        (root / CONTRACT).unlink()
        blind = False
        try:
            check(root)
        except Blind:
            blind = True
        case("a MISSING contract goes BLIND, not pass", blind)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        build(root, contract=faithful, sha=None)
        (root / IDENTITY).write_text('"""generated"""\n\nCONTRACT_VERSION = "1.2.3"\n')
        blind = False
        try:
            check(root)
        except Blind:
            blind = True
        case("an identity file with NO digest goes BLIND, not pass", blind)

    if failures:
        print(f"\nself-test FAILED: {', '.join(failures)}")
        return 1
    print("\nself-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    try:
        return check(args.repo_root.resolve())
    except Blind as exc:
        print(f"BLIND: {exc}", file=sys.stderr)
        print("Refusing to report success on input I could not read.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
