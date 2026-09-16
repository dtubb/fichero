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
    case read        // ⌘⌥1  library · source · reader        (today's three columns)
    case browse      // ⌘⌥2  [ library·columns / reader ] · source
    case transcribe  // ⌘⌥3  image · [ word-boxes / editor ]
    case compare     // ⌘⌥4  [ page A / reader / library ] · [ page B / reader / related ]
    case catalogue   // ⌘⌥5  library·table · [ source / reader ] · inspector
    case claims      // ⌘⌥6  library·claims · source · inspector

    var id: String { rawValue }

    var title: String {
        switch self {
        case .read: "Read"
        case .browse: "Browse"
        case .transcribe: "Transcribe"
        case .compare: "Compare"
        case .catalogue: "Catalogue"
        case .claims: "Claims"
        }
    }

    var systemImage: String {
        switch self {
        case .read: "text.book.closed"
        case .browse: "sidebar.squares.left"
        case .transcribe: "text.viewfinder"
        case .compare: "rectangle.split.2x1"
        case .catalogue: "tray.full"
        case .claims: "quote.bubble"
        }
    }

    /// One-line description of the arrangement (for the Manager and menus).
    var summary: String {
        switch self {
        case .read: "Library, page and reader in three columns."
        case .browse: "A column browser over a reader, the full-height page beside."
        case .transcribe: "The page, its word-boxes and the editor."
        case .compare: "Two witnesses side by side — each with its page, reader and navigation."
        case .catalogue: "The table, the page over a reader, metadata docked right."
        case .claims: "Claims beside the source, the knowledge panel docked right."
        }
    }

    /// The default ⌘⌥N slot (1-based declaration position) — the built-in half of the
    /// slot→workspace map. ⌘⌥7–9 (beyond the six) are user-assignable.
    var defaultSlot: Int { (Self.allCases.firstIndex(of: self) ?? 0) + 1 }

    /// The composition.
    var panes: PaneList {
        switch self {
        case .read:
            // The default (CD 2026-09-16): 1 library above 1 reader, beside 1 preview — a left
            // column of library-over-reader, the page on the right. Single instances of each kind,
            // so it's inherently instance-safe.
            return PaneList([
                .split(.vertical, [
                    .leaf(.library, config: PaneConfig(libraryLayout: "list")),
                    .leaf(.reading)
                ]),
                .leaf(.preview)
            ])
        case .browse:
            return PaneList([
                .split(.vertical, [
                    .leaf(.library, config: PaneConfig(libraryLayout: "columns")),
                    .leaf(.reading)
                ]),
                .leaf(.preview)
            ])
        case .transcribe:
            return PaneList([
                .leaf(.preview),
                .split(.vertical, [
                    .leaf(.preview, config: PaneConfig(previewWordBoxes: true)),
                    .leaf(.reading)
                ])
            ])
        case .compare:
            // Two witness columns — each the page over its reader. Two previews + two readers is
            // safe (the focused-value guard, panes.instance-safe); TWO LIBRARY panes is NOT yet —
            // the library content view loops on shared data/selection state (loadLibraryData +
            // SidebarItemBuilder reload storm, CD live 2026-09-15, ⌘⌥4 beachball). The per-column
            // library/related nav the CD designed returns once the library pane is data-instance-safe
            // (spec panes.instance-safe-library). For now Compare collates page + reader per witness,
            // which is the core of a comparison.
            return PaneList([
                .split(.vertical, [.leaf(.preview), .leaf(.reading)]),
                .split(.vertical, [.leaf(.preview), .leaf(.reading)])
            ])
        case .catalogue:
            return PaneList([
                .leaf(.library, config: PaneConfig(libraryLayout: "table")),
                .split(.vertical, [.leaf(.preview), .leaf(.reading)]),
                .leaf(.inspector)
            ])
        case .claims:
            return PaneList([
                .leaf(.library, config: PaneConfig(libraryContentKind: "claims", libraryLayout: "table")),
                .leaf(.preview),
                .leaf(.inspector)
            ])
        }
    }
}
