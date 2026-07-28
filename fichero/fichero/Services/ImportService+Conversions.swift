import FicheroAPIClient
import Foundation

// Generated-schema → domain conversions, split out of ImportService.swift so the
// class body stays inside `type_body_length` (#4208). These four functions are
// PURE: they touch no instance state — no `client`, no `logger`, no `self` — which
// is why they can live in another file at all. Keep it that way; a conversion that
// starts reading instance state belongs back in the primary declaration, not here
// behind a widened access level.
extension ImportService {

    func convertToDocument(_ generated: Components.Schemas.Document) throws -> Document {
        // Same typed-first / extras-fallback pattern as
        // DocumentService.convertToDocument — typed schema fields
        // decode into typed properties, NOT additionalProperties. Reading
        // typed fields only from extras silently returns nil and corrupts
        // the local cache (#762, #774, audit on 2026-05-03).
        let extras = generated.additionalProperties.value
        let parentId = generated.parentId ?? (extras["parent_id"] as? String)
        let fileType = generated.fileType?.rawValue ?? (extras["file_type"] as? String)
        let sortOrder = extras["sort_order"] as? Int ?? 0

        return Document(
            id: generated.id ?? UUID().uuidString,
            parentId: parentId,
            docType: convertFromGeneratedDocType(generated.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: generated.name,
            path: generated.path ?? (extras["path"] as? String),
            sequence: generated.sequence ?? (extras["sequence"] as? Int),
            bbox: (generated.bbox?.value as? [Int]) ?? (extras["bbox"] as? [Int]),
            status: convertFromGeneratedStatus(generated.status),
            metadata: convertMetadata(generated.metadata),
            pageContent: generated.pageContent ?? (extras["page_content"] as? String),
            excludeFromProcessing: generated.excludeFromProcessing ?? false,
            sortOrder: sortOrder,
            createdAt: generated.createdAt ?? Date(),
            updatedAt: generated.updatedAt ?? Date(),
            expectedThumbnailPath: generated.expectedThumbnailPath,
            expectedDisplayPath: generated.expectedDisplayPath
        )
    }

    private func convertFromGeneratedDocType(_ docType: Components.Schemas.DocType?) -> DocType {
        guard let docType = docType else { return .file }
        switch docType {
        case .folder: return .folder
        case .group: return .group
        case .file: return .file
        case .page: return .page
        case .chunk: return .chunk
        }
    }

    private func convertFromGeneratedStatus(_ status: Components.Schemas.Status?) -> Status {
        guard let status = status else { return .pending }
        switch status {
        case .pending: return .pending
        case .processing: return .processing
        case .active: return .processing  // active is an in-progress state
        case .completed: return .completed
        case .failed: return .failed
        }
    }

    private func convertMetadata(_ metadata: Components.Schemas.Document.MetadataPayload?) -> [String: AnyCodable] {
        guard let metadata = metadata else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in metadata.additionalProperties.value {
            result[key] = AnyCodable(value ?? "")
        }
        return result
    }
}

// MARK: - Ingest Task Types

/// Represents an async ingest task
struct IngestTask: Identifiable {
    let taskId: String
    let status: String
    let path: String

    var id: String { taskId }
}

/// One file the import could not take, surfaced rather than swallowed (#4203).
struct IngestFailure: Identifiable, Equatable {
    let path: String
    let error: String
    let documentId: String?

    /// The failed stub's document id when the engine made one, else the path —
    /// two files can't share a path within one import.
    var id: String { documentId ?? path }
}

/// Status of an ingest task
///
/// `Equatable` is load-bearing, not decoration: the poll loop republishes this
/// twice a second for the whole import, and observers must invalidate only when
/// a number actually MOVED. Otherwise every progress surface re-renders 2×/sec
/// for the duration — the no-wholesale-re-render rule, applied to a struct
/// instead of a list (#4203).
struct IngestTaskStatus: Equatable {
    let taskId: String
    let status: String
    let path: String
    let progress: Double?
    let total: Int?
    let processed: Int?
    let error: String?
    let documentIds: [String]
    let failed: Int
    let failures: [IngestFailure]
    /// Throughput the engine measured; 0 until the first file lands.
    let filesPerSecond: Double

    /// The walk hasn't finished counting yet, so `processed / total` would read
    /// "0 of 0" — the moment the user currently sees nothing at all (#4203).
    var isScanning: Bool { (total ?? 0) == 0 }

    /// Cancellation requested and not yet settled.
    var isCancelling: Bool { status == "cancelling" }

    /// Terminal, whatever the outcome — polling stops here.
    var isFinished: Bool { ["completed", "failed", "cancelled"].contains(status) }

    /// Seconds of work left at the measured rate, or nil while scanning, while
    /// the rate is still unknown, or once there's nothing left to do.
    var estimatedSecondsRemaining: Double? {
        guard !isScanning, filesPerSecond > 0,
              let total, let processed, total > processed else { return nil }
        return Double(total - processed) / filesPerSecond
    }
}

// MARK: - Error Types

enum ImportServiceError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)
    case taskFailed(String)
    case timeout

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from import service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        case .taskFailed(let message):
            return "Import task failed: \(message)"
        case .timeout:
            return "Import task timed out"
        }
    }
}
