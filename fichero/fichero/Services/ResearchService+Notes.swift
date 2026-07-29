import FicheroAPIClient
import Foundation

extension ResearchService {
    // MARK: - Notes

    func loadNotes(projectId: String) async throws -> [ResearchNote] {
        let response = try await client.api.listNotesApiResearchProjectsProjectIdNotesGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchNote.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createNote(
        projectId: String,
        content: String,
        taskId: String? = nil,
        noteType: String = "observation",
        tags: [String] = []
    ) async throws -> ResearchNote {
        let body = Components.Schemas.FicheroServerApiRoutesResearchNotesNoteCreateRequest(
            projectId: projectId,
            taskId: taskId,
            noteType: researchNoteType(noteType),
            content: content,
            tags: tags
        )
        let response = try await client.api.createNoteApiResearchNotesPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func getNote(id: String) async throws -> ResearchNote {
        let response = try await client.api.getNoteApiResearchNotesNoteIdGet(
            .init(
                path: .init(noteId: id),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateNote(
        id: String,
        content: String? = nil,
        noteType: String? = nil,
        tags: [String]? = nil
    ) async throws -> ResearchNote {
        let body = Components.Schemas.NoteUpdateRequest(
            content: content,
            noteType: researchNoteType(noteType),
            tags: tags
        )
        let response = try await client.api.updateNoteApiResearchNotesNoteIdPatch(
            .init(
                path: .init(noteId: id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }
}
