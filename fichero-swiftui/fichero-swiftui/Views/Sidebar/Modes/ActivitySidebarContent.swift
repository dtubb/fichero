import OSLog
import SwiftUI

let activitySidebarLogger = Logger(subsystem: "com.tubb.Fichero", category: "ActivitySidebarContent")

/// Represents a workflow group for sidebar display (groups runs by workflow ID, not name)
struct ActivityWorkflowGroup: Hashable, Identifiable {
    let id: String  // workflowId (or fallback key for runs without ID)
    let displayName: String

    static func key(workflowId: String?, workflowName: String) -> String {
        workflowId ?? "name:\(workflowName)"
    }
}

/// Unified Activity sidebar - shows all workflow runs (running + completed + failed)
struct ActivitySidebarContent: View {
    @ObservedObject var libraryManager: LibraryManager
    @ObservedObject var sidebarState: SidebarState
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @EnvironmentObject var windowState: WindowState

    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode

    let historicalRunsByLibrary: [UUID: [ActivityItem]]
    let isLoading: Bool
    var onRefresh: (() -> Void)?

    var activeExecutionsSnapshot: [String: WorkflowExecution] {
        executionObserver.activeExecutions
    }

    // MARK: - Expansion State Helpers

    func isWorkflowExpanded(_ groupId: String) -> Bool {
        sidebarState.expandedItems.contains("activity-workflow-\(groupId)")
    }

    func setWorkflowExpanded(_ groupId: String, expanded: Bool) {
        let key = "activity-workflow-\(groupId)"
        if expanded {
            sidebarState.expandedItems.insert(key)
        } else {
            sidebarState.expandedItems.remove(key)
        }
    }

    func isRunExpanded(_ runId: String) -> Bool {
        sidebarState.expandedItems.contains("activity-run-\(runId)")
    }

    func setRunExpanded(_ runId: String, expanded: Bool) {
        let key = "activity-run-\(runId)"
        if expanded {
            sidebarState.expandedItems.insert(key)
        } else {
            sidebarState.expandedItems.remove(key)
        }
    }

    var selectedRun: SelectedActivityRun? {
        if case .activity(let run) = viewMode {
            return run
        }
        return nil
    }

    func totalRunCount(for library: LibraryManager.LibraryReference) -> Int {
        runsByWorkflow(
            for: library,
            activeExecutions: activeExecutionsSnapshot,
            historicalRuns: historicalRunsByLibrary
        )
        .values.reduce(0) { $0 + $1.count }
    }

    var body: some View {
        List(selection: $selectedItemId) {
            if isLoading && historicalRunsByLibrary.isEmpty && activeExecutionsSnapshot.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else {
                ForEach(libraryManager.openLibraries, id: \.id) { library in
                    let groupedRuns = runsByWorkflow(
                        for: library,
                        activeExecutions: activeExecutionsSnapshot,
                        historicalRuns: historicalRunsByLibrary
                    )
                    Section {
                        if !groupedRuns.isEmpty {
                            ForEach(groupedRuns.keys.sorted { $0.displayName < $1.displayName }) { workflowGroup in
                                if let runs = groupedRuns[workflowGroup] {
                                    workflowSection(group: workflowGroup, runs: runs)
                                }
                            }
                        } else if !isLoading {
                            Text("No workflow runs")
                                .foregroundStyle(.secondary)
                                .font(.caption)
                        }
                    } header: {
                        LibrarySectionHeader(
                            library: library,
                            itemCount: totalRunCount(for: library),
                            isCurrentLibrary: library.id == windowState.libraryId
                        )
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .onChange(of: selectedItemId) { _, newId in
            handleSelection(newId)
        }
        .onChange(of: viewMode) { _, newMode in
            if case .activity(let run) = newMode {
                if let run = run {
                    let selectedRunToken = sidebarRunToken(for: run.id) ?? run.id
                    if let childType = run.childType {
                        selectedItemId = "run-\(selectedRunToken)-\(childType.rawValue)"
                    } else {
                        selectedItemId = "run-\(selectedRunToken)"
                    }
                } else {
                    selectedItemId = nil
                }
            }
        }
        .onAppear {
            let snapshot = activeExecutionsSnapshot
            for execution in snapshot.values {
                setWorkflowExpanded(execution.id, expanded: true)
                setRunExpanded(execution.threadId, expanded: true)
            }
        }
        .onChange(of: activeExecutionsSnapshot.count) { oldCount, newCount in
            let snapshot = activeExecutionsSnapshot
            for execution in snapshot.values {
                setWorkflowExpanded(execution.id, expanded: true)
                setRunExpanded(execution.threadId, expanded: true)
            }

            if newCount < oldCount {
                Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(500))
                    onRefresh?()
                }
            }
        }
    }

    func sidebarRunToken(for runId: String) -> String? {
        for library in libraryManager.openLibraries {
            let groups = runsByWorkflow(
                for: library,
                activeExecutions: activeExecutionsSnapshot,
                historicalRuns: historicalRunsByLibrary
            )
            for runs in groups.values {
                if let run = runs.first(where: { $0.runId == runId }) {
                    return run.id
                }
            }
        }
        return nil
    }
}

// MARK: - Preview

#Preview {
    ActivitySidebarContent(
        libraryManager: .shared,
        sidebarState: SidebarState(windowId: "preview"),
        selectedItemId: .constant(nil),
        viewMode: .constant(.activity(nil)),
        historicalRunsByLibrary: [:],
        isLoading: false,
        onRefresh: nil
    )
    .environment(WorkflowExecutionObserver())
    .environmentObject(WindowState(libraryId: LibraryManager.globalLibraryId))
    .frame(width: 280, height: 500)
}
