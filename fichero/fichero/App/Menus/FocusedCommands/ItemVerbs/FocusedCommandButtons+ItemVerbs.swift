import FicheroAPIClient
import SwiftUI

// MARK: - The item verbs, one component each (#5652 slice 4, `menus.context-matches-bar`)

// Rename, Delete, Exclude from / Include in Processing and Search, Bookmark…, Add to Workspace… and Export a
// Copy… are ONE item each. The sidebar's row menu and the Items list's context menu render them on the clicked row
// (Finder semantics: the selection when the click is part of it), and Edit (File for Export a Copy…) renders them on
// the focused pane's selection, through `ItemVerbsTarget`. What each does is one function here or the pane's own
// one path (its rename field, its delete confirmation, its picker sheet); no surface has a second.

/// What the item verbs act on, and how each acts there. A verb that cannot act on these items has no action (nil),
/// and says why (`ItemVerbs`). Equatable on what the menu shows, never on the closures, so a pane's republish of the
/// same selection short-circuits.
struct ItemVerbsTarget: Equatable {
    /// The items the verbs act on (sidebar items of any kind, or Items rows).
    var ids: [String]
    /// The documents among them: what Exclude, Bookmark, Add to Workspace and Export a Copy read.
    var documents: [Document]
    var rename: (@MainActor () -> Void)?
    /// The one document's name as the person reads it, for a menu title that names its target.
    var singleDocumentName: String? {
        documents.count == 1 ? documents.first.map { DocumentTitle.displayName(for: $0) } : nil
    }
    /// How many of the items Delete would remove.
    var deletableCount = 0
    var delete: (@MainActor () -> Void)?
    var setExcluded: (@MainActor (ItemVerbs.Exclusion, Bool) -> Void)?
    var bookmark: (@MainActor () -> Void)?
    var addToWorkspace: (@MainActor () -> Void)?
    var export: (@MainActor () -> Void)?
    // Group 2 (#5652): opening, copying and finding the item.
    var open: (@MainActor () -> Void)?
    var openInNewTab: (@MainActor () -> Void)?
    var openInNewWindow: (@MainActor () -> Void)?
    var duplicate: (@MainActor () -> Void)?
    var makeAlias: (@MainActor () -> Void)?
    var quickLook: (@MainActor () -> Void)?
    /// New Folder in the pane's own place (the folder it shows), whatever is selected.
    var newFolder: (@MainActor () -> Void)?
    // Group 4 (#5652): proposed documents the selection names, and one source's direction.
    var proposals: ProposalVerbs?
    var direction: DirectionVerbs?
    // Group 6 (#5652): a workflow run and a chat on the selection.
    var runWorkflow: WorkflowRunVerbs?
    var addToChat: (@MainActor () -> Void)?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.ids == rhs.ids
            && lhs.documents.map(\.excludeFromProcessing) == rhs.documents.map(\.excludeFromProcessing)
            && lhs.documents.map(\.excludeFromSearch) == rhs.documents.map(\.excludeFromSearch)
            && lhs.deletableCount == rhs.deletableCount
            && lhs.offered == rhs.offered
            && lhs.proposals == rhs.proposals && lhs.direction == rhs.direction
            && lhs.runWorkflow == rhs.runWorkflow && (lhs.addToChat != nil) == (rhs.addToChat != nil)
    }

    /// Which verbs have an action, in order: what the menu shows enabled.
    var offered: [Bool] {
        [rename != nil, delete != nil, setExcluded != nil, bookmark != nil, addToWorkspace != nil, export != nil,
         open != nil, openInNewTab != nil, openInNewWindow != nil, duplicate != nil, makeAlias != nil, quickLook != nil,
         newFolder != nil]
    }
}

extension FocusedValues {
    /// The focused pane's selection, as the item verbs act on it (the Items list publishes it).
    @Entry var itemVerbs: ItemVerbsTarget?
}

/// The item verbs' words and reasons, and their shared operations. Pure where it can be, so every surface agrees and
/// a test can check it.
enum ItemVerbs {
    enum Exclusion: Equatable {
        case processing, search, everywhere

        var scopes: [Components.Schemas.DocumentExclusionScope] {
            switch self {
            case .processing: [.processing]
            case .search: [.search]
            case .everywhere: [.processing, .search]
            }
        }
    }

    static let renameTitle = "Rename"
    static let bookmarkTitle = "Bookmark…"
    static let addToWorkspaceTitle = "Add to Workspace…"
    static let exportTitle = "Export a Copy…"

    /// "Delete “Name”" for one named item, so the menu shows what ⌘⌫ will take before it is pressed
    /// (`delete.what-is-shown-selected-is-what-is-deleted`, #6175); "Delete 3 Items" for several.
    static func deleteTitle(_ count: Int, name: String? = nil) -> String {
        if count > 1 { return "Delete \(count) Items" }
        if let name, !name.isEmpty { return "Delete “\(name)”" }
        return "Delete"
    }

