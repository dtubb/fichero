# iOS/iPad/Mac AppKit Audit (#2101)

Read-only per-file audit of AppKit / UIKit usage under `fichero/fichero/`.
Goal: identify the smallest incremental path to a shared iPhone / iPad / Mac
codebase while keeping the Mac app unchanged. Mac-only code stays behind
`#if os(macOS)` shims; cross-platform code moves to the existing #2097 shim
layer rather than being reimplemented.

## Scope

- **33 `.swift` files import AppKit** under `fichero/fichero/`
- **3 `.swift` files import UIKit** — all existing cross-platform shims
- This audit covers only files with `import AppKit` / `import UIKit`.
  Additional macOS-only code (e.g. `EmbeddedBackendService`) is noted in the
  summary only if it is already gated and does not import AppKit.

## Existing shim layer (#2097)

Only two shim files currently exist under `fichero/fichero/Models/Platform/`:

- `PlatformAliases.swift` — `PlatformColor` / `PlatformImage`, plus
  `Color(platformColor:)` / `Image(platformImage:)` bridges.
- `PlatformPasteboard.swift` — `writeString(_:)` / `string()` clipboard
  wrapper.

**Important:** `PlatformViewRepresentable`, `PlatformFilePicker`, etc. were
mentioned in planning documents but are **not present yet**. A file that uses
`NSViewRepresentable` / `NSScrollView` / `NSTextView` / `QLPreviewView` cannot be
"shimmed" today and belongs in bucket **D** (replace).

## Classification buckets

| Bucket | Meaning | Action |
|--------|---------|--------|
| **A. Already cross-platform** | Uses `canImport` guards or only Foundation/SwiftUI; no AppKit-only behavior. | None (or remove unused import). |
| **B. Shim** | AppKit usage maps cleanly to an existing shim (`NSImage` → `PlatformImage`, `NSColor` → `PlatformColor`, `NSPasteboard` → `PlatformPasteboard`). | Swap to the shim; gate tiny mac-only accessors if necessary. |
| **C. Gate** | Genuinely Mac-only (`NSWindow`, `NSApp`, `NSApplication`, `NSSavePanel`, `NSOpenPanel`, `NSAlert`, `NSWorkspace`, `NSToolbar`, `NSCursor`, `NSEvent`, `NSScriptCommand`, `NSVisualEffectView`, unused AppKit import). | Wrap behind `#if os(macOS)` and provide iOS no-op/alternative. |
| **D. Replace** | AppKit view with no existing shim; needs SwiftUI/UIKit equivalent for iOS (`NSTextView`, `NSScrollView`, `NSViewRepresentable`, `QLPreviewView`, `NSEvent` tracking). | Build `UIViewRepresentable` counterpart or pure SwiftUI replacement. |

## Per-file audit table

### A. Already cross-platform

| File | AppKit / UIKit symbols | Recommended action | Effort |
|------|------------------------|--------------------|--------|
| `Models/Platform/PlatformAliases.swift` | `NSImage`, `NSColor` / `UIImage`, `UIColor` | Keep as the canonical shim layer; no work. | — |
| `Models/Platform/PlatformPasteboard.swift` | `NSPasteboard` / `UIPasteboard` | Keep as the canonical pasteboard shim; no work. | — |
| `Models/MindPalaceTheme.swift` | `NSColor` / `UIColor` | Already uses `canImport` guards and `PlatformColor`; no work. | — |
| `Views/Library/ArtifactRichTextCodec.swift` | `import AppKit` (unused) | Remove unused `import AppKit`; `NSAttributedString`, `NSParagraphStyle`, and RTF options are all `Foundation`. | S |

### B. Shim

| File | AppKit / UIKit symbols | Recommended action | Effort |
|------|------------------------|--------------------|--------|
| `Views/Components/BackendConnectionView.swift` | `NSImage`, `NSApp` | Replace `NSImage` with `PlatformImage`; gate the `NSApp.applicationIconImage` fallback behind `#if os(macOS)` (use `UIImage(named:)` on iOS). | S |
| `Services/ImageEditingServiceGenerated.swift` | `NSImage` | Change `PreviewImage.image: NSImage` → `PlatformImage`; update decoding path. | S |
| `Views/Library/ImageEditor/ImageEditorView.swift` | `NSImage` | Use `Image(platformImage:)` instead of `Image(nsImage:)`. | S |
| `Views/Library/ImageEditor/ImageEditorModel.swift` | `import AppKit` (indirect via `PreviewImage`) | No direct AppKit usage; dependency becomes cross-platform once `ImageEditingServiceGenerated` uses `PlatformImage`. | S |
| `Views/Library/PDFThumbnailView.swift` | `NSImage` | Convert PDF page rendering to `PlatformImage`; `UIGraphicsImageRenderer` on iOS. | S |

