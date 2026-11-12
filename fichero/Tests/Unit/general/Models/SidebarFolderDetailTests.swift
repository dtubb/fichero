@testable import Fichero
import Testing

/// A sidebar folder click changes the detail document once (#4228, `read.a-click-shows-its-folder-at-once`): the old
/// clear-then-set ran the whole detail cascade twice per click (seen in the NAVTRACE log, 2026-11-12).
struct SidebarFolderDetailTests {
    @Test("a folder in hand is one write; one to fetch clears first (#795); the same folder writes nothing")
    func oneWritePerClick() {
        #expect(SidebarFolderDetail.plan(currentDetailId: "a", folderId: "b", inHand: true) == .apply)
        #expect(SidebarFolderDetail.plan(currentDetailId: nil, folderId: "b", inHand: true) == .apply)
        #expect(SidebarFolderDetail.plan(currentDetailId: "a", folderId: "b", inHand: false) == .clearThenFetch)
        #expect(SidebarFolderDetail.plan(currentDetailId: "b", folderId: "b", inHand: false) == .keep)
    }
}
