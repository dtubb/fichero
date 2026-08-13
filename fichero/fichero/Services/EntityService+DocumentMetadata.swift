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

    // MARK: - Prototype-declared attributes (datasets Stage 1)

    /// One attribute declaration resolved from the prototype chain.
    struct AttributeDeclaration: Identifiable, Equatable, Sendable {
        let name: String
        let type: String
        let role: String?
        let options: [String]
        let required: Bool
        var id: String { name }

        init?(name: String, raw: (any Sendable)?) {
            guard let dict = raw as? [String: (any Sendable)?] else { return nil }
            self.name = name
            self.type = dict["type"] as? String ?? "text"
            self.role = dict["role"] as? String
            self.options = (dict["options"] as? [(any Sendable)?])?.compactMap { $0 as? String } ?? []
            self.required = dict["required"] as? Bool ?? false
        }
    }

    /// A node's structured data, resolved: declarations from the prototype
    /// chain, effective values (defaults overlaid with the node's own), and
    /// the node's OWN dict — the wholesale-replace base for saves.
    struct EffectiveAttributes: Sendable {
        let prototypeKey: String?
        let declarations: [AttributeDeclaration]
        let values: [String: (any Sendable)?]
        let ownValues: [String: (any Sendable)?]
    }

    /// GET /api/documents/{id}/effective-attributes plus the document's own
    /// `attributes` dict. Two requests because effective values alone cannot
    /// seed an edit: PATCH replaces the node's own dict wholesale, and merged
    /// values would bake prototype defaults into the node.
    func effectiveAttributes(documentId: String) async throws -> EffectiveAttributes {
        let response = try await client.api.getEffectiveAttributesApiDocumentsDocIdEffectiveAttributesGet(
            path: .init(docId: documentId)
        )
        let resolved: Components.Schemas.EffectiveAttributesResponse
        switch response {
        case .ok(let okResponse):
            resolved = try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Unresolvable prototype")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }

        let docResponse = try await client.api.getDocumentApiDocumentsDocIdGet(
            .init(path: .init(docId: documentId))
        )
        guard case .ok(let okDoc) = docResponse else {
            throw ServiceError.validationError("Document \(documentId) not found")
        }
        let own = try okDoc.body.json.attributes?.additionalProperties.value ?? [:]

        let rawDeclarations = resolved.declarations.additionalProperties.value
        let declarations = rawDeclarations
            .compactMap { AttributeDeclaration(name: $0.key, raw: $0.value) }
            .sorted { lhs, rhs in
                // Title-role first — it names the row everywhere else.
                if (lhs.role == "title") != (rhs.role == "title") { return lhs.role == "title" }
                return lhs.name < rhs.name
            }
        return EffectiveAttributes(
            prototypeKey: resolved.prototypeKey,
            declarations: declarations,
            values: resolved.values.additionalProperties.value,
            ownValues: own
        )
    }

    /// PUT /api/documents/{id} with only `attributes` set — wholesale replace
    /// of the node's own dict, mirroring the metadata contract.
    func updateDocumentAttributes(
        documentId: String,
        attributes: [String: (any Sendable)?]
    ) async throws {
        let container = try OpenAPIObjectContainer(unvalidatedValue: attributes)
        let response = try await client.api.updateDocumentApiDocumentsDocIdPut(.init(
            path: .init(docId: documentId),
            body: .json(.init(attributes: .init(additionalProperties: container)))
        ))
        switch response {
        case .ok:
            return
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
