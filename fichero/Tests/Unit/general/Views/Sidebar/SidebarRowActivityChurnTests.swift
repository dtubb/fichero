@testable import Fichero
import Foundation
import Observation
import Testing

/// The sidebar churn (2026-11-17, the canvas-zoom hitches): every sidebar row read its activity straight from the
/// store, so every change-stream batch (about once a second while work ran) re-rendered every visible row. Each row now
/// observes its own `RowActivityBox`, written only when its value changes.
@MainActor
struct SidebarRowActivityChurnTests {
    private func doc(_ id: String, parent: String) -> Document {
        Document(id: id, parentId: parent, docType: .file, fileType: .image, name: "\(id).jpg")
    }

    /// Whether reading `box.inputs` is told of a change by `change`.
    private func changes(_ box: RowActivityBox, after change: () -> Void) -> Bool {
        var told = false
        withObservationTracking { _ = box.inputs } onChange: { told = true }
        change()
        return told
    }

    private func store() -> DocumentStore {
        let store = DocumentStore(apiClient: APIClient())
        store.childrenCache["folder-a"] = [doc("a1", parent: "folder-a"), doc("a2", parent: "folder-a")]
        store.childrenCache["folder-b"] = [doc("b1", parent: "folder-b")]
        return store
    }

    @Test("a poll that changes nothing re-renders no sidebar row")
    func noChangeNoRender() {
        let store = store()
        let boxA = store.rowActivity(for: "folder-a"), boxB = store.rowActivity(for: "folder-b")
        store.refreshRowActivity()
        let toldA = changes(boxA) {}
        let toldB = changes(boxB) {
            store.revision += 1  // a change-stream batch that changed nothing a row shows
            store.refreshRowActivity()
        }
        #expect(!toldA && !toldB)
        #expect(boxA.inputs.busyChildren == 0 && boxB.inputs.busyChildren == 0)
    }

    @Test("a count change re-renders only that row")
    func onlyItsRow() {
        let store = store()
        let boxA = store.rowActivity(for: "folder-a"), boxB = store.rowActivity(for: "folder-b")
        store.refreshRowActivity()
        var toldA = false, toldB = false
        withObservationTracking { _ = boxA.inputs } onChange: { toldA = true }
        withObservationTracking { _ = boxB.inputs } onChange: { toldB = true }

        store.workflowStatusOverrides["a1"] = .processing
        store.refreshRowActivity()

        #expect(toldA && !toldB)
        #expect(boxA.inputs == .init(isSelfProcessing: false, busyChildren: 1, totalChildren: 2))
        #expect(boxB.inputs == .init(isSelfProcessing: false, busyChildren: 0, totalChildren: 1))
    }

    @Test("a row's box is the same box each read, so the row keeps one observation")
    func oneBoxPerRow() {
        let store = store()
        let box = store.rowActivity(for: "folder-a")
        #expect(store.rowActivity(for: "folder-a") === box)
    }

    @Test("a box nobody holds is dropped, so the refresh no longer computes it")
    func releasedBoxIsDropped() {
        let store = store()
        var box: RowActivityBox? = store.rowActivity(for: "folder-a")
        #expect(box != nil)
        box = nil
        store.refreshRowActivity()
        #expect(store.rowActivityBoxes.isEmpty)
    }
}
