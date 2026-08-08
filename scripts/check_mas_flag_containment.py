#!/usr/bin/env python3
"""The MAS build flag gates code ONLY in EmbeddedBackendService+Ports.swift.

Three times in one day (2026-08-08) an `#if FICHERO_APP_STORE` turned out to
be a stale proxy for "are we sandboxed" — a premise that died when every
config became sandboxed on 2026-07-29. The live one compiled the engine
bookmark handoff to a no-op in every non-MAS build (zero grants, folder
drops 403ing). The ONE legitimate use is binary-content policy in
EmbeddedBackendService+Ports.swift: compiling pgrep/ps/lsof/kill machinery
out of the reviewed MAS binary — a runtime guard there would put those
strings back in front of App Review.

Rule: an `#if` on FICHERO_APP_STORE may appear in that one file and nowhere
else under fichero/fichero/. Prose mentions in comments are fine (this scans
compiler directives, not words); a new sandbox-flavored need must use the
runtime `SandboxEnvironment.isSandboxed`.

Exit codes (blind vs not-armed, AGENTS.md rule 0):
  0  pass
  1  violation — the flag gates code outside the allowlist
  2  BLIND — the scan found no Swift files or not even the allowlisted use
     (a scanner that finds nothing is indistinguishable from a broken one)

Usage:
  python3 scripts/check_mas_flag_containment.py [--self-test]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = REPO_ROOT / "fichero" / "fichero"
ALLOWLIST = {"Services/EmbeddedBackendService+Ports.swift"}
# Anchored to line start (whitespace only before the directive): a compiler
# directive must begin its line, while a PROSE mention — SandboxEnvironment's
# doc comment quotes "`#if FICHERO_APP_STORE`" mid-line — must not trip the
# scan. Caught live by the first run of this very check.
GATE = re.compile(r"^\s*#(?:if|elseif)\s+!?\s*FICHERO_APP_STORE\b", re.MULTILINE)


def scan(sources: dict[str, str]) -> tuple[list[str], int]:
    """(offender paths, allowlisted-gate count) over {relpath: content}."""
    offenders: list[str] = []
    allowlisted_gates = 0
    for relpath, content in sorted(sources.items()):
        hits = len(GATE.findall(content))
        if not hits:
            continue
        if relpath in ALLOWLIST:
            allowlisted_gates += hits
        else:
            offenders.append(f"{relpath}: {hits} gate(s)")
    return offenders, allowlisted_gates


def load_sources() -> dict[str, str]:
    return {
        str(path.relative_to(SWIFT_ROOT)): path.read_text(encoding="utf-8", errors="replace")
        for path in SWIFT_ROOT.rglob("*.swift")
    }


def self_test() -> None:
    """Prove the check FIRES on a synthesized violation, and stays green
    without one — never borrowing its violation from live debt."""
    clean = {
        "Services/EmbeddedBackendService+Ports.swift": "#if !FICHERO_APP_STORE\nfunc a() {}\n#endif\n",
        "Services/Innocent.swift": "// prose mention of FICHERO_APP_STORE is fine\n",
        # The live false positive the first run caught: a doc comment QUOTING
        # the directive mid-line must not fire.
        "Services/QuotesIt.swift": "/// The proxy was `#if FICHERO_APP_STORE`, historically.\n",
    }
    offenders, gates = scan(clean)
    assert offenders == [] and gates == 1, (offenders, gates)

    dirty = dict(clean)
    dirty["Models/Sneaky.swift"] = "#if FICHERO_APP_STORE\nlet x = 1\n#endif\n"
    offenders, _ = scan(dirty)
    assert offenders == ["Models/Sneaky.swift: 1 gate(s)"], offenders

    print("[ok] self-test: fires on a synthesized out-of-allowlist gate; prose is ignored")


def main() -> None:
    if "--self-test" in sys.argv[1:]:
        self_test()
        return

    sources = load_sources()
    if not sources:
        print(f"BLIND: no Swift files found under {SWIFT_ROOT}")
        sys.exit(2)
    offenders, allowlisted_gates = scan(sources)
    if offenders:
        print("FAIL: FICHERO_APP_STORE gates code outside the one allowlisted file.")
        print("The flag is binary-content policy for the MAS review; 'am I sandboxed'")
        print("is answered at RUNTIME by SandboxEnvironment.isSandboxed (see the")
        print("2026-08-08 zero-grants defect).")
        for offender in offenders:
            print(f"  - {offender}")
        sys.exit(1)
    if allowlisted_gates == 0:
        # The allowlisted use vanished: either the machinery was legitimately
        # removed (update the allowlist and this message) or the scanner has
        # gone blind. Refuse to guess which.
        print("BLIND: found no FICHERO_APP_STORE gate even in the allowlisted file —")
        print("if +Ports.swift legitimately dropped the flag, update ALLOWLIST here.")
        sys.exit(2)
    print(f"[ok] MAS flag gates code only in the allowlisted file ({allowlisted_gates} gate(s))")


if __name__ == "__main__":
    main()
