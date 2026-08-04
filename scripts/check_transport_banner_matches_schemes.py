#!/usr/bin/env python3
"""The engine's transport banner must match what the Xcode schemes actually set.

WHY THIS EXISTS (#4222, and a live incident on 2026-08-04)

The UDS banner told a reader:

    NOT dialled by: Fichero (Dev Local) — that scheme is debugExternal,
    which expects https://127.0.0.1:8765 and will never reach this socket
    To use Dev Local instead, restart without --uds

Every clause was backwards. `Fichero (Dev Local)` is the ONE scheme that sets
`FICHERO_FORCE_UDS_PATH`, so it is the one scheme that dials the socket and
CANNOT reach the loopback port. Following the banner's advice — restarting
without --uds — is guaranteed to leave the app unable to connect, which is
exactly what happened: the engine ran on 8765 while the app dialled the socket
and reported "No external engine reachable".

Nothing was red. A banner is prose, and prose has no test, so it drifted when
Dev Local moved to UDS and nothing forced it back.

WHAT THIS CHECKS

Two facts, read from the two files that disagreed:

1. Which schemes enable `FICHERO_FORCE_UDS_PATH` (from the .xcscheme files).
2. What the banner claims about Dev Local in each mode (from the source).

and asserts they agree. It does not check prose style; it checks that the
banner does not tell a UDS-dialling scheme it cannot dial UDS.

NOT ARMED (exit 2) if it cannot find the schemes or the banner — a check that
silently finds nothing is the defect it exists to catch.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMES = ROOT / "fichero/fichero.xcodeproj/xcshareddata/xcschemes"
BANNER = ROOT / "fichero-server/src/fichero_server/api/transport_diagnostics.py"

UDS_KEY = "FICHERO_FORCE_UDS_PATH"


def schemes_forcing_uds() -> set[str]:
    """Scheme names whose environment ENABLES the UDS override."""
    forcing: set[str] = set()
    for path in sorted(SCHEMES.glob("*.xcscheme")):
        text = path.read_text(encoding="utf-8", errors="replace")
        # The key, then its value, then isEnabled — all inside one element.
        for match in re.finditer(
            rf'key\s*=\s*"{UDS_KEY}".*?isEnabled\s*=\s*"(YES|NO)"',
            text,
            re.DOTALL,
        ):
            if match.group(1) == "YES":
                forcing.add(path.stem)
    return forcing


def main() -> int:
    if not SCHEMES.is_dir():
        print(f"NOT ARMED: no scheme directory at {SCHEMES}", file=sys.stderr)
        return 2
    scheme_files = list(SCHEMES.glob("*.xcscheme"))
    if not scheme_files:
        print(f"NOT ARMED: no .xcscheme files under {SCHEMES}", file=sys.stderr)
        return 2
    if not BANNER.is_file():
        print(f"NOT ARMED: no transport banner at {BANNER}", file=sys.stderr)
        return 2

    banner = BANNER.read_text(encoding="utf-8")
    if "def transport_banner" not in banner:
        print("NOT ARMED: transport_banner() not found in the banner module", file=sys.stderr)
        return 2

    forcing = schemes_forcing_uds()
    violations: list[str] = []

    # The whole bug in one assertion: a scheme that forces UDS must not be
    # named as something that cannot reach the socket.
    uds_section = banner.split("if binding.is_uds:", 1)
    if len(uds_section) != 2:
        print("NOT ARMED: could not locate the UDS branch of the banner", file=sys.stderr)
        return 2
    uds_text = uds_section[1].split("return", 1)[0]

    # The clause may wrap over several lines; take a window from each match.
    lines = uds_text.splitlines()
    not_dialled = ""
    for i, line in enumerate(lines):
        if "NOT dialled" in line:
            not_dialled += "\n" + "\n".join(lines[i : i + 4])

    for scheme in sorted(forcing):
        # Match the full name AND the short form the prose actually uses.
        # The first version of this check looked only for "Fichero (Alpha
        # Local)" and passed a banner that said "Dev/Alpha/Beta/Release Local"
        # — the abbreviation nobody thought to match. A detector that cannot
        # see the bad case is the defect it exists to catch.
        short = scheme.removeprefix("Fichero (").removesuffix(")")
        family = short.removesuffix(" Local").removesuffix(" Embedded")
        aliases = {scheme, short}
        if short.endswith(" Local"):
            # "Dev/Alpha/Beta/Release Local" style enumerations.
            aliases.add(f"{family}/")
            aliases.add(f"/{family}")
        if any(alias in not_dialled for alias in aliases):
            violations.append(
                f"{scheme} sets {UDS_KEY}=YES, so it DOES dial the socket — "
                f"but the UDS banner lists it under 'NOT dialled by' "
                f"(matched as one of: {', '.join(sorted(aliases))})"
            )

    if violations:
        print("transport banner contradicts the Xcode schemes:\n", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nThe banner is what a person reads when nothing connects. When it is "
            "wrong it does not merely fail to help — it sends them the wrong way.",
            file=sys.stderr,
        )
        return 1

    print(
        f"transport banner agrees with {len(scheme_files)} schemes "
        f"({len(forcing)} force UDS: {', '.join(sorted(forcing)) or 'none'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
