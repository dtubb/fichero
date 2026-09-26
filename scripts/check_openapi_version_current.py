#!/usr/bin/env python3
"""Fail when the committed OpenAPI contract's ``info.version`` lags the code (#5046).

`check_openapi_version_regression.py` (#4199) refuses a sync that would move
`info.version` BACKWARDS. That is a real property, and a different one: a
contract frozen four releases behind never regresses, so it passes forever.

Which is what happened. On 2026-09-26 `pyproject.toml` said 2026.9.20, every
committed `openapi.json` said 2026.9.8, and v2026.09.20 had shipped six days
earlier. The canonical venv had drifted, the regeneration correctly refused,
and the refusal was answered by `sed`-ing the one field it named — so the
contract quietly stopped tracking the code while every check stayed green.

Ruled 2026-09-26: `info.version` ALWAYS equals `pyproject.toml`. A rule that
only binds at release boundaries is invisible in between, which is precisely
how the drift reached four releases.

Spec: docs/contributor_manual/specs/harness/version-and-contract-integrity.md
      behaviour `contract.version-tracks-code`

Exit codes:
    0  every contract matches pyproject
    1  a contract lags (or leads) the code — regenerate, never hand-edit
    2  BLIND: an input could not be read or parsed. Never silently "pass".

Usage:
    check_openapi_version_current.py [--repo-root .]
    check_openapi_version_current.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

# Every committed copy of the contract. The sync regenerates them together, so
# they must agree together — a hand-edit updates one and leaves the rest behind
# while the shadow-type and client-parity guardrails still report green.
CONTRACTS = (
    "fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json",
    "fichero-server/tests/contracts/openapi.json",
    "docs/contributor_manual/api-reference/openapi.json",
)
PYPROJECT = "fichero-server/pyproject.toml"

_VERSION_LINE = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)


class Blind(Exception):
    """An input could not be read. The check has gone blind, it has not passed."""


def code_version(repo_root: Path) -> str:
    path = repo_root / PYPROJECT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Blind(f"cannot read {path}: {exc}") from exc
    match = _VERSION_LINE.search(text)
    if not match:
        raise Blind(f"no version declared in {path}")
    return match.group(1)


def contract_version(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Blind(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Blind(f"cannot parse {path}: {exc}") from exc
    try:
        return payload["info"]["version"]
    except (KeyError, TypeError) as exc:
        raise Blind(f"no info.version in {path}") from exc


def check(repo_root: Path) -> int:
    expected = code_version(repo_root)
    print(f"pyproject.toml declares {expected}")

    stale = []
    for relative in CONTRACTS:
        path = repo_root / relative
        # A missing contract is BLIND, not "nothing to check". The floor is that
        # every listed copy was actually read (AGENTS.md rule 0).
        found = contract_version(path)
        marker = "ok" if found == expected else "STALE"
        print(f"  [{marker}] {found}  {relative}")
        if found != expected:
            stale.append((relative, found))

    if not stale:
        print(f"\nAll {len(CONTRACTS)} contracts match the code.")
        return 0

    print(f"\n{len(stale)} contract(s) do not match the code ({expected}):")
    for relative, found in stale:
        print(f"  {relative} says {found}")
    print(
        "\nRegenerate — never hand-edit info.version (AGENTS.md rule 3):\n"
        "  FICHERO_PYTHON_BIN=/path/to/a/.venv/bin/python \\\n"
        "    ./fichero-server/scripts/sync_openapi_schema.sh\n"
        "A refusal from the #4199 guard means the ENVIRONMENT is wrong: the\n"
        "canonical venv is editable-installed against the main checkout and\n"
        "drifts. Point the script at a current install (#5043)."
    )
    return 1


def self_test() -> int:
    """Synthesise a stale contract and prove it is caught — never borrowed from
    the real tree, which could shrink to nothing and make this vacuous."""
    failures = []

    def case(name: str, ok: bool) -> None:
        print(f"  {'✓' if ok else '✗'} {name}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "fichero-server").mkdir(parents=True)
        (root / PYPROJECT).write_text('[project]\nversion = "9999.9.9"\n')
        for relative in CONTRACTS:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"info": {"version": "9999.9.9"}}))

        case("a matching tree passes", check(root) == 0)

        stale_path = root / CONTRACTS[0]
        stale_path.write_text(json.dumps({"info": {"version": "1111.1.1"}}))
        case("a stale contract FAILS", check(root) == 1)

        stale_path.write_text("{ not json")
        blind = False
        try:
            check(root)
        except Blind:
            blind = True
        case("unparseable input goes BLIND, not pass", blind)

        stale_path.unlink()
        blind = False
        try:
            check(root)
        except Blind:
            blind = True
        case("a MISSING contract goes BLIND, not pass", blind)

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
