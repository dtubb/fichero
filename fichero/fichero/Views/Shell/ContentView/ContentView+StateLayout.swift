import SwiftUI

// MARK: - ContentView Layout & Window Sizing State

extension ContentView {

    /// Library/Search own the stable reading workspace: Library/List,
    /// Document Canvas, Reading/WebKit, plus the window-level inspector.
    /// This is independent of the current layout so toolbar pane buttons
    /// don't disappear when previews are temporarily hidden.
    var supportsReadingWorkspace: Bool {
        (sidebarMode == .library && !isEntityLibrarySelection) || sidebarMode == .search
    }

    /// Available display modes for the current sidebar mode.
    /// Library is icon-only in 0.0.1 unless advanced views are explicitly enabled.
    var availableViewDisplayModes: [ViewDisplayMode] {
        switch sidebarMode {
        case .library:
            if isEntityLibrarySelection {
                return [.list]
            }
            if let doc = libraryViewDocument,
               doc.docType == .folder || doc.isWorkspace ||
               (doc.docType == .file && doc.fileType.map { [.pdf, .word, .epub, .presentation].contains($0) } ?? false) {
                // Canvas (.canvas → Spatial2DCanvas) is the live 2D positioned-node
                // library view; Space (.space → SpaceSceneView) is the RealityKit
                // 3D renderer on the SAME shared stores (#3088). Both offered for
                // every folder/pdf/node (#2667/#3081/#3088).
                return [.icon, .list, .table, .canvas, .space]
            }
            if !featureManager.isLibraryAdvancedViewsEnabled {
                return [.icon]
            }
            return [.icon, .list, .table, .canvas, .space]
        case .search:
            if !featureManager.isSearchAdvancedViewsEnabled {
                return [.list]
            }
            return [.icon, .list, .table, .canvas]
        case .workflows:
            // Keep workflow editor simple by default; only expose table mode
            // when advanced views are explicitly enabled.
            if !featureManager.isWorkflowEditorAdvancedViewsEnabled {
                return [.icon, .list]
            }
            return [.icon, .list, .table]
        case .chat, .automation, .activity, .research, .knowledgeGraph:
            return [.icon]
        }
    }

    var libraryViewDocument: Document? {
        if case .library(let doc) = viewMode { return doc }
        return nil
    }

    var isEntityLibrarySelection: Bool {
        sidebarSelectionState.selectedItemId == "entities-browser"
    }

    var shellCollapsePolicy: ShellCollapsePolicy {
        Self.shellCollapsePolicy(
            windowWidth: measuredWindowWidth,
            horizontalSizeClass: horizontalSizeClass,
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    var shouldUseRuntimeSidebarCollapse: Bool {
        shellCollapsePolicy.collapseSidebar
    }

    var effectiveShowInspectorSidebar: Bool {
        showInspectorSidebar && !shellCollapsePolicy.collapseInspector
    }

    var shouldUseSplittablePane: Bool {
        Self.shouldUseSplittablePane(
            horizontalSizeClass: horizontalSizeClass,
            windowWidth: measuredWindowWidth,
            minimumWidth: paneAwareWindowMinWidth
        )
    }

    var inspectorPlacement: InspectorPlacement {
        InspectorPlacement.adaptiveDefault(horizontalSizeClass: horizontalSizeClass)
    }

    var usesDockedInspector: Bool {
        inspectorPlacement != .sheet
    }

    var paneAwareDetailMinWidth: Double {
        guard supportsReadingWorkspace else {
            return ContentView.contentMinWidth
        }

        switch currentLayoutMode {
        case .none:
            return showDocumentGrid ? ContentView.contentListMinWidth : max(ContentView.pdfCanvasMinWidth, 300)
        case .standard:
            return showDocumentGrid
                ? max(ContentView.contentListMinWidth, max(ContentView.pdfCanvasMinWidth, 300))
                : max(ContentView.pdfCanvasMinWidth, 300)
        case .widescreen:
            return adaptiveWidescreenPanePlan.minimumWidth
        }
    }

    static func adaptiveWidescreenAvailableWidth(
        windowWidth: Double?,
        inspectorVisible: Bool
    ) -> Double? {
        guard let windowWidth, windowWidth > 0 else { return nil }
        return max(0, windowWidth - (inspectorVisible ? ContentView.inspectorMinWidth : 0))
    }

    var adaptiveWidescreenPanePlan: WidescreenPanePlan {
        // Keep the reading workspace legible by dropping secondary panes as
        // the shell narrows, before SwiftUI has to overlap columns.
        let availableDetailWidth = Self.adaptiveWidescreenAvailableWidth(
            windowWidth: measuredWindowWidth,
            inspectorVisible: showInspectorSidebar
        )

        return WidescreenPanePlan.make(
            showDocumentGrid: showDocumentGrid,
            showDocumentCanvas: showDocumentCanvas,
            showReadingPane: showReadingPane,
            availableWidth: availableDetailWidth
        )
    }

    var paneAwareWindowMinWidth: Double {
        Self.windowMinWidth(
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    var shellWindowMinWidth: Double {
        Self.shellWindowMinWidth(
            windowWidth: measuredWindowWidth,
            horizontalSizeClass: horizontalSizeClass,
            sidebarVisible: showSidebar,
            inspectorVisible: showInspectorSidebar,
            detailMinWidth: paneAwareDetailMinWidth
        )
    }

    static func windowMinWidth(
        sidebarVisible: Bool,
        inspectorVisible: Bool,
        detailMinWidth: Double
    ) -> Double {
        #if os(macOS)
        let sidebarMinWidth = sidebarVisible ? ContentView.sidebarMinWidth : 0
        // The inspector's OWN .inspectorColumnWidth enforces its column width
        // internally, but the inspector width must ALSO be included in the
        // window-level minimum. Without it, a narrow window (e.g. 400 px) gives
        // the NavigationSplitView only 150 px after the inspector takes 250 px —
        // less than sidebar + content need — causing the split view to switch to
        // overlay mode and float the sidebar OVER the library content (#2309).
        let inspectorMinWidth = inspectorVisible ? ContentView.inspectorMinWidth : 0
        return sidebarMinWidth + detailMinWidth + inspectorMinWidth
        #else
        return detailMinWidth
        #endif
    }
}
