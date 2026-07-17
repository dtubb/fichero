import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

/// Service for interacting with app integrations (DEVONthink, Bookends, Tinderbox).
///
/// Routes through the generated OpenAPI client (FicheroClient → AuthTokenMiddleware
/// + LibraryPathMiddleware) instead of hand-written URLSession requests (#1666/#1713).
/// Integrations endpoints are **app-level** (they target external desktop apps,
/// not a particular `.fichero` library) and the former URLSession path sent only
/// the engine Bearer token with no library header — so this mirrors
/// `ModelComparisonService`, using the configured engine client purely to carry auth.
///
/// The `+AppSpecific` extension lives in a separate file but is the *same* type:
/// both halves share this `client` and the mapping helpers below, so there is a
/// single consistent transport for every `/api/integrations/*` call.
@MainActor
@Observable
final class IntegrationsService {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "IntegrationsService")
    private nonisolated var hostChangeObservation: NSObjectProtocol?

    var integrations: [AppIntegration] = []
    var isLoading = false
    var error: String?

    /// App-wide client (auth only, no library scope) — see type doc.
    let client: FicheroClient

    init(client: FicheroClient = FicheroClient(baseURL: EngineConfig.host)) {
        self.client = client
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.reconfigureBackendHost()
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    func reconfigureBackendHost() {
        client.reconfigure(baseURL: EngineConfig.host)
    }

    // MARK: - Response Mapping Helpers

    /// Bridge a generated typed schema (e.g. `IntegrationInfo`, `IntegrationItem`)
    /// into the matching app model. The generated schemas encode to the same
    /// snake_case wire bytes the former URLSession decoders consumed, so this is
    /// a 1:1 mapping. `internal` so the `+AppSpecific` extension can reuse it.
    func decodeModel<T: Decodable>(from value: some Encodable, as _: T.Type = T.self) throws -> T {
        let data = try JSONEncoder().encode(value)
        return try JSONDecoder().decode(T.self, from: data)
    }

    /// Bridge a list of free-form response containers (the backend returns
    /// open `items` / `databases` / `libraries` / `documents` arrays) into app
    /// models, mirroring the proven `NoteService` container-decode pattern.
    func decodeModels<T: Decodable>(from containers: [OpenAPIValueContainer], as _: T.Type = T.self) throws -> [T] {
        try containers.map { container in
            guard let object = container.value else { throw IntegrationsError.serverError }
            let data = try JSONSerialization.data(withJSONObject: object)
            return try JSONDecoder().decode(T.self, from: data)
        }
    }

    /// Build an `OpenAPIObjectContainer` from a string map for request bodies
    /// (export metadata, Tinderbox attributes).
    func objectContainer(from dict: [String: String]) throws -> OpenAPIRuntime.OpenAPIObjectContainer {
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(OpenAPIRuntime.OpenAPIObjectContainer.self, from: data)
    }

    // MARK: - Integration Management

    /// Load all available integrations
    func loadIntegrations() async {
        isLoading = true
        error = nil

        do {
            let response = try await client.api.listIntegrationsApiIntegrationsGet(headers: .init())
            switch response {
            case .ok(let okResponse):
                let body = try okResponse.body.json
                integrations = try decodeModels(from: body.items, as: AppIntegration.self)
                logger.info("Loaded \(self.integrations.count) integrations")
            case .undocumented(let statusCode, _):
                logger.error("Failed to load integrations: HTTP \(statusCode)")
                throw IntegrationsError.serverError
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load integrations: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Refresh a specific integration's status
    func refreshIntegration(_ name: String) async -> AppIntegration? {
        do {
            let response = try await client.api.refreshIntegrationApiIntegrationsAppNameRefreshPost(
                path: .init(appName: name.lowercased()),
                headers: .init()
            )
            switch response {
            case .ok(let okResponse):
                let integration: AppIntegration = try decodeModel(from: try okResponse.body.json)
                // Update in list
                if let index = integrations.firstIndex(where: { $0.name.lowercased() == name.lowercased() }) {
                    integrations[index] = integration
                }
                return integration
            case .unprocessableContent:
                logger.error("Failed to refresh \(name): validation error")
                return nil
            case .undocumented(let statusCode, _):
                logger.error("Failed to refresh \(name): HTTP \(statusCode)")
                return nil
            }
        } catch {
            logger.error("Failed to refresh \(name): \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - List Items

    /// List items from an integration
    func listItems(
        from appName: String,
        limit: Int = 100,
        search: String? = nil,
        database: String? = nil,
        container: String? = nil
    ) async throws -> [IntegrationItem] {
        let response = try await client.api.listItemsApiIntegrationsAppNameItemsGet(
            path: .init(appName: appName.lowercased()),
            query: .init(
                limit: limit,
                search: (search?.isEmpty == false) ? search : nil,
                database: database,
                container: container
            ),
            headers: .init()
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return try decodeModels(from: body.items, as: IntegrationItem.self)
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented(let statusCode, _):
            // The backend signals "app not running" with 503 (#1666 parity).
            if statusCode == 503 {
                throw IntegrationsError.appNotAvailable(appName)
            }
            throw IntegrationsError.serverError
        }
    }

    /// Get a specific item
    func getItem(from appName: String, externalId: String) async throws -> IntegrationItem {
        let response = try await client.api.getItemApiIntegrationsAppNameItemsExternalIdGet(
            path: .init(appName: appName.lowercased(), externalId: externalId),
            headers: .init()
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    // MARK: - Import/Export

    /// Import an item from an integration
    func importItem(
        from appName: String,
        externalId: String,
        targetPath: String? = nil
    ) async throws -> ImportResult {
        let response = try await client.api.importItemApiIntegrationsAppNameImportPost(
            path: .init(appName: appName.lowercased()),
            headers: .init(),
            body: .json(.init(externalId: externalId, targetPath: targetPath))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// Export a file to an integration
    func exportItem(
        to appName: String,
        filePath: String,
        metadata: [String: String]? = nil,
        database: String? = nil,
        group: String? = nil,
        container: String? = nil,
        prototype: String? = nil
    ) async throws -> ExportResult {
        let metadataPayload = try metadata.map {
            Components.Schemas.FicheroApiRoutesIntegrationsExportRequest.MetadataPayload(
                additionalProperties: try objectContainer(from: $0)
            )
        }
        let response = try await client.api.exportItemApiIntegrationsAppNameExportPost(
            path: .init(appName: appName.lowercased()),
            headers: .init(),
            body: .json(.init(
                filePath: filePath,
                metadata: metadataPayload,
                database: database,
                group: group,
                container: container,
                prototype: prototype
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

    /// Open an item in its native app
    func openItem(in appName: String, externalId: String) async throws -> Bool {
        let response = try await client.api.openItemApiIntegrationsAppNameOpenExternalIdPost(
            path: .init(appName: appName.lowercased(), externalId: externalId),
            headers: .init()
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.success
        case .unprocessableContent:
            throw IntegrationsError.serverError
        case .undocumented:
            throw IntegrationsError.serverError
        }
    }

}
