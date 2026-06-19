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
/// reading pane into a different layout. When the available width is too small,
/// the plan drops the reading pane first, then the canvas.
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

    var minimumWidth: Double {
        var minimumWidth = 0.0
        if showsLibraryPane {
            minimumWidth += ContentView.contentListMinWidth
        }
        if showsCanvasPane {
            minimumWidth += max(ContentView.pdfCanvasMinWidth, 300)
        }
        if showsReadingPane {
            minimumWidth += ContentView.readingPaneMinWidth
        }
        return showsLibraryPane ? max(minimumWidth, ContentView.contentListMinWidth) : minimumWidth
    }

    func collapsed(toFit availableWidth: Double) -> WidescreenPanePlan {
        if !showsLibraryPane {
            if showsCanvasPane {
                return showsReadingPane && availableWidth < minimumWidth
                    ? WidescreenPanePlan(
                        showsLibraryPane: false,
                        showsCanvasPane: true,
                        showsReadingPane: false
                    )
                    : self
            }

            if showsReadingPane {
                return self
            }

            return self
        }

        var plan = self
        while plan.minimumWidth > availableWidth {
            if plan.showsReadingPane {
                plan = WidescreenPanePlan(
                    showsLibraryPane: plan.showsLibraryPane,
                    showsCanvasPane: plan.showsCanvasPane,
                    showsReadingPane: false
                )
                continue
            }

            if plan.showsCanvasPane {
                plan = WidescreenPanePlan(
                    showsLibraryPane: plan.showsLibraryPane,
                    showsCanvasPane: false,
                    showsReadingPane: false
                )
                continue
            }

            break
        }
        return plan
    }

    static func make(
        showDocumentGrid: Bool,
        showDocumentCanvas: Bool,
        showReadingPane: Bool,
        availableWidth: Double? = nil
    ) -> WidescreenPanePlan {
        let plan = WidescreenPanePlan(
            showsLibraryPane: showDocumentGrid,
            showsCanvasPane: showDocumentCanvas,
            showsReadingPane: showReadingPane
        )
        guard let availableWidth, availableWidth > 0 else {
            return plan
        }
        return plan.collapsed(toFit: availableWidth)
    }
}

/// Toolbar behavior for the independent Library / Canvas / Reading pane buttons.
///
/// Canvas and Reading only render as separate panes in widescreen mode. If the
/// user presses one of those buttons from None or Standard, treat it as an
/// explicit request to enter the stable widescreen workspace and show that pane.
struct ReadingWorkspacePaneTogglePolicy {
    struct Result: Equatable {
        let layoutMode: LayoutMode
        let paneVisible: Bool
    }

    static func isPaneVisible(layoutMode: LayoutMode, paneFlag: Bool) -> Bool {
        layoutMode == .widescreen && paneFlag
    }

    static func toggledPane(layoutMode: LayoutMode, paneFlag: Bool) -> Result {
        if layoutMode != .widescreen {
            return Result(layoutMode: .widescreen, paneVisible: true)
        }
        return Result(layoutMode: .widescreen, paneVisible: !paneFlag)
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

/// Maps spatial scene node ids back to library document ids.
struct SpatialDocumentSelection {
    static func documentId(forNodeId nodeId: String?) -> String? {
        guard let nodeId, !nodeId.isEmpty else { return nil }
        if nodeId.hasPrefix("doc-") {
            return String(nodeId.dropFirst("doc-".count))
        }
        if nodeId.hasPrefix("doc:") {
            return String(nodeId.dropFirst("doc:".count))
        }
        return nil
    }
}
