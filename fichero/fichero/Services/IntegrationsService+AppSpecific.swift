import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - App-Specific Methods
//
// These are part of the SAME `IntegrationsService` type as the core file — they
// share its `client` and mapping helpers (`decodeModels`, `objectContainer`) so
// there is one consistent generated-client transport for every endpoint (#1713).

extension IntegrationsService {

    /// List DEVONthink databases
    func listDEVONthinkDatabases() async throws -> [DEVONthinkDatabase] {
        let response = try await client.api
            .listDevonthinkDatabasesApiIntegrationsDevonthinkDatabasesGet(headers: .init())
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return try decodeModels(from: body.databases, as: DEVONthinkDatabase.self)
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// List Bookends libraries
    func listBookendsLibraries() async throws -> [BookendsLibrary] {
        let response = try await client.api.listBookendsLibrariesApiIntegrationsBookendsLibrariesGet(headers: .init())
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return try decodeModels(from: body.libraries, as: BookendsLibrary.self)
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// Get a formatted citation from Bookends
    func getBookendsCitation(externalId: String, style: String = "APA") async throws -> String {
        let response = try await client.api.getBookendsCitationApiIntegrationsBookendsCitationExternalIdGet(
            path: .init(externalId: externalId),
            query: .init(style: style),
            headers: .init()
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.citation
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// List Tinderbox documents
    func listTinderboxDocuments() async throws -> [TinderboxDocument] {
        let response = try await client.api.listTinderboxDocumentsApiIntegrationsTinderboxDocumentsGet(headers: .init())
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return try decodeModels(from: body.documents, as: TinderboxDocument.self)
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// Create a Tinderbox note
    func createTinderboxNote(
        name: String,
        text: String = "",
        container: String? = nil,
        prototype: String? = nil,
        attributes: [String: String]? = nil
    ) async throws -> String {
        let attributesPayload = try attributes.map {
            Components.Schemas.CreateNoteRequest.AttributesPayload(
                additionalProperties: try objectContainer(from: $0)
            )
        }
        let response = try await client.api.createTinderboxNoteApiIntegrationsTinderboxNotesPost(
            headers: .init(),
            body: .json(.init(
                name: name,
                text: text,
                container: container,
                prototype: prototype,
                attributes: attributesPayload
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.id
        case .unprocessableContent:
            throw IntegrationsError.createFailed
        case .undocumented:
            throw IntegrationsError.createFailed
        }
    }
}
