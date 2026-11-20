@testable import Fichero
import Testing

/// #6729: the five search scopes, which of them a window offers, the placeholder each gives and the id the engine
/// call carries.
struct SearchScopeTests {
    private static let page = TransientSearchFolder(id: "p1", name: "001")
    private static let document = TransientSearchFolder(id: "d1", name: "Diary")
    private static let folder = TransientSearchFolder(id: "f1", name: "1885")

    private static let all = SearchScopeTargets(page: page, document: document, folder: folder)

    @Test("with a page, document and folder every scope is offered, in menu order")
    func allFiveOffered() {
        #expect(Self.all.offered == [.page, .document, .folder, .project, .everywhere])
        #expect(Self.all.offered.map(\.title) == ["This Page", "This Document", "This Folder", "This Project", "Everywhere"])
    }

    @Test("with nothing browsed only the project and everywhere are offered")
    func onlyProjectAndEverywhere() {
        #expect(SearchScopeTargets().offered == [.project, .everywhere])
    }

    @Test("the placeholder names the scope")
    func placeholderNamesScope() {
        #expect(SearchScope.allCases.map(\.placeholder) == [
            "Search this page", "Search this document", "Search this folder", "Search this project", "Search everywhere"
        ])
    }

    @Test("the engine call carries the chosen node's id, and none for project and everywhere")
    func engineFolderIds() {
        #expect(Self.all.engineFolderId(for: .page) == "p1")
        #expect(Self.all.engineFolderId(for: .document) == "d1")
        #expect(Self.all.engineFolderId(for: .folder) == "f1")
        #expect(Self.all.engineFolderId(for: .project) == nil)
        #expect(Self.all.engineFolderId(for: .everywhere) == nil)
    }

    @Test("a scope whose node is gone falls back to the project and sends no id")
    func missingNodeFallsBack() {
        let none = SearchScopeTargets()
        #expect(none.effective(.page) == .project)
        #expect(none.effective(.everywhere) == .everywhere)
        #expect(none.engineFolderId(for: .page) == nil)
    }

    @Test("the default scope is the folder only when asked for and there is one")
    func defaultScope() {
        #expect(Self.all.defaultScope(folderByDefault: true) == .folder)
        #expect(Self.all.defaultScope(folderByDefault: false) == .project)
        #expect(SearchScopeTargets().defaultScope(folderByDefault: true) == .project)
    }
}
