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

    /// Research / Workspaces section (#3533 / #3540): saved agent workspaces
    /// listed under Research. Selecting one reopens its chat/agent session in the
    /// unified Chat surface (the workspace's `messageHistoryRef` is the
    /// conversation id → the existing `.chat(id)` routing). Delete is
    /// reversible-safe per the backend. The store is the only endpoint accessor.
    @ViewBuilder
    func workspacesSection() -> some View {
        if FeatureManager.shared.isChatEnabled, let store = workspaceStore {
            Text("Workspaces")
                .font(.caption)
                .foregroundStyle(.secondary)
                .listRowInsets(EdgeInsets(top: 6, leading: 16, bottom: 2, trailing: 8))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .selectionDisabled()
                .task { await store.load() }

            ForEach(store.workspaces, id: \.id) { workspace in
                Label(workspace.title, systemImage: "bubble.left.and.text.bubble.right")
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                    .tag(SidebarDestination.chat(workspace.messageHistoryRef))
                    .listRowInsets(EdgeInsets(top: 0, leading: 24, bottom: 0, trailing: 8))
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
                    .help("Reopen this saved workspace chat")
                    .contextMenu {
                        Button(role: .destructive) {
                            Task { await store.delete(id: workspace.id) }
                        } label: {
                            Label("Delete Workspace", systemImage: "trash")
                        }
                    }
            }
        }
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

        // Model Comparison is no longer a standalone top-level mode — it folded
        // into the Chat surface's Compare facet (#3532 slice 2 / #3540). The
        // sidebar entry is retired; open Compare from within the chat.

        if FeatureManager.shared.isChatEnabled {
            chatWithDocsNavigationRow()
        }

        if FeatureManager.shared.isResearchEnabled {
            researchNavigationRow()
        }

        workspacesSection()

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
