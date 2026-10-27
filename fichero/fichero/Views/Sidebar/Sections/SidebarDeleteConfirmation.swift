import SwiftUI

// Sidebar delete-confirmation grammar — split from SidebarViewExtensions
// to keep that file inside the 400-line lint budget.

func sidebarDeleteConfirmationMessage(for item: SidebarItem?) -> String {
    guard let item else {
        return "Move this item to Trash? You can put it back later."
    }
    if case .document(let doc) = item.itemType,
       doc.isLinked,
       let path = doc.path {
        return
            "Move the Fichero reference to \"\(item.name)\" to Trash? "
            + "The original file at \(path) stays on disk, and you can put this back later."
    }
    // A FOLDER names its size (Daniel live, 2026-08-15: a folder of 63
    // pages went to Trash on a right-click aimed at one entry — the count
    // is what makes a mis-aimed click visible before Confirm).
    if case .document(let doc) = item.itemType, doc.docType == .folder {
        let count = doc.childCount
        let contents = count > 0
            ? " and the \(count) item\(count == 1 ? "" : "s") inside"
            : " and everything inside"
        return "Move the folder \"\(item.name)\"\(contents) to Trash? You can put it back later."
    }
    return "Move \"\(item.name)\" to Trash? You can put it back later."
}

/// Delete-confirmation title: names the single item, or the count for a batch.
func sidebarDeleteConfirmationTitle(for items: [SidebarItem]) -> String {
    if items.count > 1 { return "Delete \(items.count) items?" }
    return items.first.map { "Delete \"\($0.name)\"?" } ?? "Delete?"
}

/// Delete-confirmation body: the per-item message for one, a batch line for many.
///
/// FOLDERS ARE NAMED (Daniel live, 2026-08-10: a context-menu delete on a PDF
/// acted on a multi-selection that also held the Inbox — engine log showed two
/// subtree deletes — and the generic "2 items" line let it through unnoticed).
/// A batch that includes a folder now says WHICH folders, and that their whole
/// contents go with them; the count alone is not informed consent.
func sidebarDeleteConfirmationMessage(for items: [SidebarItem]) -> String {
    if items.count > 1 {
        let folders = items.filter {
            if case .document(let doc) = $0.itemType { return doc.docType == .folder }
            return false
        }
        if !folders.isEmpty {
            let names = folders.map { "“\($0.name)”" }.joined(separator: ", ")
            return "Move \(items.count) items to Trash — including the folder"
                + (folders.count > 1 ? "s " : " ") + names
                + " and everything inside? You can put them back later."
        }
        return "Move \(items.count) items to Trash? You can put them back later."
    }
    return sidebarDeleteConfirmationMessage(for: items.first)
}

/// The rows in a selection that can actually be deleted (drops library headers,
/// comparisons, activity runs — anything `canBeDeleted` rejects).
func sidebarDeletableItems(_ items: [SidebarItem]) -> [SidebarItem] {
    items.filter { $0.itemType.canBeDeleted }
}

/// What a Delete gesture on the sidebar's selection acts on: the deletable items, never the row the app selected after
/// the last delete (`inheritedSelectionId`) until the person selects again
/// (`delete.after-delete-selection-is-never-a-delete-target`, #6175).
func sidebarDeleteTargets(_ items: [SidebarItem], inheritedSelectionId: String?) -> [SidebarItem] {
    let deletable = sidebarDeletableItems(items)
    guard let inherited = inheritedSelectionId else { return deletable }
    return deletable.filter { $0.id != inherited }
}

/// A multi-delete's groups (#6175): each library's documents, in selection order, are one undoable step. A document
/// whose ancestor is also going is left out: the ancestor takes it, and a second delete of a row already in the Trash
/// fails (404) part-way through the step. Anything else (saved searches, chats, workflows, automations) writes no audit
/// row to undo and goes one by one. `parentOf` answers a document id's parent id.
func sidebarDeleteBatches(
    _ items: [SidebarItem], parentOf: (String) -> String?
) -> (documents: [(libraryId: UUID, documents: [Document])], others: [SidebarItem]) {
    let going = Set(items.compactMap { item -> String? in
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    })
    var documents: [(libraryId: UUID, documents: [Document])] = []
    var others: [SidebarItem] = []
    for item in items {
        guard case .document(let doc) = item.itemType, let libraryId = item.libraryId else {
            others.append(item)
            continue
        }
        var ancestor = doc.parentId
        var seen = Set<String>()
        var underAnotherTarget = false
        while let id = ancestor, seen.insert(id).inserted {
            if going.contains(id) { underAnotherTarget = true; break }
            ancestor = parentOf(id)
        }
        if underAnotherTarget { continue }
        if let index = documents.firstIndex(where: { $0.libraryId == libraryId }) {
            documents[index].documents.append(doc)
        } else {
            documents.append((libraryId, [doc]))
        }
    }
    return (documents, others)
}

/// The inherited row after the selection is proposed again: it stays only while the proposal is exactly that row (the
/// List echoing the app's own write), and clears for any other selection, which is the person choosing (#6175).
func inheritedSelection(afterProposing proposed: [String], inherited: String?) -> String? {
    guard let inherited, proposed == [inherited] else { return nil }
    return inherited
}

/// Items the context-menu Delete acts on. Right-clicking a row inside the
/// current multi-selection targets the whole deletable selection (Finder
/// semantics); a row outside the selection targets itself alone. Falls back
/// to the clicked row when nothing in the selection is deletable so the
/// menu item's enabled state still reflects the row under the pointer.
func sidebarContextDeleteTargets(clicked: SidebarItem, selection: [SidebarItem]) -> [SidebarItem] {
    guard selection.count > 1, selection.contains(where: { $0.id == clicked.id }) else {
        return [clicked]
    }
    let deletable = sidebarDeletableItems(selection)
    return deletable.isEmpty ? [clicked] : deletable
}
