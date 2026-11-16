import SwiftUI

// MARK: - Sidebar Bottom Toolbar

/// The sidebar's bottom bar, laid out like Xcode's navigator (Daniel, 2026-11-11):
/// [+ new item] [− remove] [filter field in a capsule]. Plain icons, no bar of glass around
/// them; the filter is the one shaped control. Import and New Workflow are not here: both are
/// entries of the + menu (`AddItemMenu`), so a second icon for either was a duplicate, and the
/// workflow icon read as "run a workflow" when it created one. Every control here carries a
/// tooltip.
struct SidebarBottomToolbar: View {
    /// One shared creation menu (#4121): the + dropdown renders AddItemMenu —
    /// the SAME registry/FocusedValue-driven list the Data menu uses — so the
    /// items, gating, and tier badges can never drift between surfaces again.
    let itemRegistry: ItemTypeRegistry
    // Selection-dependent actions (#2309)
    var deleteItem: (() -> Void)?
    var hasSelection: Bool = false
    /// Sidebar filter text (#4061). Bound straight to `SidebarView.sidebarFilterText`, which
    /// drives `filteredLibraryHeaders`; rows keep stable identity so the list updates in place
    /// rather than re-rendering wholesale on filter change.
    var sidebarFilterText: Binding<String>
    /// Every open project's knowledge-row counts (#5413): the show/hide control is drawn only
    /// when at least one of them has a non-empty row.
    var knowledgeRowStores: [KnowledgeRowCountsStore] = []

    private var metrics: MiniToolbarMetrics {
        #if os(macOS)
        MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false)
        #else
        MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false)
        #endif
    }

    private var iconFont: Font {
        #if os(macOS)
        .caption
        #else
        .body
        #endif
    }

    /// One hairline above the bar on macOS (`panes.chrome.bar-hairline-rule`); the glass on touch needs none.
    nonisolated static var drawsHairlineAbove: Bool { PaneBarStyle.barsDrawHairline }

    /// Room for the magnifier and a few typed characters in the narrowest sidebar.
    nonisolated private static var filterFieldMinWidth: CGFloat { 60 }

    var body: some View {
        // No `ViewThatFits` ladder and no field inside one (#5293): the field is one view for the
        // life of the bar, so typing never remounts it. The verbs are few enough to stay inline.
        // + · 🗑 · Metadata · Filter, in one row (`sidebar.bottom-bar.plus-trash-filter`, owner 2026-11-13): no Sort,
        // the sidebar keeps its own order; the knowledge rows' switch (#5413) is in the Filter's menu.
        HStack(spacing: 4) {
            newItemMenu
            removeButton
            PaneMetadataButton { SidebarMetadataMenu() }
            PaneFilterField(text: sidebarFilterText, accessibilityID: "sidebarFilterField") {
                SidebarFilterMenu(knowledgeRowStores: knowledgeRowStores)
            }
            .frame(minWidth: Self.filterFieldMinWidth)
            .help("Filter the sidebar by name")
        }
        .padding(.horizontal, 8)
        .frame(height: PaneFilterBar<EmptyView>.height)
        .frame(maxWidth: .infinity)
    }

    /// New item menu (dropdown) — ONE source of truth (#4121); Import is its submenu.
    private var newItemMenu: some View {
        Menu {
            AddItemMenu(registry: itemRegistry, style: .contextual)
        } label: {
            Image(systemName: "plus")
                .font(iconFont)
                .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                .contentShape(Rectangle())
        }
        // A SwiftUI-drawn menu, not `.borderlessButton`: that one is an AppKit pop-up that ignores
        // the label's font, so the + came out larger and darker than the − beside it.
        .menuStyle(.button)
        .paneBarButtonStyle()
        .menuIndicator(.hidden)
        .fixedSize()
        .help("New Item")
        .accessibilityLabel("New Item")
    }

    /// Move the selection to the Trash: the trash icon, as it says what happens (`sidebar.bottom-bar.plus-trash-filter`).
    private var removeButton: some View {
        Button {
            deleteItem?()
        } label: {
            Image(systemName: "trash")
                .font(iconFont)
                .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                .contentShape(Rectangle())
        }
        .paneBarButtonStyle()
        .disabled(!hasSelection)
        .help("Move to Trash")
        .accessibilityLabel("Move to Trash")
    }
}

/// The sidebar Filter's menu (`sidebar.filter-menu.shows-toggles`): what the sidebar shows. Entities and Claims (the
/// project knowledge rows, #5413) while any project has one; the other kinds named by the spec are not built yet.
struct SidebarFilterMenu: View {
    var knowledgeRowStores: [KnowledgeRowCountsStore] = []
    @AppStorage(SidebarKnowledgeRows.shownKey) private var knowledgeShown = true

    var body: some View {
        if SidebarKnowledgeRows.toggleIsShown(knowledgeRowStores) {
            Toggle("Entities and Claims", isOn: $knowledgeShown)
        } else {
            Text("Nothing to filter yet")
        }
    }
}
