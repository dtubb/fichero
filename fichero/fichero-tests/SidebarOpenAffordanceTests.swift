import AppKit
@testable import Fichero
import Foundation
import Testing

/// Locks the sidebar double-click / trailing-affordance open contract:
/// where the open routes (`sidebarAuxiliaryOpenTarget`) and whether it
/// joins a tab group (`sidebarOpenPrefersTab`). The actual window/tab
/// creation reuses the shipped `WindowOpener` path (#1685) untouched.
struct SidebarOpenAffordanceTests {

    private let libraryId = UUID()
    private let fallbackId = UUID()

    private func documentItem(_ id: String, libraryId: UUID?) -> SidebarItem {
        let doc = Document(id: id, docType: .file, fileType: .pdf, name: id)
        guard let libraryId else {
            // `fromDocument` requires a library; a nil-library document row can
            // still exist transiently, so build one directly for the fallback case.
            return SidebarItem(
                id: "doc:\(id)", name: id, icon: "doc", category: .documents,
                itemType: .document(doc), children: nil, libraryId: nil,
                folderPath: "/", sortOrder: 0, isFolder: false
            )
        }
        return SidebarItem.fromDocument(doc, libraryId: libraryId)
    }

    @Test("document row opens its library focused on the document")
    func documentRowFocusesDocument() {
        let target = sidebarAuxiliaryOpenTarget(
            item: documentItem("doc-1", libraryId: libraryId),
            fallbackLibraryId: fallbackId
        )
        #expect(target?.libraryId == libraryId)
        #expect(target?.documentId == "doc-1")
    }

    @Test("non-document row opens its library without a focused document")
    func nonDocumentRowOpensLibraryOnly() {
        let header = SidebarItem(
            id: "lib:x", name: "Lib", icon: "book", category: .library, itemType: .libraryHeader,
            children: nil, libraryId: libraryId, folderPath: "/", sortOrder: 0, isFolder: false
        )
        let target = sidebarAuxiliaryOpenTarget(item: header, fallbackLibraryId: fallbackId)
        #expect(target?.libraryId == libraryId)
        #expect(target?.documentId == nil)
    }

    @Test("row without a library falls back to the current library")
    func missingLibraryUsesFallback() {
        let target = sidebarAuxiliaryOpenTarget(
            item: documentItem("doc-2", libraryId: nil),
            fallbackLibraryId: fallbackId
        )
        #expect(target?.libraryId == fallbackId)
        #expect(target?.documentId == "doc-2")
    }

    @Test("no row and no fallback opens nothing")
    func nothingToOpenReturnsNil() {
        #expect(sidebarAuxiliaryOpenTarget(item: nil, fallbackLibraryId: fallbackId) == nil)
        #expect(
            sidebarAuxiliaryOpenTarget(
                item: documentItem("doc-3", libraryId: nil),
                fallbackLibraryId: nil
            ) == nil
        )
    }

    @Test("trailing affordance shows only on hover, outside rename, with a library")
    func trailingAffordanceVisibilityRules() {
        #expect(sidebarRowShowsOpenAffordance(isHovered: true, isRenaming: false, hasLibrary: true))
        #expect(!sidebarRowShowsOpenAffordance(isHovered: false, isRenaming: false, hasLibrary: true))
        #expect(!sidebarRowShowsOpenAffordance(isHovered: true, isRenaming: true, hasLibrary: true))
        #expect(!sidebarRowShowsOpenAffordance(isHovered: true, isRenaming: false, hasLibrary: false))
    }

    @Test("only the system 'always prefer tabs' setting opens a tab")
    func tabPreferenceHonorsSystemSetting() {
        #expect(sidebarOpenPrefersTab(.always))
        #expect(!sidebarOpenPrefersTab(.manual))
        // Full-screen preference stays a window: the helper can't cheaply
        // know the key window's full-screen state, so a window is the safe
        // default (documented on the helper).
        #expect(!sidebarOpenPrefersTab(.inFullScreen))
    }
}
