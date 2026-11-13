import FicheroAPIClient
import Foundation

/// What a paired Mac says about itself (#6556): which libraries it has open now, and every address it is reached at.
extension PairingService {
    /// The libraries the host has open now (`GET /api/registry/open`).
    func openLibraryPaths() async throws -> [String] {
        let response = try await client.api.listOpenLibrariesApiRegistryOpenGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.libraries.filter { $0.isOpen != false }.map(\.path)
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    /// The addresses the host lists for itself (`GET /api/health`, `sharing.addresses`): its `.local` name, its tailnet
    /// name, its LAN address. Empty when the host reports none.
    func ownAddresses() async throws -> [String] {
        let response = try await client.api.healthCheckApiHealthGet(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.sharing?.addresses.map(\.url) ?? []
        default:
            throw APIError.httpError(statusCode: -1, message: "Unexpected response")
        }
    }
}
