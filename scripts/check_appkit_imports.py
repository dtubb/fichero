#!/usr/bin/env python3
"""AppKit/UIKit import allowlist guardrail (§6b reform master plan).

Rule (cross-platform debt is explicit, not creeping):

    > A SwiftUI view/model/service must not reach for `import AppKit` (or
    > `import UIKit`) unless it is a sanctioned platform bridge. Every file that
    > imports AppKit/UIKit today is the cross-platform migration backlog and is
    > listed in KNOWN_VIOLATIONS. The guardrail FAILS the moment a NEW file adds
    > `import AppKit`/`import UIKit` without being allowlisted, and flags stale
    > entries when a file drops the import.

This makes the cross-platform debt (~35 AppKit files) visible and prevents
silent regression: new feature code is steered to pure SwiftUI / cross-platform
APIs, and any genuinely-needed AppKit bridge must be added here with intent.

The unit of violation is a FILE (keyed by its repo-relative path — a stable
identity, never a line number). A file is flagged once if it imports AppKit
and/or UIKit anywhere outside comments.

Usage:
    scripts/check_appkit_imports.py
    scripts/check_appkit_imports.py --list
    scripts/check_appkit_imports.py --help

Exit codes:
    0  every AppKit/UIKit importer is in KNOWN_VIOLATIONS
    1  a new file imports AppKit/UIKit, or a known entry is stale
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWIFT_DIR = ROOT / "fichero" / "fichero"
RULE_DOC = "docs/contributor/architecture/swiftui/appkit_import_audit_2101.md"

# Current cross-platform migration backlog: files that import AppKit/UIKit.
# Keys are paths relative to SWIFT_DIR (posix). Value documents why it is a
# sanctioned bridge OR that it is baseline debt to migrate.
KNOWN_VIOLATIONS: dict[str, str] = {
    "App/AppInstaller.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "App/LibraryWindow.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "App/SparkleUpdater.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "FicheroApp.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "FicheroApp_iOS.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/Platform/PlatformAliases.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/Platform/PlatformPasteboard.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/SpatialTheme.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/WorkflowExporter.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Services/ImageEditingServiceGenerated.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Services/EmbeddedBackendService.swift": "#2864 — macOS engine lifecycle/alert bridge uses NSApplication/NSAlert; #2101",
    "Services/EngineConfig.swift": "#2381 — macOS launch-mode bridge reads Option-key state via NSEvent; #2101",
    "Services/RemoteClientPairing.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Capture/MobileCaptureQueueView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Components/BackendConnectionView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Components/MacPlainTextEditor.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ArtifactRichTextCodec.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/DocumentKGWebPane.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ImmersiveReaderView.swift": "#2520 — macOS first-responder bridge catches Esc via NSViewRepresentable; #2101",
    "Views/Library/FolderAccessManager.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/AnnotatableTextView.swift": "#2458 — NSTextView bridge for selectable highlighted text spans; #2101",
    "Views/Library/ImageEditor/ImageEditorModel.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ImageEditor/ImageEditorView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ImageViewer/ImageWithCursorTracking.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ImageViewer/TrackingImageView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ImageViewerComponents.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/LibraryWorkspaceRoot.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/MagnifierPanel.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/PDFPageView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/PDFThumbnailView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/QuickLookComponents.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/QuickLookPreviewViews.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ScrollWheelZoom.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Menu/FileMenuCommands.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Onboarding/FirstRunWindow.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/OpenAffordances.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Sidebar/SidebarView+ActivityRows.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*")
_IMPORT_RE = re.compile(r"^\s*import\s+(AppKit|UIKit)\b", re.MULTILINE)


def _strip_comments(text: str) -> str:
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", text)


def scan(swift_dir: Path = SWIFT_DIR) -> dict[str, str]:
    """Return {relpath: 'imports AppKit/UIKit'} for every importer file."""
    found: dict[str, str] = {}
    for path in sorted(swift_dir.rglob("*.swift")):
        if "Tests" in path.parts:
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        cleaned = _strip_comments(source)
        frameworks = sorted({m.group(1) for m in _IMPORT_RE.finditer(cleaned)})
        if not frameworks:
            continue
        rel = path.relative_to(swift_dir).as_posix()
        found[rel] = "imports " + "/".join(frameworks)
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"AppKit/UIKit importers ({len(found)} file(s)):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}  <-  {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"AppKit/UIKit import guardrail: scanned {SWIFT_DIR.relative_to(ROOT)}")
    print(f"  {len(found)} file(s) import AppKit/UIKit; {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new file(s) importing AppKit/UIKit without allowlisting:")
        for key in new:
            print(f"      {key}  ←  {found[key]}")
        print(
            "\nFix: prefer pure SwiftUI / cross-platform APIs. If a platform bridge "
            "is genuinely required, add the file to KNOWN_VIOLATIONS with a reason. "
            f"Rule: {RULE_DOC} §6b."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ No new AppKit/UIKit importers beyond the known backlog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
