import SwiftUI

// MARK: - Activity Navigation Row

extension SidebarView {
    private func pinnedNavigationRow(
        _ title: String,
        systemImage: String,
        tag: SidebarDestination,
        help: String
    ) -> some View {
        Label(title, systemImage: systemImage)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .tag(tag)
            .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
            .help(help)
    }

    /// Single non-expandable "Activity" row — clicking navigates to the activity browser.
    /// Styled as a regular sidebar leaf row (icon + normal-weight label) matching
    /// Inbox / folder rows. Bold section-header style removed in #655.
    @ViewBuilder
    private func activityNavigationRow() -> some View {
        Label {
            HStack(spacing: 4) {
                Text("Activity")
                    .lineLimit(1)
                if executionObserver.isAnyWorkflowRunning {
                    // Spinner instead of static play.circle so it's clear
                    // something is actively in flight (#785). Daniel: "the
                    // blue dot in activity is also not a spinner".
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.7)
                }
            }
        } icon: {
            Image(systemName: "clock.arrow.circlepath")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        // Use .tag so List(selection:) owns the tap → onChange routes to activity view.
        // A Button without .tag in sidebar List doesn't reliably fire on macOS (#647).
        .tag(SidebarDestination.browser(.activity))
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private func workflowsNavigationRow() -> some View {
        pinnedNavigationRow(
            "Workflows",
            systemImage: "bolt",
            tag: .browser(.workflows),
            help: "Browse workflows"
        )
    }

    private func batchesNavigationRow() -> some View {
        pinnedNavigationRow(
            "Batches",
            systemImage: "square.stack.3d.up",
            tag: .browser(.batches),
            help: "Browse batch runs"
        )
    }

    private func comparisonNavigationRow() -> some View {
        pinnedNavigationRow(
            "Model Comparison",
            systemImage: "rectangle.split.2x1",
            tag: .browser(.comparison),
            help: "Open the model comparison workspace"
        )
    }

    private func chatWithDocsNavigationRow() -> some View {
        Button {
            onOpenChatWithCurrentScope?()
        } label: {
            Label("Chat with Docs", systemImage: "text.bubble")
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
        .help("Open chat scoped to the current library selection")
    }

    private func researchNavigationRow() -> some View {
        pinnedNavigationRow(
            "Research",
            systemImage: SidebarMode.research.icon,
            tag: .browser(.research),
            help: "Open the research workspace"
        )
    }

    private func entitiesNavigationRow() -> some View {
        pinnedNavigationRow(
            "Entities",
            systemImage: SidebarMode.knowledgeGraph.icon,
            tag: .browser(.entities),
            help: "Browse the library by entity and knowledge graph"
        )
    }

    /// Workflows / Batches / Activity pinned once at the bottom of the sidebar.
    /// These are app-level destinations with fixed selection tags, so they must
    /// appear exactly once — not repeated under every library, which both
    /// duplicated them and made all copies share one selection highlight (#1456).
    @ViewBuilder
    func pinnedGlobalNavigationRows() -> some View {
        if FeatureManager.shared.isWorkflowsEnabled
            || FeatureManager.shared.isBatchesEnabled
            || FeatureManager.shared.isChatEnabled
            || FeatureManager.shared.isResearchEnabled
            || FeatureManager.shared.isKnowledgeGraphEnabled
            || FeatureManager.shared.isActivityEnabled {
            Divider()
                .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .allowsHitTesting(false)
                .selectionDisabled()
        }

        if FeatureManager.shared.isWorkflowsEnabled {
            workflowsNavigationRow()
        }

        if FeatureManager.shared.isChatEnabled {
            comparisonNavigationRow()
        }

        if FeatureManager.shared.isChatEnabled {
            chatWithDocsNavigationRow()
        }

        if FeatureManager.shared.isResearchEnabled {
            researchNavigationRow()
        }

        if FeatureManager.shared.isKnowledgeGraphEnabled {
            entitiesNavigationRow()
        }

        if FeatureManager.shared.isActivityEnabled {
            activityNavigationRow()
        }
    }
}
