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
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

# Current cross-platform migration backlog: files that import AppKit/UIKit.
# Keys are paths relative to SWIFT_DIR (posix). Value documents why it is a
# sanctioned bridge OR that it is baseline debt to migrate.
KNOWN_VIOLATIONS: dict[str, str] = {
    "App/ViewSettings.swift": "#3682 — Reader/Editor font scale multiplies the SEMANTIC base size, which only NSFont/UIFont.preferredFont(forTextStyle:) can report (SwiftUI exposes no point size). Both sides are #if canImport-guarded; #2101",
    "Views/Preview/ImageEditor/LiveEditPreview.swift": "#3673 — Core Image live preview bridges CGImage → NSImage/UIImage for display; Core Image itself is AppKit/UIKit-side. #if canImport-guarded; #2101",
    "App/AppState.swift": "#3341/#3369 — app state owns macOS activation/recovery routing; migrate remaining AppKit hooks under #2101",
    "App/LibraryWindow.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "App/LibraryWindow+Actions.swift": "hygiene — NSSavePanel new/save-library actions split out of LibraryWindow.swift by file_length; macOS-only (#if os(macOS))",
    "App/SparkleUpdater.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "FicheroApp.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Connect/ConnectPairingIOS.swift": "hygiene — pairing/connect flow (RemoteConnectionSetupView, PairingIncomingLinkSheet) uses AVCaptureDevice/UIImage/UIPasteboard; split out of FicheroApp_iOS.swift by file_length; iOS-only",
    "Views/Connect/ConnectPairingEntryIOS.swift": "hygiene — manual pairing entry + QR scan sheet use UIPasteboard; split out of FicheroApp_iOS.swift by file_length; iOS-only",
    "Views/Connect/ConnectQRScannerIOS.swift": "hygiene — UIKit/AVFoundation camera scanner bridge (UIViewControllerRepresentable) split out of FicheroApp_iOS.swift by file_length; iOS-only",
    "Views/Capture/CaptureInlineRowIOS.swift": "hygiene — capture-queue row thumbnail uses UIImage; split out of FicheroApp_iOS.swift by file_length; iOS-only",
    "Models/Platform/PlatformAliases.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/Platform/PlatformPasteboard.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Models/SpaceTheme.swift": "#2713 — Spatial renderer color bridge uses NSColor/UIColor behind #if canImport; #2101",
    "Models/WorkflowExporter.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Services/ImageEditingService.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Services/EngineConfig+Launch.swift": "#2381 — macOS launch-mode bridge reads Option-key state via NSEvent; #2101 (split out of EngineConfig.swift)",
    "Services/RemoteClientPairing.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Auth/AuthGateView.swift": "#3331 — auth gate loads the platform app icon via NSApp/UIImage fallback; #2101",
    "Views/Capture/MobileCaptureQueueView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Components/BackendConnection/BackendConnectionView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Components/BackendConnection/BackendConnectionView+Actions.swift": "#2713 — retry/reset actions use NSApplication.terminate + platform affordances via #if canImport (split from BackendConnectionView by file_length); #2101",
    "Views/Components/BackendConnection/BackendConnectionView+Icons.swift": "#2713 — engine/app icon loading via NSImage/UIImage #if canImport (split from BackendConnectionView by file_length); #2101",
    "App/AppState+Settings.swift": "#3341 — settings navigation touches macOS activation via NSApp #if canImport (split from AppState by file_length); #2101",
    "Views/Components/MacPlainTextEditor.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCardView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Inspector/Artifacts/ArtifactRichTextCodec.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Menus.swift": "#2101 — AppKit via #if canImport (context-menu / pasteboard); split from DocumentInspectorEntitiesTab",
    "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+SupportTypes.swift": "#2101 — AppKit via #if canImport (drag support types); split from DocumentInspectorEntitiesTab",
    "Views/Reader/Knowledge/DocumentKGWebPane.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Services/FolderAccessManager.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Reader/Page/AnnotatableTextView.swift": "#2458 — NSTextView bridge for selectable highlighted text spans; #2101",
    "Views/Preview/ImageEditor/ImageEditorModel.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Preview/ImageEditor/ImageEditorView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Preview/ImageEditor/ImageEditorView+Canvas.swift": "#2713 — canvas rendering uses PlatformImage/NS* via #if canImport (moved here when ImageEditorView was split by file_length); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMac.swift": "#2713 — macOS NSView cursor/zoom bridge #if canImport (split from ImageWithCursorTracking by file_length); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingMacCoordinator.swift": "#2713 — macOS NSView coordinator #if canImport (split); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingIOS.swift": "#2713 — iOS UIView cursor/zoom bridge #if canImport (split); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageWithCursorTrackingIOSCoordinator.swift": "#2713 — iOS UIScrollView coordinator #if canImport (split); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageSDRDecodingHelper.swift": "#2713 — macOS ImageIO/NSImage SDR decode #if canImport (split); #2101",
    "Views/Preview/ImageViewer/CursorTracking/ImageIODecodingHelpers.swift": "#2713 — iOS ImageIO/UIImage decode #if canImport (split); #2101",
    "Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift": "#2713 — macOS zoomable image preview uses AppKit image helpers #if canImport (split from ImageViewerComponents by file_length); #2101",
    "Views/Preview/ImageViewer/TrackingImageView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Reader/Knowledge/DocumentKGWebPane+Theme.swift": "#2713 — reader theme resolves NSColor/UIColor semantic colors #if canImport (split from DocumentKGWebPane by file_length); #2101",
    "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift": "#2713 — macOS WKWebView coordinator #if canImport (split); #2101",
    "Views/Reader/Knowledge/DocumentKGWebPaneCoordinatoriOS.swift": "#2713 — iOS WKWebView coordinator #if canImport (split); #2101",
    "Views/Preview/ImageViewer/MagnifierPanel.swift": "#2713 — loupe bridge uses AppKit/UIKit-specific magnifier surfaces; #2101",
    "Views/Preview/ImageViewer/ScrollWheelZoom.swift": "#2713 — zoom gesture bridge uses AppKit/UIKit event adapters; #2101",
    "Views/Reader/Page/Immersive/KeyboardExitCatcher.swift": "#2520 — immersive reader catches Esc via AppKit keyboard bridge (moved here when ImmersiveReaderView was split by file_length); #2101",
    "Views/Preview/PDFViewer/PDFPageView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Preview/PDFViewer/PDFThumbnailView.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/Workspace/LibraryWorkspaceRoot.swift": "#2713 — workspace root uses UIKit-only mobile affordances; #2101",
    "Views/Preview/QuickLookViewer/QuickLookComponents.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Preview/QuickLookViewer/QuickLookPreviewViews.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "App/Menus/FileMenuCommands.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "App/Menus/FocusedCommandButtons+UndoNavigation.swift": "#2713 — undo/nav buttons use macOS NSAlert via AppKit (moved here when FocusedCommandButtons was split by file_length); #2101",
    "Views/Onboarding/FirstRunWindow.swift": "#2713 — PDFKit page bridge (AppKit/UIKit via #if canImport); #2101",
    "Views/Library/Search/SearchArrowKeyNavigation.swift": "#2713 — search keyboard navigation listens to AppKit key events; #2101",
    "Views/Shell/OpenAffordances.swift": "#2713 — open/import affordance bridge uses AppKit open-panel helpers; #2101",
    "Views/Sidebar/ItemRow/SidebarItemRow.swift": "#711 — sidebar row drag bridges AppKit's NSTableView row-drag (which List uses under the hood) via #if canImport; #2101",
    "Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift": "#711 — sidebar row drag-source presentation split from SidebarItemRow.swift by file_length; same NSTableView row-drag bridge via #if canImport; #2101",
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
