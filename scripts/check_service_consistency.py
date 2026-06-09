#!/usr/bin/env python3
"""Service-consistency guardrail — flag services bypassing the generated client.

Rule (#1943): feature services in `fichero/fichero/Services` should call the
generated OpenAPI client (`FicheroClient` / `client.api.*`) instead of raw
`URLSession` or hand-built `URLRequest` glue.

This detector strips comments, scans `Services/*.swift`, and flags transport
signals such as `URLSession`, `URLRequest`, `URLComponents`, `httpMethod`, and
manual header/body mutation. Low-level client/backend infrastructure is excluded
because it is the transport layer itself. `KNOWN_VIOLATIONS` is the current
backlog: the script exits 0 while only those files are found, and exits 1 for a
new bypass. See docs/ROADMAP.md for the guardrail roadmap.

Usage:
    python3 scripts/check_service_consistency.py
    python3 scripts/check_service_consistency.py --list
    python3 scripts/check_service_consistency.py -h
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = ROOT / "fichero" / "fichero" / "Services"
RULE_DOC = "docs/ROADMAP.md"

TRANSPORT_PATTERNS: dict[str, re.Pattern[str]] = {
    "raw URLSession": re.compile(r"\bURLSession\b"),
    "hand-built URLRequest": re.compile(r"\bURLRequest\s*\("),
    "manual URLComponents": re.compile(r"\bURLComponents\b"),
    "manual httpMethod": re.compile(r"\.httpMethod\s*="),
    "manual request body": re.compile(r"\.httpBody\s*="),
    "manual request headers": re.compile(r"\.(?:setValue|addValue)\s*\("),
}

INFRASTRUCTURE_FILES = {
    "APIClient.swift",
    "APIClient+Types.swift",
    "APIEndpoints.swift",
    "EmbeddedBackendService.swift",
    "EngineConfig.swift",
    "LibraryChangeStream.swift",
}

# Current generated-client migration backlog. Drop entries as services move to
# FicheroClient / generated OpenAPI operations.
KNOWN_VIOLATIONS: dict[str, str] = {
    "AppleScriptSupport.swift": "#1943 — AppleScript bridge still uses raw URLSession/URLRequest",
    "ArtifactServiceGenerated.swift": "#1943 — generated artifact service still has raw transport helpers",
    "BatchServiceGenerated.swift": "#1943 — generated batch service still has raw transport helper",
    "ImageEditingServiceGenerated.swift": "#1943 — image editing service still hand-builds image endpoints",
    "StorageServiceGenerated.swift": "#1943 — storage service still uses raw URLSession/URLRequest",
    "WorkflowServiceGenerated.swift": "#1943 — workflow service still has raw preview transport helper",
    "WorkflowStreamService.swift": "#1943 — SSE stream still uses raw URLSession",
}

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"(?<!:)//.*")


def code_only(text: str) -> str:
    text = BLOCK_COMMENT.sub("", text)
    return "\n".join(LINE_COMMENT.sub("", line) for line in text.splitlines())


def is_excluded(path: Path) -> bool:
    return path.name in INFRASTRUCTURE_FILES


def violations_for(path: Path) -> list[str]:
    src = code_only(path.read_text(errors="ignore"))
    reasons = [
        reason
        for reason, pattern in TRANSPORT_PATTERNS.items()
        if reason != "manual URLComponents" and pattern.search(src)
    ]
    if reasons and TRANSPORT_PATTERNS["manual URLComponents"].search(src):
        reasons.append("manual URLComponents")
    return reasons


def scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in sorted(SERVICES_DIR.glob("*.swift")):
        if is_excluded(path):
            continue
        reasons = violations_for(path)
        if reasons:
            found[path.name] = reasons
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Service consistency offenders ({len(found)} file(s)):\n")
        for name, reasons in sorted(found.items()):
            tag = "known" if name in known else "NEW"
            print(f"  [{tag}] {name}")
            for reason in reasons:
                print(f"          - {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Service-consistency guardrail: scanned {SERVICES_DIR.relative_to(ROOT)}/*.swift")
    print(f"  {len(found)} service file(s) bypass generated-client transport; {len(known)} known backlog entries.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for name in stale:
            print(f"      {name}")

    if new:
        print(f"\n  ✗ {len(new)} new service file(s) use raw transport:")
        for name in new:
            for reason in found[name]:
                print(f"      {name}  ←  {reason}")
        print(
            "\nFix: route endpoint calls through FicheroClient / generated OpenAPI "
            f"operations, or add a documented migration backlog entry. Rule: {RULE_DOC}."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No service-consistency offenders beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
