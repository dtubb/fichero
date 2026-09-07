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

    /// The pinned bottom navigation rows were retired (#4102): everything in the
    /// sidebar is a node under its library. The knowledge-graph collections
    /// (Entities / Claims, P4) are library-scoped, so they render at LIBRARY level
    /// under the active library — see `unifiedLibrarySections` — not here. Only the
    /// automation load-error surface remains at the global bottom.
    @ViewBuilder
    func pinnedGlobalNavigationRows() -> some View {
        if let automationLoadError {
            sidebarLoadErrorRow(
                title: "Automation Unavailable",
                message: automationLoadError,
                retry: { await loadAutomationData() }
            )
        }
    }
}
