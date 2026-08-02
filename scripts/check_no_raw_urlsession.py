#!/usr/bin/env python3
"""Ban raw URLSession in the OpenAPI transport package (#2393).

Hand-rolled `URLSession` paths silently bypass the pinned-HTTPS transport (cert
pinning) and engine auth (`addEngineAuth` / the generated `FicheroAPIClient`
contract) — the #2392 class ("Activity shows nothing because it hand-rolled a
request that skips pinning+auth").

Two scopes own this rule:

  • The APP (`fichero/fichero/**`) is ALREADY guarded by
    `scripts/check_swift_transport.py` rule 1 — any raw `URLSession(` /
    `URLSession.shared` that is not the pinned `RemoteCertificatePinning`
    session is a regression there.

  • The generated OpenAPI client PACKAGE (`fichero/fichero-api-client/
    Sources/**`) is NOT in that check's scope. It is the one approved transport
    layer, so the ONLY file allowed to touch a raw `URLSession` is the pinned-
    session owner, `RemoteCertificatePinning.swift`. Any other file in the
    package that constructs or sends on a raw session (a new middleware, a
    helper) bypasses pinning and must fail.

This guardrail closes that package gap. It bans `URLSession(`,
`URLSession.shared`, `.dataTask`, `.data(for:`, `.bytes(for:`, `.download(for:`
and `.upload(for:` anywhere in the package except the allowlisted transport
file(s). Baseline is CLEAN.

Usage:
    scripts/check_no_raw_urlsession.py
    scripts/check_no_raw_urlsession.py --list
    scripts/check_no_raw_urlsession.py --help
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = ROOT / "fichero" / "fichero-api-client" / "Sources"
RULE_DOC = "docs/contributor/architecture/fichero/api_client.md"

# The ONLY approved transport file(s) in the package: the pinned-session owner.
ALLOWLIST: set[str] = {"RemoteCertificatePinning.swift"}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")
_RAW_SESSION_RE = re.compile(
    r"URLSession\s*\(|URLSession\s*\.\s*shared|\.dataTask\b|"
    r"\.data\s*\(\s*for:|\.bytes\s*\(\s*for:|\.download\s*\(\s*for:|\.upload\s*\(\s*for:"
)

# Clean: only RemoteCertificatePinning.swift (allowlisted) touches raw URLSession.
KNOWN_VIOLATIONS: dict[str, str] = {}


def _code(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def scan(package_dir: Path = PACKAGE_DIR) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(package_dir.rglob("*.swift")):
        if path.name in ALLOWLIST:
            continue
        try:
            source = _code(path.read_text(errors="ignore"))
        except OSError:
            continue
        try:
            rel = path.relative_to(package_dir).as_posix()
        except ValueError:
            rel = path.name
        for idx, line in enumerate(source.splitlines(), start=1):
            m = _RAW_SESSION_RE.search(line)
            if m:
                found[f"{rel}:{idx}"] = f"raw URLSession transport `{m.group(0).strip()}`"
    return found


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in argv:
        print(f"Raw URLSession in OpenAPI client package ({len(found)}):")
        print(f"  allowlisted transport file(s): {', '.join(sorted(ALLOWLIST))}\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    # #4487 scan floor: 20 package Swift files on 2026-08-02.
    require_scan_floor(
        sum(1 for _ in PACKAGE_DIR.rglob("*.swift")), 10,
        "api-client Swift files (20 on 2026-08-02)",
    )
    print("Raw-URLSession ban — OpenAPI client package (#2393):")
    print(f"  scanned {PACKAGE_DIR.relative_to(ROOT)} (allowlist: {', '.join(sorted(ALLOWLIST))})")
    print(f"  {len(found)} raw-transport site(s); {len(known)} known.")

    if new:
        print(f"\n  ✗ {len(new)} raw URLSession outside the pinned transport:")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: route through the pinned RemoteCertificatePinning session and the "
            f"generated FicheroAPIClient. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entr(ies) now clean — drop them:")
        for key in stale:
            print(f"      {key}")

    print("\n✓ Only the pinned transport file touches raw URLSession in the client package.")
    return 0


def _require_scan_roots_4382(*roots):
    """#4382: a guardrail must know when it has gone blind, and say so.

    A missing scan root means "I could not check" (exit 2) -- never a silent
    exit 0. Distinct from exit 1 ("I checked and found violations"), so a
    moved or renamed directory can never disable this guardrail while the
    gate stays green.
    """
    import sys as _sys

    flat = []
    for root in roots:
        flat.extend(root if isinstance(root, (tuple, list)) else [root])
    missing = [str(r) for r in flat if not r.exists()]
    if missing:
        print(
            f"{__file__.rsplit('/', 1)[-1]}: BLIND -- scan root(s) missing: "
            + ", ".join(missing)
            + " (the tree moved; update this guardrail's paths)",
            file=_sys.stderr,
        )
        _sys.exit(2)


if __name__ == "__main__":
    _require_scan_roots_4382(PACKAGE_DIR)
    raise SystemExit(main())
