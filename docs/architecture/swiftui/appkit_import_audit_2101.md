# AppKit / UIKit Import Audit (#2101)

Status: captured for the iOS/iPad remote-client port.

Rule: SwiftUI first. AppKit/UIKit imports are allowed only as macOS-only code, a platform shim, or a real UI capability gap that needs an iOS alternative.

The machine guardrail is `scripts/check_appkit_imports.py`. This document explains every current allowlisted importer.

## Buckets

| File | Bucket | Next move |
|---|---|---|
| `App/AppInstaller.swift` | macOS-only | Keep behind `#if canImport(AppKit)`; no iOS installer path. |
| `App/LibraryWindow.swift` | macOS-only shell | Keep Mac window behavior isolated; iOS uses scene/navigation shell. |
| `App/SparkleUpdater.swift` | macOS-only | Keep Sparkle out of iOS. |
| `FicheroApp.swift` | macOS-only app entry | Keep Mac app delegate/window wiring isolated. |
| `FicheroApp_iOS.swift` | iOS app entry | UIKit entry point for the remote-only client. |
| `Models/Platform/PlatformAliases.swift` | platform shim | Canonical `PlatformImage`, `PlatformColor`, `PlatformFont`, and split-view aliases. |
| `Models/Platform/PlatformPasteboard.swift` | platform shim | Pasteboard bridge; keep as the single copy/paste crossing. |
| `Models/SpatialTheme.swift` | platform shim | Uses `PlatformColor`; keep platform color math centralized. |
| `Models/WorkflowExporter.swift` | file picker bridge | Replace panel-specific paths with SwiftUI file exporter/importer when porting. |
| `Services/EmbeddedBackendService.swift` | engine lifecycle | `NSClassFromString` test detection + `NSError` lifecycle plumbing for the Mac-only embedded engine; iOS embeds in-process differently. |
| `Services/EngineConfig.swift` | macOS interaction gap | `NSEvent.modifierFlags` option-key detection to pick the launch/provisioning mode; iOS has no modifier keys. |
| `Services/ImageEditingServiceGenerated.swift` | platform shim | Uses `PlatformImage`; keep image decode/preview platform-neutral. |
| `Services/RemoteClientPairing.swift` | platform shim | Uses UIKit device name where available; keep pairing logic shared. |
| `Views/Capture/MobileCaptureQueueView.swift` | iOS surface | UIKit-only capture queue UI for mobile. |
| `Views/Components/BackendConnectionView.swift` | platform shim | Uses `PlatformImage`; iOS branch is remote-only connection copy. |
| `Views/Components/MacPlainTextEditor.swift` | needs iOS alternative | Keep Mac text editor bridge; iOS should use SwiftUI/UITextView. |
| `Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift` | macOS interaction gap | Cmd-click/open-window behavior needs touch/edit-mode alternative. |
| `Views/Library/ArtifactRichTextCodec.swift` | rich text bridge | Keep concrete AppKit attributes for RTF round-trip; iOS alternative must preserve formatting. |
| `Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+EntitiesTab.swift` | macOS interaction gap | Multi-select/open behavior needs iOS edit-mode alternative. |
| `Views/Library/DocumentInspector/DocumentInspectorArtifactsTab+KGSection.swift` | macOS interaction gap | Multi-select/open behavior needs iOS edit-mode alternative. |
| `Views/Library/DocumentKGWebPane.swift` | WebKit bridge | Keep platform WebView/pinning boundary isolated. |
| `Views/Library/FolderAccessManager.swift` | file picker/bookmark bridge | Swap panels to SwiftUI file importer/exporter for iOS. |
| `Views/Library/AnnotatableTextView.swift` | rich text bridge | `NSViewRepresentable` over `NSTextView` to draw highlight backgrounds; iOS needs a `UITextView` equivalent. |
| `Views/Library/ImmersiveReaderView.swift` | macOS interaction gap | `NSViewRepresentable` keyboard-exit catcher (Esc) for the immersive reader; iOS uses gesture/back. |
| `Views/Library/ImageEditor/ImageEditorModel.swift` | platform shim | Uses platform image type for editor previews. |
| `Views/Library/ImageEditor/ImageEditorView.swift` | platform shim | Uses platform image views; keep editor logic shared. |
| `Views/Library/ImageViewer/ImageWithCursorTracking.swift` | needs iOS alternative | Mac uses `NSScrollView`/tracking; iOS needs `UIScrollView`/gesture path. |
| `Views/Library/ImageViewer/TrackingImageView.swift` | needs iOS alternative | Mac cursor/loupe bridge; iOS needs touch/loupe implementation. |
| `Views/Library/ImageViewerComponents.swift` | image viewer host | Keep shared host; platform-specific viewer remains behind child bridge. |
| `Views/Library/LibraryWorkspaceRoot.swift` | iOS scene support | Uses UIKit scene capability checks. |
| `Views/Library/MagnifierPanel.swift` | needs iOS alternative | Mac AppKit magnifier; iOS touch magnifier can be SwiftUI/UIKit. |
| `Views/Library/PDFPageView.swift` | PDFKit bridge | PDFKit is cross-platform; keep bridge split by platform. |
| `Views/Library/PDFThumbnailView.swift` | PDFKit/platform image shim | Keep shared thumbnail rendering through `PlatformImage`. |
| `Views/Library/QuickLookComponents.swift` | Quick Look bridge | Mac inline Quick Look; iOS should present `QLPreviewController`. |
| `Views/Library/QuickLookPreviewViews.swift` | Quick Look bridge | Mac `QLPreviewView`; iOS presenter needed. |
| `Views/Library/ScrollWheelZoom.swift` | macOS interaction gap | Mac scroll-wheel zoom only; iOS uses pinch. |
| `Views/Menu/FileMenuCommands.swift` | macOS menu/file panels | Keep Mac menu commands; iOS uses toolbar/share/file exporters. |
| `Views/Onboarding/FirstRunWindow.swift` | macOS onboarding window | iOS needs remote-host onboarding, not Mac package picker. |
| `Views/OpenAffordances.swift` | macOS windowing | Keep NSWindow tab/window affordances Mac-only. |
| `Views/Sidebar/SidebarView+ActivityRows.swift` | macOS interaction gap | Cmd-click/multi-select needs touch/edit-mode alternative. |

## Near-Term Slice

Do not add new AppKit/UIKit imports. For incremental work, prefer:

- Moving platform types into `Models/Platform/PlatformAliases.swift`.
- Keeping Mac-only app/window/updater code behind compile guards.
- Replacing file panels with SwiftUI `fileImporter` / `fileExporter` where practical.
- Leaving image viewer, rich text, Quick Look, and command-click behavior as explicit iOS-alternative work rather than pretending they are mechanical.
