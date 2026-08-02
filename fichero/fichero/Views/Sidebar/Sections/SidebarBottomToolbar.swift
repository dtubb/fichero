import SwiftUI

// MARK: - Sidebar Bottom Toolbar

/// Compact bottom toolbar for sidebar with common actions.
///
/// Modeled after macOS Preview/Finder bottom toolbars with small, icon-only buttons.
/// Layout: [+new menu] [−delete] [export] [import menu] [workflow] (#2309)
struct SidebarBottomToolbar: View {
    // Feature manager to hide buttons
    let featureManager = FeatureManager.shared

    /// One shared creation menu (#4121): the + dropdown renders AddItemMenu —
    /// the SAME registry/FocusedValue-driven list the Data menu uses — so the
    /// items, gating, and tier badges can never drift between surfaces again.
    let itemRegistry: ItemTypeRegistry
    let importFiles: (IngestMode) -> Void
    // Optional automation creation callbacks
    // Selection-dependent actions (#2309)
    var deleteItem: (() -> Void)?
    var hasSelection: Bool = false
    /// Sidebar filter text (#4061). The filter field lives inside this bottom
    /// toolbar — one unified bottom toolbar owns the filter + the
    /// sidebar-scoped actions — so there is no standalone filter chrome above
    /// the bar. Bound straight to `SidebarView.sidebarFilterText`, which
    /// drives `filteredLibraryHeaders`; rows keep stable identity so the list
    /// updates in place rather than re-rendering wholesale on filter change.
    var sidebarFilterText: Binding<String>

    private var metrics: MiniToolbarMetrics {
        #if os(macOS)
        MiniToolbarMetricPolicy.metrics(isMac: true, isTV: false)
        #elseif os(tvOS)
        MiniToolbarMetricPolicy.metrics(isMac: false, isTV: true)
        #else
        MiniToolbarMetricPolicy.metrics(isMac: false, isTV: false)
        #endif
    }

    private var iconFont: Font {
        #if os(macOS)
        .caption
        #elseif os(tvOS)
        .title
        #else
        .body
        #endif
    }

    var body: some View {
        PaneFilterBar { adaptiveActionRow }
    }

    /// The action row on the shared AdaptiveMiniToolbarRow (#3058, parent #2670):
    /// essential verbs inline, secondary verbs into a trailing '…' menu when the
    /// sidebar is narrow or on compact width — no more overrun.
    private var adaptiveActionRow: some View {
        AdaptiveMiniToolbarRow {
            essentialButtons
        } secondary: {
            secondaryButtons
        } overflowMenu: {
            overflowMenu
        }
    }

    /// The sidebar filter field, integrated into the bottom toolbar's essential
    /// tier (#4061). Replaces the old standalone `sidebarFilterBar` so the
    /// sidebar has one unified bottom toolbar owning the filter + actions,
    /// matching the shared Surface Chrome pattern. The clear button appears
    /// only when there's text to clear — a small in-place update, no list
    /// re-render (rows keep stable identity via `filteredLibraryHeaders`).
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
    }

    /// Essential verbs — always inline (#3058): the filter field, then the
    /// New-item menu + Delete. The leading `Spacer` separates the filter from
    /// the actions so the filter sits on the left and the verbs on the right.
    @ViewBuilder
    private var essentialButtons: some View {
        filterField

        Spacer(minLength: 12)

        // New item menu (dropdown) — ONE source of truth (#4121).
        Menu {
                AddItemMenu(registry: itemRegistry, style: .contextual)
            } label: {
                Image(systemName: "plus")
                    .font(iconFont)
                    .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                    .contentShape(Rectangle())
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("New Item")
            .accessibilityLabel("New Item")

            // Remove / delete selected item
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

    /// Secondary verbs — inline when they fit, else the '…' overflow (macOS narrow)
    /// or menu-only (compact iPhone) (#3058): Import menu, New Workflow.
    ///
    /// Export used to sit here as a permanently `.disabled(true)` button whose
    /// own `.help` read "Export (not yet wired)" (#4100). A control that can
    /// never do anything is placeholder chrome, and the dead-simple-UX rule is
    /// that a feature is ON or OFF — a greyed button that never ungreys reads
    /// as "broken", not "coming".
    ///
    /// Nothing is lost: File ▸ Export already exports (BibTeX, Markdown static
    /// site), library-scoped and working. #2309 tracks a SIDEBAR-scoped export
    /// handler, and the button comes back when there is something behind it.
    @ViewBuilder
    private var secondaryButtons: some View {
            // Import menu
            Menu {
                Button(
                    action: { importFiles(.link) },
                    label: {
                        Label(IngestMode.link.displayName, systemImage: IngestMode.link.icon)
                    }
                )

                Button(
                    action: { importFiles(.copy) },
                    label: {
                        Label(IngestMode.copy.displayName, systemImage: IngestMode.copy.icon)
                    }
                )

                Button(
                    action: { importFiles(.move) },
                    label: {
                        Label(IngestMode.move.displayName, systemImage: IngestMode.move.icon)
                    }
                )
            } label: {
                Image(systemName: "square.and.arrow.down")
                    .font(iconFont)
                    .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                    .contentShape(Rectangle())
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Import Files (⌘I)")
            .accessibilityLabel("Import Files")

            // Run workflow on selection (only shown when workflows feature is enabled)
            if featureManager.isWorkflowsEnabled {
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

    /// `Label`-based mirror of the secondary verbs for the overflow '…' menu
    /// (#3058) — same actions + disabled logic, menu-item presentation.
    @ViewBuilder
    private var overflowMenu: some View {
        // Export intentionally absent — see `secondaryButtons` (#4100). The
        // overflow menu mirrors the inline verbs, so a dead entry here would
        // reintroduce the same never-enabled control one menu deeper.

        // Import submenu (link / copy / move), mirroring the inline Import menu.
        Menu {
            Button { importFiles(.link) } label: {
                Label(IngestMode.link.displayName, systemImage: IngestMode.link.icon)
            }
            Button { importFiles(.copy) } label: {
                Label(IngestMode.copy.displayName, systemImage: IngestMode.copy.icon)
            }
            Button { importFiles(.move) } label: {
                Label(IngestMode.move.displayName, systemImage: IngestMode.move.icon)
            }
        } label: {
            Label("Import Files", systemImage: "square.and.arrow.down")
        }

        if featureManager.isWorkflowsEnabled {
            Button {
                itemRegistry.createWorkflow?()
            } label: {
                Label("New Workflow", systemImage: "bolt")
            }
            .disabled(!hasSelection)
        }
    }
}
