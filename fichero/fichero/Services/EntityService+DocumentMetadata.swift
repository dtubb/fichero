import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - Document prototype assignment (#1377)

    @discardableResult
    func assignDocumentPrototype(
        documentId: String,
        prototypeKey: String
    ) async throws -> Components.Schemas.PrototypeAssignResponse {
        let response = try await client.api.assignDocumentPrototypeApiDocumentsDocIdPrototypePut(
            path: .init(docId: documentId),
            body: .json(.init(prototypeKey: prototypeKey))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Document workflow provenance (#1434)

    func listDocumentWorkflowRuns(
        documentId: String
    ) async throws -> [Components.Schemas.WorkflowRunProvenanceResponse] {
        let response = try await client.api.getDocumentWorkflowRunsApiDocumentsDocIdWorkflowRunsGet(
            path: .init(docId: documentId),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Hermeneutics interpretations per document

    /// Fetch interpretations for a document through the generated OpenAPI client.
    func listDocumentInterpretations(
        documentId: String
    ) async throws -> [Components.Schemas.Interpretation] {
        let response = try await client.api.listInterpretationsApiHermeneuticsInterpretationsGet(
            query: .init(documentId: documentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// GET /api/hermeneutics/frameworks through the generated OpenAPI client.
    func listFrameworks() async throws -> [Components.Schemas.InterpretiveFramework] {
        let response = try await client.api.listFrameworksApiHermeneuticsFrameworksGet(query: .init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// PATCH /api/hermeneutics/interpretations/{id} — update text and/or confidence.
    @discardableResult
    func updateInterpretation(
        interpretationId: String,
        interpretationText: String,
        confidence: Double
    ) async throws -> Components.Schemas.Interpretation {
        let response = try await client.api.updateInterpretationApiHermeneuticsInterpretationsInterpretationIdPatch(
            path: .init(interpretationId: interpretationId),
            body: .json(.init(interpretationText: interpretationText, confidence: confidence))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// POST /api/hermeneutics/interpretations — create a human interpretation on a document.
    @discardableResult
    func createInterpretation(
        frameworkId: String,
        documentId: String,
        act: Components.Schemas.InterpretiveActType,
        interpretationText: String,
        confidence: Double = 0.8
    ) async throws -> Components.Schemas.Interpretation {
        let response = try await client.api.createInterpretationApiHermeneuticsInterpretationsPost(
            body: .json(.init(
                frameworkId: frameworkId,
                documentId: documentId,
                interpretationText: interpretationText,
                act: act,
                confidence: confidence,
                createdBy: "human"
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
