import SwiftUI

/// What a sidebar row draws from its parent, reduced to what can change THIS row (#4228).
///
/// Every row used to re-run its body whenever `SidebarView` did, which is on every click: the
/// whole selection and expansion sets are its inputs, and they change for one row at a time. A
/// folder click re-ran every visible row, up to 140 in one turn, on every frame of a window resize
/// too. Two keys equal means the row would draw the same thing, so `SidebarRowSkip` lets SwiftUI
/// keep the row it has.
///
/// An expanded row builds its child rows in its own body, so the key covers its SUBTREE: the item
/// itself, deep (a rename, a child added or moved), and the expansion of every row in it. The
/// selection is reduced the same way, except when anything in the subtree is selected: a selected
/// row's context menu acts on the whole selection (#6528), so then the key carries the whole
/// selection and the row is rebuilt whenever it changes. A row with nothing selected in its
/// subtree acts on itself alone and does not care what else is selected.
///
/// `@unchecked Sendable`: `SidebarItem` is not marked Sendable, but this is an immutable value of
/// value types (its payloads are boxed `let` enums), read only by the `nonisolated ==` SwiftUI
/// calls to compare.
struct SidebarRowInputs: Equatable, @unchecked Sendable {
    let item: SidebarItem
    let mergeAbove: Bool
    let mergeBelow: Bool
    /// The expanded rows of this subtree.
    let expanded: Set<String>
    /// The whole selection when something in this subtree is selected; empty otherwise.
    let selection: Set<SidebarDestination>
    /// The single selected id when something in this subtree is selected; nil otherwise.
    let selectedItemId: String?

    init(
        item: SidebarItem,
        selection: Set<SidebarDestination>,
        selectedItemId: String?,
        expanded: Set<String>,
        mergeAbove: Bool,
        mergeBelow: Bool
    ) {
        self.item = item
        self.mergeAbove = mergeAbove
        self.mergeBelow = mergeBelow
        let ids = Self.subtreeIds(of: item)
        self.expanded = expanded.intersection(ids)
        let touchesSelection = (selectedItemId.map(ids.contains) ?? false)
            || selection.contains { ids.contains($0.serializedID) }
        self.selection = touchesSelection ? selection : []
        self.selectedItemId = touchesSelection ? selectedItemId : nil
    }

    /// The ids of `item` and every row built beneath it.
    static func subtreeIds(of item: SidebarItem) -> Set<String> {
        var ids: Set<String> = [item.id]
        var pending = item.children ?? []
        while let next = pending.popLast() {
            ids.insert(next.id)
            pending.append(contentsOf: next.children ?? [])
        }
        return ids
    }
}

/// Holds a sidebar row and lets SwiftUI skip it when its `SidebarRowInputs` did not change.
/// Observed state the row reads itself (rename, delete, drop targets, running workflows) still
/// reaches it directly; only the parent's rebuild is skipped.
struct SidebarRowSkip<Row: View>: View, Equatable {
    let inputs: SidebarRowInputs
    @ViewBuilder let row: Row

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.inputs == rhs.inputs
    }

    var body: some View { row }
}

extension SidebarView {
    /// A top-level sidebar row, skipped when nothing it draws changed (`SidebarRowInputs`).
    func skippableRow(for item: SidebarItem, mergeAbove: Bool, mergeBelow: Bool) -> some View {
        SidebarRowSkip(inputs: SidebarRowInputs(
            item: item,
            selection: selectionState.selectedDestinations,
            selectedItemId: selectionState.selectedItemId,
            expanded: sidebarState.expandedItems,
            mergeAbove: mergeAbove,
            mergeBelow: mergeBelow
        )) {
            SidebarItemRow(
                item: item,
                // O(1) id lookup against the cached index — never hand rows the
                // whole forest to copy (#4545).
                lookupItem: { cachedItem(id: $0) },
                expandedItems: Binding(
                    get: { sidebarState.expandedItems },
                    set: { sidebarState.expandedItems = $0 }
                ),
                selectedItemId: Binding(
                    get: { selectionState.selectedItemId },
                    set: { selectionState.selectedItemId = $0 }
                ),
                selectedDestinations: selectionState.selectedDestinations,
                renameState: renameState,
                deleteState: deleteState,
                sidebarState: sidebarState,
                libraryManager: libraryManager,
                onOpenChatWithCurrentScope: onOpenChatWithCurrentScope,
                onSelectionProposal: { applySidebarSelectionProposal($0) },
                mergeSelectionAbove: mergeAbove,
                mergeSelectionBelow: mergeBelow,
                // A schedule, trigger or batch changed by its own verb: read them again (#5712).
                onAutomationChanged: {
                    Task { @MainActor in
                        await loadAutomationData()
                        await loadActivityData()
                    }
                }
            )
        }
        .equatable()
    }
}

extension SidebarItemRow {
    /// A child row built inside this row's disclosure group, skipped the same way.
    func skippableChildRow(_ child: SidebarItem, mergeAbove: Bool, mergeBelow: Bool) -> some View {
        SidebarRowSkip(inputs: SidebarRowInputs(
            item: child, selection: selectedDestinations, selectedItemId: selectedItemId,
            expanded: expandedItems, mergeAbove: mergeAbove, mergeBelow: mergeBelow
        )) {
            SidebarItemRow(
                item: child,
                lookupItem: lookupItem,
                expandedItems: $expandedItems,
                selectedItemId: $selectedItemId,
                selectedDestinations: selectedDestinations,
                renameState: renameState,
                deleteState: deleteState,
                sidebarState: sidebarState,
                libraryManager: libraryManager,
                onOpenChatWithCurrentScope: onOpenChatWithCurrentScope,
                onSelectionProposal: onSelectionProposal,
                mergeSelectionAbove: mergeAbove,
                mergeSelectionBelow: mergeBelow
            )
        }
        .equatable()
    }
}
