@testable import Fichero
import XCTest

/// #4292 + #4293 — the workflow sidebar family.
///
/// #4292: selecting a workflow mirror row (engine-mirrored `.file` doc with
/// `prototype_key == "workflow"`) routed like a plain document into the
/// library/preview path, whose container fallback is "No Preview available".
/// It must route to the workflow EDITOR.
///
/// #4293: workflow folders (and any folder-of-folders two levels down) never
/// showed a disclosure chevron: the expand hook skipped `loadSidebarChildren`
/// when the row's own children were already cached, but that call is ALSO what
/// prefetches the grandchildren — so prefetched folders' subfolders never got
/// children cached and rendered chevron-less.
@MainActor
final class SidebarWorkflowRoutingTests: XCTestCase {

    private func makeMirror(id: String, name: String) -> Document {
        Document(id: id, docType: .file, fileType: nil, name: name, prototypeKey: "workflow")
    }

    // MARK: - #4292 destination resolution

    /// The mirror resolves to the live store item sharing its id.
    func testMirrorResolvesToStoreWorkflowById() {
        let store = [
            WorkflowSidebarItem(id: "wf-1", name: "Transcribe", nodeCount: 4),
            WorkflowSidebarItem(id: "wf-2", name: "Summarize", nodeCount: 2)
        ]
        let destination = sidebarWorkflowDestination(for: makeMirror(id: "wf-2", name: "Summarize"), workflows: store)
        XCTAssertEqual(destination.id, "wf-2")
        XCTAssertEqual(destination.nodeCount, 2, "must be the live store item, not a placeholder")
    }

    /// Fresh install: the store may not have loaded when the first click
    /// arrives. Routing still targets the editor with an id/name placeholder —
    /// never falls through to the preview path.
    func testMirrorFallsBackToPlaceholderWhenStoreEmpty() {
        let destination = sidebarWorkflowDestination(for: makeMirror(id: "wf-9", name: "OCR"), workflows: [])
        XCTAssertEqual(destination.id, "wf-9")
        XCTAssertEqual(destination.name, "OCR")
    }

    /// An id miss (stale store) behaves like the empty store: placeholder,
    /// same id — the editor loads the definition by id either way.
    func testMirrorWithUnknownIdKeepsItsId() {
        let store = [WorkflowSidebarItem(id: "wf-1", name: "Transcribe")]
        let destination = sidebarWorkflowDestination(for: makeMirror(id: "wf-3", name: "New Flow"), workflows: store)
        XCTAssertEqual(destination.id, "wf-3")
    }

    // MARK: - #4292 routing seam (source contract)

    /// The selection handler must special-case workflow mirror docs BEFORE the
    /// generic `.document` case, and route them to the workflows surface.
    func testSelectionHandlerRoutesWorkflowMirrorsToTheEditor() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+SelectionHandling.swift")
        let mirrorCase = source.range(of: "case .document(let doc) where doc.isWorkflowNode:")
        let genericCase = source.range(of: "case .document(let doc):")
        XCTAssertNotNil(mirrorCase, "#4292: workflow mirror rows need their own routing case")
        XCTAssertNotNil(genericCase)
        if let mirrorCase, let genericCase {
            XCTAssertTrue(
                mirrorCase.lowerBound < genericCase.lowerBound,
                "the mirror case must precede the generic document case or it is dead"
            )
        }
        XCTAssertTrue(
            source.contains("sidebarWorkflowDestination(for: doc"),
            "routing resolves the editor destination through the shared pure helper"
        )
    }

    // MARK: - #4293 expand always prefetches (source contract)

    /// Expanding any folder row must call `loadSidebarChildren`
    /// unconditionally — the old cached-children guard starved grandchildren
    /// of their prefetch and left second-level folders chevron-less.
    func testExpandAlwaysRunsTheOneLevelPrefetch() throws {
        let source = try appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        XCTAssertFalse(
            source.contains("else if item.children == nil, store.childrenCache[document.id] == nil"),
            "#4293: the cached-children guard must not come back"
        )
        XCTAssertTrue(source.contains("Task { await store.loadSidebarChildren(of: document) }"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