### C. Gate

| File | AppKit / UIKit symbols | Recommended action | Effort |
|------|------------------------|--------------------|--------|
| `FicheroApp.swift` | `NSApplication`, `NSAlert` | Entire app entry point is Mac-only. Add an iOS `App` entry or `#if os(iOS)` alternative scene. | M |
| `App/SparkleUpdater.swift` | `NSAlert` | Sparkle is mac-only; gate whole file behind `#if os(macOS)`. | S |
| `App/AppInstaller.swift` | `NSApp`, `NSAlert` | Engine installer / bundle copy is Mac-only; gate file or expose no-op iOS stub. | M |
| `App/LibraryWindow.swift` | `NSWindow`, `NSView`, `NSViewRepresentable`, `NSSavePanel` | Window chrome + save-panel wrapper. Gate Mac window path; iOS uses `NavigationSplitView` or `WindowGroup`. | M |
| `Views/Onboarding/FirstRunWindow.swift` | `NSOpenPanel` | Folder picker for first-run bookmark; on iOS use a document picker or `PlatformFilePicker` shim. | M |
| `Views/Menu/FileMenuCommands.swift` | `NSSavePanel`, `NSAlert` | Mac menu commands; on iOS expose as toolbar/menu actions or no-op. | M |
| `Models/WorkflowExporter.swift` | `NSSavePanel`, `NSOpenPanel` | Save/export panels; gate or bridge to `UIDocumentPickerViewController`. | M |
| `Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift` | `NSApp` | `NSApp` reference (likely for openURL / activation); gate or replace with `UIApplication.shared`. | S |
| `Views/Sidebar/SidebarView+ActivityRows.swift` | `NSApp` | Same as above; `UIApplication.shared` equivalent on iOS. | S |
| `Views/Library/FolderAccessManager.swift` | `NSOpenPanel` | Security-scoped folder picker; iOS alternative is document picker or sandbox container. | M |
| `Views/OpenAffordances.swift` | `NSApp`, `NSWindow` | Window / app activation affordances; gate or replace with iOS scene APIs. | M |
| `Views/Sidebar/SidebarView+ViewComponents.swift` | `NSVisualEffectView` | mac-only vibrancy wrapper; remove import or gate the `VisualEffectBlur` helper. | S |
| `Views/Research/ResearchBrowserPane.swift` | `import AppKit` (unused) | Remove unused import; `WKWebView` wrapper is cross-platform. | S |

### D. Replace

| File | AppKit / UIKit symbols | Recommended action | Effort |
|------|------------------------|--------------------|--------|
| `Views/Components/MacPlainTextEditor.swift` | `NSViewRepresentable`, `NSFont`, `NSTextView`, `NSScrollView`, `NSSize` | Replace with `UIViewRepresentable` over `UITextView` or a pure SwiftUI `TextEditor` once behavior matches. | M |
| `Views/Library/DocumentInspector/AttributedTextEditor.swift` | `NSViewRepresentable`, `NSFont`, `NSTextView`, `NSTextStorage`, `NSAttributedString`, `NSScrollView`, `NSSize` | Same as above; rich-text support needs `UITextView` attributed-string path. | M |
| `Views/Library/ImageViewer/ImageWithCursorTracking.swift` | `NSView`, `NSViewRepresentable`, `NSImage`, `NSImageView`, `NSColor`, `NSScrollView`, `NSMagnificationGestureRecognizer`, `NSRect`, `NSClickGestureRecognizer`, `NSGestureRecognizer` | Build `UIViewRepresentable` over `UIScrollView` + `UIImageView` with pinch/zoom/pan gestures. | L |
| `Views/Library/ImageViewer/TrackingImageView.swift` | `NSImage`, `NSImageView`, `NSColor`, `NSFont`, `NSEvent`, `NSCursor`, `NSAttributedString`, `NSPoint`, `NSRect`, `NSSize`, `NSGraphicsContext`, `NSBezierPath` | Same as above; includes annotation/cursor tracking that needs `UIGestureRecognizer` equivalent. | L |
| `Views/Library/MagnifierPanel.swift` | `NSView`, `NSViewRepresentable`, `NSImage`, `NSColor`, `NSEvent`, `NSCursor`, `NSRect` | Replace with SwiftUI magnifier overlay or `UIView` magnifier on iOS. | M |
| `Views/Library/QuickLookPreviewViews.swift` | `NSView`, `NSViewRepresentable`, `NSEvent` | Wrap `QLPreviewController` via `UIViewControllerRepresentable` on iOS. | M |
| `Views/Library/QuickLookComponents.swift` | `import AppKit`, `import Quartz` | Depends on `SmartPreviewView` (bucket D); keep as consumer, gate the mac-only `QLPreviewView` path. | M |
| `Views/Library/ScrollWheelZoom.swift` | `NSView`, `NSViewRepresentable`, `NSEvent` | iOS uses pinch gesture (`UIPinchGestureRecognizer`) or `UIScrollView` zoom; no scroll-wheel equivalent. | S |
| `Views/Library/ImageViewerComponents.swift` | `NSViewRepresentable`, `NSImage`, `NSScrollView` | Same as `ImageWithCursorTracking`; replace scroll/image view wrapper. | M |
| `Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift` | `NSEvent` | Modifier-flag multi-selection logic (`NSEvent.modifierFlags`). Gate behind `#if os(macOS)`; iOS uses direct touch selection. | S |
| `Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift` | `NSEvent` | Same as above. | S |

