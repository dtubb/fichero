import SwiftUI

// MARK: - Activity Workflow Group

/// Groups activity runs by workflow ID (falls back to name-based key when
/// the workflow ID is absent) for sidebar display. Previously lived in
/// `ActivitySidebarContent.swift`; moved here when the pre-unified
/// mode-sidebar files were retired.
struct ActivityWorkflowGroup: Hashable, Identifiable {
    let id: String  // workflowId (or fallback key for runs without ID)
    let displayName: String

    static func key(workflowId: String?, workflowName: String) -> String {
        workflowId ?? "name:\(workflowName)"
    }
}

// MARK: - Data Processing (File-level functions)

// All runs grouped by workflow ID for a specific library
@MainActor
func runsByWorkflow(
    for library: LibraryManager.LibraryReference,
    activeExecutions: [String: WorkflowExecution],
    historicalRuns: [UUID: [ActivityItem]]
) -> [ActivityWorkflowGroup: [ActivityRun]] {
    var groups: [ActivityWorkflowGroup: [ActivityRun]] = [:]
    var seenThreadIds = Set<String>()

    if library.id == LibraryManager.globalLibraryId {
        addActiveExecutionRuns(
            activeExecutions,
            libraryId: library.id,
            groups: &groups,
            seenThreadIds: &seenThreadIds
        )
    }

    addHistoricalRuns(
        historicalRuns[library.id] ?? [],
        libraryId: library.id,
        groups: &groups,
        seenThreadIds: &seenThreadIds
    )

    for key in groups.keys {
        groups[key]?.sort { $0.timestamp > $1.timestamp }
    }

    return groups
}

