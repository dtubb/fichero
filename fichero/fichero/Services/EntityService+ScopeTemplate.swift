import FicheroAPIClient
import Foundation

// MARK: - A scope's template and its saved column choice (attributes-and-prototypes.md §3, #6282)
//
// The columns are the engine's (`GET /api/documents/{id}/template`); the app shows them and never
// computes them. A person's narrowing is saved on the scope as a view by an audited action, so ⌘Z
// takes it back: `ScopeColumnChoice.registerUndo` files the audit row the answer names.

extension EntityService {
    /// The scope's columns, narrowed by its saved choice.
    func scopeTemplate(documentId: String) async throws -> Components.Schemas.ScopeTemplate {
        let response = try await client.api.getScopeTemplateApiDocumentsDocIdTemplateGet(
            path: .init(docId: documentId)
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

    /// Hide columns, or show one kind's columns only. Saved on the scope, never on a prototype.
    func setColumnChoice(
        documentId: String, hide: [String] = [], onlyKind: String? = nil
    ) async throws -> Components.Schemas.ColumnChoiceAnswer {
        let response = try await client.api.putColumnChoiceApiDocumentsDocIdColumnChoicePut(
            path: .init(docId: documentId),
            body: .json(.init(hide: hide, onlyKind: onlyKind))
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

    /// Back to the union of the rows' columns.
    func clearColumnChoice(documentId: String) async throws -> Components.Schemas.ColumnChoiceAnswer {
        let response = try await client.api.clearColumnChoiceApiDocumentsDocIdColumnChoiceDelete(
            path: .init(docId: documentId)
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

extension Components.Schemas.ColumnChoiceAnswer {
    /// ⌘Z for this choice, by the audit row the engine wrote (`undo.one-path`).
    @MainActor
    @discardableResult
    func registerUndo(
        named name: String = "Change Columns", service: (any UndoSetEngine)?, steps: WindowSteps?,
        afterChange: @escaping @MainActor () async -> Void = {}
    ) -> ActionUndo.Handle? {
        UndoableChange.register(
            [auditId].compactMap { $0 }, named: name, service: service, steps: steps, afterEach: afterChange
        )
    }
}
