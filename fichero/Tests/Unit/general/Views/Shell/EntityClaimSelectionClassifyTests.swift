@testable import Fichero
import Testing

/// #4850 / #4862 — `ContentView.handleBrowserSelectionChange` classifies the selected row's OWN
/// id first (`ContentView.browserRowAction(forNodeId:)`), instead of relying on the ambient
/// "which collection is the sidebar showing" flag. The prior code passed the row's COMPOSITE
/// outline id ("<doc>:entity:<id>") straight to `kgFocusState.focusEntity(entityId:)`, which
/// asked the engine for `GET /api/entities/<doc>:entity:<id>` — a guaranteed 404, surfaced as
/// "Entity Unavailable" in the inspector.
///
/// The decision is a pure function of the id, so these tests run it on real composite ids
/// (replacing the source scrapes of the handler, #5052).
///
/// Spec: kg-entity-inspector `kg.entity.select.inspector-shows-entity`.
struct EntityClaimSelectionClassifyTests {

    @Test("an entity row focuses the BARE item id, never the composite outline id (#4850)")
    func entityRowFocusesBareId() {
        #expect(ContentView.browserRowAction(forNodeId: "doc-1:entity:e9") == .focusEntity("e9"))
        // A document id that itself contains a colon survives; only the entity id is taken.
        #expect(ContentView.browserRowAction(forNodeId: "container:wf:entity:e9") == .focusEntity("e9"))
    }

    @Test("an entity GROUP row focuses nothing (no item id to focus)")
    func entityGroupRowFocusesNothing() {
        #expect(ContentView.browserRowAction(forNodeId: "doc-1:entities") == .focusEntity(nil))
    }

    @Test("a claim row never reaches the document-promotion path (#4850)")
    func claimRowIsIgnored() {
        #expect(ContentView.browserRowAction(forNodeId: "doc-1:claim:c1") == .ignore)
    }

    @Test("a page row promotes its OWN bare page id, never the composite (#4862)")
    func pageRowPromotesItsOwnId() {
        #expect(ContentView.browserRowAction(forNodeId: "pdf-1:page:p7") == .promotePage("p7"))
    }

    @Test("artifact and note rows are a safe no-op here (#4862)")
    func artifactAndNoteRowsAreIgnored() {
        #expect(ContentView.browserRowAction(forNodeId: "doc-1:artifact:a1") == .ignore)
        #expect(ContentView.browserRowAction(forNodeId: "doc-1:notes") == .ignore)
    }

    @Test("a plain document row falls through to the document path")
    func documentRowIsNotClassified() {
        #expect(ContentView.browserRowAction(forNodeId: "doc-1") == .notClassified)
    }
}
