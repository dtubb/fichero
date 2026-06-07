import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

// MARK: - Note model

typealias NoteItem = Components.Schemas.Note

extension Components.Schemas.Note: Identifiable {}

struct NoteListResponse: Codable {
    let items: [NoteItem]
    let count: Int
}

struct NoteCreateBody: Encodable {
    let title: String?
    let body: String
    let linkedDocumentIds: [String]

    enum CodingKeys: String, CodingKey {
        case title, body
        case linkedDocumentIds = "linked_document_ids"
    }
}

/// Create body for an entity-linked note (#1501). `kind` defaults to
/// `reference` for entity bio/summary notes.
struct NoteCreateEntityBody: Encodable {
    let title: String?
    let body: String
    let kind: String
    let linkedEntityIds: [String]

    enum CodingKeys: String, CodingKey {
        case title, body, kind
        case linkedEntityIds = "linked_entity_ids"
    }
}

struct NotePatchBody: Encodable {
    let body: String
}

/// Create body for a free-floating note (no links) — used by the standalone
/// notes browser (#1500).
struct NoteCreateFreeBody: Encodable {
    let title: String?
    let body: String
    let kind: String
}

// MARK: - Service

@MainActor
final class NoteService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "NoteService")

    @Published var notes: [NoteItem] = []
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

    init(ficheroClient: FicheroClient = FicheroClient(), libraryPath: String? = nil) {
        self.client = ficheroClient
        self.libraryPath = libraryPath ?? ficheroClient.currentLibraryPath
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

    private var headers: Operations.ListNotesApiNotesGet.Input.Headers {
        .init(xFicheroLibraryPath: libraryPath ?? "")
    }

    private func note(from value: OpenAPIValueContainer) throws -> NoteItem {
        guard let object = value.value else { throw NoteServiceError.emptyContainer }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try note(from: decoder.decode(NoteItem.self, from: data))
    }

    private func note(from generated: Components.Schemas.Note) throws -> NoteItem {
        guard let id = generated.id else { throw NoteServiceError.missingId }
        return NoteItem(
            id: id,
            title: generated.title,
            body: generated.body ?? "",
            kind: generated.kind ?? .zettel,
            tags: generated.tags ?? [],
            linkedNoteIds: generated.linkedNoteIds ?? [],
            linkedEntityIds: generated.linkedEntityIds ?? [],
            linkedClaimIds: generated.linkedClaimIds ?? [],
            linkedDocumentIds: generated.linkedDocumentIds ?? [],
            linkedStructureNodeId: generated.linkedStructureNodeId,
            address: generated.address,
            parentAddress: generated.parentAddress,
            authorType: generated.authorType,
            createdBy: generated.createdBy,
            createdAt: generated.createdAt,
            updatedAt: generated.updatedAt,
            additionalProperties: generated.additionalProperties
        )
    }

    private func noteKind(_ kind: String?) -> Components.Schemas.NoteKind? {
        guard let kind, !kind.isEmpty else { return nil }
        return Components.Schemas.NoteKind(rawValue: kind)
    }

    private func load(query: Operations.ListNotesApiNotesGet.Input.Query) async {
        syncLibraryPath()
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            let response = try await client.api.listNotesApiNotesGet(.init(query: query, headers: headers))
            guard case .ok(let okResponse) = response else {
                notes = []
                self.error = "Notes unavailable"
                return
            }
            notes = try okResponse.body.json.items.map { try note(from: $0) }
        } catch {
            self.error = error.localizedDescription
            logger.error("load notes failed: \(error.localizedDescription)")
        }
    }

    func load(linkedDocumentId: String) async {
        await load(query: .init(linkedDocumentId: linkedDocumentId))
    }

    /// Load all notes, optionally filtered by kind / tag / linked entity /
    /// full-text query. Powers the standalone notes browser (#1500).
    func loadAll(
        kind: String? = nil,
        tag: String? = nil,
        linkedEntityId: String? = nil,
        query: String? = nil
    ) async {
        await load(query: .init(
            kind: noteKind(kind),
            tag: tag?.isEmpty == false ? tag : nil,
            linkedEntityId: linkedEntityId?.isEmpty == false ? linkedEntityId : nil,
            q: query?.isEmpty == false ? query : nil
        ))
    }

    /// Create a free-floating note with no links (#1500).
    func createFree(body: String, kind: String) async throws -> NoteItem {
        let note = try await create(body: body, kind: kind)
        notes.insert(note, at: 0)
        return note
    }

    /// Load notes linked to a KG entity (#1501).
    func load(linkedEntityId: String) async {
        await load(query: .init(linkedEntityId: linkedEntityId))
    }

    /// Create a note linked to a KG entity. Defaults to `kind=reference`
    /// (entity bio/summary). (#1501)
    func create(body: String, linkedEntityId: String, kind: String = "reference") async throws -> NoteItem {
        let note = try await create(body: body, kind: kind, linkedEntityIds: [linkedEntityId])
        notes.insert(note, at: 0)
        return note
    }

    func create(body: String, linkedDocumentId: String) async throws -> NoteItem {
        let note = try await create(body: body, linkedDocumentIds: [linkedDocumentId])
        notes.insert(note, at: 0)
        return note
    }

    private func create(
        body: String,
        kind: String? = nil,
        linkedEntityIds: [String]? = nil,
        linkedDocumentIds: [String]? = nil
    ) async throws -> NoteItem {
        syncLibraryPath()
        let payload = Components.Schemas.FicheroApiRoutesNotesNoteCreateRequest(
            body: body,
            kind: noteKind(kind),
            linkedEntityIds: linkedEntityIds,
            linkedDocumentIds: linkedDocumentIds
        )
        let response = try await client.api.createNoteApiNotesPost(.init(
            headers: .init(xFicheroLibraryPath: libraryPath ?? ""),
            body: .json(payload)
        ))
        guard case .ok(let okResponse) = response else { throw NoteServiceError.unexpectedResponse }
        return try note(from: try okResponse.body.json)
    }

    func update(noteId: String, body: String) async throws -> NoteItem {
        syncLibraryPath()
        let response = try await client.api.patchNoteApiNotesNoteIdPatch(.init(
            path: .init(noteId: noteId),
            headers: .init(xFicheroLibraryPath: libraryPath ?? ""),
            body: .json(.init(body: body))
        ))
        guard case .ok(let okResponse) = response else { throw NoteServiceError.unexpectedResponse }
        let updated = try note(from: try okResponse.body.json)
        if let idx = notes.firstIndex(where: { $0.id == noteId }) {
            notes[idx] = updated
        }
        return updated
    }

    func delete(noteId: String) async throws {
        syncLibraryPath()
        let response = try await client.api.deleteNoteApiNotesNoteIdDelete(.init(
            path: .init(noteId: noteId),
            headers: .init(xFicheroLibraryPath: libraryPath ?? "")
        ))
        guard case .noContent = response else { throw NoteServiceError.unexpectedResponse }
        notes.removeAll { $0.id == noteId }
    }
}

enum NoteServiceError: LocalizedError {
    case invalidURL
    case emptyContainer
    case missingId
    case unexpectedResponse

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid URL"
        case .emptyContainer: return "Note response was empty"
        case .missingId: return "Note response was missing an id"
        case .unexpectedResponse: return "Unexpected note response"
        }
    }
}
