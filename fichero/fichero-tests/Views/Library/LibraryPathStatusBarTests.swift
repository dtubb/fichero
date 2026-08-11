@testable import Fichero
import Testing

// The library pane's Finder-style path + status rows (#106-108, 2026-08-09).
@Suite("libraryStatusText / libraryPathCrumbs — the pane's bottom rows")
struct LibraryPathStatusBarTests {
    @Test("status grammar matches Finder: items / K of N selected")
    func statusGrammar() {
        #expect(libraryStatusText(selectionCount: 0, itemCount: 5) == "5 items")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 1) == "1 item")
        #expect(libraryStatusText(selectionCount: 2, itemCount: 5) == "2 of 5 selected")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 0) == "0 items")
    }

    private let root = Document(id: "root", docType: .folder, name: "Letters")
    private let child = Document(id: "child", parentId: "root", docType: .folder, name: "1893")
    private let leaf = Document(id: "leaf", parentId: "child", docType: .file, name: "scan.tif")

    private func resolve(_ id: String) -> Document? {
        [root, child, leaf].first { $0.id == id }
    }

    @Test("crumbs walk parentId root-first from the anchor")
    func crumbsWalkRootFirst() {
        let crumbs = libraryPathCrumbs(anchorId: "leaf", resolve: resolve)
        #expect(crumbs.map(\.id) == ["root", "child", "leaf"])
    }

    @Test("unresolvable anchor or nil yields no crumbs; missing parents stop the walk")
    func crumbsDegradeQuietly() {
        #expect(libraryPathCrumbs(anchorId: nil, resolve: resolve).isEmpty)
        #expect(libraryPathCrumbs(anchorId: "ghost", resolve: resolve).isEmpty)
        let orphan = Document(id: "o", parentId: "missing", docType: .file, name: "o.pdf")
        let crumbs = libraryPathCrumbs(anchorId: "o") { id in id == "o" ? orphan : nil }
        #expect(crumbs.map(\.id) == ["o"])
    }

    @Test("a cyclic parent chain terminates")
    func cycleGuard() {
        let a = Document(id: "a", parentId: "b", docType: .folder, name: "A")
        let b = Document(id: "b", parentId: "a", docType: .folder, name: "B")
        let crumbs = libraryPathCrumbs(anchorId: "a") { id in id == "a" ? a : (id == "b" ? b : nil) }
        #expect(crumbs.count <= 3)
    }
}
