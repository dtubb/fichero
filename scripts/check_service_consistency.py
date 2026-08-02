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
new bypass. See agents/ROADMAP.md for the guardrail roadmap.

Usage:
    python3 scripts/check_service_consistency.py
    python3 scripts/check_service_consistency.py --list
    python3 scripts/check_service_consistency.py -h
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = ROOT / "fichero" / "fichero" / "Services"
RULE_DOC = "agents/ROADMAP.md"

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
    "ActionInvokeService.swift": "#1848 — action layer cli-only, store/UI deferred",
    "ImageEditingService.swift": "#1943 — image editing service still hand-builds image endpoints",
    "WorkflowService.swift": "#1943 — workflow service still has raw preview transport helper",
}

# Raw transport that is intentionally allowed because the generated client
# cannot preserve the current binary/flexible-decoding behavior. These are not
# backlog entries; each needs a one-line reason to stay sanctioned.
SANCTIONED_RAW_TRANSPORT: dict[str, str] = {
    "ActivityStreamService.swift": (
        "#1943 — /api/activity/stream is an infinite text/event-stream SSE feed; "
        "the generated client cannot surface it incrementally, so this pinned "
        "URLSession byte stream derives base URL and library context from the "
        "same generated-client transport as the typed activity endpoints"
    ),
    "ChangeStreamTransport.swift": (
        "#1943/#2518 — library change-stream is an infinite SSE feed; generated "
        "operations buffer the response body, so the pinned raw stream remains "
        "the sanctioned transport for incremental change events"
    ),
    "EngineReadinessProbe.swift": (
        "#3106 — readiness bootstrap must probe health/registry before the "
        "generated client and signed-in library context are usable"
    ),
    "EntityService.swift": (
        "#1943 — remaining raw helpers (split out of ArtifactService.swift) "
        "decode flexible citation/classification/hermeneutics payloads that generated "
        "types expose as untyped containers"
    ),
    "WorkflowStreamService.swift": (
        "#1943/#2538 — the generated streamWorkflowEvents… operation buffers its "
        "200 body via getResponseBodyAsJSON (OpenAPI schema declares application/json, "
        "not a streaming text/event-stream body), so it can never surface an infinite "
        "SSE HTTPBody. The raw byte stream now derives host, library path, auth and "
        "certificate pinning from the SAME FicheroClient the execute/stop/resume calls "
        "use, so it shares the generated transport's pinning/auth and cannot drift (#2376)."
    ),
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
    sanctioned = set(SANCTIONED_RAW_TRANSPORT)

    if "--list" in sys.argv[1:]:
        print(f"Service consistency offenders ({len(found)} file(s)):\n")
        for name, reasons in sorted(found.items()):
            if name in sanctioned:
                tag = "sanctioned"
            elif name in known:
                tag = "known"
            else:
                tag = "NEW"
            print(f"  [{tag}] {name}")
            for reason in reasons:
                print(f"          - {reason}")
            if name in sanctioned:
                print(f"          reason: {SANCTIONED_RAW_TRANSPORT[name]}")
        return 0

    allowed = known | sanctioned
    new = sorted(set(found) - allowed)
    stale = sorted(known - set(found))
    stale_sanctioned = sorted(sanctioned - set(found))

    # #4487 scan floor: flat glob by design (top-level services only).
    require_scan_floor(
        sum(1 for _ in SERVICES_DIR.glob("*.swift")), 30, "service files (~70 on 2026-08-02)"
    )
    print(f"Service-consistency guardrail: scanned {SERVICES_DIR.relative_to(ROOT)}/*.swift")
    print(
        f"  {len(found)} service file(s) bypass generated-client transport; "
        f"{len(known)} known backlog entries; {len(sanctioned)} sanctioned."
    )

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for name in stale:
            print(f"      {name}")

    if stale_sanctioned:
        print(f"\n  ✓ {len(stale_sanctioned)} SANCTIONED_RAW_TRANSPORT entry now CLEAN — drop from the set:")
        for name in stale_sanctioned:
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

    if stale or stale_sanctioned:
        print("\n(Allowlist has stale entries — clean them up when convenient.)")

    print("\n✓ No service-consistency offenders beyond the known backlog.")
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
    _require_scan_roots_4382(SERVICES_DIR)
    raise SystemExit(main())
