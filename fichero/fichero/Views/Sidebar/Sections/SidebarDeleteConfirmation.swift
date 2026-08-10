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
