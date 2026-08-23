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
        // The data views speak the dataset's language (2026-08-16: "1 of X
        // dates selected … make it clearer"); Finder's bare grammar above is
        // untouched when no noun is passed.
        #expect(libraryStatusText(selectionCount: 1, itemCount: 160, noun: "date",
                                  detail: "January 14, 1918")
                == "1 of 160 dates selected — January 14, 1918")
        #expect(libraryStatusText(selectionCount: 3, itemCount: 160, noun: "date",
                                  detail: "ignored for multi")
                == "3 of 160 dates selected")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 160, noun: "date") == "160 dates")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 1, noun: "entry") == "1 entry")
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

extension LibraryPathStatusBarTests {
    // "425 entrys" (Daniel's screenshot, 2026-08-23).
    @Test("y-nouns pluralize as -ies")
    func yNounsPluralizeAsIES() {
        #expect(libraryStatusText(selectionCount: 0, itemCount: 425, noun: "entry") == "425 entries")
        #expect(libraryStatusText(selectionCount: 1, itemCount: 425, noun: "entry") == "1 of 425 entries selected")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 2, noun: "day") == "2 days")
        #expect(libraryStatusText(selectionCount: 0, itemCount: 1, noun: "entry") == "1 entry")
    }
}
