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
        .listRowInsets(SidebarRowMetrics.insets(.inlineNotice))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
        .selectionDisabled()
    }

    /// The pinned bottom navigation rows were retired (#4102) — except this
    /// deliberate, narrow pair (P4): the two peer knowledge-graph collections,
    /// Entities and Claims. A claim and an entity are NODES that flow through the
    /// SAME library as a document, so each row simply re-scopes the library pane
    /// to that node kind, LIBRARY-WIDE (the pane reads the selected item id as its
    /// `contentCollection` and shows the corresponding table). Reusing the two
    /// tables, the shared selection and the source cursor — no new KG surface.
    @ViewBuilder
    func pinnedGlobalNavigationRows() -> some View {
        Section("Knowledge") {
            knowledgeRow(
                title: "Entities",
                systemImage: "person.2",
                destination: .browser(.entities)
            )
            knowledgeRow(
                title: "Claims",
                systemImage: "quote.bubble",
                destination: .browser(.claims)
            )
        }

        if let automationLoadError {
            sidebarLoadErrorRow(
                title: "Automation Unavailable",
                message: automationLoadError,
                retry: { await loadAutomationData() }
            )
        }
    }

    /// One knowledge-graph entry row. Tagged with its `SidebarDestination` so the
    /// list's own selection routes it through `handleBrowserSelectionDestination`
    /// the same way every other node does.
    private func knowledgeRow(
        title: String,
        systemImage: String,
        destination: SidebarDestination
    ) -> some View {
        Label(title, systemImage: systemImage)
            .tag(destination)
            .listRowInsets(SidebarRowMetrics.insets(.libraryItem))
    }
}
