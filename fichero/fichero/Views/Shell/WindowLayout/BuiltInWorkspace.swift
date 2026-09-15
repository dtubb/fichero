import Foundation

// MARK: - Built-in workspaces (Daniel, 2026-08-31)

/// The arrangements that ship with the app, so the Workspaces menu is useful
/// before anyone has saved anything ("can we have some defaults?"). Declaration
/// order IS the menu order and the ⌘⌥1–9 order (spec panes-magnifiers-workspaces,
/// the best-nine; #7–9 Compare/Claims/Entities need a per-pane view-mode/scope the
/// PaneVisibilityPlan model can't yet carry, so they land once that's designed).
///
/// A built-in is not stored in the catalog — it is COMPUTED — so it can
/// neither be deleted nor go stale, and "reset" is simply choosing it again.
/// It decides only the chrome it means: pane set, workflow bar, and which
/// toolbar buttons show. Widths, splits, kind overrides and the view mode
/// stay exactly as the user has them, because a built-in cannot know them.
enum BuiltInWorkspace: String, CaseIterable, Identifiable, Sendable {
    case library
    case reader
    case source
    case reading
    case cataloguing
    case everything

    var id: String { rawValue }

    /// The ⌘⌥N number this workspace binds to (1-based position, ≤9), or nil
    /// past nine. The keyboard shortcut itself is applied in the command layer.
    var shortcutNumber: Int? {
        guard let index = Self.allCases.firstIndex(of: self) else { return nil }
        let number = index + 1
        return number <= 9 ? number : nil
    }

    var title: String {
        switch self {
        case .library: "Library"
        case .reader: "Reader"
        case .source: "Source"
        case .reading: "Close Reading"
        case .cataloguing: "Cataloguing"
        case .everything: "Everything"
        }
    }

    var systemImage: String {
        switch self {
        case .library: "sidebar.left"
        case .reader: "book"
        case .source: "photo"
        case .reading: "book.pages"
        case .cataloguing: "tray.full"
        case .everything: "rectangle.split.3x1"
        }
    }

    var help: String {
        switch self {
        case .library: "The library list on its own — for browsing"
        case .reader: "Library beside the reader — the transcription desk"
        case .source: "Library beside the full-height page image"
        case .reading: "Library, page image and reader together — close reading"
        case .cataloguing: "Library, preview, inspector and the workflow bar"
        case .everything: "Every pane and every toolbar button"
        }
    }

    var panes: PaneVisibilityPlan {
        switch self {
        case .library:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: false,
                showReaderPane: false, showChatPane: false
            )
        case .reader:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: false,
                showReaderPane: true, showChatPane: false
            )
        case .source:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: false, showChatPane: false
            )
        case .reading:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: false,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: true, showChatPane: false
            )
        case .cataloguing:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: true,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: false, showChatPane: false
            )
        case .everything:
            PaneVisibilityPlan(
                showSidebar: true, showInspector: true,
                showLibraryPane: true, showPreviewPane: true,
                showReaderPane: true, showChatPane: true
            )
        }
    }

    /// The workflow bar rides with Cataloguing — that is what cataloguing is.
    var showsWorkflowBar: Bool { self == .cataloguing }

    /// The markup bar rides with a reader — annotating is what a reading desk
    /// is for, and a built-in that names the workflow bar but stays silent
    /// about the markup bar leaves half the chrome wherever it happened to be.
    var showsMarkupBar: Bool { self == .reader || self == .reading }

    var toolbar: ToolbarVisibilityPlan {
        switch self {
        case .library, .reader, .source, .reading: .minimal
        case .cataloguing, .everything: .everything
        }
    }

    /// Whether the window is currently arranged exactly this way — drives the
    /// menu's checkmark. Compares only what the built-in decides.
    func matches(
        panes current: PaneVisibilityPlan,
        toolbar currentToolbar: ToolbarVisibilityPlan,
        workflowBar: Bool,
        markupBar: Bool
    ) -> Bool {
        panes == current
            && toolbar == currentToolbar
            && showsWorkflowBar == workflowBar
            && showsMarkupBar == markupBar
    }
}
