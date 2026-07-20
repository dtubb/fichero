import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

// MARK: - Models

/// User annotation kinds. Mirrors the backend `AnnotationKind` enum (#914) so the
/// SwiftUI layer can decode `kind` directly. `unknown` is a forward-compatibility
/// fallback: if the backend introduces a new kind before the app knows about it,
/// decoding still succeeds instead of crashing the whole list (#1276 graceful
/// degradation requirement).
enum AnnotationKind: String, Codable, CaseIterable, Identifiable {
    case highlight
    case note
    case rating
    case bookmark
    case comment
    case unknown

    var id: String { rawValue }

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = AnnotationKind(rawValue: raw) ?? .unknown
    }

    /// SF Symbol used to badge each annotation row.
    var icon: String {
        switch self {
        case .highlight: return "highlighter"
        case .note: return "note.text"
        case .rating: return "star"
        case .bookmark: return "bookmark"
        case .comment: return "bubble.left"
        case .unknown: return "questionmark.circle"
        }
    }

    var label: String {
        switch self {
        case .unknown: return "Annotation"
        default: return rawValue.capitalized
        }
    }
}

/// A user-authored annotation on a document, text span, or image region (#914 / #1276).
///
/// Anchored to a `Document` via `documentId`, optionally refined by a text span
/// (`charStart`/`charEnd`) and/or an image/PDF region (`bbox` = `[x, y, width, height]`
/// in source coordinates). Decoded from the backend `Annotation` schema. Every field
/// beyond `id` / `documentId` / `kind` is treated as optional so a not-yet-wired
/// backend field never breaks decoding.
struct DocumentAnnotation: Codable, Identifiable, Hashable {
    let id: String
    let documentId: String?
    let pageId: String?
    let folderId: String?
    var pageIndex: Int?
    var pageLabel: String?
    var charStart: Int?
    var charEnd: Int?
    var bbox: [Double]?
    var kind: AnnotationKind
    var text: String?
    var rating: Int?
    var color: String?
    var tags: [String]
    var linkedClaimIds: [String]
    var linkedEntityIds: [String]
    var linkedNoteIds: [String]
    var createdBy: String?
    var createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case documentId = "document_id"
        case pageId = "page_id"
        case folderId = "folder_id"
        case pageIndex = "page_index"
        case pageLabel = "page_label"
        case charStart = "char_start"
        case charEnd = "char_end"
        case bbox
        case kind
        case text
        case rating
        case color
        case tags
        case linkedClaimIds = "linked_claim_ids"
        case linkedEntityIds = "linked_entity_ids"
        case linkedNoteIds = "linked_note_ids"
        case createdBy = "created_by"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        documentId = try container.decodeIfPresent(String.self, forKey: .documentId)
        pageId = try container.decodeIfPresent(String.self, forKey: .pageId)
        folderId = try container.decodeIfPresent(String.self, forKey: .folderId)
        pageIndex = try container.decodeIfPresent(Int.self, forKey: .pageIndex)
        pageLabel = try container.decodeIfPresent(String.self, forKey: .pageLabel)
        charStart = try container.decodeIfPresent(Int.self, forKey: .charStart)
        charEnd = try container.decodeIfPresent(Int.self, forKey: .charEnd)
        bbox = try container.decodeIfPresent([Double].self, forKey: .bbox)
        kind = try container.decodeIfPresent(AnnotationKind.self, forKey: .kind) ?? .unknown
        text = try container.decodeIfPresent(String.self, forKey: .text)
        rating = try container.decodeIfPresent(Int.self, forKey: .rating)
        color = try container.decodeIfPresent(String.self, forKey: .color)
        tags = try container.decodeIfPresent([String].self, forKey: .tags) ?? []
        linkedClaimIds = try container.decodeIfPresent([String].self, forKey: .linkedClaimIds) ?? []
        linkedEntityIds = try container.decodeIfPresent([String].self, forKey: .linkedEntityIds) ?? []
        linkedNoteIds = try container.decodeIfPresent([String].self, forKey: .linkedNoteIds) ?? []
        createdBy = try container.decodeIfPresent(String.self, forKey: .createdBy)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
    }

    /// True when the annotation carries an image/PDF region (`[x, y, width, height]`).
    var hasRegion: Bool { (bbox?.count ?? 0) >= 4 }

    /// True when the annotation carries a text span.
    var hasSpan: Bool { charStart != nil && charEnd != nil }

    var isFolderScoped: Bool { folderId != nil }

    var canRevealSource: Bool { documentId != nil }

    /// Convenience initializer for tests and local construction.
    init(
        id: String,
        documentId: String? = nil,
        pageId: String? = nil,
        folderId: String? = nil,
        pageIndex: Int? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        bbox: [Double]? = nil,
        kind: AnnotationKind = .note,
        text: String? = nil,
        rating: Int? = nil,
        color: String? = nil,
        tags: [String] = [],
        linkedClaimIds: [String] = [],
        linkedEntityIds: [String] = [],
        linkedNoteIds: [String] = [],
        createdBy: String? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil
    ) {
        self.id = id
        self.documentId = documentId
        self.pageId = pageId
        self.folderId = folderId
        self.pageIndex = pageIndex
        self.pageLabel = pageLabel
        self.charStart = charStart
        self.charEnd = charEnd
        self.bbox = bbox
        self.kind = kind
        self.text = text
        self.rating = rating
        self.color = color
        self.tags = tags
        self.linkedClaimIds = linkedClaimIds
        self.linkedEntityIds = linkedEntityIds
        self.linkedNoteIds = linkedNoteIds
        self.createdBy = createdBy
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

enum AnnotationScope: Equatable {
    case document(String)
    case page(String)
    case folder(String)
}

/// Envelope returned by `GET /api/annotations` (#1276). The backend declares
/// `items: list[Any]`, so the OpenAPI generator can only emit an untyped array —
/// decoding it here against the concrete `Annotation` model is what gives the UI
/// typed rows.
private struct AnnotationListResponse: Decodable {
    let items: [DocumentAnnotation]
    let count: Int
}

// MARK: - Service

/// Thin generated-client wrapper over the backend annotations API (`/api/annotations`, #1276).
///
/// Every method degrades gracefully: a network or decode failure sets `error`
/// and leaves `annotations` untouched (or returns `nil`) rather than throwing
/// into the view layer.
@MainActor
@Observable
final class AnnotationService {
    let logger = Logger(subsystem: "app.fichero.fichero", category: "AnnotationService")

    var annotations: [DocumentAnnotation] = []
    var isLoading = false
    var error: String?

    /// Active library path for the owning window. Prefer passing this into
    /// `init(libraryPath:)` so the transport is configured before any `load()`.
    /// It stays settable so a view can re-point the service when the window's
    /// library changes, but assignment no longer drives transport state via a
    /// fragile `didSet` — `syncLibraryPath()` reconciles the client immediately
    /// before each request, so a load can never run with a stale path (#1716).
    var libraryPath: String?

    let client: FicheroClient
    let decoder = JSONDecoder()

    init(ficheroClient: FicheroClient? = nil, libraryPath: String? = nil) {
        let resolvedClient = ficheroClient ?? FicheroClient(baseURL: EngineConfig.host, libraryPath: libraryPath)
        self.client = resolvedClient
        self.libraryPath = libraryPath ?? resolvedClient.currentLibraryPath
        client.currentLibraryPath = self.libraryPath
    }

    /// Reconcile the transport's library path with `libraryPath` right before a
    /// request. Removes the init-race + `didSet` seam: every call targets the
    /// owning window's library regardless of when `libraryPath` was assigned.
    func syncLibraryPath() {
        if client.currentLibraryPath != libraryPath {
            client.currentLibraryPath = libraryPath
        }
    }
}

enum AnnotationServiceError: LocalizedError {
    case emptyContainer

    var errorDescription: String? {
        switch self {
        case .emptyContainer:
            return "Annotation response was empty"
        }
    }
}
