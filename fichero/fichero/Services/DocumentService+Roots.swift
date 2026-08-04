import FicheroAPIClient
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentService")

/// The sidebar's root listing — the load the whole library hangs off.
///
/// Split out of `DocumentService.swift` (which is at its 1000-line limit)
/// because this one call needs room to explain its failures properly: it is the
/// request whose 403 decides whether a library is *explained* or merely
/// *unloaded* (C3).
extension DocumentService {
    /// Get root-level documents.
    /// - Parameter sort: Server-side ordering, or nil for the stored order.
    /// - Returns: Array of root documents, in the order the server returned them.
    func getRoots(sort: ListingSort? = nil) async throws -> [Document] {
        logger.info("Fetching root documents sort: \(sort?.field ?? "default")")

        let response = try await client.api.listRootsApiDocumentsRootsGet(.init(
            query: .init(sortBy: sort?.field, sortDirection: sort?.direction)
        ))

        switch response {
        case .ok(let okResponse):
            let docs = try okResponse.body.json
            logger.info("Found \(docs.count) root documents")
            return try docs.items.map { try convertToDocument($0) }

        case .undocumented(let statusCode, let payload):
            // C3: every non-200 threw `.unexpectedResponse`, which discarded
            // both the status code and the sentence the engine wrote for the
            // user — e.g. "Library path is not in an allowed location or not a
            // .fichero package." for a library outside the engine's allowlist.
            // `LibraryView` renders `LibraryAccessDeniedView` only when the
            // store's error IS an `AccessError`, so with the reason discarded
            // the denial pane could never appear and the library rendered as an
            // empty list. Carry the denial out TYPED, in the engine's words.
            if let denial = await AccessError.denial(statusCode: statusCode, payload: payload) {
                logger.error(
                    "list roots denied: HTTP \(statusCode) — \(denial.localizedDescription, privacy: .public)"
                )
                throw denial
            }
            // Not a denial: still name the operation and the REAL status code.
            logger.error("list roots failed: HTTP \(statusCode)")
            throw DocumentServiceError.httpStatus(operation: "list roots", code: statusCode)

        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        }
    }
}
