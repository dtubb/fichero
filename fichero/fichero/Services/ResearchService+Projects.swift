import FicheroAPIClient
import Foundation

extension ResearchService {
    // MARK: - Projects

    func loadProjects() async {
        isLoading = true
        error = nil
        do {
            let response = try await client.api.listProjectsApiResearchProjectsGet(
                .init()
            )
            switch response {
            case .ok(let okResponse):
                projects = try decodeModels(from: try okResponse.body.json.items, as: ResearchProject.self)
            case .unprocessableContent, .undocumented:
                throw ServiceError.unexpectedResponse
            }
        } catch {
            // Superseded/cancelled load is not a failure — skip logging and the
            // error state, but still clear `isLoading` below.
            if !error.isCancellationError {
                self.error = error.localizedDescription
                logger.error("Failed to load research projects: \(error.localizedDescription)")
            }
        }
        isLoading = false
    }

    func createProject(
        name: String,
        description: String = "",
        folderDestinationId: String? = nil
    ) async throws -> ResearchProject {
        let body = Components.Schemas.FicheroServerApiRoutesResearchCrudProjectCreateRequest(
            name: name,
            description: description,
            libraryDestinationFolderId: folderDestinationId
        )
        let response = try await client.api.createProjectApiResearchProjectsPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            let project: ResearchProject = try decodeModel(from: try okResponse.body.json)
            projects.append(project)
            return project
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateProject(_ project: ResearchProject) async throws {
        let body = Components.Schemas.ProjectUpdateRequest(
            name: project.name,
            description: project.description,
            status: projectStatus(project.status),
            libraryDestinationFolderId: project.libraryDestinationFolderId
        )
        let response = try await client.api.updateProjectApiResearchProjectsProjectIdPatch(
            .init(
                path: .init(projectId: project.id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            let updated: ResearchProject = try decodeModel(from: try okResponse.body.json)
            if let idx = projects.firstIndex(where: { $0.id == project.id }) {
                projects[idx] = updated
            }
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func deleteProject(id: String) async throws {
        let response = try await client.api.deleteProjectApiResearchProjectsProjectIdDelete(
            .init(
                path: .init(projectId: id),
            )
        )
        switch response {
        case .ok:
            projects.removeAll { $0.id == id }
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }
}
