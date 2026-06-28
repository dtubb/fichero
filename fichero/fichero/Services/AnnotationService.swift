// swiftlint:disable file_length
import FicheroAPIClient
import Foundation
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

// swiftlint:disable type_body_length
/// Thin generated-client wrapper over the backend annotations API (`/api/annotations`, #1276).
///
/// Every method degrades gracefully: a network or decode failure sets `error`
/// and leaves `annotations` untouched (or returns `nil`) rather than throwing
/// into the view layer.
@MainActor
final class AnnotationService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "AnnotationService")

    @Published var annotations: [DocumentAnnotation] = []
    @Published var isLoading = false
    @Published var error: String?

    /// Active library path for the owning window. Prefer passing this into
    /// `init(libraryPath:)` so the transport is configured before any `load()`.
    /// It stays settable so a view can re-point the service when the window's
    /// library changes, but assignment no longer drives transport state via a
    /// fragile `didSet` — `syncLibraryPath()` reconciles the client immediately
    /// before each request, so a load can never run with a stale path (#1716).
    var libraryPath: String?

    private let client: FicheroClient
    private let decoder = JSONDecoder()

    init(ficheroClient: FicheroClient? = nil, libraryPath: String? = nil) {
        let resolvedClient = ficheroClient ?? FicheroClient(baseURL: EngineConfig.host, libraryPath: libraryPath)
        self.client = resolvedClient
        self.libraryPath = libraryPath ?? resolvedClient.currentLibraryPath
        client.currentLibraryPath = self.libraryPath
    }

    /// Reconcile the transport's library path with `libraryPath` right before a
    /// request. Removes the init-race + `didSet` seam: every call targets the
    /// owning window's library regardless of when `libraryPath` was assigned.
    private func syncLibraryPath() {
        if client.currentLibraryPath != libraryPath {
            client.currentLibraryPath = libraryPath
        }
    }

    private func annotation(from value: OpenAPIValueContainer) throws -> DocumentAnnotation {
        guard let object = value.value else { throw AnnotationServiceError.emptyContainer }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try decoder.decode(DocumentAnnotation.self, from: data)
    }

    private func annotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        // documentId is optional on the wire since #1759 (folder-scoped
        // annotations carry folder_id, not document_id). This per-document
        // converter only surfaces annotations bound to a document.
        guard let id = generated.id, let documentId = generated.documentId else { return nil }
        return DocumentAnnotation(
            id: id,
            documentId: documentId,
            pageId: generated.pageId,
            folderId: generated.folderId,
            pageLabel: generated.pageLabel,
            charStart: generated.charStart,
            charEnd: generated.charEnd,
            bbox: generated.bbox,
            kind: AnnotationKind(rawValue: generated.kind.rawValue) ?? .unknown,
            text: generated.text,
            rating: generated.rating,
            color: generated.color,
            tags: generated.tags ?? [],
            linkedClaimIds: generated.linkedClaimIds ?? [],
            linkedEntityIds: generated.linkedEntityIds ?? [],
            linkedNoteIds: generated.linkedNoteIds ?? [],
            createdBy: generated.createdBy,
            createdAt: generated.createdAt?.ISO8601Format(),
            updatedAt: generated.updatedAt?.ISO8601Format()
        )
    }

    private func folderAnnotation(from generated: Components.Schemas.Annotation) -> DocumentAnnotation? {
        guard let id = generated.id, let folderId = generated.folderId else { return nil }
        return DocumentAnnotation(
            id: id,
            documentId: generated.documentId,
            pageId: generated.pageId,
            folderId: folderId,
            pageLabel: generated.pageLabel,
            charStart: generated.charStart,
            charEnd: generated.charEnd,
            bbox: generated.bbox,
            kind: AnnotationKind(rawValue: generated.kind.rawValue) ?? .unknown,
            text: generated.text,
            rating: generated.rating,
            color: generated.color,
            tags: generated.tags ?? [],
            linkedClaimIds: generated.linkedClaimIds ?? [],
            linkedEntityIds: generated.linkedEntityIds ?? [],
            linkedNoteIds: generated.linkedNoteIds ?? [],
            createdBy: generated.createdBy,
            createdAt: generated.createdAt?.ISO8601Format(),
            updatedAt: generated.updatedAt?.ISO8601Format()
        )
    }

    // MARK: - List

    /// Load annotations for a document into `annotations`. Never throws — on failure
    /// `annotations` is cleared and `error` is set so the tab can show an empty state.
    func load(documentId: String) async {
        await load(query: .init(documentId: documentId))
    }

    func load(pageId: String) async {
        await load(query: .init(pageId: pageId))
    }

    func load(folderId: String) async {
        await load(query: .init(folderId: folderId))
    }

    private func load(
        query: Operations.ListAnnotationsApiAnnotationsGet.Input.Query
    ) async {
        syncLibraryPath()
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let response = try await client.api.listAnnotationsApiAnnotationsGet(.init(
                query: query
            ))
            guard case .ok(let okResponse) = response else {
                logger.warning("List annotations returned non-OK response")
                error = "Annotations unavailable"
                annotations = []
                return
            }
            let decoded = try okResponse.body.json
            // List items arrive as untyped containers (backend `items: list[Any]`);
            // DocumentAnnotation decodes them directly (carrying document/page/folder
            // ids). Scope is already enforced by the query above.
            annotations = decoded.items.compactMap { try? annotation(from: $0) }
        } catch {
            // Backend may not be wired yet during parallel development — degrade
            // to an empty list rather than crashing the inspector (#1276).
            logger.warning("Failed to load annotations: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load annotations"
            annotations = []
        }
    }

    // MARK: - Detail

    /// Fetch the latest server copy for one annotation and merge it into the list.
    @discardableResult
    func getAnnotation(id: String) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let response = try await client.api.getAnnotationApiAnnotationsAnnotationIdGet(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok(let okResponse) = response,
                  let annotation = annotation(from: try okResponse.body.json) else {
                error = "Could not load annotation"
                return nil
            }
            if let index = annotations.firstIndex(where: { $0.id == annotation.id }) {
                annotations[index] = annotation
            } else {
                annotations.insert(annotation, at: 0)
            }
            error = nil
            return annotation
        } catch {
            logger.warning("Failed to fetch annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load annotation"
            return nil
        }
    }

    // MARK: - Create

    /// Create a note annotation (`kind: note`) and prepend it to `annotations`.
    /// Returns the created annotation, or `nil` on failure (with `error` set).
    @discardableResult
    func addNote(
        scope: AnnotationScope,
        text: String,
        pageLabel: String? = nil,
        bbox: [Double]? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        kind: AnnotationKind = .note,
        color: String? = nil,
        tags: [String] = [],
        linkedClaimIds: [String] = []
    ) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let documentId: String?
            let pageId: String?
            let folderId: String?
            switch scope {
            case .document(let scopedDocumentId):
                documentId = scopedDocumentId
                pageId = nil
                folderId = nil
            case .page(let scopedPageId):
                documentId = nil
                pageId = scopedPageId
                folderId = nil
            case .folder(let scopedFolderId):
                documentId = nil
                pageId = nil
                folderId = scopedFolderId
            }
            let request = Components.Schemas.AnnotationCreateRequest(
                documentId: documentId,
                pageId: pageId,
                folderId: folderId,
                kind: Components.Schemas.AnnotationKind(rawValue: (kind == .unknown ? AnnotationKind.note : kind).rawValue) ?? .note,
                pageLabel: pageLabel,
                charStart: charStart,
                charEnd: charEnd,
                bbox: bbox,
                text: text.isEmpty ? nil : text,
                color: color,
                tags: tags,
                linkedClaimIds: linkedClaimIds.isEmpty ? nil : linkedClaimIds
            )
            let response = try await client.api.createAnnotationApiAnnotationsPost(.init(
                body: .json(request)
            ))
            guard case .ok(let okResponse) = response,
                  let created = createdAnnotation(from: try okResponse.body.json, scope: scope) else {
                error = "Could not save annotation"
                return nil
            }
            annotations.insert(created, at: 0)
            error = nil
            return created
        } catch {
            logger.warning("Failed to create annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not save annotation"
            return nil
        }
    }

    private func createdAnnotation(
        from generated: Components.Schemas.Annotation,
        scope: AnnotationScope
    ) -> DocumentAnnotation? {
        switch scope {
        case .folder:
            return folderAnnotation(from: generated)
        case .document, .page:
            return annotation(from: generated)
        }
    }

    // MARK: - Update

    /// Patch an annotation's note text (and optionally its color/tags). Updates the
    /// in-memory copy on success. Returns `nil` on failure.
    @discardableResult
    func updateText(id: String, text: String) async -> DocumentAnnotation? {
        syncLibraryPath()
        do {
            let response = try await client.api.patchAnnotationApiAnnotationsAnnotationIdPatch(.init(
                path: .init(annotationId: id),
                body: .json(.init(text: text))
            ))
            guard case .ok(let okResponse) = response,
                  let updated = annotation(from: try okResponse.body.json) else {
                error = "Could not update annotation"
                return nil
            }
            if let idx = annotations.firstIndex(where: { $0.id == id }) {
                annotations[idx] = updated
            }
            error = nil
            return updated
        } catch {
            logger.warning("Failed to update annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not update annotation"
            return nil
        }
    }

    // MARK: - Crop

    /// Fetch cropped text/image bytes for an annotation's source span or region.
    @discardableResult
    func cropAnnotation(id: String) async -> Data? {
        syncLibraryPath()
        do {
            let response = try await client.api.getCropApiAnnotationsAnnotationIdCropGet(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok(let okResponse) = response else {
                error = "Could not crop annotation"
                return nil
            }
            guard let value = try okResponse.body.json.value else {
                error = "Could not crop annotation"
                return nil
            }
            error = nil
            if let string = value as? String {
                return string.data(using: .utf8)
            }
            return try JSONSerialization.data(withJSONObject: value)
        } catch {
            logger.warning("Failed to crop annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not crop annotation"
            return nil
        }
    }

    // MARK: - Promote

    /// Promote a highlight/note annotation into a KnowledgeClaim.
    @discardableResult
    func promoteToClaim(id: String) async -> Bool {
        syncLibraryPath()
        do {
            let response = try await client.api.promoteToClaimApiAnnotationsAnnotationIdPromoteToClaimPost(.init(
                path: .init(annotationId: id),
            ))
            guard case .ok = response else {
                error = "Could not promote annotation"
                return false
            }
            error = nil
            return true
        } catch {
            logger.warning("Failed to promote annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not promote annotation"
            return false
        }
    }

    // MARK: - Delete

    /// Delete an annotation and remove it from `annotations`. Returns `true` on success.
    @discardableResult
    func delete(id: String) async -> Bool {
        syncLibraryPath()
        do {
            let response = try await client.api.deleteAnnotationApiAnnotationsAnnotationIdDelete(.init(
                path: .init(annotationId: id),
            ))
            guard case .noContent = response else {
                error = "Could not delete annotation"
                return false
            }
            annotations.removeAll { $0.id == id }
            error = nil
            return true
        } catch {
            logger.warning("Failed to delete annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not delete annotation"
            return false
        }
    }

    // MARK: - Search

    static func matchesSearch(_ annotation: DocumentAnnotation, query: String) -> Bool {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return true }
        let needle = trimmed.lowercased()

        if annotation.text?.lowercased().contains(needle) == true { return true }
        if annotation.pageLabel?.lowercased().contains(needle) == true { return true }
        if annotation.kind.label.lowercased().contains(needle) { return true }
        if annotation.tags.contains(where: { $0.lowercased().contains(needle) }) { return true }
        if annotation.linkedClaimIds.contains(where: { $0.lowercased().contains(needle) }) { return true }
        return false
    }
}
// swiftlint:enable type_body_length

enum AnnotationServiceError: LocalizedError {
    case emptyContainer

    var errorDescription: String? {
        switch self {
        case .emptyContainer:
            return "Annotation response was empty"
        }
    }
}
