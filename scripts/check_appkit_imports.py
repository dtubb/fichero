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
RULE_DOC = "docs/architecture/swiftui/reform_masterplan_2026-06.md"

# Current cross-platform migration backlog: files that import AppKit/UIKit.
# Keys are paths relative to SWIFT_DIR (posix). Value documents why it is a
# sanctioned bridge OR that it is baseline debt to migrate.
KNOWN_VIOLATIONS: dict[str, str] = {
    "App/AppInstaller.swift": "§6b baseline — NSWorkspace install flow",
    "App/LibraryWindow.swift": "§6b baseline — NSWindow chrome",
    "App/SparkleUpdater.swift": "§6b baseline — Sparkle/AppKit updater bridge",
    "FicheroApp.swift": "§6b baseline — NSApplication lifecycle",
    "Models/MindPalaceTheme.swift": "§6b baseline — NSColor theme",
    "Models/Platform/PlatformAliases.swift": "sanctioned cross-platform shim — #if canImport(AppKit/UIKit) (#2097/#2098)",
    "Models/Platform/PlatformPasteboard.swift": "sanctioned cross-platform shim — #if canImport(AppKit/UIKit) (#2097/#2098)",
    "Models/WorkflowExporter.swift": "§6b baseline — NSSavePanel export",
    "Views/Menu/FileMenuCommands.swift": "§6b baseline — NSSavePanel/NSAlert file-menu; gate behind #if os(macOS) for iOS (#2098/#2101)",
    "Services/ImageEditingServiceGenerated.swift": "§6b baseline — NSImage codec",
    "Views/Components/BackendConnectionView.swift": "§6b baseline — AppKit bridge",
    "Views/Components/MacPlainTextEditor.swift": "sanctioned bridge — NSTextView editor",
    "Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift": "§6b baseline — AppKit",
    "Views/Library/ArtifactRichTextCodec.swift": "sanctioned bridge — NSAttributedString codec",
    "Views/Library/DocumentInspector/AttributedTextEditor.swift": "sanctioned bridge — NSTextView",
    "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift": "§6b baseline",
    "Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift": "§6b baseline",
    "Views/Library/FolderAccessManager.swift": "sanctioned bridge — NSOpenPanel/security scope",
    "Views/Library/ImageEditor/ImageEditorModel.swift": "sanctioned bridge — NSImage editor",
    "Views/Library/ImageEditor/ImageEditorView.swift": "sanctioned bridge — NSImage editor",
    "Views/Library/ImageViewer/ImageWithCursorTracking.swift": "sanctioned bridge — NSView cursor",
    "Views/Library/ImageViewer/TrackingImageView.swift": "sanctioned bridge — NSView tracking",
    "Views/Library/ImageViewerComponents.swift": "sanctioned bridge — NSImage viewer",
    "Views/Library/MagnifierPanel.swift": "sanctioned bridge — NSPanel loupe",
    "Views/Library/PDFThumbnailView.swift": "sanctioned bridge — PDFKit/AppKit",
    "Views/Library/QuickLookComponents.swift": "sanctioned bridge — QuickLook/AppKit",
    "Views/Library/QuickLookPreviewViews.swift": "sanctioned bridge — QuickLook/AppKit",
    "Views/Library/ScrollWheelZoom.swift": "sanctioned bridge — NSEvent scroll",
    "Views/Onboarding/FirstRunWindow.swift": "§6b baseline — NSWindow onboarding",
    "Views/OpenAffordances.swift": "§6b baseline — NSWorkspace open",
    "Views/Research/ResearchBrowserPane.swift": "sanctioned bridge — WKWebView/AppKit",
    "Views/Sidebar/SidebarView+ActivityRows.swift": "§6b baseline — AppKit",
    "Views/Sidebar/SidebarView+ViewComponents.swift": "§6b baseline — AppKit",
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