    /// Whether the documents are all already excluded in that sense: the verb then includes them again.
    static func isExcluded(_ documents: [Document], _ exclusion: Exclusion) -> Bool {
        guard !documents.isEmpty else { return false }
        switch exclusion {
        case .processing: return documents.allSatisfy(\.excludeFromProcessing)
        case .search: return documents.allSatisfy(\.excludeFromSearch)
        case .everywhere: return documents.allSatisfy { $0.excludeFromProcessing && $0.excludeFromSearch }
        }
    }

    /// What a press sets: include them again when all already are excluded, else exclude them.
    static func pressExcludes(_ documents: [Document], _ exclusion: Exclusion) -> Bool {
        !isExcluded(documents, exclusion)
    }

    static func exclusionTitle(_ documents: [Document], _ exclusion: Exclusion) -> String {
        exclusionTitle(exclusion, including: isExcluded(documents, exclusion))
    }

    /// The words for one way: include (the documents are excluded) or exclude. A surface that knows the way without
    /// the documents (a dataset row's fixed verbs, the Inspector's one document) asks for it directly.
    static func exclusionTitle(_ exclusion: Exclusion, including include: Bool) -> String {
        switch exclusion {
        case .processing: return include ? "Include in Processing" : "Exclude from Processing"
        case .search: return include ? "Include in Search" : "Exclude from Search"
        case .everywhere: return include ? "Include Everywhere" : "Exclude Everywhere"
        }
    }

    static func exclusionImage(_ documents: [Document], _ exclusion: Exclusion) -> String {
        exclusionImage(exclusion, including: isExcluded(documents, exclusion))
    }

    static func exclusionImage(_ exclusion: Exclusion, including include: Bool) -> String {
        switch exclusion {
        case .processing: return include ? "eye" : "eye.slash"
        case .search: return include ? "magnifyingglass" : "text.magnifyingglass"
        case .everywhere: return include ? "eye.circle" : "eye.slash.circle"
        }
    }

    // MARK: Why a verb cannot act (nil: it can)

    static let nothingSelected = "Select an item first"

    static func renameReason(_ target: ItemVerbsTarget?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.ids.count > 1 { return "Select one item to rename" }
        return target.rename == nil ? "This item cannot be renamed" : nil
    }

    static func deleteReason(_ target: ItemVerbsTarget?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        return target.delete == nil || target.deletableCount == 0 ? "Nothing selected can be deleted" : nil
    }

    static func excludeReason(_ target: ItemVerbsTarget?) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.documents.isEmpty { return "Only documents and folders can be excluded" }
        return target.setExcluded == nil ? "Select documents in Items to exclude them" : nil
    }

    static func bookmarkReason(_ target: ItemVerbsTarget?) -> String? {
        oneDocumentReason(target, action: target?.bookmark, verb: "bookmark")
    }

    static func addToWorkspaceReason(_ target: ItemVerbsTarget?) -> String? {
        oneDocumentReason(target, action: target?.addToWorkspace, verb: "add to a workspace")
    }

    static func exportReason(_ target: ItemVerbsTarget?) -> String? {
        if target?.documents.count == 1, target?.ids.count == 1, target?.documents.first?.docType == .folder {
            return "A folder has no file to export"
        }
        return oneDocumentReason(target, action: target?.export, verb: "export")
    }

    private static func oneDocumentReason(_ target: ItemVerbsTarget?, action: (@MainActor () -> Void)?,
                                          verb: String) -> String? {
        guard let target, !target.ids.isEmpty else { return nothingSelected }
        if target.documents.count != 1 || target.ids.count != 1 { return "Select one document to \(verb)" }
        return action == nil ? "Select the document in Items to \(verb) it" : nil
    }

    // MARK: Shared operations

    /// Exclude or include documents, in one or both senses: the audited batch exclusion, each changed document set
    /// in place in the project's store. Returns the documents as the engine now has them.
    @MainActor @discardableResult
    static func setExcluded(_ ids: [String], excluded: Bool, _ exclusion: Exclusion,
                            using service: DocumentService,
                            refreshing store: DocumentStore?) async throws -> [Document] {
        var refreshed: [Document] = []
        for scope in exclusion.scopes {
            refreshed = try await service.batchExclude(documentIds: ids, excluded: excluded, scope: scope)
            for updated in refreshed { store?.refreshLocalContent(updated) }
        }
        return refreshed
    }
}

// MARK: - The items

struct RenameItemMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.rename?() } label: { Label(ItemVerbs.renameTitle, systemImage: "pencil") }
            .disabled(ItemVerbs.renameReason(target) != nil)
    }
}

struct DeleteItemsMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button(role: .destructive) { target?.delete?() } label: {
            Label(ItemVerbs.deleteTitle(target?.deletableCount ?? 0, name: target?.singleDocumentName), systemImage: "trash")
        }
        .disabled(ItemVerbs.deleteReason(target) != nil)
    }
}

