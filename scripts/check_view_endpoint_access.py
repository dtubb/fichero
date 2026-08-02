#!/usr/bin/env python3
"""Observable-data-layer guardrail — flag Views that bypass an @Observable store.

The rule (see docs/contributor/architecture/fichero/observable_data_layer.md §1):

    > A view never calls a backend endpoint. It observes an @Observable domain
    > store and renders what the store publishes. The store is the only endpoint
    > accessor.

`EntityStore` is the reference implementation. Every other view is being migrated
to the same shape (#1882–#1900, #1862). This script is the *programmatic* half of
the guardrail (#1876): it scans the SwiftUI Views tree and flags any view file
that talks to the backend transport DIRECTLY instead of going through a store.

What counts as a direct-transport violation (scanned outside comments + #Preview):
  1. `client.api.…`               — calling the generated OpenAPI client in a view
  2. `URLSession`                  — raw HTTP / hand-built request in a view
  3. `@StateObject … = FooService()` / `FooServiceGenerated()`
                                    — constructing a transport service inside a view

NOT flagged (intentionally): WKWebView `URLRequest(url:)` loads (a webview pane is
display, not a data fetch); `*Store.swift` files (they ARE the store layer); the
Services/ dir; the sanctioned AppKit bridges (PDFKit / QuickLook / MagnifierPanel /
ImageWithCursorTracking / AttributedTextEditor); and anything inside a `#Preview {}`.

This is deterministic and token-free — same philosophy as check_ui_wiring.py.
It catches the failure mode that matters: a NEW view that hand-rolls a service call
instead of binding a store. `KNOWN_VIOLATIONS` is the migration backlog — the script
PASSES today because every current offender is listed, and it FAILS the moment a new
view bypasses a store. As views migrate to stores, shrink this set.

Usage:
    python3 scripts/check_view_endpoint_access.py            # report + exit 1 on NEW violations
    python3 scripts/check_view_endpoint_access.py --list     # list every current offender + reason
    python3 scripts/check_view_endpoint_access.py -h         # this help

Exit codes:
    0  no new violations (and no stale KNOWN_VIOLATIONS entries)
    1  a view bypasses a store and isn't in KNOWN_VIOLATIONS  -> migrate it, or
       (if it's a legitimately new offender) add it to KNOWN_VIOLATIONS with the issue #.
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "fichero" / "fichero" / "Views"
RULE_DOC = "docs/contributor/architecture/fichero/observable_data_layer.md"

# Filename substrings for the sanctioned AppKit bridges (display-only, not data
# access) — these are allowed to touch the platform directly. See AGENTS.md
# "SwiftUI-first (AppKit only where SwiftUI can't reach)".
APPKIT_BRIDGE_MARKERS = (
    "PDFKit", "PDFThumbnail", "PDFZoom",
    "QuickLook",
    "MagnifierPanel",
    "ImageWithCursorTracking",
    "AttributedTextEditor", "MacPlainTextEditor",
    "ScrollWheelZoom",
)

# Direct-transport signals scanned inside a view's *code* (comments + previews
# stripped first). name -> compiled pattern.
TRANSPORT_PATTERNS: dict[str, re.Pattern] = {
    "client.api.* (generated client called from a view)": re.compile(r"\bclient\.api\."),
    "raw URLSession (hand-built HTTP in a view)": re.compile(r"\bURLSession(?:\.shared|\s*\()"),
    "@StateObject = …Service() (transport built inside a view)": re.compile(
        r"@StateObject[^\n=]*=\s*[A-Za-z_][A-Za-z0-9_]*Service(?:Generated)?\s*\("
    ),
}

# ── Migration backlog ────────────────────────────────────────────────────────
# Views known to bypass a store TODAY (audit #1882–#1900 / #1862). The script
# passes because these are listed; it FAILS if a NEW view bypasses a store.
# Drop an entry the moment its view binds a store (EntityStore is the template).
# Keys are POSIX paths relative to fichero/fichero/Views/.
KNOWN_VIOLATIONS: dict[str, str] = {
    # @StateObject = …Service() constructed inside the view (#1882–#1900)
    "Shell/ContentView/ContentView.swift": "#1884 — @StateObject PerformanceService() in view",
    "Connect/ConnectPairingIOS.swift": "#3102 — @StateObject BonjourDiscoveryService() in the iOS pairing view (local LAN discovery for pairing; grandfathered from FicheroApp_iOS before the file_length split)",
    "Chat/ModelComparison/ModelComparisonView.swift": "#1900 — @StateObject ModelComparisonService()",
    "Chat/ModelComparison/NodeComparisonSheet.swift": "#1900 — @StateObject ModelComparisonService()",
    "Components/NodeClassPicker.swift": "#1886 — @StateObject WorkspacePickerService()",
    "Library/WorkspaceItemPicker.swift": "#1886 — @StateObject WorkspacePickerService()",
    "Integrations/IntegrationsView.swift": "#1899 — @StateObject IntegrationsService()",
    # client.api.* called directly from the view (raw transport)
    "Settings/AI/LocalModelsSettingsView.swift": "#1894 — client.api.* local-models calls in view",
    "Chat/ModelComparison/ComparisonDetailView+Actions.swift": "#1900 — client.api.getComparison… in view",
    # Migrated to stores (de-baselined): WorkflowDiagramPreview + WorkflowExecutionView
    # → WorkflowStore (#1911); Notes/Annotation tabs + ImageEditor + EntityDetail+Notes
    # → NoteStore/AnnotationStore (#1882/#1883/#1889).
}

# ── Comment / preview stripping ──────────────────────────────────────────────
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# line comment, but not the `//` in a URL scheme like http://
_LINE_COMMENT = re.compile(r"(?<!:)//.*")


def _strip_preview_blocks(text: str) -> str:
    """Remove `#Preview { … }` (brace-matched) blocks — preview/mock code is not
    production data access and may legitimately construct services."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = text.find("#Preview", i)
        if m == -1:
            out.append(text[i:])
            break
        out.append(text[i:m])
        brace = text.find("{", m)
        if brace == -1:
            out.append(text[m:])
            break
        depth = 0
        j = brace
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        i = j  # skip the whole preview block
    return "".join(out)


