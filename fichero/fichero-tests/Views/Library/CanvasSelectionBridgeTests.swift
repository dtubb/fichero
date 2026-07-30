@testable import Fichero
import Foundation
import Testing

/// #4192 — the Canvas (2D) and Spatial (3D) library view modes must behave like
/// the other view modes, including selection.
///
/// They did not: `LibraryView` handed both canvases a private
/// `@State spatialSelectedNodeId` that nothing else read or wrote. So selecting
/// a row in List and switching to Canvas showed nothing selected, and clicking
/// a card on the Canvas never reached `selection` — which drives the inspector,
/// the toolbar buttons, and every selection-scoped command. Two pieces of state
/// for one idea.
///
/// `canvasSelectedNodeIds` is now a projection of the SAME `selection` set, and
/// these tests pin the translation in both directions.
@Suite("Canvas selection is the library selection (#4192)")
struct CanvasSelectionBridgeTests {

    // MARK: - Library selection → canvas node

    @Test("a selected document becomes its spatial node id")
    func singleSelectionMapsToNode() {
        #expect(LibraryView.canvasNodeIds(forSelection: ["doc-1"]) == ["doc:doc-1"])
    }

    @Test("no selection means no selected node")
    func emptySelectionMapsToNil() {
        #expect(LibraryView.canvasNodeIds(forSelection: []).isEmpty)
    }

    /// The canvas model is ONE node. Showing an arbitrary member of a five-row
    /// selection would be a lie about what is selected, and the full set is
    /// still there when the user switches back to a list mode.
    @Test("a multi-selection selects no single node rather than an arbitrary one")
    func multiSelectionMapsToNil() {
        // #4409: these ASSERTED the defect. A multi-selection mapped to nil,
        // so the canvas showed nothing selected when several rows were. The
        // bridge now carries every member.
        #expect(LibraryView.canvasNodeIds(forSelection: ["doc-1", "doc-2"]).count == 2)
        #expect(LibraryView.canvasNodeIds(forSelection: ["a", "b", "c"]).count == 3)
    }

    // MARK: - Canvas node → library selection

    @Test("clicking a document card selects that document")
    func nodeMapsToSelection() {
        #expect(LibraryView.librarySelection(forCanvasNodeIds: ["doc:doc-1"]) == ["doc-1"])
    }

    @Test("clicking the background clears the selection")
    func nilNodeClearsSelection() {
        #expect(LibraryView.librarySelection(forCanvasNodeIds: []).isEmpty)
    }

    /// Entity orbs and standalone canvas items have no row in any list mode, so
    /// they select no document — they must not be coerced into one.
    @Test("a non-document node selects no document")
    func nonDocumentNodesSelectNothing() {
        #expect(LibraryView.librarySelection(forCanvasNodeIds: ["entity:e-1"]).isEmpty)
        #expect(LibraryView.librarySelection(forCanvasNodeIds: ["item-42"]).isEmpty)
        #expect(LibraryView.librarySelection(forCanvasNodeIds: [""]).isEmpty)
    }

    // MARK: - Round trips

    @Test("document → node → document is the identity")
    func documentRoundTrip() {
        for documentId in ["doc-1", "abc-123", "a", "doc:weird"] {
            let nodeIds = LibraryView.canvasNodeIds(forSelection: [documentId])
            #expect(LibraryView.librarySelection(forCanvasNodeIds: nodeIds) == [documentId])
        }
    }

    /// The bridge agrees with the id scheme the projector actually emits — the
    /// canvas renders nodes built by `SpatialLibraryProjector`, so a mismatch
    /// here means clicking a card selects nothing.
    @Test("the bridge uses the projector's own node ids")
    func agreesWithTheProjector() {
        let projected = SpatialLibraryProjector.nodeId(forDocument: "doc-9")
        #expect(LibraryView.canvasNodeIds(forSelection: ["doc-9"]) == [projected])
        #expect(LibraryView.librarySelection(forCanvasNodeIds: [projected]) == ["doc-9"])
    }

    /// Clearing on the canvas must not be mistaken for "keep the old selection".
    @Test("clearing on the canvas clears the library selection")
    func clearingPropagates() {
        let selection = LibraryView.librarySelection(forCanvasNodeIds: [])
        #expect(selection == Set<String>())
        #expect(LibraryView.canvasNodeIds(forSelection: selection).isEmpty)
    }

    // MARK: - The user-visible bug (#4409)

    /// Select several rows in a list mode, switch to canvas, switch back: the
    /// selection must be exactly what it was.
    ///
    /// This is the round trip the old bridge broke. `canvasNodeId` mapped any
    /// multi-selection to nil, so the canvas showed nothing selected — and
    /// anything the canvas then wrote back replaced the set with one id or
    /// none. A five-row selection did not survive looking at it.
    @Test("a multi-selection survives a switch to canvas and back")
    func multiSelectionSurvivesTheRoundTrip() {
        for selection in [
            Set(["doc-1"]),
            Set(["doc-1", "doc-2"]),
            Set(["a", "b", "c", "d", "e"])
        ] {
            let onCanvas = LibraryView.canvasNodeIds(forSelection: selection)
            let backInList = LibraryView.librarySelection(forCanvasNodeIds: onCanvas)

            #expect(onCanvas.count == selection.count, Comment(rawValue: "\(selection)"))
            #expect(backInList == selection, Comment(rawValue: "\(selection) -> \(backInList)"))
        }
    }

    /// The round trip must not invent a selection either — an empty one stays
    /// empty rather than becoming "everything" or a stray node.
    @Test("an empty selection round-trips to empty")
    func emptySelectionSurvivesTheRoundTrip() {
        let onCanvas = LibraryView.canvasNodeIds(forSelection: [])
        #expect(onCanvas.isEmpty)
        #expect(LibraryView.librarySelection(forCanvasNodeIds: onCanvas).isEmpty)
    }

    /// Non-document nodes still select no document — that half of the mapping
    /// was correct and stays. A canvas holding an entity orb beside two
    /// documents round-trips to the two documents, not three ids.
    @Test("non-document nodes drop out without disturbing the rest")
    func nonDocumentNodesDropOut() {
        let mixed: Set<String> = ["doc:doc-1", "doc:doc-2", "entity:e-1", "item-42"]
        #expect(LibraryView.librarySelection(forCanvasNodeIds: mixed) == ["doc-1", "doc-2"])
    }

}
