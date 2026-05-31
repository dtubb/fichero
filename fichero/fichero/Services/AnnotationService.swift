import Foundation
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
    let documentId: String
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
        documentId = try container.decode(String.self, forKey: .documentId)
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

    /// Convenience initializer for tests and local construction.
    init(
        id: String,
        documentId: String,
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

/// Envelope returned by `GET /api/annotations` (#1276). The backend declares
/// `items: list[Any]`, so the OpenAPI generator can only emit an untyped array —
/// decoding it here against the concrete `Annotation` model is what gives the UI
/// typed rows.
private struct AnnotationListResponse: Decodable {
    let items: [DocumentAnnotation]
    let count: Int
}

// MARK: - Service

/// Thin wrapper over the backend annotations API (`/api/annotations`, #1276),
/// modelled on `ActionsService`. Hand-written rather than generated because the
/// list envelope is untyped on the wire (see `AnnotationListResponse`).
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

    private let baseURL = "http://localhost:8765/api/annotations"
    private let session = URLSession.shared

    private func decoder() -> JSONDecoder { JSONDecoder() }

    private func authedGet(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.addEngineAuth()
        return request
    }

    private func authedRequest(_ url: URL, method: String, body: Data? = nil) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.addEngineAuth()
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        return request
    }

    // MARK: - List

    /// Load annotations for a document into `annotations`. Never throws — on failure
    /// `annotations` is cleared and `error` is set so the tab can show an empty state.
    func load(documentId: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        guard var components = URLComponents(string: baseURL) else {
            error = "Invalid annotations URL"
            return
        }
        components.queryItems = [URLQueryItem(name: "document_id", value: documentId)]
        guard let url = components.url else {
            error = "Invalid annotations URL"
            return
        }

        do {
            let (data, response) = try await session.data(for: authedGet(url))
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                logger.warning("List annotations returned status \(code, privacy: .public)")
                error = "Annotations unavailable (HTTP \(code))"
                annotations = []
                return
            }
            let decoded = try decoder().decode(AnnotationListResponse.self, from: data)
            annotations = decoded.items
        } catch {
            // Backend may not be wired yet during parallel development — degrade
            // to an empty list rather than crashing the inspector (#1276).
            logger.warning("Failed to load annotations: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load annotations"
            annotations = []
        }
    }

    // MARK: - Create

    /// Create a note annotation (`kind: note`) and prepend it to `annotations`.
    /// Returns the created annotation, or `nil` on failure (with `error` set).
    @discardableResult
    func addNote(
        documentId: String,
        text: String,
        pageLabel: String? = nil,
        bbox: [Double]? = nil,
        kind: AnnotationKind = .note,
        color: String? = nil,
        tags: [String] = [],
        linkedClaimIds: [String] = []
    ) async -> DocumentAnnotation? {
        guard let url = URL(string: baseURL) else {
            error = "Invalid annotations URL"
            return nil
        }

        var payload: [String: Any] = [
            "document_id": documentId,
            "kind": (kind == .unknown ? AnnotationKind.note : kind).rawValue,
            "tags": tags
        ]
        if !text.isEmpty { payload["text"] = text }
        if let pageLabel { payload["page_label"] = pageLabel }
        if let bbox { payload["bbox"] = bbox }
        if let color { payload["color"] = color }
        if !linkedClaimIds.isEmpty { payload["linked_claim_ids"] = linkedClaimIds }

        do {
            let body = try JSONSerialization.data(withJSONObject: payload)
            let (data, response) = try await session.data(for: authedRequest(url, method: "POST", body: body))
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                error = "Could not save annotation (HTTP \(code))"
                return nil
            }
            let created = try decoder().decode(DocumentAnnotation.self, from: data)
            annotations.insert(created, at: 0)
            error = nil
            return created
        } catch {
            logger.warning("Failed to create annotation: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not save annotation"
            return nil
        }
    }

    // MARK: - Update

    /// Patch an annotation's note text (and optionally its color/tags). Updates the
    /// in-memory copy on success. Returns `nil` on failure.
    @discardableResult
    func updateText(id: String, text: String) async -> DocumentAnnotation? {
        guard let url = URL(string: "\(baseURL)/\(id)") else {
            error = "Invalid annotations URL"
            return nil
        }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["text": text])
            let (data, response) = try await session.data(for: authedRequest(url, method: "PATCH", body: body))
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                error = "Could not update annotation (HTTP \(code))"
                return nil
            }
            let updated = try decoder().decode(DocumentAnnotation.self, from: data)
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

    // MARK: - Delete

    /// Delete an annotation and remove it from `annotations`. Returns `true` on success.
    @discardableResult
    func delete(id: String) async -> Bool {
        guard let url = URL(string: "\(baseURL)/\(id)") else {
            error = "Invalid annotations URL"
            return false
        }
        do {
            let (_, response) = try await session.data(for: authedRequest(url, method: "DELETE"))
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                let code = (response as? HTTPURLResponse)?.statusCode ?? -1
                error = "Could not delete annotation (HTTP \(code))"
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
