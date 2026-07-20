import Foundation
import OSLog

let workflowStreamLogger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowStreamService")

extension WorkflowStreamService {
    func parseEvent(_ jsonString: String) -> WorkflowStreamEvent? {
        guard let data = jsonString.data(using: .utf8) else {
            workflowStreamLogger.error("[SSE-PARSE] Failed to convert string to data")
            return nil
        }

        do {
            let decoder = JSONDecoder()
            let eventData = try decoder.decode(SSEEventData.self, from: data)
            workflowStreamLogger.info("[SSE-PARSE] Event type: \(eventData.event), threadId: \(eventData.threadId)")

            switch eventData.event {
            case "start", "node_begin", "node_end", "complete", "pause", "cancelled", "error", "log":
                return parseLifecycleEvent(eventData)
            case "parallel_start", "file_start", "file_complete", "file_error", "parallel_complete", "systemic_error":
                return parseFileEvent(eventData)
            default:
                workflowStreamLogger.warning("Unknown SSE event type: \(eventData.event)")
                return nil
            }
        } catch {
            workflowStreamLogger.error("Failed to parse SSE event: \(error.localizedDescription)")
            return nil
        }
    }

    /// Parse the non-parallel, non-file lifecycle events: workflow start/end,
    /// per-node begin/end, pause/cancel, top-level error, and log lines.
    private func parseLifecycleEvent(_ eventData: SSEEventData) -> WorkflowStreamEvent? {
        switch eventData.event {
        case "start":
            let workflowName = (eventData.data["workflow_name"]?.stringValue) ?? "Unknown"
            return .start(threadId: eventData.threadId, workflowName: workflowName)

        case "node_begin":
            // node_id can be top-level or in data dict
            let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
            let nodeName = (eventData.data["node_name"]?.stringValue) ?? nodeId
            return .nodeBegin(threadId: eventData.threadId, nodeId: nodeId, nodeName: nodeName)

        case "node_end":
            // node_id can be top-level or in data dict
            let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
            let durationMs = (eventData.data["duration_ms"]?.doubleValue) ?? 0
            return .nodeEnd(
                threadId: eventData.threadId,
                nodeId: nodeId,
                durationMs: durationMs,
                output: nil // Simplified - full output parsing would require more work
            )

        case "complete":
            let checkpointId = eventData.data["checkpoint_id"]?.stringValue
            return .complete(threadId: eventData.threadId, checkpointId: checkpointId, finalState: nil)

        case "pause":
            let checkpointId = eventData.data["checkpoint_id"]?.stringValue
            return .pause(threadId: eventData.threadId, checkpointId: checkpointId, currentState: nil)

        case "cancelled":
            return .cancelled(threadId: eventData.threadId)

        case "error":
            let errorMsg = (eventData.data["error"]?.stringValue) ?? "Unknown error"
            return .error(threadId: eventData.threadId, error: errorMsg)

        case "log":
            let line = (eventData.data["line"]?.stringValue) ?? ""
            return .log(threadId: eventData.threadId, line: line)

        default:
            return nil
        }
    }

    /// Dispatch the parallel-execution and per-file progress events to their
    /// two sub-parsers (kept separate to stay under the function-length limit).
    private func parseFileEvent(_ eventData: SSEEventData) -> WorkflowStreamEvent? {
        switch eventData.event {
        case "file_start", "file_complete", "file_error":
            return parseFileProgressEvent(eventData)
        case "parallel_start", "parallel_complete", "systemic_error":
            return parseParallelAggregateEvent(eventData)
        default:
            return nil
        }
    }

    /// Shared node/file identity + progress fields, common to `file_start`,
    /// `file_complete` and `file_error` (top-level fields win, falling back to
    /// the nested `data` dictionary).
    private struct FileEventMeta {
        let nodeId: String
        let filePath: String
        let fileIndex: Int
        let fileTotal: Int
        let progress: Double
    }

    private func extractFileMeta(_ eventData: SSEEventData) -> FileEventMeta {
        let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
        let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
        let fileIndex = eventData.fileIndex ?? eventData.data["file_index"]?.intValue ?? 0
        let fileTotal = eventData.fileTotal ?? eventData.data["file_total"]?.intValue ?? 0
        let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
        return FileEventMeta(
            nodeId: nodeId, filePath: filePath, fileIndex: fileIndex, fileTotal: fileTotal, progress: progress
        )
    }

    /// Parse per-file progress events for a single file in a parallel batch.
    private func parseFileProgressEvent(_ eventData: SSEEventData) -> WorkflowStreamEvent? {
        switch eventData.event {
        case "file_start":
            // A single file has started processing in parallel
            let meta = extractFileMeta(eventData)
            return .fileStart(
                threadId: eventData.threadId,
                nodeId: meta.nodeId,
                filePath: meta.filePath,
                fileIndex: meta.fileIndex,
                fileTotal: meta.fileTotal,
                progress: meta.progress,
                documentId: eventData.documentId,
                pageId: eventData.pageId,
                displayName: eventData.displayName,
                sequence: eventData.sequence
            )

        case "file_complete":
            // A single file has completed processing in parallel
            let meta = extractFileMeta(eventData)
            let cached = eventData.data["cached"]?.boolValue ?? false
            return .fileComplete(
                threadId: eventData.threadId,
                nodeId: meta.nodeId,
                filePath: meta.filePath,
                fileIndex: meta.fileIndex,
                fileTotal: meta.fileTotal,
                progress: meta.progress,
                cached: cached,
                documentId: eventData.documentId,
                pageId: eventData.pageId,
                displayName: eventData.displayName,
                sequence: eventData.sequence
            )

        case "file_error":
            // A single file failed processing in parallel
            let meta = extractFileMeta(eventData)
            let errorMsg = eventData.data["error"]?.stringValue ?? "Unknown error"
            return .fileError(
                threadId: eventData.threadId,
                nodeId: meta.nodeId,
                filePath: meta.filePath,
                error: errorMsg,
                progress: meta.progress,
                documentId: eventData.documentId,
                pageId: eventData.pageId,
                displayName: eventData.displayName,
                sequence: eventData.sequence
            )

        default:
            return nil
        }
    }

    /// Parse the node-level parallel-batch aggregate events (start/complete of
    /// the whole batch, plus the systemic-error terminal event).
    private func parseParallelAggregateEvent(_ eventData: SSEEventData) -> WorkflowStreamEvent? {
        switch eventData.event {
        case "parallel_start":
            // Parallel processing has begun for a node
            let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
            let fileTotal = eventData.fileTotal ?? eventData.data["total"]?.intValue ?? 0
            return .parallelStart(
                threadId: eventData.threadId,
                nodeId: nodeId,
                fileTotal: fileTotal
            )

        case "parallel_complete":
            // node_id is top-level for parallel events
            let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
            let successCount = eventData.data["success_count"]?.intValue ?? 0
            let errorCount = eventData.data["error_count"]?.intValue ?? 0
            let total = eventData.fileTotal ?? eventData.data["total"]?.intValue ?? 0
            return .parallelComplete(
                threadId: eventData.threadId,
                nodeId: nodeId,
                successCount: successCount,
                errorCount: errorCount,
                total: total
            )

        case "systemic_error":
            let errorMsg = (eventData.data["error"]?.stringValue) ?? "Unknown error"
            let errorCount = eventData.data["error_count"]?.intValue ?? 0
            let totalCount = eventData.data["total_count"]?.intValue ?? 0
            return .systemicError(
                threadId: eventData.threadId,
                error: errorMsg,
                errorCount: errorCount,
                totalCount: totalCount
            )

        default:
            return nil
        }
    }
}
