import SwiftUI

/// One row in the Activity monitor's hierarchical outline table (#2546 / B2).
///
/// The monitor is a three-level tree built from the shared, threadId-keyed
/// `WorkflowExecutionStore`:
///
///   run  →  nodes  →  files the running node is working on
///
/// All three levels share this single row type so a `Table` can render them
/// with one set of columns (each column switches on `kind`). Display values are
/// precomputed by `ActivityMonitorRow.rows(from:)` so the column closures stay
/// tiny — important because hierarchical `Table` bodies type-check slowly.
struct ActivityMonitorRow: Identifiable {
    enum Kind {
        case run
        case node
        case file
    }

    /// Stable, tree-unique id. Composite (`run:` / `node:` / `file:` prefixed)
    /// so selection never collides across levels.
    let id: String

    let kind: Kind

    /// Owning run's `threadId` — lets the action buttons act on the run that
    /// owns ANY selected row (node or file), not just a top-level run row.
    let runThreadId: String

    let name: String

    /// SF Symbol for the status column. Ignored when `isSpinning` is true.
    let statusSymbol: String
    let statusColor: Color

    /// Show an indeterminate spinner instead of `statusSymbol` (active work).
    let isSpinning: Bool

    /// 0...1 for the progress-bar column, or nil to leave it blank.
    let progress: Double?

    /// The count / detail column text ("5/20", "3 steps", error counts …).
    let detail: String

    /// Child rows. `nil` = leaf (no disclosure triangle).
    var children: [ActivityMonitorRow]?
}

/// Resolved status appearance for one monitor row.
private struct StatusGlyph {
    let symbol: String
    let color: Color
    let spinning: Bool
}

// MARK: - Tree construction

extension ActivityMonitorRow {

    /// Build the monitor's root rows (one per run) from live executions.
    ///
    /// Runs are sorted newest-first. Only human-visible workflow nodes are shown
    /// (LangGraph plumbing is filtered via `activityHumanNodeName`). A run's
    /// per-file `documentProgress` is attached under whichever node is *actively*
    /// processing files (status running/parallel + `fileTotal > 0`) — the backend
    /// doesn't attribute files to nodes, but in a live run only one node fans out
    /// at a time, so this reads as "what this node is working on right now".
    static func rows(from executions: [WorkflowExecution]) -> [ActivityMonitorRow] {
        executions
            .sorted { $0.startTime > $1.startTime }
            .map { runRow(for: $0) }
    }

    private static func runRow(for execution: WorkflowExecution) -> ActivityMonitorRow {
        let visibleNodes = execution.nodeStates.values
            .filter { activityHumanNodeName($0.nodeId) != nil }
            .sorted { $0.nodeId < $1.nodeId }

        let nodeRows = visibleNodes.map { nodeRow(for: $0, in: execution) }

        let glyph = runStatusGlyph(execution.status)

        let detail: String
        if execution.totalFiles > 0 {
            detail = "\(execution.processedFiles)/\(execution.totalFiles) files"
        } else if !visibleNodes.isEmpty {
            let done = visibleNodes.filter { $0.status == .completed }.count
            detail = "\(done)/\(visibleNodes.count) steps"
        } else {
            detail = ""
        }

        return ActivityMonitorRow(
            id: "run:\(execution.threadId)",
            kind: .run,
            runThreadId: execution.threadId,
            name: activityCleanWorkflowName(execution.name),
            statusSymbol: glyph.symbol,
            statusColor: glyph.color,
            isSpinning: glyph.spinning,
            progress: execution.overallProgress,
            detail: detail,
            children: nodeRows.isEmpty ? nil : nodeRows
        )
    }

