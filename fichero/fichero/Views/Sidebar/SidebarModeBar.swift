import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarModeBar")

/// Xcode-style mode icon bar at the top of the sidebar.
/// Shows mode icons for the enabled sidebar modes.
struct SidebarModeBar: View {
    @Binding var selectedMode: SidebarMode

    // Feature manager to hide disabled modes
    @EnvironmentObject var featureManager: FeatureManager

    // Badge counts from environment
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    var body: some View {
        // Modern translucent Liquid Glass background, matching SidebarBottomToolbar
        // and the pane mini-toolbars (PaneFilterBar / MiniToolbar) for a consistent
        // glass look across the sidebar chrome (#2550).
        GlassEffectContainer {
            HStack(spacing: 2) {
                // Content modes (1-4)
                Group {
                    SidebarModeIcon(
                        mode: .library,
                        isSelected: selectedMode == .library,
                        badgeCount: badgeCount(for: .library)
                    ) {
                        selectMode(.library)
                    }

                    if featureManager.isSearchEnabled {
                        SidebarModeIcon(
                            mode: .search,
                            isSelected: selectedMode == .search,
                            badgeCount: badgeCount(for: .search)
                        ) {
                            selectMode(.search)
                        }
                    }

                    if featureManager.isChatEnabled {
                        SidebarModeIcon(
                            mode: .chat,
                            isSelected: selectedMode == .chat,
                            badgeCount: badgeCount(for: .chat)
                        ) {
                            selectMode(.chat)
                        }
                    }

                    if featureManager.isWorkflowsEnabled {
                        SidebarModeIcon(
                            mode: .workflows,
                            isSelected: selectedMode == .workflows,
                            badgeCount: badgeCount(for: .workflows)
                        ) {
                            selectMode(.workflows)
                        }
                    }

                    if featureManager.isResearchEnabled {
                        SidebarModeIcon(
                            mode: .research,
                            isSelected: selectedMode == .research,
                            badgeCount: 0
                        ) {
                            selectMode(.research)
                        }
                    }

                    if featureManager.isKnowledgeGraphEnabled {
                        SidebarModeIcon(
                            mode: .knowledgeGraph,
                            isSelected: selectedMode == .knowledgeGraph,
                            badgeCount: 0
                        ) {
                            selectMode(.knowledgeGraph)
                        }
                    }
                }

                if featureManager.isAutomationEnabled {
                    modeSeparator
                }

                // Automation mode
                Group {
                    if featureManager.isAutomationEnabled {
                        SidebarModeIcon(
                            mode: .automation,
                            isSelected: selectedMode == .automation,
                            badgeCount: badgeCount(for: .automation)
                        ) {
                            selectMode(.automation)
                        }
                    }
                }

                if featureManager.isActivityEnabled {
                    modeSeparator

                    // Monitoring mode (7)
                    SidebarModeIcon(
                        mode: .activity,
                        isSelected: selectedMode == .activity,
                        badgeCount: badgeCount(for: .activity)
                    ) {
                        selectMode(.activity)
                    }
                }

            }
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, maxHeight: MiniToolbar<EmptyView, EmptyView>.standardHeight)  // Normalize to 44pt
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    // MARK: - Helper Views

    private var modeSeparator: some View {
        Divider()
            .frame(height: 16)
            .padding(.horizontal, 4)
    }

    // MARK: - Badge Counts

    private func badgeCount(for mode: SidebarMode) -> Int {
        switch mode {
        case .activity:
            // Show count of running executions
            return executionObserver.activeExecutions.count
        default:
            return 0
        }
    }

    // MARK: - Actions

    private func selectMode(_ mode: SidebarMode) {
        logger.debug("Mode selected: \(mode.label)")
        selectedMode = mode
    }
}

#Preview {
    VStack {
        SidebarModeBar(selectedMode: .constant(.library))
        Divider()
        Text("Sidebar content would go here")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .frame(width: 280, height: 400)
    .environment(WorkflowExecutionObserver())
    .environmentObject(FeatureManager.shared)
}
