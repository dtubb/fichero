@testable import Fichero
import Testing

/// `import.folder-shows-at-once` (#7066, the app half): the start answer puts the folder on the sidebar with a spinner,
/// the finish event clears it, a failure keeps the row with its reason.
@MainActor
struct FolderImportTrackerTests {
    @Test("the start answer marks the folder importing and asks to reveal it")
    func startAnswer() {
        let tracker = FolderImportTracker()
        tracker.begin(folderId: "f1")
        #expect(tracker.isImporting("f1"))
        #expect(tracker.pendingReveal == ["f1"])
        #expect(!tracker.isImporting("other"))
    }

    @Test("the finish event clears the spinner")
    func finish() {
        let tracker = FolderImportTracker()
        tracker.begin(folderId: "f1")
        tracker.finish(folderId: "f1")
        #expect(!tracker.isImporting("f1") && tracker.error(for: "f1") == nil && tracker.pendingReveal.isEmpty)
    }

    @Test("a failure keeps the row, marked, with its reason, until it is dismissed")
    func failure() {
        let tracker = FolderImportTracker()
        tracker.begin(folderId: "f1")
        tracker.fail(folderId: "f1", reason: "No canvases found")
        #expect(!tracker.isImporting("f1"))
        #expect(tracker.error(for: "f1") == "No canvases found")
        tracker.dismissError(folderId: "f1")
        #expect(tracker.error(for: "f1") == nil)
    }

    @Test("the ancestors to open are the parents, nearest first, and a cycle ends")
    func ancestors() {
        let parents = ["f": "b", "b": "a", "a": "f"]
        #expect(FolderImportTracker.ancestors(of: "f", parentOf: { parents[$0] }) == ["b", "a"])
        #expect(FolderImportTracker.ancestors(of: "x", parentOf: { _ in nil }).isEmpty)
    }
}