## UIKit files

Three files import UIKit today. All are part of the existing #2097 shim layer:

| File | Purpose |
|------|---------|
| `Models/Platform/PlatformAliases.swift` | iOS branch of `PlatformColor` / `PlatformImage` aliases and `Color`/`Image` bridges. |
| `Models/Platform/PlatformPasteboard.swift` | iOS branch of `PlatformPasteboard` using `UIPasteboard.general`. |
| `Models/MindPalaceTheme.swift` | iOS branch of platform colour resolution for the RealityKit renderer. |

## Summary

| Bucket | Count | Description |
|--------|-------|-------------|
| **A. Already cross-platform** | 4 | Shim files + `MindPalaceTheme` + `ArtifactRichTextCodec` (unused import). |
| **B. Shim** | 5 | Replace `NSImage` / `NSColor` with existing `PlatformImage` / `PlatformColor` aliases. |
| **C. Gate** | 13 | Mac-only window / app / panel / menu / unused-import code. |
| **D. Replace** | 11 | Real AppKit views (`NSTextView`, `NSScrollView`, `NSViewRepresentable`, `NSEvent` tracking) with no existing shim. |
| **Total** | **33** | Files that import AppKit under `fichero/fichero/`. |

### Recommended tackle order

1. **Bucket A** — remove the one unused `import AppKit` in `ArtifactRichTextCodec.swift`; no risk.
2. **Bucket B** — swap `NSImage` → `PlatformImage`. This unblocks the image pipeline and editor without changing behavior on Mac.
3. **Bucket C** — wrap Mac-only surfaces behind `#if os(macOS)` so the iOS target compiles. Provide no-op or alternative paths for app entry, window chrome, menus, save/open panels, and `NSEvent` modifiers.
4. **Bucket D** — implement SwiftUI/UIKit replacements for the most-used surfaces (text editors, image viewer, Quick Look). These can be delivered incrementally; early iOS builds can gate them out entirely.

### Blockers for a first iOS build

The real blockers are **Bucket C**:

- `FicheroApp.swift` — a new iOS app entry point is required.
- `App/LibraryWindow.swift` + `Views/Onboarding/FirstRunWindow.swift` — window / panel chrome.
- `Views/Menu/FileMenuCommands.swift` + `Models/WorkflowExporter.swift` — menus and save/open panels.
- `App/AppInstaller.swift` + `App/SparkleUpdater.swift` — Mac-only app lifecycle helpers.

**Bucket D** views do not need to be fully replaced before the first iOS build if they are gated behind `#if os(macOS)`; the app will simply lack those editors/viewers on iOS until their replacements land.

### Notes for reviewers

- Do **not** treat `NSViewRepresentable`, `NSScrollView`, `NSTextView`, or
  `QLPreviewView` as shim-able today. Creating a cross-platform
  `PlatformViewRepresentable` is future work, not part of this audit.
- `NSAttributedString` and `NSParagraphStyle` are `Foundation` and work on iOS;
  the `import AppKit` in `ArtifactRichTextCodec.swift` is a leftover.
- `EmbeddedBackendService.swift` does not import AppKit and is already gated with
  `#if os(macOS)`; it is out of scope for this import-based audit.