def code_only(text: str) -> str:
    """Source with block comments, line comments, and #Preview blocks removed."""
    text = _BLOCK_COMMENT.sub("", text)
    text = "\n".join(_LINE_COMMENT.sub("", line) for line in text.splitlines())
    return _strip_preview_blocks(text)


def is_excluded(path: Path) -> bool:
    name = path.name
    if name.endswith("Store.swift"):  # the store layer itself
        return True
    if any(marker in name for marker in APPKIT_BRIDGE_MARKERS):
        return True
    return False


def violations_for(path: Path) -> list[str]:
    """Transport-bypass reasons found in this view file (empty == clean)."""
    try:
        src = code_only(path.read_text(errors="ignore"))
    except OSError:
        return []
    return [reason for reason, pat in TRANSPORT_PATTERNS.items() if pat.search(src)]


def scan() -> dict[str, list[str]]:
    """rel-path -> list of violation reasons, for every offending view file."""
    found: dict[str, list[str]] = {}
    for f in sorted(VIEWS_DIR.rglob("*.swift")):
        if is_excluded(f):
            continue
        reasons = violations_for(f)
        if reasons:
            found[f.relative_to(VIEWS_DIR).as_posix()] = reasons
    return found


def main() -> int:
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Views that bypass a store ({len(found)} files):\n")
        for rel, reasons in found.items():
            tag = "known" if rel in known else "NEW"
            print(f"  [{tag}] {rel}")
            for r in reasons:
                print(f"          - {r}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Observable-data-layer guardrail: scanned {VIEWS_DIR.relative_to(ROOT)}")
    # #4487 scan floor: on view files ENUMERATED (582 on 2026-08-02).
    require_scan_floor(
        sum(1 for _ in VIEWS_DIR.rglob("*.swift")), 291,
        "view files (582 on 2026-08-02)",
    )
    print(f"  {len(found)} view file(s) bypass a store; {len(known)} known (migration backlog).")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now CLEAN — drop from the set:")
        for rel in stale:
            print(f"      {rel}")

    if new:
        print(f"\n  ✗ {len(new)} view(s) bypass a store and are NOT in KNOWN_VIOLATIONS:")
        for rel in new:
            for r in found[rel]:
                print(f"      {rel}  ←  {r}")
        print(
            "\nFix: bind an @Observable store (EntityStore is the reference) instead of "
            "calling the backend transport from the view.\n"
            f"Rule: {RULE_DOC} §1.  If this is a genuinely new offender being staged for "
            "migration, add it to KNOWN_VIOLATIONS with its issue #."
        )
        return 1

    if stale:
        # Stale entries don't fail the build, but nudge to keep the backlog honest.
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")

    print("\n✓ No view bypasses a store beyond the known migration backlog.")
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
    _require_scan_roots_4382(VIEWS_DIR)
    raise SystemExit(main())
