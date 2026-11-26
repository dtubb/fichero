import Foundation

/// The one folder "Run the Recipe on This Folder…" acts on (`source.recipe.folder-scoped-start`, #5540).
/// Pure, so every surface agrees.
enum RecipeFolderScope {
    /// Why the item cannot act: no single folder.
    static let noFolderReason = "Select one folder to run the recipe on"

    /// A context menu: the clicked folder, unless it is one of several selected (Finder semantics: the
    /// verb would act on the selection, and the recipe runs on one folder); a page is nothing.
    static func forClick(on id: String, isFolder: Bool, selection: Set<String>) -> String? {
        if selection.contains(id) && selection.count > 1 { return nil }
        return isFolder ? id : nil
    }

    /// The menu bar: the one selected folder; or, with nothing selected, the folder the window shows.
    /// Several selected, or one page, is nothing.
    static func forSelection(
        _ selection: Set<String>, shownFolderId: String?, isFolder: (String) -> Bool
    ) -> String? {
        if selection.count > 1 { return nil }
        if let only = selection.first { return isFolder(only) ? only : nil }
        if let shownFolderId, isFolder(shownFolderId) { return shownFolderId }
        return nil
    }

    /// What a context menu's Run Step acts on (#7087): the whole selection when the clicked row is in it (Finder
    /// semantics), else the clicked row alone.
    static func runStepTargets(clicked: String, selection: Set<String>) -> Set<String> {
        let documents = Set(selection.map { LibraryOutlineNode.parse(nodeId: $0).documentId })
        return documents.contains(clicked) ? documents : [clicked]
    }

    /// The documents a surface knows of, each once: the sidebar's loaded listings and the pane's own rows. A page
    /// the sidebar has not loaded (its folder is closed there) is still a page the Items list shows.
    static func knownDocuments(_ lists: [Document]...) -> [Document] {
        var seen: Set<String> = []
        return lists.flatMap { $0 }.filter { seen.insert($0.id).inserted }
    }

    /// The pages "Run a Step Again" runs on for a selection of folders and items (#6744): a page is itself, a
    /// folder is every page under it at any depth, each once. The engine's `documents` takes pages, never folders.
    static func redoPages(selection: Set<String>, in documents: [Document]) -> [String] {
        let children = WorkflowRunTargetResolver.childrenIndex(of: documents)
        var pages: [String] = []
        var seen: Set<String> = []
        // The Items list's rows are outline node ids ("<document id>" plus a child-group suffix); a row's document is
        // what runs (#7087).
        let chosen = Set(selection.map { LibraryOutlineNode.parse(nodeId: $0).documentId })
        for document in documents where chosen.contains(document.id) {
            let ids = document.docType == .folder
                ? WorkflowRunTargetResolver.descendantFileIDs(of: document.id, childrenByParent: children)
                : [document.id]
            for id in ids where seen.insert(id).inserted { pages.append(id) }
        }
        return pages
    }
}
