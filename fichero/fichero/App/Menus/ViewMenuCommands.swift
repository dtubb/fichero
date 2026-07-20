import SwiftUI

extension FeatureTier {
    var tierBadgeText: String { environmentValue.uppercased() }

    var legendColor: Color {
        switch self {
        case .dev:
            .red
        case .alpha:
            .orange
        case .beta:
            .blue
        case .release:
            .green
        }
    }
}

extension FeatureManager {
    var shouldShowTierChrome: Bool { activeBuildTier != .release }

    var buildTierStatusText: String {
        "\(activeBuildTier.tierBadgeText) build - features shown at tier >= \(activeBuildTier.environmentValue)."
    }

    func badgedLabel(_ base: String, for key: FeatureKey) -> String {
        guard
            shouldShowTierChrome,
            isVisible(key),
            let descriptor = FeatureTiers.map[key],
            descriptor.tier != .release
        else {
            return base
        }
        return "\(base) [\(descriptor.tier.tierBadgeText)]"
    }

    func badgedFeatureName(for key: FeatureKey, fallback: String) -> String {
        badgedLabel(FeatureTiers.map[key]?.name ?? fallback, for: key)
    }
}

/// View menu commands - Sidebar modes, library layouts, preview modes, and inspector toggle
/// Extracted from FicheroApp.swift to maintain consistency with other menu command patterns
struct ViewMenuCommands: View {
    @Environment(ViewSettings.self) var viewSettings

    var body: some View {
        SidebarModeSection()

        Divider()

        LibraryLayoutSection(viewSettings: viewSettings)

        Divider()

        SortSection()

        Divider()

        PreviewModeSection(viewSettings: viewSettings)

        Divider()

        RepresentationSection()

        KnowledgeGraphViewModeSection()

        Divider()

        ImagePreviewMenuCommands()

        Divider()

        InspectorButton()

        PaneVisibilitySection()

        Divider()

        SelectionDrivenLayoutToggle()

        Divider()

        NavigateToParentButton()

        Divider()

        ShowRulerButton()

        Divider()

        ShowFindBarButton()
    }
}

// MARK: - Sidebar Mode Section

/// Sidebar mode selection commands with keyboard shortcuts
/// Uses @FocusedValue to update the current window's sidebar mode (reads from focusedSceneValue)
struct SidebarModeSection: View {
    @FocusedValue(\.sidebarMode) var sidebarMode

    // Feature manager to hide modes
    let featureManager = FeatureManager.shared

    /// Current mode, defaulting to .library if no window is focused
    private var currentMode: SidebarMode {
        sidebarMode?.wrappedValue ?? .library
    }

    var body: some View {
        Section("Sidebar") {
            // Content modes (1-2 always, 3-4 conditional)
            SidebarModeButton(
                mode: .library,
                label: SidebarMode.library.label,
                icon: SidebarMode.library.icon,
                shortcut: SidebarMode.library.shortcutNumber,
                current: currentMode
            ) {
                sidebarMode?.wrappedValue = .library
            }

            if featureManager.isSearchEnabled {
                SidebarModeButton(
                    mode: .search,
                    label: SidebarMode.search.label,
                    icon: SidebarMode.search.icon,
                    shortcut: SidebarMode.search.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .search
                }
            }

            if featureManager.isChatEnabled {
                SidebarModeButton(
                    mode: .chat,
                    label: featureManager.badgedFeatureName(for: .chat, fallback: SidebarMode.chat.label),
                    icon: SidebarMode.chat.icon,
                    shortcut: SidebarMode.chat.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .chat
                }
            }

            if featureManager.isWorkflowsEnabled {
                SidebarModeButton(
                    mode: .workflows,
                    label: SidebarMode.workflows.label,
                    icon: SidebarMode.workflows.icon,
                    shortcut: SidebarMode.workflows.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .workflows
                }
            }

            if featureManager.isAutomationEnabled {
                Divider()
            }

            if featureManager.isAutomationEnabled {
                SidebarModeButton(
                    mode: .automation,
                    label: featureManager.badgedFeatureName(
                        for: .automation,
                        fallback: SidebarMode.automation.label
                    ),
                    icon: SidebarMode.automation.icon,
                    shortcut: SidebarMode.automation.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .automation
                }
            }

            // Research (8) + Knowledge Graph (9) menu entries. These exist in the
            // sidebar mode-icon bar but had dropped out of the View menu, so the
            // menu items + ⌃⌘8 / ⌃⌘9 shortcuts that surface the entity browser
            // (OntologyBrowser) went missing — the lost entry point in #1485.
            if featureManager.isResearchEnabled {
                SidebarModeButton(
                    mode: .research,
                    label: featureManager.badgedFeatureName(
                        for: .research,
                        fallback: SidebarMode.research.label
                    ),
                    icon: SidebarMode.research.icon,
                    shortcut: SidebarMode.research.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .research
                }
            }

            if featureManager.isKnowledgeGraphEnabled {
                Divider()

                // Knowledge Graph mode — entity list + per-entity KG (OntologyBrowser).
                SidebarModeButton(
                    mode: .knowledgeGraph,
                    label: SidebarMode.knowledgeGraph.label,
                    icon: SidebarMode.knowledgeGraph.icon,
                    shortcut: SidebarMode.knowledgeGraph.shortcutNumber,
                    current: currentMode
                ) {
                    sidebarMode?.wrappedValue = .knowledgeGraph
                }
            }
        }
    }
}

/// Reusable sidebar mode button with checkmark when active
struct SidebarModeButton: View {
    let mode: SidebarMode
    let label: String
    let icon: String
    let shortcut: String
    let current: SidebarMode
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(label, systemImage: icon)
            if current == mode {
                Image(systemName: "checkmark")
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.control, .command]
        )
    }
}
