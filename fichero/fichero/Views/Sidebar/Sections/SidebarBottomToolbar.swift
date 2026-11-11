import SwiftUI

// MARK: - Sidebar Bottom Toolbar

/// The sidebar's bottom bar, laid out like Xcode's navigator (Daniel, 2026-11-11):
/// [+ new item] [− remove] [filter field in a capsule] [new workflow]. Plain icons, no bar of
/// glass around them; the filter is the one shaped control. Import is not here: it is the
/// Import submenu of the + menu (`AddItemMenu`), so a second icon for it was a duplicate.
struct SidebarBottomToolbar: View {
    // Feature manager to hide buttons
    let featureManager = FeatureManager.shared

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

    /// Room for the magnifier and a few typed characters in the narrowest sidebar.
    private static var filterFieldMinWidth: CGFloat { 60 }

    var body: some View {
        // No `ViewThatFits` ladder and no field inside one (#5293): the field is one view for the
        // life of the bar, so typing never remounts it. The verbs are few enough to stay inline.
        HStack(spacing: 4) {
            newItemMenu
            removeButton
            // Show/hide every project's non-empty knowledge rows (#5413); absent while no
            // project has one, since there would be nothing for it to do.
            if SidebarKnowledgeRows.toggleIsShown(knowledgeRowStores) {
                SidebarKnowledgeRowsToggle(font: iconFont, side: metrics.touchTargetSide)
            }
            filterField
                .frame(minWidth: Self.filterFieldMinWidth)
            if featureManager.isWorkflowsEnabled {
                newWorkflowButton
            }
        }
        .padding(.horizontal, 8)
        .frame(height: PaneFilterBar<EmptyView>.height)
        .frame(maxWidth: .infinity)
    }

    /// The sidebar filter field in its capsule (#4061). The clear button appears only when
    /// there's text to clear — a small in-place update, no list re-render (rows keep stable
    /// identity via `filteredLibraryHeaders`).
    private var filterField: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
            TextField("Filter", text: sidebarFilterText)
                .textFieldStyle(.plain)
                .accessibilityIdentifier("sidebarFilterField")
            if !sidebarFilterText.wrappedValue.isEmpty {
                Button {
                    sidebarFilterText.wrappedValue = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Clear filter")
                .accessibilityLabel("Clear filter")
            }
        }
        .padding(.horizontal, 8)
        .frame(minHeight: metrics.touchTargetSide)
        .background(.fill.tertiary, in: Capsule())
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
        .buttonStyle(.borderless)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("New Item")
        .accessibilityLabel("New Item")
    }

    /// Remove / delete selected item
    private var removeButton: some View {
        Button {
            deleteItem?()
        } label: {
            Image(systemName: "minus")
                .font(iconFont)
                .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .disabled(!hasSelection)
        .help("Remove selected item")
        .accessibilityLabel("Remove selected item")
    }

    /// New workflow (only shown when the workflows feature is enabled).
    ///
    /// Export used to sit beside this as a permanently `.disabled(true)` button whose own `.help`
    /// read "Export (not yet wired)" (#4100). A control that can never do anything is placeholder
    /// chrome; File ▸ Export already exports, and #2309 tracks a SIDEBAR-scoped export handler.
    private var newWorkflowButton: some View {
        Button {
            itemRegistry.createWorkflow?()
        } label: {
            Image(systemName: "bolt")
                .font(iconFont)
                .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .disabled(!hasSelection)
        .help("New Workflow")
        .accessibilityLabel("New Workflow")
    }
}
