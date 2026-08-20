import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentService")

// MARK: - Flat listings + batch fetch (split from DocumentService.swift at the
// 1000-line error threshold, 2026-08-20 — same members, only the file moved)

extension DocumentService {
    /// Fetch exactly these documents in ONE round-trip (perf audit
    /// 2026-08-19: the change-stream patch flush issued one GET per id —
    /// 1,001 requests in a session). Missing/deleted ids are simply absent
    /// from the result; order follows the engine, so callers keying by id
    /// must not assume input order.
    func getDocuments(ids: [String]) async throws -> [Document] {
        guard !ids.isEmpty else { return [] }
        let response = try await client.api.listDocumentsApiDocumentsGet(
            .init(query: .init(ids: ids.joined(separator: ",")))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map { try convertToDocument($0) }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    func listDocuments(limit: Int? = nil) async throws -> [Document] {
        logger.info("Listing documents (limit \(limit.map(String.init) ?? "default"))")

        let response = try await client.api.listDocumentsApiDocumentsGet(
            .init(query: .init(limit: limit))
        )

        switch response {
        case .ok(let okResponse):
            let docs = try okResponse.body.json
            logger.info("Found \(docs.items.count) documents")
            return try docs.items.map { try convertToDocument($0) }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }
}