// Extracted from `runsByWorkflow`: folds live executions (global library
// only) into `groups`, mirroring the original loop order/side effects.
private func addActiveExecutionRuns(
    _ activeExecutions: [String: WorkflowExecution],
    libraryId: UUID,
    groups: inout [ActivityWorkflowGroup: [ActivityRun]],
    seenThreadIds: inout Set<String>
) {
    for execution in activeExecutions.values {
        let workflowName = activityCleanWorkflowName(execution.name)
        let groupKey = ActivityWorkflowGroup(
            id: ActivityWorkflowGroup.key(workflowId: execution.id, workflowName: workflowName),
            displayName: workflowName
        )
        let status = activityMapExecutionStatus(execution.status)
        let sidebarRunId = "\(libraryId.uuidString)|\(execution.threadId)"
        let run = ActivityRun(
            id: sidebarRunId,
            runId: execution.threadId,
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
        seenThreadIds.insert(execution.threadId)
    }
}

// Extracted from `runsByWorkflow`: folds historical (persisted) runs into
// `groups`, skipping thread IDs already seen from live executions.
private func addHistoricalRuns(
    _ unsortedRuns: [ActivityItem],
    libraryId: UUID,
    groups: inout [ActivityWorkflowGroup: [ActivityRun]],
    seenThreadIds: inout Set<String>
) {
    let libraryRuns = unsortedRuns
        .sorted { ($0.parsedTimestamp ?? .distantPast) > ($1.parsedTimestamp ?? .distantPast) }
    for item in libraryRuns {
        // Batch-level events can be missing threadId; use synthetic thread token.
        let threadId = item.threadId ?? item.batchId.map { "batch:\($0)" }
        guard let threadId else { continue }

        if seenThreadIds.contains(threadId) {
            continue
        }

        let status = activityMapActivityType(item.type)
        let workflowName = activityExtractWorkflowName(from: item)
        let sidebarRunId = "\(libraryId.uuidString)|\(threadId)"
        let groupKey = ActivityWorkflowGroup(
            id: ActivityWorkflowGroup.key(workflowId: item.workflowId, workflowName: workflowName),
            displayName: workflowName
        )
        let run = ActivityRun(
            id: sidebarRunId,
            runId: threadId,
            workflowId: item.workflowId,
            threadId: threadId,
            workflowName: workflowName,
            timestamp: item.parsedTimestamp ?? Date(),
            status: status,
            progress: nil,
            currentStep: nil,
            errorCount: activityHasError(item) ? 1 : 0,
            fileCount: activityExtractFileCount(from: item),
            isLive: false
        )
        groups[groupKey, default: []].append(run)
        seenThreadIds.insert(threadId)
    }
}

func activityMapExecutionStatus(_ status: WorkflowStatus) -> ActivityRunStatus {
    switch status {
    case .running, .idle: return .running
    case .paused: return .paused
    case .completed: return .completed
    case .failed: return .failed
    }
}

func activityMapActivityType(_ type: String) -> ActivityRunStatus {
    switch type {
    case "workflow_started": return .running
    case "workflow_paused": return .paused
    case "workflow_completed": return .completed
    case "workflow_failed": return .failed
    case "workflow_cancelled": return .cancelled
    case "batch_started", "batch_item_started": return .running
    case "batch_completed", "batch_item_completed": return .completed
    case "batch_failed", "batch_item_failed": return .failed
    case "batch_cancelled": return .cancelled
    default: return .completed
    }
}

func activityHasError(_ item: ActivityItem) -> Bool {
    if let error = item.error, !error.isEmpty { return true }
    return item.type == "workflow_failed" || item.type == "batch_failed" || item.type == "batch_item_failed"
}

func activityExtractFileCount(from item: ActivityItem) -> Int {
    if let count = item.metadataStrings?["input_count"].flatMap(Int.init) { return count }
    if let count = item.metadataStrings?["total_results"].flatMap(Int.init) { return count }
    if let count = item.metadataStrings?["nodes_completed"].flatMap(Int.init) { return count }
    return 0
}

func activityExtractWorkflowName(from item: ActivityItem) -> String {
    if item.type.hasPrefix("batch_"), let batchId = item.batchId {
        return "Batch \(String(batchId.prefix(8)))"
    }
    if let name = item.metadataStrings?["workflow_name"] { return activityCleanWorkflowName(name) }
    if item.message.hasPrefix("Workflow '") {
        let afterPrefix = String(item.message.dropFirst(10))
        if let endQuote = afterPrefix.firstIndex(of: "'") {
            return activityCleanWorkflowName(String(afterPrefix[..<endQuote]))
        }
    }
    return "Unknown Workflow"
}

func activityCleanWorkflowName(_ name: String) -> String {
    name.hasPrefix("Workflow ") ? String(name.dropFirst(9)) : name
}

/// Strips the Fichero storage-hash prefix from a filename for display.
/// Fichero stores files as `<8-hex>_<original-name>.<ext>` to deduplicate by
/// content. The hash is useful internally but looks like noise in the UI
/// (#698). Returns the original filename if no hash prefix is present.
func activityCleanFilename(_ name: String) -> String {
    let components = name.split(separator: "_", maxSplits: 1, omittingEmptySubsequences: false)
    guard components.count == 2 else { return name }
    let prefix = components[0]
    let looksLikeHash = prefix.count >= 6 && prefix.count <= 12
        && prefix.allSatisfy { $0.isHexDigit }
    return looksLikeHash ? String(components[1]) : name
}

/// Returns a human-readable display name for a LangGraph node ID, or nil
/// if the node is internal plumbing that should be hidden from the UI.
///
/// Hidden: UUID thread slots, dunder names (__start__, __pregel_*), fan_out.
/// Others: snake_case converted to Title Case.
func activityHumanNodeName(_ nodeId: String) -> String? {
    if UUID(uuidString: nodeId) != nil { return nil }
    if nodeId.hasPrefix("__") { return nil }
    let hiddenInternals: Set<String> = ["fan_out"]
    if hiddenInternals.contains(nodeId) { return nil }
    return nodeId
        .split(separator: "_")
        .map { $0.prefix(1).uppercased() + $0.dropFirst() }
        .joined(separator: " ")
}

/// Maps internal identifiers (artifact types, node ids) to user-facing labels.
/// Falls back to Title Case from snake_case.
func activityDisplayName(forIdentifier identifier: String) -> String {
    let key = identifier.lowercased()
    let known: [String: String] = [
        "page_content": "Page Content",
        "transcription": "Transcription",
        "entities": "Entities",
        "summary": "Summary",
        "translation": "Translation",
        "grouping": "Grouping",
        "segmentation": "Segmentation",
        "classification": "Classification",
        "embedding": "Embedding",
        "extract_all_entities": "Extract Entities",
        "extract_entities": "Extract Entities",
        "catalogue": "Catalogue",
        "describe": "Describe",
        "summarize": "Summarize"
    ]
    if let mapped = known[key] { return mapped }
    return identifier
        .split(separator: "_")
        .map { $0.prefix(1).uppercased() + $0.dropFirst() }
        .joined(separator: " ")
}

/// Humanizes internal pipeline tokens embedded in activity messages so the
/// Activity UI surfaces user-facing names.
func activityHumanizeMessage(_ message: String) -> String {
    var result = message
    let patterns = [
        #"(artifact(?:_type)?[=: ]+)([a-z][a-z0-9_]+)"#,
        #"(node(?:_name|_id)?[=: ]+)([a-z][a-z0-9_]+)"#,
        #"(step(?:_name)?[=: ]+)([a-z][a-z0-9_]+)"#
    ]
    for pattern in patterns {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
            continue
        }
        let messageNSString = result as NSString
        let matches = regex.matches(
            in: result,
            range: NSRange(location: 0, length: messageNSString.length)
        ).reversed()
        for match in matches where match.numberOfRanges >= 3 {
            let prefix = messageNSString.substring(with: match.range(at: 1))
            let token = messageNSString.substring(with: match.range(at: 2))
            let replacement = prefix + activityDisplayName(forIdentifier: token)
            result = (result as NSString).replacingCharacters(in: match.range, with: replacement)
        }
    }
    return result
}

func activityRunDisplayName(for run: ActivityRun) -> String {
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
