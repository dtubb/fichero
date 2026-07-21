import SwiftUI

// MARK: - Sidebar Bottom Toolbar

/// Compact bottom toolbar for sidebar with common actions.
///
/// Modeled after macOS Preview/Finder bottom toolbars with small, icon-only buttons.
/// Layout: [+new menu] [−delete] [export] [import menu] [workflow] (#2309)
struct SidebarBottomToolbar: View {
    // Feature manager to hide buttons
    let featureManager = FeatureManager.shared

    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    // Optional automation creation callbacks
    var createComparison: (() -> Void)?
    var createSchedule: (() -> Void)?
    var createTrigger: (() -> Void)?
    // Selection-dependent actions (#2309)
    var deleteItem: (() -> Void)?
    var hasSelection: Bool = false

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

    /// Essential verbs — always inline (#3058): the New-item menu + Delete.
    @ViewBuilder
    private var essentialButtons: some View {
        // New item menu (dropdown)
        Menu {
                if featureManager.isSearchEnabled {
                    Button(action: createSearch) {
                        Label("New Search", systemImage: "magnifyingglass")
                    }
                }

                if featureManager.isChatEnabled {
                    Button(action: createChat) {
                        Label("New Chat", systemImage: "bubble.left.and.bubble.right")
                    }
                }

                if featureManager.isWorkflowsEnabled {
                    if let createComparison = createComparison {
                        Button(action: createComparison) {
                            Label("New Comparison", systemImage: "arrow.left.arrow.right")
                        }
                    }
                    Button(action: createWorkflow) {
                        Label("New Workflow", systemImage: "arrow.triangle.branch")
                    }
                }

                if featureManager.isAutomationEnabled || featureManager.isWorkflowsEnabled {
                    Divider()
                }

                if featureManager.isAutomationEnabled {
                    if let createSchedule = createSchedule {
                        Button(action: createSchedule) {
                            Label("New Schedule", systemImage: "clock")
                        }
                    }
                    if let createTrigger = createTrigger {
                        Button(action: createTrigger) {
                            Label("New Trigger", systemImage: "bolt")
                        }
                    }

                    if createSchedule != nil || createTrigger != nil {
                        Divider()
                    }
                }

                Button(action: createFolder) {
                    Label("New Folder", systemImage: "folder.badge.plus")
                }
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

            Spacer()
    }

    /// Secondary verbs — inline when they fit, else the '…' overflow (macOS narrow)
    /// or menu-only (compact iPhone) (#3058): Export, Import menu, New Workflow.
    @ViewBuilder
    private var secondaryButtons: some View {
            // Export — no sidebar-level export handler yet; left disabled (#2309)
            Button {
            } label: {
                Image(systemName: "square.and.arrow.up")
                    .font(iconFont)
                    .frame(minWidth: metrics.touchTargetSide, minHeight: metrics.touchTargetSide)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.borderless)
            .disabled(true)
            .help("Export (not yet wired)")
            .accessibilityLabel("Export")

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
                    createWorkflow()
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
        // Export — still disabled until a sidebar-scoped handler exists (#2309).
        Button {} label: {
            Label("Export", systemImage: "square.and.arrow.up")
        }
        .disabled(true)

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
                createWorkflow()
            } label: {
                Label("New Workflow", systemImage: "bolt")
            }
            .disabled(!hasSelection)
        }
    }
}
