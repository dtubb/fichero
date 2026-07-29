#!/usr/bin/env python3
"""Every TCP launcher must serve the wrapper, not the bare app (#4222).

The sharing control surface is a normal FastAPI route on
``fichero_server.api.main:app`` — so it keeps its OpenAPI schema and generated Swift
client — and is withheld from remote callers by ``fichero_server.api.tcp_transport``,
which 404s it at the TCP entry point.

That guarantee lives at the ENTRY POINT, which means it holds only while every
TCP launcher uses the wrapper. A launcher that reaches for the obvious
``fichero_server.api.main:app`` silently loses it: no error, no failing test, an open
door to the route that opens ports. This check is what makes that a failing
gate instead of something everyone has to remember.

It is the same fix as the ChangeEvent field-set check (#4211): a real
constraint that neither the type system nor codegen can see, so it needs a
guardrail or it does not exist.

ALLOWLIST_REASONS holds the call sites that legitimately serve the raw app —
each with a reason, because an unexplained exemption is indistinguishable from
an oversight. Entries that stop matching are reported, so the list cannot rot.

Usage:
    scripts/check_tcp_transport_wrapper.py
    scripts/check_tcp_transport_wrapper.py --list
    scripts/check_tcp_transport_wrapper.py --help
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BARE_APP = "fichero_server.api.main:app"
WRAPPER = "fichero_server.api.tcp_transport:app"
RULE_DOC = "#4222"

SEARCH_ROOTS = (
    ROOT / "fichero-server" / "src",
    ROOT / "fichero-server" / "scripts",
    ROOT / "fichero-server" / "tests",
    ROOT / "scripts",
)
SEARCHED_SUFFIXES = (".py", ".sh")

#: Call sites that may serve the bare app, keyed "relative/path.py". Each needs
#: a reason naming WHY the wrapper would defeat the purpose of that call site.
ALLOWLIST_REASONS: dict[str, str] = {
    "scripts/check_tcp_transport_wrapper.py": (
        "this checker — it must name the string it searches for"
    ),
    "fichero-server/src/fichero_server/api/tcp_transport.py": (
        "the wrapper itself — it imports the bare app in order to wrap it"
    ),
    "fichero-server/src/fichero_server/api/main.py": (
        "module docstring shows the bare uvicorn invocation for dev reference"
    ),
    "fichero-server/tests/integration/test_transport_round_trips.py": (
        "drives a real HTTPS listener to prove the transport works; wrapping "
        "would test the wrapper instead of the transport (#4176)"
    ),
    "fichero-server/tests/integration/test_cli_engine_contract.py": (
        "exercises the CLI against a raw engine; the control surface is not "
        "part of that contract"
    ),
    "fichero-server/tests/integration/_cli_live.py": (
        "shared live-engine helper for the CLI contract tests (see above)"
    ),
    "fichero-server/tests/integration/test_cli_generated_multiuser_auth_writes.py": (
        "multiuser auth-write coverage against a raw engine; unrelated surface"
    ),
    "fichero-server/tests/unit/test_bind_host.py": (
        "NEGATIVE assertion — `cmd[-1] != \"fichero_server.api.main:app\"` checks the "
        "UDS launch does not serve the TCP app, so it must name the string it "
        "excludes. It is not a launcher."
    ),
}


def _searched_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for suffix in SEARCHED_SUFFIXES:
            files.extend(p for p in root.rglob(f"*{suffix}") if "__pycache__" not in p.parts)
    return sorted(set(files))


def scan() -> dict[str, list[int]]:
    """{"relative/path": [line numbers]} for files naming the bare app."""
    found: dict[str, list[int]] = {}
    pattern = re.compile(re.escape(BARE_APP))
    for path in _searched_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        hits = [i for i, line in enumerate(lines, 1) if pattern.search(line)]
        if hits:
            found[path.relative_to(ROOT).as_posix()] = hits
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(ALLOWLIST_REASONS)

    if "--list" in argv:
        print(f"Files naming `{BARE_APP}` ({len(found)}):\n")
        for rel, lines in sorted(found.items()):
            tag = "known" if rel in known else "NEW"
            print(f"  [{tag}] {rel}:{','.join(map(str, lines))}")
        return 0

    offenders = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"TCP transport wrapper: {len(found)} file(s) name `{BARE_APP}`; {len(known)} allowed.")

    if stale:
        print(f"\n  {len(stale)} ALLOWLIST_REASONS entr(ies) no longer match; remove them:")
        for rel in stale:
            print(f"      {rel}")

    if offenders:
        print(f"\n  {len(offenders)} launcher(s) serving the BARE app:")
        for rel in offenders:
            print(f"      {rel}:{','.join(map(str, found[rel]))}")
        print(
            f"\nA TCP listener on the bare app exposes the local-only control surface\n"
            f"to remote callers. Serve `{WRAPPER}` instead, or add the file to\n"
            f"ALLOWLIST_REASONS with a reason. Rule pointer: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n✗ Stale ALLOWLIST_REASONS entries (listed above).")
        return 1

    print("\nPASS every TCP launcher serves the wrapper.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
