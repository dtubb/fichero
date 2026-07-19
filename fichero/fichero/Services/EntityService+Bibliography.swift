import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - Bibliography (per-document metadata)

    /// Fetch bibliographic metadata for a document — title, authors,
    /// year, container, identifiers, etc. The backend stores
    /// extractor-emitted bib data alongside user edits and merges them.
    /// Backed by `/api/bibliography/document/{document_id}`.
    func bibliographyMetadata(
        forDocumentId documentId: String
    ) async throws -> Components.Schemas.MetadataResponse {
        let response = try await client.api.getMetadataApiBibliographyDocumentDocumentIdGet(
            path: .init(documentId: documentId),
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

    /// Set bibliographic metadata for a document. ⚠️ The backend **replaces**
    /// `source_metadata` wholesale — unspecified keys (including extractor-
    /// emitted fields like canonical BibTeX / identifiers) are DROPPED, not
    /// merged. To preserve them, GET the current metadata and merge client-side
    /// before calling. (#3253: this documents today's behavior so a metadata
    /// editor built on this wrapper doesn't silently destroy fields; the
    /// eventual merge-vs-replace semantics are a pending product decision.)
    /// Pass the full key/value set the bibliography editor supports — title,
    /// authors, year, container_title, etc.
    /// Backed by `PATCH /api/bibliography/document/{document_id}`.
    func patchBibliographyMetadata(
        forDocumentId documentId: String,
        metadata: [String: any Sendable]
    ) async throws -> Components.Schemas.MetadataResponse {
        let payload = Components.Schemas.MetadataPatchRequest.MetadataPayload(
            additionalProperties: try .init(unvalidatedValue: metadata)
        )
        let body = Components.Schemas.MetadataPatchRequest(metadata: payload)
        let response = try await client.api.patchMetadataApiBibliographyDocumentDocumentIdPatch(
            path: .init(documentId: documentId),
            body: .json(body)
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

    /// Trigger the bibliography extractor on a document — re-runs the
    /// LLM-backed metadata extraction and replaces extractor-emitted
    /// fields (user-edited fields are preserved per the backend's merge
    /// rule). Backed by
    /// `POST /api/bibliography/document/{document_id}/extract`.
    func runBibliographyExtractor(
        forDocumentId documentId: String
    ) async throws -> Components.Schemas.MetadataResponse {
        let response = try await client.api.runExtractorApiBibliographyDocumentDocumentIdExtractPost(
            path: .init(documentId: documentId),
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

    private func bibliographyData(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> Data {
        try await endpointData(
            path: path,
            method: method,
            queryItems: queryItems,
            jsonBody: jsonBody
        )
    }

    private func bibliographyText(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> String {
        let data = try await bibliographyData(
            path: path,
            method: method,
            queryItems: queryItems,
            jsonBody: jsonBody
        )
        return String(data: data, encoding: .utf8) ?? ""
    }

    func exportBibliographyBib(documentIds: [String]) async throws -> String {
        try await bibliographyText(
            path: "/api/bibliography/export.bib",
            method: "POST",
            jsonBody: ["document_ids": documentIds]
        )
    }

    func importBibliography(text: String, format: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let format {
            body["format"] = format
        }
        return try await bibliographyData(
            path: "/api/bibliography/import",
            method: "POST",
            jsonBody: body
        )
    }

    func resolveBibliography(
        doi: String? = nil,
        isbn: String? = nil,
        documentId: String? = nil
    ) async throws -> Data {
        var body: [String: Any] = [:]
        if let doi {
            body["doi"] = doi
        }
        if let isbn {
            body["isbn"] = isbn
        }
        let queryItems = documentId.map {
            [URLQueryItem(name: "document_id", value: $0)]
        } ?? []
        return try await bibliographyData(
            path: "/api/bibliography/resolve",
            method: "POST",
            queryItems: queryItems,
            jsonBody: body
        )
    }

    func renderDocumentCitation(
        documentId: String,
        style: String = "bibtex"
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/citations/document/\(documentId)",
            queryItems: [URLQueryItem(name: "style", value: style)]
        )
    }

    func documentBibtexCitation(documentId: String) async throws -> String {
        try await bibliographyText(path: "/api/citations/document/\(documentId).bib")
    }

    func exportCitationsBibtex(documentIds: [String]) async throws -> String {
        try await bibliographyText(
            path: "/api/citations/export",
            queryItems: documentIds.map {
                URLQueryItem(name: "document_ids", value: $0)
            }
        )
    }

    func listReferences(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await bibliographyData(
            path: "/api/references",
            queryItems: [
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "offset", value: "\(offset)")
            ]
        )
    }

    func getReference(_ referenceId: String) async throws -> Data {
        try await bibliographyData(path: "/api/references/\(referenceId)")
    }

    func patchReference(
        _ referenceId: String,
        patch: [String: Any]
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/references/\(referenceId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteReference(_ referenceId: String) async throws {
        _ = try await bibliographyData(
            path: "/api/references/\(referenceId)",
            method: "DELETE"
        )
    }

    func listSources() async throws -> Data {
        try await bibliographyData(path: "/api/sources")
    }

    func upsertSource(
        title: String,
        filePath: String,
        id: String? = nil,
        metadata: [String: Any] = [:]
    ) async throws -> Data {
        var body: [String: Any] = [
            "title": title,
            "file_path": filePath,
            "document_type": "source",
            "metadata": metadata
        ]
        if let id {
            body["id"] = id
        }
        return try await bibliographyData(
            path: "/api/sources",
            method: "POST",
            jsonBody: body
        )
    }

    func getSource(_ sourceId: String) async throws -> Data {
        try await bibliographyData(path: "/api/sources/\(sourceId)")
    }

    func updateSource(
        _ sourceId: String,
        title: String,
        filePath: String,
        metadata: [String: Any] = [:]
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/sources/\(sourceId)",
            method: "PUT",
            jsonBody: [
                "title": title,
                "file_path": filePath,
                "document_type": "source",
                "metadata": metadata
            ]
        )
    }

    func deleteSource(_ sourceId: String) async throws {
        _ = try await bibliographyData(
            path: "/api/sources/\(sourceId)",
            method: "DELETE"
        )
    }
}
