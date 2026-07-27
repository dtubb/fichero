import Foundation
import OSLog

// MARK: - SSE Event Types

/// Events received from workflow execution SSE stream
enum WorkflowStreamEvent: Equatable {
    case start(threadId: String, workflowName: String)
    case nodeBegin(threadId: String, nodeId: String, nodeName: String)
    case nodeEnd(threadId: String, nodeId: String, durationMs: Double, output: [String: Any]?)
    // Parallel execution events
    case parallelStart(threadId: String, nodeId: String, fileTotal: Int)
    case fileStart(threadId: String, nodeId: String, filePath: String, fileIndex: Int, fileTotal: Int,
                   progress: Double, documentId: String?, pageId: String?, displayName: String?, sequence: Int?)
    case fileComplete(threadId: String, nodeId: String, filePath: String, fileIndex: Int, fileTotal: Int,
                      progress: Double, cached: Bool, documentId: String?, pageId: String?, displayName: String?,
                      sequence: Int?)
    case fileError(threadId: String, nodeId: String, filePath: String, error: String, progress: Double,
                   documentId: String?, pageId: String?, displayName: String?, sequence: Int?)
    case parallelComplete(threadId: String, nodeId: String, successCount: Int, errorCount: Int, total: Int)
    case complete(threadId: String, checkpointId: String?, finalState: [String: Any]?)
    case pause(threadId: String, checkpointId: String?, currentState: [String: Any]?)
    case cancelled(threadId: String)
    case error(threadId: String, error: String)
    case systemicError(threadId: String, error: String, errorCount: Int, totalCount: Int)
    case log(threadId: String, line: String)

