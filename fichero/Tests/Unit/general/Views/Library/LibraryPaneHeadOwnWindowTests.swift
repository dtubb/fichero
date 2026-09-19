@testable import Fichero
import Testing

/// #4860, `panes.head.names-its-own-window`: the library pane's head must
/// name ITS OWN window's library, never the app-wide
/// `LibraryManager.shared.currentLibraryId` — with two window tabs on
/// different libraries, that app-wide pointer names whichever tab was
/// activated most recently ANYWHERE, so a second tab's pane head could show
/// the WRONG library's breadcrumb root (and drag the wrong library's items).
/// Same shape as the `KGFocusState` singleton fix.
@Suite(.tags(.knowledgeGraph))
struct LibraryPaneHeadOwnWindowTests {
    private static func appSource() throws -> String {
        try AppSource.text("Views/Library/LibraryView+PaneHead.swift")
    }

    @Test("the breadcrumb root reads this window's own library, not the app-wide pointer")
    func breadcrumbRootReadsThisWindowsLibrary() throws {
        let source = try Self.appSource()
        let body = try #require(
            source.components(separatedBy: "private var libraryHeadCrumbs: [PaneCrumb] {").dropFirst().first
        )
        // Bounded by the property's own closing brace, a structural marker.
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(scope.contains("windowState.libraryId"))
        #expect(!scope.contains("LibraryManager.shared.currentLibraryId"))
    }

    @Test("the crumb drag payload reads this window's own library, not the app-wide pointer")
    func crumbDragPayloadReadsThisWindowsLibrary() throws {
        let source = try Self.appSource()
        let body = try #require(
            source.components(separatedBy: "crumbDragPayload: { crumb in").dropFirst().first
        )
        let scope = try #require(body.components(separatedBy: "},").first)
        #expect(scope.contains("windowState.libraryId"))
        #expect(!scope.contains("LibraryManager.shared.currentLibraryId"))
    }
}
