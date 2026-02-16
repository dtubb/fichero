import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "SidebarModeBar")

/// Xcode-style mode icon bar at the top of the sidebar
/// Shows 7 mode icons: Library, Search, Chat, Workflows | Batches, Automation | Activity
struct SidebarModeBar: View {
    @Binding var selectedMode: SidebarMode

    // Badge counts from environment
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    // Badge counts that need to be loaded
    @State private var runningBatchCount: Int = 0

    var body: some View {
        HStack(spacing: 2) {
            // Content modes (1-4)
            ForEach([SidebarMode.library, .search, .chat, .workflows], id: \.self) { mode in
                SidebarModeIcon(
                    mode: mode,
                    isSelected: selectedMode == mode,
                    badgeCount: badgeCount(for: mode)
                ) {
                    selectMode(mode)
                }
            }

            modeSeparator

            // Automation modes (5-6)
            ForEach([SidebarMode.batches, .automation], id: \.self) { mode in
                SidebarModeIcon(
                    mode: mode,
                    isSelected: selectedMode == mode,
                    badgeCount: badgeCount(for: mode)
                ) {
                    selectMode(mode)
                }
            }

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
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity)  // Ensure full width
        .background(.bar, ignoresSafeAreaEdges: .horizontal)
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
        case .batches:
            return runningBatchCount
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
}