    // Equatable for testing - simplified comparison
    // Exhaustive switch over every case of this enum, one comparison per case;
    // the complexity is inherent to enumerating the cases, not real branching logic.
    // swiftlint:disable:next cyclomatic_complexity
    static func == (lhs: WorkflowStreamEvent, rhs: WorkflowStreamEvent) -> Bool {
        switch (lhs, rhs) {
        case (.start(let lhsThread, _), .start(let rhsThread, _)):
            return lhsThread == rhsThread
        case (.nodeBegin(let lhsThread, let lhsNode, _), .nodeBegin(let rhsThread, let rhsNode, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.nodeEnd(let lhsThread, let lhsNode, _, _), .nodeEnd(let rhsThread, let rhsNode, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.parallelStart(let lhsThread, let lhsNode, _), .parallelStart(let rhsThread, let rhsNode, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileStart(let lhsThread, let lhsNode, _, _, _, _, _, _, _, _),
              .fileStart(let rhsThread, let rhsNode, _, _, _, _, _, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileComplete(let lhsThread, let lhsNode, _, _, _, _, _, _, _, _, _),
              .fileComplete(let rhsThread, let rhsNode, _, _, _, _, _, _, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.fileError(let lhsThread, let lhsNode, _, _, _, _, _, _, _),
              .fileError(let rhsThread, let rhsNode, _, _, _, _, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.parallelComplete(let lhsThread, let lhsNode, _, _, _),
              .parallelComplete(let rhsThread, let rhsNode, _, _, _)):
            return lhsThread == rhsThread && lhsNode == rhsNode
        case (.complete(let lhsThread, _, _), .complete(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.pause(let lhsThread, _, _), .pause(let rhsThread, _, _)):
            return lhsThread == rhsThread
        case (.cancelled(let lhsThread), .cancelled(let rhsThread)):
            return lhsThread == rhsThread
        case (.error(let lhsThread, let lhsError), .error(let rhsThread, let rhsError)):
            return lhsThread == rhsThread && lhsError == rhsError
        case (.systemicError(let lhsThread, _, _, _), .systemicError(let rhsThread, _, _, _)):
            return lhsThread == rhsThread
        case (.log(let lhsThread, let lhsLine), .log(let rhsThread, let rhsLine)):
            return lhsThread == rhsThread && lhsLine == rhsLine
        default:
            return false
        }
    }
}

/// Response from POST /execute (202 Accepted)
struct ExecuteAcceptedResponse: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: String
    let streamUrl: String

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case workflowName = "workflow_name"
        case status
        case streamUrl = "stream_url"
    }
}

/// SSE event data from backend
struct SSEEventData: Codable {
    let event: String
    let threadId: String
    let workflowId: String
    let data: [String: AnyCodableValue]
    let timestamp: String
    // Parallel execution fields (top-level, not nested in data)
    let nodeId: String?
    let filePath: String?
    let fileIndex: Int?
    let fileTotal: Int?
    let progress: Double?
    let documentId: String?
    let pageId: String?
    let displayName: String?
    let sequence: Int?

    enum CodingKeys: String, CodingKey {
        case event
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case data
        case timestamp
        case nodeId = "node_id"
        case filePath = "file_path"
        case fileIndex = "file_index"
        case fileTotal = "file_total"
        case progress
        case documentId = "document_id"
        case pageId = "page_id"
        case displayName = "display_name"
        case sequence
    }
}

struct FileProgressIdentity: Equatable {
    let filePath: String
    let documentId: String?
    let pageId: String?
    let displayName: String?
    let sequence: Int?

    var stableId: String {
        pageId ?? documentId ?? filePath
    }

    var leafDocumentId: String? {
        pageId ?? documentId
    }

    var resolvedDisplayName: String {
        if let displayName, !displayName.isEmpty {
            return displayName
        }
        if let sequence {
            return "Page \(sequence)"
        }
        return (filePath as NSString).lastPathComponent
    }
}

extension WorkflowStreamEvent {
    var isTerminal: Bool {
        switch self {
        case .complete, .cancelled, .error, .systemicError:
            return true
        default:
            return false
        }
    }

    var fileProgressIdentity: FileProgressIdentity? {
        switch self {
        case .fileStart(_, _, let filePath, _, _, _, let documentId, let pageId, let displayName, let sequence):
            return FileProgressIdentity(
                filePath: filePath,
                documentId: documentId,
                pageId: pageId,
                displayName: displayName,
                sequence: sequence
            )
        case .fileComplete(
            _, _, let filePath, _, _, _, _, let documentId, let pageId, let displayName, let sequence
        ):
            return FileProgressIdentity(
                filePath: filePath,
                documentId: documentId,
                pageId: pageId,
                displayName: displayName,
                sequence: sequence
            )
        case .fileError(_, _, let filePath, _, _, let documentId, let pageId, let displayName, let sequence):
            return FileProgressIdentity(
                filePath: filePath,
                documentId: documentId,
                pageId: pageId,
                displayName: displayName,
                sequence: sequence
            )
        default:
            return nil
        }
    }
}

// MARK: - Errors

enum WorkflowStreamError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int)
    case parseError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL for workflow stream"
        case .invalidResponse:
            return "Invalid response from workflow stream"
        case .httpError(let statusCode):
            return "HTTP error: \(statusCode)"
        case .parseError(let message):
            return "Parse error: \(message)"
        }
    }

    static func streamFailureDescription(error: Error, streamURL: URL) -> String {
        guard streamURL.scheme?.lowercased() == "https",
              let host = streamURL.host?.lowercased(),
              host == "127.0.0.1" || host == "localhost" || host == "::1" else {
            return error.localizedDescription
        }

        return """
        Engine stream is not reachable over HTTPS at \(streamURL.absoluteString). \
        Start the dev engine with fichero-engine/scripts/start_backend.sh so TLS and pinning are available. \
        Underlying error: \(error.localizedDescription)
        """
    }
}

// MARK: - AnyCodableValue Extensions

extension AnyCodableValue {
    var stringValue: String? {
        switch self {
        case .string(let value):
            return value
        default:
            return nil
        }
    }

    var doubleValue: Double? {
        switch self {
        case .int(let value):
            return Double(value)
        case .double(let value):
            return value
        default:
            return nil
        }
    }

    var intValue: Int? {
        switch self {
        case .int(let value):
            return value
        case .double(let value):
            return Int(value)
        default:
            return nil
        }
    }

    var boolValue: Bool? {
        switch self {
        case .bool(let value):
            return value
        default:
            return nil
        }
    }
}
