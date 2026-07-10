import SwiftUI

extension SidebarView {
    @ViewBuilder
    private func sidebarLoadErrorRow(
        title: String,
        message: String,
        retry: @escaping @MainActor () async -> Void
    ) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .fontWeight(.semibold)
                Text(message)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 8)
            Button("Retry") {
                Task { @MainActor in
                    await retry()
                }
            }
            .buttonStyle(.borderless)
        }
        .listRowInsets(EdgeInsets(top: 2, leading: 16, bottom: 2, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
        .selectionDisabled()
    }

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
            || FeatureManager.shared.isKnowledgeGraphEnabled {
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

        if let automationLoadError {
            sidebarLoadErrorRow(
                title: "Automation Unavailable",
                message: automationLoadError,
                retry: { await loadAutomationData() }
            )
        }
    }
}
