@testable import Fichero
import Testing

/// #4860 audit finding: `LibraryView.documentId(forNodeId:)` split a node id
/// on its FIRST colon — a document id that itself contains a colon (a
/// "container:<name>" default-workflow subfolder, the same example #4850's
/// fix for `LibraryOutlineNode.parse` cites) split wrong. Now delegates to
/// `LibraryOutlineNode.parse(nodeId:)`, which searches from the RIGHT for
/// the marker `id` actually mints.
///
/// The `LibraryView` wrapper was removed (#5052): the Table view calls
/// `LibraryOutlineNode.parse(nodeId:).documentId` directly, so no first-colon split can be
/// reintroduced there, and this pins the parser itself.
@Suite(.tags(.knowledgeGraph))
struct LibraryTableDocumentIdTests {
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
