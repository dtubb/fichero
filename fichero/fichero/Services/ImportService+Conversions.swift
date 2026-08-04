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
        // The SECOND wire→model converter (the diagnosis called
        // `DocumentService`'s the only one). It carried the identical defect:
        // typed schema keys read out of `additionalProperties`, where the
        // generated decoder guarantees they never are — so `sort_order` was
        // always 0 and every freshly-imported row lost its position, its
        // child count, and its prototype/alias/read-only identity until some
        // later refresh replaced it. Fixed the same way, in the same commit,
        // because one of two identical converters being right is how the class
        // comes back (#4514/#4515/#4516).
        let fileType = generated.fileType?.rawValue

        return Document(
            id: generated.id ?? UUID().uuidString,
            parentId: generated.parentId,
            docType: convertFromGeneratedDocType(generated.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: generated.name,
            path: generated.path,
            sequence: generated.sequence,
            bbox: generated.bbox?.value as? [Int],
            status: convertFromGeneratedStatus(generated.status),
            metadata: convertMetadata(generated.metadata),
            pageContent: generated.pageContent,
            excludeFromProcessing: generated.excludeFromProcessing ?? false,
            isWorkspace: generated.isWorkspace ?? false,
            childCount: generated.childCount ?? 0,
            sortOrder: generated.sortOrder ?? 0,
            prototypeKey: generated.prototypeKey,
            nodeKind: generated.nodeKind,
            aliasTargetId: generated.aliasTargetId,
            attributes: convertAttributes(generated.attributes),
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

    /// Prototype-scoped node attributes (`read_only`, `scope`, `system`, …) —
    /// see `Document.isReadOnly`. A distinct generated payload type from
    /// `MetadataPayload`, so the two cannot share one function.
    private func convertAttributes(
        _ attributes: Components.Schemas.Document.AttributesPayload?
    ) -> [String: AnyCodable] {
        guard let attributes = attributes else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in attributes.additionalProperties.value {
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
