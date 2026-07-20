import FicheroAPIClient
import Foundation

extension ResearchService {
    // MARK: - Checklists

    func loadChecklists(projectId: String) async throws -> [ResearchChecklist] {
        let response = try await client.api.listChecklistsApiResearchProjectsProjectIdChecklistsGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchChecklist.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createChecklist(
        projectId: String,
        title: String,
        itemLabels: [String] = [],
        taskId: String? = nil
    ) async throws -> ResearchChecklist {
        let body = Components.Schemas.ChecklistCreateRequest(
            projectId: projectId,
            taskId: taskId,
            title: title,
            items: itemLabels.map { .init(label: $0) }
        )
        let response = try await client.api.createChecklistApiResearchChecklistsPost(
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

    func toggleChecklistItem(
        checklistId: String,
        itemId: String,
        checked: Bool,
        notes: String = ""
    ) async throws -> ResearchChecklist {
        let body = Components.Schemas.ChecklistItemToggleRequest(checked: checked, notes: notes)
        let response = try await client.api.toggleChecklistItemApiResearchChecklistsChecklistIdItemsItemIdPatch(
            .init(
                path: .init(checklistId: checklistId, itemId: itemId),
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
