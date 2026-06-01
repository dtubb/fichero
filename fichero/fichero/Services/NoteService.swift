import Foundation
import OSLog

// MARK: - Note model

struct NoteItem: Codable, Identifiable {
    let id: String
    let title: String?
    let body: String
    let kind: String
    let tags: [String]
    let linkedDocumentIds: [String]
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, title, body, kind, tags
        case linkedDocumentIds = "linked_document_ids"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

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

struct NotePatchBody: Encodable {
    let body: String
}

// MARK: - Service

@MainActor
final class NoteService: ObservableObject {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "NoteService")
    private let base = "http://127.0.0.1:8765/api/notes"

    @Published var notes: [NoteItem] = []
    @Published var isLoading = false
    @Published var error: String?

    func load(linkedDocumentId: String) async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            guard var comps = URLComponents(string: base) else { return }
            comps.queryItems = [URLQueryItem(name: "linked_document_id", value: linkedDocumentId)]
            guard let url = comps.url else { return }
            var req = URLRequest(url: url)
            req.addEngineAuth()
            let (data, _) = try await URLSession.shared.data(for: req)
            let resp = try JSONDecoder().decode(NoteListResponse.self, from: data)
            notes = resp.items
        } catch {
            self.error = error.localizedDescription
            logger.error("load notes failed: \(error.localizedDescription)")
        }
    }

    func create(body: String, linkedDocumentId: String) async throws -> NoteItem {
        guard let url = URL(string: base) else { throw NoteServiceError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addEngineAuth()
        let payload = NoteCreateBody(title: nil, body: body, linkedDocumentIds: [linkedDocumentId])
        req.httpBody = try JSONEncoder().encode(payload)
        let (data, _) = try await URLSession.shared.data(for: req)
        let note = try JSONDecoder().decode(NoteItem.self, from: data)
        notes.insert(note, at: 0)
        return note
    }

    func update(noteId: String, body: String) async throws -> NoteItem {
        guard let url = URL(string: "\(base)/\(noteId)") else { throw NoteServiceError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "PATCH"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addEngineAuth()
        req.httpBody = try JSONEncoder().encode(NotePatchBody(body: body))
        let (data, _) = try await URLSession.shared.data(for: req)
        let updated = try JSONDecoder().decode(NoteItem.self, from: data)
        if let idx = notes.firstIndex(where: { $0.id == noteId }) {
            notes[idx] = updated
        }
        return updated
    }

    func delete(noteId: String) async throws {
        guard let url = URL(string: "\(base)/\(noteId)") else { throw NoteServiceError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.addEngineAuth()
        _ = try await URLSession.shared.data(for: req)
        notes.removeAll { $0.id == noteId }
    }
}

enum NoteServiceError: LocalizedError {
    case invalidURL

    var errorDescription: String? { "Invalid URL" }
}
