import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ActivitySidebarContent")

/// Represents a workflow group for sidebar display (groups runs by workflow ID, not name)
struct ActivityWorkflowGroup: Hashable, Identifiable {
    let id: String  // workflowId (or fallback key for runs without ID)
    let displayName: String

    /// Create a unique key for a workflow
    /// Uses workflowId when available, falls back to "name:<name>" for disambiguation
    static func key(workflowId: String?, workflowName: String) -> String {
        workflowId ?? "name:\(workflowName)"
    }
}

/// Unified Activity sidebar - shows all workflow runs (running + completed + failed)
/// Xcode Report Navigator style: Library sections → Workflow groups → individual runs
/// Data is managed by parent (SidebarView) using proper Combine observers
struct ActivitySidebarContent: View {
    @ObservedObject var libraryManager: LibraryManager
    @ObservedObject var sidebarState: SidebarState
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @EnvironmentObject var windowState: WindowState

    // Selection binding from parent (following Library pattern)
    @Binding var selectedItemId: String?
    @Binding var viewMode: AppViewMode

    // Data from parent (SidebarView manages loading via Combine pattern)
    let historicalRunsByLibrary: [UUID: [ActivityItem]]
    let isLoading: Bool
    var onRefresh: (() -> Void)?

    /// Snapshot of active executions to avoid re-entrancy issues during view updates
    private var activeExecutionsSnapshot: [String: WorkflowExecution] {
        executionObserver.activeExecutions
    }

    // MARK: - Expansion State Helpers (use SidebarState)

    private func isWorkflowExpanded(_ groupId: String) -> Bool {
        sidebarState.expandedItems.contains("activity-workflow-\(groupId)")
    }

    private func setWorkflowExpanded(_ groupId: String, expanded: Bool) {
        let key = "activity-workflow-\(groupId)"
        if expanded {
            sidebarState.expandedItems.insert(key)
        } else {
            sidebarState.expandedItems.remove(key)
        }
    }

    private func isRunExpanded(_ runId: String) -> Bool {
        sidebarState.expandedItems.contains("activity-run-\(runId)")
    }

    private func setRunExpanded(_ runId: String, expanded: Bool) {
        let key = "activity-run-\(runId)"
        if expanded {
            sidebarState.expandedItems.insert(key)
        } else {
            sidebarState.expandedItems.remove(key)
        }
    }

    /// Currently selected run and child
    private var selectedRun: SelectedActivityRun? {
        if case .activity(let run) = viewMode {
            return run
        }
        return nil
    }

