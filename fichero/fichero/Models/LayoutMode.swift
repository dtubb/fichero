import Foundation

/// Layout modes for the main content area
/// Inspired by DevonThink's view menu
enum LayoutMode: String, CaseIterable, Identifiable {
    case none = "None"
    case standard = "Standard"
    case widescreen = "Widescreen"

    var id: String { rawValue }

    /// SF Symbol icon for toolbar
    var icon: String {
        switch self {
        case .none: "square"
        case .standard: "rectangle.split.1x2"
        case .widescreen: "rectangle.split.2x1"
        }
    }

    /// Description for menu items
    var description: String {
        switch self {
        case .none: "Content only, no preview"
        case .standard: "Content and preview side-by-side"
        case .widescreen: "Content and preview stacked vertically"
        }
    }

    /// Keyboard shortcut (optional)
    var keyboardShortcut: String? {
        switch self {
        case .none: "0"
        case .standard: "1"
        case .widescreen: "2"
        }
    }
}

/// Visibility plan for the widescreen reading workspace.
///
/// The three panes are independent user choices: Library/List, document canvas,
/// and reading/WebKit. Hiding the Library pane must not collapse the canvas or
/// reading pane into a different layout.
struct WidescreenPanePlan: Equatable {
    let showsLibraryPane: Bool
    let showsCanvasPane: Bool
    let showsReadingPane: Bool

    var showsLibraryDivider: Bool {
        showsLibraryPane && (showsCanvasPane || showsReadingPane)
    }

    var showsCanvasReadingDivider: Bool {
        showsCanvasPane && showsReadingPane
    }

    static func make(
        showDocumentGrid: Bool,
        showDocumentCanvas: Bool,
        showReadingPane: Bool
    ) -> WidescreenPanePlan {
        WidescreenPanePlan(
            showsLibraryPane: showDocumentGrid,
            showsCanvasPane: showDocumentCanvas,
            showsReadingPane: showReadingPane
        )
    }
}

/// Selection policy for the library browser's detail/canvas document.
///
/// If the user has a preview/canvas pane visible, a plain selection should drive
/// that pane. If preview is hidden, selection remains browse-only until the user
/// explicitly opens a document.
struct BrowserSelectionPreviewPolicy {
    static func shouldPromoteSelectionToDetail(
        layoutMode: LayoutMode,
        selectedDocumentId: String?,
        currentDetailDocumentId: String?
    ) -> Bool {
        guard layoutMode != .none, let selectedDocumentId else {
            return false
        }
        return selectedDocumentId != currentDetailDocumentId
    }
}

/// Chooses the document that should drive the image/PDF canvas.
///
/// The inspector can legitimately show a folder or group. The canvas accepts
/// those containers too, but renders them as a placeholder rather than hiding
/// the pane. Keeping selection precedence explicit prevents folder selection
/// from blanking the image/PDF pane while a child page remains selected in the
/// library list.
struct CanvasDocumentPolicy {
    static func isCanvasPreviewable(_ document: Document) -> Bool {
        true
    }

    static func shouldUsePDFCanvas(for document: Document) -> Bool {
        if document.fileType == .pdf {
            return true
        }
        if document.docType == .page {
            return document.fileType != .image
        }
        return false
    }

    static func documentForCanvas(
        selectedDocumentIds: Set<String>,
        documents: [Document],
        detailDocument: Document?,
        inspectorDocument: Document?
    ) -> Document? {
        if let selectedId = selectedDocumentIds.first,
           let selected = documents.first(where: { $0.id == selectedId }),
           isCanvasPreviewable(selected) {
            return selected
        }
        if let detailDocument, isCanvasPreviewable(detailDocument) {
            return detailDocument
        }
        if let inspectorDocument, isCanvasPreviewable(inspectorDocument) {
            return inspectorDocument
        }
        return nil
    }
}
