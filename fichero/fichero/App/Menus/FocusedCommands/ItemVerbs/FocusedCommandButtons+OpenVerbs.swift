import SwiftUI

// MARK: - Opening, copying and finding an item, one component each (#5652 slice 4, group 2)

// Open, Open in New Tab, Open in New Window, Duplicate, Make Alias, Show Original (or Reveal) in Finder, Quick Look
// and New Folder are ONE item each: the sidebar's row menu and the Items list's context menu render them on the
// clicked row, and File renders them on the focused pane's selection (`ItemVerbsTarget`), each disabled with its
// reason under it. Every action is the pane's own one path (its open, its audited duplicate, its alias, its Quick
// Look); none is written twice.

extension ItemVerbs {
    static let openTitle = "Open"
    static let openInNewTabTitle = "Open in New Tab"
    static let openInNewWindowTitle = "Open in New Window"
    static let duplicateTitle = "Duplicate"
    static let makeAliasTitle = "Make Alias"
    static let quickLookTitle = "Quick Look"
    static let newFolderTitle = "New Folder"

    static func openReason(_ target: ItemVerbsTarget?, action: (@MainActor () -> Void)?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.ids.count > 1 { return "Select one item to open" }
        return action == nil ? "This item does not open here" : nil
    }

    static func duplicateReason(_ target: ItemVerbsTarget?) -> String? {
        oneItemReason(target, action: target?.duplicate, verb: "duplicate")
    }

    static func makeAliasReason(_ target: ItemVerbsTarget?) -> String? {
        oneItemReason(target, action: target?.makeAlias, verb: "make an alias of")
    }

    static func quickLookReason(_ target: ItemVerbsTarget?) -> String? {
        if target?.ids.count == 1, target?.documents.first?.docType == .folder {
            return "A folder has no file to preview"
        }
        return oneItemReason(target, action: target?.quickLook, verb: "preview")
    }

    /// Why Show Original in Finder cannot act: nothing, several, or an original that is not on this Mac (a remote
    /// engine, a moved file, a folder with no path).
    static func revealReason(_ target: ItemVerbsTarget?, revealable: (Document) -> Bool) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        guard target.ids.count == 1, let document = target.documents.first else {
            return "Select one document to show in Finder"
        }
        return revealable(document) ? nil : "Its original is not on this Mac"
    }

    private static func oneItemReason(_ target: ItemVerbsTarget?, action: (@MainActor () -> Void)?,
                                      verb: String) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.ids.count > 1 { return "Select one item to \(verb)" }
        return action == nil ? "Select it in Items to \(verb) it" : nil
    }
}

extension ItemVerbsTarget {
    /// The three open verbs over a surface's own actions (the Reader, the Preview's pages, the claim cards use them
    /// too, through `OpenInMenuItems`).
    @MainActor static func opening(
        id: String, open: (() -> Void)?, openInNewTab: @escaping () -> Void,
        openInNewWindow: @escaping () -> Void
    ) -> Self {
        var target = Self(ids: [id], documents: [])
        if let open { target.open = { open() } }
        target.openInNewTab = { openInNewTab() }
        target.openInNewWindow = { openInNewWindow() }
        return target
    }
}

// MARK: - The items

struct OpenItemMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.open?() } label: { Label(ItemVerbs.openTitle, systemImage: "arrow.up.forward.app") }
            .disabled(ItemVerbs.openReason(target, action: target?.open) != nil)
    }
}

struct OpenInNewTabMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.openInNewTab?() } label: {
            Label(ItemVerbs.openInNewTabTitle, systemImage: "plus.rectangle.on.rectangle")
        }
        .disabled(ItemVerbs.openReason(target, action: target?.openInNewTab) != nil)
    }
}

struct OpenInNewWindowMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.openInNewWindow?() } label: {
            Label(ItemVerbs.openInNewWindowTitle, systemImage: "macwindow.badge.plus")
        }
        .disabled(ItemVerbs.openReason(target, action: target?.openInNewWindow) != nil)
    }
}

struct DuplicateItemMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.duplicate?() } label: {
            Label(ItemVerbs.duplicateTitle, systemImage: "plus.square.on.square")
        }
        .disabled(ItemVerbs.duplicateReason(target) != nil)
    }
}

struct MakeAliasMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.makeAlias?() } label: {
            Label(ItemVerbs.makeAliasTitle, systemImage: "arrowshape.turn.up.right")
        }
        .disabled(ItemVerbs.makeAliasReason(target) != nil)
    }
}

struct QuickLookItemMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.quickLook?() } label: { Label(ItemVerbs.quickLookTitle, systemImage: "eye") }
            .disabled(ItemVerbs.quickLookReason(target) != nil)
    }
}

/// New Folder, as ONE item: File, the sidebar's folder rows and the Items list's menu. Inside a clicked folder,
/// beside a clicked document, or in the folder the focused pane shows.
struct NewFolderMenuItem: View {
    let create: (@MainActor () -> Void)?

    var body: some View {
        Button { create?() } label: { Label(ItemVerbs.newFolderTitle, systemImage: "folder.badge.plus") }
            .disabled(create == nil)
    }
}

// MARK: - The menu bar (File)

/// File › Open, Duplicate, Make Alias, Show Original in Finder and Quick Look on the focused selection, each disabled
/// with its reason under it. No new chords: ⌘O is Open Project, ⌘D is unclaimed but a text field's, ⌘R is Rotate
/// Right, ⌘Y is unclaimed but Quick Look already has Space in the list.
struct FocusedItemOpenButtons: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        OpenItemMenuItem(target: target)
        FocusedItemOrganiseButtons.reason(ItemVerbs.openReason(target, action: target?.open))
        DuplicateItemMenuItem(target: target)
        FocusedItemOrganiseButtons.reason(ItemVerbs.duplicateReason(target))
        MakeAliasMenuItem(target: target)
        FocusedItemOrganiseButtons.reason(ItemVerbs.makeAliasReason(target))
        FocusedRevealOriginalButton(target: target)
        QuickLookItemMenuItem(target: target)
        FocusedItemOrganiseButtons.reason(ItemVerbs.quickLookReason(target))
    }
}

/// File › Show Original in Finder (or Reveal in Finder) on the one selected document: the context menus'
/// `RevealOriginalMenuItem`, or the reason it is not there.
struct FocusedRevealOriginalButton: View {
    let target: ItemVerbsTarget?

    var body: some View {
        let reason = ItemVerbs.revealReason(target, revealable: RevealOriginalMenuItem.isRevealable)
        if reason == nil, let document = target?.documents.first {
            RevealOriginalMenuItem(document: document)
        } else {
            Button {} label: { Label(RevealOriginalPolicy.label(isLinked: true), systemImage: "folder") }
                .disabled(true)
            FocusedItemOrganiseButtons.reason(reason)
        }
    }
}
