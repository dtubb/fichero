@testable import Fichero
import Testing

/// #4860 audit finding: `LibraryView.documentId(forNodeId:)` split a node id
/// on its FIRST colon — a document id that itself contains a colon (a
/// "container:<name>" default-workflow subfolder, the same example #4850's
/// fix for `LibraryOutlineNode.parse` cites) split wrong. Now delegates to
/// `LibraryOutlineNode.parse(nodeId:)`, which searches from the RIGHT for
/// the marker `id` actually mints.
///
/// Source-scan: `documentId(forNodeId:)` is an instance method on
/// `LibraryView` with heavy dependencies and no seam to construct in a unit
/// test — same limitation `EntityClaimSelectionClassifyTests` states for
/// itself.
@Suite(.tags(.knowledgeGraph))
struct LibraryTableDocumentIdTests {
    @Test("documentId(forNodeId:) delegates to LibraryOutlineNode.parse, not a first-colon split")
    func delegatesToParse() throws {
        let source = try AppSource.text("Views/Library/ViewModes/Table/LibraryView+TableView.swift")
        let body = try #require(
            source.components(separatedBy: "func documentId(forNodeId nodeId: String) -> String {").dropFirst().first
        )
        // Bounded by the function's own closing brace, a structural marker.
        let scope = try #require(body.components(separatedBy: "\n    }").first)
        #expect(scope.contains("LibraryOutlineNode.parse(nodeId: nodeId).documentId"))
        #expect(!scope.contains("firstIndex(of: \":\")"))
    }

    /// The delegated-to function itself, exercised directly (it IS pure):
    /// a document id containing its own colon must not be truncated at it.
    @Test("a document id containing a colon is not truncated at the FIRST one")
    func documentIdWithColonSurvivesIntact() {
        let parsed = LibraryOutlineNode.parse(nodeId: "container:my-workflow:page:p1")
        // The marker search is from the RIGHT: "page:" is the last marker,
        // so everything before it — including the document id's OWN colon —
        // is the document id, intact.
        #expect(parsed.documentId == "container:my-workflow")
        #expect(parsed.itemId == "p1")
    }
}
