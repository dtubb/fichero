import SwiftUI

// MARK: - Activity Navigation Row

extension SidebarView {
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
        .tag("activity-browser")
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private func workflowsNavigationRow() -> some View {
        Label("Workflows", systemImage: "bolt")
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .tag("workflows-browser")
            .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
    }

    private func batchesNavigationRow() -> some View {
        Label("Batches", systemImage: "square.stack.3d.up")
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .tag("batches-browser")
            .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
    }

    private func entitiesNavigationRow() -> some View {
        Label("Entities", systemImage: SidebarMode.knowledgeGraph.icon)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .tag("entities-browser")
            .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
            .help("Browse the library by entity and knowledge graph")
    }

    /// Workflows / Batches / Activity pinned once at the bottom of the sidebar.
    /// These are app-level destinations with fixed selection tags, so they must
    /// appear exactly once — not repeated under every library, which both
    /// duplicated them and made all copies share one selection highlight (#1456).
    @ViewBuilder
    func pinnedGlobalNavigationRows() -> some View {
        if FeatureManager.shared.isWorkflowsEnabled
            || FeatureManager.shared.isBatchesEnabled
            || FeatureManager.shared.isKnowledgeGraphEnabled
            || FeatureManager.shared.isActivityEnabled {
            Divider()
                .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
        }

        if FeatureManager.shared.isWorkflowsEnabled {
            workflowsNavigationRow()
        }

        if FeatureManager.shared.isBatchesEnabled {
            batchesNavigationRow()
        }

        if FeatureManager.shared.isKnowledgeGraphEnabled {
            entitiesNavigationRow()
        }

        if FeatureManager.shared.isActivityEnabled {
            activityNavigationRow()
        }
    }
}
