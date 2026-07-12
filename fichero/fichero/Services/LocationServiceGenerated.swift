import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LocationServiceGenerated")

/// Resolves navigation anchors through the engine's single
/// `POST /api/locations/resolve` route (#3576/#3577). Page-child → parent
/// resolution (and page-range validation) now lives ONCE in the engine, so
/// every UI/MCP caller shares it instead of re-implementing it client-side.
/// Mirrors `DocumentServiceGenerated`: a thin service over the generated
/// OpenAPI client — no hand-rolled URLSession.
@MainActor
class LocationServiceGenerated {
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Resolve a `Location` to its parent document + resolved page. Throws on
    /// 404 (document/parent missing) or 422 (out-of-range) so callers can fall
    /// back to their legacy navigation path — a reveal must never crash.
    func resolve(_ location: Components.Schemas.Location) async throws -> Components.Schemas.ResolvedLocation {
        let response = try await client.api.resolveLocationApiLocationsResolvePost(.init(
            body: .json(location)
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw LocationServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw LocationServiceError.unexpectedResponse(statusCode)
        }
    }
}

enum LocationServiceError: Error {
    case validationError(String)
    case unexpectedResponse(Int)
}
