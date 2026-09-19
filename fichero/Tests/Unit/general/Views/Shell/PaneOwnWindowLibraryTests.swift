@testable import Fichero
import Testing

/// #4860 — the same-defect sites named in the audit: each pane-level
/// breadcrumb/drag-payload/new-window/artifact-scope resolution must read
/// ITS OWN window's library (`windowState.libraryId`), never the app-wide
/// `LibraryManager.shared.currentLibraryId` pointer, which names whichever
/// window tab was activated most recently ANYWHERE.
///
/// Source-scan: each site lives on a view type with heavy SwiftUI
/// dependencies and no seam to construct in a unit test — same limitation
/// `EntityClaimSelectionClassifyTests`/`LibraryPaneHeadOwnWindowTests` state
/// for themselves.
@Suite(.tags(.knowledgeGraph))
struct PaneOwnWindowLibraryTests {
    @Test("WorkflowEditor's pane-head breadcrumb reads this window's own library")
    func workflowEditorCrumbsReadOwnWindow() throws {
        let source = try AppSource.text("Views/Workflow/Editor/WorkflowEditor.swift")
        let body = try #require(
            source.components(separatedBy: "private var editorHeadCrumbs: [PaneCrumb] {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(scope.contains("windowState.libraryId"))
        #expect(!scope.contains("LibraryManager.shared.currentLibraryId"))
    }

    @Test("ReadingPaneView's crumb drag payload, new-window open, and proxy drag identity all read this window's own library")
    func readingPaneViewSitesReadOwnWindow() throws {
        // CODE only — the `windowState` property's own doc comment
        // explains what it replaces by NAMING the old app-wide pointer,
        // which would otherwise trip this exact guard.
        let source = AppSource.codeOnly(try AppSource.text("Views/Reader/Page/ReadingPaneView.swift"))
        #expect(!source.contains("LibraryManager.shared.currentLibraryId"))
        #expect(source.contains("windowState.libraryId"))

        let crumbs = try AppSource.text("Views/Reader/Page/ReadingPaneView+Crumbs.swift")
        #expect(!crumbs.contains("LibraryManager.shared.currentLibraryId"))
        #expect(crumbs.contains("windowState.libraryId"))
    }

    @Test("the artifact lens and artifact compare library fallbacks read this window's own library")
    func artifactLensAndCompareReadOwnWindow() throws {
        let lens = try AppSource.text("Views/Reader/Page/Lenses/ReadingPaneView+ArtifactLens.swift")
        #expect(!lens.contains("LibraryManager.shared.currentLibraryId"))
        #expect(lens.contains("windowState.libraryId"))

        let compare = try AppSource.text("Views/Reader/Page/Lenses/ReadingPaneView+ArtifactCompare.swift")
        #expect(!compare.contains("LibraryManager.shared.currentLibraryId"))
        #expect(compare.contains("windowState.libraryId"))
    }

    @Test("the claim card's delete action and new-window opens read this window's own library")
    func claimCardSitesReadOwnWindow() throws {
        let details = try AppSource.text(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        #expect(!details.contains("LibraryManager.shared.currentLibraryId"))

        let navigation = try AppSource.text(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCardView+Navigation.swift"
        )
        #expect(!navigation.contains("LibraryManager.shared.currentLibraryId"))
        #expect(navigation.contains("windowState.libraryId"))
    }

    @Test("the PDF toolbar's new-window open reads this pane's own window's library, with the global library only as ITS fallback")
    func pdfToolbarReadsOwnWindow() throws {
        let source = try AppSource.text("Views/Preview/PDFViewer/PDFPageWithToolbar.swift")
        let body = try #require(
            source.components(separatedBy: "private func openThisDocumentInNewWindow(asTab: Bool) {").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(scope.contains("pdfWindowState?.libraryId ?? LibraryManager.globalLibraryId"))
        #expect(!scope.contains("LibraryManager.shared.currentLibraryId"))
    }
}
