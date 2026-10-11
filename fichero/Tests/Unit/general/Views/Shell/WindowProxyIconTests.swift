@testable import Fichero
import Foundation
import Testing

/// The window title's proxy icon (Daniel, 2026-10-11): the item the title names, with its own icon, dragging as that
/// item does from a row.
@MainActor
struct WindowProxyIconTests {
    @Test("a selected folder or page gives the title its icon and its drag; nothing selected gives none")
    func proxyCarriesTheItem() throws {
        let project = UUID()
        let folder = Document(id: "caciques", docType: .folder, name: "CACIQUES")
        let proxy = try #require(WindowProxyIcon.proxy(for: folder, libraryId: project))
        #expect(proxy.symbol == folder.displaySymbol())
        #expect(proxy.drag == LibraryItemDrag.forDocument(folder, libraryId: project), "the same drag a row makes")

        let page = Document(id: "p1", parentId: "caciques", docType: .page, name: "f. 1", sequence: 1)
        #expect(WindowProxyIcon.proxy(for: page, libraryId: project)?.drag.kind == .page)

        #expect(WindowProxyIcon.proxy(for: nil, libraryId: project) == nil)
    }
}
