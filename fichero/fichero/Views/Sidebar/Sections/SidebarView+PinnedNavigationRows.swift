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

    /// The pinned bottom navigation rows (workflows browser, scoped chat,
    /// research, saved workspaces, entities) are retired (#4102): everything
    /// in the sidebar is a node under its library, and app-level surfaces
    /// are reached via the View menu (⌘-number) instead of duplicate
    /// bottom entries. Only the automation load-error surface remains here.
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
