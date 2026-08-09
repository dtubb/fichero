import Foundation
import PDFKit

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

/// Page-arrangement modes for the reading surface (#2090) — how the pages of a
/// PDF or image-sequence document are laid out: 1-up · 2-up (facing spread) ·
/// 3-up · 4-up, each optionally continuous-scrolling.
///
/// Unifies PDFKit's native display modes (Tier 1: single / single-continuous /
/// two-up / two-up-continuous — PDFKit's ceiling is two-up) with the custom
/// N-up image grid (Tier 2: three-up / four-up, and *all* modes for image
/// documents, which have no `PDFView`). The reader toolbar, View menu, and
/// per-window `@SceneStorage` all key off this one value type, so a host branches
/// PDFKit-native vs custom-grid on `pdfDisplayMode`/`isPDFKitNative` and drives
/// the shared `LazyVGrid` off `columns`.
enum PageLayoutMode: String, CaseIterable, Identifiable {
    case singlePage = "Single Page"
    case singleContinuous = "Single Page Continuous"
    case twoUp = "Two Up"
    case twoUpContinuous = "Two Up Continuous"
    case threeUp = "Three Up"
    case fourUp = "Four Up"

    var id: String { rawValue }

    /// Menu / tooltip label.
    var label: String { rawValue }

    /// Number of page columns rendered side-by-side. Drives the shared grid for
    /// the custom (image / 3-4-up) renderer.
    var columns: Int {
        switch self {
        case .singlePage, .singleContinuous: 1
        case .twoUp, .twoUpContinuous: 2
        case .threeUp: 3
        case .fourUp: 4
        }
    }

    /// Whether pages scroll continuously (vs one paged spread at a time). The
    /// multi-column grid modes (3/4-up) always scroll.
    var isContinuous: Bool {
        switch self {
        case .singleContinuous, .twoUpContinuous, .threeUp, .fourUp: true
        case .singlePage, .twoUp: false
        }
    }

    /// The PDFKit display mode for this layout, or `nil` when it exceeds
    /// PDFKit's two-up ceiling and must render through the custom page-image
    /// grid (Tier 2). Image documents ignore this — they always use the grid.
    var pdfDisplayMode: PDFDisplayMode? {
        switch self {
        case .singlePage: .singlePage
        case .singleContinuous: .singlePageContinuous
        case .twoUp: .twoUp
        case .twoUpContinuous: .twoUpContinuous
        case .threeUp, .fourUp: nil
        }
    }

    /// True when PDFKit renders this natively; false ⇒ the shared image grid.
    var isPDFKitNative: Bool { pdfDisplayMode != nil }

    /// SF Symbol for the toolbar / menu.
    var systemImage: String {
        switch self {
        case .singlePage: "rectangle.portrait"
        case .singleContinuous: "scroll"
        case .twoUp: "book"
        case .twoUpContinuous: "book.pages"
        case .threeUp: "rectangle.split.3x1"
        case .fourUp: "square.grid.2x2"
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
        // Zero is a real collapse input here; it must still flow through the
        // collapse policy so the plan can shed panes at the edge case.
        let plan = WidescreenPanePlan(
            showsLibraryPane: showDocumentGrid,
            showsCanvasPane: showDocumentCanvas,
            showsReadingPane: showReadingPane
        )
        guard let availableWidth else {
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
/// A plain click should always drive the in-window detail/inspector selection.
/// Open-in-new-window/tab stays on the explicit affordances.
struct BrowserSelectionPreviewPolicy {
    static func shouldPromoteSelectionToDetail(
        layoutMode _: LayoutMode,
        selectedDocumentId: String?,
        currentDetailDocumentId: String?
    ) -> Bool {
        guard let selectedDocumentId else {
            return false
        }
        return selectedDocumentId != currentDetailDocumentId
    }

    /// Whether a sidebar-selection change is a browse-CONTEXT change that
    /// should reset the grid selection (and, through the selection cascade,
    /// the detail/preview document).
    ///
    /// Clicking a `doc:` folder row IS a context change — the stale selection
    /// from the previous folder must not shadow the new folder's inspector
    /// (#712). But clicking the library root row (`library:<UUID>`, the
    /// "/library" location) only re-roots the listing: nuking the selection
    /// there blanked the preview pane while the user still had an image
    /// selected (#4299). Empty-pane states are only for genuinely-nothing-
    /// selected, so the library-row click preserves selection → detail.
    static func shouldClearBrowseContext(onSidebarItemChangeTo newItemId: String?) -> Bool {
        guard let newItemId else { return true }
        return !newItemId.hasPrefix("library:")
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
        // Document-order primary, never Set.first (F3, 2026-08-09): this
        // feeds BOTH preview call sites, and a hash-order draw here while
        // the shell resolves in document order meant the preview and the
        // detail could name DIFFERENT members of one multi-selection.
        if let selectedId = shellPrimarySelectionId(in: selectedDocumentIds, orderedBy: documents),
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