struct ExcludeItemsMenuItem: View {
    let target: ItemVerbsTarget?
    let exclusion: ItemVerbs.Exclusion

    var body: some View {
        let documents = target?.documents ?? []
        Button {
            target?.setExcluded?(exclusion, ItemVerbs.pressExcludes(documents, exclusion))
        } label: {
            Label(ItemVerbs.exclusionTitle(documents, exclusion), systemImage: ItemVerbs.exclusionImage(documents, exclusion))
        }
        .disabled(ItemVerbs.excludeReason(target) != nil)
    }
}

struct BookmarkItemMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.bookmark?() } label: { Label(ItemVerbs.bookmarkTitle, systemImage: "bookmark") }
            .disabled(ItemVerbs.bookmarkReason(target) != nil)
    }
}

struct AddToWorkspaceMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.addToWorkspace?() } label: {
            Label(ItemVerbs.addToWorkspaceTitle, systemImage: "square.grid.2x2")
        }
        .disabled(ItemVerbs.addToWorkspaceReason(target) != nil)
    }
}

struct ExportCopyMenuItem: View {
    let target: ItemVerbsTarget?

    var body: some View {
        Button { target?.export?() } label: { Label(ItemVerbs.exportTitle, systemImage: "square.and.arrow.up") }
            .disabled(ItemVerbs.exportReason(target) != nil)
    }
}

// MARK: - The menu bar

/// What Edit's item verbs act on: the focused Items list's selection, else the focused sidebar's. In the sidebar,
/// Rename and Delete go through its own actions; Exclude, Bookmark, Add to Workspace and Export a Copy are the Items
/// list's (the sidebar's pickers are per row, since its rows span projects), and say so.
@MainActor
enum FocusedItemVerbs {
    static func target(items: ItemVerbsTarget?, actions: SidebarActions?, info: SidebarSelectionInfo?) -> ItemVerbsTarget? {
        if let items { return items }
        guard let actions, let info, let item = info.selectedItem else { return nil }
        var documents: [Document] = []
        if case .document(let document) = item.itemType { documents = [document] }
        var target = ItemVerbsTarget(ids: [item.id], documents: documents)
        if info.canRename { target.rename = { actions.renameItem() } }
        target.deletableCount = info.deletableCount
        if info.deletableCount > 0 { target.delete = { actions.deleteItem() } }
        target.openInNewTab = { actions.openSelectionInNewTab() }
        target.openInNewWindow = { actions.openSelectionInNewWindow() }
        return target
    }
}

/// Edit › Rename on the focused selection. Return, as in Finder's sidebar, only while the sidebar has focus: in the
/// Items list Return opens the selected row (`LibraryView`'s own key handler), and a menu chord would take it first.
struct FocusedRenameButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        RenameItemMenuItem(target: target)
            .keyboardShortcut(items == nil ? KeyboardShortcut(.return, modifiers: []) : nil)
        if let reason = ItemVerbs.renameReason(target) {
            Text(reason)
        }
    }
}

/// Edit › Delete on the focused selection: the same batch path as the Delete key, so the title counts what it
/// would remove. Its chord (⌘⌫) is set where Edit places it.
struct FocusedDeleteButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        DeleteItemsMenuItem(target: target)
        // With nothing selected, Rename's reason above says it once.
        if let reason = ItemVerbs.deleteReason(target), reason != ItemVerbs.nothingSelected {
            Text(reason)
        }
    }
}

/// Edit's Exclude / Include (Processing, Search, Everywhere), Bookmark… and Add to Workspace… on the focused
/// selection, each disabled with its reason under it.
struct FocusedItemOrganiseButtons: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        ExcludeItemsMenuItem(target: target, exclusion: .processing)
        ExcludeItemsMenuItem(target: target, exclusion: .search)
        ExcludeItemsMenuItem(target: target, exclusion: .everywhere)
        Self.reason(ItemVerbs.excludeReason(target))
        BookmarkItemMenuItem(target: target)
        Self.reason(ItemVerbs.bookmarkReason(target))
        AddToWorkspaceMenuItem(target: target)
        Self.reason(ItemVerbs.addToWorkspaceReason(target))
    }

    /// A reason under its item; "Select an item first" is said once, under Rename.
    @ViewBuilder
    static func reason(_ text: String?) -> some View {
        if let text, text != ItemVerbs.nothingSelected {
            Text(text)
        }
    }
}

/// File › Export a Copy… on the focused selection.
struct FocusedExportCopyButton: View {
    @FocusedValue(\.itemVerbs) private var items
    @FocusedValue(\.sidebarActions) private var sidebarActions
    @FocusedValue(\.sidebarSelectionInfo) private var selectionInfo

    var body: some View {
        let target = FocusedItemVerbs.target(items: items, actions: sidebarActions, info: selectionInfo)
        ExportCopyMenuItem(target: target)
        if let reason = ItemVerbs.exportReason(target) {
            Text(reason)
        }
    }
}
