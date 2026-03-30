import Foundation
import OSLog

let workflowStreamLogger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowStreamService")

extension WorkflowStreamService {
    // swiftlint:disable:next todo
    // TODO: Refactor parseEvent - extract case handlers into separate methods
    // Function is 115 lines, target <100
    // swiftlint:disable:next function_body_length cyclomatic_complexity
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

            case "error":
                let errorMsg = (eventData.data["error"]?.stringValue) ?? "Unknown error"
                return .error(threadId: eventData.threadId, error: errorMsg)

            case "parallel_start":
                // Parallel processing has begun for a node
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let fileTotal = eventData.fileTotal ?? eventData.data["total"]?.intValue ?? 0
                return .parallelStart(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    fileTotal: fileTotal
                )

            case "file_start":
                // A single file has started processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let fileIndex = eventData.fileIndex ?? eventData.data["file_index"]?.intValue ?? 0
                let fileTotal = eventData.fileTotal ?? eventData.data["file_total"]?.intValue ?? 0
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                return .fileStart(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    fileIndex: fileIndex,
                    fileTotal: fileTotal,
                    progress: progress
                )

            case "file_complete":
                // A single file has completed processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let fileIndex = eventData.fileIndex ?? eventData.data["file_index"]?.intValue ?? 0
                let fileTotal = eventData.fileTotal ?? eventData.data["file_total"]?.intValue ?? 0
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                let cached = eventData.data["cached"]?.boolValue ?? false
                return .fileComplete(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    fileIndex: fileIndex,
                    fileTotal: fileTotal,
                    progress: progress,
                    cached: cached
                )

            case "file_error":
                // A single file failed processing in parallel
                let nodeId = eventData.nodeId ?? (eventData.data["node_id"]?.stringValue) ?? ""
                let filePath = eventData.filePath ?? (eventData.data["file_path"]?.stringValue) ?? ""
                let errorMsg = eventData.data["error"]?.stringValue ?? "Unknown error"
                let progress = eventData.progress ?? eventData.data["progress"]?.doubleValue ?? 0.0
                return .fileError(
                    threadId: eventData.threadId,
                    nodeId: nodeId,
                    filePath: filePath,
                    error: errorMsg,
                    progress: progress
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

            case "log":
                let line = (eventData.data["line"]?.stringValue) ?? ""
                return .log(threadId: eventData.threadId, line: line)

            default:
                workflowStreamLogger.warning("Unknown SSE event type: \(eventData.event)")
                return nil
            }
        } catch {
            workflowStreamLogger.error("Failed to parse SSE event: \(error.localizedDescription)")
            return nil
        }
    }
}
