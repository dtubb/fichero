import Foundation

// MARK: - Data Models

struct ProgressTimeline: Codable {
    let nodes: [String: NodeProgressStats]
    let steps: [ExecutionStep]
}

struct NodeProgressStats: Codable {
    let totalFiles: Int
    let successCount: Int
    let errorCount: Int

    enum CodingKeys: String, CodingKey {
        case totalFiles = "total_files"
        case successCount = "success_count"
        case errorCount = "error_count"
    }
}

struct ExecutionStep: Codable {
    let type: String?  // nil for node steps, "file" for file steps
    let nodeId: String
    let filePath: String?
    let fileIndex: Int?
    let fileTotal: Int?
    let startedAt: String
    let completedAt: String?
    let status: String
    let durationMs: Double?
    let filesProcessed: Int?
    let artifactsCreated: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case type, status, error
        case nodeId = "node_id"
        case filePath = "file_path"
        case fileIndex = "file_index"
        case fileTotal = "file_total"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationMs = "duration_ms"
        case filesProcessed = "files_processed"
        case artifactsCreated = "artifacts_created"
    }

    var isFileStep: Bool { type == "file" }
    var isNodeStep: Bool { type == nil }
}