    private static func nodeRow(
        for state: NodeExecutionState,
        in execution: WorkflowExecution
    ) -> ActivityMonitorRow {
        let glyph = nodeStatusGlyph(state.status)

        let isActiveParallel = (state.status == .running || state.status == .parallelRunning)
            && state.fileTotal > 0

        // Progress: prefer the file fraction for parallel nodes, else the node's
        // own 0...1 progress (completed nodes read as full).
        let progress: Double?
        if state.fileTotal > 0 {
            progress = Double(state.successCount + state.errorCount) / Double(state.fileTotal)
        } else if state.status == .completed {
            progress = 1.0
        } else if state.progress > 0 {
            progress = state.progress
        } else {
            progress = nil
        }

        var detail = ""
        if state.fileTotal > 0 {
            detail = "\(state.successCount)/\(state.fileTotal)"
            if state.errorCount > 0 {
                detail += "  \(state.errorCount) failed"
            }
        }

        let fileRows = isActiveParallel
            ? execution.orderedDocumentProgress.map { fileRow(for: $0, runThreadId: execution.threadId) }
            : []

        return ActivityMonitorRow(
            id: "node:\(execution.threadId):\(state.nodeId)",
            kind: .node,
            runThreadId: execution.threadId,
            name: state.displayName ?? activityHumanNodeName(state.nodeId) ?? state.nodeId,
            statusSymbol: glyph.symbol,
            statusColor: glyph.color,
            isSpinning: glyph.spinning,
            progress: progress,
            detail: detail,
            children: fileRows.isEmpty ? nil : fileRows
        )
    }

    private static func fileRow(
        for doc: DocumentProgress,
        runThreadId: String
    ) -> ActivityMonitorRow {
        let steps = Array(doc.stepStatuses.values)
        let hasFailed = steps.contains { if case .failed = $0 { return true }; return false }
        let hasRunning = steps.contains { if case .running = $0 { return true }; return false }
        let doneCount = steps.filter { if case .completed = $0 { return true }; return false }.count

        let glyph: StatusGlyph
        if hasFailed {
            glyph = StatusGlyph(symbol: "xmark.circle.fill", color: .red, spinning: false)
        } else if hasRunning {
            glyph = StatusGlyph(symbol: "circle", color: .secondary, spinning: true)
        } else if doneCount == steps.count && !steps.isEmpty {
            glyph = StatusGlyph(symbol: "checkmark.circle.fill", color: .green, spinning: false)
        } else {
            glyph = StatusGlyph(symbol: "circle", color: .secondary, spinning: false)
        }

        return ActivityMonitorRow(
            id: "file:\(runThreadId):\(doc.id)",
            kind: .file,
            runThreadId: runThreadId,
            name: activityCleanFilename(doc.documentName),
            statusSymbol: glyph.symbol,
            statusColor: glyph.color,
            isSpinning: glyph.spinning,
            progress: nil,
            detail: steps.isEmpty ? "" : "\(doneCount)/\(steps.count) steps",
            children: nil
        )
    }

    // MARK: - Status glyphs

    private static func runStatusGlyph(_ status: WorkflowStatus) -> StatusGlyph {
        switch status {
        case .running:   return StatusGlyph(symbol: "circle", color: .blue, spinning: true)
        case .paused:    return StatusGlyph(symbol: "pause.circle.fill", color: .orange, spinning: false)
        case .completed: return StatusGlyph(symbol: "checkmark.circle.fill", color: .green, spinning: false)
        case .failed:    return StatusGlyph(symbol: "xmark.circle.fill", color: .red, spinning: false)
        case .idle:      return StatusGlyph(symbol: "circle", color: .secondary, spinning: false)
        }
    }

    private static func nodeStatusGlyph(_ status: NodeExecutionStatus) -> StatusGlyph {
        switch status {
        case .running, .parallelRunning: return StatusGlyph(symbol: "circle", color: .blue, spinning: true)
        case .completed:                 return StatusGlyph(symbol: "checkmark.circle.fill", color: .green, spinning: false)
        case .failed:                    return StatusGlyph(symbol: "xmark.circle.fill", color: .red, spinning: false)
        case .idle:                      return StatusGlyph(symbol: "circle", color: .secondary, spinning: false)
        }
    }
}
