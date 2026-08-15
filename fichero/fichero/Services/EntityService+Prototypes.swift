import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Document prototype CRUD (datasets Stage 1, slice B)
//
// The editor's write path onto the classifications routes — the SAME audited
// CRUD the engine has always had (#1377); Stage 1 only added the typed
// `attributes` field. All through generated ops (knowledge-consistency
// mandate): the legacy `endpointData` classification wrappers in
// EntityService+Claims are not used here.

extension EntityService {
    /// The closed schema vocabularies, mirroring
    /// `models/prototype_schema.py`. The server validates on save (422, loud)
    /// — these exist so the editor's pickers can only OFFER legal values.
    enum PrototypeSchema {
        static let attributeTypes = [
            "text", "long_text", "number", "date", "select", "multi_select",
            "checkbox", "rating", "url", "geo", "media",
            "document_ref", "entity_ref", "claim_ref"
        ]
        static let attributeRoles = ["title", "date", "geo", "media", "subtitle"]
    }

    /// One typed attribute row as edited in the prototype editor. Serializes
    /// to the dict-declaration convention the engine validates; parses back
    /// from both typed declarations and legacy plain defaults.
    struct PrototypeAttributeDraft: Identifiable, Equatable {
        let id = UUID()
        var name: String
        var type: String = "text"
        /// Renderer role; empty string = none (Picker-friendly).
        var role: String = ""
        var defaultValue: String = ""
        /// Vocabulary for select / multi_select, comma-edited in the UI.
        var optionsCSV: String = ""
        var required = false

        init(name: String = "") {
            self.name = name
        }

        init?(name: String, raw: (any Sendable)?) {
            self.name = name
            if let dict = raw as? [String: (any Sendable)?] {
                guard let type = dict["type"] as? String else { return nil }
                self.type = type
                self.role = dict["role"] as? String ?? ""
                if let value = dict["default"], let value { self.defaultValue = "\(value)" }
                let options = (dict["options"] as? [(any Sendable)?])?
                    .compactMap { $0 as? String } ?? []
                self.optionsCSV = options.joined(separator: ", ")
                self.required = dict["required"] as? Bool ?? false
            } else if let raw {
                // Legacy plain value = untyped text default (builtin seeds).
                self.type = "text"
                self.defaultValue = "\(raw)"
            }
        }

        /// The wire dict. Empty/default fields are omitted so a plain text
        /// attribute round-trips small.
        var payload: [String: (any Sendable)?] {
            var decl: [String: (any Sendable)?] = ["type": type]
            if !role.isEmpty { decl["role"] = role }
            if !defaultValue.isEmpty { decl["default"] = defaultValue }
            let options = optionsCSV
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            if !options.isEmpty { decl["options"] = options }
            if required { decl["required"] = true }
            return decl
        }
    }

    /// Parse a prototype row's stored attributes into editable drafts.
    static func attributeDrafts(
        from value: Components.Schemas.ClassificationValue
    ) -> [PrototypeAttributeDraft] {
        let raw = value.attributes?.additionalProperties.value ?? [:]
        return raw
            .compactMap { PrototypeAttributeDraft(name: $0.key, raw: $0.value) }
            .sorted { $0.name < $1.name }
    }

    private func attributesPayload(
        _ drafts: [PrototypeAttributeDraft]
    ) throws -> OpenAPIObjectContainer {
        var dict: [String: (any Sendable)?] = [:]
        for draft in drafts {
            let name = draft.name.trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { continue }
            dict[name] = draft.payload
        }
        return try OpenAPIObjectContainer(unvalidatedValue: dict)
    }

    @discardableResult
    func createDocumentPrototype(
        key: String,
        label: String,
        parentKey: String?,
        color: String?,
        attributes: [PrototypeAttributeDraft]
    ) async throws -> Components.Schemas.ClassificationValue {
        let response = try await client.api.createValueApiClassificationsPost(
            body: .json(.init(
                dimension: .documentPrototype,
                key: key,
                label: label,
                parentKey: parentKey,
                color: color,
                attributes: .init(additionalProperties: try attributesPayload(attributes))
            ))
        )
        switch response {
        case .ok(let okResponse):
            let data = try JSONEncoder().encode(try okResponse.body.json)
            return try JSONDecoder().decode(Components.Schemas.ClassificationValue.self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func updateDocumentPrototype(
        valueId: String,
        label: String,
        parentKey: String?,
        color: String?,
        attributes: [PrototypeAttributeDraft]
    ) async throws {
        let response = try await client.api.patchValueApiClassificationsValueIdPatch(
            path: .init(valueId: valueId),
            body: .json(.init(
                label: label,
                parentKey: parentKey,
                color: color,
                attributes: .init(additionalProperties: try attributesPayload(attributes))
            ))
        )
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

    func deleteDocumentPrototype(valueId: String) async throws {
        let response = try await client.api.deleteValueApiClassificationsValueIdDelete(
            path: .init(valueId: valueId)
        )
        switch response {
        case .noContent:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// The chain-merged declarations for a prototype key — the editor's
    /// inheritance preview. 422 (unknown key / cycle) surfaces as an error,
    /// never partial data.
    func resolvedPrototypeDeclarations(
        key: String
    ) async throws -> [AttributeDeclaration] {
        let response = try await client.api.resolvedPrototypeApiClassificationsResolvedKeyGet(
            path: .init(key: key)
        )
        switch response {
        case .ok(let okResponse):
            let resolved = try okResponse.body.json
            return resolved.declarations.additionalProperties.value
                .compactMap { AttributeDeclaration(name: $0.key, raw: $0.value) }
                .sorted { $0.name < $1.name }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Unresolvable prototype")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