    var body: some View {
        List(selection: $selectedItemId) {
            if isLoading && historicalRunsByLibrary.isEmpty && activeExecutionsSnapshot.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .center)
                    .listRowSeparator(.hidden)
            } else {
                // Show each library with its workflow runs
                ForEach(libraryManager.openLibraries, id: \.id) { library in
                    let groupedRuns = runsByWorkflow(
                        for: library,
                        activeExecutions: activeExecutionsSnapshot,
                        historicalRuns: historicalRunsByLibrary
                    )
                    Section {
                        if !groupedRuns.isEmpty {
                            // Sort workflow groups by display name for consistent ordering
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
        .scrollContentBackground(.hidden)  // Transparent background for sidebar
        .onChange(of: selectedItemId) { _, newId in
            handleSelection(newId)
        }
        .onChange(of: viewMode) { _, newMode in
            // Sync viewMode -> selection
            if case .activity(let run) = newMode {
                if let run = run {
                    if let childType = run.childType {
                        selectedItemId = "run-\(run.id)-\(childType.rawValue)"
                    } else {
                        selectedItemId = "run-\(run.id)"
                    }
                } else {
                    selectedItemId = nil
                }
            }
        }
        .onAppear {
            // Auto-expand workflows with live runs on initial appearance
            let snapshot = activeExecutionsSnapshot
            for execution in snapshot.values {
                setWorkflowExpanded(execution.id, expanded: true)
                setRunExpanded(execution.threadId, expanded: true)
            }
        }
        .onChange(of: activeExecutionsSnapshot.count) { oldCount, newCount in
            // Auto-expand new live runs (use snapshot)
            let snapshot = activeExecutionsSnapshot
            for execution in snapshot.values {
                setWorkflowExpanded(execution.id, expanded: true)
                setRunExpanded(execution.threadId, expanded: true)
            }

            // Trigger parent to refresh history when a workflow completes (count decreases)
            if newCount < oldCount {
                Task {
                    // Brief delay to let backend save activity record
                    try? await Task.sleep(for: .milliseconds(500))
                    onRefresh?()
                }
            }
        }
    }

    // MARK: - Selection Handling

    private func handleSelection(_ id: String?) {
        // Sync selection -> viewMode
        guard let id = id else {
            logger.debug("🔵 Activity selection cleared")
            viewMode = .activity(nil)
            return
        }
        logger.debug("🔵 Activity selection: \(id)")

        // Parse the ID: "run-{UUID}" or "run-{UUID}-{childType}"
        // UUIDs contain hyphens, so we can't just split on "-"
        guard id.hasPrefix("run-") else {
            logger.warning("🔵 Invalid activity ID format (missing run- prefix): \(id)")
            return
        }

        // Remove "run-" prefix
        let remainder = String(id.dropFirst("run-".count))

        // Check if it ends with a known child type
        var runId = remainder
        var childType: ActivityChildType?

        for type in ActivityChildType.allCases {
            let suffix = "-\(type.rawValue)"
            if remainder.hasSuffix(suffix) {
                childType = type
                runId = String(remainder.dropLast(suffix.count))
                break
            }
        }

        logger.debug("🔵 Parsed runId: \(runId), childType: \(childType?.rawValue ?? "none")")

        // Find the run in our data
        if let run = findRun(byId: runId) {
            if let childType = childType {
                logger.debug("🔵 Setting viewMode to activity run \(runId) with child: \(childType.rawValue)")
                viewMode = .activity(run.toSelectedRun().with(childType: childType))
            } else {
                logger.debug("🔵 Setting viewMode to activity run \(runId) (overview)")
                viewMode = .activity(run.toSelectedRun())
            }
        } else {
            logger.warning("🔵 Could not find run with ID: \(runId)")
        }
    }

    /// Total run count for a library (for header display)
    private func totalRunCount(for library: LibraryManager.LibraryReference) -> Int {
        runsByWorkflow(for: library, activeExecutions: activeExecutionsSnapshot, historicalRuns: historicalRunsByLibrary)
            .values.reduce(0) { $0 + $1.count }
    }

    // MARK: - Workflow Section (groups runs by workflow ID)

    @ViewBuilder
    private func workflowSection(group: ActivityWorkflowGroup, runs: [ActivityRun]) -> some View {
        DisclosureGroup(
            isExpanded: Binding(
                get: { isWorkflowExpanded(group.id) },
                set: { setWorkflowExpanded(group.id, expanded: $0) }
            )
        ) {
            ForEach(runs) { run in
                runDisclosure(run)
            }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "arrow.triangle.branch")
                    .foregroundStyle(.secondary)
                    .frame(width: 16)

                Text(group.displayName)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()

                // Show count of runs
                Text("\(runs.count)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.secondary.opacity(0.15), in: Capsule())
            }
        }
    }

    // MARK: - Run Disclosure

    @ViewBuilder
    private func runDisclosure(_ run: ActivityRun) -> some View {
        DisclosureGroup(
            isExpanded: Binding(
                get: { isRunExpanded(run.id) },
                set: { setRunExpanded(run.id, expanded: $0) }
            )
        ) {
            // Children: Console, Progress, Errors
            ForEach(ActivityChildType.allCases, id: \.self) { childType in
                childRow(childType, for: run)
            }
        } label: {
            runRowLabel(run)
        }
    }

    @ViewBuilder
    private func runRowLabel(_ run: ActivityRun) -> some View {
        HStack(spacing: 8) {
            // Status icon
            if run.status == .running {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
            } else {
                Image(systemName: run.status.icon)
                    .foregroundStyle(run.status.color)
                    .frame(width: 16)
            }

            // Run timestamp (e.g., "Run 2:28 PM")
            Text(runDisplayName(for: run))
                .font(.subheadline)
                .lineLimit(1)

            Spacer()

            // Progress for running
            if run.status == .running, let progress = run.progress {
                Text("\(Int(progress * 100))%")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            // Error badge
            if run.errorCount > 0 {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                    .font(.caption)
            }
        }
        .tag("run-\(run.id)")
    }

    @ViewBuilder
    private func childRow(_ childType: ActivityChildType, for run: ActivityRun) -> some View {
        HStack(spacing: 8) {
            Image(systemName: childType.icon)
                .foregroundStyle(childType == .errors && run.errorCount > 0 ? .orange : .secondary)
                .frame(width: 16)

            Text(childType.label)
                .font(.subheadline)

            Spacer()

            // Error count badge
            if childType == .errors && run.errorCount > 0 {
                Text("\(run.errorCount)")
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.orange.opacity(0.2), in: Capsule())
            }
        }
        .tag("run-\(run.id)-\(childType.rawValue)")
    }

    // MARK: - Data

    /// Find a run by ID across all libraries
    private func findRun(byId runId: String) -> ActivityRun? {
        for library in libraryManager.openLibraries {
            let groups = runsByWorkflow(
                for: library,
                activeExecutions: activeExecutionsSnapshot,
                historicalRuns: historicalRunsByLibrary
            )
            for runs in groups.values {
                if let run = runs.first(where: { $0.id == runId }) {
                    return run
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

// MARK: - Data Processing (File-level functions)

/// All runs grouped by workflow ID for a specific library
@MainActor
private func runsByWorkflow(
    for library: LibraryManager.LibraryReference,
    activeExecutions: [String: WorkflowExecution],
    historicalRuns: [UUID: [ActivityItem]]
) -> [ActivityWorkflowGroup: [ActivityRun]] {
    var groups: [ActivityWorkflowGroup: [ActivityRun]] = [:]

    // Add active executions (currently all go to global library)
    if library.id == LibraryManager.globalLibraryId {
        for execution in activeExecutions.values {
            let workflowName = cleanWorkflowName(execution.name)
            let groupKey = ActivityWorkflowGroup(id: execution.id, displayName: workflowName)
            let status = mapExecutionStatus(execution.status)
            let run = ActivityRun(
                id: execution.threadId,
                workflowId: execution.id,
                threadId: execution.threadId,
                workflowName: workflowName,
                timestamp: execution.startTime,
                status: status,
                progress: execution.overallProgress,
                currentStep: execution.currentNodeName,
                errorCount: execution.nodeStates.values.reduce(0) { $0 + $1.errorCount },
                fileCount: execution.totalFiles,
                isLive: execution.isRunning
            )
            groups[groupKey, default: []].append(run)
        }
    }

    // Add historical runs for this library
    let libraryRuns = historicalRuns[library.id] ?? []
    for item in libraryRuns where item.type != "workflow_started" {
        let status = mapActivityType(item.type)
        let workflowName = extractWorkflowName(from: item)
        let groupKey = ActivityWorkflowGroup(
            id: ActivityWorkflowGroup.key(workflowId: item.workflowId, workflowName: workflowName),
            displayName: workflowName
        )
        let run = ActivityRun(
            id: item.id,
            workflowId: item.workflowId,
            threadId: item.threadId,
            workflowName: workflowName,
            timestamp: item.parsedTimestamp ?? Date(),
            status: status,
            progress: nil,
            currentStep: nil,
            errorCount: hasError(item) ? 1 : 0,
            fileCount: extractFileCount(from: item),
            isLive: false
        )
        groups[groupKey, default: []].append(run)
    }

    // Sort runs within each group by timestamp (newest first)
    for key in groups.keys {
        groups[key]?.sort { $0.timestamp > $1.timestamp }
    }

    return groups
}

private func mapExecutionStatus(_ status: WorkflowStatus) -> ActivityRunStatus {
    switch status {
    case .running, .paused, .idle: return .running
    case .completed: return .completed
    case .failed: return .failed
    }
}

private func mapActivityType(_ type: String) -> ActivityRunStatus {
    switch type {
    case "workflow_completed": return .completed
    case "workflow_failed": return .failed
    case "workflow_cancelled": return .cancelled
    default: return .completed
    }
}

private func hasError(_ item: ActivityItem) -> Bool {
    if let error = item.error, !error.isEmpty { return true }
    return item.type == "workflow_failed"
}

private func extractFileCount(from item: ActivityItem) -> Int {
    if let count = item.metadata?["input_count"].flatMap(Int.init) { return count }
    if let count = item.metadata?["total_results"].flatMap(Int.init) { return count }
    if let count = item.metadata?["nodes_completed"].flatMap(Int.init) { return count }
    return 0
}

private func extractWorkflowName(from item: ActivityItem) -> String {
    if let name = item.metadata?["workflow_name"] { return cleanWorkflowName(name) }
    if item.message.hasPrefix("Workflow '") {
        let afterPrefix = String(item.message.dropFirst(10))
        if let endQuote = afterPrefix.firstIndex(of: "'") {
            return cleanWorkflowName(String(afterPrefix[..<endQuote]))
        }
    }
    return "Unknown Workflow"
}

private func cleanWorkflowName(_ name: String) -> String {
    name.hasPrefix("Workflow ") ? String(name.dropFirst(9)) : name
}

private func runDisplayName(for run: ActivityRun) -> String {
    let formatter = DateFormatter()
    let daysSince = Calendar.current.dateComponents([.day], from: run.timestamp, to: Date()).day ?? 0
    switch daysSince {
    case 0: formatter.dateFormat = "'Today' h:mm a"
    case 1: formatter.dateFormat = "'Yesterday' h:mm a"
    case 2..<7: formatter.dateFormat = "EEE MMM d, h:mm a"
    default: formatter.dateFormat = "MMM d, h:mm a"
    }
    var name = formatter.string(from: run.timestamp)
    if run.fileCount > 0 { name += " (\(run.fileCount) files)" }
    return name
}
