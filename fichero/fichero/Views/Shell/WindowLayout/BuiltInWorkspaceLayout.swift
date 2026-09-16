import Foundation

// MARK: - Built-in workspace COMPOSITIONS (v2, spec §"v2 workspace design", 2026-09-15)

/// The six default workspaces as DATA — each a `PaneList` (kind + per-pane config + nesting), so
/// adding or editing a default is a data change and a saved workspace is the same shape ("easy to
/// set up in a backend", CD 2026-09-15). Pure; no SwiftUI.
///
/// Conventions grounded in the surface inventory:
///   - the sidebar (with chat beneath) is NOT a centre pane;
///   - the inspector always docks on the RIGHT, full height;
///   - claims / entities / related are the LIBRARY pane browsing different content
///     (`PaneConfig.libraryContentKind`), not separate kinds;
///   - the word-box overlay is the PREVIEW pane with `previewWordBoxes` on.
///
/// Names describe what each is for (CD: not app-metaphors). The declaration order is the default
/// ⌘⌥1–6 slot order; ⌘⌥7–9 are left for user workspaces (the slot→workspace map, CD-approved).
enum BuiltInWorkspaceLayout: String, CaseIterable, Identifiable, Sendable {
    case read           // ⌘⌥1  [ library·table / reader ] · preview
    case browse         // ⌘⌥2  library·icons · preview · reader
    case transcribe     // ⌘⌥3  [ preview | reader ] over library·icons
    case transcribeTall // ⌘⌥4  [ preview | word-boxes | editor ] over library·icons (three-long)
    case compare        // ⌘⌥5  [ page A | page B | reader ] over library·icons

    var id: String { rawValue }

    var title: String {
        switch self {
        case .read: "Read"
        case .browse: "Browse"
        case .transcribe: "Transcribe"
        case .transcribeTall: "Transcribe · Tall"
        case .compare: "Compare"
        }
    }

    var systemImage: String {
        switch self {
        case .read: "text.book.closed"
        case .browse: "sidebar.squares.left"
        case .transcribe: "text.viewfinder"
        case .transcribeTall: "rectangle.split.3x1"
        case .compare: "rectangle.split.2x1"
        }
    }

    /// One-line description of the arrangement (for the Manager and menus).
    var summary: String {
        switch self {
        case .read: "The table over a reader, the page beside."
        case .browse: "Icons, then the page, then the reader."
        case .transcribe: "The page and the editor over a strip of pages."
        case .transcribeTall: "The page, its word-boxes and the editor, over a strip of pages."
        case .compare: "Two witnesses side by side with the reader, over a strip of pages."
        }
    }

    /// The default ⌘⌥N slot (1-based declaration position) — the built-in half of the
    /// slot→workspace map. ⌘⌥7–9 (beyond the six) are user-assignable.
    var defaultSlot: Int { (Self.allCases.firstIndex(of: self) ?? 0) + 1 }

    /// The composition.
    var panes: PaneList {
        switch self {
        // CD 2026-09-16 — the workspace set redesigned from the CD's Mail-referenced sketch. NOTE:
        // per-pane `libraryLayout` (table vs icons) is not yet read by the renderer (it uses the
        // window's global layout); wiring that is the next step so these actually look different.
        case .read:
            // Default (Mail-style): table at top, reader below, preview to the right.
            return PaneList([
                .split(.vertical, [
                    .leaf(.library, config: PaneConfig(libraryLayout: "table")),
                    .leaf(.reading)
                ]),
                .leaf(.preview)
            ])
        case .browse:
            // Icon view (vertical column), then preview, then reader — "like we had it".
            return PaneList([
                .leaf(.library, config: PaneConfig(libraryLayout: "icons")),
                .leaf(.preview),
                .leaf(.reading)
            ])
        case .transcribe:
            // Icons along the bottom, preview above and reader to its right.
            return PaneList([
                .split(.vertical, [
                    .split(.horizontal, [.leaf(.preview), .leaf(.reading)]),
                    .leaf(.library, config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        case .transcribeTall:
            // Three-long (CD 2026-09-16): the page, its word-box overlay, and the editor across the
            // top, over the strip of pages. The middle preview carries the OCR word boxes — the
            // detailed-transcription triptych. Two previews are instance-safe (the focused-value
            // guard flags the second secondary).
            return PaneList([
                .split(.vertical, [
                    .split(.horizontal, [
                        .leaf(.preview),
                        .leaf(.preview, config: PaneConfig(previewWordBoxes: true)),
                        .leaf(.reading)
                    ]),
                    .leaf(.library, config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        case .compare:
            // Icons along the bottom, with TWO previews and one reader above (two witnesses side by
            // side + the reader). Two previews are instance-safe (the focused-value guard flags the
            // second secondary); the ⌘⌥4 crash was the animated swap, now removed (5bd6cf61a).
            return PaneList([
                .split(.vertical, [
                    .split(.horizontal, [.leaf(.preview), .leaf(.preview), .leaf(.reading)]),
                    .leaf(.library, config: PaneConfig(libraryLayout: "icons", paneExtent: 72))
                ])
            ])
        }
    }
}
