import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

// MARK: - Note model

typealias NoteItem = Components.Schemas.Note

extension Components.Schemas.Note: @retroactive Identifiable {}

struct NoteListResponse: Codable {
    let items: [NoteItem]
    let count: Int
}

/// A note's relations (#1433): notes that link to it (`backlinks`) and notes it
/// links to (`forward`). Tinderbox-style bidirectional linking.
struct NoteLinks: Equatable {
    let backlinks: [NoteItem]
    let forward: [NoteItem]

    static let empty = NoteLinks(backlinks: [], forward: [])
    var isEmpty: Bool { backlinks.isEmpty && forward.isEmpty }
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

enum NoteScope: Equatable {
    case linkedDocument(String)
    case page(String)
    case folder(String)
}

// MARK: - Service

@MainActor
@Observable
final class NoteService {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "NoteService")

    var notes: [NoteItem] = []
    var isLoading = false
    var error: String?

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
        let resolvedClient = ficheroClient ?? FicheroClient(
            baseURL: EngineConfig.host,
            libraryPath: libraryPath,
            transportMode: EngineConfig.transportMode
        )
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

    private func note(from value: OpenAPIValueContainer) throws -> NoteItem {
        guard let object = value.value else { throw NoteServiceError.emptyContainer }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try note(from: decoder.decode(NoteItem.self, from: data))
    }

    private func note(from generated: Components.Schemas.Note) throws -> NoteItem {
        guard generated.id != nil else { throw NoteServiceError.missingId }
        return generated
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
            let response = try await client.api.listNotesApiNotesGet(.init(query: query))
            guard case .ok(let okResponse) = response else {
                notes = []
                self.error = "Notes unavailable"
                return
            }
            notes = try okResponse.body.json.items.map { try note(from: $0) }
        } catch {
            if error.isCancellationError { return }   // superseded — not a failure (defer clears isLoading)
            self.error = error.localizedDescription
            logger.error("load notes failed: \(error.localizedDescription)")
        }
    }

    func load(linkedDocumentId: String) async {
        await load(query: .init(linkedDocumentId: linkedDocumentId))
    }

    func load(pageId: String) async {
        await load(query: .init(pageId: pageId))
    }

    func load(folderId: String) async {
        await load(query: .init(folderId: folderId))
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
        let note = try await create(body: body, scope: .linkedDocument(linkedDocumentId))
        notes.insert(note, at: 0)
        return note
    }

    func create(body: String, pageId: String) async throws -> NoteItem {
        let note = try await create(body: body, scope: .page(pageId))
        notes.insert(note, at: 0)
        return note
    }

    func create(body: String, folderId: String) async throws -> NoteItem {
        let note = try await create(body: body, scope: .folder(folderId))
        notes.insert(note, at: 0)
        return note
    }

    private func create(
        body: String,
        kind: String? = nil,
        linkedEntityIds: [String]? = nil,
        linkedDocumentIds: [String]? = nil,
        scope: NoteScope? = nil
    ) async throws -> NoteItem {
        syncLibraryPath()
        let resolvedLinkedDocumentIds: [String]?
        let pageId: String?
        let folderId: String?
        switch scope {
        case .linkedDocument(let documentId):
            resolvedLinkedDocumentIds = [documentId]
            pageId = nil
            folderId = nil
        case .page(let scopedPageId):
            resolvedLinkedDocumentIds = nil
            pageId = scopedPageId
            folderId = nil
        case .folder(let scopedFolderId):
            resolvedLinkedDocumentIds = nil
            pageId = nil
            folderId = scopedFolderId
        case nil:
            resolvedLinkedDocumentIds = linkedDocumentIds
            pageId = nil
            folderId = nil
        }
        let payload = Components.Schemas.FicheroServerApiRoutesDocumentNotesNoteCreateRequest(
            body: body,
            kind: noteKind(kind),
            linkedEntityIds: linkedEntityIds,
            linkedDocumentIds: resolvedLinkedDocumentIds,
            pageId: pageId,
            folderId: folderId
        )
        let response = try await client.api.createNoteApiNotesPost(.init(
            body: .json(payload)
        ))
        guard case .ok(let okResponse) = response else { throw NoteServiceError.unexpectedResponse }
        return try note(from: try okResponse.body.json)
    }

    func update(noteId: String, body: String) async throws -> NoteItem {
        syncLibraryPath()
        let response = try await client.api.patchNoteApiNotesNoteIdPatch(.init(
            path: .init(noteId: noteId),
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
        ))
        guard case .noContent = response else { throw NoteServiceError.unexpectedResponse }
        notes.removeAll { $0.id == noteId }
    }

    // MARK: - Links (#1433 — Tinderbox-style note↔note relations)

    /// Notes that link TO this note (its backlinks).
    func backlinks(noteId: String) async throws -> [NoteItem] {
        syncLibraryPath()
        let response = try await client.api.backlinksApiNotesNoteIdBacklinksGet(.init(
            path: .init(noteId: noteId)
        ))
        guard case .ok(let okResponse) = response else { throw NoteServiceError.unexpectedResponse }
        return try okResponse.body.json.items.map { try note(from: $0) }
    }

    /// Notes that this note links TO (its forward links).
    func forwardLinks(noteId: String) async throws -> [NoteItem] {
        syncLibraryPath()
        let response = try await client.api.forwardLinksApiNotesNoteIdForwardLinksGet(.init(
            path: .init(noteId: noteId)
        ))
        guard case .ok(let okResponse) = response else { throw NoteServiceError.unexpectedResponse }
        return try okResponse.body.json.items.map { try note(from: $0) }
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
