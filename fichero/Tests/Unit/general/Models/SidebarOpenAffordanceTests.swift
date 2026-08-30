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
                id: "doc:\(id)", name: id, icon: "doc", category: .folder,
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

    // MARK: - Keyboard focus exit (right-arrow on leaf → content pane)

    @Test("right-arrow exits focus only on a non-expandable leaf")
    func focusExitOnlyOnLeafRows() {
        let leaf = documentItem("doc-leaf", libraryId: libraryId)
        #expect(sidebarShouldExitFocusRight(selectedItem: leaf))
        // Expandable rows keep right-arrow = native expand.
        let folder = SidebarItem(
            id: "doc:f", name: "F", icon: "folder", category: .folder,
            itemType: .document(Document(id: "f", docType: .folder, name: "F")),
            children: [leaf], libraryId: libraryId, folderPath: "/",
            sortOrder: 0, isFolder: true
        )
        #expect(!sidebarShouldExitFocusRight(selectedItem: folder))
        // No selection: leave the event to the List.
        #expect(!sidebarShouldExitFocusRight(selectedItem: nil))
    }

    // MARK: - Menu-command discoverability (source-locked: @FocusedValue
    // buttons can't be instantiated in a unit test without a focus system)

    @Test("File menu surfaces Open in New Tab/Window for the sidebar selection")
    func fileMenuContainsSelectionOpenCommands() throws {
        let source = try appSource("App/Menus/FileMenuCommands.swift")
        #expect(source.contains("FocusedOpenInNewTabButton()"))
        #expect(source.contains("FocusedOpenInNewWindowButton()"))
    }

    @Test("selection-open commands use the ⌘⌥O family and disable without a selection")
    func selectionOpenCommandsShortcutsAndDisabling() throws {
        let source = try appSource("App/Menus/FocusedCommandButtons+SidebarActions.swift")
        // ⌘O is Open Library; selection-opens must stay on the ⌘⌥O family.
        #expect(source.contains(#".keyboardShortcut("o", modifiers: [.command, .option])"#))
        #expect(source.contains(#".keyboardShortcut("o", modifiers: [.command, .option, .shift])"#))
        // Both buttons gate on an actual sidebar selection, not just sidebar focus.
        let disabledGates = source.components(
            separatedBy: ".disabled(selectionInfo?.selectedItem == nil)"
        ).count - 1
        #expect(disabledGates == 2)
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
