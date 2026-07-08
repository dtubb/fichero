#!/usr/bin/env python3
"""Raw-URLSession ratchet for the APP (#1666 enforcement backfill).

The sibling `check_no_raw_urlsession.py` keeps the api-client PACKAGE clean;
this covers the app (`fichero/fichero/**`), which the package guard does not.
SwiftUI should display backend objects through the generated FicheroAPIClient;
custom transport is allowed only for the audited KEEP sites (SSE streams, engine
health/lifecycle, auth probe, multipart import — see
docs/contributor/architecture/swiftui/raw_urlsession_audit_1666.md) and only via the pinned
`RemoteCertificatePinning.configuredSession()`.

This is a RATCHET: every file that currently touches raw URLSession is
grandfathered in GRANDFATHERED_FILES, so the check passes today. A NEW file with
raw URLSession fails. As #3028/#3029/#3030 migrate the MIGRATE-list files onto
generated ops, delete them from the allowlist so it can only shrink — the check
reports stale entries to nudge that.

Usage:
    scripts/check_no_raw_urlsession_app.py           # gate mode
    scripts/check_no_raw_urlsession_app.py --list     # every hit incl. allowlisted
    scripts/check_no_raw_urlsession_app.py --self-test
    scripts/check_no_raw_urlsession_app.py --help

Exit codes:
    0  no NEW raw-URLSession file (and no stale allowlist entries)
    1  a new offender, or a stale allowlist entry to drop
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "fichero" / "fichero"
AUDIT_DOC = "docs/contributor/architecture/swiftui/raw_urlsession_audit_1666.md"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//.*")
_RAW_SESSION_RE = re.compile(
    r"URLSession\s*\(|URLSession\s*\.\s*shared|\.dataTask\b|"
    r"\.data\s*\(\s*for:|\.data\s*\(\s*from:|"
    r"\.bytes\s*\(\s*for:|\.download\s*\(\s*for:|\.upload\s*\(\s*for:"
)

# Every app file that touches raw URLSession today (audit baseline, #1666).
# KEEP = custom transport genuinely required (stays). MIGRATE = route through
# generated ops then delete the entry.
GRANDFATHERED_FILES: set[str] = {
    # KEEP
    "Services/EngineReadinessProbe.swift",      # readiness bootstrap: probes health/registry over RemoteCertificatePinning before the generated client is usable (#3106)
    "Models/DocumentStore+CRUD.swift",          # multipart import upload
    "Views/Library/QuickLookComponents.swift",  # binary source bytes for QuickLook
    "Services/ActivityStreamService.swift",     # SSE
    "Services/LibraryChangeStream.swift",       # SSE
    "Services/WorkflowStreamService.swift",     # SSE
    "Services/EmbeddedBackendService.swift",    # engine health / lifecycle
    # MIGRATE (delete when the sub-issue lands)
    "Services/ImageEditingServiceGenerated.swift",  # #3028 (binary preview KEEP)
    "Services/ArtifactServiceGenerated.swift",  # #3029 (entity free-form-container KEEP)
    "Services/WorkflowServiceGenerated.swift",  # #3029 (visualization.png binary KEEP; op mis-declares JSON)
}


def _code(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())


def raw_transport_files(app_dir: Path = APP_DIR) -> dict[str, list[int]]:
    """Rel path -> line numbers of raw-transport hits (comment-stripped)."""
    found: dict[str, list[int]] = {}
    for path in sorted(app_dir.rglob("*.swift")):
        s = str(path)
        if "/fichero-tests/" in s or "/fichero-ui-tests/" in s:
            continue
        rel = path.relative_to(app_dir).as_posix()
        code = _code(path.read_text(errors="ignore"))
        hits = [i for i, line in enumerate(code.splitlines(), start=1)
                if _RAW_SESSION_RE.search(line)]
        if hits:
            found[rel] = hits
    return found


def _assert_logic() -> None:
    assert _RAW_SESSION_RE.search("let (d, r) = try await session.data(for: request)")
    assert _RAW_SESSION_RE.search("urlSession.bytes(for: request)")
    assert _RAW_SESSION_RE.search("URLSession.shared")
    # A generated-client call is not raw transport.
    assert not _RAW_SESSION_RE.search("try await client.api.listEntitiesApiEntitiesGet()")
    # WKWebView challenge signatures reference URLSession.AuthChallengeDisposition
    # but are not a data path — must not match.
    assert not _RAW_SESSION_RE.search("URLSession.AuthChallengeDisposition")


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--self-test" in argv:
        _assert_logic()
        print("check_no_raw_urlsession_app self-test: OK")
        return 0

    _assert_logic()
    found = raw_transport_files()

    if "--list" in argv:
        for rel, lines in sorted(found.items()):
            tag = "grandfathered" if rel in GRANDFATHERED_FILES else "NEW"
            print(f"[{tag}] {rel}  (lines {', '.join(map(str, lines))})")
        print(f"\n{len(found)} file(s); {len(GRANDFATHERED_FILES)} grandfathered.")

    new = sorted(set(found) - GRANDFATHERED_FILES)
    stale = sorted(GRANDFATHERED_FILES - set(found))

    if not new and not stale:
        print("Raw-URLSession ratchet (app, #1666):")
        print(f"  {len(found)} grandfathered file(s), 0 new. Route new code through "
              "the generated FicheroAPIClient.")
        return 0

    if new:
        print("Raw-URLSession ratchet FAILED — new raw URLSession in the app. Route "
              f"through the generated FicheroAPIClient (see {AUDIT_DOC}); custom "
              "transport only behind RemoteCertificatePinning for an audited KEEP "
              "case, then add it to GRANDFATHERED_FILES with a reason:\n")
        for rel in new:
            print(f"  {rel}  (lines {', '.join(map(str, found[rel]))})")
    if stale:
        print("\nStale allowlist entries — a #1666 migration cleaned these; drop "
              "them from GRANDFATHERED_FILES to keep the ratchet tight:")
        for rel in stale:
            print(f"  {rel}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
